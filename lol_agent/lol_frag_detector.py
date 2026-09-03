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

        # Jeśli brak wyraźnych pikseli napisów, pomiń
        if (gold_cnt + white_cnt + red_cnt + blue_cnt) < 50:
            continue

        # Czerwony baner = akcja wroga lub śmierć gracza -> ODRZUĆ
        is_enemy_banner = (red_cnt > (gold_cnt + white_cnt) * 1.5) and red_cnt > 150

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 175, 255, cv2.THRESH_BINARY)
        thresh_up = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        text = ""
        for psm in (6, 11, 7):
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
        if is_enemy_banner or re.search(r'(?:enemy\s*penta|enemy\s*quadra|enemy\s*triple|enemy\s*double|an\s*ally\s*has\s*been\s*slain)', text):
            return 0, "ENEMY_KILL", False

        # ── 3. FILTR FRAGÓW SOJUSZNIKÓW (TEAMMATE KILLS) ──
        # Komunikat 'an ally has scored' lub 'an enemy has been slain' oznacza, że to nie gracz zdobył frag/multikill
        if re.search(r'an\s*ally\s*has\s*scored', text):
            return 0, "ALLY_MULTIKILL", False
        if re.search(r'an\s*enemy\s*has\s*been\s*slain', text) and not re.search(r'\+(?:300|150|1000)', text):
            return 0, "ALLY_KILL", False

        # ── 4. POTWIERDZONE WŁASNE FRAGI GRACZA (PLAYER KILLS) ──
        # Złoty baner lub wyraźny komunikat PENTAKILL / QUADRA / TRIPLE / DOUBLE / YOU HAVE SLAIN
        if re.search(r'penta(?:kill|kut|kit|kil|\s*kill)?', text):
            return 5, "PENTAKILL", True
        if re.search(r'quadra(?:kill|kut|kit|kil|\s*kill)?', text):
            return 4, "QUADRAKILL", True
        if re.search(r'triple(?:kill|kut|kit|kil|\s*kill)?', text):
            return 3, "TRIPLE KILL", True
        if re.search(r'double(?:kill|kut|kit|kil|\s*kill)?', text):
            return 2, "DOUBLE KILL", True
        if re.search(r'shut\s*down|shutdown|legendary|godlike|unstoppable', text):
            return 1, "OUTPLAY", True
        if re.search(r'(?:you\s*have\s*slain|\+300|\+150|\+1000)', text):
            return 1, "KILL", True

    return 0, "", False


def compute_optimal_clip_window(
    frag_res: FragAnalysisResult,
    total_dur: float
) -> Tuple[float, float, float, Optional[List[Tuple[float, float]]]]:
    """
    Wyznacza optymalne okno czasowe (clip_start, clip_end, peak_moment) oraz segmenty jump-cut
    na podstawie detekcji OCR i aktywnego profilu pacingu (Ekstremalnie Szybkie / Zbalansowane / Cinematic).
    """
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

    real_kills = [k for k in frag_res.kills if k.get("tier", 1) >= 2 or k.get("timestamp", 0) > 1.0]

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

        # Jeśli mamy co najmniej 2 klastry i przerwa między nimi wynosi > 3.5s
        # generujemy segmenty Jump-Cut (wycinamy martwy bieg pomiędzy walkami)
        if len(clusters) >= 2:
            segments = []
            # Bufor wejścia w walkę (doskok / engage / Shunpo):
            # Baner killa pojawia się z opóźnieniem (~1s po śmierci, a sama walka trwa 2-3s wcześniej).
            # Aby widz widział fizyczny doskok do wrogów, a nie tylko ciało i bounty,
            # potrzebujemy min. 3.2s-3.5s przed banerem pierwszego killa w segmencie.
            engage_lead = max(3.5, buildup * 2.5)

            for i, c in enumerate(clusters):
                c_start = c[0]["timestamp"]
                c_end = c[-1]["timestamp"]
                if i == 0:
                    s = max(0.0, round(c_start - max(1.2, buildup), 1))
                    e = round(c_end + 1.2, 1)
                elif i == len(clusters) - 1:
                    s = max(0.0, round(c_start - engage_lead, 1))
                    e = min(round(total_dur, 1), round(c_end + max(outro, 2.0), 1))
                else:
                    s = max(0.0, round(c_start - engage_lead, 1))
                    e = round(c_end + 1.2, 1)
                segments.append((s, e))

            # Scal jeśli któryś segment nachodzi na sąsiedni
            merged_segs = [segments[0]]
            for s, e in segments[1:]:
                if s <= merged_segs[-1][1]:
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

        start = max(0.0, round(first_k - buildup, 1))
        end = min(round(total_dur, 1), round(last_k + outro, 1))

        # Najpierw obetnij do max_dur (priorytet: nie przekraczaj limitu profilu)
        if end - start > max_dur:
            start = max(0.0, round(last_k - (max_dur - outro), 1))
            end = min(round(total_dur, 1), round(last_k + outro, 1))

        # Potem rozszerz do min_dur jesli wciaz za krotkie
        if end - start < min_dur:
            needed = min_dur - (end - start)
            start = max(0.0, round(start - needed * 0.5, 1))
            end = min(round(total_dur, 1), round(end + needed * 0.5, 1))

        peak_moment = max(1.0, round(last_k - start, 1))
        return start, end, peak_moment, None
    else:
        end = max(5.0, round(total_dur - 1.0, 1))
        start = max(0.0, round(end - max_dur, 1))
        peak_moment = max(1.0, round(end - start - outro, 1))
        return start, end, peak_moment, None




def analyze_clip_frags(video_path: str, sample_fps: float = 3.0) -> FragAnalysisResult:
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

    interval = 1.0 / max(1.0, sample_fps)
    timestamps = np.arange(0.0, max(0.1, duration), interval)

    hp_readings = []
    kills_detected = []
    max_kill_tier = 0
    highest_label = "OUTPLAY"
    last_kill_t = -10.0
    has_crit_vignette = False

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

        # 3. Sprawdź napisy Kill przez OCR z Guardem własności gracza
        k_tier, k_label, is_player_kill = _scan_ocr_for_kills(frame)
        if is_player_kill and k_tier > 0:
            # Ignoruj słabe sygnały OUTPLAY w pierwszych 1.2s jeśli nie są multikillem
            if t <= 1.2 and k_tier < 2:
                continue

            if (t - last_kill_t) > 1.2 or k_tier > max_kill_tier:
                kills_detected.append({
                    "timestamp": round(float(t), 2),
                    "label": k_label,
                    "tier": k_tier,
                })
                if k_tier > max_kill_tier:
                    max_kill_tier = k_tier
                    highest_label = k_label
                last_kill_t = t
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
        hook = "Insane 1v5 Pentakill Rampage"
        conf = 0.95
    elif max_kill_tier == 4:
        detected_type = "quadrakill"
        badge = "QUADRA KILL"
        color = "#f97316"  # Pomarańczowy
        hook = "Unstoppable Quadra Kill Frenzy"
        conf = 0.92
    elif is_clutch:
        detected_type = "clutch"
        badge = "1% HP CLUTCH"
        color = "#ef4444"  # Czerwony neon
        hook = f"Survives with {int(min_hp)}% HP & Outplays"
        conf = 0.90
    elif max_kill_tier == 3:
        detected_type = "triple"
        badge = "TRIPLE KILL"
        color = "#a855f7"  # Fioletowy
        hook = "Dominating Triple Kill"
        conf = 0.88
    elif len(kills_detected) >= 3:
        detected_type = "triple"
        badge = f"MULTI-KILL ({len(kills_detected)} FRAGI)"
        color = "#a855f7"  # Fioletowy
        hook = "Insane Multi-Kill Sequence 💥"
        conf = 0.87
    elif max_kill_tier == 2 or len(kills_detected) == 2:
        detected_type = "double"
        badge = "DOUBLE KILL"
        color = "#06b6d4"  # Turkusowy
        hook = "Clean Double Kill ⚔️"
        conf = 0.85
    else:
        detected_type = "outplay"
        badge = "INSANE OUTPLAY"
        color = "#3b82f6"  # Niebieski
        hook = "Frame-Perfect Mechanical Outplay"
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

