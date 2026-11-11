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
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

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
# Dolny pasek zdrowia bohatera (HUD dolny środek):
HP_BAR_ROI = (0.860, 0.905, 0.420, 0.580)  # y_start, y_end, x_start, x_end
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


def _measure_player_hp(frame: np.ndarray) -> Optional[float]:
    """
    Mierzy procent napełnienia paska zdrowia bohatera w dolnym HUD (0.0 - 100.0%).
    Analizuje nasycenie zieleni/cyjanu w obszarze HP_BAR_ROI.
    """
    h, w = frame.shape[:2]
    ys, ye = int(h * HP_BAR_ROI[0]), int(h * HP_BAR_ROI[1])
    xs, xe = int(w * HP_BAR_ROI[2]), int(w * HP_BAR_ROI[3])
    
    roi = frame[ys:ye, xs:xe]
    if roi.size == 0:
        return None

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Maska zielonego/cyjanowego paska zdrowia w LoL:
    # H: 35-95 (zielenie i seledyny/turkusy), S: 70-255, V: 60-255
    mask_green = cv2.inRange(hsv, (35, 70, 60), (95, 255, 255))
    # Maska tarczy (biały/szary pasek na wierzchu HP):
    mask_shield = cv2.inRange(hsv, (0, 0, 180), (180, 40, 255))
    mask_hp = cv2.bitwise_or(mask_green, mask_shield)

    # Oblicz poziom napełnienia paska wzdłuż osi X (poziomej)
    col_has_hp = np.any(mask_hp > 0, axis=0)
    total_cols = len(col_has_hp)
    if total_cols == 0:
        return None

    filled_cols = np.sum(col_has_hp)
    # Sprawdź czy to w ogóle jest HUD (jeśli < 5% zieleni, może to być poza grą)
    ratio = (filled_cols / float(total_cols)) * 100.0
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

        # Pre-filter: Sprawdź czy są jakiekolwiek piksele tekstu (złote lub białe napisy banera)
        # Oszczędza 75% czasu OCR przez pomijanie pustych klatek
        if (gold_cnt + white_cnt) < 40:
            continue

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY)
        thresh_up = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        text = ""
        for psm in (6, 7):
            try:
                text = pytesseract.image_to_string(thresh_up, config=f"--psm {psm} --oem 1").strip().lower()
                if text:
                    break
            except Exception:
                pass

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

        # ── 3. FILTR FRAGÓW SOJUSZNIKÓW (TEAMMATE KILLS) ──
        # Komunikat 'an ally has scored' lub 'an enemy has been slain' oznacza, że to sojusznik zdobył frag
        is_dwann = bool(re.search(r'dwan|enga|you\s*have\s*slain|\+(?:400|300|150|1000|[0-9]{3})', text))
        if re.search(r'an\s*ally\s*has\s*scored', text):
            return 0, "ALLY_MULTIKILL", False
        if re.search(r'an\s*enemy\s*has\s*been\s*slain', text) and not is_dwann:
            return 0, "ALLY_KILL", False
        if blue_cnt > 5000 and not is_dwann:
            return 0, "ALLY_BANNER", False

        # ── 4. POTWIERDZONE WŁASNE FRAGI GRACZA (PLAYER KILLS) ──
        # Złoty baner lub wyraźny komunikat PENTAKILL / QUADRA / TRIPLE / DOUBLE / RAMPAGE / YOU HAVE SLAIN
        if re.search(r'penta(?:kill|kut|kit|kil|\s*kill)?', text):
            return 5, "PENTAKILL", True
        if re.search(r'quadra(?:kill|kut|kit|kil|\s*kill)?', text):
            return 4, "QUADRAKILL", True
        if re.search(r'tri[pbl][rl]e?(?:kill|kut|kit|kil|\s*kill)?|trie[re]\s*ki|[sr]riper?\s*ki|[st]e?ipre\s*ki|reiprek|[sr]riprr', text):
            return 3, "TRIPLE KILL", True
        if re.search(r'dou[brv][bl]e?(?:kill|kut|kit|kil|\s*kill)?|doue?le\s*ki|doublekinlt', text):
            return 2, "DOUBLE KILL", True
        if re.search(r'first\s*bloo[mdr]|1st\s*blood|first\s*rlood', text):
            return 1, "FIRST BLOOD", True
        if re.search(r'ram[pn]a[gc]e|is\s*on\s*a\s*ram|kill(?:ing)?\s*s[pn]r[ea]e|is\s*on\s*a\s*kill|is\s*on\s*a\s*s[pn]r|shut\s*down|shutdown|legendary|godlike|unstoppable', text):
            return 1, "OUTPLAY", True
        if re.search(r'(?:you\s*have\s*slain|\+(?:400|300|150|1000))', text):
            return 1, "KILL", True

    return 0, "", False


def find_combat_start_before(
    video_path: str,
    first_kill_t: float,
    max_lookback: float = 8.0
) -> float:
    """
    Skanuje wstecz od pierwszego killa (do max_lookback sekund),
    aby ustalić moment rozpoczęcia realnej walki (obecność wrogich pasków HP,
    błyski czarów, dynamiczny ruch). Zapobiega obcięciu engage/setupu/combo.
    """
    if not video_path or not os.path.exists(video_path):
        return max(0.0, first_kill_t - 2.0)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return max(0.0, first_kill_t - 2.0)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    search_start = max(0.0, first_kill_t - max_lookback)
    samples = np.arange(search_start, first_kill_t, 0.4)
    earliest_combat = max(0.0, first_kill_t - 2.5)

    try:
        from lol_agent.lol_quality_validator import _check_combat_in_frame, _check_enemy_combat_in_frame
    except ImportError:
        try:
            from lol_quality_validator import _check_combat_in_frame, _check_enemy_combat_in_frame
        except ImportError:
            _check_combat_in_frame = None
            _check_enemy_combat_in_frame = None

    try:
        prev_gray = None
        for t in samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ret, fr = cap.read()
            if not ret or fr is None:
                continue
            has_combat = False
            if _check_combat_in_frame and _check_enemy_combat_in_frame:
                hc, c_px, _ = _check_combat_in_frame(fr)
                he, e_px, _ = _check_enemy_combat_in_frame(fr)
                if (hc and c_px > 300) or (he and e_px > 300):
                    has_combat = True
            if not has_combat:
                h, w = fr.shape[:2]
                pa = fr[int(h * 0.15):int(h * 0.80), int(w * 0.20):int(w * 0.80)]
                gray = cv2.cvtColor(cv2.resize(pa, (320, 180)), cv2.COLOR_BGR2GRAY)
                if prev_gray is not None and float(np.mean(cv2.absdiff(gray, prev_gray))) >= 9.0:
                    has_combat = True
                prev_gray = gray

            if has_combat:
                earliest_combat = t
                break
    finally:
        cap.release()

    return earliest_combat


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
        first_k = real_kills[0]["timestamp"]
        max_tier = max(k.get("tier", 1) for k in real_kills)
        peak_candidates = [k for k in real_kills if k.get("tier", 1) == max_tier]
        last_k = peak_candidates[-1]["timestamp"] if peak_candidates else real_kills[-1]["timestamp"]

        # Wykryj precyzyjny moment śmiertelnego ciosu (last-hit)
        has_real_video = bool(frag_res.video_path and os.path.exists(frag_res.video_path))
        if has_real_video:
            lethal_hit_t = find_lethal_strike_moment(frag_res.video_path, last_k)
            c_start = find_combat_start_before(frag_res.video_path, min(first_k, lethal_hit_t), max_lookback=8.0)
        else:
            lethal_hit_t = last_k
            c_start = max(0.0, first_k - 2.0)

        final_kill_t = max(lethal_hit_t, last_k)
        # Zgodnie z wytycznymi użytkownika: MAX 2.0s po finalnym zabójstwie (eliminacja martwego czasu i recallu)
        is_multikill_tier = (len(real_kills) >= 3) or (act in ('triple', 'quadrakill', 'quadra', 'pentakill', 'penta'))
        default_outro = 1.8 if is_multikill_tier else 1.4
        clean_outro = min(2.0, max(default_outro, outro))
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
            if (first_k - start) > 2.5:
                start = max(0.0, round(first_k - 2.5, 1))
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

        # Zabezpieczenie przed ucięciem pierwszego killa
        if start > first_k - 0.8:
            start = max(0.0, round(first_k - 1.0, 1))

        peak_moment = max(0.5, round(lethal_hit_t - start, 1))
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

    effective_sample_fps = max(sample_fps, 2.0) if (sample_fps <= 1.0 and 0.0 < duration <= 50.0) else sample_fps
    interval = 1.0 / max(1.0, effective_sample_fps)
    timestamps = np.arange(0.0, max(0.1, duration), interval)

    hp_readings = []
    kills_detected = []
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
            is_multikill_step = (k_tier >= 2 and k_tier > max_kill_tier and (t - last_kill_t) >= 0.8)
            is_new_kill = ((t - last_kill_t) > 3.0) or is_multikill_step

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

    cap.release()

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
    elif is_clutch:
        detected_type = "clutch"
        badge = "1% HP CLUTCH"
        color = "#ef4444"  # Czerwony neon
        hook = _pick_varied_hook("clutch", video_path, min_hp)
        conf = 0.90
    elif max_kill_tier == 3 or len(kills_detected) >= 3:
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
    )
    _, _, _, segments = compute_optimal_clip_window(temp_res, duration)
    temp_res.combat_segments = segments
    temp_res.has_jump_cut = bool(segments and len(segments) > 1)
    return temp_res

