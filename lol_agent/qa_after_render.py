"""
LOL Agent — QA After Render
Jeden skrypt który po renderze sprawdza jakość:
  1. Kill timing OCR (tak/nie + timestamp) — na output MP4
  2. Peak velocity kamery (czy skacze)     — ze source MP4 lub z logów pipeline
  3. Cisza na początku (sekundy bez dźwięku) — na output MP4

Użycie:
  python lol_agent/qa_after_render.py <output.mp4> [<source.mp4>]

Przypadki:
  Tylko output  → velocity z logów pipeline (lol_agent/lol_temp/*.log)
  Output+source → velocity przez smart_camera standalone na source
"""

import os
import sys
import subprocess
import json
import cv2
import numpy as np

# ── Tesseract setup ────────────────────────────────────────────────────────────
try:
    import pytesseract
    for _p in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# ── Konfiguracja ───────────────────────────────────────────────────────────────
KILL_KEYWORDS = {
    "pentakill": "PENTAKILL",
    "penta kill": "PENTAKILL",
    "penta": "PENTAKILL",
    "quadra kill": "QUADRAKILL",
    "quadrakill": "QUADRAKILL",
    "triple kill": "TRIPLE KILL",
    "triple": "TRIPLE KILL",
    "double kill": "DOUBLE KILL",
    "double": "DOUBLE KILL",
}
KILL_REGION = (0.05, 0.30, 0.15, 0.85)   # (y_start%, y_end%, x_start%, x_end%)
OCR_EVERY_N = 6                            # co ile klatek robimy OCR
SILENCE_DB_THRESHOLD = -45.0              # dB — poniżej = cisza
MAX_SILENCE_WARN = 1.5                    # sekundy ciszy na początku → WARN
VELOCITY_WARN = 80                        # px/krok — powyżej → WARN (powinno być ≤60)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Kill timing OCR
# ══════════════════════════════════════════════════════════════════════════════
def _check_kill_text(frame: np.ndarray) -> tuple[float, str]:
    """Zwraca (bonus_score, label) jeśli w klatce jest kill text."""
    h, w = frame.shape[:2]
    y1 = int(KILL_REGION[0] * h)
    y2 = int(KILL_REGION[1] * h)
    x1 = int(KILL_REGION[2] * w)
    x2 = int(KILL_REGION[3] * w)
    roi = frame[y1:y2, x1:x2]

    # Izoluj złote/białe piksele (kill tekst LoL)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Złoty (PENTAKILL): H=20-35, S>100, V>150
    mask_gold = cv2.inRange(hsv, (15, 80, 130), (40, 255, 255))
    # Biały (DOUBLE/TRIPLE): S<40, V>200
    mask_white = cv2.inRange(hsv, (0, 0, 200), (180, 45, 255))
    mask = cv2.bitwise_or(mask_gold, mask_white)

    if cv2.countNonZero(mask) < 30:
        return 0.0, ""

    result = cv2.bitwise_and(roi, roi, mask=mask)
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    scale = 3
    thresh_big = cv2.resize(thresh, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_CUBIC)

    text = ""
    for psm in (7, 6):
        try:
            t = pytesseract.image_to_string(
                thresh_big,
                config=f"--psm {psm} --oem 1 "
                       f"-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ "
            ).strip().lower()
            if t:
                text = t
                break
        except Exception:
            continue

    for kw, label in KILL_KEYWORDS.items():
        if kw in text:
            return 1.0, label
    return 0.0, ""


def check_kill_timing(video_path: str) -> dict:
    """Skanuje output wideo pod kątem kill text OCR."""
    if not OCR_AVAILABLE:
        return {"ok": False, "reason": "pytesseract niedostepny", "kills": []}

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    kills = []
    frame_idx = 0
    last_kill_t = -5.0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % OCR_EVERY_N == 0:
            t = frame_idx / fps
            _, label = _check_kill_text(frame)
            if label and (t - last_kill_t) > 2.0:
                kills.append((round(t, 1), label))
                last_kill_t = t
        frame_idx += 1
    cap.release()

    return {
        "ok": len(kills) > 0,
        "kills": kills,
        "total_frames_scanned": frame_idx,
        "fps": fps,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Peak velocity kamery
# ══════════════════════════════════════════════════════════════════════════════
def _parse_velocity_from_log(output_path: str) -> dict | None:
    """
    Próbuje znaleźć dane velocity w logu pipeline.
    smart_camera.py drukuje: '+VelLimit=60px'
    oraz wartości tracków w logach.
    """
    log_candidates = [
        os.path.join(os.path.dirname(output_path), "pipeline.log"),
        os.path.join("lol_agent", "lol_temp", "pipeline.log"),
        "agent_run.log",
        "start_daily_run.log",
    ]
    for log_path in log_candidates:
        if not os.path.isfile(log_path):
            continue
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            # Szukaj linii smart_camera z VelLimit
            for line in text.splitlines():
                if "VelLimit" in line and "bar-detected" in line:
                    # Format: "(v9 Median+EMA a=0.65 +VelLimit=60px: 86/89 bar-detected)"
                    import re
                    m = re.search(r"VelLimit=(\d+)px.*?(\d+)/(\d+) bar-detected", line)
                    if m:
                        max_delta = int(m.group(1))
                        detected  = int(m.group(2))
                        total     = int(m.group(3))
                        pct = round(100 * detected / total) if total else 0
                        ok = max_delta <= VELOCITY_WARN and pct >= 80
                        return {
                            "source": "pipeline_log",
                            "ok": ok,
                            "max_delta_px": max_delta,
                            "bar_detection_pct": pct,
                            "detected_frames": detected,
                            "total_frames": total,
                            "threshold_px": VELOCITY_WARN,
                            "log_file": log_path,
                        }
        except Exception:
            continue
    return None


def check_camera_velocity_on_source(source_path: str) -> dict:
    """
    Uruchamia smart_camera.find_action_path() na source video
    i mierzy max skok między sąsiednimi punktami śledzenia.
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from smart_camera import find_action_path
        import cv2 as _cv2

        cap = _cv2.VideoCapture(source_path)
        fps = cap.get(_cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        source_w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        source_h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        points = find_action_path(source_path, 0.0, duration,
                                  source_w=source_w, source_h=source_h, crop_w=608)
        if not points or len(points) < 2:
            return {"ok": False, "reason": "brak punktów śledzenia"}

        deltas = [abs(points[i][1] - points[i-1][1]) for i in range(1, len(points))]
        peak_delta = max(deltas) if deltas else 0.0
        avg_delta  = float(np.mean(deltas)) if deltas else 0.0
        jumps = [
            (round(points[i][0], 2), round(deltas[i-1], 1))
            for i in range(1, len(points))
            if deltas[i-1] > VELOCITY_WARN
        ]
        return {
            "source": "smart_camera_standalone",
            "ok": peak_delta <= VELOCITY_WARN,
            "peak_velocity_px": round(peak_delta, 1),
            "avg_velocity_px":  round(avg_delta, 1),
            "jumps_over_threshold": jumps[:5],
            "threshold_px": VELOCITY_WARN,
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def check_camera_velocity(output_path: str, source_path: str = None) -> dict:
    """
    Router:
      source_path podany  → smart_camera standalone (najdokładniejszy)
      source_path brak    → parsuj logi pipeline
      logi brak           → informacja że brak danych
    Uwaga: NIE używamy optical flow / phase-corr na output wideo —
    minterpolate i zoom-punch generują fałszywe alarmy.
    """
    if source_path and os.path.isfile(source_path):
        return check_camera_velocity_on_source(source_path)

    # Spróbuj z logów pipeline
    from_log = _parse_velocity_from_log(output_path)
    if from_log:
        return from_log

    return {
        "ok": None,   # None = brak danych (nie FAIL)
        "reason": "Brak source video i brak logów pipeline. Dodaj source: python qa_after_render.py output.mp4 source.mp4",
        "threshold_px": VELOCITY_WARN,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. Cisza na początku
# ══════════════════════════════════════════════════════════════════════════════
def check_silence_at_start(video_path: str) -> dict:
    """Używa ffmpeg silencedetect do znalezienia ciszy na początku klipu."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={SILENCE_DB_THRESHOLD}dB:duration=0.3",
        "-f", "null", "-"
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = r.stderr

        silence_end = None
        for line in output.splitlines():
            if "silence_end" in line:
                try:
                    val = float(line.split("silence_end:")[1].split("|")[0].strip())
                    if silence_end is None:
                        silence_end = val  # pierwsza cisza = na początku
                    break
                except Exception:
                    pass

        silence_duration = silence_end if silence_end is not None else 0.0

        return {
            "ok": silence_duration <= MAX_SILENCE_WARN,
            "silence_at_start_s": round(silence_duration, 2),
            "threshold_s": MAX_SILENCE_WARN,
        }
    except Exception as e:
        return {"ok": False, "silence_at_start_s": -1, "reason": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# MAIN REPORT
# ══════════════════════════════════════════════════════════════════════════════
def run_qa(video_path: str, source_path: str = None) -> None:
    if not os.path.isfile(video_path):
        print(f"[QA] BLAD: plik nie istnieje: {video_path}")
        sys.exit(1)
    if source_path and not os.path.isfile(source_path):
        print(f"[QA] WARN: source nie istnieje: {source_path} -- pomijam velocity check ze zrodla")
        source_path = None

    fname = os.path.basename(video_path)
    size_mb = os.path.getsize(video_path) / 1_048_576

    print(f"\n{'='*60}")
    print(f"  LOL QA REPORT — {fname}")
    print(f"  Rozmiar: {size_mb:.1f} MB")
    print(f"{'='*60}")

    # 1. Kill timing
    print("\n[1/3] Kill timing OCR...")
    kill = check_kill_timing(video_path)
    if kill["ok"]:
        kills_str = ", ".join(f"{t}s:{lb}" for t, lb in kill["kills"])
        print(f"  OK  Kill wykryty: {kills_str}")
    else:
        reason = kill.get("reason", "brak kill text w video")
        print(f"  WARN Kill NIE wykryty ({reason})")
    print(f"       Przeskanowano {kill.get('total_frames_scanned',0)} klatek @ {kill.get('fps',0):.0f}fps")

    # 2. Kamera
    print("\n[2/3] Velocity kamery...")
    cam = check_camera_velocity(video_path, source_path)
    if cam.get("ok") is None:
        vel_status = "INFO"
    elif cam["ok"]:
        vel_status = "OK  "
    else:
        vel_status = "WARN"
    src_label = cam.get("source", "?")
    if "reason" in cam:
        print(f"  {vel_status} {cam['reason']}")
    elif src_label == "pipeline_log":
        pct = cam.get('bar_detection_pct', '?')
        md  = cam.get('max_delta_px', '?')
        print(f"  {vel_status} [z logu] MAX_DELTA={md}px | bar-detection={pct}% | log: {cam.get('log_file','')}")
    else:
        print(f"  {vel_status} [smart_cam] Peak={cam.get('peak_velocity_px','?')}px | avg={cam.get('avg_velocity_px','?')}px | threshold={cam['threshold_px']}px")
        if cam.get("jumps_over_threshold"):
            for jt, jv in cam["jumps_over_threshold"][:5]:
                print(f"       Skok {jv}px @ {jt}s")
        else:
            print(f"       Brak skokow powyzej progu")

    # 3. Cisza
    print("\n[3/3] Cisza na poczatku...")
    sil = check_silence_at_start(video_path)
    sil_status = "OK  " if sil["ok"] else "WARN"
    print(f"  {sil_status} Cisza: {sil['silence_at_start_s']}s (max OK: {sil['threshold_s']}s)")

    # Podsumowanie
    cam_ok = cam.get("ok")  # None = brak danych, nie liczy do FAIL
    all_ok = kill["ok"] and (cam_ok is None or cam_ok) and sil["ok"]
    print(f"\n{'='*60}")
    overall = "PASS" if all_ok else "WARN — sprawdz powyzej"
    print(f"  WYNIK: {overall}")
    print(f"{'='*60}\n")

    # Zapis JSON
    report = {
        "file": fname,
        "size_mb": round(size_mb, 1),
        "kill_timing": kill,
        "camera_velocity": cam,
        "silence": sil,
        "overall_pass": all_ok,
    }
    out_json = video_path.replace(".mp4", "_qa.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"  Raport JSON: {out_json}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uzycie: python lol_agent/qa_after_render.py <output.mp4> [<source.mp4>]")
        sys.exit(1)
    src = sys.argv[2] if len(sys.argv) > 2 else None
    run_qa(sys.argv[1], src)
