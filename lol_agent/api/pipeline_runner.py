"""
Shortsyt API — async wrapper dla render_short()
Uruchamia pipeline w osobnym wątku, żeby nie blokować FastAPI.
"""
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple
import uuid

# Dodaj lol_agent do path
sys.path.insert(0, str(Path(__file__).parent.parent))


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class PipelineState:
    status: PipelineStatus = PipelineStatus.IDLE
    progress: int = 0          # 0-100%
    current_step: str = ""
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    pinned_comment: Optional[str] = None
    champion_name: Optional[str] = None
    action_type: Optional[str] = None
    rank: Optional[str] = None
    game_type: str = "lol"
    source_path: Optional[str] = None

    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    combat_segments: Optional[List[Tuple[float, float]]] = None
    qa_status: str = "PASS"
    qa_score: int = 100
    qa_details: List[str] = field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    logs: List[str] = field(default_factory=list)


# Globalny stan pipeline — singleton
_state = PipelineState()
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_cancel_event = threading.Event()
_active_proc = None


def set_active_subprocess(proc):
    """Zarejestruj aktywny proces podrzędny (FFmpeg/FFprobe) do ewentualnego przerwania."""
    global _active_proc
    with _lock:
        _active_proc = proc


def clear_active_subprocess():
    """Wyczyść referencję do procesu podrzędnego."""
    global _active_proc
    with _lock:
        _active_proc = None


def check_cancellation():
    """Rzuć wyjątek InterruptedError jeśli użytkownik zażądał zatrzymania pipeline."""
    if _cancel_event.is_set():
        raise InterruptedError("Pipeline został anulowany przez użytkownika")


def get_state() -> dict:
    """Zwróć aktualny stan pipeline jako dict."""
    with _lock:
        return {
            "status": _state.status.value,
            "progress": _state.progress,
            "current_step": _state.current_step,
            "output_path": _state.output_path,
            "thumbnail_path": _state.thumbnail_path,
            "title": _state.title,
            "description": _state.description,
            "pinned_comment": _state.pinned_comment,
            "champion_name": _state.champion_name,
            "action_type": _state.action_type,
            "rank": _state.rank,
            "game_type": _state.game_type,
            "source_path": _state.source_path,

            "clip_start": _state.clip_start,
            "clip_end": _state.clip_end,
            "combat_segments": _state.combat_segments,
            "qa_status": _state.qa_status,
            "qa_score": _state.qa_score,
            "qa_details": _state.qa_details,
            "error": _state.error,
            "started_at": _state.started_at,
            "finished_at": _state.finished_at,
            "logs": _state.logs[-50:],  # ostatnie 50 linii
        }


def _update(step: str, progress: int, log: Optional[str] = None):
    """Zaktualizuj stan w wątku pipeline."""
    with _lock:
        _state.current_step = step
        _state.progress = progress
        if log:
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log}")


def _run_pipeline(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str,
    champion_name: str,
    rank: str,
    peak_moment: float,
    hook_text: str,
    output_filename: str,
    use_speed_ramp: bool,
    use_zoom_punch: bool,
    use_smart_camera: bool,
    notify_token: Optional[str],
    combat_segments: Optional[List[Tuple[float, float]]] = None,
    game_type: str = "lol",
):
    """Główna funkcja pipeline — uruchamiana w osobnym wątku."""
    global _state

    try:
        with _lock:
            _state.status = PipelineStatus.RUNNING
            _state.progress = 0
            _state.started_at = datetime.now().isoformat()
            _state.output_path = None
            _state.thumbnail_path = None
            _state.title = None
            _state.description = None
            _state.pinned_comment = None
            _state.champion_name = champion_name
            _state.action_type = action_type
            _state.rank = rank
            _state.game_type = game_type
            _state.source_path = source_path
            _state.clip_start = clip_start
            _state.clip_end = clip_end
            _state.combat_segments = combat_segments

            _state.qa_status = "PASS"
            _state.qa_score = 100
            _state.qa_details = []
            _state.error = None
            _state.logs = []

        _update("Wykrywanie kill eventów", 5, f"Source: {source_path}")

        # ── Resolwuj source_path do pełnej ścieżki jeśli podano tylko filename ──
        if source_path and not Path(source_path).is_absolute() and not Path(source_path).exists():
            # Szukaj pliku w znanych katalogach nagrań
            candidate_dirs = [
                Path(__file__).parent.parent / "input_clips",
                Path(r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends"),
                Path(r"C:\Medal\Edits"),
            ]
            target_name = Path(source_path).name
            found_path = None
            for search_dir in candidate_dirs:
                if not search_dir.exists():
                    continue
                cand = search_dir / target_name
                if cand.is_file():
                    found_path = str(cand.resolve())
                    break
                try:
                    import os
                    for entry in os.scandir(search_dir):
                        if entry.is_dir():
                            sub_cand = Path(entry.path) / target_name
                            if sub_cand.is_file():
                                found_path = str(sub_cand.resolve())
                                break
                except Exception:
                    pass
                if found_path:
                    break

            if found_path:
                _update("Ścieżka klipu rozwiązana", 6, f"Znaleziono pełną ścieżkę: {found_path}")
                source_path = found_path
                with _lock:
                    _state.source_path = source_path
            else:
                raise FileNotFoundError(
                    f"Nie znaleziono pliku '{source_path}' w żadnym katalogu nagrań. "
                    f"Sprawdź czy plik istnieje: {[str(d) for d in candidate_dirs]}"
                )

        # Sprawdź czy plik istnieje
        if not Path(source_path).exists():
            raise FileNotFoundError(f"Plik źródłowy nie istnieje: {source_path}")

        # Safeguard: Sprawdź rzeczywistą długość wideo
        import cv2
        cap = cv2.VideoCapture(source_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        src_total_dur = frame_count / fps if fps > 0 else 30.0
        cap.release()

        # Jeśli przekazano domyślne okno (clip_start == 0.0 i clip_end <= 15.0), a klip ma > 20s:
        # Sprawdzamy czy akcja nie toczy się w dalszej części wideo, aby nie uciąć walki ani nie wyrenderować samego biegania!
        if src_total_dur > 20.0 and clip_start == 0.0 and clip_end <= 15.0:
            _update("Weryfikacja okna akcji", 7, f"Klip trwa {src_total_dur:.1f}s — sprawdzam pozycję akcji...")
            try:
                from lol_agent.lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window
                f_res = analyze_clip_frags(source_path, sample_fps=1.0)
                if f_res.kills:
                    auto_s, auto_e, auto_p, auto_segs = compute_optimal_clip_window(f_res, src_total_dur, action_type=action_type)
                    if auto_s > 2.0 or (auto_e - auto_s) > (clip_end - clip_start):
                        _update("Autocentrowanie na akcję", 8, f"Wykryto kille poza oknem początkowym! Przesuwam na {auto_s:.1f}s - {auto_e:.1f}s")
                        clip_start = auto_s
                        clip_end = auto_e
                        peak_moment = auto_p
                        if auto_segs and action_type.lower() not in ("solo_bolo", "solo", "1v1"):
                            combat_segments = auto_segs
                        if f_res.detected_frag_type:
                            action_type = f_res.detected_frag_type
                            if (not hook_text or hook_text.upper() in ("PENTAKILL", "OUTPLAY")) and action_type != "pentakill":
                                hook_text = getattr(f_res, "suggested_title_hook", "") or action_type.upper().replace("_", " ")
                        with _lock:
                            _state.clip_start = clip_start
                            _state.clip_end = clip_end
                            _state.combat_segments = combat_segments
                            _state.action_type = action_type
            except Exception as auto_ex:
                print(f"[pipeline_runner] Auto-centering warning: {auto_ex}")

        # Import tutaj żeby uniknąć circular import
        try:
            from lol_agent.smart_camera import detect_kill_events
        except ImportError:
            from smart_camera import detect_kill_events
        try:
            from lol_agent.lol_editor import render_short
        except ImportError:
            from lol_editor import render_short
        try:
            from lol_agent.lol_metadata_generator import generate_metadata
        except ImportError:
            from lol_metadata_generator import generate_metadata
        try:
            from lol_agent.lol_thumbnail import generate_thumbnail
        except ImportError:
            from lol_thumbnail import generate_thumbnail
        try:
            from lol_agent.tuning_manager import get_pacing_parameters
        except ImportError:
            try:
                from tuning_manager import get_pacing_parameters
            except ImportError:
                get_pacing_parameters = lambda: {}
        try:
            from lol_agent.lol_quality_validator import validate_pre_flight
        except ImportError:
            try:
                from lol_quality_validator import validate_pre_flight
            except ImportError:
                validate_pre_flight = None

        tuning_prof = get_pacing_parameters()

        # Krok 1 — detekcja kill / action eventów
        try:
            try:
                from lol_agent.game_event_detector import detect_kill_events as _detect_events
            except ImportError:
                from game_event_detector import detect_kill_events as _detect_events
            peaks = _detect_events(
                source_path, clip_start, clip_end,
                clip_duration=clip_end - clip_start,
                game_profile=game_type
            )
            _update("Kill detection gotowa", 12, f"Peaks: {peaks}")
        except Exception as e:
            try:
                peaks = detect_kill_events(
                    source_path, clip_start, clip_end,
                    clip_duration=clip_end - clip_start
                )
                _update("Kill detection gotowa (fallback)", 12, f"Peaks: {peaks}")
            except Exception as e2:
                _update("Kill detection pominięta", 12, f"Błąd detekcji: {e2}")
                peaks = []


        # Sprawdź czy kille mają lukę > 3.5s (martwe bieganie) i czy potrzeba jump-cut
        # Dla SOLO BOLO oraz klipów o ciągłej akcji <= 26s nie stosujemy jump-cutów
        total_clip_span = clip_end - clip_start
        if action_type.lower() in ("solo_bolo", "solo", "1v1") or total_clip_span <= 26.0:
            combat_segments = None
        elif not combat_segments and peaks and len(peaks) >= 2:
            sorted_p = sorted(peaks, key=lambda x: x[0])
            gaps = [sorted_p[i+1][0] - sorted_p[i][0] for i in range(len(sorted_p)-1)]
            if any(g > 3.5 for g in gaps):
                try:
                    from lol_agent.lol_momentum_analyzer import find_combat_segments
                except ImportError:
                    try:
                        from lol_momentum_analyzer import find_combat_segments
                    except ImportError:
                        find_combat_segments = None
                if find_combat_segments:
                    combat_segments = find_combat_segments(
                        peaks=peaks,
                        clip_start=clip_start,
                        clip_end=clip_end,
                        pre_roll=float(tuning_prof.get("buildup_sec", 0.8)),
                        post_roll=float(tuning_prof.get("outro_sec", 1.5)),
                        max_total_duration=float(tuning_prof.get("target_max_dur", 18.0)),
                    )
                    _update("Jump-Cut aktywny", 15, f"Wykryto przerwę w walce — aktywne {len(combat_segments)} segmenty")

        # Krok 1b — Pre-Flight Quality Validator
        qa_status = "PASS"
        qa_score = 100
        qa_details = []
        smart_cam_track = None
        if use_smart_camera:
            try:
                from lol_agent.smart_camera import find_action_path
                smart_cam_track = find_action_path(source_path, clip_start, clip_end)
            except Exception as se:
                print(f"Smart Camera QA track err: {se}")
        if validate_pre_flight:
            try:
                qa_res = validate_pre_flight(
                    video_path=source_path,
                    trim_start=clip_start,
                    trim_end=clip_end,
                    peaks=peaks,
                    smart_camera_track=smart_cam_track,
                    action_type=action_type,
                    combat_segments=combat_segments,
                    tuning_profile=tuning_prof,
                )
                qa_status = qa_res.qa_status
                qa_score = qa_res.qa_score
                qa_details = qa_res.diagnostic_details

                if qa_res.corrected_action_type:
                    action_type = qa_res.corrected_action_type
                    _update("Korekta typu akcji", 17, f"Skorygowano akcję na {action_type.upper()}")
                    if not hook_text or "penta" in hook_text.lower():
                        hook_text = action_type.upper().replace("_", " ")

                is_solo = action_type.lower() in ("solo_bolo", "solo", "1v1")
                if not is_solo and qa_res.suggested_combat_segments and not combat_segments:
                    combat_segments = qa_res.suggested_combat_segments
                    _update("Jump-Cut z QA", 18, f"QA zaleciło segmenty jump-cut: {combat_segments}")
                elif not is_solo and qa_res.suggested_combat_segments is None and combat_segments:
                    # QA wykryło ciągłą walkę (np. zabójstwo w luce bez banera) — anulujemy jump-cut
                    combat_segments = None
                    _update("Płynny montaż z QA", 18, "QA potwierdziło ciągłą walkę — anulowano jump-cut aby zachować wszystkie fragi")

                if not is_solo and qa_res.adjusted_trim_start > clip_start and not combat_segments:
                    clip_start = qa_res.adjusted_trim_start

                if is_solo:
                    combat_segments = None

                _update("QA Pre-Flight", 19, f"QA {qa_status} ({qa_score}/100) — {len(qa_details)} uwag")
            except Exception as qe:
                _update("Ostrzeżenie QA", 19, f"Pre-flight QA warning: {qe}")

        # ─── QA Auto-Retry (max 1 próba naprawy) ────────────────────────────────
        QA_RETRY_THRESHOLD = 85
        if qa_score < QA_RETRY_THRESHOLD and validate_pre_flight and peaks:
            _update("QA Auto-Retry", 19, f"Score {qa_score}/100 < {QA_RETRY_THRESHOLD} — diagnozuję i próbuję naprawić...")
            fixed = False
            clip_start_orig, clip_end_orig = clip_start, clip_end
            # 1) Outro za długie — skróć clip_end do last_kill + 2.5s
            # peaks mogą być tuple (ts, label) lub dict {"timestamp": ts}
            def _peak_ts(p):
                return p[0] if isinstance(p, (tuple, list)) else p["timestamp"]
            # UWAGA: peaks timestamps są RELATIVE do clip_start; clip_start/clip_end są ABSOLUTNE
            last_kill_t_rel = max((_peak_ts(p) for p in peaks), default=None)
            last_kill_t_abs = (clip_start + last_kill_t_rel) if last_kill_t_rel is not None else None
            # 1) Outro za długie — skróć clip_end do last_kill + 2.5s (tylko dla pojedynczego klipu)
            if not combat_segments:
                for detail in qa_details:
                    detail_low = detail.lower()
                    if any(kw in detail_low for kw in ("akcja po ostatnim", "pacing", "długość")):
                        if last_kill_t_abs is not None:
                            new_end = round(last_kill_t_abs + 2.5, 1)
                            if new_end < clip_end:
                                _update("QA Fix: Outro", 19, f"Skracam outro: clip_end {clip_end}→{new_end}s")
                                clip_end = new_end
                                fixed = True
                        break
            # 2) Kill poza kadrem — przesuń clip_start bliżej pierwszego killa (tylko dla pojedynczego klipu)
            if not combat_segments:
                for detail in qa_details:
                    detail_low = detail.lower()
                    if any(kw in detail_low for kw in ("poza krawędzią", "poza kadrem")):
                        if last_kill_t_abs is not None:
                            first_kill_t_abs = clip_start + min((_peak_ts(p) for p in peaks), default=last_kill_t_rel)
                            new_start = round(max(clip_start, first_kill_t_abs - 4.0), 1)
                            if new_start > clip_start:
                                _update("QA Fix: Intro", 19, f"Przesuwam intro: clip_start {clip_start}→{new_start}s")
                                clip_start = new_start
                                fixed = True
                        break
            if fixed:
                smart_cam_track2 = smart_cam_track
                if use_smart_camera:
                    try:
                        from lol_agent.smart_camera import find_action_path
                        smart_cam_track2 = find_action_path(source_path, clip_start, clip_end)
                    except Exception:
                        pass
                try:
                    qa_res2 = validate_pre_flight(
                        video_path=source_path,
                        trim_start=clip_start,
                        trim_end=clip_end,
                        peaks=peaks,
                        smart_camera_track=smart_cam_track2,
                        action_type=action_type,
                        combat_segments=combat_segments,
                        tuning_profile=tuning_prof,
                    )
                    if qa_res2.qa_score >= qa_score:
                        qa_status = qa_res2.qa_status
                        qa_score = qa_res2.qa_score
                        qa_details = qa_res2.diagnostic_details
                        smart_cam_track = smart_cam_track2
                        _update("QA Po Naprawie", 19, f"QA {qa_status} ({qa_score}/100) po auto-fix")
                    else:
                        clip_start, clip_end = clip_start_orig, clip_end_orig
                        _update("QA Fix Cofnięty", 19, f"Auto-fix pogorszył ({qa_res2.qa_score}) — przywracam oryginał")
                except Exception as qe2:
                    clip_start, clip_end = clip_start_orig, clip_end_orig
                    _update("QA Retry Error", 19, f"QA retry err: {qe2}")
        # ─────────────────────────────────────────────────────────────────────────

        with _lock:
            _state.action_type = action_type
            _state.clip_start = clip_start
            _state.clip_end = clip_end
            _state.combat_segments = combat_segments
            _state.qa_status = qa_status
            _state.qa_score = qa_score
            _state.qa_details = qa_details

        # Krok 1d — Minimap zone detection (kontekst lokalizacji akcji dla tytułu)
        map_zone_info = {"zone": "unknown", "zone_label": "", "confidence": 0.0}
        try:
            from lol_agent.lol_minimap_analyzer import detect_map_zone
            # peak_moment może być relative (do clip_start) lub absolute — normalizujemy
            abs_peak = (clip_start + peak_moment) if peak_moment < (clip_end - clip_start + 5) else peak_moment
            abs_peak = min(abs_peak, clip_end - 0.5)
            map_zone_info = detect_map_zone(source_path, abs_peak, clip_start)
            zone_log = f"{map_zone_info.get('zone')} ({map_zone_info.get('confidence', 0):.0%})"
            _update("Minimap zone detected", 19, f"Strefa akcji: {zone_log}")
        except Exception as me:
            _update("Minimap skip", 19, f"Minimap detection pominięta: {me}")

        # Krok 2 — render
        check_cancellation()
        _update("Renderowanie klipu", 20, "Uruchamiam render_short...")

        output = render_short(
            source_path=source_path,
            clip_start=clip_start,
            clip_end=clip_end,
            action_type=action_type,
            champion_name=champion_name,
            rank=rank,
            use_speed_ramp=use_speed_ramp,
            use_zoom_punch=use_zoom_punch,
            use_smart_camera=use_smart_camera,
            peak_moment=peak_moment,
            hook_text=hook_text,
            peaks=peaks,
            output_filename=output_filename,
            combat_segments=combat_segments,
        )

        check_cancellation()
        _update("Generowanie miniaturki & metadanych", 90, "Tworzę miniaturkę 9:16 i tytuł...")
        
        # Miniaturka
        thumb_file = None
        try:
            thumb_out = str(output).replace(".mp4", "_thumb.jpg")
            # FIX: peak_moment z oryginalnego klipu (np. 45s) jest za duży dla 15s shorta.
            # Przeliczamy względem czasu renderowanego klipu (clip_start → 0).
            clip_duration = float(clip_end) - float(clip_start) if clip_end and clip_start else None
            if clip_duration and peak_moment is not None:
                # Względny czas w shorcie = peak_moment_in_source - clip_start
                relative_peak = float(peak_moment) - float(clip_start)
                # Bezpieczny zakres: 0.2s od początku do 1s przed końcem
                if clip_duration > 0:
                    thumb_time = min(max(0.2, relative_peak), clip_duration - 1.0)
                else:
                    thumb_time = 1.0
            elif peak_moment is not None:
                thumb_time = float(peak_moment)
            else:
                thumb_time = 1.5
            thumb_file = generate_thumbnail(
                video_path=str(output),
                peak_moment=thumb_time,
                action_label=action_type.upper().replace("_", " "),
                champion_name=champion_name,
                output_path=thumb_out,
            )
        except Exception as te:
            _update("Błąd miniaturki", 92, f"Miniaturka warning: {te}")

        # Metadane
        meta = {}
        try:
            # Określ styl walki z danych klipu
            k_count = len(peaks) if peaks else (1 if action_type.lower() in ("solo_bolo", "solo", "1v1") else 0)
            c_dur = round(float(clip_end - clip_start), 1) if clip_end and clip_start else 15.0
            z_label = map_zone_info.get("zone_label", "") if map_zone_info.get("confidence", 0) >= 0.60 else ""
            
            if action_type.lower() in ("solo_bolo", "solo", "1v1"):
                c_style = f"1v1 Lane Duel / Pure Mechanical Skill Check{' in ' + z_label if z_label else ''}"
                c_narrative = "Aggressive 1v1 mechanical outplay and ego check."
            elif k_count >= 5 or "penta" in action_type.lower():
                c_style = f"Full Teamfight Ace (5 Kills / Pentakill){' at ' + z_label if z_label else ''}"
                c_narrative = "Relentless pentakill chase & teamfight wipe. Zero escape for the enemy."
            elif "oneshot" in action_type.lower():
                c_style = "Instant Burst Combo / Assassination"
                c_narrative = "Instant proactive assassination and burst execution."
            elif "clutch" in action_type.lower():
                c_style = "1% HP Survival / Miracle Turnaround"
                c_narrative = "Extreme low HP survival and comeback clutch."
            elif "triple" in action_type.lower() or k_count == 3:
                c_style = f"Relentless Triple Kill Chase & Rampage{' in ' + z_label if z_label else ''}"
                c_narrative = "Offensive pursuit: Chasing down and hunting enemies across the map. NOT defending a tower dive."
            elif "double" in action_type.lower() or k_count == 2:
                c_style = f"Fast Double Kill Pursuit{' in ' + z_label if z_label else ''}"
                c_narrative = "Aggressive engage and double kill execution."
            else:
                c_style = f"Aggressive Outplay / Hunting Enemies{' in ' + z_label if z_label else ''}"
                c_narrative = "Offensive hunting and mechanical execution of fleeing opponents."

            extra_ctx = {
                "map_zone": map_zone_info,
                "kill_count": k_count,
                "clip_duration": c_dur,
                "combat_style": c_style,
                "combat_narrative": c_narrative,
                "is_solo": action_type.lower() in ("solo_bolo", "solo", "1v1"),
            }

            try:
                from lol_agent.lol_metadata_generator import generate_metadata_universal
            except ImportError:
                from lol_metadata_generator import generate_metadata_universal
            meta = generate_metadata_universal(
                game_type=game_type,
                action_type=action_type,
                subject_name=champion_name,
                rank=rank,
                extra_context=extra_ctx,
            )
        except Exception:
            try:
                try:
                    from lol_agent.lol_metadata_generator import generate_channel_title, build_channel_description, build_pinned_comment
                except ImportError:
                    from lol_metadata_generator import generate_channel_title, build_channel_description, build_pinned_comment
                valid_fallback_zone = map_zone_info.get("zone_label", "") if map_zone_info.get("confidence", 0) >= 0.60 else ""
                fallback_title = generate_channel_title(action_type, champion_name, rank, map_zone_label=valid_fallback_zone)
                meta = {
                    "title": fallback_title,
                    "description": build_channel_description(fallback_title, champion_name, action_type, map_zone_label=valid_fallback_zone),
                    "pinned_comment": build_pinned_comment(champion_name, action_type),
                }
            except Exception:
                meta = {
                    "title": f"{action_type.upper()} {champion_name} #Shorts",
                    "description": f"Insane {action_type} play! #Shorts",
                    "pinned_comment": "Rate this play 1-10! 👇",
                }

        if _cancel_event.is_set():
            return

        with _lock:
            _state.status = PipelineStatus.DONE
            _state.progress = 100
            _state.current_step = "Gotowe"
            _state.output_path = str(output)
            _state.thumbnail_path = str(thumb_file) if thumb_file else None
            _state.title = meta.get("title") or f"{action_type.upper()} {champion_name} #Shorts"
            _state.description = meta.get("description") or ""
            _state.pinned_comment = meta.get("pinned_comment") or ""
            _state.finished_at = datetime.now().isoformat()

            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Output: {output}")

        # Zapisz w pamięci uczenia (render wygenerowany, oczekuje na decyzję)
        try:
            from lol_agent.user_learning_memory import record_render_generated
            record_render_generated(
                filename=str(output),
                action_type=action_type,
                duration=float(clip_duration or 15.0),
                qa_score=int(qa_score)
            )
        except Exception:
            pass

        # Wyślij push notyfikację
        if notify_token:
            _send_push(notify_token, "✅ Short gotowy!", f"{output_filename} wyrenderowany")

    except InterruptedError as ie:
        with _lock:
            _state.status = PipelineStatus.ERROR
            _state.error = str(ie)
            _state.finished_at = datetime.now().isoformat()
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 {ie}")
        return
    except Exception as e:
        err = traceback.format_exc()
        with _lock:
            _state.status = PipelineStatus.ERROR
            _state.error = str(e)
            _state.finished_at = datetime.now().isoformat()
            _state.logs.append(f"[ERROR] {err}")

        if notify_token:
            _send_push(notify_token, "❌ Błąd renderowania", str(e))


def _send_push(expo_token: str, title: str, body: str):
    """Wyślij push notyfikację przez Expo."""
    try:
        import httpx
        httpx.post(
            "https://exp.host/--/api/v2/push/send",
            json={
                "to": expo_token,
                "title": title,
                "body": body,
                "sound": "default",
            },
            timeout=10,
        )
    except Exception:
        pass  # Push jest opcjonalny — nie przerywaj jeśli się nie uda


def start_pipeline(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str = "pentakill",
    champion_name: str = "Katarina",
    rank: str = "Gold",
    peak_moment: float = 17.0,
    hook_text: str = "PENTAKILL",
    output_filename: str = "short_output.mp4",
    use_speed_ramp: bool = True,
    use_zoom_punch: bool = True,
    use_smart_camera: bool = True,
    notify_token: Optional[str] = None,
    combat_segments: Optional[List[Tuple[float, float]]] = None,
    game_type: str = "lol",
) -> bool:
    """Uruchom pipeline w osobnym wątku. Zwraca False jeśli już działa."""
    global _thread

    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            return False
        _cancel_event.clear()

    _thread = threading.Thread(
        target=_run_pipeline,
        kwargs=dict(
            source_path=source_path,
            clip_start=clip_start,
            clip_end=clip_end,
            action_type=action_type,
            champion_name=champion_name,
            rank=rank,
            peak_moment=peak_moment,
            hook_text=hook_text,
            output_filename=output_filename,
            use_speed_ramp=use_speed_ramp,
            use_zoom_punch=use_zoom_punch,
            use_smart_camera=use_smart_camera,
            notify_token=notify_token,
            combat_segments=combat_segments,
            game_type=game_type,
        ),
        daemon=True,
    )
    _thread.start()
    return True



def stop_pipeline():
    """Zatrzymaj pipeline natychmiastowo: flaga anulowania + ubicie aktywnego procesu FFmpeg."""
    global _active_proc
    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            _cancel_event.set()
            _state.status = PipelineStatus.ERROR
            _state.error = "Zatrzymano przez użytkownika"
            _state.finished_at = datetime.now().isoformat()
            if _active_proc is not None:
                try:
                    _active_proc.terminate()
                except Exception:
                    try:
                        _active_proc.kill()
                    except Exception:
                        pass
                _active_proc = None
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Pipeline przerwany przez użytkownika")
