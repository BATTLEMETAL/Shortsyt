"""
LOL Agent — Precyzyjny Detektor Fragów i Sytuacji Clutch (Computer Vision + OCR)
Automatycznie klasyfikuje:
  - PENTAKILL (5 eliminacji)
  - QUADRAKILL (4 eliminacje)
  - TRIPLE KILL (3 eliminacje)
  - DOUBLE KILL (2 eliminacje)
  - CLUTCH 1% HP (walka wygrana przy skrajnie niskim zdrowiu <= 20% HP)
  - OUTPLAY (solowe ogranie mechaniczne / shutdown)
"""
import os
import sys
import re
import cv2
import numpy as np
import threading
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field, replace

_FRAG_CACHE: Dict[Tuple[str, int, int, float], "FragAnalysisResult"] = {}
_FRAG_CACHE_LOCK = threading.Lock()

try:
    import pytesseract
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


# LoL HUD Coordinates for 1920x1080 / 16:9
# Dolny pasek zdrowia bohatera (szerokie pasmo wspierające różne skale HUD w LoL):
HP_BAR_ROI = (0.860, 0.988, 0.400, 0.620)  # y_start, y_end, x_start, x_end
# Czerwony vignette / ostrzeżenie o krytycznym zdrowiu (krawędzie ekranu):
VIGNETTE_ROI_TOP = (0.01, 0.10, 0.20, 0.80)
# Baner zabójstw na środku góry ekranu:
KILL_BANNER_ROI = (0.04, 0.28, 0.18, 0.82)
# Kill feed w prawym górnym rogu:
KILL_FEED_ROI = (0.04, 0.25, 0.65, 0.98)


@dataclass
class FragAnalysisResult:
    video_path: str
    duration: float
    detected_frag_type: str        # 'pentakill' | 'quadrakill' | 'triple' | 'double' | 'clutch' | 'outplay'
    confidence: float              # 0.0 - 1.0
    kill_count: int                # Liczba wykrytych fragów
    kills: List[Dict[str, Any]]    # [{'timestamp': 14.2, 'label': 'DOUBLE KILL', 'type': 'double'}]
    min_hp_percentage: float       # Najniższy poziom HP (0 - 100%)
    is_clutch_1hp: bool            # True jeśli HP spadło <= 20%
    badge_label: str               # 'PENTAKILL' | '1% HP CLUTCH' | 'QUADRA KILL' | 'TRIPLE KILL' | 'DOUBLE KILL' | 'INSANE OUTPLAY'
    suggested_title_hook: str      # Sugerowany haczyk tytułu
    suggested_badge_color: str     # Kolor badge'a (hex)
    combat_segments: Optional[List[Tuple[float, float]]] = None
    has_jump_cut: bool = False
    objective_secured: bool = False
    objective_label: str = ""
    ally_banner_blocked: bool = False


def _measure_player_hp(frame: np.ndarray) -> Optional[float]:
    """
    Mierzy procent napełnienia paska zdrowia bohatera w dolnym HUD (0.0 - 100.0%).
    Dynamicznie lokalizuje poziomy pasek zieleni/tarczy w paśmie HP_BAR_ROI (działa przy każdej skali HUD
    i odrzuca 1-pikselowe linie obramowania HUD lub śnieg na zimowej mapie).
    """
    h, w = frame.shape[:2]
    ys, ye = int(h * HP_BAR_ROI[0]), int(h * HP_BAR_ROI[1])
    xs, xe = int(w * HP_BAR_ROI[2]), int(w * HP_BAR_ROI[3])

    roi = frame[ys:ye, xs:xe]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask_green = cv2.inRange(hsv, (35, 70, 60), (95, 255, 255))
    mask_shield = cv2.inRange(hsv, (0, 0, 180), (180, 40, 255))

    row_green_ratio = (mask_green > 0).mean(axis=1)
    idxs = np.where(row_green_ratio >= 0.03)[0]
    clusters: List[List[int]] = []
    cur: List[int] = []
    for r in idxs:
        r_i = int(r)
        if not cur or r_i == cur[-1] + 1:
            cur.append(r_i)
        else:
            clusters.append(cur)
            cur = [r_i]
    if cur:
        clusters.append(cur)

    bars = [c for c in clusters if len(c) >= 4]
    if not bars:
        return None

    best = max(bars, key=lambda c: float(row_green_ratio[c].sum()))
    strip_g = mask_green[best[0]:best[-1] + 1]
    strip_s = mask_shield[best[0]:best[-1] + 1]
    if float((strip_g > 0).mean()) < 0.03:
        return None

    col_has_hp = np.any((strip_g > 0) | (strip_s > 0), axis=0)
    total_cols = len(col_has_hp)
    if total_cols == 0:
        return None

    ratio = (float(np.sum(col_has_hp)) / float(total_cols)) * 100.0
    return max(0.0, min(100.0, ratio))


def _detect_critical_low_hp_vignette(frame: np.ndarray) -> bool:
    """Wykrywa czerwony błysk / pulsowanie ekranu przy skrajnie niskim HP (<15%)."""
    h, w = frame.shape[:2]
    ys, ye = int(h * VIGNETTE_ROI_TOP[0]), int(h * VIGNETTE_ROI_TOP[1])
    xs, xe = int(w * VIGNETTE_ROI_TOP[2]), int(w * VIGNETTE_ROI_TOP[3])
    
    roi = frame[ys:ye, xs:xe]
    if roi.size == 0:
        return False

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask_red1 = cv2.inRange(hsv, (0, 120, 100), (10, 255, 255))
    mask_red2 = cv2.inRange(hsv, (170, 120, 100), (180, 255, 255))
    red_count = cv2.countNonZero(cv2.bitwise_or(mask_red1, mask_red2))
    return red_count > (roi.shape[0] * roi.shape[1] * 0.15)


def _scan_ocr_for_kills(frame: np.ndarray) -> Tuple[int, str, bool]:
    """
    Wykrywa napisy zabójstw z rygorystycznym filtrem własności gracza (Player Kill Ownership Guard):
    Zwraca: (tier: int, label: str, is_player_kill: bool)
    
    Zabezpieczenia:
      1. ODRZUCA śmierć gracza ('YOU HAVE BEEN SLAIN', 'EXECUTED')
      2. ODRZUCA multikille wrogów ('ENEMY PENTAKILL', 'ENEMY QUADRAKILL', czerwone banery)
      3. ODRZUCA multikille sojuszników ('AN ALLY HAS SCORED A QUADRAKILL' / 'AN ENEMY HAS BEEN SLAIN')
      4. AKCEPTUJE TYLKO własne zabójstwa gracza (złote banery 'YOU HAVE SLAIN', złote multikille, popupy '+300g')
    """
    if not OCR_AVAILABLE:
        return 0, "", False

    h, w = frame.shape[:2]
    fallback_non_player_label = ""
    for roi_coords in (KILL_BANNER_ROI, KILL_FEED_ROI):
        ys, ye = int(h * roi_coords[0]), int(h * roi_coords[1])
        xs, xe = int(w * roi_coords[2]), int(w * roi_coords[3])
        roi = frame[ys:ye, xs:xe]
        if roi.size == 0:
            continue

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask_gold  = cv2.inRange(hsv, (10, 80, 140), (45, 255, 255))
        mask_white = cv2.inRange(hsv, (0, 0, 190), (180, 50, 255))
        mask_red1  = cv2.inRange(hsv, (0, 120, 100), (10, 255, 255))
        mask_red2  = cv2.inRange(hsv, (170, 120, 100), (180, 255, 255))
        mask_red   = cv2.bitwise_or(mask_red1, mask_red2)
        mask_blue  = cv2.inRange(hsv, (100, 100, 100), (135, 255, 255))

        gold_cnt = cv2.countNonZero(mask_gold)
        white_cnt = cv2.countNonZero(mask_white)
        red_cnt = cv2.countNonZero(mask_red)
        blue_cnt = cv2.countNonZero(mask_blue)

        # Pre-filter: pomijaj puste klatki oraz biały śnieg w prawym górnym kill-feedzie
        if roi_coords == KILL_FEED_ROI and gold_cnt < 220 and red_cnt < 380:
            continue
        if (gold_cnt + white_cnt) < 40:
            continue

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
        thresh_up = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        texts_to_check = []
        try:
            t_ocr = pytesseract.image_to_string(thresh_up, config="--psm 6 --oem 1").strip().lower()
            if t_ocr:
                texts_to_check.append(t_ocr)
        except Exception:
            t_ocr = ""

        # Zapasowe wywołanie na surowym ROI tylko przy wyraźnym złotym błysku bez słów kluczowych
        has_kw = bool(re.search(r'(?:kill|doub|trip|quad|pent|slain|dwan|ally|enem|legend|ramp|god|unstop|shut|blood)', t_ocr))
        if gold_cnt >= 300 and not has_kw:
            try:
                t_raw = pytesseract.image_to_string(roi, config="--psm 6 --oem 1").strip().lower()
                if t_raw:
                    texts_to_check.append(t_raw)
            except Exception:
                pass

        text = " | ".join(texts_to_check)
        if not text:
            continue

        # ── 1. FILTR ŚMIERCI GRACZA ──
        if re.search(r'(?:you\s*have\s*been\s*slain|executed|you\s*died)', text):
            return 0, "PLAYER_DEATH", False

        # ── 2. FILTR MULTIKILLI WROGÓW ──
        # Baner multikilla wroga zawiera słowo 'enemy' bezpośrednio przed kill/penta/itp.
        # UWAGA: NIE odrzucamy przez sam red_cnt, bo banery gracza (zwłaszcza Double/Triple) oraz spelle mają czerwone akcenty!
        if re.search(r'(?:enemy\s*(?:penta|quadra|triple|double|kill)|an\s*ally\s*has\s*been\s*slain)', text):
            return 0, "ENEMY_KILL", False

        # ── 3. DETEKCJA EPICKICH OBIEKTÓW (Smok / Baron / Herald) ──
        if re.search(r'(?:your\s*team\s*has\s*slain\s*the|slain\s*the\s*(?:infernal|mountain|ocean|cloud|hextech|chemtech|elder)?\s*(?:drake|dragon|baron|herald)|stolen\s*the\s*(?:drake|dragon|baron))', text):
            return 0, "OBJECTIVE_SLAIN", False

        # ── 4. FILTR FRAGÓW SOJUSZNIKÓW I WIEŻ (TEAMMATE / TURRET BANNERS) ──
        # Zimowa mapa (Winter Rift) daje >20k niebieskich pikseli w tle, więc filtrujemy po tekście OCR zamiast po blue_cnt.
        is_dwann = bool(re.search(r'dwan|enga|wann|nnel|you\s*have\s*slain|\+(?:400|300|150|1000|[0-9]{3})', text))
        if re.search(r'an\s*ally\s*has\s*scored', text):
            fallback_non_player_label = fallback_non_player_label or "ALLY_MULTIKILL"
            continue
        if re.search(r'(?:an\s*enemy\s*has\s*been\s*slain|ally\s*slain|ally\s*turret\s*destroyed|turret\s*destroyed|inhibitor\s*destroyed)', text) and not is_dwann:
            fallback_non_player_label = fallback_non_player_label or "ALLY_KILL"
            continue

        # ── 5. POTWIERDZONE WŁASNE FRAGI GRACZA (PLAYER KILLS) ──
        # Złoty baner lub wyraźny komunikat PENTAKILL / QUADRA / TRIPLE / DOUBLE / RAMPAGE / YOU HAVE SLAIN
        if re.search(r'penta(?:kill|kut|kit|kil|\s*kill)?', text):
            return 5, "PENTAKILL", True
        if re.search(r'quadra(?:kill|kut|kit|kil|\s*kill)?', text):
            return 4, "QUADRAKILL", True
        if re.search(r'tri[pbl][ilf1u][eif]?(?:kill|kut|kit|kil|kin|ktl|\s*ki[a-z]*)?|tri[pbl][rl]e?(?:kill|kut|kit|kil|\s*kill)?|treple\s*ki[a-z]*|tripue[a-z]*|trie[re]\s*ki|[sr]riper?\s*ki|[st]e?ipre\s*ki|reiprek|[sr]riprr', text):
            return 3, "TRIPLE KILL", True
        if re.search(r'dou[brv][bl]e?(?:kill|kut|kit|kil|\s*kill)?|doue?le\s*ki|doublekinlt|pous[ct]e\s*ki[a-z]*', text):
            return 2, "DOUBLE KILL", True
        if re.search(r'first\s*bloo[mdr]|1st\s*blood|first\s*rlood', text):
            return 1, "FIRST BLOOD", True
        if is_dwann and re.search(r'ram[pn]a[gc]e|is\s*on\s*a\s*ram|is\s*(?:leg|f|t)[ea]?g?[eo]ndary\w*|isfeendary|itlegondary|kill(?:ing)?\s*s[pn]r[ea]e|is\s*on\s*a\s*kill|is\s*on\s*a\s*s[pn]r|shut\s*down|shutdown|legendary|godlike|unstoppable', text):
            return 1, "OUTPLAY", True
        if re.search(r'(?:you\s*have\s*slain|\+(?:400|300|150|1000))', text):
            return 1, "KILL", True

    return 0, fallback_non_player_label, False


def find_combat_start_before(
    video_path: str,
    first_kill_t: float,
    max_lookback: float = 8.0
) -> float:
    """
    Skanuje WSTECZ od pierwszego killa (od `first_kill_t - 0.3s` do `max_lookback`),
    szukając ciągłego okna walki z obecnością wrogiego championa (`e_px > 420`).
    Przerywa natychmiast po 2 kolejnych pustych próbkach, aby nie zasysać martwego farmienia minionów.
    """
    if not video_path or not os.path.exists(video_path):
        return max(0.0, first_kill_t - 2.2)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return max(0.0, first_kill_t - 2.2)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    search_floor = max(0.0, first_kill_t - max_lookback)
    t_hi = max(search_floor, first_kill_t - 0.3)
    samples = np.arange(t_hi, max(-0.01, search_floor - 0.01), -0.35)
    earliest_combat = max(0.0, first_kill_t - 2.2)

    try:
        from lol_agent.lol_quality_validator import _check_combat_in_frame, _check_enemy_combat_in_frame
    except ImportError:
        try:
            from lol_quality_validator import _check_combat_in_frame, _check_enemy_combat_in_frame
        except ImportError:
            _check_combat_in_frame = None
            _check_enemy_combat_in_frame = None

    try:
        quiet_streak = 0
        confirmed_any = False
        for t in samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, fr = cap.read()
            if not ret or fr is None:
                continue
            has_combat = False
            if _check_enemy_combat_in_frame:
                he, e_px, _ = _check_enemy_combat_in_frame(fr)
                if he and e_px > 420:
                    has_combat = True
            if not has_combat and _check_combat_in_frame:
                hc, c_px, _ = _check_combat_in_frame(fr)
                if hc and c_px > 650:
                    has_combat = True

            if has_combat:
                confirmed_any = True
                earliest_combat = float(t)
                quiet_streak = 0
            else:
                quiet_streak += 1
                if quiet_streak >= 2 and (confirmed_any or (first_kill_t - float(t)) >= 2.2):
                    break
    finally:
        cap.release()

    return round(earliest_combat, 2)


def find_lethal_strike_moment(
    video_path: str,
    banner_timestamp: float,
    max_lookback: float = 4.0
) -> float:
    """
    Precyzyjnie ustala moment decydującego ciosu (last-hit / lethal strike) przed pojawieniem się banera killa.
    W League of Legends banery (Double/Triple/Spree) mają opóźnienie 1.5s - 2.8s po śmierci wroga.
    Wykrywa:
      1. Rozbłysk złota (+300g / +gold popup w play area).
      2. Moment zniknięcia paska HP wroga (czerwony pasek spada do 0 po aktywnej walce).
    Zwraca: dokładny timestamp uderzenia eliminującego (ostatni skill / auto-attack).
    """
    if not video_path or not os.path.exists(video_path):
        return max(0.5, round(banner_timestamp - 1.2, 2))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return max(0.5, round(banner_timestamp - 1.2, 2))

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    t_start = max(0.0, banner_timestamp - max_lookback)
    t_end = max(0.0, banner_timestamp - 0.25)
    samples = np.arange(t_start, t_end + 0.05, 0.1)

    gold_scores = []
    enemy_bars = []

    try:
        for t in samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, fr = cap.read()
            if not ret or fr is None:
                continue
            h, w = fr.shape[:2]

            # 1. Złote piksele nagrody (+300g / popup śmierci wroga)
            hsv = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)
            gold_m = cv2.inRange(hsv, (18, 140, 160), (35, 255, 255))
            gold_play = gold_m[int(h * 0.2):int(h * 0.75), int(w * 0.2):int(w * 0.8)]
            gold_px = int(cv2.countNonZero(gold_play))
            gold_scores.append((t, gold_px))

            # 2. Paski HP wrogów
            m1 = cv2.inRange(hsv, (0, 120, 140), (10, 255, 255))
            m2 = cv2.inRange(hsv, (170, 120, 140), (180, 255, 255))
            red_m = cv2.bitwise_or(m1, m2)
            red_m[int(h * 0.82):, :] = 0
            red_m[:int(h * 0.10), :] = 0
            red_m[int(h * 0.70):, int(w * 0.75):] = 0
            cnts, _ = cv2.findContours(red_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            nbars = sum(1 for c in cnts if 20 <= cv2.boundingRect(c)[2] <= 160 and 4 <= cv2.boundingRect(c)[3] <= 20)
            enemy_bars.append((t, nbars))
    finally:
        cap.release()

    # Znajdź ostatni pik złota bezpośrednio poprzedzający baner (konkretny cios eliminujący dla tego komunikatu)
    gold_peaks = [g for g in gold_scores if g[1] >= 600]
    if gold_peaks:
        max_gold_t, max_gold_val = gold_peaks[-1]
    else:
        max_gold_t, max_gold_val = max(gold_scores, key=lambda x: x[1]) if gold_scores else (None, 0)

    # Szukaj momentu zniknięcia paska HP wroga
    death_t = None
    for i in range(len(enemy_bars) - 1, 0, -1):
        t_curr, b_curr = enemy_bars[i]
        t_prev, b_prev = enemy_bars[i - 1]
        if b_prev > 0 and b_curr == 0 and (max_gold_t is None or abs(t_curr - max_gold_t) <= 1.2):
            death_t = t_prev
            break

    if max_gold_t and max_gold_val > 500:
        # Cios decydujący (last-hit) następuje ~0.4s-0.5s przed pełnym rozbłyskiem cyfr złota
        lethal_hit_t = max(0.5, round(max_gold_t - 0.45, 2))
        return lethal_hit_t
    elif death_t is not None:
        return max(0.5, round(death_t, 2))
    else:
        return max(0.5, round(banner_timestamp - 1.2, 2))



def find_solo_bolo_window(
    video_path: str,
    kill_t: float,
    total_dur: float
) -> Tuple[float, float, float]:
    """
    Wyznacza okno dla akcji SOLO BOLO (1v1):
      - Gdy akcja rozpoczyna się od początku klipu lub kill jest w pierwszych 14.5s:
        Bierzemy pierwsze 15 sekund (0.0s do 15.0s) bez żadnego wycinania początku!
      - Cała walka bez żadnych cięć (bez jump-cut).
      - Długość: idealnie 15.0s (złoty standard Shorts).
    """
    # Jeśli kill jest w pierwszych 5.5 sekundach klipu:
    # Akcja rozpoczyna się od samego początku
    if kill_t <= 5.5:
        start_t = 0.0
        end_t = min(round(total_dur, 1), round(kill_t + 1.8, 1))
        peak_moment = max(1.0, round(kill_t, 1))
        return start_t, end_t, peak_moment

    if not video_path or not os.path.exists(video_path):
        start_t = max(0.0, round(kill_t - 6.0, 1))
        end_t = min(round(total_dur, 1), round(kill_t + 1.8, 1))
        return start_t, end_t, max(1.0, round(kill_t - start_t, 1))

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        start_t = max(0.0, round(kill_t - 6.0, 1))
        end_t = min(round(total_dur, 1), round(kill_t + 1.8, 1))
        return start_t, end_t, max(1.0, round(kill_t - start_t, 1))

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    search_start = max(0.0, kill_t - 12.0)
    search_end = max(search_start + 1.0, kill_t - 2.0)

    prev_gray = None
    motion_history = []

    try:
        for t in np.arange(search_start, search_end, 0.25):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            h, w = frame.shape[:2]
            play_area = frame[int(h * 0.15):int(h * 0.80), int(w * 0.20):int(w * 0.80)]
            gray = cv2.cvtColor(cv2.resize(play_area, (320, 180)), cv2.COLOR_BGR2GRAY)
            m_score = 0.0
            if prev_gray is not None:
                m_score = float(np.mean(cv2.absdiff(gray, prev_gray)))
            prev_gray = gray
            motion_history.append((t, m_score))
    finally:
        cap.release()

    engage_t = None
    for t, m in motion_history:
        if m >= 9.0:
            engage_t = t
            break

    if engage_t is not None:
        start_t = max(0.0, round(engage_t - 1.5, 1))
    else:
        start_t = max(0.0, round(kill_t - 5.5, 1))

    # Tylko jeśli start wypada bardzo blisko początku (<= 1.5s), bierzemy od 0.0s
    if start_t <= 1.5:
        start_t = 0.0

    end_t = min(round(total_dur, 1), round(kill_t + 1.8, 1))
    dur = end_t - start_t
    if dur > 18.0:
        start_t = max(0.0, round(end_t - 18.0, 1))

    peak_moment = max(1.0, round(kill_t - start_t, 1))
    return round(start_t, 1), round(end_t, 1), peak_moment


def compute_optimal_clip_window(
    frag_res: FragAnalysisResult,
    total_dur: float,
    action_type: Optional[str] = None
) -> Tuple[float, float, float, Optional[List[Tuple[float, float]]]]:
    """
    Wyznacza optymalne okno czasowe (clip_start, clip_end, peak_moment) oraz segmenty jump-cut
    na podstawie detekcji OCR i aktywnego profilu pacingu (Ekstremalnie Szybkie / Zbalansowane / Cinematic).
    Dla SOLO BOLO (1v1) gwarantuje brak cięć (ciągła walka) oraz wejście z buta ~1.2s przed doskokiem.
    """
    act = (action_type or frag_res.detected_frag_type or "").lower()
    real_kills = [k for k in frag_res.kills if k.get("tier", 1) >= 2 or k.get("timestamp", 0) > 1.0]

    # ── SPECJALNY TRYB SOLO BOLO (1v1) ──
    if "solo" in act or "1v1" in act or act == "solo_bolo" or "first" in act:
        kill_t = real_kills[-1]["timestamp"] if real_kills else (total_dur * 0.65)
        s, e, p = find_solo_bolo_window(frag_res.video_path, kill_t, total_dur)
        return s, e, p, None  # Brak jump-cutów! Cała walka bez cięć

    try:
        from lol_agent.tuning_manager import get_pacing_parameters
    except ImportError:
        try:
            from tuning_manager import get_pacing_parameters
        except ImportError:
            get_pacing_parameters = lambda: {
                "buildup_sec": 0.8, "outro_sec": 1.5,
                "target_min_dur": 10.0, "target_max_dur": 13.0
            }

    p = get_pacing_parameters()
    buildup = float(p.get("buildup_sec", 0.8))
    outro = float(p.get("outro_sec", 1.5))
    min_dur = float(p.get("target_min_dur", 10.0))
    max_dur = float(p.get("target_max_dur", 13.0))

    if real_kills:
        # Sprawdź czy kille dzielą się na oddzielne klastry walki rozdzielone przerwą > 3.5s
        clusters = []
        current = []
        for k in real_kills:
            if not current:
                current.append(k)
            else:
                if k["timestamp"] - current[-1]["timestamp"] <= 3.5:
                    current.append(k)
                else:
                    clusters.append(current)
                    current = [k]
        if current:
            clusters.append(current)

        # Jeśli całkowity czas walki mieści się w dopuszczalnym limicie (do 28s dla multikilli),
        # lub przerwa między klastrami zawiera aktywną walkę (np. zabójstwo bez banera lub wymianę ciosów),
        # montujemy jako jedną płynną, ciągłą akcję bez cięć!
        lead_in = max(1.5, min(2.5, buildup))
        total_span = (real_kills[-1]["timestamp"] + max(outro, 2.0)) - (real_kills[0]["timestamp"] - lead_in)

        # Sprawdź czy przerwa między klastrami zawiera aktywną walkę (aby nie wyciąć np. fraga Jhina pod wieżą):
        gap_has_combat = False
        if len(clusters) >= 2:
            try:
                from lol_agent.lol_quality_validator import _check_enemy_combat_in_frame
                cap = cv2.VideoCapture(frag_res.video_path)
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                g_start = clusters[0][-1]["timestamp"] + 1.2
                g_end = clusters[1][0]["timestamp"] - 1.2
                if g_end > g_start + 1.0:
                    test_samples = np.linspace(g_start, g_end, 5)
                    c_count = 0
                    for ts in test_samples:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
                        ret, fr = cap.read()
                        if ret:
                            has_c, px, _ = _check_enemy_combat_in_frame(fr)
                            if has_c and px > 400:
                                c_count += 1
                    if c_count >= 2:
                        gap_has_combat = True
                cap.release()
            except Exception:
                pass

        if getattr(frag_res, "objective_secured", False):
            gap_has_combat = True
        allow_jump_cut = (len(clusters) >= 2) and (not gap_has_combat) and (total_span > max(26.0, max_dur + 3.0))
        if allow_jump_cut:
            segments = []
            engage_lead = max(3.5, buildup * 2.5)

            for i, c in enumerate(clusters):
                c_start = c[0]["timestamp"]
                c_end = c[-1]["timestamp"]
                if i == 0:
                    s = max(0.0, round(c_start - lead_in, 1))
                    e = round(c_end + 1.5, 1)
                elif i == len(clusters) - 1:
                    s = max(0.0, round(c_start - engage_lead, 1))
                    e = min(round(total_dur, 1), round(c_end + max(outro, 2.0), 1))
                else:
                    s = max(0.0, round(c_start - engage_lead, 1))
                    e = round(c_end + 1.2, 1)
                segments.append((s, e))

            # Scal jeśli któryś segment nachodzi lub przerwa wynosi <= 1.5s (brak mikro-cięć)
            merged_segs = [segments[0]]
            for s, e in segments[1:]:
                if s <= (merged_segs[-1][1] + 1.5):
                    merged_segs[-1] = (merged_segs[-1][0], max(merged_segs[-1][1], e))
                else:
                    merged_segs.append((s, e))

            if len(merged_segs) >= 2:
                # Oblicz peak moment na sklejonej osi czasu
                cum_dur = 0.0
                last_k_mapped = 0.0
                for s, e in merged_segs:
                    for k in real_kills:
                        kt = k["timestamp"]
                        if s <= kt <= e:
                            last_k_mapped = cum_dur + (kt - s)
                    cum_dur += (e - s)

                peak_moment = max(1.0, round(last_k_mapped or (cum_dur - outro), 1))
                clip_start = merged_segs[0][0]
                clip_end = merged_segs[-1][1]
                return clip_start, clip_end, peak_moment, merged_segs

        # Pojedynczy ciągły klaster walki
        first_k = min(float(k["timestamp"]) for k in real_kills)
        last_k = max(float(k["timestamp"]) for k in real_kills)

        # Wykryj precyzyjny moment śmiertelnego ciosu (last-hit) — zaciskamy okno tak by peak nie uciekł za daleko wstecz
        has_real_video = bool(frag_res.video_path and os.path.exists(frag_res.video_path))
        if has_real_video:
            raw_lethal_t = find_lethal_strike_moment(frag_res.video_path, last_k)
            lethal_hit_t = max(max(0.5, last_k - 0.40), min(last_k, raw_lethal_t))
            lookback_s = 7.0 if getattr(frag_res, "ally_banner_blocked", False) else 5.0
            c_start = find_combat_start_before(frag_res.video_path, min(first_k, lethal_hit_t), max_lookback=lookback_s)
        else:
            lethal_hit_t = last_k
            c_start = max(0.0, first_k - 2.0)

        final_kill_t = max(lethal_hit_t, last_k)
        if has_real_video:
            try:
                try:
                    from lol_agent.outplayed_db import get_outplayed_clip_info
                except ImportError:
                    from outplayed_db import get_outplayed_clip_info  # type: ignore
                op_info = get_outplayed_clip_info(frag_res.video_path)
                if op_info and int(op_info.get("event_tier_rank") or 0) >= 2:
                    est_last = op_info.get("est_last_kill_s")
                    if isinstance(est_last, (int, float)) and (last_k + 0.5) <= float(est_last) <= min(total_dur, last_k + 8.0):
                        final_kill_t = max(final_kill_t, float(est_last))
            except Exception:
                pass

        # Dynamiczny finisz z oddechem 1.65s–2.0s po ostatnim fragu (zero ucinania końca walki)
        is_multikill_tier = (len(real_kills) >= 3) or (act in ('triple', 'quadrakill', 'quadra', 'pentakill', 'penta'))
        default_outro = 1.75 if is_multikill_tier else 1.65
        clean_outro = min(1.95, max(default_outro, outro))
        max_allowed_end = min(round(total_dur, 1), round(final_kill_t + 2.0, 1))

        # ── ADAPTACYJNY REŻYSER MONTAŻU (Podejście A vs Podejście B) ──
        kill_count = len(real_kills)
        is_dense_teamfight = (
            (kill_count >= 3)
            or (act in ("triple", "quadrakill", "quadra", "pentakill", "penta"))
            or (has_real_video and (first_k - c_start) < 1.8 and kill_count >= 2)
        )
        is_approach_fit = (
            ("solo" in act or "1v1" in act or act in ("outplay", "clutch", "disrespect", "ego_check", "duel"))
            or (kill_count == 1)
            or (not is_dense_teamfight and (first_k - c_start) >= 2.0)
        )

        if is_approach_fit and not is_dense_teamfight:
            # PODEJŚCIE A: "DOBIEGAM DO AKCJI, WALCZĘ, KOŃCZĘ" (Approach & Context)
            # Pokazuje podejście gracza, inicjację, wymianę ciosów i zwięzły finisz (12-18s)
            approach_lead = min(4.0, max(2.5, buildup * 1.8)) if has_real_video else max(1.5, min(2.5, buildup))
            start = max(0.0, round(c_start - approach_lead, 1))
            if (c_start - start) > 4.5:
                start = max(0.0, round(c_start - 4.5, 1))
            end = min(max_allowed_end, round(final_kill_t + clean_outro, 1))
            target_max = 18.0
            if (end - start) > target_max and len(real_kills) <= 1:
                start = max(0.0, round(end - target_max, 1))
            print(f"   🎬 [Montage Director] Wybrano PODEJŚCIE A (Approach & Context): start={start:.1f}s, end={end:.1f}s (dur={end-start:.1f}s, outro={end-final_kill_t:.1f}s)")
        else:
            # PODEJŚCIE B: "SEKUNDA PRZED SKOKIEM W PRZECIWNIKA" (Instant Chaos Skirmish)
            lead_in = max(1.5, min(2.5, buildup))
            if has_real_video:
                start = max(0.0, round(min(c_start - 0.8, first_k - lead_in), 1))
                if (c_start - start) > 2.5:
                    start = max(0.0, round(c_start - 2.5, 1))
            else:
                start = max(0.0, round(first_k - lead_in, 1))
            end = min(max_allowed_end, round(final_kill_t + clean_outro, 1))
            max_continuous_span = 24.0 if is_multikill_tier else 18.0
            if (end - start) > max_continuous_span:
                start = max(0.0, round(end - max_continuous_span, 1))
            print(f"   ⚡ [Montage Director] Wybrano PODEJŚCIE B (Instant Chaos Skirmish): start={start:.1f}s, end={end:.1f}s (dur={end-start:.1f}s, outro={end-final_kill_t:.1f}s)")

        # Jeśli baner pojawił się tuż po lethal hit, pozwól mu wybrzmieć (ale nigdy powyżej max_allowed_end)
        if has_real_video and last_k > lethal_hit_t and (last_k + 0.6) > end:
            end = min(max_allowed_end, round(last_k + 0.6, 1))

        # Wydłużanie czasu (setup/context) wyłącznie z PRZODU nagrania:
        MIN_SHORT_SPAN = 10.0
        if (end - start) < MIN_SHORT_SPAN and start > 0.0:
            needed = MIN_SHORT_SPAN - (end - start)
            start = max(0.0, round(start - needed, 1))

        # TWARDY BEZPIECZNIK OUTRO: Po ostatnim killu MAX 2.0s do końca klipu!
        end = min(end, max_allowed_end)

        # Retention Lead-In Guard: szybki hook (<= 4.2s do 1. killa, lub <= 5.2s przy epicznym obiekcie), min. 10s
        obj_sec = bool(getattr(frag_res, "objective_secured", False))
        ally_blk = bool(getattr(frag_res, "ally_banner_blocked", False))
        max_lead_in = 5.2 if obj_sec else 4.2
        if real_kills and (first_k - start) > max_lead_in:
            start = max(0.0, round(first_k - max_lead_in, 1))
            if (end - start) < MIN_SHORT_SPAN:
                start = max(0.0, round(end - MIN_SHORT_SPAN, 1))

        # Zabezpieczenie przed ucięciem pierwszego killa
        if start > first_k - 0.8:
            start = max(0.0, round(first_k - 1.0, 1))

        peak_moment = max(0.5, round(lethal_hit_t - start, 1))

        # Dry-Run Symulator & Rollback Guard dla izolowanych pojedynczych killi (>6.0s bez walki)
        if len(real_kills) >= 3 and not obj_sec and not ally_blk and not gap_has_combat:
            rk_times = sorted(float(k["timestamp"]) for k in real_kills)
            rk_gaps = [b - a for a, b in zip(rk_times, rk_times[1:])]
            proposed_win = None
            if rk_gaps and rk_gaps[0] > 6.0 and (len(rk_gaps) == 1 or max(rk_gaps[1:]) <= 4.5):
                p_start = max(0.0, round(rk_times[1] - lead_in, 1))
                p_peak = max(0.5, round(lethal_hit_t - p_start, 1))
                proposed_win = (p_start, end, p_peak)
            elif rk_gaps and rk_gaps[-1] > 6.0 and (len(rk_gaps) == 1 or max(rk_gaps[:-1]) <= 4.5):
                last_k_obj = max(real_kills, key=lambda x: float(x["timestamp"]))
                if int(last_k_obj.get("tier", 1) or 1) < 2:
                    p_end = min(round(total_dur, 1), round(rk_times[-2] + clean_outro, 1))
                    p_peak = max(0.5, round(rk_times[-2] - start, 1))
                    if (p_end - start) >= 8.0:
                        proposed_win = (start, p_end, p_peak)
            if proposed_win is not None:
                try:
                    try:
                        from lol_agent.lol_quality_gate import simulate_and_guard_director_decision
                    except ImportError:
                        from lol_quality_gate import simulate_and_guard_director_decision
                    guard = simulate_and_guard_director_decision(
                        base_window=(start, end, peak_moment),
                        proposed_window=proposed_win,
                        all_kills_abs=rk_times,
                        proposed_style="PRIMARY",
                        objective_secured=obj_sec,
                    )
                    if guard.get("approved"):
                        start, end, peak_moment = guard["selected_window"]
                except Exception:
                    pass

        return start, end, peak_moment, None
    else:
        # ── BRAK WYKRYTYCH KILLI PRZEZ OCR ──
        # Nie bierzemy ślepo początku lub końca — wykrywamy realną walkę przez analizę wrogich pasków HP
        try:
            from lol_agent.lol_quality_validator import _check_enemy_combat_in_frame
            cap = cv2.VideoCapture(frag_res.video_path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            combat_ts = []
            try:
                for t in np.arange(0.0, total_dur, 0.75):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
                    ret, fr = cap.read()
                    if not ret: break
                    has_c, px, _ = _check_enemy_combat_in_frame(fr)
                    if has_c and px >= 350:
                        combat_ts.append(t)
            finally:
                cap.release()

            if combat_ts:
                start = max(0.0, round(combat_ts[0] - 1.2, 1))
                end = min(round(total_dur, 1), round(combat_ts[-1] + 1.2, 1))
                # Bezpiecznik Shorts: okno wizualne nie może przekraczać max_dur (max 13s)
                if (end - start) > max_dur:
                    start = max(0.0, round(end - max_dur, 1))
                peak_moment = max(1.0, round((end - start) * 0.65, 1))
                print(f"   [FragDetector] Okno wyznaczone przez wizualną analizę walki: {start:.1f}s - {end:.1f}s (dur={end-start:.1f}s)")
                return start, end, peak_moment, None
        except Exception:
            pass

        end = max(5.0, round(total_dur - 1.0, 1))
        start = max(0.0, round(end - max_dur, 1))
        peak_moment = max(1.0, round(end - start - outro, 1))
        return start, end, peak_moment, None




def _count_enemy_bars_in_frame(frame: np.ndarray) -> int:
    """Zlicza widoczne paski HP przeciwników (czerwone paski nad bohaterami)."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, (0, 120, 140), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 120, 140), (180, 255, 255))
    red_mask = cv2.bitwise_or(m1, m2)

    # Wyklucz HUD, scoreboard górny i minimapę
    red_mask[int(h * 0.82):, :] = 0
    red_mask[:int(h * 0.10), :] = 0
    red_mask[int(h * 0.70):, int(w * 0.75):] = 0

    cnts, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    count = 0
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if 32 <= bw <= 160 and 4 <= bh <= 25 and (bw / max(1, bh)) >= 1.8:
            count += 1
    return count


def _pick_varied_hook(action_type: str, video_path: str = "", min_hp: float = 100.0) -> str:
    """Wybiera zroznicowany hook z rotujacej puli sprawdzonych haczykow pod retencje."""
    HOOK_ROTATION = {
        "pentakill": [
            "PENTAKILL - 1V5 DEFENSE",
            "PENTAKILL - THEY GROUPED FOR FREE",
            "PENTAKILL - ZERO SURVIVORS",
            "PENTAKILL - RESET MACHINE",
            "PENTAKILL - DID ENEMY FF?",
        ],
        "quadrakill": [
            "QUADRAKILL - NO ESCAPE",
            "QUADRAKILL - 4 DOWN IN SECONDS",
            "QUADRAKILL - THEY THOUGHT 4v1 WAS SAFE",
            "QUADRAKILL - ONE MORE LEFT",
            "QUADRAKILL - RELENTLESS CHASE",
        ],
        "triple": [
            "TRIPLE KILL - ENEMY DIFF",
            "TRIPLE KILL - THEY WALKED INTO IT",
            "TRIPLE KILL - 3 DOWN IN SECONDS",
            "TRIPLE KILL - CLEAN RESET",
            "TRIPLE KILL - DISRESPECT PUNISHED",
        ],
        "double": [
            "DOUBLE KILL - CLEAN OR LUCKY?",
            "DOUBLE KILL - 2v1 TURNAROUND",
            "DOUBLE KILL - THEY GANKED WRONG LANE",
            "DOUBLE KILL - TWO DOWN INSTANTLY",
            "DOUBLE KILL - NEVER DIVE THIS",
        ],
        "solo_bolo": [
            "SOLO BOLO - 1v1 MASTERCLASS",
            "SOLO BOLO - EGO CHECKED",
            "SOLO BOLO - THEY THOUGHT THEY WON",
            "SOLO BOLO - PURE MECHANICS",
            "SOLO BOLO - NO CONTEST",
        ],
        "clutch": [
            f"HE HAD {int(min_hp)}% HP - WATCH THIS" if min_hp < 40 else "1% HP CLUTCH - HOW DID HE LIVE?",
            "IMPOSSIBLE SURVIVAL - WATCH CLOSELY",
            "THEY CELEBRATED TOO EARLY",
            "1 HP DREAM - THE CLEANEST ESCAPE",
        ],
        "outplay": [
            "WATCH THE LAST 3 SECONDS",
            "THEY THOUGHT THEY HAD ME",
            "WRONG MOVE - WATCH WHAT HAPPENS",
            "ONE MISTAKE COST THEM EVERYTHING",
            "THEY GAVE TOO MUCH SPACE",
            "DISRESPECT TURNED INTO REGRET",
            "ZERO HESITATION - PURE OUTPLAY",
        ],
    }
    pool = HOOK_ROTATION.get(action_type, HOOK_ROTATION["outplay"])
    seed_str = os.path.basename(video_path) if video_path else action_type
    idx = sum(ord(c) for c in seed_str) % len(pool)
    return pool[idx]

def _find_first_kill_gold_spike(video_path: str, t_start: float, t_end: float) -> Optional[float]:
    """Szuka piku złota (+300g/+370g) w oknie [t_start, t_end], gdy górny baner był zatkany przez Ally slain."""
    if not video_path or not os.path.exists(video_path) or t_end <= t_start:
        return None
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    best_t = None
    best_gold = 0
    try:
        for t in np.arange(max(0.5, t_start), t_end, 0.5):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, fr = cap.read()
            if not ret or fr is None:
                continue
            h, w = fr.shape[:2]
            hsv = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)
            gold_m = cv2.inRange(hsv, (18, 140, 160), (35, 255, 255))
            gold_play = gold_m[int(h * 0.20):int(h * 0.75), int(w * 0.20):int(w * 0.80)]
            g_px = int(cv2.countNonZero(gold_play))
            if g_px > best_gold and g_px >= 450:
                best_gold = g_px
                best_t = round(float(t), 2)
    finally:
        cap.release()
    return best_t


def _reconcile_multikill_sequence(
    kills_detected: List[Dict[str, Any]],
    ally_banner_times: List[float],
    objective_times: List[float],
    video_path: str = "",
) -> List[Dict[str, Any]]:
    """
    Rekonstruuje monotoniczną sekwencję multikilla (1 -> 2 -> 3 -> 4 -> 5),
    gdy wrogi/sojuszniczy baner lub baner Smoka/Barona opóźnił bądź odwrócił kolejność banerów.
    """
    if not kills_detected:
        return kills_detected

    reconciled = [dict(k) for k in sorted(kills_detected, key=lambda x: float(x.get("timestamp", 0.0)))]

    # 1. Wykryj inwersję na początku (np. wrogi TRIPLE KILL przed własnym DOUBLE KILL po serii Ally slain)
    if len(reconciled) >= 2 and reconciled[0].get("tier", 1) > reconciled[1].get("tier", 1):
        t_first_banner = float(reconciled[0]["timestamp"])
        has_prior_block = bool(
            [t for t in ally_banner_times if (t_first_banner - 10.0) <= t <= (t_first_banner + 0.5)]
        )
        search_from = max(1.0, t_first_banner - (6.0 if has_prior_block else 5.0))
        search_to = max(search_from + 0.5, t_first_banner - 1.5)
        gold_t = _find_first_kill_gold_spike(video_path, search_from, search_to)
        first_kill_t = gold_t if gold_t is not None else round(max(1.0, t_first_banner - 4.0), 2)

        reconciled[0] = {"timestamp": first_kill_t, "label": "KILL", "tier": 1}
        reconciled[1] = {"timestamp": t_first_banner, "label": "DOUBLE KILL", "tier": 2}

    # 2. Uzupełnij brakujący TRIPLE KILL między DOUBLE (tier=2) a QUADRA (tier=4), gdy kolejkę zablokował Smok/Baron
    tiers_present = {k.get("tier", 1) for k in reconciled}
    if 4 in tiers_present and 2 in tiers_present and 3 not in tiers_present:
        double_items = [k for k in reconciled if k.get("tier") == 2]
        quadra_items = [k for k in reconciled if k.get("tier") == 4]
        t_double = float(double_items[-1]["timestamp"])
        t_quadra = float(quadra_items[0]["timestamp"])
        if t_quadra > t_double + 2.0:
            obj_in_gap = [float(t) for t in objective_times if (t_double + 0.5) <= float(t) <= (t_quadra - 0.5)]
            gold_mid = _find_first_kill_gold_spike(video_path, t_double + 1.5, max(t_double + 2.0, t_quadra - 1.0))
            if gold_mid is not None:
                triple_t = gold_mid
            elif obj_in_gap:
                triple_t = round(obj_in_gap[0], 2)
            else:
                triple_t = round((t_double + t_quadra) / 2.0, 2)
            reconciled.append({"timestamp": triple_t, "label": "TRIPLE KILL", "tier": 3})

    reconciled.sort(key=lambda x: float(x.get("timestamp", 0.0)))
    return reconciled


def analyze_clip_frags(video_path: str, sample_fps: float = 1.0) -> FragAnalysisResult:
    """
    Główna funkcja auto-detektora: skanuje wideo i zwraca dokładną klasyfikację fraga.
    """
    if not os.path.exists(video_path):
        return FragAnalysisResult(
            video_path=video_path,
            duration=0.0,
            detected_frag_type="outplay",
            confidence=0.5,
            kill_count=1,
            kills=[],
            min_hp_percentage=100.0,
            is_clutch_1hp=False,
            badge_label="INSANE OUTPLAY",
            suggested_title_hook="Insane Mechanical Outplay",
            suggested_badge_color="#3b82f6"
        )

    cache_key = None
    try:
        st = os.stat(video_path)
        cache_key = (os.path.abspath(video_path), int(st.st_size), int(st.st_mtime_ns), round(float(sample_fps), 2))
        with _FRAG_CACHE_LOCK:
            cached = _FRAG_CACHE.get(cache_key)
        if cached is not None:
            return replace(
                cached,
                kills=[dict(k) for k in cached.kills],
                combat_segments=list(cached.combat_segments) if cached.combat_segments else None,
            )
    except Exception:
        cache_key = None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return FragAnalysisResult(
            video_path=video_path,
            duration=0.0,
            detected_frag_type="outplay",
            confidence=0.5,
            kill_count=1,
            kills=[],
            min_hp_percentage=100.0,
            is_clutch_1hp=False,
            badge_label="INSANE OUTPLAY",
            suggested_title_hook="Insane Mechanical Outplay",
            suggested_badge_color="#3b82f6"
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if fps > 0 else 0.0

    effective_sample_fps = max(sample_fps, 2.0) if (sample_fps <= 1.0 and 0.0 < duration <= 90.0) else sample_fps
    interval = 1.0 / max(1.0, effective_sample_fps)
    timestamps = np.arange(0.0, max(0.1, duration), interval)

    hp_readings = []
    kills_detected = []
    ally_banner_times = []
    objective_times = []
    max_kill_tier = 0
    highest_label = ""
    last_kill_t = -10.0
    has_crit_vignette = False
    max_enemies_around_fight = 0

    for t in timestamps:
        frame_idx = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue

        # 1. Sprawdź pasek HP
        hp_val = _measure_player_hp(frame)
        if hp_val is not None and hp_val > 1.0:
            hp_readings.append(hp_val)

        # 2. Sprawdź efekt Low HP Vignette
        if not has_crit_vignette and _detect_critical_low_hp_vignette(frame):
            has_crit_vignette = True

        # 3. Zlicz wrogie paski HP w kadrze (do weryfikacji 1v1 vs 1v2 / walki grupowej)
        e_bars = _count_enemy_bars_in_frame(frame)
        if e_bars > 0:
            max_enemies_around_fight = min(max(max_enemies_around_fight, e_bars), 5)

        # 4. Sprawdź napisy Kill przez OCR z Guardem własności gracza
        k_tier, k_label, is_player_kill = _scan_ocr_for_kills(frame)
        if is_player_kill and k_tier > 0:
            # Ignoruj słabe sygnały OUTPLAY w pierwszych 1.2s jeśli nie są multikillem
            if t <= 1.2 and k_tier < 2:
                continue

            # Debounce: Baner killa w LoL wisi na ekranie przez 2.5-3.0s.
            # 1. Nowy kill o tym samym/niższym tierze wymaga odstępu min. 3.0s
            # 2. Wyższy tier multikilla (np. DOUBLE KILL po zwykłym killu) to KOLEJNY frag (wymaga min. 0.8s)
            # 3. Zmiana tieru w dół (np. własny DOUBLE KILL po zaległym wrogim TRIPLE) też musi zostać zapisana do rekonstrukcji
            is_multikill_step = (k_tier >= 2 and k_tier > max_kill_tier and (t - last_kill_t) >= 0.8)
            is_tier_inversion = (k_tier >= 2 and bool(kills_detected) and k_tier < kills_detected[-1]["tier"] and (t - last_kill_t) >= 1.5)
            is_new_kill = ((t - last_kill_t) > 3.0) or is_multikill_step or is_tier_inversion

            if is_new_kill:
                kills_detected.append({
                    "timestamp": round(float(t), 2),
                    "label": k_label,
                    "tier": k_tier,
                })
                last_kill_t = t
            elif k_tier > max_kill_tier and kills_detected and (t - last_kill_t) < 0.8:
                # Błyskawiczna korekta OCR tego samego banera w tej samej sekundzie
                kills_detected[-1] = {
                    "timestamp": round(float(t), 2),
                    "label": k_label,
                    "tier": k_tier,
                }
                last_kill_t = t

            if k_tier > max_kill_tier:
                max_kill_tier = k_tier
                highest_label = k_label
        elif k_label == "PLAYER_DEATH":
            # Zarejestruj śmierć gracza — nie może być oznaczona jako udany clutch
            hp_readings.append(0.0)
        elif k_label == "OBJECTIVE_SLAIN":
            objective_times.append(round(float(t), 2))
        elif k_label in ("ALLY_BANNER", "ALLY_KILL", "ALLY_MULTIKILL", "ENEMY_KILL"):
            ally_banner_times.append(round(float(t), 2))

    cap.release()

    kills_detected = _reconcile_multikill_sequence(
        kills_detected=kills_detected,
        ally_banner_times=ally_banner_times,
        objective_times=objective_times,
        video_path=video_path,
    )
    if kills_detected:
        top_k = max(kills_detected, key=lambda x: int(x.get("tier", 0)))
        max_kill_tier = int(top_k.get("tier", 0))
        highest_label = str(top_k.get("label", ""))

    # Wylicz minimalne HP
    min_hp = min(hp_readings) if hp_readings else 100.0
    if has_crit_vignette and min_hp > 15.0:
        min_hp = 12.0

    # Clutch wymaga przetrwania walki (HP > 0), spadku HP <= 22% oraz zdobycia co najmniej 1 fraga
    is_clutch = (0.0 < min_hp <= 22.0 and len(hp_readings) > 2 and len(kills_detected) >= 1)

    # Klasyfikacja priorytetowa:
    # Pentakill i Quadrakill mają zawsze najwyższy priorytet (są unikalnymi rzadkimi momentami)
    if max_kill_tier >= 5:
        detected_type = "pentakill"
        badge = "PENTAKILL"
        color = "#eab308"  # Złoty
        hook = _pick_varied_hook("pentakill", video_path, min_hp)
        conf = 0.95
    elif max_kill_tier == 4:
        detected_type = "quadrakill"
        badge = "QUADRA KILL"
        color = "#f97316"  # Pomarańczowy
        hook = _pick_varied_hook("quadrakill", video_path, min_hp)
        conf = 0.92
    elif max_kill_tier == 3 or (len(kills_detected) >= 3 and max_kill_tier != 2):
        detected_type = "triple"
        badge = "TRIPLE KILL" if max_kill_tier == 3 else f"MULTI-KILL ({len(kills_detected)} FRAGI)"
        color = "#a855f7"  # Fioletowy
        hook = _pick_varied_hook("triple", video_path, min_hp)
        conf = 0.88
    elif max_kill_tier == 2 or len(kills_detected) >= 2:
        # Gra wyświetliła baner DOUBLE KILL lub zarejestrowano 2 fragi
        detected_type = "double"
        badge = "DOUBLE KILL"
        color = "#06b6d4"  # Turkusowy
        hook = _pick_varied_hook("double", video_path, min_hp)
        conf = 0.85
    elif is_clutch:
        detected_type = "clutch"
        badge = "1% HP CLUTCH"
        color = "#ef4444"  # Czerwony neon
        hook = _pick_varied_hook("clutch", video_path, min_hp)
        conf = 0.90
    elif len(kills_detected) == 1:
        # Dokładnie 1 kill: rozróżniamy Solo Bolo (czyste 1v1 / First Blood) od Outplay (1v2, shutdown, teamfight)
        is_first_blood = (highest_label == "FIRST BLOOD")
        is_multi_enemy = (max_enemies_around_fight >= 2) and not is_first_blood
        is_explicit_outplay = (highest_label == "OUTPLAY")

        if is_first_blood:
            detected_type = "solo_bolo"
            badge = "FIRST BLOOD"
            color = "#FF1744"
            hook = _pick_varied_hook("solo_bolo", video_path, min_hp)
            conf = 0.92

        if is_multi_enemy:
            detected_type = "outplay"
            badge = "INSANE OUTPLAY"
            color = "#3b82f6"  # Niebieski
            hook = _pick_varied_hook("outplay", video_path, min_hp)
            conf = 0.86
        elif is_explicit_outplay:
            detected_type = "outplay"
            badge = "INSANE OUTPLAY"
            color = "#3b82f6"  # Niebieski
            hook = _pick_varied_hook("outplay", video_path, min_hp)
            conf = 0.87
        else:
            # Czyste 1v1: 1 wróg w kadrze, brak banera shutdown
            detected_type = "solo_bolo"
            badge = "SOLO BOLO"
            color = "#FF1744"  # Neonowa czerwień
            hook = _pick_varied_hook("solo_bolo", video_path, min_hp)
            conf = 0.89
    else:
        # Brak potwierdzonych killi (0 killi)
        detected_type = "outplay"
        badge = "INSANE OUTPLAY"
        color = "#3b82f6"  # Niebieski
        hook = _pick_varied_hook("outplay", video_path, min_hp)
        conf = 0.80


    temp_res = FragAnalysisResult(
        video_path=video_path,
        duration=round(duration, 2),
        detected_frag_type=detected_type,
        confidence=conf,
        kill_count=max(len(kills_detected), max_kill_tier, 1),
        kills=kills_detected,
        min_hp_percentage=round(min_hp, 1),
        is_clutch_1hp=is_clutch,
        badge_label=badge,
        suggested_title_hook=hook,
        suggested_badge_color=color,
        objective_secured=bool(objective_times),
        objective_label="DRAGON_OR_OBJECTIVE_SLAIN" if objective_times else "",
        ally_banner_blocked=bool(ally_banner_times),
    )
    opt_s, opt_e, _, segments = compute_optimal_clip_window(temp_res, duration)
    temp_res.combat_segments = segments
    temp_res.has_jump_cut = bool(segments and len(segments) > 1)

    is_meaningful_hard_case = (
        len(kills_detected) >= 2
        or (bool(getattr(temp_res, "objective_secured", None)) and len(kills_detected) >= 1)
    )
    if (temp_res.objective_secured or temp_res.ally_banner_blocked) and is_meaningful_hard_case:
        try:
            try:
                from lol_agent.hard_case_learner import record_hard_case
            except ImportError:
                from hard_case_learner import record_hard_case
            reasons = []
            if temp_res.ally_banner_blocked:
                reasons.append("ally_banner_blocked")
            if temp_res.objective_secured:
                reasons.append("objective_steal_or_slain")
            record_hard_case(
                video_path=video_path,
                detected_frag_type=detected_type,
                kills=kills_detected,
                clip_start=opt_s,
                clip_end=opt_e,
                reason=", ".join(reasons),
                objective_secured=temp_res.objective_secured,
                objective_label=temp_res.objective_label,
                ally_banner_blocked=temp_res.ally_banner_blocked,
                min_hp_pct=float(min_hp),
            )
        except Exception:
            pass

    if cache_key is not None:
        with _FRAG_CACHE_LOCK:
            if len(_FRAG_CACHE) >= 16:
                oldest = next(iter(_FRAG_CACHE))
                _FRAG_CACHE.pop(oldest, None)
            _FRAG_CACHE[cache_key] = replace(
                temp_res,
                kills=[dict(k) for k in temp_res.kills],
                combat_segments=list(temp_res.combat_segments) if temp_res.combat_segments else None,
            )

    return temp_res

