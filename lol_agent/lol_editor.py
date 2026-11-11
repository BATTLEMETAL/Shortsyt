"""
LOL Agent — Editor v3
Styl: czysty gameplay, tekst hook na peak, muzyka dobrana do energii akcji,
      efekt zoom-punch na peak moment + dynamiczne śledzenie kamery.
"""
import os
import time
import random
import subprocess
import glob
import shutil
import threading
import numpy as np
from typing import Optional

_music_lock = threading.Lock()
try:
    from lol_agent.lol_config import (
        LOL_MUSIC_DIR, LOL_TEMP_DIR,
        OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS,
        MUSIC_VOLUME, GAME_AUDIO_VOLUME, SHORT_MAX_DURATION, SMOOTH_SLOWMO
    )
except ImportError:
    from lol_config import (
        LOL_MUSIC_DIR, LOL_TEMP_DIR,
        OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS,
        MUSIC_VOLUME, GAME_AUDIO_VOLUME, SHORT_MAX_DURATION, SMOOTH_SLOWMO
    )
import json

# Jedna oś czasu dla obrazu, napisów, muzyki i dźwięku gry (11.11.2026; patrz lol_timeline.py)
try:
    from lol_agent import lol_timeline as TL
except ImportError:
    import lol_timeline as TL

# Dropy sprawdzone uchem. Tylko te wygrywają z automatyczną detekcją; reszta mapy to przybliżenia.
MUSIC_DROP_VERIFIED = {"ncs_cartoon_on_and_on.mp3", "ncs_elektronomia_sky_high.mp3"}
# Ostatnia synchronizacja muzyki (do przepisu shorta): wypełnia merge_music
LAST_MUSIC_SYNC = {}
# Dźwięk gry rozciągany razem z obrazem (False = stare zachowanie: dźwięk gry bez zwolnień)
WARP_GAME_AUDIO = True
# Źródło inne niż 1920x1080 jest przy wycinaniu sprowadzane do 1920x1080 (maski HUD i kamera są liczone dla 1080p)
NORMALIZE_SOURCE = True

def get_performance_insights() -> dict:
    """Wczytuje najnowsze wnioski z analizy wydajności (lol_pre_analysis.json)."""
    insights_path = os.path.join(os.path.dirname(__file__), "lol_pre_analysis.json")
    if os.path.exists(insights_path):
        try:
            with open(insights_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("yt_stats", {})
        except Exception:
            pass
    return {}

# librosa beat detector — auto-detects drop from any MP3
try:
    from lol_agent.lol_beat_detector import get_drop_time as _get_drop_time
    BEAT_DETECTOR_OK = True
except ImportError:
    try:
        from lol_beat_detector import get_drop_time as _get_drop_time
        BEAT_DETECTOR_OK = True
    except ImportError:
        BEAT_DETECTOR_OK = False
        _get_drop_time = None

# Smart camera — import z obsługą błędu jeśli brak numpy/PIL
try:
    from lol_agent.smart_camera import find_action_crop_x, find_action_path, generate_ffmpeg_pan_expression
    SMART_CAMERA_AVAILABLE = True
except ImportError:
    try:
        from smart_camera import find_action_crop_x, find_action_path, generate_ffmpeg_pan_expression
        SMART_CAMERA_AVAILABLE = True
    except ImportError:
        SMART_CAMERA_AVAILABLE = False
        print("⚠️  Smart camera niedostępna (brak numpy/PIL) — używam centrum")

# Hardware acceleration & GPU auto-detection
try:
    from hardware_accel import get_optimal_encoder_args, detect_hardware
    HW_ACCEL_OK = True
except ImportError:
    try:
        from lol_agent.hardware_accel import get_optimal_encoder_args, detect_hardware
        HW_ACCEL_OK = True
    except ImportError:
        HW_ACCEL_OK = False
        def get_optimal_encoder_args(quality='high'):
            return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "0", "-pix_fmt", "yuv420p"]
        def detect_hardware():
            return "libx264", "CPU fallback"

# ─── Kategorie muzyki wg energii akcji ───────────────────────────────────────
# Klucz = typ akcji, wartość = wymagana energia (high/medium/any)
ACTION_ENERGY = {
    "pentakill": "high",
    "quadrakill": "high",
    "baron": "high",
    "dragon": "high",
    "triple": "medium",
    "outplay": "medium",
    "oneshot": "medium",
    "clutch": "medium",
    "solo_bolo": "medium",
    "escape": "low",
    "double": "any",
}

# Manual energy map — filename → energy level
# Add new files here after downloading from ncs.io
MUSIC_ENERGY_MAP = {
    # HIGH energy — use for: pentakill, quadrakill, baron, dragon
    "ncs_elektronomia_sky_high.mp3":           "high",
    "ncs_egzod_royalty.mp3":                   "high",
    "ncs_lost_sky_dreams_pt2.mp3":             "high",
    "ncs_robin_hustin_light_it_up.mp3":        "high",
    "ncs_elektronomia_memory.mp3":             "high",

    # MEDIUM energy — use for: triple, outplay, clutch, oneshot, solo_bolo
    # (unknown_brain is medium in NCS library — corrected from high)
    "ncs_unknown_brain_superhero.mp3":         "medium",
    "ncs_cartoon_on_and_on.mp3":               "medium",
    "ncs_different_heaven_my_heart.mp3":       "medium",
    "ncs_alan_walker_fade.mp3":                "medium",
    "ncs_alex_skrindo_euphoria.mp3":           "medium",

    # LOW energy — use for: escape, double kill (tension/dramatic)
    "ncs_jim_yosef_link.mp3":                  "low",
    "ncs_distrion_atlas_rubicon.mp3":          "low",
}

# Beat drop timestamps in seconds — where the song's main drop hits
# Used for beat-sync: drop aligns with the kill peak in the video
MUSIC_DROP_MAP = {
    "ncs_cartoon_on_and_on.mp3":               38.0,
    "ncs_elektronomia_sky_high.mp3":           30.0,

    # Fill these in after listening to each track:
    "ncs_egzod_royalty.mp3":                   45.0,   # approximate — adjust after listening
    "ncs_lost_sky_dreams_pt2.mp3":             40.0,
    "ncs_robin_hustin_light_it_up.mp3":        35.0,
    "ncs_elektronomia_memory.mp3":             32.0,
    "ncs_unknown_brain_superhero.mp3":         38.0,
    "ncs_different_heaven_my_heart.mp3":       28.0,
    "ncs_alan_walker_fade.mp3":                42.0,
    "ncs_alex_skrindo_euphoria.mp3":           36.0,
    "ncs_jim_yosef_link.mp3":                  30.0,
    "ncs_distrion_atlas_rubicon.mp3":          44.0,
}




def ensure_temp_dir():
    os.makedirs(LOL_TEMP_DIR, exist_ok=True)
    try:
        now = time.time()
        for f in glob.glob(os.path.join(LOL_TEMP_DIR, "*.meta.json")):
            if now - os.path.getmtime(f) > 7 * 86400:
                try: os.remove(f)
                except OSError: pass
        for f in glob.glob(os.path.join(LOL_TEMP_DIR, "seg_*.mp4")):
            if now - os.path.getmtime(f) > 86400:
                try: os.remove(f)
                except OSError: pass
    except Exception:
        pass


def pick_music_for_action(action_type: str = "outplay", preferred_track: Optional[str] = None) -> str:
    """
    Wybiera plik muzyczny dopasowany do energii akcji.
    """
    if preferred_track:
        cand = os.path.join(LOL_MUSIC_DIR, preferred_track)
        if os.path.exists(cand):
            print(f"🎵 Muzyka [preferred]: {preferred_track}")
            return cand

    music_files = glob.glob(os.path.join(LOL_MUSIC_DIR, "*.mp3"))
    if not music_files:
        raise FileNotFoundError(f"Brak plików MP3 w {LOL_MUSIC_DIR}")

    # Filtruj po energii akcji jeśli mapa dostępna
    required_energy = ACTION_ENERGY.get(action_type.lower(), "any")
    if required_energy != "any":
        matched = []
        for f in music_files:
            fname = os.path.basename(f)
            energy = MUSIC_ENERGY_MAP.get(fname, "any")
            if energy == required_energy or energy == "any":
                matched.append(f)
        if matched:
            music_files = matched

    # Dedup: wykluczaj ostatnio używane utwory (historia ostatnich utworów) chronione lockiem wątkowym
    last_track_file = os.path.join(LOL_MUSIC_DIR, ".last_track")
    recent_tracks = []
    with _music_lock:
        if os.path.exists(last_track_file):
            try:
                with open(last_track_file, "r", encoding="utf-8") as f:
                    recent_tracks = [line.strip() for line in f if line.strip()]
            except Exception:
                pass

        # Wyklucz ostatnie utwory z puli
        candidates = [f for f in music_files if os.path.basename(f) not in recent_tracks]
        if not candidates and len(music_files) > 1:
            # Jeśli wszystkie z puli były w historii, wyklucz przynajmniej ostatni
            candidates = [f for f in music_files if os.path.basename(f) != recent_tracks[-1]]
        if candidates:
            music_files = candidates
            if recent_tracks:
                print(f"🎵 Dedup: aktywna rotacja muzyki (wykluczono ostatnie: {', '.join(recent_tracks[-3:])})")

        chosen = random.choice(music_files)
        chosen_name = os.path.basename(chosen)

        # Zapisz historię (max 7 ostatnich utworów — większy pool = lepsza rotacja)
        try:
            updated_history = (recent_tracks + [chosen_name])[-7:]
            with open(last_track_file, "w", encoding="utf-8") as f:
                f.write("\n".join(updated_history))
        except Exception:
            pass

    energy_label = MUSIC_ENERGY_MAP.get(chosen_name, "?")
    print(f"🎵 Muzyka [{energy_label}]: {chosen_name}")
    return chosen


def _run_ffmpeg(cmd: list, timeout: float = 180.0, desc: str = "") -> subprocess.CompletedProcess:
    """Bezpieczne wywołanie procesu potomnego z rejestracją procesu i timeoutem."""
    try:
        from lol_agent.api.pipeline_runner import set_active_subprocess, clear_active_subprocess, check_cancellation
        check_cancellation()
    except Exception:
        try:
            from api.pipeline_runner import set_active_subprocess, clear_active_subprocess, check_cancellation
            check_cancellation()
        except Exception:
            set_active_subprocess = lambda p: None
            clear_active_subprocess = lambda: None
            check_cancellation = lambda: None

    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    set_active_subprocess(p)
    try:
        stdout, stderr = p.communicate(timeout=timeout)
        ret = p.returncode
        return subprocess.CompletedProcess(args=cmd, returncode=ret, stdout=stdout, stderr=stderr)
    except subprocess.TimeoutExpired as te:
        p.kill()
        stdout, stderr = p.communicate()
        print(f"⚠️  FFmpeg timeout po {timeout}s ({desc}) — proces przerwany")
        raise RuntimeError(f"Przekroczono limit czasu operacji wideo ({timeout}s: {desc})") from te
    finally:
        clear_active_subprocess()
        check_cancellation()


def get_video_duration(path: str) -> float:
    """Zwraca długość wideo w sekundach."""
    r = _run_ffmpeg([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], timeout=15.0, desc="ffprobe duration")
    try:
        return float(r.stdout.decode("utf-8", errors="replace").strip())
    except (ValueError, AttributeError):
        return 0.0


def get_video_size(path: str):
    """Zwraca (szerokość, wysokość) pierwszego strumienia wideo albo (0, 0), gdy nie da się odczytać."""
    try:
        # celowo poza _run_ffmpeg: to tylko odczyt, nie krok montażu (testy liczą wywołania _run_ffmpeg)
        r = subprocess.run([
            "ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0", path
        ], capture_output=True, timeout=15.0)
        w, h = r.stdout.decode("utf-8", errors="replace").strip().split("x")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


def _normalize_vf(input_path: str) -> str:
    """Filtr sprowadzający źródło do 1920x1080 (z czarnymi pasami, gdy proporcje inne niż 16:9). Pusty dla 1080p."""
    if not NORMALIZE_SOURCE:
        return ""
    w, h = get_video_size(input_path)
    if (w, h) in ((0, 0), (1920, 1080)):
        return ""
    print(f"   📐 Źródło {w}x{h} → normalizuję do 1920x1080 (kamera i maski HUD liczą w 1080p)")
    return ",scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"


def cut_clip(input_path: str, start: float, end: float, output_path: str, smooth_seams: bool = False) -> str:
    """
    Wycina fragment klipu z zachowaniem dokładności klatkowej (Frame-Accurate Cut).
    Używa szybkiego enkodera NVENC / ultrafast CPU aby wyeliminować desynchronizację I-frame.
    smooth_seams: stosuje mikro-fade audio (30ms) na brzegach cięcia, eliminując trzaski przy łączeniu segmentów jump-cut.
    """
    duration = max(0.1, end - start)
    encoder_draft = get_optimal_encoder_args("draft")
    norm_vf = _normalize_vf(input_path)

    af_args = []
    if smooth_seams and duration >= 0.15:
        fade_d = 0.03
        out_start = max(0.0, duration - fade_d)
        af_args = ["-af", f"afade=t=in:ss=0:d={fade_d:.3f},afade=t=out:st={out_start:.3f}:d={fade_d:.3f}"]

    # Próba 1: Dokładne cięcie z enkoderem sprzętowym (NVENC trwa < 0.5s)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-i", input_path,
        "-t", f"{duration:.3f}",
        *encoder_draft,
        "-vf", "setpts=PTS-STARTPTS" + norm_vf,   # zeruje PTS — eliminuje offset AV po cięciu NVENC
        "-c:a", "aac", "-b:a", "192k",
        *af_args,
        "-avoid_negative_ts", "make_zero",
        output_path
    ]
    print(f"✂️  Tnę (frame-accurate): {start:.1f}s → {end:.1f}s ({duration:.1f}s)")
    r = _run_ffmpeg(cmd, timeout=60.0, desc="cut_clip frame-accurate")
    if r.returncode != 0:
        # Fallback 1: CPU ultrafast
        cmd_cpu = [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-i", input_path,
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-vf", "setpts=PTS-STARTPTS" + norm_vf,
            "-c:a", "aac", "-b:a", "192k",
            *af_args,
            "-avoid_negative_ts", "make_zero",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=60.0, desc="cut_clip CPU")
        if r_cpu.returncode != 0:
            # Fallback 2: Stream copy (ostatnia deska ratunku)
            cmd_copy = [
                "ffmpeg", "-y",
                "-ss", f"{start:.3f}", "-i", input_path,
                "-t", f"{duration:.3f}",
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                output_path
            ]
            r_copy = _run_ffmpeg(cmd_copy, timeout=60.0, desc="cut_clip copy fallback")
            if r_copy.returncode != 0:
                raise RuntimeError(f"FFmpeg cut error: {r_copy.stderr.decode('utf-8', errors='replace')[:400]}")
    return output_path


def apply_editor_effects(input_path: str, output_path: str,
                         clip_duration: float, crop_x: str,
                         peak_moment: float = 0.0,
                         zoom_level: float = 1.08,
                         zoom_duration: float = 0.8,
                         slowmo_speed: float = 0.75,
                         slowmo_duration: float = 1.5,
                         intermediate_peaks: list = None,
                         use_easing: bool = True,
                         timeline_out: Optional[dict] = None) -> float:
    """
    Stosuje pionowe kadrowanie, zoom-punch i spowolnienie (speed ramp)
    w jednym przebiegu za pomocą filter_complex w FFmpeg.
    Obsługuje krzywą easing (ease-in / ease-out) dla eliminacji nagłych skoków tempa.
    crop_x moze byc wyrazeniem (np. if(lt(t,5.0),...)) dla dynamicznego sledzenia.
    intermediate_peaks: czasy (rel. do klipu) killów PRZED glównym peak_moment.
    Gwarantuje idealna dokladnosc klatkowa i brak przyciec/desynchronizacji.
    timeline_out: gdy podany słownik, dostaje "segments" (oś czasu), "output_duration" i "mapped_peak"
                  (cios na osi gotowego filmu) — tego używają muzyka, napisy i dźwięk gry.
    """
    source_w, source_h = 1920, 1080
    crop_w = TL.vertical_crop_width(source_h)   # 608 (parzyste; 607 wywala NVENC)
    crop_h = source_h

    # Jeśli podano int/float, skonwertuj na str
    if not isinstance(crop_x, str):
        cx = max(0, min(int(crop_x), source_w - crop_w)) if crop_x >= 0 else (source_w - crop_w) // 2
        crop_x_expr = f"{cx}"
    else:
        crop_x_expr = crop_x

    # Parametry zoomu (PENTA/ostatni kill) - bezpieczny zoom max ZOOM_MAX z centrowaniem w pionie
    effective_zoom = min(zoom_level, TL.ZOOM_MAX)
    crop_w_zoom = int(crop_w / effective_zoom)
    crop_h_zoom = int(crop_h / effective_zoom)
    crop_w_zoom -= crop_w_zoom % 2
    crop_h_zoom -= crop_h_zoom % 2
    crop_x_expr_zoom = f"({crop_x_expr})+{(crop_w - crop_w_zoom) // 2}"
    # Centrowanie w pionie chroni dolny obszar walki (sztylety, przeciwników pod postacią):
    crop_y_zoom = max(0, (crop_h - crop_h_zoom) // 2)

    out_w, out_h = 1080, 1920

    eff = TL.effective_edit_values(zoom_level, zoom_duration, slowmo_duration)
    if eff["zoom_level"] < zoom_level - 1e-6 or eff["slowmo_window"] < slowmo_duration - 1e-6 or eff["zoom_window"] < zoom_duration - 1e-6:
        print(f"   ℹ️  Limity montażu: zoom {zoom_level:.2f}x→{eff['zoom_level']:.2f}x, okno zoomu {zoom_duration:.2f}s→{eff['zoom_window']:.2f}s, "
              f"slow-mo {slowmo_duration:.2f}s→{eff['slowmo_window']:.2f}s (lol_timeline.py)")

    normal_crop = f"crop={crop_w}:{crop_h}:'{crop_x_expr}':0"
    zoom_crop = f"crop={crop_w_zoom}:{crop_h_zoom}:'{crop_x_expr_zoom}':{crop_y_zoom}"

    # Oś czasu: JEDNO źródło prawdy (lol_timeline.build_speed_segments)
    time_segments = TL.build_speed_segments(
        clip_duration=clip_duration, peak_moment=peak_moment, slowmo_speed=slowmo_speed,
        slowmo_duration=slowmo_duration, zoom_duration=zoom_duration,
        intermediate_peaks=intermediate_peaks, use_easing=use_easing,
    )
    if not time_segments:
        time_segments = [{"start": 0.0, "end": float(clip_duration), "speed": 1.0, "zoom": False}]
    segs = [dict(ts, crop=(zoom_crop if ts["zoom"] else normal_crop)) for ts in time_segments]
    if timeline_out is not None:
        timeline_out["segments"] = time_segments
        timeline_out["output_duration"] = TL.output_duration(time_segments)
        timeline_out["mapped_peak"] = TL.warp_time(time_segments, peak_moment)

    filter_lines = []
    labels = []
    output_duration = 0.0

    for i, seg in enumerate(segs):
        lbl = f"v{i}"
        trim = f"trim=start={seg['start']:.3f}:end={seg['end']:.3f}"
        setpts1 = "setpts=PTS-STARTPTS"
        crop_scale = (
            f"{seg['crop']},scale={out_w}:{out_h}:flags=lanczos,fps=60,setsar=1,"
            f"eq=contrast=1.08:saturation=1.35:brightness=0.03"
        )

        seg_dur = seg['end'] - seg['start']
        output_duration += seg_dur / seg['speed']

        if seg['speed'] != 1.0:
            factor = 1.0 / seg['speed']
            setpts = f"setpts=(PTS-STARTPTS)*{factor:.4f}"
            filter_lines.append(f"[0:v]{trim},{crop_scale},{setpts}[{lbl}]")
        else:
            setpts = "setpts=PTS-STARTPTS"
            filter_lines.append(f"[0:v]{trim},{crop_scale},{setpts}[{lbl}]")

        labels.append(f"[{lbl}]")

    concat_str = "".join(labels) + f"concat=n={len(segs)}:v=1:a=0[v_final]"
    filter_lines.append(concat_str)

    filter_complex = ";".join(filter_lines)

    # Zapisz filter_complex do pliku skryptu aby uniknąć limitu długości linii poleceń Windows (WinError 206)
    fc_script = output_path.replace(".mp4", "_filter.txt")
    with open(fc_script, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    print(f"🎬 Processing filtergraph with dynamic tracking...")

    encoder_high = get_optimal_encoder_args("high")
    encoder_draft = get_optimal_encoder_args("draft")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex_script", fc_script,
        "-map", "[v_final]",
        *encoder_high,
        output_path
    ]

    # Optymalizacja GPU: Pojedynczy szybki przebieg z enkoderem sprzętowym
    # Jeśli minterpolate jest wymagane tylko na CPU, pomijamy ciężki CPU blend na GPU
    enc_name, _ = detect_hardware()
    is_gpu = enc_name in ('h264_nvenc', 'h264_amf', 'h264_qsv')

    has_slowmo = any(seg["speed"] != 1.0 for seg in segs)
    try:
        if is_gpu or not (has_slowmo and SMOOTH_SLOWMO):
            # Tryb ULTRA-FAST (GPU / Direct Single Pass): ~3-4 sekundy!
            r = _run_ffmpeg(cmd, timeout=180.0, desc="apply_editor_effects GPU")
            if r.returncode != 0:
                err_msg = r.stderr.decode('utf-8', errors='replace')[:400]
                print(f"⚠️  GPU encoder ({enc_name}) nie powiódł się na ciężkim klipie: {err_msg}")
                print("🔄  Automatyczny bezpieczny fallback: przełączam na procesor (CPU libx264 veryfast)...")
                cmd_cpu = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-filter_complex_script", fc_script,
                    "-map", "[v_final]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    output_path
                ]
                r_cpu = _run_ffmpeg(cmd_cpu, timeout=240.0, desc="apply_editor_effects CPU fallback")
                if r_cpu.returncode != 0:
                    raise RuntimeError(f"FFmpeg filtergraph error (CPU fallback): {r_cpu.stderr.decode('utf-8', errors='replace')[:800]}")
                print("✅  Render ukończony pomyślnie przez bezpieczny fallback CPU!")
        else:
            # CPU Fallback z minterpolate
            tmp_pre_interp = output_path.replace(".mp4", "_pre_interp.mp4")
            cmd_step1 = [
                "ffmpeg", "-y", "-i", input_path,
                "-filter_complex_script", fc_script,
                "-map", "[v_final]",
                *encoder_draft,
                tmp_pre_interp
            ]
            r = _run_ffmpeg(cmd_step1, timeout=180.0, desc="apply_editor_effects step 1")
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg filtergraph error: {r.stderr.decode('utf-8', errors='replace')[:800]}")

            print(f"🎬 Minterpolate blend — wygładzanie slow-mo (output_duration={output_duration:.2f}s)...")
            cmd_step2 = [
                "ffmpeg", "-y", "-i", tmp_pre_interp,
                "-vf", (
                    f"tpad=stop_mode=clone:stop_duration=0.5,"
                    f"minterpolate=fps={OUTPUT_FPS}:mi_mode=blend,"
                    f"trim=0:duration={output_duration:.4f},"
                    f"setpts=PTS-STARTPTS"
                ),
                *encoder_high,
                output_path
            ]
            r2 = _run_ffmpeg(cmd_step2, timeout=180.0, desc="apply_editor_effects minterpolate")
            if r2.returncode != 0:
                import shutil as _sh
                _sh.move(tmp_pre_interp, output_path)
            else:
                try:
                    import os as _os
                    _os.remove(tmp_pre_interp)
                except OSError:
                    pass
    finally:
        if os.path.exists(fc_script):
            try:
                os.remove(fc_script)
            except OSError:
                pass

    return output_duration


# ─── Czcionka Impact (Bundled + System Fallbacks) ─────────────────────────────
BUNDLED_FONT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts", "impact.ttf")
FONT_PATH = r"C:\Windows\Fonts\impact.ttf"
FONT_FALLBACK = r"C:\Windows\Fonts\arialbd.ttf"


def _get_font_path() -> str:
    # 1. Sprawdź zbundle'owany font w repozytorium (cross-platform Linux/Docker/Windows)
    if os.path.exists(BUNDLED_FONT):
        return BUNDLED_FONT
    # 2. Windows standardowe ścieżki
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    if os.path.exists(FONT_FALLBACK):
        return FONT_FALLBACK
    # 3. Linux / Docker standardowe czcionki
    linux_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for lf in linux_fonts:
        if os.path.exists(lf):
            return lf
    return ""


def build_text_overlay_filters(
    hook_text: str,
    peak_moment: float,
    video_duration: float,
    show_duration: float = 2.5
) -> list[str]:
    """
    Buduje filtry FFmpeg drawbox i drawtext dla tekstu hook (np. 'DOUBLE KILL - CLEAN OR LUCKY?').
    """
    if not hook_text:
        return []

    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki Impact — pomijam overlay tekstu")
        return []

    import re
    clean_text = re.sub(r'[^\x00-\x7F]+', '', hook_text).strip()
    clean_text = clean_text.replace("'", "")   # usuń apostrof — łamie FFmpeg drawtext parser w subprocess
    clean_text = clean_text.replace(":", "\\:")  # escape dwukropek (separator FFmpeg)
    clean_text = clean_text.replace("%", "%%")   # escape procent

    if not clean_text:
        return []

    # Hook zawsze zaczyna się od klatki 0.0s — to kluczowe dla retencji w pierwszych 2 sekundach
    # oraz gwarantuje, że klatka 0.0 (miniatura na TikTok) ma czytelny napis i okładkę.
    t_start = 0.0
    t_end = min(video_duration, max(1.5, show_duration))

    hook_color = "0xFFD700" if any(w in clean_text.upper() for w in ("SOLO", "PENTA", "CLUTCH", "1V1", "1%")) else "white"
    approx_w = min(max(int(len(clean_text) * 58) + 80, 480), 1020)
    drawbox = (
        f"drawbox="
        f"x=trunc((iw-{approx_w})/2)"
        f":y=trunc(ih*0.075)"
        f":w={approx_w}"
        f":h=120"
        f":color=black@0.65"
        f":t=fill"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )
    drawtext = (
        f"drawtext="
        f"fontfile='{font.replace(chr(92), '/').replace(':', '\\:')}'"
        f":text='{clean_text}'"
        f":x=(w-text_w)/2"
        f":y=h*0.09"
        f":fontsize=95"
        f":fontcolor={hook_color}"
        f":borderw=6"
        f":bordercolor=black"
        f":shadowx=4:shadowy=4:shadowcolor=black@0.8"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )
    return [drawbox, drawtext]


def add_text_overlay(
    video_path: str,
    hook_text: str,
    peak_moment: float,
    video_duration: float,
    output_path: str,
    show_duration: float = 2.5
) -> str:
    """
    Nakłada tekst hook (np. 'TRIPLE KILL') na wideo przy peak_moment.
    Styl: białe duże litery z czarnym obramowaniem, na dole ekranu.
    """
    filters = build_text_overlay_filters(hook_text, peak_moment, video_duration, show_duration)
    if not filters:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    vf_chain = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf_chain,
        *get_optimal_encoder_args("high"),
        "-c:a", "copy",
        output_path
    ]
    r = _run_ffmpeg(cmd, timeout=60.0, desc="add_text_overlay GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  Overlay error (próbuję fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "copy",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=90.0, desc="add_text_overlay CPU")
        if r_cpu.returncode != 0:
            print(f"⚠️  Overlay CPU fallback error (pomijam): {r_cpu.stderr.decode('utf-8', errors='replace')[:400]}")
            import shutil as _sh
            _sh.copy(video_path, output_path)
    return output_path


def build_dynamic_captions_filters(
    peaks: list,
    trim_start: float,
    video_duration: float,
    peak_moment: float = 0.0,
    slowmo_speed: float = 0.50,
    slowmo_duration: float = 1.5,
    action_type: str = "",
    time_segments: Optional[list] = None,
) -> list[str]:
    """
    Buduje filtry FFmpeg dla dynamicznych napisów kill-by-kill, HUD oraz progress bara.
    time_segments: oś czasu z apply_editor_effects. Gdy podana, czasy napisów liczy lol_timeline.warp_time
                   (ta sama oś co obraz); bez niej działa stary, przybliżony model.
    """
    if not peaks:
        return []

    # Normalizuj peak_moment do video_duration
    if trim_start > 0.0 and peak_moment >= trim_start:
        peak_moment = peak_moment - trim_start
    elif peak_moment > video_duration and video_duration > 0.0:
        peak_moment = min(video_duration * 0.70, max(1.0, peak_moment % video_duration))

    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki — pomijam dynamiczne napisy")
        return []

    import re
    font_safe = font.replace(chr(92), '/').replace(':', '\\:')

    KILL_STYLES = {
        "DOUBLE KILL":   {"size": 80,  "color": "white",     "duration": 1.8},
        "TRIPLE KILL":   {"size": 100, "color": "yellow",    "duration": 2.0},
        "QUADRAKILL":    {"size": 115, "color": "orange",    "duration": 2.2},
        "PENTAKILL":     {"size": 135, "color": "0xFFD700",  "duration": 2.5},
        "KILLING SPREE": {"size": 85,  "color": "white",     "duration": 1.8},
        "UNSTOPPABLE":   {"size": 90,  "color": "yellow",    "duration": 2.0},
        "LEGENDARY":     {"size": 105, "color": "orange",    "duration": 2.2},
        "GODLIKE":       {"size": 120, "color": "0xFFD700",  "duration": 2.5},
        "SOLO BOLO":     {"size": 115, "color": "0xFF3333",  "duration": 2.2},
        "OUTPLAY":       {"size": 105, "color": "0xFFD700",  "duration": 2.0},
        "KILL":          {"size": 85,  "color": "white",     "duration": 1.8},
        "SHUTDOWN":      {"size": 105, "color": "0xFFD700",  "duration": 2.0},
        "CLUTCH":        {"size": 115, "color": "0xFF1744",  "duration": 2.2},
        "1% HP CLUTCH":  {"size": 115, "color": "0xFF1744",  "duration": 2.2},
        "ONESHOT":       {"size": 110, "color": "0xFF9100",  "duration": 2.0},
    }

    def _adjust_t(t_orig: float) -> float:
        if time_segments:
            return TL.warp_time(time_segments, float(t_orig))
        MINI_SPEED = 0.6
        MINI_DUR   = 1.0
        
        t0 = 0.0
        t1 = max(t0, min(peak_moment - 0.4, video_duration))
        t2 = max(t1, min(peak_moment + 1.0, video_duration))
        t3 = max(t2, min(peak_moment + slowmo_duration, video_duration))
        t4 = video_duration

        segments = []
        cursor = t0
        
        int_peaks = [
            (tk if (tk < trim_start or trim_start == 0.0) else (tk - trim_start))
            for (tk, _) in (peaks or [])
            if (tk if (tk < trim_start or trim_start == 0.0) else (tk - trim_start)) < peak_moment - 0.1
        ]
        if int_peaks:
            for pk in sorted(int_peaks):
                pk_f = float(pk)
                if pk_f < cursor + 0.05 or pk_f >= t1 - 0.05:
                    continue
                mini_end = min(pk_f + MINI_DUR, t1)
                if pk_f > cursor + 0.05:
                    segments.append((cursor, pk_f, 1.0))
                if mini_end > pk_f + 0.05:
                    segments.append((pk_f, mini_end, MINI_SPEED))
                cursor = mini_end

        if t1 > cursor + 0.05:
            segments.append((cursor, t1, 1.0))
        if t2 > t1 + 0.05:
            segments.append((t1, t2, slowmo_speed))
        if t3 > t2 + 0.05:
            segments.append((t2, t3, slowmo_speed))
        if t4 > t3 + 0.05:
            segments.append((t3, t4, 1.0))

        mapped_t = 0.0
        for s_start, s_end, speed in segments:
            if t_orig < s_start:
                break
            elif t_orig <= s_end:
                mapped_t += (t_orig - s_start) / speed
                return mapped_t
            else:
                mapped_t += (s_end - s_start) / speed

        return mapped_t

    act_lower = (action_type or "").lower().strip()
    is_solo = act_lower in ("solo_bolo", "solo", "1v1", "first_blood", "first blood")

    caption_items = []
    if is_solo:
        # NON-MULTIKILL (Solo Bolo, Outplay, Clutch, First Blood, 1v1):
        # BEZWZGLĘDNY ZAKAZ wyświetlania Double/Triple/Quadra/Pentakill!
        # Renderujemy dokładnie JEDEN napis w punkcie kulminacyjnym.
        single_label = "SOLO BOLO" if act_lower in ("solo_bolo", "solo", "1v1") else (
            "FIRST BLOOD" if "first" in act_lower else (
                "1% HP CLUTCH" if "clutch" in act_lower else (
                    "OUTPLAY" if "outplay" in act_lower else "SOLO BOLO"
                )
            )
        )
        if peaks:
            best_p = min(peaks, key=lambda p: abs((p[0] if p[0] < trim_start or trim_start == 0.0 else p[0] - trim_start) - peak_moment))
            t_abs, _ = best_p
            t_raw = t_abs if (t_abs < trim_start or trim_start == 0.0) else (t_abs - trim_start)
            t_in_clip = _adjust_t(t_raw)
            if 0 <= t_in_clip <= video_duration:
                style = KILL_STYLES.get(single_label, {"size": 115, "color": "0xFF3333", "duration": 2.2})
                t_start = max(0.0, t_in_clip + 0.15)
                t_end = min(video_duration, t_start + style["duration"])
                clean_single = re.sub(r"[^\x00-\x7F]+", "", single_label).strip().replace("'", "\\'")
                caption_items.append({
                    "start": t_start,
                    "end": t_end,
                    "label": clean_single,
                    "style": style,
                    "t_in_clip": t_in_clip,
                })
    else:
        # Multikill: clamp banner tier to the maximum tier achieved (e.g. Double can never show Triple or Penta)
        MAX_TIER_MAP = {
            "double": "DOUBLE KILL",
            "triple": "TRIPLE KILL",
            "quadra": "QUADRAKILL",
            "quadrakill": "QUADRAKILL",
            "penta": "PENTAKILL",
            "pentakill": "PENTAKILL",
        }
        max_allowed_banner = MAX_TIER_MAP.get(act_lower, "PENTAKILL")
        TIER_ORDER = ["KILL", "DOUBLE KILL", "TRIPLE KILL", "QUADRAKILL", "PENTAKILL"]
        max_tier_idx = TIER_ORDER.index(max_allowed_banner) if max_allowed_banner in TIER_ORDER else len(TIER_ORDER) - 1

        for (t_abs, label) in peaks:
            t_raw = t_abs if (t_abs < trim_start or trim_start == 0.0) else (t_abs - trim_start)
            t_in_clip = _adjust_t(t_raw)
            if t_in_clip < 0 or t_in_clip > video_duration:
                continue

            clean_lbl = str(label).upper().strip()
            if clean_lbl in TIER_ORDER:
                curr_tier_idx = TIER_ORDER.index(clean_lbl)
                if curr_tier_idx > max_tier_idx:
                    clean_lbl = TIER_ORDER[max_tier_idx]

            style = KILL_STYLES.get(clean_lbl, {"size": 90, "color": "white", "duration": 2.0})
            t_start = max(0.0, t_in_clip + 0.15)
            t_end   = min(video_duration, t_start + style["duration"])

            clean_label = re.sub(r"[^\x00-\x7F]+", "", clean_lbl).strip()
            clean_label = clean_label.replace("'", "\\'")
            caption_items.append({
                "start": t_start,
                "end": t_end,
                "label": clean_label,
                "style": style,
                "t_in_clip": t_in_clip,
            })

    # Deduplikacja napisów: eliminacja nakładania się napisów z tej samej eliminacji (<1.4s)
    TIER_RANK = {
        "PENTAKILL": 10, "QUADRAKILL": 9, "TRIPLE KILL": 8, "DOUBLE KILL": 7,
        "SOLO BOLO": 6, "1% HP CLUTCH": 5, "CLUTCH": 5, "SHUTDOWN": 4,
        "GODLIKE": 4, "LEGENDARY": 4, "UNSTOPPABLE": 3, "KILLING SPREE": 3,
        "ONESHOT": 3, "OUTPLAY": 2, "KILL": 1
    }
    caption_items.sort(key=lambda x: x["start"])
    deduped_items = []
    for item in caption_items:
        if not deduped_items:
            deduped_items.append(item)
        else:
            prev = deduped_items[-1]
            if abs(item["start"] - prev["start"]) < 1.4:
                # Kolizja czasowa: wybierz napis o wyższej randze
                p_rank = TIER_RANK.get(prev["label"].upper(), 1)
                c_rank = TIER_RANK.get(item["label"].upper(), 1)
                if c_rank > p_rank:
                    deduped_items[-1] = item
            else:
                deduped_items.append(item)
    caption_items = deduped_items

    for i in range(len(caption_items) - 1):
        next_start = caption_items[i+1]["start"]
        if caption_items[i]["end"] > next_start:
            # Minimum: 60% normalnej długości stylu, aby napis zdążył się pokazać i był czytelny
            min_show = caption_items[i]["style"]["duration"] * 0.60
            caption_items[i]["end"] = max(caption_items[i]["start"] + min_show, next_start - 0.05)

    drawtext_filters = []
    total_kills = len(caption_items)

    for idx, item in enumerate(caption_items):
        t_start = item["start"]
        t_end   = item["end"]
        clean_label = item["label"]
        style = item["style"]

        is_multikill = bool(action_type and action_type.lower() in ("double", "triple", "quadrakill", "quadra", "pentakill", "penta"))
        if is_multikill and total_kills >= 2 and not is_solo:
            is_final_kill = (idx == total_kills - 1)
            hud_text = f"KILL {idx + 1}/{total_kills}" if not is_final_kill else f"FINAL KILL {idx + 1}/{total_kills}"
            hud_color = "0xFFD700" if is_final_kill else ("0xFFA500" if idx > 0 else "white")
            hud_box_w = 340 if is_final_kill else 260
            hud_box_h = 44
            hud_y_pos = "trunc(ih*0.13)"

            hud_dbox = (
                f"drawbox="
                f"x=trunc((iw-{hud_box_w})/2)"
                f":y={hud_y_pos}"
                f":w={hud_box_w}"
                f":h={hud_box_h}"
                f":color=black@0.65"
                f":t=fill"
                f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
            hud_dt = (
                f"drawtext="
                f"fontfile='{font_safe}'"
                f":text='{hud_text}'"
                f":x=(w-text_w)/2"
                f":y=h*0.135"
                f":fontsize=32"
                f":fontcolor={hud_color}"
                f":borderw=3"
                f":bordercolor=black"
                f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
                f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
            drawtext_filters.append(hud_dbox)
            drawtext_filters.append(hud_dt)

        box_h = style['size'] + 20
        approx_box_w = min(max(int(style['size'] * max(len(clean_label), 6) * 0.72), 400), 1020)
        box_x_expr = f"trunc((iw-{approx_box_w})/2)"
        box_y_expr = f"trunc(ih*0.55)-{box_h // 2}"
        dbox = (
            f"drawbox="
            f"x={box_x_expr}"
            f":y={box_y_expr}"
            f":w={approx_box_w}"
            f":h={box_h}"
            f":color=black@0.55"
            f":t=fill"
            f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
        )
        dt = (
            f"drawtext="
            f"fontfile='{font_safe}'"
            f":text='{clean_label}'"
            f":x=(w-text_w)/2"
            f":y=h*0.55"
            f":fontsize={style['size']}"
            f":fontcolor={style['color']}"
            f":borderw=5"
            f":bordercolor=black"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.8"
            f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
        )
        drawtext_filters.append(dbox)
        drawtext_filters.append(dt)
        print(f"   🗨️  {clean_label} (kill {idx+1}/{total_kills}) @ {item.get('t_in_clip', t_start):.1f}s (start {t_start:.1f}s) — {style['size']}px")

    progress_bar = (
        f"drawbox="
        f"x=0"
        f":y=ih-5"
        f":w='trunc(iw*min(1.0,t/{max(0.1, video_duration):.2f}))'"
        f":h=5"
        f":color=0xC89B3C@0.90"
        f":t=fill"
    )
    drawtext_filters.append(progress_bar)
    return drawtext_filters


def add_dynamic_captions(
    video_path: str,
    peaks: list,
    trim_start: float,
    video_duration: float,
    output_path: str,
    peak_moment: float = 0.0,
    slowmo_speed: float = 0.50,
    slowmo_duration: float = 1.5,
    action_type: str = "",
) -> str:
    """
    Nakłada wiele dynamicznych napisów — jeden na każdy wykryty kill peak.
    peaks = [(t_abs, label), ...] gdzie t_abs to czas w ORYGINALNYM klipie.
    trim_start = offset od którego zaczęto ciąć (do przeliczenia na czas w klipie).
    """
    drawtext_filters = build_dynamic_captions_filters(
        peaks=peaks,
        trim_start=trim_start,
        video_duration=video_duration,
        peak_moment=peak_moment,
        slowmo_speed=slowmo_speed,
        slowmo_duration=slowmo_duration,
        action_type=action_type,
    )
    if not drawtext_filters:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    vf_chain = ",".join(drawtext_filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf_chain,
        *get_optimal_encoder_args("high"),
        "-c:a", "copy",
        output_path
    ]
    print(f"🎬 Renderuję {len(drawtext_filters)} filtrów wizualnych (HUD, banery, neon progress bar)...")
    r = _run_ffmpeg(cmd, timeout=120.0, desc="add_dynamic_captions GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:600]
        print(f"⚠️  Dynamiczne napisy error (próbuję fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "copy",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=150.0, desc="add_dynamic_captions CPU")
        if r_cpu.returncode != 0:
            print(f"⚠️  Dynamiczne napisy CPU fallback error (pomijam): {r_cpu.stderr.decode('utf-8', errors='replace')[:600]}")
            import shutil as _sh
            _sh.copy(video_path, output_path)
    return output_path


def merge_music(video_path: str, music_path: Optional[str],
                output_path: str, video_duration: float,
                video_peak_time: float,
                game_audio_path: Optional[str] = None,
                kill_peaks: list = None,
                music_volume: Optional[float] = None,
                game_volume: Optional[float] = None,
                time_segments: Optional[list] = None) -> str:
    """Nakłada muzykę i miesza ją z oryginalnym dźwiękiem gry.

    video_peak_time = moment ciosu NA OSI GOTOWEGO FILMU (po zwolnieniach), nie w surowym klipie.
    kill_peaks      = (czas, etykieta) również na osi gotowego filmu.
    time_segments   = oś czasu z apply_editor_effects: dźwięk gry jest rozciągany tak samo jak obraz.

    video_path      = wideo bez audio (step4 po apply_editor_effects)
    game_audio_path = źródłowy klip z dźwiękiem gry (step1 — wyciety raw clip)
                      Jeśli None — spróbuj pobrać audio z video_path.
    """
    if not music_path or not os.path.exists(music_path):
        print("⚠️ Brak muzyki — eksportuję bez dźwięku")
        shutil.copy(video_path, output_path)
        return output_path

    fname = os.path.basename(music_path)

    # Drop: 1) sprawdzony uchem (MUSIC_DROP_VERIFIED), 2) detekcja librosa, 3) przybliżona mapa, 4) brak synchronizacji
    if fname in MUSIC_DROP_VERIFIED and fname in MUSIC_DROP_MAP:
        drop_time = MUSIC_DROP_MAP[fname]
    elif BEAT_DETECTOR_OK:
        drop_time = _get_drop_time(music_path, manual_map=MUSIC_DROP_MAP)
    else:
        drop_time = MUSIC_DROP_MAP.get(fname, 0.0)

    music_seek_args = []
    if drop_time > 0.0:
        music_start, drop_early = TL.music_start_for_drop(drop_time, video_peak_time)
        print(f"🎵 Beat Sync: drop piosenki = {drop_time}s, cios w gotowym filmie = {video_peak_time:.2f}s -> start piosenki = {music_start:.2f}s")
        if drop_early > 0.05:
            print(f"⚠️  Beat Sync: drop padnie {drop_early:.2f}s PRZED ciosem (drop utworu jest wcześniej niż cios w filmie) — wybierz utwór z późniejszym dropem")
        music_seek_args = ["-ss", f"{music_start:.3f}"]
        LAST_MUSIC_SYNC.update(track=fname, drop_time=drop_time, music_start=music_start, drop_early_sec=drop_early,
                               drop_verified=fname in MUSIC_DROP_VERIFIED, peak_in_output=round(video_peak_time, 3))
    else:
        print(f"🎵 Brak mapy dropu dla {fname} — puszczam od początku")
        LAST_MUSIC_SYNC.update(track=fname, drop_time=0.0, music_start=0.0, drop_early_sec=0.0, drop_verified=False,
                               peak_in_output=round(video_peak_time, 3))

    # Sprawdź źródło audio gry: preferuj game_audio_path (step1), fallback do video_path
    audio_source = game_audio_path if (game_audio_path and os.path.exists(game_audio_path)) else video_path
    probe = _run_ffmpeg([
        "ffprobe", "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_source
    ], timeout=15.0, desc="ffprobe audio stream check")
    has_game_audio = probe.stdout.decode("utf-8", errors="replace").strip() == "audio"

    # Seamless Loop: mikro-fade 40ms wyłącznie na styku zapętlenia (brak wyciszania 1.5s przed końcem)
    fade_dur = 0.04
    fade_start = max(0.0, video_duration - fade_dur)

    if has_game_audio and GAME_AUDIO_VOLUME > 0.0:
        # ── Miksuj dźwięk gry + muzykę przez amix ──────────────────────────────────
        game_vol  = game_volume if game_volume is not None else GAME_AUDIO_VOLUME
        music_vol = music_volume if music_volume is not None else MUSIC_VOLUME

        # Generuj dynamiczny boost audio gry przy killach (krzyk, announcer, uderzenie czaru)
        def _game_boost_expr(base, peaks):
            if not peaks:
                return f"{base:.2f}"
            parts = []
            for t, label in (peaks or []):
                dur = 1.6 if "PENTA" in label else (1.4 if "QUADRA" in label else 1.1)
                boost = 3.2 if "PENTA" in label else 2.4
                parts.append(f"between(t,{t:.2f},{t+dur:.2f})*{boost-1:.1f}")
            if not parts:
                return f"{base:.2f}"
            return f"min(3.5,{base:.2f}*(1+{'+'.join(parts)}))"

        # Dynamiczne wyciszanie muzyki (sidechain ducking) na KAŻDYM killu
        def _music_duck_expr(base, peaks):
            if not peaks:
                return f"{base:.2f}"
            duck_parts = []
            for t, label in (peaks or []):
                dur = 1.6 if "PENTA" in label else 1.2
                duck_factor = 0.65 if "PENTA" in label else 0.45
                duck_parts.append(f"between(t,{t:.2f},{t+dur:.2f})*{duck_factor:.2f}")
            if not duck_parts:
                return f"{base:.2f}"
            combined = "+".join(duck_parts)
            return f"max(0.10,{base:.2f}*(1-min(0.70,{combined})))"

        game_boost = _game_boost_expr(game_vol, kill_peaks)
        music_duck  = _music_duck_expr(music_vol, kill_peaks)

        # Dźwięk gry na tej samej osi czasu co obraz (inaczej po pierwszym zwolnieniu uderzenia słychać przed obrazem)
        warp_on = bool(WARP_GAME_AUDIO and time_segments and any(abs(sg["speed"] - 1.0) > 1e-6 for sg in time_segments))
        game_in = "[gwarp]" if warp_on else "[2:a]"
        warp_prefix = (TL.audio_warp_filter(time_segments, "2:a", "gwarp") + ";") if warp_on else ""
        filter_complex = (
            f"{warp_prefix}{game_in}loudnorm=I=-14:TP=-1.5:LRA=11,"
            f"volume=eval=frame:volume='{game_boost}',"
            f"afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}[ga];"
            f"[1:a]loudnorm=I=-17:TP=-1.5:LRA=11,"
            f"volume=eval=frame:volume='{music_duck}',"
            f"afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}[ma];"
            f"[ga][ma]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,           # input 0: wideo
            *music_seek_args,
            "-i", music_path,           # input 1: muzyka
            "-i", audio_source,         # input 2: game audio
            "-map", "0:v:0",
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-t", f"{video_duration:.3f}",
            output_path
        ]
        src_label = os.path.basename(audio_source)
        print(f"🎵 Miksuję dźwięk gry [{src_label}] ({int(game_vol*100)}%) + muzykę ({int(music_vol*100)}%) przez amix (Seamless Loop)")
    else:
        # ── Brak audio lub game audio wyłączone — tylko muzyka ────────────────
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            *music_seek_args, "-i", music_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-af", f"volume={MUSIC_VOLUME},loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}",
            "-t", f"{video_duration:.3f}",
            "-shortest",
            output_path
        ]
        print(f"🎵 Tylko muzyka ({int(MUSIC_VOLUME*100)}%) — brak dźwięku gry w źródle")

    r = _run_ffmpeg(cmd, timeout=120.0, desc="merge_music")
    if r.returncode != 0 and time_segments and "gwarp" in " ".join(str(c) for c in cmd):
        # Bezpiecznik: gdyby rozciąganie dźwięku gry zawiodło, miks jak dawniej (dźwięk gry bez zwolnień), nie sama muzyka
        print("⚠️  Rozciąganie dźwięku gry nie powiodło się — miksuję dźwięk gry bez zwolnień")
        return merge_music(video_path, music_path, output_path, video_duration, video_peak_time,
                           game_audio_path=game_audio_path, kill_peaks=kill_peaks,
                           music_volume=music_volume, game_volume=game_volume, time_segments=None)
    if r.returncode != 0:
        err_msg = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  Błąd zaawansowanego miksowania amix: {err_msg}")
        print("🔄  Automatyczny bezpieczny fallback audio: miksuję z muzyką bezpośrednio...")
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", video_path,
            *music_seek_args, "-i", music_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-af", f"volume={music_volume or MUSIC_VOLUME},afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}",
            "-t", f"{video_duration:.3f}",
            "-shortest",
            output_path
        ]
        r_fb = _run_ffmpeg(cmd_fallback, timeout=120.0, desc="merge_music fallback")
        if r_fb.returncode != 0:
            raise RuntimeError(f"Audio merge fallback error: {r_fb.stderr.decode('utf-8', errors='replace')[:600]}")
        print("✅  Audio nałożone pomyślnie przez bezpieczny fallback!")

    print("✅ Audio nałożone i zsynchronizowane (Seamless Loop ready)")
    return output_path


def prepend_freeze_hook(
    video_path: str,
    hook_text: str,
    output_path: str,
    freeze_duration: float = 0.6,
    clean_source_path: Optional[str] = None,
) -> str:
    """
    Wstawia freeze-frame z wielkim hookiem na początku shorta (0.0s – freeze_duration).

    Mechanizm:
      1. Wyciąga pierwszą klatkę jako [clean:v]trim=end=0.04,loop=N → freeze_duration s
      2. Na freeze narzuca drawbox + drawtext z hookiem (duże litery, góra ekranu)
      3. concat filter: [freeze][glowne wideo] → output
      4. Audio freeze = adelay (muzyka przesunięta o freeze_duration ms)

    Warunek wywołania: tylko gdy hook_text niepusty i action_type != solo_bolo
    """
    import re, shutil

    if not hook_text:
        shutil.copy(video_path, output_path)
        return output_path

    font = _get_font_path()
    if not font:
        print("brak czcionki — pomijam freeze hook")
        shutil.copy(video_path, output_path)
        return output_path

    # Sanityzacja tekstu (identyczna jak w add_text_overlay)
    clean_hook = re.sub(r'[^\x00-\x7F]+', '', hook_text).strip()
    clean_hook = clean_hook.replace("'", "")
    clean_hook = clean_hook.replace(":", "\\:")
    clean_hook = clean_hook.replace("%", "%%")
    if not clean_hook:
        shutil.copy(video_path, output_path)
        return output_path

    # Skroc hook do maks 32 znakow zeby zmiesci sie w 1080px
    if len(clean_hook) > 32:
        clean_hook = clean_hook[:29] + "..."

    font_safe = font.replace(chr(92), '/').replace(':', '\\:')

    # Ile klatek freeze (fps=30 → 18 klatek ≈ 0.6s)
    n_loop = max(18, int(freeze_duration * 30))

    # Rozmiar tekstu — dynamiczny wzgledem dlugosci
    fsize = max(68, min(110, int(3700 // max(len(clean_hook), 1))))

    # Szerokosc tla pod tekst
    approx_w = min(max(int(len(clean_hook) * fsize * 0.55) + 60, 400), 1060)

    drawbox = (
        f"drawbox="
        f"x=trunc((iw-{approx_w})/2)"
        f":y=trunc(ih*0.06)"
        f":w={approx_w}"
        f":h={int(fsize * 1.45)}"
        f":color=black@0.72"
        f":t=fill"
    )
    drawtext = (
        f"drawtext="
        f"fontfile='{font_safe}'"
        f":text='{clean_hook}'"
        f":x=(w-text_w)/2"
        f":y=h*0.075"
        f":fontsize={fsize}"
        f":fontcolor=0xFFD700"
        f":borderw=5"
        f":bordercolor=black"
        f":shadowx=3:shadowy=3:shadowcolor=black@0.85"
    )

    # Strzalka pod tekstem (v = wizualna wskazowka ze idzie dalej)
    arrow_y = int(0.075 * 1920) + int(fsize * 1.45) + 8
    arrow_text = (
        f"drawtext="
        f"fontfile='{font_safe}'"
        f":text='v'"
        f":x=(w-text_w)/2"
        f":y={arrow_y}"
        f":fontsize=52"
        f":fontcolor=white@0.85"
        f":borderw=3"
        f":bordercolor=black"
    )

    # filter_complex: freeze segment z hookiem, concat z glownym wideo
    # Używamy clean_source_path (jeśli dostępny), aby tło klatki freeze było czyste bez podwójnego tekstu
    delay_ms = int(freeze_duration * 1000)
    has_clean = bool(clean_source_path and os.path.exists(clean_source_path))
    frz_in = "1:v" if has_clean else "0:v"
    inputs = ["-i", video_path]
    if has_clean:
        inputs.extend(["-i", clean_source_path])

    fc = (
        f"[{frz_in}]trim=end=0.04,loop={n_loop}:size=1:start=0,setpts=N/FRAME_RATE/TB,"
        f"{drawbox},{drawtext},{arrow_text}[frz];"
        f"[0:v]setpts=PTS-STARTPTS[main];"
        f"[frz][main]concat=n=2:v=1:a=0[outv];"
        f"[0:a]adelay=delays={delay_ms}:all=1,apad[outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", fc,
        "-map", "[outv]",
        "-map", "[outa]",
        *get_optimal_encoder_args("high"),
        "-shortest",
        output_path
    ]
    print(f"Freeze hook: '{clean_hook}' ({freeze_duration:.1f}s) -> {os.path.basename(output_path)}")
    r = _run_ffmpeg(cmd, timeout=120.0, desc="prepend_freeze_hook GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:500]
        print(f"Freeze hook GPU error (CPU fallback): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", fc,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=180.0, desc="prepend_freeze_hook CPU")
        if r_cpu.returncode != 0:
            print(f"Freeze hook CPU error (pomijam): {r_cpu.stderr.decode('utf-8', errors='replace')[:400]}")
            shutil.copy(video_path, output_path)
    return output_path


def get_engagement_cta(action_type: str = "", champion: str = "", hook_text: str = "") -> str:
    """
    Zwraca wysoce konwertujące wezwanie do zaangażowania (Like Rate & Comment Rate)
    dopasowane do typu akcji i postaci.
    Zastępuje konfundujące 'AND THIS IS WHY IT WAS A...' bezpośrednim sygnałem
    zwiększającym Like Rate (z 0.2% do 3%+), co podbija algorytm Shorts do wyższych tierów.
    """
    act = (action_type or "").lower().strip()
    champ = (champion or "").upper().strip()

    cta_map = {
        "solo_bolo": [
            "LIKE IF THAT WAS CLEAN!",
            "WOULD YOU WIN THIS 1v1?",
            "CLEAN OR DISRESPECTFUL?",
            "DROP A LIKE FOR THE DUEL!",
            "1 TO 10: RATE THIS 1v1",
        ],
        "pentakill": [
            "LIKE FOR THE PENTA RESET!",
            "CAN YOUR MAIN DO THIS?",
            "1 TO 10: RATE THIS PENTA",
            "WOULD YOU SURVIVE THIS? COMMENT 👇",
            "DROP A LIKE FOR THE ACE!",
        ],
        "quadrakill": [
            "LIKE IF HE DESERVED PENTA!",
            "DROP A LIKE FOR THE CHASE!",
            "CLEAN QUADRA OR ENEMY THROW?",
            "CLEAN OR ENEMY INT? DROP A LIKE! 🔥",
        ],
        "triple": [
            "LIKE IF THAT RESET WAS CLEAN!",
            "CLEAN OR ENEMY DIFF? COMMENT BELOW",
            "WOULD YOU SURVIVE THIS?",
            f"DROP A LIKE FOR {champ}!" if champ else "DROP A LIKE FOR THE TRIPLE!",
            "DROP A SUB IF YOU WOULD FLASH! 💀",
        ],
        "double": [
            "LIKE IF THAT 2v1 WAS CLEAN!",
            "CLEAN OUTPLAY OR LUCKY?",
            "DROP A LIKE IF YOU WOULD FLASH!",
            f"DROP A LIKE FOR {champ}!" if champ else "DROP A LIKE FOR THE PLAY!",
        ],
        "clutch": [
            "HOW DID HE SURVIVE THIS?",
            "LIKE IF YOU WOULD PANIC HERE!",
            "DROP A LIKE FOR THE 1% HP!",
            "CLEAN OR PURE LUCK? COMMENT BELOW",
        ],
        "outplay": [
            "CLEAN OR LUCKY? COMMENT BELOW",
            "LIKE IF YOU WOULD PANIC HERE!",
            "RATE THIS OUTPLAY: 1 TO 10?",
            f"DROP A LIKE FOR {champ}!" if champ else "DROP A LIKE FOR THE OUTPLAY!",
            "RATE THIS OUTPLAY: 1 TO 10? 👇",
        ],
    }

    candidates = cta_map.get(act)
    if not candidates:
        if "solo" in act or "1v1" in act:
            candidates = cta_map["solo_bolo"]
        elif "penta" in act:
            candidates = cta_map["pentakill"]
        elif "quadra" in act:
            candidates = cta_map["quadrakill"]
        elif "triple" in act:
            candidates = cta_map["triple"]
        elif "double" in act:
            candidates = cta_map["double"]
        elif "clutch" in act or "1hp" in act:
            candidates = cta_map["clutch"]
        else:
            candidates = cta_map["outplay"]

    seed_val = sum(ord(c) for c in (hook_text or act or "lol"))
    return candidates[seed_val % len(candidates)]


def get_seamless_loop_cta(hook_text: str, action_type: str = "") -> str:
    """
    Generuje wezwanie / hook końcowy, który płynnie i gramatycznie
    zapętla się z początkowym tekstem hooka (Infinite Retention Loop).
    Gdy widz ogląda końcówkę Shorts, tekst CTA wprowadza myśl,
    która zostaje natychmiast dokończona przez pierwszą klatkę wideo (t=0s).
    """
    hook_upper = (hook_text or "").upper().strip()
    act_lower = (action_type or "").lower().strip()

    if "WRONG MOVE" in hook_upper or "WATCH WHAT HAPPENS" in hook_upper:
        return "AND THIS IS WHY IT WAS A..."
    elif "CAN HE WIN" in hook_upper or "CAN HE SURVIVE" in hook_upper:
        return "REWATCH TO SEE HOW HE WINS A..."
    elif "DIDNT EXPECT" in hook_upper or "DIDN'T EXPECT" in hook_upper:
        return "AND THIS IS WHY THE..."
    elif "SOLO BOLO" in hook_upper or "SOLO" in hook_upper or "1V1" in hook_upper:
        return "AND THAT'S HOW YOU PLAY A..."
    elif "PENTA" in hook_upper or "PENTAKILL" in hook_upper or "penta" in act_lower:
        return "AND THAT'S HOW YOU GET A..."
    elif "QUADRA" in hook_upper or "quadra" in act_lower:
        return "AND THAT'S HOW YOU GET A..."
    elif "TRIPLE" in hook_upper or "triple" in act_lower:
        return "AND THAT'S HOW YOU SECURE A..."
    elif "DOUBLE" in hook_upper or "double" in act_lower:
        return "AND THAT'S HOW YOU PULL OFF A..."
    elif "1HP" in hook_upper or "CLUTCH" in hook_upper or "clutch" in act_lower:
        return "REWATCH TO SEE HOW HE SURVIVED..."
    elif "OUTPLAY" in hook_upper or "outplay" in act_lower:
        return "AND THIS IS WHY IT WAS AN..."
    else:
        return "AND THIS IS WHY IT WAS A..."


def build_cta_overlay_filters(
    video_duration: float,
    cta_text: str = "SUBSCRIBE FOR MORE!",
    show_duration: float = 2.0,
) -> list[str]:
    """
    Buduje filtry FFmpeg drawbox i drawtext dla wezwania do akcji (CTA).
    """
    if not cta_text:
        return []

    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki — pomijam CTA overlay")
        return []

    import re
    font_safe = font.replace(chr(92), '/').replace(':', '\\:')
    clean_cta = re.sub(r'[^\x00-\x7F]+', '', cta_text).strip()
    clean_cta = clean_cta.replace("'", "\\\\'")
    clean_cta = clean_cta.replace(":", "\\:")
    clean_cta = clean_cta.replace("%", "%%")

    if not clean_cta:
        return []

    t_start = max(0.0, video_duration - show_duration)
    t_end   = video_duration

    # Dynamiczne dopasowanie rozmiaru czcionki do szerokości 1080px
    cta_len = len(clean_cta)
    fsize = 55
    if cta_len > 28:
        fsize = max(36, int(55 * 28 / cta_len))

    # Dolna bezpieczna strefa (y=ih*0.74) — nad HUDem gracza, nie zasłania banerów killi u góry
    cta_box = (
        f"drawbox="
        f"x=0"
        f":y=ih*0.68"
        f":w=iw"
        f":h=ih*0.08"
        f":color=black@0.50"
        f":t=fill"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )
    drawtext = (
        f"drawtext="
        f"fontfile='{font_safe}'"
        f":text='{clean_cta}'"
        f":x=(w-text_w)/2"
        f":y=h*0.70"
        f":fontsize={fsize}"
        f":fontcolor=0xFFD700"
        f":borderw=4"
        f":bordercolor=black"
        f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )
    return [cta_box, drawtext]


def add_cta_overlay(
    video_path: str,
    video_duration: float,
    output_path: str,
    cta_text: str = "SUBSCRIBE FOR MORE!",
    show_duration: float = 2.0,
) -> str:
    """
    Nakłada wezwanie do subskrypcji (CTA) na ostatnie `show_duration` sekund wideo.
    Tekst pojawia się u góry ekranu — poza zasłoniętą strefą UI YouTube Shorts.
    """
    filters = build_cta_overlay_filters(video_duration, cta_text, show_duration)
    if not filters:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    vf_chain = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf_chain,
        *get_optimal_encoder_args("draft"),
        "-movflags", "+faststart",
        "-c:a", "copy",
        output_path
    ]
    r = _run_ffmpeg(cmd, timeout=90.0, desc="add_cta_overlay GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  CTA overlay error (próbuję fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-movflags", "+faststart",
            "-c:a", "copy",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=120.0, desc="add_cta_overlay CPU")
        if r_cpu.returncode != 0:
            print(f"⚠️  CTA overlay CPU fallback error (pomijam): {r_cpu.stderr.decode('utf-8', errors='replace')[:400]}")
            import shutil as _sh
            _sh.copy(video_path, output_path)
    return output_path


def apply_overlays_unified(
    video_path: str,
    output_path: str,
    peaks: list = None,
    trim_start: float = 0.0,
    video_duration: float = 0.0,
    peak_moment: float = 0.0,
    slowmo_speed: float = 0.50,
    slowmo_duration: float = 1.5,
    action_type: str = "",
    hook_text: str = "",
    cta_text: str = "",
    cta_duration: float = 1.8,
    time_segments: Optional[list] = None,
) -> str:
    """
    Łączy dynamiczne napisy kill-by-kill, hook overlay oraz CTA overlay
    w jeden zunifikowany filtergraph FFmpeg (Task B2).
    Eliminuje 2 zbędne fazy re-enkodowania i 2 pliki tymczasowe na dysku.
    """
    filters = []

    # 1. Dynamic captions (HUD + Kill Banners + Neon Scrubber)
    if peaks:
        cap_filters = build_dynamic_captions_filters(
            peaks=peaks,
            trim_start=trim_start,
            video_duration=video_duration,
            peak_moment=peak_moment,
            slowmo_speed=slowmo_speed,
            slowmo_duration=slowmo_duration,
            action_type=action_type,
            time_segments=time_segments,
        )
        filters.extend(cap_filters)

    # 2. Hook overlay (0.0s - 2.5s)
    if hook_text and hook_text.strip():
        hook_filters = build_text_overlay_filters(
            hook_text=hook_text.strip(),
            peak_moment=0.0,
            video_duration=video_duration,
            show_duration=2.5,
        )
        filters.extend(hook_filters)

    # 3. CTA overlay (ostatnie cta_duration s)
    if cta_text and cta_text.strip():
        cta_filters = build_cta_overlay_filters(
            video_duration=video_duration,
            cta_text=cta_text.strip(),
            show_duration=cta_duration,
        )
        filters.extend(cta_filters)

    if not filters:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    vf_chain = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf_chain,
        *get_optimal_encoder_args("high"),
        "-movflags", "+faststart",
        "-c:a", "copy",
        output_path
    ]
    print(f"🎬 [Unified Overlays] Renderuję {len(filters)} filtrów w jednym przejściu FFmpeg...")
    r = _run_ffmpeg(cmd, timeout=120.0, desc="apply_overlays_unified GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:600]
        print(f"⚠️  Unified overlays GPU error (fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_chain,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-movflags", "+faststart",
            "-c:a", "copy",
            output_path
        ]
        r_cpu = _run_ffmpeg(cmd_cpu, timeout=150.0, desc="apply_overlays_unified CPU")
        if r_cpu.returncode != 0:
            print(f"⚠️  Unified overlays CPU error (fallback copy): {r_cpu.stderr.decode('utf-8', errors='replace')[:600]}")
            import shutil as _sh
            _sh.copy(video_path, output_path)
    return output_path


def render_short(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str = "outplay",
    champion_name: str = "",
    rank: str = "",
    use_speed_ramp: bool = True,
    use_zoom_punch: bool = True,
    use_smart_camera: bool = True,
    peak_moment: float = 0.0,
    hook_text: str = "",
    peaks: list = None,
    preferred_track: Optional[str] = None,
    output_filename: str = "lol_short_final.mp4",
    combat_segments: list = None,
    custom_temp_dir: Optional[str] = None,
) -> str:
    """
    Pipeline montażu v6 — Combat-Segment-Aware editing:
      1. Wycięcie fragmentów (jump-cut gdy combat_segments dostarczone)
      2. Smart Camera crop (dynamic tracking)
      3. Filtry wizualne (Crop, Scale, Zoom-punch, Speed-ramp + minterpolate)
      4. Muzyka z momentum sync + miksowanie z dźwiękiem gry (amix)
      5. Dynamiczne napisy kill-by-kill
      6. Hook overlay
      7. Subscribe CTA overlay (ostatnie 2s)

    combat_segments: [(start, end), ...] w osi czasu oryginalnego klipu.
      Gdy podane — każda przerwa miedzy segmentami jest JUMP CUT'em (bieganie usuwane).
      Gdy None — fallback do pojedynczego okna clip_start→clip_end.
    """
    ensure_temp_dir()
    clip_duration = clip_end - clip_start

    print(f"\n{'='*55}")
    print(f"🎬  LOL EDITOR v6 — {action_type.upper()} | {champion_name} | {clip_duration:.1f}s")
    print(f"{'='*55}")

    _tmp = custom_temp_dir or LOL_TEMP_DIR
    t = lambda name: os.path.join(_tmp, name)
    step1        = t("01_cut.mp4")
    step4        = t("04_processed.mp4")
    step5_music  = t("05_music.mp4")
    step5        = os.path.join(_tmp, output_filename)

    # ── KROK 1: Wycięcie fragmentu / segmentów ────────────────────────────────
    print("\n[1/4] Wycinanie fragmentu...")

    # ── ADAPTIVE MONTAGE DIRECTOR (AI Decyzja scenariuszowa) ───────────────────
    director_decision = None
    try:
        try:
            from lol_agent.lol_montage_director import direct_clip_montage
        except ImportError:
            from lol_montage_director import direct_clip_montage
        director_decision = direct_clip_montage(
            action_type=action_type,
            champion_name=champion_name,
            duration=clip_duration,
            peaks=peaks or []
        )
        if director_decision:
            print(f"🎬  Reżyser AI [{director_decision.archetype}]: Jump-Cut={director_decision.allow_jump_cut}, Zoom={director_decision.zoom_aggression:.2f}x, Slowmo={director_decision.slowmo_duration:.1f}s")
            print(f"    Uzasadnienie: {director_decision.rationale}")
    except Exception as _dir_err:
        print(f"    [editor] Montage director fallback: {_dir_err}")

    # Dla SOLO BOLO wykluczamy jakiekolwiek cięcia jump-cut — cała walka ma być płynna od wejścia do finału
    if action_type.lower() in ("solo_bolo", "solo", "1v1"):
        combat_segments = None
    elif director_decision and not director_decision.allow_jump_cut:
        print(f"   🛡️  Director Lock: Archetyp {director_decision.archetype} zabrania jump-cutów — zachowuję pełną ciągłość walki!")
        combat_segments = None

    if combat_segments and len(combat_segments) > 1:
        tot_seg_dur = sum(e - s for s, e in combat_segments)
        if tot_seg_dur < 10.0:
            print(f"   🛡️  Jump-Cut Abort: Łączny czas segmentów ({tot_seg_dur:.1f}s) < 10s — montaż ciągły zachowuje pełną walkę!")
            combat_segments = None
        # Safeguard: Sprawdź czy przerwa między segmentami nie zawiera aktywnej walki
        # (np. zabójstwo Jhina przykryte powiadomieniem zniszczenia wieży)
        try:
            try:
                from lol_agent.lol_quality_validator import _check_enemy_combat_in_frame
            except ImportError:
                from lol_quality_validator import _check_enemy_combat_in_frame
            import cv2
            cap = cv2.VideoCapture(source_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            gap_s = combat_segments[0][1] + 1.0
            gap_e = combat_segments[1][0] - 1.0
            if gap_e > gap_s + 1.0:
                test_ts = np.linspace(gap_s, gap_e, 5)
                c_hits = 0
                for ts in test_ts:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
                    ret, fr = cap.read()
                    if ret:
                        has_c, px, _ = _check_enemy_combat_in_frame(fr)
                        if has_c and px > 350:
                            c_hits += 1
                if c_hits >= 2:
                    print("   🛡️  Combat Continuity Guard: Wykryto walkę w luce między segmentami — anuluję jump-cut!")
                    combat_segments = None
            cap.release()
        except Exception as ge:
            print(f"   [editor] Gap combat check err: {ge}")

    if combat_segments and len(combat_segments) > 1:
        # ── Multi-segment jump-cut ──────────────────────────────────────────
        print(f"   ✂️  Jump-cut mode: {len(combat_segments)} segmentów walki")
        seg_files = []
        concat_list_path = t("concat_list.txt")

        for i, (seg_s, seg_e) in enumerate(combat_segments):
            seg_path = t(f"seg_{i:02d}.mp4")
            cut_clip(source_path, seg_s, seg_e, seg_path, smooth_seams=True)
            seg_files.append((seg_path, seg_s, seg_e))

        # Zbuduj listę FFmpeg concat demuxer
        with open(concat_list_path, "w", encoding="utf-8") as cf:
            for seg_path, _, _ in seg_files:
                safe = seg_path.replace("\\", "/")
                cf.write(f"file '{safe}'\n")

        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            step1
        ]
        print(f"   🔗 Łączę {len(seg_files)} segmentów → {os.path.basename(step1)}")
        r = _run_ffmpeg(concat_cmd, timeout=120.0, desc="concat combat segments")
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", errors="replace")[:400]
            print(f"   ⚠️  Concat error (fallback do single cut): {err}")
            cut_clip(source_path, clip_start, clip_end, step1)
            combat_segments = None  # wyłącz remap peaków

        # ── Remapuj peaks na nową oś czasu po połączeniu ──────────────────
        if combat_segments:
            clip_duration = sum(e - s for s, e in combat_segments)
            orig_clip_start = clip_start
            clip_start = 0.0
            clip_end = clip_duration
            if peaks:
                remapped = []
                cursor = 0.0
                # Sprawdź czy peaks są względne do początku całego klipu
                is_relative = (peaks[0][0] < orig_clip_start)
                norm_peaks = [
                    (round(orig_clip_start + pk_t, 3), pk_lbl) if is_relative else (pk_t, pk_lbl)
                    for (pk_t, pk_lbl) in peaks
                ]
                for seg_path, seg_s, seg_e in seg_files:
                    seg_dur = seg_e - seg_s
                    for (abs_pk_t, pk_lbl) in norm_peaks:
                        if seg_s <= abs_pk_t <= seg_e:
                            new_t = cursor + (abs_pk_t - seg_s)
                            remapped.append((round(new_t, 3), pk_lbl))
                    cursor += seg_dur
                if remapped:
                    print(f"   🗺️  Peaks remapped: {[f'{t:.1f}s:{l}' for t,l in remapped]}")
                    peaks = remapped
                    peak_moment = max(0.0, peaks[-1][0] - 0.5)
    else:
        orig_clip_start = clip_start
        cut_clip(source_path, clip_start, clip_end, step1)
        # Remapuj peaks do czasu lokalnego step1 (0.0 -> clip_duration)
        if peaks:
            # Jeśli którykolwiek znacznik przekracza długość wycinka, peaks są w osi czasu całego źródła
            is_source_timeline = any(t_k > clip_duration for (t_k, _) in peaks)
            if is_source_timeline and orig_clip_start > 0:
                peaks = [
                    (round(t_k - orig_clip_start, 3), lbl)
                    for (t_k, lbl) in peaks
                    if (orig_clip_start - 0.5) <= t_k <= (clip_end + 0.5)
                ]
            else:
                peaks = [(round(t_k, 3), lbl) for (t_k, lbl) in peaks if 0.0 <= t_k <= clip_duration]

        if peak_moment > clip_duration and orig_clip_start > 0:
            peak_moment = max(0.5, min(clip_duration - 0.5, peak_moment - orig_clip_start))
        elif peaks and (peak_moment <= 0.0 or peak_moment > clip_duration):
            banner_latency = 1.0
            peak_moment = max(0.5, min(clip_duration - 0.5, peaks[-1][0] - banner_latency))
        elif peak_moment <= 0.0 or peak_moment > clip_duration:
            peak_moment = max(0.5, min(clip_duration - 0.5, clip_duration * 0.75))
        clip_start = 0.0
        clip_end = clip_duration


    # KROK 2: Smart Camera Crop do 9:16 (znajdź ścieżkę na wyciętym pliku step1)
    print("\n[2/4] Smart Camera crop...")
    crop_x_expr = "-1"   # default: centrum geometryczne
    if use_smart_camera and SMART_CAMERA_AVAILABLE:
        try:
            path_points = find_action_path(
                step1,
                0.0, clip_duration,
                source_w=1920, source_h=1080,
                crop_w=TL.vertical_crop_width(1080),
                peaks=peaks or []     # <- kill-snap: champion locked during kills
            )
            # Champion centering: BANNER_SHIFT is fixed at 0 to guarantee the player
            # is always 100% centered in 9:16 frame without artificial horizontal offset.
            crop_x_expr = generate_ffmpeg_pan_expression(path_points)
        except Exception as e:
            print(f"   Blad sledzenia sciezki: {e} — fallback do centrum")
            crop_x = find_action_crop_x(
                step1,
                0.0, clip_duration,
                source_w=1920, source_h=1080,
                crop_w=TL.vertical_crop_width(1080)
            )
            crop_x_expr = f"{crop_x}"

    # KROK 3: Zastosuj efekty wizualne — parametry dopasowane do wagi akcji
    print("\n[3/4] Nakładanie efektów (crop, zoom, speed ramp)...")

    # Załaduj parametry z aktywnego profilu (Ekstremalnie Szybkie / Zbalansowane / Cinematic)
    try:
        from lol_agent.tuning_manager import get_pacing_parameters
    except ImportError:
        try:
            from tuning_manager import get_pacing_parameters
        except ImportError:
            get_pacing_parameters = lambda: {}

    tuning_p = get_pacing_parameters()
    is_solo_fight = action_type.lower() in ("solo_bolo", "solo", "1v1")

    if is_solo_fight:
        # SOLO BOLO: Walka 1v1 ma być dynamiczna i płynna (60 FPS) od 1-ego tradu do zabójstwa.
        # Bezpieczny zoom 1.10x gwarantuje pełną widoczność obu postaci w kadrze.
        _zoom_level   = 1.10
        _zoom_dur     = 0.40
        _slowmo_dur   = 0.55
        _slowmo_speed = 0.70
    elif director_decision:
        _zoom_level   = director_decision.zoom_aggression
        _zoom_dur     = 0.55
        _slowmo_dur   = director_decision.slowmo_duration
        _slowmo_speed = 0.55
    else:
        _zoom_level   = min(1.12, float(tuning_p.get("zoom_aggression", 1.15)))
        _zoom_dur     = 0.60
        _slowmo_dur   = float(tuning_p.get("slowmo_duration", 1.2))
        _slowmo_speed = 0.55

    _music_vol    = float(tuning_p.get("music_balance", 0.85))
    _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))

    print(f"   ⚙️  Profil montażu ({'SOLO BOLO' if is_solo_fight else tuning_p.get('id', 'default')}): zoom={_zoom_level:.2f}x, slowmo={_slowmo_dur:.1f}s ({_slowmo_speed}x), muzyka={int(_music_vol*100)}%, gra={int(_game_vol*100)}%")

    # Normalizacja peak_moment do lokalnej osi czasu wyciętego klipu (0.0 -> clip_duration):
    rel_peak_moment = peak_moment
    if clip_start > 0.0 and peak_moment >= clip_start:
        rel_peak_moment = peak_moment - clip_start
    elif peak_moment > clip_duration and clip_duration > 0.0:
        rel_peak_moment = min(clip_duration * 0.70, max(1.0, peak_moment % clip_duration))

    # Guard pustych peaks: jeśli detektor CV/OCR nie wychwycił zabójstw, ZAWSZE tworzymy punkt kulminacji!
    if not peaks:
        fallback_label = {
            "pentakill": "PENTAKILL",
            "quadrakill": "QUADRAKILL",
            "triple": "TRIPLE KILL",
            "double": "DOUBLE KILL",
            "solo_bolo": "SOLO BOLO",
            "clutch": "CLUTCH",
            "outplay": "OUTPLAY",
        }.get(action_type.lower(), "OUTPLAY")
        default_t = rel_peak_moment if (0.5 < rel_peak_moment < clip_duration - 0.5) else round(clip_duration * 0.70, 1)
        peaks = [(round(clip_start + default_t, 2), fallback_label)]
        print(f"   🎯 [Editor Guard] Brak detekcji zabójstw w CV — ustawiam punkt kulminacji: {default_t:.1f}s ({fallback_label})")

    # Intermediate peaks: wszystkie kille PRZED ostatnim -> mini slow-mo na moment uderzenia (last-hit)
    _all_kill_rel = sorted([(t_k if (t_k < clip_start or clip_start == 0.0) else (t_k - clip_start)) for (t_k, _) in (peaks or [])])
    _inter_peaks  = [max(0.2, round(p - 0.50, 2)) for p in _all_kill_rel[:-1]] if len(_all_kill_rel) > 1 else []
    if _inter_peaks:
        print(f"   ⚡ Intermediate peaks (mini slow-mo): {[f'{p:.1f}s' for p in _inter_peaks]}")

    _timeline = {}
    final_duration = apply_editor_effects(
        input_path=step1,
        output_path=step4,
        clip_duration=clip_duration,
        crop_x=crop_x_expr,
        peak_moment=rel_peak_moment,
        zoom_level=_zoom_level if use_zoom_punch else 1.0,
        zoom_duration=_zoom_dur,
        slowmo_speed=_slowmo_speed if use_speed_ramp else 1.0,
        slowmo_duration=_slowmo_dur,
        intermediate_peaks=_inter_peaks if use_speed_ramp else [],
        timeline_out=_timeline,
    )
    _segments = _timeline.get("segments") or []
    # Cios na osi GOTOWEGO filmu (po zwolnieniach). Przed 11.11.2026 muzyka dostawała czas surowy
    # i przy multikillach drop padał nawet ~0.8 s przed ciosem.
    _mapped_peak = _timeline.get("mapped_peak", rel_peak_moment)
    if abs(_mapped_peak - rel_peak_moment) > 0.02:
        print(f"   🧭 Oś czasu: cios {rel_peak_moment:.2f}s (klip) → {_mapped_peak:.2f}s (gotowy film), długość {final_duration:.2f}s")

    # KROK 4: Muzyka dopasowana do akcji z beat-sync
    print("\n[4/7] Muzyka i synchronizacja beat-sync + miksowanie audio gry...")
    music = pick_music_for_action(action_type, preferred_track=preferred_track or ("ncs_egzod_royalty.mp3" if action_type == "pentakill" else None))
    # Przekazuj step1 (surowy wycinek z audio gry) jako game_audio_path
    # step4 nie ma audio (apply_editor_effects mapuje tylko [v_final])
    _rel_kill_peaks = [((tk if (tk < clip_start or clip_start == 0.0) else (tk - clip_start)), lbl) for (tk, lbl) in (peaks or [])]
    _out_kill_peaks = TL.warp_peaks(_segments, _rel_kill_peaks) if _segments else _rel_kill_peaks
    merge_music(step4, music, step5_music, final_duration, _mapped_peak,
                game_audio_path=step1, kill_peaks=_out_kill_peaks,
                music_volume=_music_vol, game_volume=_game_vol, time_segments=_segments)

    # ── KROK 5+6+7: Zunifikowany montaż nakładek (Unified Overlays — Task B2) ──
    _hook = hook_text.strip() if hook_text else ""
    if not _hook:
        try:
            from lol_agent.lol_config import ACTION_LABELS
        except ImportError:
            from lol_config import ACTION_LABELS
        _hook = ACTION_LABELS.get(action_type, "").replace("🔥","").replace("⚡","").replace("💥","").replace("🎯","").replace("👑","").strip()
    if not _hook:
        _hook = f"{champion_name.upper()} {action_type.upper()}" if champion_name else action_type.upper()

    _end_cta = get_engagement_cta(action_type=action_type, champion=champion_name, hook_text=_hook)

    print(f"\n[5/6] Zunifikowane nakładki (Dynamic Captions + Hook '{_hook[:25]}' + CTA '{_end_cta[:25]}')...")
    apply_overlays_unified(
        video_path=step5_music,
        output_path=step5,
        peaks=peaks or [],
        trim_start=clip_start,
        video_duration=final_duration,
        peak_moment=rel_peak_moment,
        slowmo_speed=_slowmo_speed,
        slowmo_duration=_slowmo_dur,
        action_type=action_type,
        hook_text=_hook,
        cta_text=_end_cta,
        cta_duration=1.8,
        time_segments=_segments,
    )

    # ── KROK 8: Freeze-frame hook na klatce 0.0s (P2 — Hook Frame Zero) ─────────
    # Wstawia 0.6s freeze pierwszej klatki z hookiem żeby zatrzymać scrollera.
    # Nie dotyczy solo_bolo (tam walka zaczyna się natychmiast — freeze by zepsuła dynamikę).
    # Guard: jeśli pierwszy kill jest w pierwszych 3s klipu → pomijamy freeze (pierwsza akcja by zniknęła).
    _first_kill_t = min((t_k for (t_k, _) in (peaks or [])), default=999.0)
    _action_starts_immediately = _first_kill_t <= 3.0
    # Seamless Loop Standard: freeze frame na klatce 0.0s wprowadzał 0.6s zamrożenia obrazu i 600ms ciszy audio (adelay),
    # co niszczyło płynność zapętlenia na YouTube Shorts. Zamiast statycznej stop-klatki, dynamiczne napisy z KROKU 5
    # nakładają się w locie na wideo w pełnym 60 FPS ruchu bez opóźnień audio.
    _do_freeze = False
    if bool(_hook):
        print(f"\n[8/8] Freeze-frame hook: POMINIĘTY (Seamless Loop Standard — dynamiczny overlay w ruchu)")
    if _do_freeze:
        step5_freeze = t("08_freeze_hook.mp4")
        print(f"\n[8/8] Freeze-frame hook: '{_hook[:30]}' (0.6s freeze na starcie)...")
        prepend_freeze_hook(
            video_path=step5,
            hook_text=_hook,
            output_path=step5_freeze,
            freeze_duration=0.6,
            clean_source_path=step5_music,
        )
        if os.path.exists(step5_freeze) and os.path.getsize(step5_freeze) > 10_000:
            import shutil as _shfz
            _shfz.move(step5_freeze, step5)
            final_duration += 0.6
            print(f"   Freeze hook wklejony — nowa dlugosc: {final_duration:.1f}s")
        else:
            print("   Freeze hook: plik wyjsciowy niepoprawny — pomijam")
            if os.path.exists(step5_freeze):
                os.remove(step5_freeze)
    else:
        print(f"\n[8/8] Freeze-frame hook: pomijam (solo_bolo lub brak hooka)")
    # ─────────────────────────────────────────────────────────────────────────

    # ── POST-RENDER 15s SNAP ─────────────────────────────────────────────────
    # ZABEZPIECZENIE: Nigdy nie tnij początku wyrenderowanego klipu przez -c copy!
    # -c copy bez re-enkodowania niszczy GOP/PTS (powoduje 2s freeze obrazu)
    # oraz wycina pierwszy frag (np. doskok do sztyletu i zabójstwo Kai'sy w pierwszych 1.5s).
    # Całkowity czas akcji jest już kontrolowany na etapie compute_optimal_clip_window (14.5s).
    # ─────────────────────────────────────────────────────────────────────────


    # ── PRZEPIS SHORTA ──────────────────────────────────────────────────────────
    # Wszystko, co zrobiło ten film, obok niego (<plik>.recipe.json). Bez przepisu wynik (wyświetlenia, retencja)
    # nie wskazuje przyczyny; z przepisem cykl uczenia może porównywać ustawienia, a nie tylko typ akcji.
    try:
        _eff = TL.effective_edit_values(_zoom_level if use_zoom_punch else 1.0, _zoom_dur, _slowmo_dur)
        _recipe = {
            "recipe_version": 1,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": os.path.basename(source_path),
            "action_type": action_type, "champion": champion_name,
            "clip_seconds_in": round(clip_duration, 3), "final_seconds": round(final_duration, 3),
            "jump_cut_segments": [list(x) for x in combat_segments] if combat_segments else None,
            "peaks_in_clip": [[round(float(tk), 3), lbl] for (tk, lbl) in (_rel_kill_peaks or [])],
            "peak_in_clip": round(rel_peak_moment, 3), "peak_in_output": round(_mapped_peak, 3),
            "director": ({"archetype": director_decision.archetype, "allow_jump_cut": director_decision.allow_jump_cut,
                          "asked_zoom": director_decision.zoom_aggression, "asked_slowmo": director_decision.slowmo_duration}
                         if director_decision else None),
            "applied": {"zoom_level": _eff["zoom_level"], "zoom_window": _eff["zoom_window"], "slowmo_window": _eff["slowmo_window"],
                        "slowmo_speed": _slowmo_speed if use_speed_ramp else 1.0, "smart_camera": bool(use_smart_camera and SMART_CAMERA_AVAILABLE),
                        "music_volume": _music_vol, "game_volume": _game_vol, "game_audio_warped": bool(WARP_GAME_AUDIO and _segments)},
            "time_segments": _segments,
            "music": dict(LAST_MUSIC_SYNC) if music else None,
            "hook_text": _hook, "cta_text": _end_cta,
        }
        with open(os.path.splitext(step5)[0] + ".recipe.json", "w", encoding="utf-8") as _rf:
            json.dump(_recipe, _rf, indent=1, ensure_ascii=False)
    except Exception as _re:
        print(f"   [editor] Przepis shorta nie został zapisany: {_re}")

    # ── SPRZĄTANIE PLIKÓW TYMCZASOWYCH ──────────────────────────────────────────
    temp_intermediates = [step1, step4, step5_music]
    for temp_f in temp_intermediates:
        try:
            if temp_f and os.path.exists(temp_f) and temp_f != step5:
                os.remove(temp_f)
        except Exception as ce:
            print(f"   [editor] Temp cleanup warning ({os.path.basename(temp_f)}): {ce}")
    # ─────────────────────────────────────────────────────────────────────────

    print(f"\n{'='*55}")
    print(f"✅  SHORT GOTOWY: {step5}")
    print(f"   ⏱️  {final_duration:.1f}s | 🎮 {action_type.upper()} | 🎵 {os.path.basename(music) if music else 'brak'} | 🖊️  {_hook}")
    print(f"{'='*55}\n")
    return step5


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else r"C:\Medal\Edits\MedalTVLeagueofLegends20260524184943960-trim-1780471647631.mp4"
    if os.path.exists(src):
        render_short(
            source_path=src,
            clip_start=0.0,
            clip_end=14.2,
            action_type="outplay",
            champion_name="Yone",
            peak_moment=8.0,
            output_filename="test_v3_smart_camera.mp4"
        )
    else:
        print(f"❌ Nie znaleziono: {src}")
