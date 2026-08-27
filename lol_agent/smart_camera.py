"""
LOL Agent — Smart Camera v2: sledzi championa przez zolty pasek zdrowia.
Priorytet: zolty HP bar (ally champion) → motion diff (fallback).

Dlaczego HP bar?
  - W LoL TYLKO allied champion gracza ma zolty pasek zdrowia
  - Wrogowie = czerwony, miniony = zielony, VFX = cyan/niebieski
  - Motion diff sledzi VFX efekty (AOE kola, wybuchy) → ZLE kadrowanie
  - Zolty kolor jest bardzo charakterystyczny i niezawodny

Nie wymaga AI/CV — tylko PIL + numpy.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import subprocess
import tempfile
import numpy as np
import cv2
from PIL import Image


# ─── Ekstrakcja klatek ────────────────────────────────────────────────────────

def extract_sample_frames(video_path: str, clip_start: float, clip_end: float,
                           n_frames: int = 10,
                           scale_w: int = 384, scale_h: int = 216) -> list:
    """
    Wycina n_frames klatek równo rozłożonych między clip_start a clip_end.
    Zoptymalizowane: czyta bezpośrednio z RAM przez cv2.VideoCapture (50x szybciej, bez plików na dysku).
    """
    duration = clip_end - clip_start
    interval = duration / (n_frames + 1)
    frames = []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0

    for i in range(n_frames):
        t = clip_start + interval * (i + 1)
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame_bgr = cap.read()
        if ret and frame_bgr is not None:
            if frame_bgr.shape[1] != scale_w or frame_bgr.shape[0] != scale_h:
                frame_bgr = cv2.resize(frame_bgr, (scale_w, scale_h), interpolation=cv2.INTER_AREA)
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
            frames.append(frame_rgb)

    cap.release()
    return frames


def compute_motion_map(frames: list) -> np.ndarray:
    """
    Oblicza mape ruchu jako srednia absolutna roznice miedzy kolejnymi klatkami.
    Zwraca 2D array (H, W) — wyzsze wartosci = wiecej ruchu.
    """
    if len(frames) < 2:
        h, w = frames[0].shape[:2] if frames else (216, 384)
        return np.ones((h, w))

    diffs = []
    for i in range(len(frames) - 1):
        diff = np.abs(frames[i+1] - frames[i]).mean(axis=2)
        diffs.append(diff)

    return np.mean(diffs, axis=0)


# ─── Detekcja zoltego HP bara (champion gracza) ───────────────────────────────

def _detect_fight_center_x(frame_rgb: np.ndarray,
                           hud_y_cutoff: int,
                           top_cutoff: int,
                           dead_buckets: set = None) -> tuple[int | None, int | None, int]:
    """
    Wykrywa centrum walki przez wykrywanie WSZYSTKICH paskow HP na ekranie.

    Zwraca: (yellow_x, fight_center_x, bar_count)
      - yellow_x       : x championa gracza (zolty HP bar) lub None
      - fight_center_x : centroid WSZYSTKICH pasków HP (zolty + czerwone wrogów) lub None
      - bar_count      : liczba wykrytych pasków (0=nic, 1=tylko gracz, 2+=walka)

    W LoL:
      - Gracz       → ZOLTY HP bar (R>160, G>130, B<110)
      - Wrogowie    → CZERWONY HP bar (R>150, G<90, B<80)
      - Sojusznicy  → NIEBIESKI/ZIELONY HP bar (wykluczone)
    """
    f = frame_rgb.astype(np.int16)
    r, g, b = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    h, w = r.shape

    # Outplayed stats panel (lewy-gorny naroznik)
    outplayed_x = int(w * 0.22)
    outplayed_y = int(h * 0.35)

    def make_exclusion_mask():
        mask = np.ones((h, w), dtype=bool)
        mask[:int(h * 0.10), :] = False       # górny scoreboard/HUD
        mask[int(h * 0.78):, :] = False       # dolny pas umiejętności/HUD
        # Dolna prawa ćwiartka — minimapa i panel przedmiotów w LoL
        mask[int(h * 0.62):, int(w * 0.76):] = False
        # Dolna lewa ćwiartka — portret i chat
        mask[int(h * 0.65):, :int(w * 0.20)] = False
        mask[:, :8] = False                   # lewy margines
        mask[:, -8:] = False                  # prawy margines
        return mask

    excl = make_exclusion_mask()

    # --- Żółty & Zielony HP bar (Gracz) ---
    yellow = (
        (r > 160) & (g > 130) & (b < 110) &
        ((r - b) > 80) & ((g - b) > 50)
    ) & excl
    green = (
        (g > 150) & (r < 120) & (b < 120) &
        ((g - r) > 50)
    ) & excl
    player_mask = (yellow | green)

    player_x = None
    if player_mask.sum() >= 5:
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(player_mask.astype(np.uint8))
        best_score = -1
        for comp_i in range(1, num_labels):
            cx, cy, cw, ch, area = stats[comp_i]
            aspect = cw / max(ch, 1)
            # Prawdziwy pasek HP championa jest cienki i szeroki (aspect >= 2.0, ch <= 5)
            if cw >= 5 and ch <= 5 and aspect >= 2.0 and area >= 5:
                score = area * aspect
                if score > best_score:
                    best_score = score
                    player_x = int(centroids[comp_i][0])

    # --- Czerwony HP bar (Wrogowie) ---
    red = (
        (r > 150) & (g < 95) & (b < 85) &
        ((r - g) > 60) & ((r - b) > 70)
    ) & excl

    enemy_xs = []
    if red.sum() >= 4:
        num_labels_r, labels_r, stats_r, centroids_r = cv2.connectedComponentsWithStats(red.astype(np.uint8))
        for comp_i in range(1, num_labels_r):
            cx, cy, cw, ch, area = stats_r[comp_i]
            aspect = cw / max(ch, 1)
            if cw >= 4 and ch <= 6 and aspect >= 1.8 and area >= 4:
                enemy_xs.append(int(centroids_r[comp_i][0]))

    # --- Centroid walki ---
    all_xs = []
    bar_count = 0

    if player_x is not None:
        all_xs.append(player_x)
        bar_count += 1

    if enemy_xs:
        all_xs.extend(enemy_xs)
        bar_count += len(enemy_xs)

    fight_center_x = int(np.mean(all_xs)) if all_xs else None

    return player_x, fight_center_x, bar_count


def _detect_enemy_buckets(frame_rgb: np.ndarray,
                          hud_y_cutoff: int,
                          top_cutoff: int) -> set:
    """
    Pre-pass: wykrywa pozycje zyowych wrogow jako zbior bucket-kluczy (25px/bucket).
    Uzywane do budowania kill-order timeline z histereza.
    Lzejsza wersja _detect_fight_center_x — tylko czerwone HP bary.
    """
    f = frame_rgb.astype(np.int16)
    r, g, b = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    h, w = r.shape

    excl = np.ones((h, w), dtype=bool)
    excl[:top_cutoff, :] = False
    excl[hud_y_cutoff:, :] = False
    excl[:, :6]  = False
    excl[:, -6:] = False

    red = (
        (r > 150) & (g < 90) & (b < 80) &
        ((r - g) > 70) & ((r - b) > 80)
    ) & excl

    red_row_counts = red.sum(axis=1)
    enemy_xs = []
    for row_idx in np.where(red_row_counts >= 5)[0]:
        cols = np.where(red[row_idx, :])[0]
        if len(cols) >= 5:
            enemy_xs.append(int(np.median(cols)))

    buckets = {}
    for x in enemy_xs:
        key = int(x // 25)
        buckets.setdefault(key, []).append(x)

    # Prog >=2 (nie >=3) bo w pre-passie chcemy wyższą czulosc detekcji zycia
    return {key for key, v in buckets.items() if len(v) >= 2}


def detect_kill_events_from_audio(video_path: str,
                                   clip_start: float,
                                   clip_end: float,
                                   clip_duration: float | None = None
                                   ) -> list[tuple[float, str]]:
    """
    Wykrywa momenty oglosen multi-kill przez analize audio gry.

    Algorytm:
      1. Ekstrakcja mono 22050 Hz PCM przez ffmpeg
      2. Bandpass FFT (300-4000 Hz) = pasmo glosu announcera
         odfiltrowanie dzwiekow atakow (nisko) i szumow (wysoko)
      3. Suwajace okno RMS 50ms co 10ms
      4. Peak = RMS > mediana + 2.5*std  (announcer glosniejszy niz tlo)
      5. Grupowanie: min 150ms, min 300ms przerwa miedzy zdarzeniami
      6. Etykiety multi-kill po sekwencji zdarzen

    Zwraca: [(t_clip, label), ...] gdzie t_clip = wzgledny do clip_start (0-based).
    """
    if clip_duration is None:
        clip_duration = clip_end - clip_start

    SAMPLE_RATE = 22050
    HOP_MS  = 10    # krok okna RMS (ms)
    WIN_MS  = 50    # okno RMS (ms)
    VOICE_LO = 300  # Hz dolna granica pasma glosu
    VOICE_HI = 4000 # Hz gorna granica pasma glosu

    win_samples = int(SAMPLE_RATE * WIN_MS / 1000)
    hop_samples = int(SAMPLE_RATE * HOP_MS / 1000)

    # 1. Ekstrakcja PCM
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.raw')
    os.close(tmp_fd)
    try:
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(clip_start), '-t', str(clip_duration),
            '-i', video_path,
            '-vn', '-ac', '1', '-ar', str(SAMPLE_RATE),
            '-f', 'f32le', tmp_path
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(f"   [kills-audio] ffmpeg error — pomijam")
            return []
        audio = np.fromfile(tmp_path, dtype=np.float32)
    finally:
        try: os.unlink(tmp_path)
        except: pass

    if len(audio) < win_samples * 2:
        print("   [kills-audio] Za krotki fragment audio")
        return []

    # Normalizuj do peak=1.0 — niezalezne od glosnosci nagrania
    peak_amp = float(np.max(np.abs(audio)))
    if peak_amp > 1e-6:
        audio = audio / peak_amp

    freqs = np.fft.rfftfreq(win_samples, d=1.0 / SAMPLE_RATE)
    voice_mask = (freqs >= VOICE_LO) & (freqs <= VOICE_HI)
    hann = np.hanning(win_samples)

    # 2. Bandpass + RMS per frame
    n_frames = max(1, (len(audio) - win_samples) // hop_samples + 1)
    rms = np.zeros(n_frames, dtype=np.float32)
    for i in range(n_frames):
        chunk = audio[i * hop_samples: i * hop_samples + win_samples]
        if len(chunk) < win_samples:
            break
        spec = np.fft.rfft(chunk * hann)
        spec[~voice_mask] = 0
        voice_sig = np.fft.irfft(spec)
        rms[i] = float(np.sqrt(np.mean(voice_sig ** 2)))

    frame_times = np.arange(n_frames) * hop_samples / SAMPLE_RATE

    # 3. Lokalnie adaptywny prog: srednia krocząca 2s * wspolczynnik
    # Dziala nawet gdy cale audio jest glosne (walka/Malphite ult przez caly klip)
    # okno 2s = 200 klatek przy 10ms hop
    WIN_LOCAL = min(200, n_frames // 4)
    local_avg = np.convolve(rms, np.ones(WIN_LOCAL) / WIN_LOCAL, mode='same')
    # Prog: 1.6x powyzej lokalnej sredniej (announcer jest wyranie glosniejszy niz tlo)
    # Minimalny prog absolutny = 0.001 (ciche nagrania)
    above = rms > np.maximum(local_avg * 1.6, 0.001)

    _max_rms = float(np.max(rms)) if len(rms) > 0 else 0.0
    _avg_rms = float(np.mean(rms)) if len(rms) > 0 else 0.0
    print(f"   [kills-audio] max_rms={_max_rms:.4f}  avg={_avg_rms:.4f}")

    # 4. Grupuj cigle przebiegi powyżej progu
    MIN_DUR_S = 0.10  # min 100ms
    MAX_DUR_S = 3.00  # max 3s (wieksze mogą byc seria uderzeń)
    MIN_GAP_S = 0.25  # min 250ms przerwy

    events: list[float] = []
    in_ev = False
    ev_start = 0

    for i in range(len(above)):
        if above[i] and not in_ev:
            in_ev, ev_start = True, i
        elif not above[i] and in_ev:
            in_ev = False
            dur = (i - ev_start) * hop_samples / SAMPLE_RATE
            t_s = float(frame_times[ev_start])
            if MIN_DUR_S <= dur <= MAX_DUR_S:
                if not events or (t_s - events[-1]) >= MIN_GAP_S:
                    events.append(t_s)

    if not events:
        print("   [kills-audio] Brak pikow announcera — pomijam overlaye")
        return []

    print(f"   [kills-audio] Piki audio: {[round(t,2) for t in events]}")

    # 5. Etykiety multi-kill
    MULTI_WINDOW = 12.0
    LABELS = ["DOUBLE KILL", "TRIPLE KILL", "QUADRAKILL", "PENTAKILL"]
    result: list[tuple[float, str]] = []
    streak = 1

    for idx, t in enumerate(events):
        if idx == 0:
            streak = 1
        elif (t - events[idx - 1]) <= MULTI_WINDOW:
            streak += 1
        else:
            streak = 1

        if streak >= 2:
            label = LABELS[min(streak - 2, len(LABELS) - 1)]
            result.append((t, label))
            if label == "PENTAKILL":
                break

    if result:
        print(f"   [kills-audio] Overlaye: {[(round(t,2), l) for t, l in result]}")
    return result



def detect_kill_events_from_video(video_path: str,
                                   clip_start: float,
                                   clip_end: float,
                                   source_w: int = 1920,
                                   source_h: int = 1080,
                                   n_samples: int = 120,
                                   action_type: str | None = None,
                                   ) -> list[tuple[float, str]]:
    """
    Wykrywa momenty kilow przez analize jasnosci pikseli w regionie tekstu kilu.

    LoL wyswietla duzy bialy tekst z kolorowa aureola w centrum dolnej polowy ekranu:
      "Double Kill" / "Triple Kill" / "Quadra Kill" / "Penta Kill"
    Region: y=40-60%, x=30-70% (1920x1080 → 576-1344 x, 432-648 y)
    Aureola: ciepla zloto-pomaranczowa (R>200, G>150, B<100) lub biala (R,G,B>220)

    Metoda: ekstrakcja klatek w wyzszej czestotliwosci (120 klatek/20s = co 167ms)
    → dla kazdej klatki suma pikseli spelnajacych warunek jaskrawosci w regionie
    → lokalnie adaptywny prog → grupowanie eventow → etykiety wg sekwencji

    Nie wymaga pytesseract — dziala przez sam kolor i jasnosc.
    """
    duration = clip_end - clip_start
    scale_w, scale_h = 384, 216     # robocza rozdzielczosc
    # Region tekstu kilu w skalowanym obrazie (proporcjonalny)
    rx1 = int(scale_w * 0.30)       # x=30%
    rx2 = int(scale_w * 0.70)       # x=70%
    ry1 = int(scale_h * 0.38)       # y=38%
    ry2 = int(scale_h * 0.62)       # y=62%

    print(f"   [kills-video] Skanuje {n_samples} klatek dla kill text region...")

    try:
        frames = extract_sample_frames(video_path, clip_start, clip_end,
                                       n_frames=n_samples,
                                       scale_w=scale_w, scale_h=scale_h)
    except Exception as e:
        print(f"   [kills-video] Blad ekstrakcji klatek: {e}")
        return []

    if len(frames) < 4:
        print("   [kills-video] Za malo klatek")
        return []

    t_points = np.linspace(0.0, duration, len(frames))

    # Dla kazdej klatki: suma pikseli kill-text w regionie
    scores = np.zeros(len(frames), dtype=np.float32)
    for i, frame in enumerate(frames):
        roi = frame[ry1:ry2, rx1:rx2]          # H x W x 3, uint8
        r = roi[:, :, 0].astype(np.float32)
        g = roi[:, :, 1].astype(np.float32)
        b = roi[:, :, 2].astype(np.float32)

        # Bialy tekst kill announcement (R,G,B > 220)
        white_mask  = ((r > 215) & (g > 215) & (b > 215)).astype(np.float32)
        # Zloto-pomaranczowa aureola kilu (R>200, G>130, B<100)
        gold_mask   = ((r > 190) & (g > 120) & (b < 110)
                       & ((r - b) > 100)).astype(np.float32)
        # Niebieskawa aureola (kill ribbon) — R>150, G>150, B>200
        blue_mask   = ((b > 195) & (r > 140) & (g > 140)
                       & ((b - r) > 30)).astype(np.float32)

        scores[i] = white_mask.sum() + gold_mask.sum() * 0.8 + blue_mask.sum() * 0.6

    # Lokalnie adaptywny prog (okno 2s = ~24 klatki przy 120/20s)
    win = max(6, n_samples // 10)
    local_avg = np.convolve(scores, np.ones(win) / win, mode='same')
    # Prog: srednia * 2.0 LUB absolutny minimum (klatka bez walki ~ 200 pikseli)
    threshold = np.maximum(local_avg * 2.0, 250.0)
    above = scores > threshold

    _max_sc = float(np.max(scores))
    _avg_sc = float(np.mean(scores))
    print(f"   [kills-video] max_score={_max_sc:.0f}  avg={_avg_sc:.0f}  "
          f"thresh_avg={float(np.mean(threshold)):.0f}")

    # Grupuj cigle przebiegi
    MIN_DUR_FRAMES = 2    # min 2 klatki (~334ms)
    MIN_GAP_FRAMES = 8    # min 8 klatek (~1.3s) miedzy eventami
    events: list[float] = []
    in_ev = False
    ev_start = 0

    for i in range(len(above)):
        if above[i] and not in_ev:
            in_ev, ev_start = True, i
        elif not above[i] and in_ev:
            in_ev = False
            dur_frames = i - ev_start
            if dur_frames >= MIN_DUR_FRAMES:
                t_s = float(t_points[ev_start])
                if not events or (i - (ev_start - dur_frames)) >= MIN_GAP_FRAMES:
                    events.append(t_s)

    if not events:
        print("   [kills-video] Brak zdarzen kill text — pomijam overlaye")
        return []

    print(f"   [kills-video] Kill events: {[round(t, 2) for t in events]}")

    # Etykiety multi-kill po sekwencji eventow
    # LABELS[i] = etykieta dla streak=i+2 (DOUBLE=2, TRIPLE=3, QUADRA=4, PENTA=5+)
    MULTI_WINDOW = 12.0
    ACTION_LABEL_MAP = {
        'pentakill':  'PENTAKILL',
        'quadrakill': 'QUADRAKILL',
        'triple':     'TRIPLE KILL',
        'double':     'DOUBLE KILL',
        'outplay':    'OUTPLAY',
        'clutch':     'CLUTCH',
    }
    LABELS = ["DOUBLE KILL", "TRIPLE KILL", "QUADRAKILL", "PENTAKILL"]
    result: list[tuple[float, str]] = []
    streak = 1

    for idx, t in enumerate(events):
        if idx == 0:
            streak = 1
        elif (t - events[idx - 1]) <= MULTI_WINDOW:
            streak += 1
        else:
            streak = 1

        if streak >= 2:
            label = LABELS[min(streak - 2, len(LABELS) - 1)]
            result.append((t, label))
            if label == "PENTAKILL":
                break

    # Jesli 1 event (np. LoL wyswietla tylko "Penta Kill!" bez etapow posrednich)
    # i znamy action_type — uzyj go jako etykiety
    if not result and events and action_type:
        label = ACTION_LABEL_MAP.get(action_type.lower(), action_type.upper())
        result = [(events[0], label)]
        print(f"   [kills-video] Single event — label z action_type: '{label}' @ {events[0]:.2f}s")

    if result:
        print(f"   [kills-video] Overlaye: {[(round(t,2), l) for t, l in result]}")
    return result


def detect_kill_events(video_path: str,
                       clip_start: float,
                       clip_end: float,
                       clip_duration: float | None = None,
                       action_type: str | None = None,
                       ) -> list[tuple[float, str]]:
    """
    Glowna funkcja detekcji kilow. Probuje metody w kolejnosci:
      1. Video brightness/color (detect_kill_events_from_video) — bez dependencies
         Jesli 1 event + action_type znany → uzywa action_type jako etykiety
      2. Audio bandpass (detect_kill_events_from_audio) — fallback gdy video nie wykrylo

    Uzywana przez pipeline i test_render_v17.py.
    """
    # --- Metoda 1: Video ---
    video_result = detect_kill_events_from_video(video_path, clip_start, clip_end,
                                                  action_type=action_type)
    if len(video_result) >= 1:
        print(f"   [kills] Uzywam detekcji VIDEO ({len(video_result)} event(ow))")
        return video_result

    # --- Metoda 2: Audio fallback ---
    print(f"   [kills] Video nie wykrylo — fallback do AUDIO")
    audio_result = detect_kill_events_from_audio(video_path, clip_start, clip_end,
                                                  clip_duration=clip_duration)
    return audio_result


def _detect_cursor_x(frame_rgb: np.ndarray,
                     hud_y_cutoff: int,
                     top_cutoff: int,
                     scale_w: int = 384) -> int | None:
    """
    Wykrywa pozycje kursora ataku LoL. Obsluguje DWA warianty:

    1. ZLOTY RING (domyslny kursor LoL):
       - Zloty/zolty krag: R≈220, G≈200, B≈30  (G bliskie R, ale B bardzo male)
       - Warunek: R>185, G>140, B<65, (G-B)>80, (R-B)>120
       - Okragle skupisko (~16-20px przy 768px), odrzucamy HP bary (poziome)

    2. CZERWONY KURSOR Z MIECZAMI (skiny niestandardowe):
       - Czerwone kolo: R>155, G<90, B<90 (identyczne z HP barami!)
       - Weryfikacja: biale piksele mieczy (R>180, G>180, B>165) w otoczeniu +-20px
       - Bez bialych pikseli = HP bar = odrzucamy

    scale_w: rozdzielczosc (384 lub 768). Progi skaluja sie automatycznie.
    Zwraca scaled_x w skali 384px lub None.
    """
    f = frame_rgb.astype(np.int16)
    r, g, b = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    h, w = r.shape

    border = max(6, int(6 * scale_w / 384))
    excl = np.ones((h, w), dtype=bool)
    excl[:top_cutoff, :] = False
    excl[hud_y_cutoff:, :] = False
    excl[:, :border]  = False
    excl[:, -border:] = False

    s     = (scale_w / 384) ** 2   # Area scale (piksele)
    dim_s = scale_w / 384           # Dimension scale (rozmiar)
    n_min = int(4 * s)
    n_max = int(150 * s)
    max_dim = int(28 * dim_s)
    min_row = max(2, int(2 * dim_s))

    def _eval_mask(mask):
        """Zwraca (col_median, row_span, col_span) lub None."""
        n = int(mask.sum())
        if n < n_min or n > n_max:
            return None
        rows_a = np.where(mask.sum(axis=1) > 0)[0]
        cols_a = np.where(mask.sum(axis=0) > 0)[0]
        if len(rows_a) == 0 or len(cols_a) == 0:
            return None
        rs = int(rows_a[-1] - rows_a[0]) + 1
        cs = int(cols_a[-1] - cols_a[0]) + 1
        if rs < min_row:
            return None                    # Zbyt plaska = fragment HP bar
        if cs > 3 * max(rs, 1):
            return None                    # Zbyt pozioma = HP bar
        if cs > max_dim or rs > max_dim:
            return None                    # Zbyt duzy = VFX
        return int(np.median(cols_a))

    # ── WARIANT 1: Zloty/zolty ring ────────────────────────────────────────
    # G=140-240 (bliskie R), B<65, (G-B)>80 oddziela zolty od czerwonego HP bar
    gold_mask = (
        (r > 185) & (g > 140) & (g < 245) & (b < 65) &
        ((r - b) > 120) & ((g - b) > 80)
    ) & excl
    result = _eval_mask(gold_mask)
    if result is not None:
        return int(result * 384 / scale_w)

    # ── WARIANT 2: Czerwony kursor + biale piksele mieczy ──────────────────
    # Samo czerwone kolko = nierozroznialne od HP bar → potrzebujemy
    # bialych pikseli mieczy w blizkim sasiedztwie jako weryfikacji.
    red_mask = (
        (r > 150) & (g < 90) & (b < 90) &
        ((r - g) > 70) & ((r - b) > 70)
    ) & excl
    result_r = _eval_mask(red_mask)
    if result_r is not None:
        # Weryfikacja: czy sa biale piksele (miecze) w promieniu 20px?
        cx = result_r
        white_mask = (
            (r > 175) & (g > 175) & (b > 160)
        ) & excl
        # Okno 40px wokol kursora
        half = int(20 * dim_s)
        rows_r = np.where(red_mask.sum(axis=1) > 0)[0]
        if len(rows_r) > 0:
            ry = int(rows_r.mean())
            rx_lo = max(0, cx - half)
            rx_hi = min(w, cx + half)
            ry_lo = max(0, ry - half)
            ry_hi = min(h, ry + half)
            if white_mask[ry_lo:ry_hi, rx_lo:rx_hi].sum() >= max(2, int(2 * s)):
                return int(result_r * 384 / scale_w)

    return None


# ─── Glowne funkcje ───────────────────────────────────────────────────────────

def find_action_crop_x(video_path: str, clip_start: float, clip_end: float,
                        source_w: int = 1920, source_h: int = 1080,
                        crop_w: int = 608) -> int:
    """
    Analizuje klip i zwraca optymalny x dla cropa 9:16.
    Priorytet: zolty HP bar → motion diff.
    """
    print(f"Smart Camera: analiza centrum akcji ({clip_end - clip_start:.1f}s)...")

    scale_w, scale_h = 384, 216
    scale_factor = source_w / scale_w      # 1920/384 = 5.0
    hud_cutoff   = int(scale_h * 0.80)    # dolne 20% = HUD
    top_cutoff   = int(scale_h * 0.08)    # gorne 8% = scoreboard

    try:
        frames = extract_sample_frames(video_path, clip_start, clip_end,
                                        n_frames=12,
                                        scale_w=scale_w, scale_h=scale_h)
        if not frames:
            raise ValueError("Brak klatek")

        # Sprobuj wykryc championa przez HP bary (zolty gracz + czerwone wrogowie)
        champion_xs = []
        for frame in frames:
            _, fight_x, bar_count = _detect_fight_center_x(frame, hud_cutoff, top_cutoff)
            if fight_x is not None:
                champion_xs.append(fight_x)

        if champion_xs:
            champion_center_small = float(np.median(champion_xs))
            action_center = int(champion_center_small * scale_factor)
            print(f"   \U0001f7e1 Fight center: {len(champion_xs)}/{len(frames)} klatek | "
                  f"x={action_center}px")
        else:
            # Fallback: srodek ekranu (motion diff ciagnie do VFX!)
            action_center = source_w // 2
            print(f"   \u26a0\ufe0f  HP bars not found \u2192 fallback do centrum")

        x = max(0, min(action_center - crop_w // 2, source_w - crop_w))
        offset = action_center - source_w // 2
        direction = "lewo" if offset < 0 else "prawo"
        print(f"   📍 action_center={action_center}px ({abs(offset)}px {direction} od centrum)")
        print(f"   ✂️  crop_x={x}")
        return x

    except Exception as e:
        print(f"   Smart Camera error: {e} — fallback do centrum")
        return (source_w - crop_w) // 2


def find_action_path(video_path: str, clip_start: float, clip_end: float,
                     source_w: int = 1920, source_h: int = 1080,
                     crop_w: int = 608, n_samples: int = 90,
                     peaks: list = None) -> list:
    """
    Analizuje ruch klatka po klatce i zwraca ścieżkę (t, x) dla dynamicznego kadrowania.
    v11 Stateful HD Trajectory Tracker:
      - Próbkowanie w rozdzielczości 640x360 (precyzyjna geometria pasków HP championa).
      - Ciągły Nearest-Neighbor Trajectory Tracker: eliminuje skakanie kamery na odległych sojuszników (np. Smoldera na tyłach).
      - Śledzi aktywnego gracza w walce i utrzymuje cel w idealnym centrum kadru 9:16.
    """
    print(f"Smart Camera: analiza sciezki ruchu ({clip_end - clip_start:.1f}s)...")

    scale_w, scale_h = 640, 360
    scale_factor = source_w / scale_w
    duration  = clip_end - clip_start
    default_x = (source_w - crop_w) // 2

    try:
        # Load sample frames at full 1080p for exact pixel precision
        frames = extract_sample_frames(video_path, clip_start, clip_end,
                                       n_frames=n_samples,
                                       scale_w=1920, scale_h=1080)
        if len(frames) < 2:
            raise ValueError("Za mało klatek do analizy ruchu")

        t_points = np.linspace(0.0, duration, len(frames))

        # ── Step 1: Auto-discover player Level Badge from first frames ──
        frames_bgr = [cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2BGR) for f in frames]
        templates = []
        init_x = float(source_w // 2)

        for f_idx in range(min(12, len(frames))):
            f_init = frames[f_idx]
            r, g, b = f_init[:, :, 0], f_init[:, :, 1], f_init[:, :, 2]
            # Gold HP bar mask (RGB channels from extract_sample_frames)
            gold_m = ((r > 160) & (g > 130) & (b < 100) & ((r - b) > 55) & ((g - b) > 35))
            gold_m[:100, :] = False
            gold_m[880:, :] = False
            gold_m[600:, 1450:] = False
            gold_m[650:, :300] = False
            
            num_l, _, stats, cents = cv2.connectedComponentsWithStats(gold_m.astype(np.uint8))
            cands = []
            for ci in range(1, num_l):
                cx, cy, cw, ch, area = stats[ci]
                aspect = cw / max(ch, 1)
                if area >= 100 and 30 <= cw <= 130 and 4 <= ch <= 20 and aspect >= 2.5 and 200 <= cx <= 1650:
                    cands.append((ci, cx, cy, cw, ch, area, aspect))
            
            if cands:
                best_c = max(cands, key=lambda c: c[5]) # largest area is player HP bar
                ci, cx, cy, cw, ch, area, aspect = best_c
                bx0 = max(0, cx - 65)
                bx1 = min(1920, cx + 15)
                by0 = max(0, cy - 15)
                by1 = min(1080, cy + 25)
                tmpl = frames_bgr[f_idx][by0:by1, bx0:bx1].copy()
                templates.append(tmpl)
                init_x = float(cx)
                break

        print(f"   🎯 Player Badge auto-discovery: {'OK' if templates else 'Fallback to Color Tracker'} (init_x={init_x:.0f}px)")

        # ── Step 2: Full-Frame Multi-Template Champion Tracking ──
        raw_points = []
        track_x = init_x

        for i in range(len(frames)):
            t = t_points[i]
            fb = frames_bgr[i]
            cand_x = None
            best_score = 0.0

            # Option A: Match against all discovered player templates in active gameplay area
            if templates:
                roi_x0, roi_x1 = 80, 1840
                roi_y0, roi_y1 = 120, 850
                roi = fb[roi_y0:roi_y1, roi_x0:roi_x1]

                for tmpl in templates:
                    if roi.shape[0] >= tmpl.shape[0] and roi.shape[1] >= tmpl.shape[1]:
                        res = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, max_loc = cv2.minMaxLoc(res)
                        if max_val > best_score and max_val >= 0.55:
                            best_score = max_val
                            cand_x = float(roi_x0 + max_loc[0] + tmpl.shape[1] // 2 + 25) # center on champion

            # Option B: Fallback to Gold HP Bar
            if cand_x is None:
                f = frames[i]
                r, g, b = f[:, :, 0], f[:, :, 1], f[:, :, 2]
                gold_m = ((r > 160) & (g > 130) & (b < 100) & ((r - b) > 55) & ((g - b) > 35))
                gold_m[:100, :] = False
                gold_m[880:, :] = False
                gold_m[600:, 1450:] = False
                gold_m[650:, :300] = False
                num_l, _, stats, cents = cv2.connectedComponentsWithStats(gold_m.astype(np.uint8))
                gold_cands = []
                for ci in range(1, num_l):
                    cx, cy, cw, ch, area = stats[ci]
                    aspect = cw / max(ch, 1)
                    if 20 <= cw <= 130 and 4 <= ch <= 22 and aspect >= 2.0 and 150 <= cx <= 1750:
                        gold_cands.append((cents[ci][0], abs(cents[ci][0] - track_x), area, ci, cx, cy))
                if gold_cands:
                    gold_cands.sort(key=lambda c: c[1])
                    cand_x = float(gold_cands[0][0])
                    best_score = 0.50
                    # Auto-discover new level badge if player leveled up
                    if gold_cands[0][2] >= 140 and len(templates) < 3:
                        ci_g, cx_g, cy_g = gold_cands[0][3], gold_cands[0][4], gold_cands[0][5]
                        bx0 = max(0, cx_g - 65)
                        bx1 = min(1920, cx_g + 15)
                        by0 = max(0, cy_g - 15)
                        by1 = min(1080, cy_g + 25)
                        new_tmpl = fb[by0:by1, bx0:bx1].copy()
                        if new_tmpl.shape[0] > 10 and new_tmpl.shape[1] > 10:
                            templates.append(new_tmpl)
                else:
                    # Player is in action / channel / untargetable — maintain previous position
                    cand_x = track_x
                    best_score = 0.0

            # Dynamic exponential smoothing (responsiveness: 0.85/0.15)
            track_x = 0.85 * cand_x + 0.15 * track_x

            # Safe crop 9:16 bounds
            crop_x = int(max(0, min(track_x - crop_w // 2, source_w - crop_w)))
            raw_points.append((t, crop_x))

        print(f"   🎥 Universal Champion Tracker: {len(raw_points)} klatek przetworzonych (v17 True-Lock)")

        # ── Temporal smoothing (window=5) ──
        raw_xs = np.array([p[1] for p in raw_points], dtype=float)
        win = 5
        smoothed = np.array([
            raw_xs[max(0, i-win//2):min(len(raw_xs), i+win//2+1)].mean()
            for i in range(len(raw_xs))
        ])
        smoothed = np.clip(smoothed, 0, source_w - crop_w).astype(int)

        full_points = [(t, int(x)) for (t, _), x in zip(raw_points, smoothed)]

        # ── Downsample to 14-16 keyframes for clean FFmpeg expression ──
        target_keys = 14
        step = max(1, len(full_points) // target_keys)
        final_points = full_points[::step]
        if full_points[-1] not in final_points:
            final_points.append(full_points[-1])

        print(f"   Wygenerowano {len(final_points)} kluczowych punktów kamery (v16 True-Lock)")
        return final_points

    except Exception as e:
        print(f"   Smart Camera error: {e} -- fallback centrum")
        return [(0.0, default_x), (duration, default_x)]



# ─── FFmpeg pan expression ────────────────────────────────────────────────────

def generate_ffmpeg_pan_expression(points: list) -> str:
    """
    Generuje zwięzłe wyrażenie FFmpeg interpolujące pozycję x w czasie t.
    """
    if not points:
        return "656"   # fallback: centrum 1920px → crop 608px
    if len(points) == 1:
        return f"{int(points[0][1])}"

    expr = f"{int(points[-1][1])}"
    for i in range(len(points) - 2, -1, -1):
        t_curr, x_curr = points[i]
        t_next, x_next = points[i+1]
        dt = t_next - t_curr
        dx = x_next - x_curr
        if dt > 1e-4:
            interp = f"{int(x_curr)}+{dx:.1f}*(t-({t_curr:.2f}))/{dt:.2f}"
        else:
            interp = f"{int(x_curr)}"
        expr = f"if(lt(t,{t_next:.2f}),{interp},{expr})"
    return expr


# ─── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys as _sys
    test_clip = _sys.argv[1] if len(_sys.argv) > 1 else r"C:\Medal\test.mp4"
    if os.path.exists(test_clip):
        path = find_action_path(test_clip, 0, 14.2)
        expr = generate_ffmpeg_pan_expression(path)
        print("\nSciezka ruchu:")
        for t, x in path:
            print(f"  t={t:.2f}s -> x={x}px")
        print(f"\nWyrazenie FFmpeg:\n{expr[:300]}...")
    else:
        print(f"Nie znaleziono: {test_clip}")
