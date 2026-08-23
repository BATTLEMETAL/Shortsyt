"""
LOL Agent — Momentum Analyzer
Buduje krzywą momentum z 3 sygnałów wizualnych:
  1. Motion Score      — absdiff klatek (chaos walki)
  2. Kill Text OCR     — wykrywa złote napisy (DOUBLE, TRIPLE, PENTAKILL)
  3. VFX Intensity     — nasycenie kolorów w strefie walki (eksplozje, czary)

Wynik: momentum_curve[], peaks[], optymalne trim start/end
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field

try:
    import pytesseract
    # Tesseract path (Winget installs to Program Files)
    _TESS_CANDIDATES = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\mz100\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    ]
    for _p in _TESS_CANDIDATES:
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  pytesseract niedostępny — kill text detection wyłączony")

# ──────────────────────────────────────────────────────────────────────────────
# Konfiguracja
# ──────────────────────────────────────────────────────────────────────────────

# Region OCR: górna część ekranu (gdzie LoL wyświetla "DOUBLE KILL" itp.)
# Współrzędne jako ułamki wysokości/szerokości ekranu [y_start, y_end, x_start, x_end]
KILL_REGION = (0.05, 0.25, 0.20, 0.80)   # top center strip

# Próbkowanie klatek
SAMPLE_EVERY_N_FRAMES = 3   # co 3 klatki (~20fps próbek przy 60fps wideo)
OCR_EVERY_N_FRAMES    = 6   # OCR co 6 klatek (~10 próbek/s) — gwarantuje że złapie krótkie flashi tekstu

# Kill text keywords and weights (English LoL client only)
KILL_KEYWORDS: Dict[str, Tuple[int, str]] = {
    "pentakill":     (100, "PENTAKILL"),
    "penta kill":    (100, "PENTAKILL"),
    "penta":         (90,  "PENTAKILL"),
    "quadra kill":   (75,  "QUADRAKILL"),
    "quadrakill":    (75,  "QUADRAKILL"),
    "quadra":        (65,  "QUADRAKILL"),
    "triple kill":   (55,  "TRIPLE KILL"),
    "triple":        (50,  "TRIPLE KILL"),
    "double kill":   (35,  "DOUBLE KILL"),
    "double":        (30,  "DOUBLE KILL"),
    "killing spree": (20,  "KILLING SPREE"),
    "slaughter":     (25,  "KILLING SPREE"),
    "dominating":    (30,  "UNSTOPPABLE"),
    "unstoppable":   (40,  "UNSTOPPABLE"),
    "legendary":     (50,  "LEGENDARY"),
    "godlike":       (60,  "GODLIKE"),
}

# Wagi sygnałów w finalnej krzywej momentum
W_MOTION = 0.35
W_KILL   = 0.45
W_VFX    = 0.20

# Okno cięcia
BUILD_BEFORE_PEAK = 15.0  # s przed głównym peakiem (obejmuje wczesne fragi)
AFTER_PEAK        = 1.2   # s po głównym peaku (punchy, dynamiczny finisz bez przeciągania)
MAX_DURATION      = 30.0  # maks. długość shorta


@dataclass
class MomentumResult:
    """Wynik analizy momentum dla jednego klipu."""
    video_path: str
    duration: float

    # Krzywa momentum: lista (timestamp, score_0_100)
    curve: List[Tuple[float, float]] = field(default_factory=list)

    # Wykryte peaki: (timestamp, label) np. (16.2, "PENTAKILL")
    peaks: List[Tuple[float, str]] = field(default_factory=list)

    # Optymalne cięcie
    trim_start: float = 0.0
    trim_end: float   = 0.0

    # Moment głównego peaku względem trim_start (do sync muzyki)
    main_peak_in_clip: float = 0.0

    # Czy znaleziono kill text
    kill_detected: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Sygnał 1: Motion Score
# ──────────────────────────────────────────────────────────────────────────────

def _compute_motion_scores(cap: cv2.VideoCapture, fps: float) -> List[Tuple[float, float]]:
    """Frame-by-frame absdiff → motion score per timestamp."""
    scores = []
    prev_gray = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % SAMPLE_EVERY_N_FRAMES == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (15, 15), 0)
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                score = float(np.mean(diff))
                scores.append((frame_idx / fps, score))
            prev_gray = gray
        frame_idx += 1

    return scores


# ──────────────────────────────────────────────────────────────────────────────
# Sygnał 2: VFX Intensity (saturacja kolorów w strefie walki)
# ──────────────────────────────────────────────────────────────────────────────

def _compute_vfx_scores(cap: cv2.VideoCapture, fps: float,
                         frame_count: int) -> List[Tuple[float, float]]:
    """
    Mierzy nasycenie kolorów w centralnej strefie ekranu (gdzie toczą się walki).
    Wysokie nasycenie = eksplozje czarów, efekty wizualne walki.
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # reset
    scores = []
    frame_idx = 0

    # Strefa walki: centrum - dolna połowa (bez UI)
    # LoL: górny UI ~10%, dolny UI ~35%, reszta = gameplay
    y_start_frac, y_end_frac = 0.10, 0.65
    x_start_frac, x_end_frac = 0.10, 0.90

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % SAMPLE_EVERY_N_FRAMES == 0:
            h, w = frame.shape[:2]
            ys, ye = int(h * y_start_frac), int(h * y_end_frac)
            xs, xe = int(w * x_start_frac), int(w * x_end_frac)
            roi = frame[ys:ye, xs:xe]

            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            sat = hsv[:, :, 1].astype(float)

            # Obszar wysoce nasycony (efekty czarów, eksplozje)
            high_sat_mask = sat > 150
            if high_sat_mask.any():
                score = float(np.mean(sat[high_sat_mask]))
            else:
                score = 0.0

            scores.append((frame_idx / fps, score))
        frame_idx += 1

    return scores


# ──────────────────────────────────────────────────────────────────────────────
# Sygnał 3: Kill Text OCR
# ──────────────────────────────────────────────────────────────────────────────

def _detect_kill_text_ocr(frame: np.ndarray) -> Tuple[float, str]:
    """
    Uruchamia OCR na górnym regionie klatki.
    Zwraca (bonus_score, kill_label) lub (0.0, "").
    LoL kill text pojawia się jako złoty/kremowy tekst w centrum-góra ekranu.
    """
    h, w = frame.shape[:2]
    ys = int(h * KILL_REGION[0])
    ye = int(h * KILL_REGION[1])
    xs = int(w * KILL_REGION[2])
    xe = int(w * KILL_REGION[3])
    roi = frame[ys:ye, xs:xe]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # LoL kill text: złoty/kremowy (H=15-45, wysokie S i V)
    mask_gold  = cv2.inRange(hsv, (10,  80, 140), (45, 255, 255))
    # Biały/kremowy (niska saturacja, wysokie V) — część tekstu jest prawie biała
    mask_white = cv2.inRange(hsv, (0,   0,  200), (180, 60, 255))
    # Jasnożółty (niektore wersje LoL kill text)
    mask_ltyel = cv2.inRange(hsv, (20,  50, 200), (40, 180, 255))
    mask = cv2.bitwise_or(mask_gold, cv2.bitwise_or(mask_white, mask_ltyel))

    # Niski próg — nawet mało pikseli może być tekstem
    if cv2.countNonZero(mask) < 40:
        return 0.0, ""

    # Izoluj tekst i wzmocnij kontrast
    result = cv2.bitwise_and(roi, roi, mask=mask)
    gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)
    # Morphological dilation — połączy rozrzucone piksele liter
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    gray = cv2.dilate(gray, kernel, iterations=1)
    _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)

    # Scale up dla OCR (3x)
    scale = 3
    thresh_big = cv2.resize(thresh, None, fx=scale, fy=scale,
                            interpolation=cv2.INTER_CUBIC)

    # Próbuj PSM 7 (single line) i PSM 6 (block)
    text = ""
    for psm in (7, 6, 8):
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

    if not text:
        return 0.0, ""

    # Szukaj słów kluczowych
    for keyword, (bonus, label) in KILL_KEYWORDS.items():
        if keyword in text:
            return float(bonus), label

    return 0.0, ""


def _compute_kill_scores(cap: cv2.VideoCapture, fps: float,
                          use_ocr: bool = True) -> Tuple[List[Tuple[float, float]], List[Tuple[float, str]]]:
    """
    Skanuje klip w poszukiwaniu kill text.
    Zwraca (scores_list, detected_kills_list).
    detected_kills_list = [(timestamp, label), ...]
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    scores = []
    kills  = []
    frame_idx = 0
    last_kill_t = -5.0  # cooldown między detekcjami

    if not use_ocr or not OCR_AVAILABLE:
        return [], []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % OCR_EVERY_N_FRAMES == 0:
            t = frame_idx / fps
            bonus, label = _detect_kill_text_ocr(frame)
            if bonus > 0 and (t - last_kill_t) > 3.5:  # cooldown 3.5s (banner trzyma się ~2s na ekranie)
                scores.append((t, bonus))
                kills.append((t, label))
                last_kill_t = t
                print(f"   💀 Kill wykryty @ {t:.1f}s: {label} (bonus={bonus:.0f})")
            else:
                scores.append((t, 0.0))
        frame_idx += 1

    return scores, kills


# ──────────────────────────────────────────────────────────────────────────────
# Łączenie sygnałów → krzywa momentum
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(scores: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Normalizuje score do zakresu [0, 100]."""
    if not scores:
        return scores
    vals = [s for _, s in scores]
    mn, mx = min(vals), max(vals)
    if mx - mn < 1e-6:
        return [(t, 50.0) for t, _ in scores]
    return [(t, 100.0 * (s - mn) / (mx - mn)) for t, s in scores]


def _interpolate_to_common_grid(
    motion: List[Tuple[float, float]],
    kill:   List[Tuple[float, float]],
    vfx:    List[Tuple[float, float]],
    duration: float,
    dt: float = 0.1
) -> List[Tuple[float, float]]:
    """Interpoluje wszystkie sygnały na wspólną siatkę czasową co dt sekund."""
    times = np.arange(0.0, duration, dt)

    def interp(data):
        if not data:
            return np.zeros(len(times))
        ts = np.array([t for t, _ in data])
        vs = np.array([v for _, v in data])
        return np.interp(times, ts, vs, left=0.0, right=0.0)

    m = interp(motion)
    k = interp(kill)
    v = interp(vfx)

    combined = W_MOTION * m + W_KILL * k + W_VFX * v

    # Gaussian smoothing
    try:
        from scipy.ndimage import gaussian_filter1d
        combined = gaussian_filter1d(combined, sigma=5)
    except ImportError:
        # Fallback: manual rolling average
        window = 10
        kernel = np.ones(window) / window
        combined = np.convolve(combined, kernel, mode='same')

    return [(float(times[i]), float(combined[i])) for i in range(len(times))]


# ──────────────────────────────────────────────────────────────────────────────
# Wybór optymalnego trim
# ──────────────────────────────────────────────────────────────────────────────

def _find_best_trim(
    curve: List[Tuple[float, float]],
    peaks: List[Tuple[float, str]],
    duration: float,
    max_dur: float = MAX_DURATION,
    build_before: float = BUILD_BEFORE_PEAK,
    after: float = AFTER_PEAK,
) -> Tuple[float, float, float]:
    """
    Wyznacza optymalne (trim_start, trim_end, main_peak_abs).
    Priorytet: główny peak kill, potem najwyższy punkt krzywej.
    """
    # Wybierz główny peak
    if peaks:
        # Sortuj peaki wg wagi (PENTA > QUADRA > TRIPLE > DOUBLE)
        priority = {"PENTAKILL": 5, "QUADRAKILL": 4, "TRIPLE KILL": 3,
                    "DOUBLE KILL": 2, "KILLING SPREE": 1}
        best_kill = max(peaks, key=lambda p: priority.get(p[1], 0))
        main_peak_t = best_kill[0]
    else:
        # Fallback: najwyższy punkt krzywej
        if curve:
            main_peak_t = max(curve, key=lambda x: x[1])[0]
        else:
            main_peak_t = duration / 2

    # Oblicz okno cięcia
    trim_start = max(0.0, main_peak_t - build_before)
    trim_end   = min(duration, main_peak_t + after)

    # Jeśli kill sekwencja zaczyna się wcześniej niż trim_start → rozszerz
    # (DOUBLE→TRIPLE→QUADRA→PENTA może rozciągać się na >8s)
    if peaks:
        first_kill_t = peaks[0][0]
        if first_kill_t < trim_start or True:
            trim_start = max(0.0, first_kill_t - 9.5)  # 9.5s buforu przed pierwszym wykrytym killem (łapie początek walki)


    # Jeśli okno > max_dur → skróć build-up
    if trim_end - trim_start > max_dur:
        trim_start = max(0.0, trim_end - max_dur)

    # Jeśli i tak za długie → skróć koniec
    if trim_end - trim_start > max_dur:
        trim_end = trim_start + max_dur

    # Peak w klipie (relative)
    peak_in_clip = main_peak_t - trim_start

    return trim_start, trim_end, peak_in_clip


# ──────────────────────────────────────────────────────────────────────────────
# Eksport wizualizacji (opcjonalny debug)
# ──────────────────────────────────────────────────────────────────────────────

def export_momentum_chart(result: MomentumResult, output_path: str) -> None:
    """Zapisuje wykres krzywej momentum do PNG (debug)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        times  = [t for t, _ in result.curve]
        scores = [s for _, s in result.curve]

        fig, ax = plt.subplots(figsize=(14, 4))
        ax.set_facecolor("#0d0d1a")
        fig.patch.set_facecolor("#0d0d1a")

        ax.plot(times, scores, color="#00c8ff", linewidth=1.5, alpha=0.9, label="Momentum")
        ax.fill_between(times, scores, alpha=0.25, color="#00c8ff")

        # Zaznacz trim okno
        ax.axvspan(result.trim_start, result.trim_end,
                   alpha=0.15, color="#ffdd00", label="Trim window")
        ax.axvline(result.trim_start, color="#ffdd00", linestyle="--", linewidth=1)
        ax.axvline(result.trim_end,   color="#ffdd00", linestyle="--", linewidth=1)

        # Zaznacz peaks
        peak_colors = {"PENTAKILL": "#ff4444", "QUADRAKILL": "#ff8800",
                       "TRIPLE KILL": "#ffdd00", "DOUBLE KILL": "#aaffaa",
                       "KILLING SPREE": "#cccccc"}
        for pt, label in result.peaks:
            col = peak_colors.get(label, "#ffffff")
            ax.axvline(pt, color=col, linewidth=2, alpha=0.9)
            ax.text(pt + 0.1, max(scores) * 0.85, label.replace(" ", "\n"),
                    color=col, fontsize=7, va="top")

        ax.set_xlabel("Czas (s)", color="#aaaaaa")
        ax.set_ylabel("Momentum Score", color="#aaaaaa")
        ax.set_title("Krzywa Momentum — LOL Agent", color="white", fontsize=12)
        ax.tick_params(colors="#aaaaaa")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")

        plt.tight_layout()
        plt.savefig(output_path, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"📊 Wykres momentum: {output_path}")
    except Exception as e:
        print(f"⚠️  Nie można wygenerować wykresu: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Główna funkcja publiczna
# ──────────────────────────────────────────────────────────────────────────────

def analyze_momentum(
    video_path: str,
    use_ocr: bool = True,
    save_chart: bool = True,
    max_duration: float = MAX_DURATION,
) -> MomentumResult:
    """
    Pełna analiza momentum klipu LoL.

    Returns MomentumResult z:
      - curve         → krzywa momentum (timestamps + scores)
      - peaks         → wykryte kill moments [(t, label), ...]
      - trim_start    → optymalne cięcie początek
      - trim_end      → optymalne cięcie koniec
      - main_peak_in_clip → peak moment względem trim_start (dla beat-sync)
    """
    print(f"\n{'━'*60}")
    print(f"📈 MOMENTUM ANALYZER")
    print(f"{'━'*60}")
    print(f"   🎬 Klip: {os.path.basename(video_path)}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Nie można otworzyć: {video_path}")

    fps         = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration    = frame_count / fps
    print(f"   ⏱️  Długość: {duration:.1f}s | FPS: {fps:.0f} | Klatki: {frame_count}")

    # ── Sygnał 1: Motion ─────────────────────────────────────────────────────
    print("\n[1/3] Analiza ruchu (motion score)...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    motion_raw = _compute_motion_scores(cap, fps)
    motion_norm = _normalize(motion_raw)

    # ── Sygnał 2: VFX ────────────────────────────────────────────────────────
    print("[2/3] Analiza VFX (nasycenie kolorów walki)...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    vfx_raw  = _compute_vfx_scores(cap, fps, frame_count)
    vfx_norm = _normalize(vfx_raw)

    # ── Sygnał 3: Kill Text OCR ───────────────────────────────────────────────
    print(f"[3/3] Kill text OCR ({'aktywny' if use_ocr and OCR_AVAILABLE else 'wyłączony'})...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    kill_raw, kills = _compute_kill_scores(cap, fps, use_ocr=use_ocr)
    kill_norm = _normalize(kill_raw) if kill_raw else []

    cap.release()

    # ── Łącz sygnały ──────────────────────────────────────────────────────────
    print("\n⚙️  Łączenie sygnałów → krzywa momentum...")
    curve = _interpolate_to_common_grid(motion_norm, kill_norm, vfx_norm, duration)

    # Normalizuj finalną krzywą do [0, 100]
    if curve:
        max_val = max(s for _, s in curve) or 1.0
        curve = [(t, 100.0 * s / max_val) for t, s in curve]

    print(f"   ✅ {len(curve)} punktów krzywej wygenerowanych")
    print(f"   💀 Kill text wykryty: {len(kills)}x — {[f'{t:.1f}s:{l}' for t,l in kills]}")

    # ── Trim ─────────────────────────────────────────────────────────────────
    if kills:
        # LoL kill sequence: DOUBLE → TRIPLE → QUADRA → PENTA
        # Climax is always the last kill. Cut tightly at last_kill + AFTER_PEAK!
        main_peak_t = kills[-1][0]
        first_kill_t = kills[0][0]
        last_label = kills[-1][1]

        # Multi-kill climax needs enough aftermath so the full death animation & pentakill banner is visible
        after_k = 3.8 if any(k in last_label.upper() for k in ["PENTA", "QUADRA"]) else AFTER_PEAK
        trim_end = min(duration, main_peak_t + after_k)
        trim_start = max(0.0, first_kill_t - 2.5)

        # Ensure minimum duration ~12s for a proper Short structure
        if trim_end - trim_start < 12.0:
            trim_start = max(0.0, trim_end - 14.0)

        # If still over max_duration, clamp
        if trim_end - trim_start > max_duration:
            trim_start = max(0.0, trim_end - max_duration)

        main_peak_in_clip = max(0.0, main_peak_t - trim_start)
        print(f"\n✂️  Precyzyjne cięcie: {trim_start:.1f}s → {trim_end:.1f}s ({trim_end - trim_start:.1f}s, finisz +{AFTER_PEAK}s po killu)")
    elif duration <= max_duration:
        trim_start, trim_end = 0.0, duration
        if curve:
            main_peak_t = max(curve, key=lambda x: x[1])[0]
        else:
            main_peak_t = duration / 2
        main_peak_in_clip = main_peak_t
        print(f"\n✂️  Klip krótki ({duration:.1f}s ≤ {max_duration}s) — używam całości")
    else:
        trim_start, trim_end, main_peak_in_clip = _find_best_trim(
            curve, kills, duration, max_dur=max_duration
        )
        print(f"\n✂️  Optymalne cięcie: {trim_start:.1f}s → {trim_end:.1f}s "
              f"({trim_end - trim_start:.1f}s)")

    print(f"   🎯 Peak w klipie @ {main_peak_in_clip:.1f}s (dla beat-sync muzyki)")

    result = MomentumResult(
        video_path       = video_path,
        duration         = duration,
        curve            = curve,
        peaks            = kills,
        trim_start       = trim_start,
        trim_end         = trim_end,
        main_peak_in_clip = main_peak_in_clip,
        kill_detected    = len(kills) > 0,
    )

    # ── Wykres debug ──────────────────────────────────────────────────────────
    if save_chart:
        chart_dir = os.path.join(os.path.dirname(__file__), "lol_temp")
        os.makedirs(chart_dir, exist_ok=True)
        chart_path = os.path.join(chart_dir, "momentum_chart.png")
        export_momentum_chart(result, chart_path)

    print(f"{'━'*60}\n")
    return result


# ──────────────────────────────────────────────────────────────────────────────
# CLI Test
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_file = (sys.argv[1] if len(sys.argv) > 1
                 else r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4")

    if not os.path.exists(test_file):
        print(f"❌ Brak pliku: {test_file}")
        sys.exit(1)

    result = analyze_momentum(test_file, use_ocr=True, save_chart=True)
    print(f"📋 WYNIK:")
    print(f"   Trim:       {result.trim_start:.1f}s → {result.trim_end:.1f}s")
    print(f"   Peak:       {result.main_peak_in_clip:.1f}s (w klipie)")
    print(f"   Kills:      {result.peaks}")
    print(f"   Curve pts:  {len(result.curve)}")
