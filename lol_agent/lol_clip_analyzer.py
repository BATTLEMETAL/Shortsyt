"""
LOL Agent — Clip Analyzer v3
Łączy dwa źródła informacji:
  1. lol_momentum_analyzer  → OCR kill detection, timing, trim window (PENTA = ostatni kill)
  2. Gemini Vision          → identyfikacja championa z klatek ekranu

API wymagane przez run_lol_agent.py:
  analyze_clip(path)  -> dict z peak_start, peak_end, action_type, peaks, main_peak_in_clip
  scan_input_folder() -> str | None
  archive_clip(path)  -> None
"""
import os
import sys
import json
import base64
import subprocess
import shutil
import tempfile

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from google import genai
    GENAI_OK = True
except ImportError:
    GENAI_OK = False

from lol_config import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS,
    LOL_INPUT_DIR, LOL_ARCHIVE_DIR, SHORT_MAX_DURATION
)

KNOWN_ACTIONS = [
    "pentakill", "quadrakill", "triple", "double",
    "outplay", "clutch", "escape", "oneshot", "baron", "dragon"
]

# LoL kill sequence: label detected by OCR → action_type
KILL_LABEL_TO_ACTION = {
    "PENTAKILL":    "pentakill",
    "QUADRAKILL":   "quadrakill",
    "TRIPLE KILL":  "triple",
    "DOUBLE KILL":  "double",
    "LEGENDARY":    "outplay",
    "GODLIKE":      "outplay",
    "UNSTOPPABLE":  "outplay",
    "KILLING SPREE":"outplay",
}

POPULAR_CHAMPIONS = [
    "Katarina", "Yone", "Yasuo", "Jinx", "Zed", "Ahri", "Lee Sin",
    "Thresh", "Vayne", "Master Yi", "Lux", "Akali", "Ezreal", "Caitlyn",
    "Sylas", "Fizz", "Rengar", "Irelia", "Viego", "Kaisa", "Varus",
    "Draven", "Jhin", "Nasus", "Darius", "Garen", "Pantheon",
]


# ─── Gemini Vision (champion detection only) ──────────────────────────────────

def _extract_frames_for_vision(video_path: str, n: int = 4) -> list:
    """Wyciaga n klatek ze srodka klipu (omijaj HUD-heavy poczatek/koniec)."""
    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ], capture_output=True, text=True)
    try:
        duration = float(r.stdout.strip())
    except Exception:
        duration = 20.0

    tmpdir = tempfile.mkdtemp(prefix="lol_vis_")
    frames = []
    for i in range(n):
        # Uzywaj klatek ze srodka (20%-80% czasu) — lepszy HUD widoczny
        t = duration * (0.2 + 0.6 * (i + 0.5) / n)
        out = os.path.join(tmpdir, f"f{i:02d}.jpg")
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", f"{t:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-vf", "scale=1280:-1",  # 640 było za małe — portrety HUD nieczytelne dla Gemini
            "-q:v", "4",
            out
        ], capture_output=True)
        if os.path.exists(out):
            frames.append((t, out))
    return frames, tmpdir


def _detect_champion_vision(video_path: str) -> str:
    """
    Uzywaj Gemini Vision TYLKO do wykrycia championa.
    Timing i kill detection -> momentum analyzer (OCR jest pewniejszy).
    Zwraca: nazwa championa lub "" jesli nie wykryto.
    """
    if not GENAI_OK or not GEMINI_API_KEY:
        return ""

    frames, tmpdir = _extract_frames_for_vision(video_path, n=4)
    if not frames:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return ""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        from lol_config import CHAMPION_WHITELIST
        whitelist_str = ", ".join(CHAMPION_WHITELIST)
        parts = [{
            "text": (
                "Look at these League of Legends gameplay screenshots.\n"
                "Identify the champion BEING PLAYED — NOT enemies.\n"
                "Clues: bottom-center HUD shows the player's champion portrait and ability icons.\n"
                "Also look for the player's nameplate above a champion.\n\n"
                f"The champion MUST be one of: {whitelist_str}.\n"
                "Respond ONLY with the champion name from the list above, or 'Unknown' if unsure.\n"
                "No other text."
            )
        }]

        for i, (t, path) in enumerate(frames):
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})

        models_to_try = GEMINI_FALLBACK_MODELS if "GEMINI_FALLBACK_MODELS" in globals() else [GEMINI_MODEL]
        champion = ""
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[{"role": "user", "parts": parts}]
                )
                raw_champ = response.text.strip().split("\n")[0].strip()
                import re as _re
                raw_champ = _re.sub(r'[*_`#]', '', raw_champ).strip()
                raw_champ = raw_champ.split('(')[0].split(',')[0].strip()
                if raw_champ.lower() == "unknown" or len(raw_champ) > 25 or len(raw_champ) < 2:
                    continue
                try:
                    from lol_config import CHAMPION_WHITELIST
                    wl_lower = [c.lower() for c in CHAMPION_WHITELIST]
                    if raw_champ.lower() not in wl_lower:
                        print(f"[VISION] {raw_champ} poza CHAMPION_WHITELIST — ignoruję")
                        continue
                    champion = CHAMPION_WHITELIST[wl_lower.index(raw_champ.lower())]
                    print(f"[VISION] Champion wykryty ({model_name}): {champion}")
                    return champion
                except Exception:
                    champion = raw_champ
                    return champion
            except Exception as _me:
                print(f"[VISION] Model {model_name} error: {_me}")
                continue
        return ""


    except Exception as e:
        print(f"[VISION] Error: {e}")
        return ""
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── Momentum analyzer integration ────────────────────────────────────────────

def _run_momentum_analyzer(video_path: str) -> dict:
    """
    Wywoluje lol_momentum_analyzer.analyze_momentum() i konwertuje wynik
    na slownik zgodny z run_lol_agent.py API.

    Klucz fix: main_peak_in_clip = OSTATNI kill (PENTA), nie pierwszy.
    Ta logika jest juz w momentum_analyzer po naszej poprawce (kills[-1][0]).
    """
    try:
        from lol_momentum_analyzer import analyze_momentum
        result = analyze_momentum(video_path, use_ocr=True, save_chart=True)

        # Typ akcji: z najwyzszego detected killa
        action_type = "outplay"
        if result.peaks:
            # Najwyzszy kill w sekwencji = ostatni = PENTA
            last_label = result.peaks[-1][1]
            action_type = KILL_LABEL_TO_ACTION.get(last_label, "outplay")

        return {
            "action_type":       action_type,
            "action_label":      action_type.upper().replace("_", " "),
            "peak_start":        result.trim_start,
            "peak_end":          result.trim_end,
            "clip_duration":     result.trim_end - result.trim_start,
            "main_peak_in_clip": result.main_peak_in_clip,  # PENTA time po fix
            "peaks":             result.peaks,
            "kill_count":        len(result.peaks),
            "kill_detected":     result.kill_detected,
            "confidence":        "high" if result.kill_detected else "low",
            "champion":          "",  # uzupelni Gemini Vision
        }

    except Exception as e:
        print(f"[ANALYZER] Momentum analyzer error: {e}")
        return None


def _filename_fallback(video_path: str) -> dict:
    """Ostatnia deska ratunku gdy wszystko zawiedzie."""
    fname = os.path.basename(video_path).lower()
    action = next((a for a in KNOWN_ACTIONS if a in fname), "outplay")
    champion = next(
        (c for c in [c.lower() for c in POPULAR_CHAMPIONS] if c in fname), ""
    )
    if champion:
        champion = champion.capitalize()

    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ], capture_output=True, text=True)
    try:
        duration = float(r.stdout.strip())
    except Exception:
        duration = 30.0

    return {
        "action_type":       action,
        "action_label":      action.upper(),
        "peak_start":        0.0,
        "peak_end":          min(duration, SHORT_MAX_DURATION),
        "clip_duration":     min(duration, SHORT_MAX_DURATION),
        "main_peak_in_clip": min(duration, SHORT_MAX_DURATION) * 0.65,
        "peaks":             [],
        "kill_count":        0,
        "kill_detected":     False,
        "confidence":        "low",
        "champion":          champion,
    }



# ─── Trim quiet start ("z buta") ─────────────────────────────────────────────

def trim_quiet_start(video_path: str,
                     scan_duration: float = 8.0,
                     pre_action_buffer: float = 0.5) -> float:
    """
    Skanuje poczatek klipu i szuka SKOKU aktywnosci powyzej baseline.
    Zwraca punkt startu = max(0, first_spike_time - pre_action_buffer).

    Cel: clip zaczyna sie NATYCHMIAST od akcji ("z buta").
    Algorytm YT Shorts promuje filmy ktore maja akcje juz w klatce 1.

    W LoL gra zawsze ma JAKIS ruch (kamera, animacje).
    Szukamy SKOKU ruchu wzgledem baseline (pierwsze 2 klatki) = walka/zabicie.
    Prog: spike_threshold = 2.5x baseline.

    Zwraca: float - punkt startu (0.0 jesli akcja od razu lub nie znaleziono)
    """
    import numpy as np
    from PIL import Image

    # Wyciagnij 18 mini-klatek z pierwszych scan_duration sekund
    n_frames = 18
    interval = scan_duration / n_frames
    frames_data = []

    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n_frames + 1):
            t = i * interval
            out = os.path.join(tmp, f"sq_{i:02d}.jpg")
            r = subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(t), "-i", video_path,
                "-vframes", "1",
                "-vf", "scale=192:108",
                out
            ], capture_output=True)
            if r.returncode == 0 and os.path.exists(out):
                try:
                    img = np.array(Image.open(out).convert("RGB"), dtype=np.float32)
                    frames_data.append((t, img))
                except Exception:
                    pass

    if len(frames_data) < 4:
        return 0.0

    # Policz ruch miedzy kolejnymi klatkami (play area: 8%..85% height)
    h = frames_data[0][1].shape[0]
    top_cut = int(h * 0.08)
    bot_cut = int(h * 0.85)

    motion_scores = []
    for i in range(len(frames_data) - 1):
        t_mid = (frames_data[i][0] + frames_data[i+1][0]) / 2
        f1 = frames_data[i][1][top_cut:bot_cut, :]
        f2 = frames_data[i+1][1][top_cut:bot_cut, :]
        score = float(np.abs(f2 - f1).mean())
        motion_scores.append((t_mid, score))

    if len(motion_scores) < 3:
        return 0.0

    # Baseline: mediana pierwszych 3 segmentow (spokojny start gry)
    baseline = float(np.median([s for _, s in motion_scores[:3]]))
    if baseline < 0.5:
        baseline = 0.5  # unikaj dzielenia przez prawie-zero

    # Prog: 2.5x baseline — wyrazna walka/zabicie/VFX flash
    spike_threshold = baseline * 2.5

    # Znajdz pierwsze przekroczenie progu (po pierwszych 2 segmentach — pomijaj samo otwarcie klipu)
    first_active_t = None
    for t_mid, score in motion_scores[2:]:
        if score >= spike_threshold:
            first_active_t = t_mid
            break

    if first_active_t is None:
        return 0.0

    trim_start = max(0.0, first_active_t - pre_action_buffer)

    # Nie przycinaj jesli akcja zaczyna sie w 1. sekundzie
    if trim_start < 0.3:
        return 0.0

    print(f"   \u2702\ufe0f  trim_quiet_start: baseline={baseline:.1f} spike={spike_threshold:.1f} "
          f"-> akcja @ {first_active_t:.1f}s -> trim od {trim_start:.1f}s")
    return trim_start


def trim_quiet_end(video_path: str,
                   scan_back: float = 10.0,
                   post_action_buffer: float = 1.0) -> float:
    """
    Skanuje KONIEC klipu i szuka OSTATNIEGO momentu akcji (motion spike).
    Zwraca czas konca = last_spike_time + post_action_buffer.

    Cel: odetnij 'martwe' sekundy po ostatnim zabojstwie.
    Uzytkownik chce: max 1s po ostatnim fragu -> nie przedluzac niepotrzebnie.
    Prog: 2.0x baseline (lagodniejszy niz start - akcja moze gasnac stopniowo).
    """
    import numpy as np
    from PIL import Image

    r = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ], capture_output=True, text=True)
    try:
        total_duration = float(r.stdout.strip())
    except Exception:
        return -1.0

    scan_start = max(0.0, total_duration - scan_back)
    scan_len = total_duration - scan_start
    if scan_len < 2.0:
        return -1.0

    n_frames = 20
    interval = scan_len / n_frames
    frames_data = []

    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n_frames + 1):
            t = scan_start + i * interval
            if t > total_duration:
                break
            out = os.path.join(tmp, f"eq_{i:02d}.jpg")
            r2 = subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(t), "-i", video_path,
                "-vframes", "1",
                "-vf", "scale=192:108",
                out
            ], capture_output=True)
            if r2.returncode == 0 and os.path.exists(out):
                try:
                    img = np.array(Image.open(out).convert("RGB"), dtype=np.float32)
                    frames_data.append((t, img))
                except Exception:
                    pass

    if len(frames_data) < 4:
        return -1.0

    h = frames_data[0][1].shape[0]
    top_cut = int(h * 0.08)
    bot_cut = int(h * 0.85)

    motion_scores = []
    for i in range(len(frames_data) - 1):
        t_mid = (frames_data[i][0] + frames_data[i+1][0]) / 2
        f1 = frames_data[i][1][top_cut:bot_cut, :]
        f2 = frames_data[i+1][1][top_cut:bot_cut, :]
        score = float(np.abs(f2 - f1).mean())
        motion_scores.append((t_mid, score))

    if not motion_scores:
        return -1.0

    baseline = float(np.median([s for _, s in motion_scores]))
    if baseline < 0.5:
        baseline = 0.5

    spike_threshold = baseline * 2.0  # lagodniejszy prog niz start (2.0x vs 2.5x)

    # Znajdz OSTATNIE przekroczenie progu (szukamy od konca)
    last_active_t = None
    for t_mid, score in reversed(motion_scores):
        if score >= spike_threshold:
            last_active_t = t_mid
            break

    if last_active_t is None:
        return -1.0

    trim_end = min(total_duration, last_active_t + post_action_buffer)

    # Nie przycinaj jesli to prawie caly klip (ostatni frag w ostatniej sekundzie)
    if trim_end >= total_duration - 0.5:
        return -1.0

    # Nie przycinaj jesli odcinalibysmy mniej niz 1.5s (niepotrzebne)
    if total_duration - trim_end < 1.5:
        return -1.0

    print(f"   \u2702\ufe0f  trim_quiet_end: baseline={baseline:.1f} spike={spike_threshold:.1f} "
          f"-> ostatnia akcja @ {last_active_t:.1f}s -> koniec @ {trim_end:.1f}s "
          f"(saved {total_duration - trim_end:.1f}s)")
    return trim_end


# ─── Main API ─────────────────────────────────────────────────────────────────

def analyze_clip(video_path: str, champion: str = "") -> dict:
    """
    Pelna analiza klipu wideo:
    1. lol_momentum_analyzer → OCR kill detection (PENTA timing, kill peaks)
    2. Gemini Vision → champion detection z klatek HUD (tylko jesli champion nie jest podany)
    3. Fallback gdy oba zawodza

    Zwraca slownik zgodny z run_lol_agent.py:
      peak_start, peak_end, clip_duration, main_peak_in_clip,
      peaks, action_type, champion, kill_count, confidence
    """
    print(f"[ANALYZER] Analizuje: {os.path.basename(video_path)}")

    # 1. Momentum analyzer (primary — OCR kill detection)
    result = _run_momentum_analyzer(video_path)
    if result is None:
        print("[ANALYZER] Momentum analyzer failed — filename fallback")
        result = _filename_fallback(video_path)

    # 2. Champion detection przez Gemini Vision
    # Tylko jesli nie podany przez uzytkownika / CLI
    if champion:
        result["champion"] = champion
    elif not result.get("champion"):
        detected_champ = _detect_champion_vision(video_path)
        result["champion"] = detected_champ

    # 3. Trim quiet start + quiet END
    if result.get("peak_start", 0.0) == 0.0 and result.get("confidence") in ("low", None):
        quiet_trim = trim_quiet_start(video_path, scan_duration=8.0)
        if quiet_trim > 0.0:
            result["peak_start"] = quiet_trim
            orig_peak = result.get("main_peak_in_clip", 0.0)
            result["main_peak_in_clip"] = max(quiet_trim, orig_peak)

    # Trim dead seconds AFTER last kill (max 1s post-action)
    # Tylko gdy brak pewnej detekcji kills (pytesseract off)
    if result.get("confidence") in ("low", None):
        trim_end = trim_quiet_end(video_path, scan_back=10.0, post_action_buffer=1.0)
        if trim_end > 0.0:
            result["peak_end"]      = trim_end
            result["clip_duration"] = trim_end - result.get("peak_start", 0.0)
            # Przesuń main_peak jesli wypadal poza nowe okno
            if result.get("main_peak_in_clip", 0.0) > trim_end:
                result["main_peak_in_clip"] = trim_end * 0.7

    # 4. Log summary
    print(
        f"[ANALYZER] {result['champion'] or 'Unknown'} | "
        f"{result['action_type'].upper()} | "
        f"{result['kill_count']} kills | "
        f"peak@{result['main_peak_in_clip']:.1f}s | "
        f"[{result['confidence']}]"
    )

    return result


# ─── scan_input_folder / archive_clip ─────────────────────────────────────────

def scan_input_folder(input_dir: str = None) -> str:
    """Zwraca sciezke do najnowszego klipu w folderze wejsciowym (lub None)."""
    folder = input_dir or LOL_INPUT_DIR
    if not os.path.isdir(folder):
        return None
    exts = (".mp4", ".mov", ".mkv", ".avi", ".webm")
    clips = sorted(
        (f for f in os.listdir(folder) if f.lower().endswith(exts)),
        key=lambda f: os.path.getmtime(os.path.join(folder, f)),
        reverse=True
    )
    return os.path.join(folder, clips[0]) if clips else None


def archive_clip(video_path: str) -> None:
    """Przenosi plik do LOL_ARCHIVE_DIR po przetworzeniu."""
    os.makedirs(LOL_ARCHIVE_DIR, exist_ok=True)
    dst = os.path.join(LOL_ARCHIVE_DIR, os.path.basename(video_path))
    if not os.path.exists(dst):
        shutil.move(video_path, dst)
        print(f"[ARCHIVE] Moved -> {dst}")
    else:
        os.remove(video_path)
        print(f"[ARCHIVE] Removed duplicate: {os.path.basename(video_path)}")


# ─── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else (
        r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4"
    )
    result = analyze_clip(path)
    print()
    print("=== CLIP ANALYSIS ===")
    for k, v in result.items():
        if k == "peaks":
            print(f"  {k:<20}: {len(v)} peaks")
            for t, lbl in v:
                print(f"    {t:.1f}s  {lbl}")
        else:
            print(f"  {k:<20}: {v}")
