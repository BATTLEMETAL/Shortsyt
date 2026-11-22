"""
LOL AGENT — Pre-Flight & Post-Flight Quality Validator
Automatyczny audytor jakości i poprawności kadru, segmentów montażu oraz finalnego klipu.

Sprawdza i realistycznie ocenia (bez ślepego 100% z automatu):
1. Action Hook Guard: czy w pierwszych 1.5s - 2.0s jest bezpośrednia walka / pierwszy kill (nie pusty bieg).
2. Kill & Action Visibility Check: czy zabójstwa i walka mieszczą się w pionowym oknie kadrowania 9:16.
3. Segment Verification: weryfikacja każdego segmentu montażu (długość, gęstość akcji, brak martwego marszu).
4. Realistic Dynamic Scoring: ważona ocena (Hook 25%, Visibility 35%, Density 25%, Pacing 15%).
5. Post-Flight Render Validator: weryfikacja wyrenderowanego pliku mp4 (rozdzielczość 9:16, brak czarnych/zamrożonych klatek).
"""
import os
import sys
import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    passed: bool
    adjusted_trim_start: float
    adjusted_trim_end: float
    rejection_code: Optional[str] = None
    rejection_message: Optional[str] = None
    tracking_confidence: float = 1.0
    kills_visible: int = 0
    total_kills: int = 0
    diagnostic_details: List[str] = field(default_factory=list)
    qa_status: str = "PASS"        # "PASS" | "WARN" | "FAIL"
    qa_score: int = 95             # 0 - 100 (realistyczna ocena oparta na klipie)
    suggested_combat_segments: Optional[List[Tuple[float, float]]] = None
    corrected_action_type: Optional[str] = None
    segment_evaluations: Optional[List[Dict[str, Any]]] = None
    hook_score: int = 100
    visibility_score: int = 100
    density_score: int = 100
    pacing_score: int = 100
    hook_latency_s: float = 0.8
    combat_density_pct: float = 85.0
    outro_latency_s: float = 1.5
    action_visibility_pct: float = 90.0
    is_seamless_loop: bool = True
    montage_execution_index: float = 95.0

    def get_mei_dict(self) -> Dict[str, Any]:
        """Zwraca słownik cech Wielowymiarowego Indeksu Egzekucji Montażu (MEI)."""
        return {
            "mei_score": round(self.montage_execution_index, 1),
            "hook_latency_s": round(self.hook_latency_s, 2),
            "combat_density_pct": round(self.combat_density_pct, 1),
            "outro_latency_s": round(self.outro_latency_s, 2),
            "action_visibility_pct": round(self.action_visibility_pct, 1),
            "is_seamless_loop": self.is_seamless_loop,
            "hook_score": self.hook_score,
            "visibility_score": self.visibility_score,
            "density_score": self.density_score,
            "pacing_score": self.pacing_score,
        }


def _check_enemy_combat_in_frame(frame: np.ndarray) -> Tuple[bool, int, Optional[Tuple[int, int]]]:
    """
    Wykrywa obecność wrogich pasków HP (czerwone).
    Zwraca: (is_combat_present, enemy_pixel_count, centroid_pos)
    """
    if frame is None or frame.size == 0:
        return False, 0, None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Czerwony pasek HP wroga
    m1 = cv2.inRange(hsv, (0, 110, 120), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 110, 120), (180, 255, 255))
    red_mask = cv2.bitwise_or(m1, m2)
    
    # Wyklucz obszar minimapy (prawy dolny róg) i górnego/dolnego UI
    h, w = frame.shape[:2]
    red_mask[int(h * 0.75):, int(w * 0.72):] = 0
    red_mask[int(h * 0.75):, :int(w * 0.25)] = 0
    red_mask[:int(h * 0.12), :] = 0
    red_mask[int(h * 0.82):, :] = 0
    
    cnts, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    champ_px = 0
    pts = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw >= 32 and 4 <= bh <= 25 and (bw / max(1, bh)) >= 1.8:
            champ_px += cv2.contourArea(c)
            pts.append((x + bw // 2, y + bh // 2))

    if champ_px >= 60 and pts:
        mean_pt = tuple(np.mean(pts, axis=0).astype(int))
        return True, int(champ_px), mean_pt
    return False, int(champ_px), None


def _check_player_in_frame(frame: np.ndarray) -> Tuple[bool, int, Optional[Tuple[int, int]]]:
    """
    Wykrywa obecność paska HP gracza (złoty / zielony) z walidacją geometrii prostokąta
    i wykluczeniem nakładek tekstowych w pionowych kadrach 9:16 (hook, kill baner, złoty CTA).
    Zwraca: (is_player_present, player_pixel_count, centroid_pos)
    """
    if frame is None or frame.size == 0:
        return False, 0, None
    h, w = frame.shape[:2]
    f = frame.astype(np.int16)
    b, g, r = f[:, :, 0], f[:, :, 1], f[:, :, 2]

    excl = np.ones((h, w), dtype=bool)
    if h > w:
        # Pionowy short 9:16: odetnij strefę hooka/kill banerów u góry i strefę CTA/HUD u dołu
        excl[:int(h * 0.30), :] = False
        excl[int(h * 0.70):, :] = False
    else:
        excl[:int(h * 0.12), :] = False
        excl[int(h * 0.82):, :] = False
        excl[int(h * 0.75):, int(w * 0.72):] = False
        excl[int(h * 0.75):, :int(w * 0.25)] = False

    # Złoty pasek (gracz - Colorblind mode)
    yellow = (
        (r > 155) & (g > 125) & (b < 115) &
        ((r - b) > 65) & ((g - b) > 35)
    ) & excl
    # Zielony pasek (gracz - Standard mode, odrzuca ciemną trawę dżungli)
    green = (
        (g > 155) & (r < 115) & (b < 105) &
        ((g - r) > 55) & ((g - b) > 65)
    ) & excl

    player_mask = ((yellow | green).astype(np.uint8)) * 255
    # Poziome scalenie segmentów paska HP (100 HP notches)
    notch_k = cv2.getStructuringElement(cv2.MORPH_RECT, (19, 1))
    player_mask = cv2.morphologyEx(player_mask, cv2.MORPH_CLOSE, notch_k)

    num_labels, _, stats, centroids = cv2.connectedComponentsWithStats(player_mask)
    best_score = -1.0
    best_area = 0
    best_pt: Optional[Tuple[int, int]] = None
    for comp_i in range(1, num_labels):
        _, _, cw, ch, area = stats[comp_i]
        asp = cw / max(ch, 1)
        fill = area / max(1, cw * ch)
        if cw >= 30 and 3 <= ch <= 28 and 2.0 <= asp <= 20.0 and area >= 45 and fill >= 0.35:
            score = float(area) * min(asp, 10.0)
            if score > best_score:
                best_score = score
                best_area = int(area)
                best_pt = (int(centroids[comp_i][0]), int(centroids[comp_i][1]))

    if best_pt is not None:
        return True, best_area, best_pt
    return False, 0, None


def _check_combat_in_frame(frame: np.ndarray) -> Tuple[bool, int, Optional[Tuple[int, int]]]:
    """
    Wykrywa jakąkolwiek aktywność walki (wróg LUB gracz).
    Zwraca: (has_action, action_pixel_count, combined_centroid)
    """
    has_e, ep, ec = _check_enemy_combat_in_frame(frame)
    has_p, pp, pc = _check_player_in_frame(frame)
    if has_e and has_p and ec and pc:
        cx = int((ec[0] * 2 + pc[0]) / 3)
        cy = int((ec[1] * 2 + pc[1]) / 3)
        return True, ep + pp, (cx, cy)
    elif has_e and ec:
        return True, ep, ec
    elif has_p and pc:
        return True, pp, pc
    return False, 0, None


def validate_montage_segments(
    video_path: str,
    segments: List[Tuple[float, float]],
    peaks: List[Tuple[float, str]],
    smart_camera_track: Optional[List[Tuple[float, int]]] = None,
    crop_w: int = 608,
) -> Dict[str, Any]:
    """
    Weryfikuje poszczególne segmenty montażu:
    - czas trwania każdego segmentu (odrzucenie mikrosegmentów < 1.0s)
    - gęstość akcji/walki w każdym segmencie (wykrywanie pustego biegu)
    - widoczność killi w oknie kadrowania 9:16
    - opóźnienie pierwszego kontaktu bojowego (Action Hook)
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {
            "error": "CANNOT_OPEN_VIDEO",
            "segments": [],
            "hook_score": 0,
            "visibility_score": 0,
            "density_score": 0,
            "pacing_score": 0,
            "composite_score": 0,
        }

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_dur = frame_count / fps

    seg_results = []
    total_combat_samples = 0
    total_samples = 0
    all_visible_kills = 0
    total_peaks_in_montage = 0
    diag_msgs = []

    # Sortuj ścieżkę kamery dla szybkiej interpolacji
    track_times = [t for t, _ in smart_camera_track] if smart_camera_track else []
    track_xs = [x for _, x in smart_camera_track] if smart_camera_track else []

    first_action_time = None

    for seg_idx, (seg_s, seg_e) in enumerate(segments):
        seg_dur = max(0.0, seg_e - seg_s)
        if seg_dur < 1.0:
            diag_msgs.append(f"Segment #{seg_idx+1}: Zbyt krótki fragment ({seg_dur:.2f}s < 1.0s) — ryzyko migotania!")

        # Próbkowanie klatek w segmencie co ok. 0.8s
        num_samples = max(2, int(seg_dur / 0.8))
        sample_ts = np.linspace(seg_s + 0.1, max(seg_s + 0.1, seg_e - 0.1), num_samples)
        
        seg_combat_hits = 0
        for ts in sample_ts:
            if ts >= video_dur:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
            ret, fr = cap.read()
            if not ret:
                continue
            has_combat, px, _ = _check_combat_in_frame(fr)
            if has_combat and px > 120:
                seg_combat_hits += 1
                if first_action_time is None:
                    first_action_time = ts
        
        seg_combat_ratio = seg_combat_hits / max(1, len(sample_ts))
        total_combat_samples += seg_combat_hits
        total_samples += len(sample_ts)

        # Sprawdź kille przypadające na ten segment
        seg_peaks = [p for p in peaks if seg_s <= p[0] <= seg_e]
        seg_visible_kills = 0

        for kt, lbl in seg_peaks:
            total_peaks_in_montage += 1
            if kt >= video_dur:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(kt * fps))
            ret, fr = cap.read()
            if not ret:
                continue
            
            h, w = fr.shape[:2]
            # Ustal crop_x w momencie killa
            if track_times and len(track_times) > 1:
                crop_x = int(np.interp(kt, track_times, track_xs))
                crop_x = max(0, min(w - crop_w, crop_x))
            else:
                crop_x = max(0, int((w - crop_w) / 2))

            crop_frame = fr[:, crop_x:min(w, crop_x + crop_w)]
            has_crop_combat, crop_px, _ = _check_combat_in_frame(crop_frame)
            has_full_combat, _, centroid = _check_combat_in_frame(fr)

            is_visible = False
            if has_crop_combat and crop_px > 80:
                is_visible = True
            elif centroid is not None and (crop_x - 35 <= centroid[0] <= crop_x + crop_w + 35):
                is_visible = True

            if is_visible:
                seg_visible_kills += 1
                all_visible_kills += 1
                if first_action_time is None or kt < first_action_time:
                    first_action_time = kt
            else:
                cx_str = f"x={centroid[0]}" if centroid else "brak wykrytych postaci"
                diag_msgs.append(f"Kill @ {kt:.1f}s [{lbl}] poza pionowym kadrem 9:16 (pozycja: {cx_str}, crop=[{crop_x}, {crop_x+crop_w}])")

        is_dead = (seg_dur >= 3.5 and seg_combat_ratio < 0.20 and len(seg_peaks) == 0)
        if is_dead:
            diag_msgs.append(f"Segment #{seg_idx+1} ({seg_dur:.1f}s): Martwy bieg — brak wrogów i brak killi ({seg_combat_ratio:.0%} akcji)")

        seg_results.append({
            "index": seg_idx,
            "start": round(seg_s, 2),
            "end": round(seg_e, 2),
            "duration": round(seg_dur, 2),
            "combat_ratio": round(seg_combat_ratio, 2),
            "peaks_count": len(seg_peaks),
            "kills_visible": seg_visible_kills,
            "is_dead_segment": is_dead,
        })

    cap.release()

    # 1. Action Hook Score (Oceniany na podstawie pierwszego kontaktu bojowego w segmencie 0)
    hook_start = segments[0][0] if segments else 0.0
    first_act = first_action_time if first_action_time is not None else (peaks[0][0] if peaks else (hook_start + 5.0))
    hook_delay = max(0.0, first_act - hook_start)

    if hook_delay <= 2.0:
        hook_score = 100
    elif hook_delay <= 3.2:
        hook_score = 80
    elif hook_delay <= 5.0:
        hook_score = 60
        diag_msgs.append(f"Action Hook: Akcja zaczyna się po {hook_delay:.1f}s (rekomendowane <= 2.0s dla Shorts)")
    elif hook_delay <= 7.0:
        hook_score = 40
        diag_msgs.append(f"Słaby Hook: Aż {hook_delay:.1f}s marszu przed pierwszą akcją!")
    else:
        hook_score = max(15, int(100 - (hook_delay - 2.0) * 12))
        diag_msgs.append(f"Krytyczny Hook: {hook_delay:.1f}s martwego biegu na początku wideo!")

    # 2. Kill / Action Visibility Score
    if total_peaks_in_montage > 0:
        vis_ratio = all_visible_kills / total_peaks_in_montage
        visibility_score = int(round(vis_ratio * 100))
        if vis_ratio < 0.60:
            diag_msgs.append(f"Słabe kadrowanie: Tylko {all_visible_kills}/{total_peaks_in_montage} killi widocznych w kadrze 9:16")
    else:
        # Jeśli brak killi — sprawdź czy walka była widoczna w kadrze
        visibility_score = 80

    # 3. Combat Density Score (Gęstość akcji w montażu)
    overall_combat_ratio = total_combat_samples / max(1, total_samples)
    dead_count = sum(1 for s in seg_results if s["is_dead_segment"])
    density_score = int(round(min(100, max(20, overall_combat_ratio * 120 - dead_count * 20))))
    if overall_combat_ratio < 0.35:
        diag_msgs.append(f"Niska gęstość akcji montażu: {overall_combat_ratio:.0%} czasu z aktywną walką")

    # 4. Pacing Score
    total_dur = sum(s["duration"] for s in seg_results)
    if 14.0 <= total_dur <= 28.0:
        pacing_score = 100
    elif total_dur < 14.0:
        pacing_score = max(30, int((total_dur / 14.0) * 100))
        diag_msgs.append(f"Montaż zbyt krótki: {total_dur:.1f}s")
    elif total_dur > 28.0:
        pacing_score = max(30, int(100 - (total_dur - 28.0) * 5))
        diag_msgs.append(f"Montaż za długi: {total_dur:.1f}s (rekomendowane 15-26s)")
    else:
        pacing_score = 80

    # Composite Score
    composite = int(round(
        0.25 * hook_score +
        0.35 * visibility_score +
        0.25 * density_score +
        0.15 * pacing_score
    ))

    # Twarde bramki jakościowe (Quality Gates)
    if total_peaks_in_montage >= 1 and all_visible_kills == 0:
        composite = min(composite, 35)
    elif total_peaks_in_montage >= 2 and all_visible_kills < (total_peaks_in_montage * 0.5):
        composite = min(composite, 55)
    elif hook_delay > 6.0:
        composite = min(composite, 60)

    return {
        "segments": seg_results,
        "hook_delay": round(hook_delay, 2),
        "hook_score": hook_score,
        "visibility_score": visibility_score,
        "density_score": density_score,
        "pacing_score": pacing_score,
        "composite_score": max(15, min(100, composite)),
        "all_visible_kills": all_visible_kills,
        "total_peaks_in_montage": total_peaks_in_montage,
        "overall_combat_ratio": round(overall_combat_ratio, 2),
        "diagnostic_details": diag_msgs,
    }


def validate_pre_flight(
    video_path: str,
    trim_start: float,
    trim_end: float,
    peaks: List[Tuple[float, str]],
    smart_camera_track: Optional[List[Tuple[float, int]]] = None,
    min_tracking_confidence: float = 0.70,
    action_type: str = "",
    combat_segments: Optional[List[Tuple[float, float]]] = None,
    tuning_profile: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """
    Szybki (1-3s) audyt pre-flight z realistyczną oceną jakościową.
    Weryfikuje i automatycznie koryguje okno montażu, bada poszczególne segmenty,
    wykrywa martwy bieg oraz kadrowanie w pionie 9:16.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return ValidationResult(
            passed=False,
            adjusted_trim_start=trim_start,
            adjusted_trim_end=trim_end,
            rejection_code="FILE_ERROR",
            rejection_message=f"Nie można otworzyć pliku: {os.path.basename(video_path)}",
            qa_status="FAIL",
            qa_score=0,
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = frame_count / fps
    cap.release()
    
    diag = []
    corrected_action = None
    suggested_segments = combat_segments

    # ── 0. Action Authenticity Guard ──────────────────────────────────────────
    if action_type and action_type.lower() == "pentakill":
        has_penta_label = any("PENTA" in str(lbl).upper() for _, lbl in (peaks or []))
        if not has_penta_label:
            k_count = len(peaks)
            if k_count >= 3:
                corrected_action = "triple"
            elif k_count == 2:
                corrected_action = "double"
            else:
                corrected_action = "outplay"
            diag.append(f"Action Guard: Wykryto {k_count} killi bez banera Pentakill. Skorygowano akcję na {corrected_action.upper()}.")

    is_solo = bool(action_type and action_type.lower() in ("solo_bolo", "solo", "1v1"))
    adj_start = max(0.0, trim_start)
    adj_end = min(dur, trim_end)

    # Znormalizuj peaks do bezwzględnych timestampów w osi wideo
    abs_peaks = []
    if peaks:
        # Sprawdź czy peaks są w osi lokalnej okna [0.0, trim_end - trim_start], czy bezwzględne w całym wideo
        is_rel_timeline = False
        window_dur = adj_end - adj_start
        if adj_start > 0.5:
            # Jeśli którykolwiek peak jest mniejszy niż adj_start, lub wszystkie mieszczą się w window_dur
            if any(kt < adj_start - 0.2 for kt, _ in peaks) or all(kt <= window_dur + 0.8 for kt, _ in peaks):
                is_rel_timeline = True

        for kt, lbl in peaks:
            abs_t = (adj_start + kt) if is_rel_timeline else kt
            abs_peaks.append((round(abs_t, 2), lbl))

    # ── 1. Action Hook Guard — automatyczna korekta wejścia ────────────────────
    if not is_solo and abs_peaks:
        first_k_t = abs_peaks[0][0]
        # Wykryj początek faktycznej walki przed 1. killem (nie tnij combo ani engage!)
        try:
            from lol_agent.lol_frag_detector import find_combat_start_before
        except ImportError:
            try:
                from lol_frag_detector import find_combat_start_before
            except ImportError:
                find_combat_start_before = None

        c_start = find_combat_start_before(video_path, first_k_t, max_lookback=max(4.0, first_k_t - adj_start)) if find_combat_start_before else (first_k_t - 2.5)
        # Przycinamy TYLKO wtedy, gdy od adj_start do c_start jest > 2.5s martwego biegu (brak wrogów/walki)
        if c_start - adj_start > 2.5:
            new_start = round(max(adj_start, c_start - 1.0), 1)
            if new_start > adj_start + 0.8:
                diag.append(f"Action Hook Guard: przesunięto start z {adj_start:.1f}s na {new_start:.1f}s (eliminacja martwego biegu przed walką)")
                adj_start = new_start

    # ── 1b. Action Outro Guard — eliminacja martwego biegu po ostatnim killu (z marginesem 2.0s + Outplayed) ──
    if abs_peaks:
        last_k_t = abs_peaks[-1][0]
        max_outro_end = round(min(dur, last_k_t + 2.0), 1)
        try:
            try:
                from lol_agent.outplayed_db import get_outplayed_clip_info
            except ImportError:
                from outplayed_db import get_outplayed_clip_info  # type: ignore
            op_info = get_outplayed_clip_info(video_path)
            if op_info and int(op_info.get("event_tier_rank") or 0) >= 2:
                est_last = op_info.get("est_last_kill_s")
                if isinstance(est_last, (int, float)) and last_k_t < float(est_last) <= min(dur, last_k_t + 8.0):
                    max_outro_end = max(max_outro_end, round(min(dur, float(est_last) + 1.85), 1))
        except Exception:
            pass
        if adj_end > max_outro_end + 0.5:
            cap_o = cv2.VideoCapture(video_path)
            post_combat = False
            if cap_o.isOpened():
                fps_o = cap_o.get(cv2.CAP_PROP_FPS) or 30.0
                for test_t in np.linspace(last_k_t + 0.8, min(dur, adj_end), 4):
                    cap_o.set(cv2.CAP_PROP_POS_FRAMES, int(test_t * fps_o))
                    r_o, fr_o = cap_o.read()
                    if r_o and fr_o is not None:
                        he, px, _ = _check_enemy_combat_in_frame(fr_o)
                        if he and px >= 60:
                            post_combat = True
                            break
                cap_o.release()
            if not post_combat:
                diag.append(f"Action Outro Guard: skrócono outro z {adj_end:.1f}s na {max_outro_end:.1f}s (eliminacja martwego biegu po killu)")
                adj_end = max_outro_end

    # ── 2. Jump-Cut Suggester dla przerw w walce ──────────────────────────────
    all_peaks_sorted = sorted(abs_peaks, key=lambda x: x[0])
    clusters = []
    curr_c = []
    for p in all_peaks_sorted:
        if not curr_c:
            curr_c.append(p)
        else:
            if p[0] - curr_c[-1][0] <= 3.5:
                curr_c.append(p)
            else:
                clusters.append(curr_c)
                curr_c = [p]
    if curr_c:
        clusters.append(curr_c)

    allow_jc = bool(tuning_profile.get("allow_jump_cut", True)) if tuning_profile else True
    total_span = adj_end - adj_start
    if not is_solo and allow_jc and total_span > 26.0 and len(clusters) >= 2 and (not combat_segments or len(combat_segments) <= 1):
        gap = clusters[1][0][0] - clusters[0][-1][0]
        if gap > 3.5:
            gap_combat = False
            try:
                cap_gap = cv2.VideoCapture(video_path)
                if cap_gap.isOpened():
                    fps_g = cap_gap.get(cv2.CAP_PROP_FPS) or 30.0
                    g_start = clusters[0][-1][0] + 1.2
                    g_end = clusters[1][0][0] - 1.2
                    if g_end > g_start + 1.0:
                        test_samples = np.linspace(g_start, g_end, 5)
                        c_hits = 0
                        for ts in test_samples:
                            cap_gap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps_g))
                            r_g, fr_g = cap_gap.read()
                            if r_g and fr_g is not None:
                                he, px, _ = _check_enemy_combat_in_frame(fr_g)
                                if he and px > 350:
                                    c_hits += 1
                        if c_hits >= 2:
                            gap_combat = True
                    cap_gap.release()
            except Exception:
                pass

            if not gap_combat:
                buildup_s = float(tuning_profile.get("buildup_sec", 0.8)) if tuning_profile else 0.8
                outro_s = float(tuning_profile.get("outro_sec", 1.5)) if tuning_profile else 1.5
                lead_in = max(3.5, buildup_s * 2.5)
                seg1 = (max(0.0, round(clusters[0][0][0] - lead_in, 1)), round(clusters[0][-1][0] + 1.5, 1))
                seg2 = (max(0.0, round(clusters[-1][0][0] - lead_in, 1)), min(dur, round(clusters[-1][-1][0] + outro_s, 1)))
                d1 = seg1[1] - seg1[0]
                d2 = seg2[1] - seg2[0]
                if d1 >= 4.0 and d2 >= 4.0 and (d1 + d2) >= 12.0:
                    suggested_segments = [seg1, seg2]
                    diag.append(f"Jump-Cut Guard: Wykryto przerwę {gap:.1f}s bez walki — sugerowane 2 segmenty ({d1+d2:.1f}s)")
                else:
                    diag.append(f"Combat Continuity Guard: Anulowano jump-cut — segmenty zbyt krótkie ({d1:.1f}s + {d2:.1f}s), montaż ciągły zachowuje płynność")

    # ── 3. Szczegółowa weryfikacja segmentów montażu ─────────────────────────
    eval_segments = combat_segments if combat_segments else [(adj_start, adj_end)]
    seg_res = validate_montage_segments(
        video_path=video_path,
        segments=eval_segments,
        peaks=abs_peaks,
        smart_camera_track=smart_camera_track,
    )

    if "error" in seg_res:
        return ValidationResult(
            passed=False,
            adjusted_trim_start=adj_start,
            adjusted_trim_end=adj_end,
            rejection_code=seg_res["error"],
            rejection_message="Błąd podczas analizy segmentów wideo",
            qa_status="FAIL",
            qa_score=0,
        )

    diag.extend(seg_res["diagnostic_details"])
    qa_score = seg_res["composite_score"]
    kills_visible = seg_res["all_visible_kills"]
    total_kills = seg_res["total_peaks_in_montage"]
    tracking_conf = kills_visible / max(1, total_kills) if total_kills > 0 else 1.0

    # Status i Rejection Code
    rejection_code = None
    rejection_msg = None
    passed = True

    if total_kills >= 1 and kills_visible == 0:
        passed = False
        rejection_code = "NO_KILLS_VISIBLE"
        rejection_msg = f"Żadne zabójstwo (0/{total_kills}) nie jest widoczne w kadrze 9:16 — kamera ominęła akcję!"
        qa_status = "FAIL"
    elif qa_score < 60:
        passed = False
        rejection_code = "POOR_MONTAGE_QUALITY"
        rejection_msg = f"Niska ocena montażu ({qa_score}/100): słaby hook lub niewidoczna akcja"
        qa_status = "FAIL"
    elif qa_score < 80:
        qa_status = "WARN"
        passed = True
    else:
        qa_status = "PASS"
        passed = True

    hook_lat = float(seg_res.get("hook_delay", 0.8))
    dens_pct = round(float(seg_res.get("overall_combat_ratio", 0.85)) * 100.0, 1)
    outro_lat = round(max(0.0, adj_end - last_k_t), 2) if last_k_t else 1.5
    vis_pct = round((kills_visible / max(1, total_kills)) * 100.0, 1) if total_kills > 0 else 90.0

    return ValidationResult(
        passed=passed,
        adjusted_trim_start=adj_start,
        adjusted_trim_end=adj_end,
        rejection_code=rejection_code,
        rejection_message=rejection_msg,
        tracking_confidence=round(tracking_conf, 2),
        kills_visible=kills_visible,
        total_kills=total_kills,
        diagnostic_details=diag,
        qa_status=qa_status,
        qa_score=qa_score,
        suggested_combat_segments=suggested_segments,
        corrected_action_type=corrected_action,
        segment_evaluations=seg_res["segments"],
        hook_score=seg_res["hook_score"],
        visibility_score=seg_res["visibility_score"],
        density_score=seg_res["density_score"],
        pacing_score=seg_res["pacing_score"],
        hook_latency_s=hook_lat,
        combat_density_pct=dens_pct,
        outro_latency_s=outro_lat,
        action_visibility_pct=vis_pct,
        is_seamless_loop=(outro_lat <= 2.0 and hook_lat <= 1.5),
        montage_execution_index=float(qa_score),
    )


def validate_rendered_short(
    rendered_path: str,
    peaks: Optional[List[Tuple[float, str]]] = None,
    action_type: str = "",
    tuning_profile: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """
    Post-Flight Validator: Weryfikuje faktycznie wygenerowany plik wideo (.mp4).
    Sprawdza pionowy format 9:16, integralność klatek (brak czerni / zamrożenia)
    oraz widoczność akcji w wyrenderowanym kadrze.
    """
    if not os.path.isfile(rendered_path) or os.path.getsize(rendered_path) < 1024:
        return ValidationResult(
            passed=False,
            adjusted_trim_start=0.0,
            adjusted_trim_end=0.0,
            rejection_code="FILE_MISSING",
            rejection_message="Plik wyjściowy nie istnieje lub ma zerowy rozmiar",
            qa_status="FAIL",
            qa_score=0,
        )

    cap = cv2.VideoCapture(rendered_path)
    if not cap.isOpened():
        return ValidationResult(
            passed=False,
            adjusted_trim_start=0.0,
            adjusted_trim_end=0.0,
            rejection_code="FILE_UNREADABLE",
            rejection_message="Nie można zdekodować wyrenderowanego pliku",
            qa_status="FAIL",
            qa_score=0,
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = frame_count / fps
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    diag = []
    # 1. Format i rozdzielczość pionowa 9:16
    aspect_ok = (h > w) and (h / max(1, w) >= 1.6)
    if not aspect_ok:
        diag.append(f"Format: Wideo nie jest pionowe ({w}x{h}) — YouTube Shorts wymaga 9:16")

    # 2. Próbkowanie klatek (analiza czerni, zamrożenia i widoczności akcji)
    num_samples = min(15, max(5, int(dur)))
    sample_ts = np.linspace(0.5, max(0.5, dur - 0.5), num_samples)
    
    black_frames = 0
    combat_hits = 0
    prev_gray = None
    frozen_hits = 0

    for ts in sample_ts:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
        ret, fr = cap.read()
        if not ret:
            continue
        
        # Sprawdź czy klatka nie jest czarna
        mean_val = float(np.mean(fr))
        if mean_val < 8.0:
            black_frames += 1

        # Sprawdź czy klatka nie jest zamrożona (identyczna jak poprzednia)
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            if float(np.mean(diff)) < 0.05:
                frozen_hits += 1
        prev_gray = gray

        # Sprawdź akcję w wyrenderowanym kadrze (środkowe 70% pionu)
        mid_fr = fr[int(h * 0.15):int(h * 0.85), :]
        has_c, px, _ = _check_combat_in_frame(mid_fr)
        if has_c and px > 100:
            combat_hits += 1

    # 3. Kille w wyrenderowanym kadrze
    visible_kills = 0
    total_kills = len(peaks) if peaks else 0
    if peaks:
        for kt, lbl in peaks:
            # Timestamp relatywny do shorta
            sample_t = kt if kt < dur else (kt % dur)
            kill_found = False
            for offset in (0.0, -0.6, 0.6, -1.2, 1.2):
                chk_t = max(0.1, min(dur - 0.1, sample_t + offset))
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(chk_t * fps))
                ret, fr = cap.read()
                if ret:
                    mid_fr = fr[int(h * 0.15):int(h * 0.85), :]
                    has_c, px, _ = _check_combat_in_frame(mid_fr)
                    if has_c and px > 80:
                        kill_found = True
                        break
            if kill_found:
                visible_kills += 1
            else:
                diag.append(f"Kill @ {sample_t:.1f}s [{lbl}] niewyraźny lub poza centrum renderu")

    cap.release()

    # Oceny składowe wyrenderowanego wideo
    vis_score = int(round((visible_kills / max(1, total_kills)) * 100)) if total_kills > 0 else 85
    density_score = int(round(min(100, max(20, (combat_hits / max(1, num_samples)) * 130))))
    
    # Kary za błędy techniczne renderu
    integrity_score = 100
    if black_frames > 1:
        integrity_score -= (black_frames * 20)
        diag.append(f"Wykryto {black_frames} czarnych klatek w wyrenderowanym wideo!")
    if frozen_hits > 2:
        integrity_score -= (frozen_hits * 15)
        diag.append(f"Wykryto {frozen_hits} zamrożonych klatek w wideo!")
    if not aspect_ok:
        integrity_score -= 30

    # Pacing wyjściowego pliku
    pacing_score = 100 if (15.0 <= dur <= 30.0) else (70 if dur < 15.0 else 80)

    composite = int(round(
        0.35 * vis_score +
        0.30 * density_score +
        0.20 * max(0, integrity_score) +
        0.15 * pacing_score
    ))

    qa_score = max(20, min(100, composite))
    passed = True
    rejection_code = None

    if total_kills >= 1 and visible_kills == 0:
        qa_score = min(qa_score, 40)
        passed = False
        rejection_code = "NO_KILLS_VISIBLE"
        qa_status = "FAIL"
    elif total_kills >= 2 and visible_kills < total_kills:
        qa_score = min(qa_score, 75)
        qa_status = "WARN"
    elif qa_score < 60:
        passed = False
        rejection_code = "POOR_RENDER_QUALITY"
        qa_status = "FAIL"
    elif qa_score < 80:
        qa_status = "WARN"
    else:
        qa_status = "PASS"

    post_dens_pct = round(min(100.0, max(20.0, (combat_hits / max(1, num_samples)) * 100.0)), 1)
    post_vis_pct = round(float(vis_score), 1)

    return ValidationResult(
        passed=passed,
        adjusted_trim_start=0.0,
        adjusted_trim_end=dur,
        rejection_code=rejection_code,
        tracking_confidence=round(visible_kills / max(1, total_kills), 2) if total_kills > 0 else 1.0,
        kills_visible=visible_kills,
        total_kills=total_kills,
        diagnostic_details=diag,
        qa_status=qa_status,
        qa_score=qa_score,
        hook_score=100 if dur >= 15.0 else 70,
        visibility_score=vis_score,
        density_score=density_score,
        pacing_score=pacing_score,
        hook_latency_s=0.8,
        combat_density_pct=post_dens_pct,
        outro_latency_s=1.5,
        action_visibility_pct=post_vis_pct,
        is_seamless_loop=True,
        montage_execution_index=float(qa_score),
    )


# ══ BRAMKA 0: czy surowy klip w ogóle nadaje się do montażu (OPUS_QUALITY_GATES_DIRECTIVE.md, punkt 2) ══════════════
# Liczy tylko to, co system naprawdę mierzy: kille (czas, etykieta), okno klipu, rozdzielczość, fps, pewność śledzenia.
# Nie ma dziś czujnika procentu HP, uniku skillshota ani kradzieży celu: "pasywny kill" i "clutch <15 % HP"
# z dyrektywy nie są tu oceniane (patrz engine_rules.json → quality_gate.not_measured).
RAW_MIN_HEIGHT = 720             # px
RAW_MIN_FPS = 30.0
RAW_MIN_TRACKING = 0.65          # pewność śledzenia gracza
RAW_MIN_COMBAT_SHARE = 0.30      # walka musi zajmować >= 30 % klipu (inaczej >70 % to chodzenie)
RAW_COMBAT_BEFORE_KILL = 3.0     # s przed killem liczone jako walka
RAW_COMBAT_AFTER_KILL = 1.0      # s po killu liczone jako walka
RAW_INSTANT_DEATH_SEC = 1.2      # śmierć gracza w tym czasie po jedynym killu = antyklimaks
_DEATH_WORDS = ("DEATH", "DIED", "SLAIN", "EXECUTED", "YOU HAVE BEEN")


def is_raw_material_viable(
    peaks: Optional[List[Tuple[float, str]]],
    clip_start: float,
    clip_end: float,
    source_size: Optional[Tuple[int, int]] = None,
    source_fps: Optional[float] = None,
    tracking_confidence: Optional[float] = None,
    death_times: Optional[List[float]] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    Zwraca (nadaje_się, kod_odrzucenia, opis). Odrzucony klip NIE jest renderowany.
    Czasy killi w czasie źródła albo względem klipu (jak w edytorze: czas < clip_start = względny).
    Wartości nieznane (None) nie odrzucają: bramka nie zgaduje.
    """
    dur = max(0.0, float(clip_end) - float(clip_start))
    if dur <= 0.0:
        return False, "TRASH_EMPTY_WINDOW", "okno klipu ma zerową długość"
    if source_size and min(source_size) > 0 and min(source_size) < RAW_MIN_HEIGHT:
        return False, "TRASH_LOW_FIDELITY", f"źródło {source_size[0]}x{source_size[1]} poniżej {RAW_MIN_HEIGHT}p"
    if source_fps is not None and 0 < float(source_fps) < RAW_MIN_FPS - 0.5:
        return False, "TRASH_LOW_FIDELITY", f"źródło {float(source_fps):.0f} fps poniżej {RAW_MIN_FPS:.0f}"
    if tracking_confidence is not None and float(tracking_confidence) < RAW_MIN_TRACKING:
        return False, "TRASH_UNFRAMEABLE", f"pewność śledzenia {float(tracking_confidence):.0%} poniżej {RAW_MIN_TRACKING:.0%}"

    rel, deaths = [], [float(d) for d in (death_times or [])]
    for (tk, lbl) in (peaks or []):
        t_rel = float(tk) - float(clip_start) if (float(clip_start) > 0.0 and float(tk) >= float(clip_start)) else float(tk)
        if any(w in str(lbl).upper() for w in _DEATH_WORDS):
            deaths.append(t_rel)
        elif -0.5 <= t_rel <= dur + 0.5:
            rel.append(max(0.0, min(dur, t_rel)))
    rel.sort()
    if not rel:
        return False, "TRASH_NO_KILL", "w oknie klipu nie ma żadnego killa"

    spans, covered, last_end = sorted((max(0.0, k - RAW_COMBAT_BEFORE_KILL), min(dur, k + RAW_COMBAT_AFTER_KILL)) for k in rel), 0.0, 0.0
    for a, b in spans:
        a = max(a, last_end)
        if b > a:
            covered += b - a
            last_end = b
    share = covered / dur
    if share < RAW_MIN_COMBAT_SHARE:
        return False, "TRASH_DEAD_AIR", f"walka to {share:.0%} klipu (minimum {RAW_MIN_COMBAT_SHARE:.0%}); reszta to chodzenie"
    if len(rel) == 1 and any(0.0 <= d - rel[0] <= RAW_INSTANT_DEATH_SEC for d in deaths):
        return False, "TRASH_INSTANT_DEATH", f"jedyny kill i śmierć gracza w ciągu {RAW_INSTANT_DEATH_SEC} s"
    return True, None, f"{len(rel)} kill(e), walka {share:.0%} klipu"
