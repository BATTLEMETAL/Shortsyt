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
import numpy as np
from typing import Optional
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

    # Dedup: wykluczaj ostatnio używane utwory (historia ostatnich utworów)
    last_track_file = os.path.join(LOL_MUSIC_DIR, ".last_track")
    recent_tracks = []
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


def cut_clip(input_path: str, start: float, end: float, output_path: str) -> str:
    """
    Wycina fragment klipu z zachowaniem dokładności klatkowej (Frame-Accurate Cut).
    Używa szybkiego enkodera NVENC / ultrafast CPU aby wyeliminować desynchronizację I-frame.
    """
    duration = max(0.1, end - start)
    encoder_draft = get_optimal_encoder_args("draft")

    # Próba 1: Dokładne cięcie z enkoderem sprzętowym (NVENC trwa < 0.5s)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-i", input_path,
        "-t", f"{duration:.3f}",
        *encoder_draft,
        "-vf", "setpts=PTS-STARTPTS",   # zeruje PTS — eliminuje offset AV po cięciu NVENC
        "-c:a", "aac", "-b:a", "192k",
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
            "-c:a", "aac", "-b:a", "192k",
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
                         intermediate_peaks: list = None) -> float:
    """
    Stosuje pionowe kadrowanie, zoom-punch i spowolnienie (speed ramp)
    w jednym przebiegu za pomocą filter_complex w FFmpeg.
    crop_x moze byc wyrazeniem (np. if(lt(t,5.0),...)) dla dynamicznego sledzenia.
    intermediate_peaks: czasy (rel. do klipu) killów PRZED glównym peak_moment.
      -> kazdy dostaje mini slow-mo 0.8x/0.5s (zaznaczenie kill bez pelnego slow-mo)
    Gwarantuje idealna dokladnosc klatkowaa i brak przyciec/desynchronizacji.
    """
    source_w, source_h = 1920, 1080
    crop_w = int(source_h * 9 / 16)   # 607 ~= 608
    crop_h = source_h

    # Jeśli podano int/float, skonwertuj na str
    if not isinstance(crop_x, str):
        cx = max(0, min(int(crop_x), source_w - crop_w)) if crop_x >= 0 else (source_w - crop_w) // 2
        crop_x_expr = f"{cx}"
    else:
        crop_x_expr = crop_x

    # Parametry zoomu (PENTA/ostatni kill)
    crop_w_zoom = int(crop_w / zoom_level)
    crop_h_zoom = int(crop_h / zoom_level)
    crop_x_expr_zoom = f"({crop_x_expr})+{(crop_w - crop_w_zoom) // 2}"
    crop_y_zoom = (source_h - crop_h_zoom) // 2

    out_w, out_h = 1080, 1920

    t0 = 0.0
    # Anticipation lead-in: zwolnienie zaczyna się 0.25s-0.4s przed decydującym ciosem
    lead_in = 0.25 if slowmo_speed >= 0.65 else 0.40
    t1 = max(t0, peak_moment - lead_in)
    t2 = peak_moment + zoom_duration
    t3 = peak_moment + slowmo_duration
    t4 = clip_duration

    # Zabezpieczenia czasowe
    t1 = max(t0, min(t1, t4))
    t2 = max(t1, min(t2, t4))
    t3 = max(t2, min(t3, t4))

    # Mini slow-mo parametry (TRIPLE/QUADRA i inne kills przed PENTA)
    MINI_SPEED = 0.6   # 60% tempa -- wyrazne zaznaczenie kill (sesja 15: 0.8→0.6)
    MINI_DUR   = 1.0   # 1.0s -- TRIPLE/QUADRA musza "bic" (sesja 15: 0.5→1.0)

    normal_crop = f"crop={crop_w}:{crop_h}:'{crop_x_expr}':0"

    segs = []
    # Segment 1: Naturalny, dynamiczny przebieg walki (1.0x, 60 FPS)
    if t1 > t0 + 0.05:
        segs.append({"start": t0, "end": t1, "speed": 1.0, "crop": normal_crop})

    # Segment 2: Kulminacyjny decydujący cios (slow-mo + subtelny zoom-punch na gracza)
    if t2 > t1 + 0.05:
        segs.append({
            "start": t1, "end": t2, "speed": slowmo_speed,
            "crop": f"crop={crop_w_zoom}:{crop_h_zoom}:'{crop_x_expr_zoom}':{crop_y_zoom}"
        })

    # Segment 3: Płynne wyjście ze spowolnienia (slow-mo bez zoomu)
    if t3 > t2 + 0.05:
        segs.append({"start": t2, "end": t3, "speed": slowmo_speed, "crop": normal_crop})

    # Segment 4: Finisz i zakończenie akcji w tempie 1.0x
    if t4 > t3 + 0.05:
        segs.append({"start": t3, "end": t4, "speed": 1.0, "crop": normal_crop})

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


# ─── Czcionka Impact Windows ─────────────────────────────────────────────────
FONT_PATH = r"C:\Windows\Fonts\impact.ttf"
FONT_FALLBACK = r"C:\Windows\Fonts\arialbd.ttf"


def _get_font_path() -> str:
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    if os.path.exists(FONT_FALLBACK):
        return FONT_FALLBACK
    return ""


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
    if not hook_text:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki Impact — pomijam overlay tekstu")
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    # Usuń emoji — FFmpeg drawtext ich nie obsługuje
    import re
    clean_text = re.sub(r'[^\x00-\x7F]+', '', hook_text).strip()
    clean_text = clean_text.replace("'", "")   # usuń apostrof — łamie FFmpeg drawtext parser w subprocess
    clean_text = clean_text.replace(":", "\\:")  # escape dwukropek (separator FFmpeg)
    clean_text = clean_text.replace("%", "%%")   # escape procent

    if peak_moment <= 0.5:
        t_start = 0.0
    else:
        t_start = max(0.0, peak_moment - 0.2)
    t_end = min(video_duration, t_start + show_duration)

    # Styl: duży Impact z czarnym obrysem i półprzezroczystym tłem dla maksymalnego CTR
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

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"{drawbox},{drawtext}",
        *get_optimal_encoder_args("high"),
        "-c:a", "copy",
        output_path
    ]
    print(f"🗨️  Overlay tekstu: '{clean_text}' @ {t_start:.1f}s–{t_end:.1f}s")
    r = _run_ffmpeg(cmd, timeout=60.0, desc="add_text_overlay GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  Overlay error (próbuję fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"{drawbox},{drawtext}",
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

    Rozmiary fontów i kolory wg rangi killa:
      DOUBLE KILL  → 80px, biały
      TRIPLE KILL  → 100px, żółty
      QUADRAKILL   → 115px, pomarańczowy
      PENTAKILL    → 135px, czerwony + blink
      SOLO BOLO    → 115px, karmazynowy (#DC2626)
    """
    if not peaks:
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki — pomijam dynamiczne napisy")
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    import re
    font_safe = font.replace(chr(92), '/').replace(':', '\\:')

    # Konfiguracja wizualna wg etykiety killa
    # P3 FIX (2026-08-12): PENTAKILL/GODLIKE zmienione z 'red' na złoty LoL '0xFFD700'
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

    # Przelicz czas z oryginalnego klipu na czas w zmontowanym wideo
    # Oblicza dokładną analityczną transformację czasu uwzględniając mini slow-mo (0.6x) i główny slow-mo (0.5x)
    def _adjust_t(t_orig: float) -> float:
        """Map original-clip timestamp → rendered-video timestamp accounting for all slow-mo segments."""
        MINI_SPEED = 0.6
        MINI_DUR   = 1.0
        
        t0 = 0.0
        t1 = max(t0, min(peak_moment - 0.4, video_duration))
        t2 = max(t1, min(peak_moment + 1.0, video_duration))
        t3 = max(t2, min(peak_moment + slowmo_duration, video_duration))
        t4 = video_duration

        # Buduj sekwencję segmentów czasu
        segments = []
        cursor = t0
        
        # Wyciągnij intermediate_peaks z peaks
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

        # Oblicz zmapowany czas
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

    is_solo = bool(action_type and action_type.lower() in ("solo_bolo", "solo", "1v1"))

    caption_items = []
    if is_solo:
        # W trybie Solo Bolo (1v1) istnieje tylko jeden cel pojedynku.
        # Wszelkie multikille (DOUBLE/TRIPLE/PENTA) oraz liczniki KILL 2/3 są całkowicie eliminowane!
        if peaks:
            best_p = min(peaks, key=lambda p: abs((p[0] if p[0] < trim_start or trim_start == 0.0 else p[0] - trim_start) - peak_moment))
            t_abs, _ = best_p
            t_raw = t_abs if (t_abs < trim_start or trim_start == 0.0) else (t_abs - trim_start)
            t_in_clip = _adjust_t(t_raw)
            if 0 <= t_in_clip <= video_duration:
                style = KILL_STYLES.get("SOLO BOLO", {"size": 115, "color": "0xFF3333", "duration": 2.2})
                t_start = max(0.0, t_in_clip - 0.5)
                t_end = min(video_duration, t_start + style["duration"])
                caption_items.append({
                    "start": t_start,
                    "end": t_end,
                    "label": "SOLO BOLO",
                    "style": style,
                    "t_in_clip": t_in_clip,
                })
    else:
        for (t_abs, label) in peaks:
            # Obsłuż zarówno relatywne (0..dur) jak i absolutne (> trim_start) timestamps
            t_raw = t_abs if (t_abs < trim_start or trim_start == 0.0) else (t_abs - trim_start)
            t_in_clip = _adjust_t(t_raw)
            if t_in_clip < 0 or t_in_clip > video_duration:
                continue

            style = KILL_STYLES.get(str(label).upper().strip(), {"size": 90, "color": "white", "duration": 2.0})
            # Offset antycypacji 0.6s: synchronizacja z momentem animacji ciosu/zgonu w grze
            t_start = max(0.0, t_in_clip - 0.6)
            t_end   = min(video_duration, t_start + style["duration"])

            clean_label = re.sub(r'[^\x00-\x7F]+', '', label).strip()
            clean_label = clean_label.replace("'", "\\\\\'")

            caption_items.append({
                "start": t_start,
                "end": t_end,
                "label": clean_label,
                "style": style,
                "t_in_clip": t_in_clip,
            })

    # Zabezpieczenie przed nakładaniem napisów: poprzedni napis znika natychmiast gdy pojawia się kolejny kill!
    caption_items.sort(key=lambda x: x["start"])
    for i in range(len(caption_items) - 1):
        next_start = caption_items[i+1]["start"]
        if caption_items[i]["end"] > next_start:
            caption_items[i]["end"] = max(caption_items[i]["start"] + 0.3, next_start - 0.05)

    drawtext_filters = []
    total_kills = len(caption_items)

    for idx, item in enumerate(caption_items):
        t_start = item["start"]
        t_end   = item["end"]
        clean_label = item["label"]
        style = item["style"]

        # ── A. Dynamic Kill Streak Counter HUD (np. [ 💀 1 / 3 ] -> [ 👑 TRIPLE ]) ──
        if total_kills >= 2 and not is_solo:
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

        # ── B. Główny Kill Banner w strefie centralnej ────────────────────────
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

    # ── C. Neon Loop Progress Scrubber (Złoty pasek na dole pod zapętlenie) ─────
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
                game_volume: Optional[float] = None) -> str:
    """Nakłada muzykę i miesza ją z oryginalnym dźwiękiem gry.

    video_path      = wideo bez audio (step4 po apply_editor_effects)
    game_audio_path = źródłowy klip z dźwiękiem gry (step1 — wyciety raw clip)
                      Jeśli None — spróbuj pobrać audio z video_path.
    """
    if not music_path or not os.path.exists(music_path):
        print("⚠️ Brak muzyki — eksportuję bez dźwięku")
        shutil.copy(video_path, output_path)
        return output_path

    fname = os.path.basename(music_path)

    # Auto-detect beat drop with librosa (falls back to manual map)
    if BEAT_DETECTOR_OK:
        drop_time = _get_drop_time(music_path, manual_map=MUSIC_DROP_MAP)
    else:
        drop_time = MUSIC_DROP_MAP.get(fname, 0.0)

    music_seek_args = []
    if drop_time > 0.0:
        music_start = max(0.0, drop_time - video_peak_time)
        print(f"🎵 Beat Sync: drop piosenki = {drop_time}s, szczyt wideo = {video_peak_time}s -> start piosenki = {music_start:.2f}s")
        music_seek_args = ["-ss", f"{music_start:.3f}"]
    else:
        print(f"🎵 Brak mapy dropu dla {fname} — puszczam od początku")

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

        filter_complex = (
            f"[2:a]loudnorm=I=-14:TP=-1.5:LRA=11,"
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
    font = _get_font_path()
    if not font:
        print("⚠️  Brak czcionki — pomijam CTA overlay")
        import shutil as _sh
        _sh.copy(video_path, output_path)
        return output_path

    import re
    font_safe = font.replace(chr(92), '/').replace(':', '\\:')
    clean_cta = re.sub(r'[^\x00-\x7F]+', '', cta_text).strip()
    clean_cta = clean_cta.replace("'", "\\\\'")
    clean_cta = clean_cta.replace(":", "\\:")
    clean_cta = clean_cta.replace("%", "%%")

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
        f":y=ih*0.74"
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
        f":y=h*0.76"
        f":fontsize={fsize}"
        f":fontcolor=0xFFD700"
        f":borderw=4"
        f":bordercolor=black"
        f":shadowx=2:shadowy=2:shadowcolor=black@0.8"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"{cta_box},{drawtext}",
        *get_optimal_encoder_args("draft"),
        "-movflags", "+faststart",
        "-c:a", "copy",
        output_path
    ]
    print(f"🔔 CTA overlay: '{clean_cta}' @ ostatnie {show_duration:.1f}s (fsize={fsize}px)")
    r = _run_ffmpeg(cmd, timeout=90.0, desc="add_cta_overlay GPU")
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  CTA overlay error (próbuję fallback CPU): {err}")
        cmd_cpu = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"{cta_box},{drawtext}",
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
    step5_cta    = t("06_cta.mp4")
    step5        = os.path.join(_tmp, output_filename)

    # ── KROK 1: Wycięcie fragmentu / segmentów ────────────────────────────────
    print("\n[1/4] Wycinanie fragmentu...")

    # Dla SOLO BOLO wykluczamy jakiekolwiek cięcia jump-cut — cała walka ma być płynna od wejścia do finału
    if action_type.lower() in ("solo_bolo", "solo", "1v1"):
        combat_segments = None

    if combat_segments and len(combat_segments) > 1:
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
            cut_clip(source_path, seg_s, seg_e, seg_path)
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
            is_relative = (peaks[0][0] < orig_clip_start) if orig_clip_start > 0 else True
            if not is_relative:
                peaks = [(round(t_k - orig_clip_start, 3), lbl) for (t_k, lbl) in peaks]
            else:
                peaks = [(round(t_k, 3), lbl) for (t_k, lbl) in peaks]
        if peak_moment > clip_duration and peak_moment >= orig_clip_start:
            peak_moment = max(0.5, min(clip_duration - 0.5, peak_moment - orig_clip_start))
        elif peaks and (peak_moment <= 0.0 or peak_moment > clip_duration):
            peak_moment = max(0.5, min(clip_duration - 0.5, peaks[-1][0]))
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
                crop_w=int(1080 * 9 / 16),
                peaks=peaks or []     # <- kill-snap: champion locked during kills
            )
            # P1 FIX (2026-08-12): Kill banner shift — gdy kill peak, przesuń crop_x
            # BANNER_SHIFT = 0: Champion pozostaje w 100% w centrum kadru.
            # Wyeliminowano sztuczne przesuwanie kadru w lewo, które wyrzucało Katarinę poza prawy margines.
            BANNER_SHIFT = 0
            BANNER_WINDOW = 0.0
            CROP_W = int(1080 * 9 / 16)
            SOURCE_W = 1920
            kill_times = [t_k for (t_k, _) in (peaks or [])]
            if kill_times and BANNER_SHIFT > 0:
                # SESJA 13 FIX: scal nakladajace sie kill windows (MERGE_GAP=1.5s)
                # Eliminuje 320px round-trip jerk w 0.3-0.4s gapach miedzy TRIPLE/QUADRA/PENTA
                MERGE_GAP = 1.5
                merged_windows = []
                for tk in sorted(kill_times):
                    ws, we = tk - BANNER_WINDOW, tk + BANNER_WINDOW
                    if merged_windows and ws < merged_windows[-1][1] + MERGE_GAP:
                        merged_windows[-1] = (merged_windows[-1][0], max(merged_windows[-1][1], we))
                    else:
                        merged_windows.append([ws, we])
                # SESJA 14 FIX A: ramp 0.5s przy wejsciu/wyjsciu z merged window
                # Zamiast instant skoku -160px: plynny ramp w ciagu RAMP_SECS
                RAMP_SECS = 0.5
                shifted = []
                for (pt, px) in path_points:
                    # Znajdz najblizszy merged window i oblicz alpha rampy
                    shift_alpha = 0.0
                    for (ws, we) in merged_windows:
                        if pt < ws:
                            continue
                        if pt > we:
                            continue
                        # pt jest wewnatrz okna
                        dist_start = pt - ws  # jak daleko od poczatku
                        dist_end   = we - pt  # jak daleko od konca
                        ramp_in  = min(1.0, dist_start / RAMP_SECS) if RAMP_SECS > 0 else 1.0
                        ramp_out = min(1.0, dist_end   / RAMP_SECS) if RAMP_SECS > 0 else 1.0
                        shift_alpha = min(ramp_in, ramp_out)
                        break
                    if shift_alpha > 0:
                        effective_shift = int(BANNER_SHIFT * shift_alpha)
                        px_shifted = max(0, min(px - effective_shift, SOURCE_W - CROP_W))
                        shifted.append((pt, px_shifted))
                    else:
                        shifted.append((pt, px))
                path_points = shifted
                print(f"   🏆 Kill banner shift: -{BANNER_SHIFT}px (ramp {RAMP_SECS}s) @ {len(merged_windows)} merged window(s) (from {len(kill_times)} kills)")
            crop_x_expr = generate_ffmpeg_pan_expression(path_points)
        except Exception as e:
            print(f"   Blad sledzenia sciezki: {e} — fallback do centrum")
            crop_x = find_action_crop_x(
                step1,
                0.0, clip_duration,
                source_w=1920, source_h=1080,
                crop_w=int(1080 * 9 / 16)
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
        # Krótkie, punktowe uderzenie na śmiertelny cios zamiast 4 sekund powolnego trupa.
        _zoom_level   = 1.15
        _zoom_dur     = 0.45
        _slowmo_dur   = 0.55
        _slowmo_speed = 0.70
    else:
        _zoom_level   = float(tuning_p.get("zoom_aggression", 1.20))
        _zoom_dur     = 0.80
        _slowmo_dur   = float(tuning_p.get("slowmo_duration", 1.4))
        _slowmo_speed = 0.50

    _music_vol    = float(tuning_p.get("music_balance", 0.85))
    _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))

    print(f"   ⚙️  Profil montażu ({'SOLO BOLO' if is_solo_fight else tuning_p.get('id', 'default')}): zoom={_zoom_level:.2f}x, slowmo={_slowmo_dur:.1f}s ({_slowmo_speed}x), muzyka={int(_music_vol*100)}%, gra={int(_game_vol*100)}%")

    # Intermediate peaks: wszystkie kille PRZED ostatnim (PENTA) -> mini slow-mo 0.8x/0.5s
    _all_kill_rel = sorted([(t_k if (t_k < clip_start or clip_start == 0.0) else (t_k - clip_start)) for (t_k, _) in (peaks or [])])
    _inter_peaks  = _all_kill_rel[:-1] if len(_all_kill_rel) > 1 else []
    if _inter_peaks:
        print(f"   ⚡ Intermediate peaks (mini slow-mo): {[f'{p:.1f}s' for p in _inter_peaks]}")

    final_duration = apply_editor_effects(
        input_path=step1,
        output_path=step4,
        clip_duration=clip_duration,
        crop_x=crop_x_expr,
        peak_moment=peak_moment,
        zoom_level=_zoom_level if use_zoom_punch else 1.0,
        zoom_duration=_zoom_dur,
        slowmo_speed=_slowmo_speed if use_speed_ramp else 1.0,
        slowmo_duration=_slowmo_dur,
        intermediate_peaks=_inter_peaks if use_speed_ramp else []
    )

    # KROK 4: Muzyka dopasowana do akcji z beat-sync
    print("\n[4/7] Muzyka i synchronizacja beat-sync + miksowanie audio gry...")
    music = pick_music_for_action(action_type, preferred_track=preferred_track or ("ncs_egzod_royalty.mp3" if action_type == "pentakill" else None))
    # Przekazuj step1 (surowy wycinek z audio gry) jako game_audio_path
    # step4 nie ma audio (apply_editor_effects mapuje tylko [v_final])
    _rel_kill_peaks = [((tk if (tk < clip_start or clip_start == 0.0) else (tk - clip_start)), lbl) for (tk, lbl) in (peaks or [])]
    merge_music(step4, music, step5_music, final_duration, peak_moment,
                game_audio_path=step1, kill_peaks=_rel_kill_peaks,
                music_volume=_music_vol, game_volume=_game_vol)

    # KROK 5: Dynamiczne napisy kill-by-kill
    _peaks = peaks or []
    step5_captions = t("05_captions.mp4")
    if _peaks:
        print(f"\n[5/6] Dynamiczne napisy ({len(_peaks)} kill peaks)...")
        add_dynamic_captions(
            video_path    = step5_music,
            peaks         = _peaks,
            trim_start    = clip_start,
            video_duration= final_duration,
            output_path   = step5_captions,
            peak_moment   = peak_moment,
            slowmo_speed  = _slowmo_speed,
            slowmo_duration = _slowmo_dur,
            action_type   = action_type,
        )
    else:
        # Brak OCR peaks — przeskocz ten krok
        import shutil as _sh
        _sh.copy(step5_music, step5_captions)
        print("\n[5/6] Brak kill peaks — pomijam dynamiczne napisy")

    # KROK 6: Hook overlay — pojawia sie na POCZATKU (pierwsze 2s) żeby zatrzymać scroll
    # Badania: hook musi trafić przed pierwszą decyzją o swipe (0-2s)
    # Kill captions (QUADRAKILL/PENTAKILL) sa dodawane w add_dynamic_captions (krok 5)
    _hook = hook_text.strip() if hook_text else ""
    if not _hook:
        try:
            from lol_agent.lol_config import ACTION_LABELS
        except ImportError:
            from lol_config import ACTION_LABELS
        _hook = ACTION_LABELS.get(action_type, "").replace("🔥","").replace("⚡","").replace("💥","").replace("🎯","").replace("👑","").strip()
    print(f"\n[6/7] Hook overlay: '{_hook}' @ 0.0s (zatrzymanie scrolla)...")
    hook_show_start = 0.0   # od klatki 0.0s — kluczowe dla obniżenia wskaźnika Swiped Away (<15%)
    add_text_overlay(step5_captions, _hook, hook_show_start, final_duration, step5_cta)

    # KROK 7: Engagement Trigger CTA overlay (ostatnie 1.8s)
    # Zamiast nudnego "Leave a like" -> prowokujące pytanie wymuszające komentarze i podbijające AVD przy zapętleniu
    act_lower = action_type.lower()
    if "penta" in act_lower:
        _end_cta = "CLEAN 1v5 OR TROLLING? RATE 1-10"
    elif "quadra" in act_lower:
        _end_cta = "CLEAN 1v4 OR LUCKY? RATE 1-10"
    elif "solo" in act_lower or "bolo" in act_lower or "1v1" in act_lower:
        _end_cta = "CLEAN OUTPLAY OR PURE LUCK? RATE 1-10"
    elif "clutch" in act_lower or "1hp" in act_lower or "1%" in act_lower:
        _end_cta = "CALCULATED OR 100% LUCK? RATE 1-10"
    else:
        _end_cta = "CLEAN PLAY OR PURE LUCK? RATE 1-10"
    print(f"\n[7/7] Engagement CTA overlay: '{_end_cta}'...")
    add_cta_overlay(step5_cta, final_duration, step5, cta_text=_end_cta, show_duration=1.8)

    # ── KROK 8: Freeze-frame hook na klatce 0.0s (P2 — Hook Frame Zero) ─────────
    # Wstawia 0.6s freeze pierwszej klatki z hookiem żeby zatrzymać scrollera.
    # Nie dotyczy solo_bolo (tam walka zaczyna się natychmiast — freeze by zepsuła dynamikę).
    # Guard: jeśli pierwszy kill jest w pierwszych 3s klipu → pomijamy freeze (pierwsza akcja by zniknęła).
    _first_kill_t = min((t_k for (t_k, _) in (peaks or [])), default=999.0)
    _action_starts_immediately = _first_kill_t <= 3.0
    _do_freeze = (bool(_hook)
                  and not _action_starts_immediately
                  and action_type.lower() not in ("solo_bolo", "solo", "1v1"))
    if _action_starts_immediately and bool(_hook):
        print(f"\n[8/8] Freeze-frame hook: POMINIĘTY — pierwszy kill za {_first_kill_t:.1f}s (akcja natychmiastowa)")
    if _do_freeze:
        step5_freeze = t("08_freeze_hook.mp4")
        print(f"\n[8/8] Freeze-frame hook: '{_hook[:30]}' (0.6s freeze na starcie)...")
        prepend_freeze_hook(
            video_path=step5,
            hook_text=_hook,
            output_path=step5_freeze,
            freeze_duration=0.6,
            clean_source_path=step5_captions,
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


    # ── SPRZĄTANIE PLIKÓW TYMCZASOWYCH ──────────────────────────────────────────
    temp_intermediates = [step1, step4, step5_music, step5_captions, step5_cta]
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
