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
            found_path = None
            for search_dir in candidate_dirs:
                if not search_dir.exists():
                    continue
                for ext in ["*.mp4", "*.mov", "*.mkv", "*.avi"]:
                    for candidate in search_dir.rglob(ext):
                        if candidate.name == source_path or candidate.name == Path(source_path).name:
                            found_path = str(candidate.resolve())
                            break
                    if found_path:
                        break
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

        # Krok 1 — detekcja kill eventów
        try:
            peaks = detect_kill_events(
                source_path, clip_start, clip_end,
                clip_duration=clip_end - clip_start
            )
            _update("Kill detection gotowa", 12, f"Kill peaks: {peaks}")
        except Exception as e:
            _update("Kill detection pominięta", 12, f"Błąd detekcji: {e}")
            peaks = []

        # Sprawdź czy kille mają lukę > 3.5s (martwe bieganie) i czy potrzeba jump-cut
        # Dla SOLO BOLO nigdy nie stosujemy jump-cutów — cała walka 1v1 musi być ciągła
        if action_type.lower() in ("solo_bolo", "solo", "1v1"):
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
        if validate_pre_flight:
            try:
                qa_res = validate_pre_flight(
                    video_path=source_path,
                    trim_start=clip_start,
                    trim_end=clip_end,
                    peaks=peaks,
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

                if qa_res.suggested_combat_segments and not combat_segments:
                    combat_segments = qa_res.suggested_combat_segments
                    _update("Jump-Cut z QA", 18, f"QA zaleciło segmenty jump-cut: {combat_segments}")

                if qa_res.adjusted_trim_start > clip_start and not combat_segments:
                    clip_start = qa_res.adjusted_trim_start

                _update("QA Pre-Flight", 19, f"QA {qa_status} ({qa_score}/100) — {len(qa_details)} uwag")
            except Exception as qe:
                _update("Ostrzeżenie QA", 19, f"Pre-flight QA warning: {qe}")

        with _lock:
            _state.action_type = action_type
            _state.clip_start = clip_start
            _state.combat_segments = combat_segments
            _state.qa_status = qa_status
            _state.qa_score = qa_score
            _state.qa_details = qa_details

        # Krok 2 — render
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

        _update("Generowanie miniaturki & metadanych", 90, "Tworzę miniaturkę 9:16 i tytuł...")
        
        # Miniaturka
        thumb_file = None
        try:
            thumb_out = str(output).replace(".mp4", "_thumb.jpg")
            thumb_file = generate_thumbnail(
                video_path=str(output),
                peak_moment=peak_moment,
                action_label=action_type.upper().replace("_", " "),
                champion_name=champion_name,
                output_path=thumb_out,
            )
        except Exception as te:
            _update("Błąd miniaturki", 92, f"Miniaturka warning: {te}")

        # Metadane
        meta = {}
        try:
            from lol_metadata_generator import generate_metadata, generate_channel_title, build_channel_description, build_pinned_comment
            meta = generate_metadata(action_type=action_type, champion_name=champion_name, rank=rank)
        except Exception as me:
            from lol_metadata_generator import generate_channel_title, build_channel_description, build_pinned_comment
            _update("Ostrzeżenie metadanych", 95, f"Metadata fallback: {me}")
            fallback_title = generate_channel_title(action_type, champion_name, rank)
            meta = {
                "title": fallback_title,
                "description": build_channel_description(fallback_title, champion_name, action_type),
                "pinned_comment": build_pinned_comment(champion_name, action_type),
            }

        with _lock:
            _state.status = PipelineStatus.DONE
            _state.progress = 100
            _state.current_step = "Gotowe"
            _state.output_path = str(output)
            _state.thumbnail_path = str(thumb_file) if thumb_file else None
            _state.title = meta.get("title") or generate_channel_title(action_type, champion_name, rank)
            _state.description = meta.get("description") or build_channel_description(_state.title, champion_name, action_type)
            _state.pinned_comment = meta.get("pinned_comment") or build_pinned_comment(champion_name, action_type)
            _state.finished_at = datetime.now().isoformat()
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Output: {output}")

        # Wyślij push notyfikację
        if notify_token:
            _send_push(notify_token, "✅ Short gotowy!", f"{output_filename} wyrenderowany")

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
) -> bool:
    """Uruchom pipeline w osobnym wątku. Zwraca False jeśli już działa."""
    global _thread

    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            return False

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
        ),
        daemon=True,
    )
    _thread.start()
    return True


def stop_pipeline():
    """Zatrzymaj pipeline (soft stop — czeka na koniec bieżącego ffmpeg)."""
    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            _state.status = PipelineStatus.ERROR
            _state.error = "Zatrzymano przez użytkownika"
            _state.finished_at = datetime.now().isoformat()
