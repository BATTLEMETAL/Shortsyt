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

# Regiony OCR LoL:
# 1. Główny złoty baner na środku góry ekranu (Double/Triple/Quadra/Pentakill, Ace, Shutdown)
KILL_BANNER_REGION = (0.12, 0.36, 0.22, 0.78)
# 2. Kill feed w prawym górnym rogu
KILL_FEED_REGION   = (0.04, 0.24, 0.68, 0.98)

# Próbkowanie klatek
SAMPLE_EVERY_N_FRAMES = 4   # co 4 klatki (~15fps próbek przy 60fps wideo)
OCR_EVERY_N_FRAMES    = 8   # OCR co 8 klatek (~7.5 próbek/s) — tekst kill trwa min 1.5s więc i tak trafimy

# Kill text keywords and weights (English LoL client)
KILL_KEYWORDS: Dict[str, Tuple[int, str]] = {
    "pentakill":     (100, "PENTAKILL"),
    "penta kill":    (100, "PENTAKILL"),
    "penta":         (95,  "PENTAKILL"),
    "quadra kill":   (80,  "QUADRAKILL"),
    "quadrakill":    (80,  "QUADRAKILL"),
    "quadra":        (70,  "QUADRAKILL"),
    "triple kill":   (60,  "TRIPLE KILL"),
    "triplekill":    (60,  "TRIPLE KILL"),
    "triple":        (50,  "TRIPLE KILL"),
    "double kill":   (40,  "DOUBLE KILL"),
    "doublekill":    (40,  "DOUBLE KILL"),
    "double":        (30,  "DOUBLE KILL"),
    "first blood":   (35,  "FIRST BLOOD"),
    "shut down":     (35,  "SHUTDOWN"),
    "shutdown":      (35,  "SHUTDOWN"),
    "ace":           (40,  "ACE"),
    "has been slain":(25,  "KILL"),
    "slain":         (20,  "KILL"),
    "killing spree": (25,  "KILLING SPREE"),
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
AFTER_PEAK        = 1.0   # s po głównym peaku (punchy, dynamiczny finisz bez przeciągania)
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
    """
    Frame-by-frame absdiff → motion score per timestamp.
    Sekwencyjny odczyt + co N-ta klatka — szybszy niż cap.set() na H.264
    (seek na H.264 wymaga forward-decode od I-frame, sekwencja jest szybsza).
    """
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
    Sekwencyjny odczyt — szybszy niż cap.set() na H.264.
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
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

            high_sat_mask = sat > 150
            score = float(np.mean(sat[high_sat_mask])) if high_sat_mask.any() else 0.0
            scores.append((frame_idx / fps, score))
        frame_idx += 1

    return scores


# ──────────────────────────────────────────────────────────────────────────────
# Sygnał 3: Kill Text OCR
# ──────────────────────────────────────────────────────────────────────────────

def _quick_kill_color_check(roi_hsv: np.ndarray) -> Tuple[bool, np.ndarray]:
    """
    Szybki test kolorowy PRZED Tesseract — sprawdza czy w regionie jest wystarczająco
    złotych/białych/czerwonych pikseli charakterystycznych dla LoL kill banner/feed.
    """
    mask_gold  = cv2.inRange(roi_hsv, (10,  80, 140), (45, 255, 255))
    mask_white = cv2.inRange(roi_hsv, (0,   0,  200), (180, 60, 255))
    mask_ltyel = cv2.inRange(roi_hsv, (20,  40, 180), (40, 200, 255))
    mask_red1  = cv2.inRange(roi_hsv, (0,   100, 120), (10, 255, 255))
    mask_red2  = cv2.inRange(roi_hsv, (170, 100, 120), (180, 255, 255))
    mask = cv2.bitwise_or(mask_gold, cv2.bitwise_or(mask_white, mask_ltyel))
    mask = cv2.bitwise_or(mask, cv2.bitwise_or(mask_red1, mask_red2))
    return cv2.countNonZero(mask) >= 120, mask


def _detect_kill_text_ocr(frame: np.ndarray) -> Tuple[float, str]:
    """
    Uruchamia OCR na górnym regionie klatki (baner centralny + kill feed).
    Wykorzystuje binaryzację luminancji (biały/złoty tekst) + wzorce multikilli i nagród za złoto.
    """
    if not OCR_AVAILABLE:
        return 0.0, ""

    import re as _re

    h, w = frame.shape[:2]

    # Sprawdź kolejno 1. Banner centralny (główny kill/multikill), 2. Kill feed
    regions = [
        KILL_BANNER_REGION,
        KILL_FEED_REGION,
    ]

    for reg in regions:
        ys = int(h * reg[0])
        ye = int(h * reg[1])
        xs = int(w * reg[2])
        xe = int(w * reg[3])
        roi = frame[ys:ye, xs:xe]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        has_color, mask = _quick_kill_color_check(hsv)
        if not has_color:
            continue

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Binaryzacja luminancji: napisy kill w LoL mają jasność > 185
        _, thresh = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY)
        thresh_big = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        text = ""
        for psm in (6, 11, 7):
            try:
                text = pytesseract.image_to_string(
                    thresh_big,
                    config=f"--psm {psm} --oem 1"
                ).strip().lower()
                if text:
                    break
            except Exception:
                pass

        if not text:
            continue

        # 1. Sprawdź słowa kluczowe (PENTAKILL, QUADRA, TRIPLE, DOUBLE, SHUTDOWN)
        for keyword, (bonus, label) in KILL_KEYWORDS.items():
            if keyword in text:
                return float(bonus), label

        # 2. Sprawdź wzorce nagród za zabójstwo championa w LoL (+150, +300, +500, +1000 itp.) lub słowa slain / shut
        if _re.search(r'\+([1-9]\d{2,3})', text) or 'slain' in text or 'shut' in text:
            return 35.0, "KILL"

    return 0.0, ""




def _compute_kill_scores(cap: cv2.VideoCapture, fps: float,
                          use_ocr: bool = True) -> Tuple[List[Tuple[float, float]], List[Tuple[float, str]]]:
    """
    Skanuje klip w poszukiwaniu kill text (baner centralny + kill feed).
    Równoległa analiza wielowątkowa + inteligentna progresja multikilli.
    """
    import concurrent.futures

    if not use_ocr or not OCR_AVAILABLE:
        return [], []

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frame_idx = 0
    candidate_frames = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % OCR_EVERY_N_FRAMES == 0:
            candidate_frames.append((frame_idx / fps, frame))
        frame_idx += 1

    max_w = min(12, os.cpu_count() or 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_w) as executor:
        futures = [executor.submit(_detect_kill_text_ocr, f) for _, f in candidate_frames]
        results = [fut.result() for fut in futures]

    scores = []
    kills = []
    last_kill_t = -5.0
    last_label = ""

    for (t, _), (bonus, label) in zip(candidate_frames, results):
        if bonus > 0:
            # Rejestruj kill jeśli:
            # a) minęło > 1.2s od poprzedniego
            # b) lub to wyższy tier w sekwencji multikilla (np. TRIPLE -> QUADRA -> PENTA)
            tier_weights = {"DOUBLE KILL": 1, "TRIPLE KILL": 2, "QUADRAKILL": 3, "PENTAKILL": 4}
            prev_tier = tier_weights.get(last_label, 0)
            curr_tier = tier_weights.get(label, 0)

            is_upgrade = (curr_tier > prev_tier and (t - last_kill_t) <= 4.5)
            is_new = (t - last_kill_t) > 1.2

            if is_new or is_upgrade:
                scores.append((t, bonus))
                kills.append((t, label))
                last_kill_t = t
                last_label = label
                print(f"   💀 Kill wykryty @ {t:.1f}s: {label} (bonus={bonus:.0f})")
            else:
                scores.append((t, 0.0))
        else:
            scores.append((t, 0.0))

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
        if first_kill_t < trim_start:  # FIX: usunięto "or True" - rozszerz TYLKO gdy first kill wypada przed oknem
            trim_start = max(0.0, first_kill_t - 4.0)  # 4.0s buforu przed pierwszym killem (kontekst walki bez biegania)


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
    action_hint: str = "",      # CLI --action override (triple/quadra/penta/double)
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

    # ── OCR Fallback ─────────────────────────────────────────────────────────
    # Jeśli OCR nie wykrył killi ALE wiemy z --action że to był multikill:
    # Klipy Outplayed kończą się ~2-3s po akcji → baner jest zawsze blisko końca.
    # Wstrzykujemy syntetyczny peak w duration - 3.5s.
    _MULTIKILL_LABELS = {
        "pentakill":  "PENTAKILL",
        "quadrakill": "QUADRAKILL",
        "triple":     "TRIPLE KILL",
        "double":     "DOUBLE KILL",
        "oneshot":    "ONE SHOT",
    }
    if not kills and action_hint in _MULTIKILL_LABELS:
        _synthetic_t = max(0.0, duration - 3.5)
        _synthetic_label = _MULTIKILL_LABELS[action_hint]
        kills = [(_synthetic_t, _synthetic_label)]
        print(f"   ⚡ OCR FALLBACK: brak detekcji → syntetyczny peak @ {_synthetic_t:.1f}s [{_synthetic_label}]")

    # ── Trim ─────────────────────────────────────────────────────────────────
    if kills:
        # LoL kill sequence: DOUBLE → TRIPLE → QUADRA → PENTA
        # Climax is always the last kill. Cut tightly at last_kill + AFTER_PEAK!
        main_peak_t = kills[-1][0]
        first_kill_t = kills[0][0]
        last_label = kills[-1][1]

        # Multi-kill climax: 1.5s after last kill → baner widoczny + czyste zakończenie dla pętli
        after_k = 1.5
        trim_end = min(duration, main_peak_t + after_k)
        trim_start = max(0.0, first_kill_t - 2.5)

        # Ensure minimum duration ~10s
        if trim_end - trim_start < 10.0:
            trim_start = max(0.0, trim_end - 12.0)

        # ── 15-SECOND SNAP RULE ──────────────────────────────────────────────
        # Klipy 15s mają najwyższy priorytet algorytmu (najlepszy watch-time / CTR).
        # Jeśli okno wychodzi 15.5–18.0s → skróć build-up do 14.0s raw
        # (po slow-mo 1.5s/0.5x → stretch ~0.75s → finalny ~14.75s ≈ 15s)
        raw_window = trim_end - trim_start
        if 15.5 <= raw_window <= 18.0:
            trim_start = max(0.0, trim_end - 14.0)
            print(f"   ⚡ 15s SNAP: okno {raw_window:.1f}s → docięto do {trim_end - trim_start:.1f}s raw (~15s po slow-mo)")

        # If still over max_duration, clamp
        if trim_end - trim_start > max_duration:
            trim_start = max(0.0, trim_end - max_duration)

        main_peak_in_clip = max(0.0, main_peak_t - trim_start)
        print(f"\n✂️  Precyzyjne cięcie: {trim_start:.1f}s → {trim_end:.1f}s ({trim_end - trim_start:.1f}s, finisz +{after_k:.1f}s po killu)")
    elif duration <= max_duration:
        # ── VFX-BASED TRIM gdy brak OCR kills ───────────────────────────────
        # Używamy TYLKO sygnału VFX (nasycenie kolorów czarów/eksplozji).
        # VFX jest wysokie TYLKO podczas walki — nie podczas biegania.
        # Two-pass threshold:
        #   45% → prawdziwy combat (ustawia start, ignoruje running ambient)
        #   20% → koniec combat zone (zostaje trochę po ostatnim efekcie)
        if curve:
            main_peak_t = max(curve, key=lambda x: x[1])[0]

        vfx_for_trim = vfx_norm if vfx_norm else curve
        if vfx_for_trim:
            max_vfx = max(s for _, s in vfx_for_trim) or 1.0

            # Pass 1: Wysoki próg — tylko prawdziwy combat (nie bieganie)
            high_threshold = max_vfx * 0.45
            high_active = [t for t, s in vfx_for_trim if s >= high_threshold]

            # Pass 2: Niski próg — koniec strefy walki
            low_threshold = max_vfx * 0.20
            low_active = [t for t, s in vfx_for_trim if s >= low_threshold]

            if high_active and low_active:
                # Start: 2s przed pierwszym wysokim VFX (pre-roll z kontekstem)
                vfx_start = max(0.0, high_active[0] - 2.0)
                # End: 2.5s po ostatnim wysokim VFX (baner zabójstwa + cooldown)
                vfx_end   = min(duration, high_active[-1] + 2.5)

                # Przesuń peak na środek combat zone jeśli OCR zawiódł
                peak_vfx_t = max(vfx_for_trim, key=lambda x: x[1])[0]
                main_peak_t = peak_vfx_t

                if vfx_end - vfx_start >= 6.0 and (vfx_start > 0.8 or vfx_end < duration - 0.8):
                    trim_start = vfx_start
                    trim_end   = vfx_end
                    print(f"\n✂️  VFX-trim (brak OCR): {trim_start:.1f}s → {trim_end:.1f}s ({trim_end-trim_start:.1f}s) — wycięto dead-zones")
                else:
                    trim_start, trim_end = 0.0, duration
                    print(f"\n✂️  Klip krótki ({duration:.1f}s ≤ {max_duration}s) — cały klip aktywny")
            else:
                trim_start, trim_end = 0.0, duration
                if not curve:
                    main_peak_t = duration / 2
                print(f"\n✂️  Klip krótki ({duration:.1f}s ≤ {max_duration}s) — brak aktywności VFX")
        else:
            trim_start, trim_end = 0.0, duration
            main_peak_t = duration / 2
            print(f"\n✂️  Klip krótki ({duration:.1f}s ≤ {max_duration}s) — używam całości")

        main_peak_in_clip = max(0.0, main_peak_t - trim_start)


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
# Combat Segment Detection
# ──────────────────────────────────────────────────────────────────────────────

def find_combat_segments(
    peaks: List[Tuple[float, str]] = None,
    curve: List[Tuple[float, float]] = None,
    clip_start: float = 0.0,
    clip_end: float = None,
    activity_threshold: float = 35.0,
    pre_roll: float = 2.5,
    post_roll: float = 1.2,
    merge_gap: float = 3.5,
    min_segment_dur: float = 2.5,
    max_total_duration: float = 26.0,
) -> List[Tuple[float, float]]:
    """
    Automatyczny silnik Jump-Cut:
    1. Skanuje krzywą aktywności i kille na całej osi czasu.
    2. Zachowuje pełny trade setup (pre_roll=2.5s przed pierwszym ciosem).
    3. Scalanie wymian (merge_gap=3.5s) — ciągła walka NIE jest bezsensownie cięta na kawałki.
    4. Loop-Bait Climax: ostro ucina ostatni segment +1.0s do +1.2s po ostatnim fragu.
    5. Gwarantuje idealną długość końcową (14s - 26s).
    """
    if clip_end is None:
        clip_end = float('inf')

    windows = []

    # 1. Okna z krzywej momentum (ruch + VFX czarów/walki)
    if curve:
        in_active = False
        act_start = clip_start
        for t, score in curve:
            if t < clip_start:
                continue
            if clip_end and t > clip_end:
                break
            if score >= activity_threshold:
                if not in_active:
                    in_active = True
                    act_start = max(clip_start, t - pre_roll)
            else:
                if in_active:
                    in_active = False
                    act_end = min(clip_end if clip_end != float('inf') else 999.0, t + post_roll)
                    if act_end > act_start:
                        windows.append([act_start, act_end])
        if in_active:
            act_end = clip_end if clip_end != float('inf') else (curve[-1][0] if curve else clip_start + MAX_DURATION)
            windows.append([act_start, act_end])

    # 2. Okna wokół wykrytych killi
    for pt, lbl in (peaks or []):
        p_start = max(clip_start, pt - pre_roll - 1.5)
        p_end = min(clip_end if clip_end != float('inf') else 999.0, pt + post_roll + 0.8)
        if p_end > p_start:
            windows.append([p_start, p_end])

    if not windows:
        # Żadnych okien z OCR ani killi — spróbuj znaleźć aktywność z samej krzywej
        # na obniżonym progu (20%) żeby wyciąć przynajmniej martwy początek/koniec
        if curve:
            low_threshold = max(s for _, s in curve) * 0.20 if curve else 0.0
            active_times = [t for t, s in curve if s >= low_threshold and clip_start <= t <= clip_end]
            if active_times:
                motion_s = max(clip_start, active_times[0] - pre_roll)
                motion_e = min(clip_end if clip_end != float('inf') else active_times[-1] + post_roll,
                               active_times[-1] + post_roll)
                if motion_e - motion_s >= min_segment_dur:
                    print(f"   [CombatSeg] Brak peaks → Motion fallback: {motion_s:.1f}s-{motion_e:.1f}s")
                    return [(round(motion_s, 2), round(motion_e, 2))]
        safe_end = clip_end if clip_end != float('inf') else clip_start + MAX_DURATION
        return [(clip_start, safe_end)]

    # 3. Scal nakładające się lub bliskie okna (przerwy <= merge_gap są zachowane, reszta = jump cut)
    windows.sort(key=lambda x: x[0])
    merged = [list(windows[0])]
    for w in windows[1:]:
        if w[0] <= merged[-1][1] + merge_gap:
            merged[-1][1] = max(merged[-1][1], w[1])
        else:
            merged.append(list(w))

    # 4. Loop-Bait Climax Cutoff:
    # Jeśli mamy wykryty kill / szczyt, utnij ostatni segment dokładnie +0.9s po nim
    if peaks:
        last_kill_t = peaks[-1][0]
        # Znajdź segment zawierający ostatni kill
        for i in range(len(merged)):
            if merged[i][0] <= last_kill_t <= merged[i][1] + 3.0:
                merged[i][1] = min(merged[i][1], last_kill_t + 1.0)
                # Odetnij wszystkie segmenty występujące po ostatnim fragu
                merged = merged[:i+1]
                break

    # 5. Filtruj segmenty za krótkie (< min_segment_dur)
    valid_segs = []
    for s, e in merged:
        s_clamped = max(clip_start, s)
        e_clamped = min(clip_end if clip_end != float('inf') else e, e)
        if (e_clamped - s_clamped) >= min_segment_dur:
            valid_segs.append([round(s_clamped, 2), round(e_clamped, 2)])

    if not valid_segs:
        safe_end = clip_end if clip_end != float('inf') else clip_start + MAX_DURATION
        valid_segs = [[clip_start, safe_end]]

    # 6. Kontrola łącznej długości (max_total_duration = 26s):
    # Jeśli suma długości przekracza limit, skróć najwcześniejszy segment (ale NIGDY nie ucinaj pierwszego killa!)
    total_dur = sum(e - s for s, e in valid_segs)
    if total_dur > max_total_duration:
        excess = total_dur - max_total_duration
        first_s, first_e = valid_segs[0]
        # Bezpieczna granica: zachowaj minimum 2.0s przed pierwszym killem
        if peaks:
            earliest_allowed_s = max(clip_start, peaks[0][0] - 2.0)
            max_safe_cut = max(0.0, earliest_allowed_s - first_s)
            actual_cut = min(excess, max_safe_cut)
        else:
            actual_cut = excess

        if actual_cut > 0 and (first_e - (first_s + actual_cut)) >= min_segment_dur:
            valid_segs[0][0] = round(first_s + actual_cut, 2)

    final_segs = [(round(s, 2), round(e, 2)) for s, e in valid_segs]

    print(f"\n   [CombatSeg] {len(final_segs)}x okno walki (Jump-Cut): "
          + " | ".join(f"{s:.1f}-{e:.1f}s ({e-s:.1f}s)" for s, e in final_segs)
          + f" -> Razem: {sum(e-s for s, e in final_segs):.1f}s")
    return final_segs



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
