"""
LOL Agent — Editor v3
Styl: czysty gameplay, tekst hook na peak, muzyka dobrana do energii akcji,
      efekt zoom-punch na peak moment + dynamiczne śledzenie kamery.
"""
import os
import re
import time
import random
import subprocess
import sys
import glob
import shutil
import threading
import numpy as np
from typing import Any, Optional

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

# Dropy sprawdzone spektralnie (35-160 Hz sub-bass + RMS).
MUSIC_DROP_VERIFIED = {
    "ncs_alan_walker_fade.mp3",
    "ncs_alex_skrindo_euphoria.mp3",
    "ncs_cartoon_on_and_on.mp3",
    "ncs_different_heaven_my_heart.mp3",
    "ncs_egzod_royalty.mp3",
    "ncs_elektronomia_memory.mp3",
    "ncs_elektronomia_sky_high.mp3",
    "ncs_jim_yosef_link.mp3",
    "ncs_lost_sky_dreams_pt2.mp3",
    "ncs_robin_hustin_light_it_up.mp3",
    "ncs_unknown_brain_superhero.mp3",
}
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

# Dokładne znaczniki wejścia głównego dropu (STFT 35-160 Hz + RMS, beat_drop_cache v2)
MUSIC_DROP_MAP = {
    "ncs_alan_walker_fade.mp3":                75.69,
    "ncs_alex_skrindo_euphoria.mp3":           46.44,
    "ncs_cartoon_on_and_on.mp3":               46.85,
    "ncs_different_heaven_my_heart.mp3":       31.93,
    "ncs_egzod_royalty.mp3":                   72.09,
    "ncs_elektronomia_memory.mp3":             74.80,
    "ncs_elektronomia_sky_high.mp3":           55.44,
    "ncs_jim_yosef_link.mp3":                  60.06,
    "ncs_lost_sky_dreams_pt2.mp3":             65.48,
    "ncs_robin_hustin_light_it_up.mp3":        52.21,
    "ncs_unknown_brain_superhero.mp3":         78.54,
}

INSTRUMENTAL_TRACKS = {
    "ncs_alan_walker_fade.mp3",
    "ncs_alex_skrindo_euphoria.mp3",
    "ncs_elektronomia_memory.mp3",
    "ncs_elektronomia_sky_high.mp3",
    "ncs_jim_yosef_link.mp3",
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


def pick_music_for_action(
    action_type: str = "outplay",
    preferred_track: Optional[str] = None,
    min_drop_time: float = 0.0,
    prefer_instrumental: bool = False,
) -> str:
    """
    Wybiera plik muzyczny dopasowany do energii akcji, minimalnego czasu dropu i opcjonalnie trybu instrumentalnego.
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

    if prefer_instrumental and len(music_files) > 1:
        instr = [f for f in music_files if os.path.basename(f) in INSTRUMENTAL_TRACKS]
        if instr:
            music_files = instr

    # Filtruj utwory z wystarczająco późnym dropem (drop >= min_drop_time => drop_early == 0)
    if min_drop_time > 0.0 and len(music_files) > 1:
        drop_cache = {}
        try:
            cache_p = os.path.join(os.path.dirname(__file__), "beat_drop_cache.json")
            if os.path.exists(cache_p):
                with open(cache_p, encoding="utf-8") as cf:
                    raw_c = json.load(cf)
                if isinstance(raw_c, dict) and isinstance(raw_c.get("drops"), dict):
                    drop_cache = raw_c["drops"]
        except Exception:
            drop_cache = {}
        late_enough = [
            f for f in music_files
            if float(MUSIC_DROP_MAP.get(os.path.basename(f)) or drop_cache.get(os.path.basename(f)) or 999.0) >= float(min_drop_time)
        ]
        if late_enough:
            music_files = late_enough

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
                         timeline_out: Optional[dict] = None,
                         fast_forward_kills: list = None,
                         fast_forward_speed: Optional[float] = None,
                         montage_style: Optional[str] = None,
                         fast_forward_tail: Optional[float] = None,
                         fast_forward_lead: Optional[float] = None) -> float:
    """
    Stosuje kadrowanie (9:16, ARENA_WIDE 1440px, STORY_RAW_POV 960px), zoom-punch i gładki speed-ramp
    w jednym przebiegu za pomocą filter_complex w FFmpeg (z segmentowym minterpolate również na GPU).
    """
    source_w, source_h = 1920, 1080
    style_prof = TL.get_style_profile(montage_style)
    frame_mode = str(style_prof["frame_mode"]) if style_prof else "vertical"
    crop_w = int(style_prof["crop_width"]) if style_prof else TL.vertical_crop_width(source_h)
    no_hud_band = frame_mode in ("arena_wide", "story_hybrid")
    crop_h = 940 if no_hud_band else source_h
    crop_y = 20 if no_hud_band else 0
    max_cx = max(0, source_w - crop_w)

    if not isinstance(crop_x, str):
        cx = max(0, min(int(crop_x), max_cx)) if crop_x >= 0 else max_cx // 2
        crop_x_expr = f"{cx}"
    else:
        crop_x_expr = crop_x
        if crop_w != TL.vertical_crop_width(source_h):
            crop_x_expr = f"clip(({crop_x_expr}),0,{max_cx})"

    zoom_max = float(style_prof["zoom_max"]) if style_prof else TL.ZOOM_MAX
    zoom_win_max = float(style_prof["zoom_window_max"]) if style_prof else TL.ZOOM_WINDOW_MAX
    slowmo_win_max = float(style_prof["slowmo_window_max"]) if style_prof else TL.SLOWMO_WINDOW_MAX
    buildup_spd = float(style_prof.get("buildup_speed", 1.0)) if style_prof else 1.0

    effective_zoom = min(zoom_level, zoom_max)
    crop_w_zoom = int(crop_w / effective_zoom)
    crop_h_zoom = int(crop_h / effective_zoom)
    crop_w_zoom -= crop_w_zoom % 2
    crop_h_zoom -= crop_h_zoom % 2
    crop_x_expr_zoom = f"({crop_x_expr})+{(crop_w - crop_w_zoom) // 2}"
    crop_y_zoom = crop_y + max(0, (crop_h - crop_h_zoom) // 2)

    out_w, out_h = 1080, 1920

    eff = TL.effective_edit_values(
        zoom_level,
        zoom_duration,
        slowmo_duration,
        zoom_max=zoom_max,
        zoom_window_max=zoom_win_max,
        slowmo_window_max=slowmo_win_max,
    )
    if eff["zoom_level"] < zoom_level - 1e-6 or eff["slowmo_window"] < slowmo_duration - 1e-6 or eff["zoom_window"] < zoom_duration - 1e-6:
        print(f"   ℹ️  Limity montażu ({montage_style or 'PRIMARY'}): zoom {zoom_level:.2f}x→{eff['zoom_level']:.2f}x, "
              f"okno zoomu {zoom_duration:.2f}s→{eff['zoom_window']:.2f}s, slow-mo {slowmo_duration:.2f}s→{eff['slowmo_window']:.2f}s")

    normal_crop = f"crop={crop_w}:{crop_h}:'{crop_x_expr}':{crop_y}"
    zoom_crop = f"crop={crop_w_zoom}:{crop_h_zoom}:'{crop_x_expr_zoom}':{crop_y_zoom}"

    time_segments = TL.build_speed_segments(
        clip_duration=clip_duration,
        peak_moment=peak_moment,
        slowmo_speed=slowmo_speed,
        slowmo_duration=slowmo_duration,
        zoom_duration=zoom_duration,
        intermediate_peaks=intermediate_peaks,
        use_easing=use_easing,
        slowmo_window_max=slowmo_win_max,
        zoom_window_max=zoom_win_max,
        buildup_speed=buildup_spd,
    )
    if not time_segments:
        time_segments = [{"start": 0.0, "end": float(clip_duration), "speed": 1.0, "zoom": False}]
    if fast_forward_kills:
        ff_spd = float(fast_forward_speed) if fast_forward_speed is not None else TL.FAST_FORWARD_SPEED
        time_segments = TL.apply_fast_forward(
            time_segments, fast_forward_kills, speed=ff_spd, tail=fast_forward_tail, lead=fast_forward_lead
        )
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
        seg_dur = seg['end'] - seg['start']
        speed_val = float(seg['speed'])
        output_duration += seg_dur / speed_val

        is_slow_seg = speed_val < 0.95
        factor = 1.0 / speed_val
        setpts = f"setpts=(PTS-STARTPTS)*{factor:.4f}" if abs(speed_val - 1.0) > 1e-6 else "setpts=PTS-STARTPTS"
        # Segmentowe minterpolate po setpts usuwa ~40% zduplikowanych klatek w slow-mo również przy h264_nvenc!
        rate_filter = (
            f"{setpts},minterpolate=fps={OUTPUT_FPS}:mi_mode=blend,setpts=PTS-STARTPTS"
            if (is_slow_seg and SMOOTH_SLOWMO)
            else f"{setpts},fps={OUTPUT_FPS},setpts=PTS-STARTPTS"
        )

        if frame_mode == "arena_wide":
            fg_eq = (
                "eq=contrast=1.14:saturation=1.32:brightness=0.04"
                if seg.get("zoom")
                else "eq=contrast=1.08:saturation=1.24:brightness=0.02"
            )
            bg_lbl = f"abg{i}"
            fg_lbl = f"afg{i}"
            # Szeroka arena 1280x940 (bez dolnego HUD/czatu) -> 1080x880 na rozmytym tle 1080x1920 + linie neonowe y=496, y=1380
            filter_lines.append(
                f"[0:v]{trim},split=2[{bg_lbl}_raw][{fg_lbl}_raw];"
                f"[{bg_lbl}_raw]crop=608:1080:(iw-608)/2:0,scale={out_w}:{out_h}:flags=bilinear,"
                f"boxblur=24:2,eq=brightness=-0.26:saturation=0.72,setpts=PTS-STARTPTS[{bg_lbl}];"
                f"[{fg_lbl}_raw]{seg['crop']},scale={out_w}:880:flags=lanczos,{fg_eq},setpts=PTS-STARTPTS[{fg_lbl}];"
                f"[{bg_lbl}][{fg_lbl}]overlay=0:500:shortest=1,setsar=1,"
                f"drawbox=x=0:y=496:w={out_w}:h=4:color=0xC8FF3A@0.95:t=fill,"
                f"drawbox=x=0:y=1380:w={out_w}:h=4:color=0xC8FF3A@0.95:t=fill,"
                f"{rate_filter}[{lbl}]"
            )
        elif frame_mode == "story_hybrid":
            fg_eq = "eq=contrast=1.08:saturation=1.22:brightness=0.02"
            bg_lbl = f"sbg{i}"
            fg_lbl = f"sfg{i}"
            # Hybrydowy szeroki kadr 960x940 (bez HUD/czatu) -> 1080x1150 na ciemnym nastrojowym blurze (zero pustej czarnej ramki)
            filter_lines.append(
                f"[0:v]{trim},split=2[{bg_lbl}_raw][{fg_lbl}_raw];"
                f"[{bg_lbl}_raw]crop=608:1080:(iw-608)/2:0,scale={out_w}:{out_h}:flags=bilinear,"
                f"boxblur=28:2,eq=brightness=-0.36:saturation=0.52,setpts=PTS-STARTPTS[{bg_lbl}];"
                f"[{fg_lbl}_raw]{seg['crop']},scale={out_w}:1150:flags=lanczos,{fg_eq},setpts=PTS-STARTPTS[{fg_lbl}];"
                f"[{bg_lbl}][{fg_lbl}]overlay=0:385:shortest=1,setsar=1,"
                f"drawbox=x=0:y=382:w={out_w}:h=3:color=0x2A2E37:t=fill,"
                f"drawbox=x=0:y=1535:w={out_w}:h=3:color=0x2A2E37:t=fill,"
                f"{rate_filter}[{lbl}]"
            )
        elif frame_mode == "vertical_velocity":
            eq_filter = (
                "eq=contrast=1.26:saturation=1.52:brightness=0.05,vignette=angle=PI/6"
                if seg.get("zoom")
                else "eq=contrast=1.18:saturation=1.42:brightness=0.015,vignette=angle=PI/8"
            )
            filter_lines.append(
                f"[0:v]{trim},{seg['crop']},scale={out_w}:{out_h}:flags=lanczos,setsar=1,"
                f"{eq_filter},{rate_filter}[{lbl}]"
            )
        else:
            eq_filter = (
                "eq=contrast=1.18:saturation=1.45:brightness=0.065,vignette=angle=PI/7"
                if seg.get("zoom")
                else "eq=contrast=1.08:saturation=1.35:brightness=0.03"
            )
            crop_scale = f"{seg['crop']},scale={out_w}:{out_h}:flags=lanczos,setsar=1,{eq_filter}"
            filter_lines.append(f"[0:v]{trim},{crop_scale},{rate_filter}[{lbl}]")

        labels.append(f"[{lbl}]")

    concat_str = "".join(labels) + f"concat=n={len(segs)}:v=1:a=0[v_final]"
    filter_lines.append(concat_str)

    filter_complex = ";".join(filter_lines)

    fc_script = output_path.replace(".mp4", "_filter.txt")
    with open(fc_script, "w", encoding="utf-8") as f:
        f.write(filter_complex)

    print(f"🎬 Processing filtergraph [{montage_style or 'PRIMARY'}] with dynamic tracking...")

    encoder_high = get_optimal_encoder_args("high")

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex_script", fc_script,
        "-map", "[v_final]",
        *encoder_high,
        output_path
    ]

    enc_name, _ = detect_hardware()
    try:
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


def _layout_overlay_text(
    text: str,
    max_width_px: int = 880,
    max_size: int = 84,
    min_size: int = 44,
    max_lines: int = 2,
) -> tuple[list[str], int]:
    """Dobiera czytelny rozmiar czcionki i (w razie potrzeby) dzieli długi napis na max 2 wyważone linie."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return [], max_size

    char_ratio = 0.58
    if int(len(clean) * max_size * char_ratio) <= max_width_px:
        return [clean], int(max_size)

    single_fit = int(max_width_px / max(1.0, len(clean) * char_ratio))
    if max_lines <= 1 or (len(clean) <= 18 and single_fit >= min_size + 14):
        return [clean], max(min_size, min(max_size, single_fit))

    lines: list[str]
    if " - " in clean:
        left, right = clean.split(" - ", 1)
        lines = [left.strip(), right.strip()]
    elif " " in clean:
        mid = len(clean) // 2
        spaces = [i for i, ch in enumerate(clean) if ch == " "]
        best_sp = min(spaces, key=lambda idx: abs(idx - mid))
        lines = [clean[:best_sp].strip(), clean[best_sp + 1 :].strip()]
    else:
        lines = [clean]

    lines = [ln for ln in lines if ln] or [clean]
    longest = max(len(ln) for ln in lines)
    fitted = int(max_width_px / max(1.0, longest * char_ratio))
    return lines, max(min_size, min(max_size, fitted))


def _alpha_fade_expr(t_start: float, t_end: float, fade_s: float = 0.14, fade_in: bool = True) -> str:
    """Zwraca wyrażenie FFmpeg `alpha` z płynnym wejściem/wyjściem (dla t=0s fade_in=False zachowuje pełną czytelność od 1. klatki)."""
    dur = float(t_end) - float(t_start)
    if dur <= fade_s * 2.2:
        return "1"
    fade_out_t = max(float(t_start), float(t_end) - fade_s)
    if not fade_in:
        return f"if(gt(t\\,{fade_out_t:.2f})\\,max(0\\,({t_end:.2f}-t)/{fade_s:.2f})\\,1)"
    return (
        f"if(lt(t-{t_start:.2f}\\,{fade_s:.2f})\\,"
        f"(t-{t_start:.2f})/{fade_s:.2f}\\,"
        f"if(gt(t\\,{fade_out_t:.2f})\\,"
        f"max(0\\,({t_end:.2f}-t)/{fade_s:.2f})\\,1))"
    )


def build_text_overlay_filters(
    hook_text: str,
    peak_moment: float,
    video_duration: float,
    show_duration: float = 2.0,
    style_mode: str = "PRIMARY",
) -> list[str]:
    """
    Buduje filtry FFmpeg drawbox i drawtext dla responsywnego tekstu hooka (max 2 linie w bezpiecznej strefie).
    Obsługuje 3 style: ARENA_WIDE (górny blur + linia #C8FF3A), BEAT_VELOCITY (czysta typografia bez boxa),
    STORY_RAW_POV (biały banner z czarnym pogrubionym tekstem) oraz legacy PRIMARY (bez pustego czarnego boxa po fade-out).
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

    s_mode = (style_mode or "PRIMARY").upper().strip()
    max_w_txt = 900 if s_mode == "STORY_RAW_POV" else 860
    max_sz = 80 if s_mode == "BEAT_VELOCITY" else (68 if s_mode == "STORY_RAW_POV" else 74)
    lines, fsize = _layout_overlay_text(
        clean_text, max_width_px=max_w_txt, max_size=max_sz, min_size=42, max_lines=2
    )
    if not lines:
        return []

    t_start = 0.0
    fade_s = 0.14
    t_end = min(video_duration, max(1.2, show_duration))
    alpha_expr = _alpha_fade_expr(t_start, t_end, fade_s=fade_s, fade_in=False)
    box_end = round(max(t_start + 0.20, t_end - fade_s - 0.02), 2) if (t_end - t_start) > 0.35 else round(t_end, 2)

    hook_color = "0xFFD700" if any(w in clean_text.upper() for w in ("SOLO", "PENTA", "CLUTCH", "1V1", "1%", "DRAGON", "STEAL")) else "white"
    line_h = int(fsize * 1.18)
    pad_y = 20 if s_mode != "STORY_RAW_POV" else 22
    box_h = len(lines) * line_h + pad_y * 2
    max_chars = max(len(ln) for ln in lines)
    box_w = min(980, max(460, int(max_chars * fsize * 0.60) + 96))
    font_safe = font.replace(chr(92), '/').replace(':', '\\:')

    filters: list[str] = []
    if s_mode == "STORY_RAW_POV":
        box_y_px = 112
        banner_w = 972
        banner_h = box_h + 12
        filters.append(
            f"drawbox=x=54:y={box_y_px}:w={banner_w}:h={banner_h}:color=0xF5F6F8@0.97:t=fill"
            f":enable='between(t,{t_start:.2f},{box_end:.2f})'"
        )
        filters.append(
            f"drawbox=x=54:y={box_y_px + banner_h - 4}:w={banner_w}:h=4:color=0xC8FF3A@0.95:t=fill"
            f":enable='between(t,{t_start:.2f},{box_end:.2f})'"
        )
        for i, line_txt in enumerate(lines):
            y_px = box_y_px + pad_y + 4 + i * line_h
            filters.append(
                f"drawtext="
                f"fontfile='{font_safe}'"
                f":text='{line_txt}'"
                f":x=(w-text_w)/2"
                f":y={y_px}"
                f":fontsize={fsize}"
                f":fontcolor=0x0D0F12"
                f":borderw=0"
                f":alpha='{alpha_expr}'"
                f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
        return filters

    if s_mode == "BEAT_VELOCITY":
        box_y_px = 165
        for i, line_txt in enumerate(lines):
            y_px = box_y_px + i * line_h
            filters.append(
                f"drawtext="
                f"fontfile='{font_safe}'"
                f":text='{line_txt}'"
                f":x=(w-text_w)/2"
                f":y={y_px}"
                f":fontsize={fsize}"
                f":fontcolor=0xFFD700"
                f":borderw=7"
                f":bordercolor=black"
                f":shadowx=5:shadowy=5:shadowcolor=black@0.92"
                f":alpha='{alpha_expr}'"
                f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
        return filters

    box_y_px = 155 if s_mode == "ARENA_WIDE" else 150
    box_color = "0x0B0E14@0.82" if s_mode == "ARENA_WIDE" else "black@0.52"
    filters.append(
        f"drawbox="
        f"x=trunc((iw-{box_w})/2)"
        f":y={box_y_px}"
        f":w={box_w}"
        f":h={box_h}"
        f":color={box_color}"
        f":t=fill"
        f":enable='between(t,{t_start:.2f},{box_end:.2f})'"
    )
    if s_mode == "ARENA_WIDE":
        filters.append(
            f"drawbox="
            f"x=trunc((iw-{box_w})/2)"
            f":y={box_y_px + box_h - 4}"
            f":w={box_w}"
            f":h=4"
            f":color=0xC8FF3A@0.95"
            f":t=fill"
            f":enable='between(t,{t_start:.2f},{box_end:.2f})'"
        )
    for i, line_txt in enumerate(lines):
        y_px = box_y_px + pad_y + i * line_h
        filters.append(
            f"drawtext="
            f"fontfile='{font_safe}'"
            f":text='{line_txt}'"
            f":x=(w-text_w)/2"
            f":y={y_px}"
            f":fontsize={fsize}"
            f":fontcolor={hook_color}"
            f":borderw=5"
            f":bordercolor=black"
            f":shadowx=3:shadowy=3:shadowcolor=black@0.85"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
        )
    return filters


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
    style_mode: str = "PRIMARY",
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
    s_mode = (style_mode or "PRIMARY").upper().strip()
    is_viral_style = s_mode in ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV")
    cap_t_offset = -0.12 if is_viral_style else 0.15
    cap_dur_cap = 1.15 if is_viral_style else 1.35

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
                t_start = max(0.0, t_in_clip + cap_t_offset)
                t_end = min(video_duration, t_start + min(float(style["duration"]), 1.45 if is_viral_style else float(style["duration"])))
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
            t_start = max(0.0, t_in_clip + cap_t_offset)
            dur_cap = min(float(style["duration"]), cap_dur_cap)
            t_end = min(video_duration, t_start + dur_cap)
            cta_cut = max(0.0, video_duration - 1.55)
            if t_start < (cta_cut - 0.55):
                t_end = min(t_end, cta_cut)

            clean_label = re.sub(r"[^\x00-\x7F]+", "", clean_lbl).strip()
            clean_label = clean_label.replace("'", "\\'")
            caption_items.append({
                "start": t_start,
                "end": t_end,
                "label": clean_label,
                "style": style,
                "t_in_clip": t_in_clip,
                "t_raw": t_raw,
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
    TIER_NUM = {
        "KILL": 1, "OUTPLAY": 1, "ONESHOT": 1, "SHUTDOWN": 1,
        "CLUTCH": 1, "1% HP CLUTCH": 1, "SOLO BOLO": 1,
        "DOUBLE KILL": 2, "TRIPLE KILL": 3, "QUADRAKILL": 4, "PENTAKILL": 5,
    }
    ACT_MIN_KILLS = {"double": 2, "triple": 3, "quadra": 4, "quadrakill": 4, "penta": 5, "pentakill": 5}
    NUM_TO_LABEL = {1: "KILL", 2: "DOUBLE KILL", 3: "TRIPLE KILL", 4: "QUADRAKILL", 5: "PENTAKILL"}
    max_item_num = max((TIER_NUM.get(item["label"].upper(), 1) for item in caption_items), default=total_kills)
    expected_total = max(total_kills, max_item_num, ACT_MIN_KILLS.get(act_lower, 1))
    prev_emitted_tier = 0

    hud_y_expr = (
        "h*0.195" if s_mode == "ARENA_WIDE"
        else ("h*0.822" if s_mode == "STORY_RAW_POV" else ("h*0.168" if s_mode == "BEAT_VELOCITY" else "h*0.175"))
    )
    banner_y_expr = (
        "h*0.222" if s_mode == "ARENA_WIDE"
        else ("h*0.848" if s_mode == "STORY_RAW_POV" else ("h*0.208" if s_mode == "BEAT_VELOCITY" else "h*0.235"))
    )
    pill_y_expr = (
        "h*0.728" if s_mode == "ARENA_WIDE"
        else ("h*0.896" if s_mode == "STORY_RAW_POV" else ("h*0.285" if s_mode == "BEAT_VELOCITY" else "h*0.305"))
    )
    bar_color = (
        "0xC8FF3A@0.92" if s_mode == "ARENA_WIDE"
        else ("0xFFFFFF@0.85" if s_mode == "STORY_RAW_POV" else ("0x00F2FE@0.92" if s_mode == "BEAT_VELOCITY" else "0xC89B3C@0.90"))
    )

    for idx, item in enumerate(caption_items):
        t_start = item["start"]
        t_end   = item["end"]
        clean_label = item["label"]
        style = item["style"]

        is_multikill = bool(action_type and action_type.lower() in ("double", "triple", "quadrakill", "quadra", "pentakill", "penta"))
        alpha_expr = _alpha_fade_expr(t_start, t_end, fade_s=0.12)
        if is_multikill and total_kills >= 2 and not is_solo:
            is_final_kill = (idx == total_kills - 1)
            item_num = TIER_NUM.get(clean_label.upper(), idx + 1)
            kill_num = expected_total if is_final_kill else min(expected_total, max(idx + 1, item_num))
            # Wymuszenie monotonicznosci: na 3/4 po DOUBLE KILL musi być TRIPLE KILL, a nie powtórzone DOUBLE KILL
            if item_num <= prev_emitted_tier or (kill_num >= 2 and item_num < kill_num):
                clean_label = NUM_TO_LABEL.get(kill_num, clean_label)
                style = KILL_STYLES.get(clean_label, style)
            prev_emitted_tier = max(prev_emitted_tier, TIER_NUM.get(clean_label.upper(), kill_num))
            hud_text = f"KILL {kill_num}/{expected_total}" if not is_final_kill else f"FINAL KILL {kill_num}/{expected_total}"
            hud_color = (
                "0xC8FF3A" if (s_mode == "ARENA_WIDE" and is_final_kill)
                else ("0xFFD700" if is_final_kill else ("0xFFA500" if idx > 0 else "white"))
            )

            hud_dt = (
                f"drawtext="
                f"fontfile='{font_safe}'"
                f":text='{hud_text}'"
                f":x=(w-text_w)/2"
                f":y={hud_y_expr}"
                f":fontsize=28"
                f":fontcolor={hud_color}"
                f":box=1:boxcolor=0x0B0E14@0.56:boxborderw=9"
                f":borderw=3"
                f":bordercolor=black"
                f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
                f":alpha='{alpha_expr}'"
                f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
            )
            drawtext_filters.append(hud_dt)

        max_banner_sz = 62 if s_mode == "BEAT_VELOCITY" else (66 if is_viral_style else 76)
        _, k_fsize = _layout_overlay_text(
            clean_label, max_width_px=840, max_size=min(style["size"], max_banner_sz), min_size=44, max_lines=1
        )
        b_color = (
            "0xFFD700" if (s_mode == "BEAT_VELOCITY" and idx == total_kills - 1)
            else ("0x00F2FE" if s_mode == "BEAT_VELOCITY" else style["color"])
        )
        b_box_col = "0x0B0E14@0.56" if s_mode == "BEAT_VELOCITY" else "black@0.44"
        b_box_pad = 10 if s_mode == "BEAT_VELOCITY" else 14
        b_border = 4 if s_mode == "BEAT_VELOCITY" else 5
        dt = (
            f"drawtext="
            f"fontfile='{font_safe}'"
            f":text='{clean_label}'"
            f":x=(w-text_w)/2"
            f":y={banner_y_expr}"
            f":fontsize={k_fsize}"
            f":fontcolor={b_color}"
            f":box=1:boxcolor={b_box_col}:boxborderw={b_box_pad}"
            f":borderw={b_border}"
            f":bordercolor=black"
            f":shadowx=4:shadowy=4:shadowcolor=black@0.8"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
        )
        drawtext_filters.append(dt)
        print(f"   🗨️  {clean_label} (kill {idx+1}/{total_kills}) @ {item.get('t_in_clip', t_start):.1f}s (start {t_start:.1f}s) — {k_fsize}px [{s_mode}]")

    # Pigułka telemetrii na finałowym killu (tylko szybkie multikille 0.4..5.5s lub clutch 1% HP)
    if caption_items:
        fin_item = caption_items[-1]
        pill_txt = ""
        if "clutch" in act_lower:
            pill_txt = "1% HP SURVIVAL"
        elif not is_solo and len(caption_items) >= 2:
            raw_pts = [float(it["t_raw"]) for it in caption_items if isinstance(it.get("t_raw"), (int, float))]
            span_s = round(max(raw_pts) - min(raw_pts), 1) if len(raw_pts) >= 2 else round(float(fin_item["t_in_clip"] - caption_items[0]["t_in_clip"]), 1)
            if 0.4 <= span_s <= 5.5:
                pill_txt = f"{expected_total} KILLS IN {span_s:.1f}S"
        if pill_txt:
            p_alpha = _alpha_fade_expr(fin_item["start"], fin_item["end"], fade_s=0.12)
            p_safe = pill_txt.replace("'", "").replace("%", "%%")
            drawtext_filters.append(
                f"drawtext="
                f"fontfile='{font_safe}'"
                f":text='{p_safe}'"
                f":x=(w-text_w)/2"
                f":y={pill_y_expr}"
                f":fontsize=26"
                f":fontcolor=0xFFD700"
                f":box=1:boxcolor=black@0.58:boxborderw=8"
                f":borderw=2"
                f":bordercolor=black"
                f":alpha='{p_alpha}'"
                f":enable='between(t,{fin_item['start']:.2f},{fin_item['end']:.2f})'"
            )

    # BEAT_VELOCITY: biały Impact Flash dokładnie na kulminacji killa
    if s_mode == "BEAT_VELOCITY" and video_duration > 0.6:
        raw_peak_val = float(peak_moment or 0.0)
        if trim_start > 0.0 and raw_peak_val >= trim_start:
            raw_peak_val = raw_peak_val - trim_start
        flash_t = _adjust_t(raw_peak_val) if time_segments else raw_peak_val
        if 0.15 <= flash_t <= video_duration - 0.10:
            drawtext_filters.append(
                f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.42:t=fill"
                f":enable='between(t,{max(0.0, flash_t - 0.02):.3f},{min(video_duration, flash_t + 0.07):.3f})'"
            )

    progress_bar = (
        f"drawbox="
        f"x=0"
        f":y=ih-5"
        f":w='trunc(iw*min(1.0,t/{max(0.1, video_duration):.2f}))'"
        f":h=5"
        f":color={bar_color}"
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

    # Zmierz dokładny czas trwania strumienia wideo, żeby audio nigdy nie wystawało o +64ms (czarna końcówka)
    target_dur = float(video_duration)
    try:
        v_probe = _run_ffmpeg([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ], timeout=10.0, desc="ffprobe video duration check")
        v_str = v_probe.stdout.decode("utf-8", errors="replace").strip()
        if v_str:
            parsed_v = float(v_str.splitlines()[0].strip())
            if parsed_v > 0.5:
                target_dur = min(target_dur, parsed_v)
    except Exception:
        pass

    # Seamless Loop: mikro-fade 40ms wyłącznie na styku zapętlenia (brak wyciszania 1.5s przed końcem)
    fade_dur = 0.04
    fade_start = max(0.0, target_dur - fade_dur)

    if has_game_audio and GAME_AUDIO_VOLUME > 0.0:
        # ── Miksuj dźwięk gry + muzykę przez amix ──────────────────────────────────
        game_vol  = game_volume if game_volume is not None else GAME_AUDIO_VOLUME
        music_vol = music_volume if music_volume is not None else MUSIC_VOLUME

        # Generuj płynny boost audio gry przy killach (rampa 0.15s zamiast twardego skoku i bez przesteru po loudnorm)
        def _game_boost_expr(base, peaks):
            capped_base = min(0.90, float(base))
            if not peaks:
                return f"{capped_base:.2f}"
            parts = []
            for t, label in (peaks or []):
                dur = 1.6 if "PENTA" in label else (1.4 if "QUADRA" in label else 1.1)
                extra = 0.45 if "PENTA" in label else 0.35
                t0 = max(0.0, float(t))
                t1 = t0 + dur
                ramp = f"min(1,max(0,(t-{t0:.2f})/0.15))*min(1,max(0,({t1:.2f}-t)/0.15))"
                parts.append(f"{ramp}*{extra:.2f}")
            if not parts:
                return f"{capped_base:.2f}"
            return f"min(1.30,{capped_base:.2f}*(1+{'+'.join(parts)}))"

        # Dynamiczna krzywa głośności muzyki: duck przed kulminacją (vacuum 0.38s), wyraźne uderzenie dropu (+0.32)
        # oraz impuls na ewentualnych kolejnych killach po wejściu bitu (drop_anchor=first_kill_engage)
        def _music_duck_expr(base, peaks, climax_peak_t=0.0):
            climax_t = float(climax_peak_t or 0.0)
            terms = []
            for t, _label in (peaks or []):
                tf = float(t)
                if climax_t > 0.5 and abs(tf - climax_t) <= 0.8:
                    continue
                if climax_t > 0.5 and tf > climax_t + 0.8:
                    terms.append(f"+between(t,{tf:.2f},{tf+1.10:.2f})*0.16")
                else:
                    terms.append(f"-between(t,{tf:.2f},{tf+1.0:.2f})*0.25")
            if climax_t > 0.5:
                pre_s = max(0.0, climax_t - 0.38)
                pre_e = max(0.0, climax_t - 0.03)
                if pre_e > pre_s + 0.05:
                    terms.append(f"-between(t,{pre_s:.2f},{pre_e:.2f})*0.42")
                terms.append(f"+between(t,{climax_t:.2f},{climax_t+1.8:.2f})*0.32")
            elif peaks:
                tf = float(peaks[-1][0])
                terms.append(f"+between(t,{tf:.2f},{tf+1.8:.2f})*0.32")
            if not terms:
                return f"{base:.2f}"
            return f"max(0.10,min(1.65,{base:.2f}*(1{''.join(terms)})))"

        game_boost = _game_boost_expr(game_vol, kill_peaks)
        music_duck  = _music_duck_expr(music_vol, kill_peaks, climax_peak_t=video_peak_time)

        # Dźwięk gry na tej samej osi czasu co obraz + highpass=130 Hz (zwalnia sub-bas 35-130 Hz wyłącznie dla dropu muzyki!)
        warp_on = bool(WARP_GAME_AUDIO and time_segments and any(abs(sg["speed"] - 1.0) > 1e-6 for sg in time_segments))
        game_in = "[gwarp]" if warp_on else "[2:a]"
        warp_prefix = (TL.audio_warp_filter(time_segments, "2:a", "gwarp", mode="clean") + ";") if warp_on else ""
        filter_complex = (
            f"{warp_prefix}{game_in}loudnorm=I=-16:TP=-2.0:LRA=11,highpass=f=130,"
            f"volume=eval=frame:volume='{game_boost}',"
            f"alimiter=limit=0.68:level=disabled:attack=3:release=50,"
            f"afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}[ga];"
            f"[1:a]volume=0.82,volume=eval=frame:volume='{music_duck}',"
            f"afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}[ma];"
            f"[ga][ma]amix=inputs=2:duration=longest:dropout_transition=2:normalize=0,"
            f"alimiter=limit=0.62:level=disabled:attack=3:release=50,"
            f"atrim=0:{target_dur:.3f},asetpts=PTS-STARTPTS[aout]"
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
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-t", f"{target_dur:.3f}",
            "-shortest",
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
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-af", f"volume={MUSIC_VOLUME},loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f},atrim=0:{target_dur:.3f},asetpts=PTS-STARTPTS",
            "-t", f"{target_dur:.3f}",
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
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
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


OUTRO_CTA_VARIANTS = [
    {"id": "debate_greedy",    "kind": "debate", "text": "CLEAN OR GREEDY? COMMENT"},
    {"id": "debate_choke",     "kind": "debate", "text": "WHO CHOKED HERE? COMMENT"},
    {"id": "debate_elo",       "kind": "debate", "text": "GUESS THE ELO IN COMMENTS"},
    {"id": "debate_panicked",  "kind": "debate", "text": "CALCULATED OR PURE PANIC?"},
    {"id": "debate_turn",      "kind": "debate", "text": "WOULD YOU TURN BACK IN?"},
    {"id": "debate_mistake",   "kind": "debate", "text": "SPOT THE MISTAKE BELOW"},
    {"id": "debate_threw",     "kind": "debate", "text": "WHO THREW THIS FIGHT?"},
    {"id": "debate_survive",   "kind": "debate", "text": "COULD YOU SURVIVE THAT?"},
    {"id": "debate_dodge",     "kind": "debate", "text": "WAS THAT DODGEABLE? COMMENT"},
    {"id": "debate_lucky",     "kind": "debate", "text": "CLEAN RESET OR LUCKY?"},
    {"id": "debate_track",     "kind": "debate", "text": "TOO FAST TO TRACK? COMMENT"},
    {"id": "debate_shunpo",    "kind": "debate", "text": "WAIT FOR THAT SHUNPO RESET"},
]


def _default_caption_history_path() -> Optional[str]:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "accounts", "caption_history.json")


def select_non_repeating_outro_cta(
    history_path: Optional[str] = None,
    action_type: str = "",
    champion_name: str = "",
) -> dict:
    """
    Wybiera 1 z 12 mikro-triggerów CTA na ostatnie 1.5s klipu z bezwzględną
    blokadą powtórek przez co najmniej 6 kolejnych filmów (accounts/caption_history.json).
    Wyklucza warianty specyficzne dla Katariny, jeśli bohater klipu jest inny.
    """
    h_path = history_path if history_path is not None else _default_caption_history_path()
    recent_ids: List[str] = []
    if h_path and os.path.isfile(h_path):
        try:
            with open(h_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                recent_ids = [str(x) for x in loaded[-6:]]
        except Exception:
            recent_ids = []

    excluded = set(recent_ids[-6:])
    champ_low = (champion_name or "").strip().lower()
    champ_banned = {"debate_shunpo", "debate_lucky"} if (champ_low and champ_low != "katarina") else set()
    pool = [v for v in OUTRO_CTA_VARIANTS if v["id"] not in excluded and v["id"] not in champ_banned]
    if not pool:
        pool = [v for v in OUTRO_CTA_VARIANTS if v["id"] not in champ_banned] or list(OUTRO_CTA_VARIANTS)

    # W testach bez podanej ścieżki lub przy produkcji losuj bezpiecznie z dostępnej puli
    import random as _rnd
    chosen = dict(_rnd.choice(pool))

    if h_path:
        try:
            new_hist = (recent_ids + [chosen["id"]])[-12:]
            os.makedirs(os.path.dirname(h_path), exist_ok=True)
            with open(h_path, "w", encoding="utf-8") as f:
                json.dump(new_hist, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return chosen


def get_engagement_cta(action_type: str = "", champion: str = "", hook_text: str = "") -> str:
    """
    Zwraca rotowane wezwanie końcowe (bez zmyślonych spelli i powtórek co 2 filmy)
    korzystając z bufora 12 wariantów outro.
    """
    return select_non_repeating_outro_cta(action_type=action_type)["text"]


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
    style_mode: str = "PRIMARY",
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
    clean_cta = clean_cta.replace("'", "")
    clean_cta = clean_cta.replace(":", "\\:")
    clean_cta = clean_cta.replace("%", "%%")

    if not clean_cta:
        return []

    s_mode = (style_mode or "PRIMARY").upper().strip()
    t_start = max(0.0, video_duration - show_duration)
    t_end   = video_duration
    fade_s = 0.14
    alpha_expr = _alpha_fade_expr(t_start, t_end, fade_s=fade_s)
    box_end = round(max(t_start + 0.15, t_end - fade_s - 0.02), 2) if (t_end - t_start) > 0.35 else round(t_end, 2)

    cta_lines, fsize = _layout_overlay_text(
        clean_cta, max_width_px=860, max_size=40 if s_mode in ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV") else 50, min_size=32, max_lines=2
    )
    if not cta_lines:
        return []

    line_h = int(fsize * 1.20)
    pad_y = 12 if s_mode in ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV") else 18
    box_h = len(cta_lines) * line_h + pad_y * 2
    max_chars = max(len(ln) for ln in cta_lines)
    box_w = min(940, max(400, int(max_chars * fsize * 0.60) + 56))
    if s_mode == "ARENA_WIDE":
        box_y_px = 1430
        box_col = "0x0B0E14@0.72"
        txt_col = "0xC8FF3A"
    elif s_mode == "STORY_RAW_POV":
        # Umieszczamy CTA w górnym pasie po wygaśnięciu białego banneru hooka (3.2s),
        # z >1300 px zapasu nad napisem FINAL KILL na h*0.822..0.896 i poza opisem Shorts.
        box_y_px = 200
        box_col = "0x0B0E14@0.72"
        txt_col = "white"
    elif s_mode == "BEAT_VELOCITY":
        box_y_px = 1380
        box_col = "0x0B0E14@0.68"
        txt_col = "0xFFD700"
    else:
        box_y_px = 1380  # bezpieczna strefa nad opisem YT Shorts/Reels z dala od górnych napisów
        box_col = "black@0.48"
        txt_col = "0xFFD700"

    cta_box = (
        f"drawbox="
        f"x=trunc((iw-{box_w})/2)"
        f":y={box_y_px}"
        f":w={box_w}"
        f":h={box_h}"
        f":color={box_col}"
        f":t=fill"
        f":enable='between(t,{t_start:.2f},{box_end:.2f})'"
    )
    filters = [cta_box]
    cta_border = 3 if s_mode in ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV") else 4
    for i, line_txt in enumerate(cta_lines):
        y_px = box_y_px + pad_y + i * line_h
        filters.append(
            f"drawtext="
            f"fontfile='{font_safe}'"
            f":text='{line_txt}'"
            f":x=(w-text_w)/2"
            f":y={y_px}"
            f":fontsize={fsize}"
            f":fontcolor={txt_col}"
            f":borderw={cta_border}"
            f":bordercolor=black"
            f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
            f":alpha='{alpha_expr}'"
            f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
        )
    return filters


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
    style_mode: str = "PRIMARY",
) -> str:
    """
    Łączy dynamiczne napisy kill-by-kill, hook overlay oraz CTA overlay
    w jeden zunifikowany filtergraph FFmpeg (Task B2).
    Eliminuje 2 zbędne fazy re-enkodowania i 2 pliki tymczasowe na dysku.
    """
    filters = []
    s_mode = (style_mode or "PRIMARY").upper().strip()

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
            style_mode=s_mode,
        )
        filters.extend(cap_filters)

    # 2. Hook overlay (0.0s - 2.0s; w STORY_RAW_POV górny biały banner może trwać 3.2s bo jest nad ramką gry)
    if hook_text and hook_text.strip():
        hook_show = 3.2 if s_mode == "STORY_RAW_POV" else 2.0
        if peaks and s_mode != "STORY_RAW_POV":
            early_raw = min(
                (float(p[0]) if (float(p[0]) < trim_start or trim_start == 0.0) else (float(p[0]) - trim_start))
                for p in peaks
            )
            if time_segments:
                early_raw = TL.warp_time(time_segments, early_raw)
            if 0.0 <= (early_raw + 0.15) < 2.15:
                hook_show = min(2.0, max(1.1, (early_raw + 0.15) - 0.15))
        hook_filters = build_text_overlay_filters(
            hook_text=hook_text.strip(),
            peak_moment=0.0,
            video_duration=video_duration,
            show_duration=hook_show,
            style_mode=s_mode,
        )
        filters.extend(hook_filters)

    # 3. CTA overlay (ostatnie cta_duration s)
    if cta_text and cta_text.strip():
        cta_filters = build_cta_overlay_filters(
            video_duration=video_duration,
            cta_text=cta_text.strip(),
            show_duration=cta_duration,
            style_mode=s_mode,
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
        "-fps_mode", "cfr", "-r", "60",
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
            "-fps_mode", "cfr", "-r", "60",
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


def _detect_death_or_tab_end(
    video_path: str,
    clip_start: float,
    clip_end: float,
    last_peak_abs: float,
) -> tuple[Optional[float], str]:
    """Wykrywa szary ekran śmierci (`BACK IN`) lub tabelę `TAB` w ogonie po ostatnim killu."""
    if not video_path or not os.path.isfile(video_path):
        return None, ""
    tail_start = max(float(clip_start) + 0.8, float(last_peak_abs) + 0.45)
    if float(clip_end) - tail_start < 0.35:
        return None, ""
    try:
        import cv2
    except Exception:
        return None, ""

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None, ""
    try:
        def _center_stats(t_s: float) -> Optional[tuple]:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(t_s)) * 1000.0)
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                return None
            h, w = frame.shape[:2]
            roi = frame[int(h * 0.18):int(h * 0.82), int(w * 0.15):int(w * 0.85)]
            if roi.size == 0:
                return None
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(frame[int(h * 0.22):int(h * 0.78), int(w * 0.22):int(w * 0.78)], cv2.COLOR_BGR2GRAY)
            mean_s = float(np.mean(hsv[:, :, 1]))
            mean_v = float(np.mean(hsv[:, :, 2]))
            sobel_y = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
            h_edge_ratio = float(np.mean(sobel_y > 18.0))
            return mean_v, mean_s, h_edge_ratio

        ref_t = max(float(clip_start) + 0.2, min(float(last_peak_abs) - 0.35, float(clip_end) - 1.0))
        ref_stats = _center_stats(ref_t)
        ref_v = ref_stats[0] if ref_stats else 108.0
        ref_s = ref_stats[1] if ref_stats else 85.0

        t_cur = tail_start
        grey_streak = 0
        first_grey_t: Optional[float] = None
        while t_cur <= float(clip_end) - 0.05:
            st = _center_stats(t_cur)
            if st is not None:
                mean_v, mean_s, h_edge_ratio = st
                is_grey_death = (mean_s < 35.0 and (ref_s - mean_s >= 22.0 or mean_s < 18.0))
                if is_grey_death:
                    if grey_streak == 0:
                        first_grey_t = t_cur
                    grey_streak += 1
                    if grey_streak >= 2 and first_grey_t is not None:
                        return round(float(first_grey_t), 2), "death_screen"
                else:
                    grey_streak = 0
                    first_grey_t = None

                is_tab = (
                    mean_v < 82.0
                    and h_edge_ratio > 0.085
                    and (
                        ref_v - mean_v >= 22.0
                        or (mean_s < 62.0 and (ref_v - mean_v >= 12.0 or mean_v < 65.0))
                    )
                )
                if is_tab:
                    return round(float(t_cur), 2), "tab_scoreboard"
            t_cur += 0.20
    except Exception:
        return None, ""
    finally:
        cap.release()
    return None, ""


def _detect_tab_scoreboard_start(
    video_path: str,
    clip_start: float,
    clip_end: float,
    last_peak_abs: float,
) -> Optional[float]:
    """Wrapper wstecznie kompatybilny — zwraca timestamp śmierci/TAB w ogonie klipu."""
    t_det, _ = _detect_death_or_tab_end(video_path, clip_start, clip_end, last_peak_abs)
    return t_det


def _canonicalize_to_source_time(
    peaks_in: Optional[list],
    peak_m: float,
    clip_s: float,
    clip_d: float,
) -> tuple[list, float]:
    """Sprowada peaks i peak_moment jednolicie do osi czasu źródła (zapobiega odwróceniu kolejności gdy clip_start < clip_duration)."""
    p_list = list(peaks_in or [])
    if clip_s <= 0.0:
        return [(float(t), lbl) for (t, lbl) in p_list], float(peak_m or 0.0)

    if p_list:
        ts = [float(t) for (t, _) in p_list]
        if any(t > clip_d + 0.35 for t in ts):
            peaks_is_abs = True
        elif any(t < clip_s - 0.15 for t in ts):
            peaks_is_abs = False
        else:
            peaks_is_abs = bool(float(peak_m or 0.0) > clip_d + 0.35)
        abs_peaks = sorted(
            [(round(t if peaks_is_abs else (clip_s + t), 3), lbl) for (t, lbl) in p_list],
            key=lambda x: x[0],
        )
    else:
        abs_peaks = []

    pm = float(peak_m or 0.0)
    if pm > clip_d + 0.35:
        abs_pm = pm
    elif abs_peaks:
        d_if_rel = min(abs((clip_s + pm) - ak) for ak, _ in abs_peaks)
        d_if_abs = min(abs(pm - ak) for ak, _ in abs_peaks) if pm >= clip_s else 1e9
        abs_pm = (clip_s + pm) if d_if_rel <= d_if_abs else pm
    else:
        abs_pm = (clip_s + pm) if pm < clip_s else pm
    return abs_peaks, round(abs_pm, 3)


def _damp_camera_path(path_points: list, max_step_px: float = 195.0) -> list:
    """
    Wygładza pojedyncze skoki kamery większe niż `max_step_px` (bez utraty docelowej pozycji),
    zmieniając brutalny teleport na szybki, ciągły pan w kadrze pionowym / hybrydowym.
    """
    pts = [(float(t), int(round(float(x)))) for (t, x) in (path_points or [])]
    if len(pts) < 2:
        return pts
    step_cap = max(20.0, float(max_step_px))
    out: list[tuple[float, int]] = [pts[0]]
    for t_cur, x_cur in pts[1:]:
        prev_x = out[-1][1]
        dx = x_cur - prev_x
        if abs(dx) <= step_cap:
            out.append((t_cur, x_cur))
        else:
            step = int(round(step_cap if dx > 0 else -step_cap))
            out.append((t_cur, prev_x + step))
    return out


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
    montage_style: Optional[str] = None,
    director_decision: Optional[Any] = None,
    objective_secured: bool = False,
    ally_banner_blocked: bool = False,
    drop_anchor: Optional[str] = None,
    speed_bridge_gap_s: Optional[float] = None,
    auto_trim_intro: bool = False,
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
    _external_director = director_decision is not None
    if not _external_director:
        try:
            try:
                from lol_agent.lol_montage_director import direct_clip_montage
            except ImportError:
                from lol_montage_director import direct_clip_montage
            director_decision = direct_clip_montage(
                action_type=action_type,
                champion_name=champion_name,
                duration=clip_duration,
                peaks=peaks or [],
                force_style=montage_style,
                objective_secured=objective_secured,
                ally_banner_blocked=ally_banner_blocked,
            )
        except Exception as _dir_err:
            print(f"    [editor] Montage director fallback: {_dir_err}")

    if director_decision:
        print(f"🎬  Reżyser AI [{director_decision.archetype}]: Jump-Cut={director_decision.allow_jump_cut}, Zoom={director_decision.zoom_aggression:.2f}x, Slowmo={director_decision.slowmo_duration:.1f}s")
        print(f"    Uzasadnienie: {director_decision.rationale}")

    _pref_style = (
        (director_decision.tuning_profile or {}).get("preferred_montage_style")
        if _external_director and director_decision and getattr(director_decision, "tuning_profile", None)
        else None
    )
    _style = (montage_style or _pref_style or "PRIMARY").upper().strip()
    _style_prof = TL.get_style_profile(_style)

    # Jednolita konwersja listowa na czas źródła (np. clip_start=8.5 < peak=9.5 przy clip_dur=13.1 nie zamiesza już kolejności!)
    peaks, peak_moment = _canonicalize_to_source_time(peaks, peak_moment, clip_start, clip_duration)
    _peaks_canonical_abs = True

    _src_total_dur = 0.0
    if source_path and os.path.isfile(source_path) and os.path.getsize(source_path) > 10_000:
        try:
            import cv2 as _cv2_dur
            _cap_d = _cv2_dur.VideoCapture(source_path)
            try:
                _fps_d = float(_cap_d.get(_cv2_dur.CAP_PROP_FPS) or 0.0)
                _cnt_d = int(_cap_d.get(_cv2_dur.CAP_PROP_FRAME_COUNT) or 0)
                if _fps_d > 0.0 and _cnt_d > 0:
                    _src_total_dur = float(_cnt_d) / _fps_d
            finally:
                _cap_d.release()
        except Exception:
            _src_total_dur = 0.0

    # Styl IN_MEDIA_RES: klip zaczyna się tuż przed walką. Przesuwamy początek tak, by pierwszy kill wypadł
    # w IN_MEDIA_RES_FIRST_KILL_AT s. Kille są w czasie źródła, więc reszta montażu liczy się sama.
    if _style == "IN_MEDIA_RES" and peaks:
        try:
            _first_abs = min(float(tk) for (tk, _) in peaks)
            _lead = 2.5
            try:
                from lol_agent.lol_montage_director import IN_MEDIA_RES_FIRST_KILL_AT as _lead
            except ImportError:
                from lol_montage_director import IN_MEDIA_RES_FIRST_KILL_AT as _lead
            _shift = (_first_abs - clip_start) - _lead
            if _shift > 0.3 and (clip_duration - _shift) >= 8.0:
                clip_start += _shift
                clip_duration = clip_end - clip_start
                print(f"   ✂️  IN_MEDIA_RES: początek klipu +{_shift:.1f}s, pierwszy kill w {_lead:.1f}s")
        except Exception as _imr:
            print(f"   [editor] IN_MEDIA_RES pominięty: {_imr}")
    elif auto_trim_intro and peaks and not combat_segments and clip_duration > 9.0 and action_type.lower() not in ("solo_bolo", "solo", "1v1"):
        try:
            _first_abs = min(float(tk) for (tk, _) in peaks)
            _last_abs_intro = max(float(tk) for (tk, _) in peaks)
            _first_rel = _first_abs - clip_start
            if _first_rel > 3.5:
                _want_shift = round(_first_rel - 2.4, 2)
                if _src_total_dur > clip_end + 0.3 and not objective_secured:
                    _need_end = round(clip_start + _want_shift + 9.8, 2)
                    _max_out_ext = float(_style_prof["max_post_kill_outro_s"]) if _style_prof else 2.2
                    _max_safe_ext = min(_src_total_dur, max(clip_end, _last_abs_intro + _max_out_ext + 1.2))
                    if _need_end > clip_end and _max_safe_ext > clip_end + 0.2:
                        clip_end = round(min(_need_end, _max_safe_ext), 2)
                        clip_duration = clip_end - clip_start
                # Nigdy nie skracamy klipu poniżej 9.8s ani nie ucinamy rozpoczętej już walki przed 1. killem
                _max_safe_shift = max(0.0, clip_duration - 9.8)
                if source_path and os.path.isfile(source_path):
                    try:
                        try:
                            from lol_agent.lol_frag_detector import find_combat_start_before
                        except ImportError:
                            from lol_frag_detector import find_combat_start_before
                        _combat_start_abs = float(find_combat_start_before(source_path, _first_abs, max_lookback=min(6.5, max(1.0, _first_rel))))
                        _combat_floor = max(clip_start, _first_abs - 3.4, _combat_start_abs - 0.8)
                        _max_safe_shift = min(_max_safe_shift, max(0.0, _combat_floor - clip_start))
                    except Exception:
                        pass
                _shift = round(min(_want_shift, _max_safe_shift), 2)
                if _shift >= 0.8:
                    clip_start += _shift
                    clip_duration = clip_end - clip_start
                    print(f"   ⚡ [Auto-Trim Intro] Usunięto {_shift:.1f}s martwego wstępu — 1. kill w ~{max(0.5, _first_rel - _shift):.1f}s!")
        except Exception as _trim_err:
            print(f"   [editor] Auto-Trim pominięty: {_trim_err}")

    if source_path and os.path.isfile(source_path) and os.path.getsize(source_path) > 10_000:
        try:
            _pk_abs_list = [float(tk) for (tk, _) in (peaks or [])]
            _last_pk_abs = max(_pk_abs_list) if _pk_abs_list else float(peak_moment)
            _tail_was_trimmed = False
            _det_t, _det_kind = _detect_death_or_tab_end(source_path, clip_start, clip_end, _last_pk_abs)
            if _det_t is not None:
                _new_end = max(_last_pk_abs + 0.65, _det_t - 0.15)
                if clip_start + 6.5 <= _new_end < clip_end - 0.20:
                    clip_end = round(_new_end, 2)
                    clip_duration = clip_end - clip_start
                    _tail_was_trimmed = True
                    if combat_segments:
                        combat_segments = [
                            (s, min(e, clip_end))
                            for (s, e) in combat_segments
                            if s < clip_end - 0.4
                        ]
                    print(f"   🛡️  [Death/TAB Guard:{_det_kind}] Wykryto @ {_det_t:.2f}s — przycięto ogon do {clip_end:.2f}s")

            # Dead-Outro Guard: nie zostawiaj 4-6s bicia wieży/kraba po ostatnim killu (uwzględniając kompresję buildup_speed!)
            _first_pk_abs = min(_pk_abs_list) if _pk_abs_list else _last_pk_abs
            _slowmo_bonus_s = (
                float(_style_prof["slowmo_window_max"]) * max(0.0, (1.0 / max(0.25, float(_style_prof["slowmo_speed"]))) - 1.0)
                if (_style_prof and use_speed_ramp)
                else 0.50
            )
            _buildup_comp_s = 0.0
            if _style_prof and use_speed_ramp and float(_style_prof.get("buildup_speed", 1.0)) > 1.05:
                _b_spd = float(_style_prof["buildup_speed"])
                _est_b = max(0.0, (_last_pk_abs - clip_start) - 1.3)
                _buildup_comp_s = _est_b * (1.0 - (1.0 / _b_spd))
            _gap_comp_s = 0.0
            if _style_prof and use_speed_ramp and len(_pk_abs_list) >= 2:
                _sorted_pk_abs = sorted(_pk_abs_list)
                _max_gap_raw = max((b - a for a, b in zip(_sorted_pk_abs, _sorted_pk_abs[1:])), default=0.0)
                if _max_gap_raw > 3.55:
                    _g_spd = max(1.1, float(_style_prof.get("fast_gap_speed", 2.0)))
                    _g_tail = 0.65 if (_style == "STORY_RAW_POV" and _max_gap_raw > 4.2) else TL.FAST_TAIL
                    _g_lead = 0.65 if (_style == "STORY_RAW_POV" and _max_gap_raw > 4.2) else TL.FAST_LEAD
                    _g_win = max(0.0, _max_gap_raw - _g_tail - _g_lead)
                    _gap_comp_s = min(2.4, _g_win * (1.0 - (1.0 / _g_spd)))
            _fast_burst = action_type.lower() in ("double", "solo_bolo", "solo", "1v1", "clutch", "oneshot", "outplay")
            _min_needed_raw = max(7.0, (9.4 if _fast_burst else 10.4) - _slowmo_bonus_s + _buildup_comp_s + _gap_comp_s)
            _max_outro_s = float(_style_prof["max_post_kill_outro_s"]) if _style_prof else 2.6
            if (
                _style != "IN_MEDIA_RES"
                and not combat_segments
                and not objective_secured
                and (_style_prof is not None or (clip_end - _last_pk_abs) > 3.2)
                and (clip_end - _last_pk_abs) > (_max_outro_s + 0.35)
            ):
                _floor_end = max(_last_pk_abs + _max_outro_s, clip_start + _min_needed_raw)
                _capped_end = round(min(clip_end, _floor_end), 2)
                if _capped_end >= clip_start + 6.5 and _capped_end < clip_end - 0.25:
                    print(f"   ✂️  [Dead-Outro Guard] Obcięto ogon po ostatnim killu: {clip_end:.2f}s → {_capped_end:.2f}s (max outro {_max_outro_s:.1f}s)")
                    clip_end = _capped_end
                    clip_duration = clip_end - clip_start
                    _tail_was_trimmed = True

            # Jeśli po odcięciu śmierci / pustego outro okno < _min_needed_raw, dobierz wejście przed 1. killem (bez psucia intro > 3.85s!)
            if _tail_was_trimmed and _style != "IN_MEDIA_RES" and not combat_segments and clip_duration < _min_needed_raw and clip_start > 0.0:
                _max_lead_floor = max(0.0, _first_pk_abs - 3.85)
                _avail_pull = max(0.0, clip_start - _max_lead_floor)
                _pull = round(min(_avail_pull, _min_needed_raw - clip_duration), 2)
                if _pull >= 0.4:
                    _old_s = clip_start
                    clip_start = round(clip_start - _pull, 2)
                    clip_duration = clip_end - clip_start
                    print(f"   ◀️  [Engage Pad] Cofnięto start o {_pull:.2f}s ({_old_s:.2f}s→{clip_start:.2f}s), długość {clip_duration:.1f}s")
        except Exception as _tab_err:
            print(f"   [editor] Death/TAB/Outro Guard pominięty: {_tab_err}")

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
                # Po _canonicalize_to_source_time peaks są już w czasie źródła
                norm_peaks = list(peaks)
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
        # Remapuj peaks (w czasie źródła) na lokalną oś step1 (0.0 -> clip_duration)
        if peaks:
            if orig_clip_start > 0.0:
                peaks = [
                    (round(float(t_k) - orig_clip_start, 3), lbl)
                    for (t_k, lbl) in peaks
                    if (orig_clip_start - 0.5) <= float(t_k) <= (clip_end + 0.5)
                ]
            else:
                peaks = [(round(float(t_k), 3), lbl) for (t_k, lbl) in peaks if 0.0 <= float(t_k) <= clip_duration]

        if orig_clip_start > 0.0 and peak_moment >= orig_clip_start:
            peak_moment = max(0.5, min(clip_duration - 0.5, peak_moment - orig_clip_start))
        elif peaks and (peak_moment <= 0.0 or peak_moment > clip_duration):
            banner_latency = 1.0
            peak_moment = max(0.5, min(clip_duration - 0.5, peaks[-1][0] - banner_latency))
        elif peak_moment <= 0.0 or peak_moment > clip_duration:
            peak_moment = max(0.5, min(clip_duration - 0.5, clip_duration * 0.75))
        clip_start = 0.0
        clip_end = clip_duration


    # KROK 2: Smart Camera Crop (9:16 = 608px, STORY_RAW_POV = 960px, ARENA_WIDE = 1440px)
    print("\n[2/4] Smart Camera crop...")
    _cam_crop_w = int(_style_prof["crop_width"]) if _style_prof else TL.vertical_crop_width(1080)
    crop_x_expr = "-1"   # default: centrum geometryczne
    _cam_step_px = None
    if use_smart_camera and SMART_CAMERA_AVAILABLE:
        _cam_mod = sys.modules.get(getattr(find_action_path, "__module__", ""), None)
        _cam_saved = {}
        try:
            if (_style == "CINEMATIC_DUEL" or (director_decision and getattr(director_decision, "camera_mode", "") == "duel_centroid")) and _cam_mod is not None and hasattr(_cam_mod, "CAMERA"):
                try:
                    from lol_agent.lol_montage_director import DUEL_CAMERA as _duel
                except ImportError:
                    from lol_montage_director import DUEL_CAMERA as _duel
                _cam_saved = {k: _cam_mod.CAMERA[k] for k in _duel}
                _cam_mod.CAMERA.update(_duel)       # spokojna kamera tylko na ten render
            elif _style == "ARENA_WIDE" and _cam_mod is not None and hasattr(_cam_mod, "CAMERA"):
                _arena_cam = {
                    "max_pan_px": 75.0,
                    "lerp_alpha": 0.35,
                    "snap_delta_px": 950.0,
                    "smooth_split_px": 950.0,
                }
                _cam_saved = {k: _cam_mod.CAMERA[k] for k in _arena_cam if k in _cam_mod.CAMERA}
                _cam_mod.CAMERA.update(_arena_cam)
            elif _style == "STORY_RAW_POV" and _cam_mod is not None and hasattr(_cam_mod, "CAMERA"):
                _story_cam = {
                    "max_pan_px": 95.0,
                    "lerp_alpha": 0.42,
                    "snap_delta_px": 450.0,
                    "smooth_split_px": 450.0,
                    "smooth_win": 7,
                }
                _cam_saved = {k: _cam_mod.CAMERA[k] for k in _story_cam if k in _cam_mod.CAMERA}
                _cam_mod.CAMERA.update(_story_cam)
            elif _style == "BEAT_VELOCITY" and _cam_mod is not None and hasattr(_cam_mod, "CAMERA"):
                _beat_cam = {
                    "max_pan_px": 115.0,
                    "lerp_alpha": 0.52,
                    "snap_delta_px": 300.0,
                    "smooth_split_px": 300.0,
                    "smooth_win": 5,
                }
                _cam_saved = {k: _cam_mod.CAMERA[k] for k in _beat_cam if k in _cam_mod.CAMERA}
                _cam_mod.CAMERA.update(_beat_cam)
            path_points = find_action_path(
                step1,
                0.0, clip_duration,
                source_w=1920, source_h=1080,
                crop_w=_cam_crop_w,
                peaks=peaks or []     # <- kill-snap: champion locked during kills
            )
            if _style_prof is not None and path_points:
                path_points = _damp_camera_path(path_points, max_step_px=195.0)
            crop_x_expr = generate_ffmpeg_pan_expression(path_points)
            try:
                _xs = [float(p[1]) for p in path_points]
                _cam_step_px = round(max([abs(b - a) for a, b in zip(_xs, _xs[1:])] or [0.0]), 1)
            except Exception:
                _cam_step_px = None
        except Exception as e:
            print(f"   Blad sledzenia sciezki: {e} — fallback do centrum")
            crop_x = find_action_crop_x(
                step1,
                0.0, clip_duration,
                source_w=1920, source_h=1080,
                crop_w=_cam_crop_w
            )
            crop_x_expr = f"{crop_x}"
        finally:
            if _cam_saved and _cam_mod is not None:
                _cam_mod.CAMERA.update(_cam_saved)

    # KROK 3: Zastosuj efekty wizualne — parametry dopasowane do wagi akcji oraz wybranego stylu
    print("\n[3/4] Nakładanie efektów (crop, zoom, speed ramp)...")

    try:
        from lol_agent.tuning_manager import get_pacing_parameters
    except ImportError:
        try:
            from tuning_manager import get_pacing_parameters
        except ImportError:
            get_pacing_parameters = lambda: {}

    tuning_p = get_pacing_parameters()
    is_solo_fight = action_type.lower() in ("solo_bolo", "solo", "1v1")

    if _style_prof is not None:
        _zoom_level   = float(_style_prof["zoom_max"])
        _zoom_dur     = float(_style_prof["zoom_window_max"])
        _slowmo_dur   = float(_style_prof["slowmo_window_max"])
        _slowmo_speed = float(_style_prof["slowmo_speed"])
        _music_vol    = float(_style_prof["music_volume"])
        _game_vol     = float(_style_prof["game_volume"])
    elif is_solo_fight:
        _zoom_level   = min(1.22, float(director_decision.zoom_aggression)) if director_decision else 1.10
        _zoom_dur     = 0.40
        _slowmo_dur   = float(director_decision.slowmo_duration) if director_decision else 0.55
        _slowmo_speed = 0.70
        _music_vol    = float(tuning_p.get("music_balance", 0.85))
        _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))
    elif director_decision:
        _zoom_level   = director_decision.zoom_aggression
        _zoom_dur     = 0.55
        _slowmo_dur   = director_decision.slowmo_duration
        _slowmo_speed = 0.55
        _music_vol    = float(tuning_p.get("music_balance", 0.85))
        _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))
    else:
        _zoom_level   = min(1.12, float(tuning_p.get("zoom_aggression", 1.15)))
        _zoom_dur     = 0.60
        _slowmo_dur   = float(tuning_p.get("slowmo_duration", 1.2))
        _slowmo_speed = 0.55
        _music_vol    = float(tuning_p.get("music_balance", 0.85))
        _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))

    print(f"   ⚙️  Profil montażu ({_style if _style_prof else ('SOLO BOLO' if is_solo_fight else tuning_p.get('id', 'default'))}): zoom={_zoom_level:.2f}x, slowmo={_slowmo_dur:.2f}s ({_slowmo_speed}x), muzyka={int(_music_vol*100)}%, gra={int(_game_vol*100)}%")

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

    _dir_drop_anchor = (
        ((director_decision.tuning_profile or {}).get("drop_anchor") if director_decision and getattr(director_decision, "tuning_profile", None) else None)
        or (director_decision.synapsa_decision.get("drop_anchor") if director_decision and isinstance(getattr(director_decision, "synapsa_decision", None), dict) else None)
    )
    if _style_prof is not None:
        _effective_drop_anchor = "climax_final_kill"
    elif drop_anchor is not None:
        _effective_drop_anchor = str(drop_anchor).strip().lower()
    elif _external_director or not os.environ.get("PYTEST_CURRENT_TEST"):
        _effective_drop_anchor = str(_dir_drop_anchor or "climax_final_kill").strip().lower()
    else:
        _effective_drop_anchor = "climax_final_kill"

    _rel_kill_times_check = sorted(
        float(t_k if (t_k < clip_start or clip_start == 0.0) else (t_k - clip_start))
        for (t_k, _) in peaks
    )
    if _rel_kill_times_check:
        if (
            _effective_drop_anchor == "first_kill_engage"
            and len(_rel_kill_times_check) >= 2
            and 0.8 <= _rel_kill_times_check[0] <= 7.0
            and _rel_kill_times_check[-1] > 8.5
        ):
            rel_peak_moment = max(0.8, round(_rel_kill_times_check[0] - 0.35, 2))
            print(f"   🎵 [DropAnchor=first_kill_engage] Kotwiczę główny beat-drop na 1. kill/engage @ {rel_peak_moment:.2f}s (zamiast finału {_rel_kill_times_check[-1]:.2f}s)")
        else:
            _last_rel_k = _rel_kill_times_check[-1]
            _peak_pre_offset = 0.55 if _style_prof is not None else 0.25
            _ideal_peak = max(0.5, min(clip_duration - 0.5, round(_last_rel_k - _peak_pre_offset, 2)))
            if _style_prof is not None or abs(rel_peak_moment - _last_rel_k) > 0.65:
                rel_peak_moment = _ideal_peak

    _all_kill_rel = _rel_kill_times_check
    _inter_peaks  = ([max(0.2, round(p - 0.50, 2)) for p in _all_kill_rel[:-1] if p < rel_peak_moment - 0.5] if (len(_all_kill_rel) > 1 and clip_duration <= 20.0) else [])
    if _inter_peaks:
        print(f"   ⚡ Intermediate peaks (mini slow-mo): {[f'{p:.1f}s' for p in _inter_peaks]}")

    _sorted_kills_rel = sorted(float(p) for p in (_all_kill_rel or []))
    _max_kill_gap_rel = (
        max((b - a for a, b in zip(_sorted_kills_rel, _sorted_kills_rel[1:])), default=0.0)
        if len(_sorted_kills_rel) >= 2
        else 0.0
    )
    _use_gap_bridge = (
        use_speed_ramp
        and (
            (_style == "STORY_RAW_POV" and _max_kill_gap_rel > 2.6)
            or (_style in ("ARENA_WIDE", "BEAT_VELOCITY") and _max_kill_gap_rel > 3.55)
            or (speed_bridge_gap_s is not None and _max_kill_gap_rel > float(speed_bridge_gap_s))
        )
    )
    _ff_kills = _all_kill_rel if (_style == "SPEED_RAMP_FLOW" or _use_gap_bridge) else None
    _ff_speed = (
        None if _style == "SPEED_RAMP_FLOW"
        else (float(_style_prof["fast_gap_speed"]) if (_style_prof and _use_gap_bridge) else (2.2 if _use_gap_bridge else None))
    )
    _ff_tail = 0.65 if (_use_gap_bridge and _style == "STORY_RAW_POV" and _max_kill_gap_rel > 4.2) else None
    _ff_lead = 0.65 if (_use_gap_bridge and _style == "STORY_RAW_POV" and _max_kill_gap_rel > 4.2) else None
    if _use_gap_bridge and _ff_kills and _ff_speed and _ff_speed > 1.05:
        _pre_segs = TL.build_speed_segments(
            clip_duration=clip_duration,
            peak_moment=rel_peak_moment,
            slowmo_speed=_slowmo_speed if use_speed_ramp else 1.0,
            slowmo_duration=_slowmo_dur,
            zoom_duration=_zoom_dur,
            intermediate_peaks=_inter_peaks if use_speed_ramp else [],
            use_easing=True,
            slowmo_window_max=float(_style_prof["slowmo_window_max"]) if _style_prof else None,
            zoom_window_max=float(_style_prof["zoom_window_max"]) if _style_prof else None,
            buildup_speed=float(_style_prof.get("buildup_speed", 1.0)) if _style_prof else 1.0,
        )
        _adap_spd = TL.compute_adaptive_gap_speed(
            _pre_segs, _ff_kills, base_speed=_ff_speed, min_output_dur=9.4,
            tail=_ff_tail, lead=_ff_lead,
        )
        if _adap_spd <= 1.05:
            _ff_kills = None
            _ff_speed = None
        else:
            _ff_speed = _adap_spd

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
        fast_forward_kills=_ff_kills,
        fast_forward_speed=_ff_speed,
        montage_style=_style,
        fast_forward_tail=_ff_tail,
        fast_forward_lead=_ff_lead,
    )
    _segments = _timeline.get("segments") or []
    # Cios na osi GOTOWEGO filmu (po zwolnieniach). Przed 11.11.2026 muzyka dostawała czas surowy
    # i przy multikillach drop padał nawet ~0.8 s przed ciosem.
    _mapped_peak = _timeline.get("mapped_peak", rel_peak_moment)
    if abs(_mapped_peak - rel_peak_moment) > 0.02:
        print(f"   🧭 Oś czasu: cios {rel_peak_moment:.2f}s (klip) → {_mapped_peak:.2f}s (gotowy film), długość {final_duration:.2f}s")

    # KROK 4: Muzyka dopasowana do akcji z beat-sync
    print("\n[4/7] Muzyka i synchronizacja beat-sync + miksowanie audio gry...")
    _pref_trk = preferred_track or ("ncs_egzod_royalty.mp3" if action_type == "pentakill" else None)
    try:
        music = pick_music_for_action(
            action_type,
            preferred_track=_pref_trk,
            min_drop_time=_mapped_peak + 0.5,
            prefer_instrumental=(_style == "STORY_RAW_POV"),
        )
    except TypeError:
        music = pick_music_for_action(action_type, preferred_track=_pref_trk)
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

    _outro_obj = select_non_repeating_outro_cta(action_type=action_type, champion_name=champion_name)
    _end_cta = _outro_obj["text"]

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
        cta_duration=1.5,
        time_segments=_segments,
        style_mode=_style,
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
        _eff = TL.effective_edit_values(
            _zoom_level if use_zoom_punch else 1.0,
            _zoom_dur,
            _slowmo_dur,
            zoom_max=float(_style_prof["zoom_max"]) if _style_prof else None,
            zoom_window_max=float(_style_prof["zoom_window_max"]) if _style_prof else None,
            slowmo_window_max=float(_style_prof["slowmo_window_max"]) if _style_prof else None,
        )
        _syn_dec = getattr(director_decision, "synapsa_decision", None) if director_decision else None
        _tp_dec = (getattr(director_decision, "tuning_profile", None) or {}) if director_decision else {}
        _recipe = {
            "recipe_version": 1,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": os.path.basename(source_path),
            "action_type": action_type, "champion": champion_name, "montage_style": _style or "PRIMARY",
            "frame_mode": (_style_prof["frame_mode"] if _style_prof else "vertical"),
            "drop_anchor": _effective_drop_anchor,
            "director_operation": ((_syn_dec or {}).get("operation") if isinstance(_syn_dec, dict) else None) or "KEEP_FULL_CONTINUOUS",
            "camera_mode": (director_decision.camera_mode if director_decision else "tight_player"),
            "camera_peak_step_px": _cam_step_px,
            "clip_seconds_in": round(clip_duration, 3), "final_seconds": round(final_duration, 3),
            "jump_cut_segments": [list(x) for x in combat_segments] if combat_segments else None,
            "peaks_in_clip": [[round(float(tk), 3), lbl] for (tk, lbl) in (_rel_kill_peaks or [])],
            "peak_in_clip": round(rel_peak_moment, 3), "peak_in_output": round(_mapped_peak, 3),
            "director": ({
                "archetype": director_decision.archetype,
                "allow_jump_cut": director_decision.allow_jump_cut,
                "asked_zoom": director_decision.zoom_aggression,
                "asked_slowmo": director_decision.slowmo_duration,
                "buildup_sec": director_decision.buildup_sec,
                "outro_sec": director_decision.outro_sec,
                "camera_mode": director_decision.camera_mode,
                "synapsa_decision": _syn_dec,
                "rollback_guard": _tp_dec.get("director_rollback_guard"),
            } if director_decision else None),
            "applied": {"zoom_level": _eff["zoom_level"], "zoom_window": _eff["zoom_window"], "slowmo_window": _eff["slowmo_window"],
                        "slowmo_speed": _slowmo_speed if use_speed_ramp else 1.0, "smart_camera": bool(use_smart_camera and SMART_CAMERA_AVAILABLE),
                        "music_volume": _music_vol, "game_volume": _game_vol, "game_audio_warped": bool(WARP_GAME_AUDIO and _segments)},
            "time_segments": _segments,
            "music": dict(LAST_MUSIC_SYNC) if music else None,
            "hook_text": _hook, "cta_text": _end_cta,
            "outro_cta_id": _outro_obj.get("id"), "outro_cta_kind": _outro_obj.get("kind"),
        }
        _recipe_out = os.path.splitext(step5)[0] + ".recipe.json"
        with open(_recipe_out, "w", encoding="utf-8") as _rf:
            json.dump(_recipe, _rf, indent=1, ensure_ascii=False)
        try:
            try:
                from lol_agent.synapsa_conversation_learner import record_recipe_delta_on_render
            except ImportError:
                from synapsa_conversation_learner import record_recipe_delta_on_render
            _delta = record_recipe_delta_on_render(_recipe_out)
            if _delta:
                print(f"   🧠 [Cause->Effect] Delta atrybutów ({_delta.get('verdict')}): {list((_delta.get('changed_attributes') or {}).keys())[:4]}")
        except Exception:
            pass
        if not os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("SYNAPSA_AUTO_WATCHABILITY", "1") == "1":
            try:
                from pathlib import Path as _WPath
                try:
                    from lol_agent.synapsa_watchability_judge import compare_shorts_and_verify
                except ImportError:
                    from synapsa_watchability_judge import compare_shorts_and_verify
                _src_val = str(_recipe.get("source") or "")
                _cur_mp4 = _WPath(step5).resolve()
                _prev_candidates = []
                for _cand in _WPath(os.path.dirname(_recipe_out)).glob("*.recipe.json"):
                    if os.path.abspath(str(_cand)) == os.path.abspath(_recipe_out):
                        continue
                    try:
                        _cd = json.loads(_cand.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if _src_val and str(_cd.get("source") or "") != _src_val:
                        continue
                    _cand_mp4 = _WPath(str(_cand)[:-len(".recipe.json")] + ".mp4")
                    if _cand_mp4.is_file() and _cand_mp4.resolve() != _cur_mp4:
                        _prev_candidates.append((_cand.stat().st_mtime, str(_cand_mp4)))
                if _prev_candidates:
                    _prev_candidates.sort(key=lambda x: x[0], reverse=True)
                    _wcmp = compare_shorts_and_verify(_prev_candidates[0][1], step5, use_local_ai=False)
                    print(f"   👁️ [Watchability] {_wcmp.get('watchability_summary')}")
            except Exception:
                pass
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
