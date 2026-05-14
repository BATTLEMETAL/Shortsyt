"""
pw_watermark_rebrand.py
========================
Wykrywa floating watermark TikTok w każdej klatce (OpenCV),
bluruje go i nakłada "@salonprettywoman" w tym samym miejscu.

Algorytm:
  1. Próbkuj klatki co 0.3s
  2. Szukaj białego tekstu "TikTok" + logo (jasne piksele w określonej strefie)
  3. Zbierz listę pozycji watermarku z timestampami
  4. Wygeneruj ffmpeg complex_filter z per-segment boxblur + drawtext
  5. Renderuj finalny film

Użycie:
  python pw_watermark_rebrand.py                   # przetwórz 2 filmy
  python pw_watermark_rebrand.py --test            # test na 1 filmie
  python pw_watermark_rebrand.py --debug-frames    # zapisz klatki z wykryciem
"""
import os, sys, json, re, shutil, subprocess, argparse, math
sys.stdout.reconfigure(encoding="utf-8")

import cv2
import numpy as np

INPUT_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman"
OUTPUT_FOLDER = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\gotowe"
TEMP_DIR      = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\pw_temp"
DEBUG_DIR     = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\pw_debug"
LIMIT         = 10

BRAND_TEXT    = "@salonprettywoman"
FONT_FILE     = "C\\:/Windows/Fonts/arialbd.ttf"
FONT_SIZE     = 22

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)


# ── Pomocnicze ───────────────────────────────────────────────────────────────
def get_video_info(path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,duration,r_frame_rate",
         "-of", "json", path],
        capture_output=True, text=True, timeout=15
    )
    try:
        s = json.loads(r.stdout)["streams"][0]
        fps_parts = s.get("r_frame_rate", "30/1").split("/")
        fps = float(fps_parts[0]) / float(fps_parts[1])
        return {
            "w": int(s["width"]),
            "h": int(s["height"]),
            "duration": float(s.get("duration", 30)),
            "fps": fps,
        }
    except Exception:
        return {"w": 576, "h": 1024, "duration": 30, "fps": 30}


# ── Wykrywanie watermarku TikTok ─────────────────────────────────────────────
def detect_tiktok_watermark_region(frame: np.ndarray, w: int, h: int) -> tuple | None:
    """
    Szuka watermarku TikTok w klatce.

    TikTok watermark charakterystyki:
    - Biały tekst + logo na ciemnym tle LUB na jasnym tle z cieniem
    - Rozmiar ~180x65px dla 576x1024 (~31% x ~6% wymiarów)
    - Pozycja: środkowa zona (y: 20%-80% wysokości, x: 0%-100% szerokości)
    - Zawiera jaśniejszy region (białe piksele logo + tekst)

    Zwraca: (x, y, w_wm, h_wm) lub None
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Strefa poszukiwań: środkowe 20-85% wysokości (poza edgesem UI)
    search_y1 = int(h * 0.15)
    search_y2 = int(h * 0.90)
    search_x1 = 0
    search_x2 = w

    zone = gray[search_y1:search_y2, search_x1:search_x2]

    # Watermark TikTok = białe piksele (>200 jasność) zgrupowane w prostokąt
    # Threshold: piksele jaśniejsze niż 200
    _, bright_mask = cv2.threshold(zone, 200, 255, cv2.THRESH_BINARY)

    # Morfologia: łącz pobliskie białe regiony
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 8))
    dilated = cv2.dilate(bright_mask, kernel, iterations=2)
    eroded  = cv2.erode(dilated, kernel, iterations=1)

    # Znajdź kontury
    contours, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_candidate = None
    best_score = 0

    # Oczekiwane wymiary watermarku TikTok (proporcjonalnie)
    wm_w_min = int(w * 0.20)  # min 20% szerokości
    wm_w_max = int(w * 0.60)  # max 60% szerokości
    wm_h_min = int(h * 0.04)  # min 4% wysokości
    wm_h_max = int(h * 0.10)  # max 10% wysokości

    for cnt in contours:
        rx, ry, rw, rh = cv2.boundingRect(cnt)

        # Filtruj po rozmiarze
        if not (wm_w_min <= rw <= wm_w_max and wm_h_min <= rh <= wm_h_max):
            continue

        # Density score: ile białych pikseli w regionie
        region = bright_mask[ry:ry+rh, rx:rx+rw]
        density = np.sum(region > 0) / (rw * rh)

        # TikTok watermark ma density 15-60% (nie jest pełnym białym blokiem)
        if not (0.10 <= density <= 0.70):
            continue

        score = rw * rh * density

        if score > best_score:
            best_score = score
            # Przesuń do absolutnych współrzędnych
            abs_x = search_x1 + rx
            abs_y = search_y1 + ry

            # Dodaj 15px margines wokół
            pad = 15
            best_candidate = (
                max(0, abs_x - pad),
                max(0, abs_y - pad),
                min(w, rw + pad * 2),
                min(h - abs_y + pad, rh + pad * 2),
            )

    return best_candidate


# ── Analiza całego wideo ──────────────────────────────────────────────────────
def analyze_watermark_positions(video_path: str, info: dict,
                                 sample_interval: float = 0.3,
                                 debug: bool = False) -> list:
    """
    Próbkuje wideo i zwraca listę pozycji watermarku:
    [(timestamp, x, y, w, h), ...]
    """
    positions = []
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"    ❌ Nie można otworzyć: {video_path}")
        return []

    duration = info["duration"]
    fps      = info["fps"]
    w, h     = info["w"], info["h"]

    t = 0.0
    frame_count = 0

    while t < duration:
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        result = detect_tiktok_watermark_region(frame, w, h)

        if result:
            rx, ry, rw, rh = result
            positions.append((round(t, 2), rx, ry, rw, rh))

            if debug:
                # Rysuj prostokąt na klatce debug
                dbg = frame.copy()
                cv2.rectangle(dbg, (rx, ry), (rx+rw, ry+rh), (0, 0, 255), 2)
                cv2.putText(dbg, f"WM t={t:.1f}", (rx, ry-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
                dbg_path = os.path.join(DEBUG_DIR, f"frame_{frame_count:04d}_t{t:.1f}.jpg")
                cv2.imwrite(dbg_path, dbg)

        t += sample_interval
        frame_count += 1

    cap.release()
    print(f"    📍 Wykryto watermark w {len(positions)}/{frame_count} klatkach")
    return positions


# ── Grupuj pozycje w segmenty czasowe ────────────────────────────────────────
def group_positions_to_segments(positions: list, max_gap: float = 0.6) -> list:
    """
    Łączy bliskie pozycje w segmenty:
    [(t_start, t_end, x, y, w, h), ...]
    """
    if not positions:
        return []

    segments = []
    seg_start = positions[0][0]
    seg_pos   = positions[0][1:]  # x, y, w, h
    seg_xs = [positions[0][1]]
    seg_ys = [positions[0][2]]
    seg_ws = [positions[0][3]]
    seg_hs = [positions[0][4]]
    prev_t = positions[0][0]

    for pos in positions[1:]:
        t, x, y, pw, ph = pos
        gap = t - prev_t

        if gap > max_gap:
            # Zakończ bieżący segment
            segments.append((
                seg_start, prev_t,
                int(np.median(seg_xs)), int(np.median(seg_ys)),
                int(np.max(seg_ws)), int(np.max(seg_hs)),
            ))
            # Nowy segment
            seg_start = t
            seg_xs = [x]; seg_ys = [y]; seg_ws = [pw]; seg_hs = [ph]
        else:
            seg_xs.append(x); seg_ys.append(y)
            seg_ws.append(pw); seg_hs.append(ph)

        prev_t = t

    # Ostatni segment
    segments.append((
        seg_start, prev_t,
        int(np.median(seg_xs)), int(np.median(seg_ys)),
        int(np.max(seg_ws)), int(np.max(seg_hs)),
    ))

    return segments


# ── Buduj ffmpeg filter ───────────────────────────────────────────────────────
def build_ffmpeg_vf(segments: list, total_w: int, total_h: int,
                    out_w: int = 1080, out_h: int = 1920,
                    crop_top_frac: float = 0.045,
                    crop_bot_frac: float = 0.04) -> str:
    """
    Buduje kompletny ffmpeg -vf filtr z:
    1. Crop (usunięcie CapCut logo)
    2. Scale do 1080x1920
    3. Beauty grading
    4. Per-segment blur w miejscu watermarku
    5. Per-segment @salonprettywoman text
    6. Brand bar na dole
    """
    crop_top = int(total_h * crop_top_frac)
    crop_bot = int(total_h * crop_bot_frac)
    new_h    = total_h - crop_top - crop_bot

    # Skala: jak piksele TikTok mapują się na 1080x1920
    scale_x = out_w / total_w
    scale_y = out_h / new_h

    parts = [
        # 1. Crop CapCut logo
        f"crop={total_w}:{new_h}:0:{crop_top}",
        # 2. Scale
        f"scale={out_w}:{out_h}:flags=lanczos",
        "setsar=1:1",
        # 3. Beauty grading
        "curves=r='0/0 0.25/0.28 0.75/0.80 1/1':"
        "g='0/0 0.25/0.25 0.75/0.76 1/0.97':"
        "b='0/0 0.25/0.22 0.75/0.70 1/0.88'",
        "hue=s=1.08",
        "eq=contrast=1.06:brightness=0.015",
        "unsharp=3:3:0.6:3:3:0.0",
    ]

    bar_h = 120
    bar_y = out_h - bar_h

    # 4. Per-segment watermark blur + rebrand
    for t_start, t_end, wx, wy, ww, wh in segments:
        # Przelicz z TikTok 576x1024 → skalowane 1080x1920
        # (po cropie góry, więc wy musi być przesunięte o crop_top)
        sx = max(0, int((wx) * scale_x))
        sy = max(0, int((wy - crop_top) * scale_y))
        sw = min(out_w - sx, int(ww * scale_x))
        sh = min(out_h - sy, int(wh * scale_y))

        if sw <= 0 or sh <= 0:
            continue

        t_cond = f"between(t,{t_start:.2f},{t_end + 0.3:.2f})"

        # Blur całego regionu watermarku
        # Technika: split → crop watermark region → blur → overlay z powrotem
        # Uproszczona wersja przez boxblur z enable:
        parts.append(
            f"boxblur=luma_radius=18:luma_power=3"
            f":chroma_radius=18:chroma_power=3"
            f":enable='{t_cond}'"
        )

        # Nakładamy nasz tekst w miejscu watermarku
        text_y = sy + max(0, (sh - FONT_SIZE) // 2)
        parts.append(
            f"drawtext=text='{BRAND_TEXT}'"
            f":fontfile='{FONT_FILE}'"
            f":fontsize={FONT_SIZE}"
            f":fontcolor=white"
            f":x={sx}"
            f":y={text_y}"
            f":shadowcolor=black:shadowx=1:shadowy=1"
            f":enable='{t_cond}'"
        )

    # 5. Brand bar na dole (stały)
    parts.append(f"drawbox=x=0:y={bar_y}:w={out_w}:h={bar_h}:color=0x1a1a2e@0.82:t=fill")
    parts.append(f"drawbox=x=0:y={bar_y}:w={out_w}:h=3:color=0xFF69B4@0.95:t=fill")
    parts.append(
        f"drawtext=text='SALON PRETTY WOMAN  |  SWIDNICA'"
        f":fontfile='{FONT_FILE}'"
        f":fontsize=34"
        f":fontcolor=white"
        f":x=(w-text_w)/2"
        f":y={bar_y + (bar_h - 34) // 2 + 5}"
        f":shadowcolor=black:shadowx=1:shadowy=1"
    )

    return ",".join(parts)


# ── Główna funkcja przetwarzania ──────────────────────────────────────────────
def process_video(entry_path: str, out_path: str, idx: int,
                  debug: bool = False) -> bool:
    tmp_src = os.path.join(TEMP_DIR, f"src_{idx:02d}.mp4")
    tmp_out = os.path.join(TEMP_DIR, f"out_{idx:02d}.mp4")

    # Kopiuj z long-path fix
    try:
        lp = "\\\\?\\" + os.path.abspath(entry_path)
        with open(lp, "rb") as fi, open(tmp_src, "wb") as fo:
            shutil.copyfileobj(fi, fo)
    except Exception as e:
        print(f"    ❌ Copy error: {e}")
        return False

    info = get_video_info(tmp_src)
    print(f"    Wymiary: {info['w']}x{info['h']} | {info['duration']:.1f}s | {info['fps']:.0f}fps")

    # Analiza watermarku
    print(f"    🔍 Analizuję pozycje watermarku...")
    positions = analyze_watermark_positions(tmp_src, info, debug=debug)

    if not positions:
        print(f"    ⚠️  Watermark nie wykryty — stosuję tylko beauty grading + brand bar")
        segments = []
    else:
        segments = group_positions_to_segments(positions)
        print(f"    📋 Segmenty watermarku ({len(segments)}):")
        for seg in segments:
            print(f"       t={seg[0]:.1f}-{seg[1]:.1f}s @ x={seg[2]} y={seg[3]} {seg[4]}x{seg[5]}px")

    # Buduj filtr
    vf = build_ffmpeg_vf(segments, info["w"], info["h"])

    # Render do temp (ASCII path)
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", tmp_src,
        "-vf", vf,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", "-r", "30",
        tmp_out
    ]
    print(f"    ⚙️  Renderuję...")
    r = subprocess.run(cmd, capture_output=True, timeout=600)

    if r.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 50_000:
        shutil.copy2(tmp_out, out_path)
        mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"    ✅ GOTOWE: {os.path.basename(out_path)} ({mb:.1f}MB)")
        for f in [tmp_src, tmp_out]:
            try: os.remove(f)
            except: pass
        return True

    err = r.stderr.decode("utf-8", errors="ignore")[-500:] if r.stderr else ""
    print(f"    ❌ ffmpeg error: {err}")
    return False


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",         action="store_true", help="Tylko 1 film")
    parser.add_argument("--debug-frames", action="store_true", help="Zapisz klatki debug")
    args = parser.parse_args()

    print("=" * 62)
    print("  🌸 PRETTYWOMAN — Watermark Detection + Rebrand")
    print("=" * 62)

    videos = [e for e in os.scandir(INPUT_FOLDER)
              if e.is_file() and e.name.lower().endswith(".mp4")]
    limit  = 1 if args.test else LIMIT
    videos = videos[:limit]
    print(f"  Filmów do przetworzenia: {len(videos)}")

    for idx, entry in enumerate(videos, 1):
        slug = re.sub(r'[^\w]+', '_', entry.name)[:40]
        out  = os.path.join(OUTPUT_FOLDER, f"pw_rb_{idx:02d}_{slug}.mp4")

        if os.path.exists(out) and os.path.getsize(out) > 50_000:
            print(f"\n[{idx}] ⏭️  Już istnieje")
            continue

        print(f"\n[{idx}/{len(videos)}] {entry.name[:60]}")
        process_video(entry.path, out, idx, debug=args.debug_frames)

    print(f"\n{'='*62}")
    print(f"✅ Gotowe filmy: {OUTPUT_FOLDER}")
    if args.debug_frames:
        print(f"🔍 Debug frames: {DEBUG_DIR}")


if __name__ == "__main__":
    main()
