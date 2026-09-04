"""
LOL Agent — Editor v3
Styl: czysty gameplay, tekst hook na peak, muzyka dobrana do energii akcji,
      efekt zoom-punch na peak moment + dynamiczne śledzenie kamery.
"""
import os
import random
import subprocess
import glob
import shutil
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
    # ── Already in lol_music/ ─────────────────────────────────────────────
    "ncs_elektronomia_sky_high.mp3":           "high",
    "ncs_cartoon_on_and_on.mp3":               "medium",

    # ── Download from ncs.io and add to lol_music/ ───────────────────────
    # HIGH energy — use for: pentakill, quadrakill, baron
    "ncs_egzod_royalty.mp3":                   "high",
    "ncs_lost_sky_dreams_pt2.mp3":             "high",
    "ncs_robin_hustin_light_it_up.mp3":        "high",
    "ncs_elektronomia_memory.mp3":             "high",
    "ncs_unknown_brain_superhero.mp3":         "high",

    # MEDIUM energy — use for: triple kill, outplay, clutch, oneshot
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

    # Zapisz historię (max 4 ostatnie utwory)
    try:
        updated_history = (recent_tracks + [chosen_name])[-4:]
        with open(last_track_file, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_history))
    except Exception:
        pass

    energy_label = MUSIC_ENERGY_MAP.get(chosen_name, "?")
    print(f"🎵 Muzyka [{energy_label}]: {chosen_name}")
    return chosen


def get_video_duration(path: str) -> float:
    """Zwraca długość wideo w sekundach."""
    r = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def cut_clip(input_path: str, start: float, end: float, output_path: str) -> str:
    """Wycina fragment klipu."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-i", input_path,
        "-t", str(duration),
        "-c", "copy", output_path
    ]
    print(f"✂️  Tnę: {start:.1f}s → {end:.1f}s ({duration:.1f}s)")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg cut error: {r.stderr.decode('utf-8', errors='replace')[:400]}")
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
    # Anticipation lead-in: zwolnienie zaczyna się 0.4s przed decydującym ciosem
    t1 = max(t0, peak_moment - 0.4)
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
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg filtergraph error: {r.stderr.decode('utf-8', errors='replace')[:800]}")
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
            r = subprocess.run(cmd_step1, capture_output=True)
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
            r2 = subprocess.run(cmd_step2, capture_output=True)
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

    t_start = max(0.0, peak_moment - 0.2)
    t_end = min(video_duration, t_start + show_duration)

    # Styl: duży biały Impact z grubym czarnym obrysem
    # Y=0.50 — bezpieczna strefa YouTube Shorts (dolne 25% zasłonięte przez UI aplikacji)
    drawtext = (
        f"drawtext="
        f"fontfile='{font.replace(chr(92), '/').replace(':', '\\:')}'"
        f":text='{clean_text}'"
        f":x=(w-text_w)/2"
        f":y=h*0.10"  # górna strefa — widoczna, nie zasłania akcji ani kill text LoL
        f":fontsize=110"
        f":fontcolor=white"
        f":borderw=6"
        f":bordercolor=black"
        f":shadowx=3:shadowy=3:shadowcolor=black@0.7"
        f":enable='between(t,{t_start:.2f},{t_end:.2f})'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", drawtext,
        *get_optimal_encoder_args("high"),
        "-c:a", "copy",
        output_path
    ]
    print(f"🗨️  Overlay tekstu: '{clean_text}' @ {t_start:.1f}s–{t_end:.1f}s")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  Overlay error (pomijam): {err}")
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
        int_peaks = [tk - trim_start for (tk, _) in (peaks or []) if (tk - trim_start) < peak_moment - 0.1]
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

    caption_items = []
    for (t_abs, label) in peaks:
        t_raw = t_abs - trim_start
        t_in_clip = _adjust_t(t_raw)
        if t_in_clip < 0 or t_in_clip > video_duration:
            continue

        style = KILL_STYLES.get(label, {"size": 90, "color": "white", "duration": 2.0})
        # Offset antycypacji 0.6s: synchronizacja z momentem animacji ciosu/zgonu w grze
        t_start = max(0.0, t_in_clip - 0.6)
        t_end   = min(video_duration, t_start + style["duration"])

        clean_label = re.sub(r'[^\x00-\x7F]+', '', label).strip()
        clean_label = clean_label.replace("'", "\\\\\'")

        caption_items.append({
            "start": t_start,
            "end": t_end,
            "label": clean_label,
            "style": style
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
        if total_kills >= 2:
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
        print(f"   🗨️  {clean_label} (kill {idx+1}/{total_kills}) @ {t_in_clip:.1f}s — {style['size']}px")

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
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:600]
        print(f"⚠️  Dynamiczne napisy error: {err}")
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
    probe = subprocess.run([
        "ffprobe", "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_source
    ], capture_output=True, text=True)
    has_game_audio = probe.stdout.strip() == "audio"

    fade_start = max(0.0, video_duration - 1.5)

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
            # loudnorm najpierw → normalizacja poziomu bazowego
            # potem volume z eval=frame → dynamiczny boost nie jest kompensowany
            f"[2:a]loudnorm=I=-14:TP=-1.5:LRA=11,"
            f"volume=eval=frame:volume='{game_boost}',"
            f"afade=t=out:st={fade_start:.2f}:d=1.5[ga];"
            f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,"
            f"volume=eval=frame:volume='{music_duck}',"
            f"afade=t=out:st={fade_start:.2f}:d=1.5[ma];"
            f"[ga][ma]amix=inputs=2:duration=longest:dropout_transition=2[aout]"
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
        print(f"🎵 Miksuję dźwięk gry [{src_label}] ({int(GAME_AUDIO_VOLUME*100)}%) + muzykę ({int(MUSIC_VOLUME*100)}%) przez amix")
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
            # loudnorm PRZED fade
            "-af", f"volume={MUSIC_VOLUME},loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=out:st={fade_start:.2f}:d=1.5",
            "-t", f"{video_duration:.3f}",
            "-shortest",
            output_path
        ]
        print(f"🎵 Tylko muzyka ({int(MUSIC_VOLUME*100)}%) — brak dźwięku gry w źródle")

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"Merge error: {r.stderr.decode('utf-8', errors='replace')[:600]}")
    print("✅ Audio nałożone i zsynchronizowane")
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
        f":fontsize=55"
        f":fontcolor=white"
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
    print(f"🔔 CTA overlay: '{clean_cta}' @ ostatnie {show_duration:.1f}s")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        err = r.stderr.decode('utf-8', errors='replace')[:400]
        print(f"⚠️  CTA overlay error (pomijam): {err}")
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

    t = lambda name: os.path.join(LOL_TEMP_DIR, name)
    step1        = t("01_cut.mp4")
    step4        = t("04_processed.mp4")
    step5_music  = t("05_music.mp4")
    step5_cta    = t("06_cta.mp4")
    step5        = os.path.join(LOL_TEMP_DIR, output_filename)

    # ── KROK 1: Wycięcie fragmentu / segmentów ────────────────────────────────
    print("\n[1/4] Wycinanie fragmentu...")

    # Dla SOLO BOLO wykluczamy jakiekolwiek cięcia jump-cut — cała walka ma być płynna od wejścia do finału
    if action_type.lower() in ("solo_bolo", "solo", "1v1"):
        combat_segments = None

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
        r = subprocess.run(concat_cmd, capture_output=True)
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
        cut_clip(source_path, clip_start, clip_end, step1)
        # Remapuj peaks do czasu lokalnego step1 (0.0 -> clip_duration)
        if peaks:
            peaks = [(round(t_k - clip_start, 3), lbl) for (t_k, lbl) in peaks]
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
    _zoom_level   = float(tuning_p.get("zoom_aggression", 1.20))
    _slowmo_dur   = float(tuning_p.get("slowmo_duration", 1.4))
    _music_vol    = float(tuning_p.get("music_balance", 0.85))
    _game_vol     = float(tuning_p.get("game_sound_balance", 0.65))
    _slowmo_speed = 0.50

    print(f"   ⚙️  Profil montażu ({tuning_p.get('id', 'default')}): zoom={_zoom_level:.2f}x, slowmo={_slowmo_dur:.1f}s, muzyka={int(_music_vol*100)}%, gra={int(_game_vol*100)}%")

    # Intermediate peaks: wszystkie kille PRZED ostatnim (PENTA) -> mini slow-mo 0.8x/0.5s
    _all_kill_rel = sorted([t_k - clip_start for (t_k, _) in (peaks or [])])
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
        zoom_duration=0.8,
        slowmo_speed=_slowmo_speed if use_speed_ramp else 1.0,
        slowmo_duration=_slowmo_dur,
        intermediate_peaks=_inter_peaks if use_speed_ramp else []
    )

    # KROK 4: Muzyka dopasowana do akcji z beat-sync
    print("\n[4/7] Muzyka i synchronizacja beat-sync + miksowanie audio gry...")
    music = pick_music_for_action(action_type, preferred_track=preferred_track or ("ncs_egzod_royalty.mp3" if action_type == "pentakill" else None))
    # Przekazuj step1 (surowy wycinek z audio gry) jako game_audio_path
    # step4 nie ma audio (apply_editor_effects mapuje tylko [v_final])
    merge_music(step4, music, step5_music, final_duration, peak_moment,
                game_audio_path=step1, kill_peaks=peaks or [],
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
        from lol_config import ACTION_LABELS
        _hook = ACTION_LABELS.get(action_type, "").replace("🔥","").replace("⚡","").replace("💥","").replace("🎯","").replace("👑","").strip()
    print(f"\n[6/7] Hook overlay: '{_hook}' @ pierwsze 2s...")
    hook_show_start = 0.5   # zawsze pierwsze sekundy — to jest przynęta dla widza
    add_text_overlay(step5_captions, _hook, hook_show_start, final_duration, step5_cta)

    # KROK 7: CTA overlay (ostatnie 1.5s) — klasyczne wezwanie do subskrypcji
    _end_cta = "LEAVE A LIKE & SUBSCRIBE FOR MORE!"
    print(f"\n[7/7] CTA overlay: '{_end_cta}'...")
    add_cta_overlay(step5_cta, final_duration, step5, cta_text=_end_cta, show_duration=1.5)

    # ── POST-RENDER 15s SNAP ─────────────────────────────────────────────────
    # Stosuj TYLKO dla pojedynczych wymian/akcji (15.5-18.0s), NIGDY nie niszcz multi-killów ani nie ucinaj pierwszego fraga!
    is_multikill = action_type in ("pentakill", "quadrakill") or (peaks and len(peaks) >= 3)
    is_solo_fight = action_type.lower() in ("solo_bolo", "solo", "1v1")
    if 15.5 <= final_duration <= 18.0 and not is_multikill and not is_solo_fight:
        trim_from_start = final_duration - 15.0
        first_peak_rel = min((t_k for (t_k, _) in (peaks or [])), default=999.0)
        # Przytnij tylko jeśli pierwszy kill jest bezpiecznie po punkcie cięcia
        if first_peak_rel > trim_from_start + 1.0:
            step5_15s = step5.replace(".mp4", "_15s.mp4")
            cmd_15s = [
                "ffmpeg", "-y",
                "-i", step5,
                "-ss", f"{trim_from_start:.3f}",
                "-t", "15.0",
                "-c", "copy",
                step5_15s
            ]
            r15 = subprocess.run(cmd_15s, capture_output=True)
            if r15.returncode == 0:
                import shutil as _sh15
                _sh15.move(step5_15s, step5)
                final_duration = 15.0
                print(f"   ⚡ 15s SNAP zastosowany: przycięto -{trim_from_start:.2f}s od początku → 15.0s")
            else:
                print(f"   ⚠️  15s SNAP błąd (pomijam): {r15.stderr.decode('utf-8', errors='replace')[:200]}")
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
