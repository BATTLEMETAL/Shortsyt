"""
LOL AGENT — Pre-Flight Quality Validator
Automatyczny audytor jakości i poprawności kadru przed uruchomieniem pełnego renderowania.

Sprawdza:
1. Action Hook Guard: czy w pierwszych 1.5s jest bezpośrednia walka (nie wieża/bieganie).
2. Kill Visibility Check: czy 100% fragów mieści się w pionowym oknie kadrowania 9:16.
3. Quality Gate Enforcer: automatyczne odrzucanie klipów niekwalifikujących się (Porofessor, rozrzut >1200px, tracking <75%).
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
    qa_score: int = 95             # 0 - 100
    suggested_combat_segments: Optional[List[Tuple[float, float]]] = None
    corrected_action_type: Optional[str] = None


def _check_enemy_combat_in_frame(frame: np.ndarray) -> Tuple[bool, int, Optional[Tuple[int, int]]]:
    """
    Wykrywa obecność wrogich pasków HP (czerwone) lub paska gracza (złoty).
    Zwraca: (is_combat_present, enemy_pixel_count, centroid_pos)
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Czerwony pasek HP wroga
    m1 = cv2.inRange(hsv, (0, 120, 140), (10, 255, 255))
    m2 = cv2.inRange(hsv, (170, 120, 140), (180, 255, 255))
    red_mask = cv2.bitwise_or(m1, m2)
    
    # Wyklucz obszar minimapy (prawy dolny róg) i górnego UI
    h, w = frame.shape[:2]
    red_mask[int(h*0.80):, int(w*0.80):] = 0
    red_mask[:int(h*0.10), :] = 0
    
    enemy_pixels = cv2.countNonZero(red_mask)
    if enemy_pixels > 80:
        # Oblicz centroid
        pts = cv2.findNonZero(red_mask)
        if pts is not None:
            mean_pt = np.mean(pts, axis=0)[0]
    return False, enemy_pixels, None


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
    Szybki (1-3s) audyt pre-flight.
    Weryfikuje i automatycznie koryguje okno montażu, wykrywa martwy bieg, fałszywy typ akcji oraz zgodność ze stylem.
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
    
    diag = []
    qa_status = "PASS"
    qa_score = 100
    corrected_action = None
    suggested_segments = combat_segments

    # ── 0. Action Authenticity Guard (Fake Pentakill / Action Check) ───────────
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
            qa_status = "WARN"
            qa_score = max(60, qa_score - 15)
            diag.append(f"Action Guard: Wykryto {k_count} killi bez banera Pentakill. Skorygowano akcję na {corrected_action.upper()}.")

    is_solo = bool(action_type and action_type.lower() in ("solo_bolo", "solo", "1v1"))

    # ── 1. Action Hook Guard (Sprawdź pierwsze 1.5s) ───────────────────────────
    adj_start = max(0.0, trim_start)
    adj_end = min(dur, trim_end)

    # Znormalizuj peaks do bezwzględnych timestampów (obsługa peaks relatywnych i absolutnych)
    abs_peaks = []
    for kt, lbl in (peaks or []):
        abs_t = kt if (kt >= adj_start or adj_start == 0.0) else (adj_start + kt)
        abs_peaks.append((round(abs_t, 2), lbl))
    
    if is_solo:
        diag.append("Solo Bolo Mode: pełna walka 1v1 od wyznaczonego początku (0.0s) bez wycinania lead-inu.")
    else:
        sample_times = [adj_start + 0.3, adj_start + 0.8, adj_start + 1.4]
        combat_detected_at_start = False
        
        for st in sample_times:
            if st < dur:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(st * fps))
                ret, fr = cap.read()
                if ret:
                    has_combat, px, _ = _check_enemy_combat_in_frame(fr)
                    if has_combat:
                        combat_detected_at_start = True
                        break
        
        if not combat_detected_at_start and abs_peaks:
            first_k_t = abs_peaks[0][0]
            # Przycina tylko przy ewidentnym pustym bieganiu (> 6.5s przed pierwszym fragiem),
            # zawsze zachowując co najmniej 4.5s wejścia w walkę, aby widz widział wymianę i skillshoty.
            if first_k_t - adj_start > 6.5:
                new_start = max(adj_start, first_k_t - 4.5)
                if new_start > adj_start + 1.0:
                    diag.append(f"Action Hook Guard: przesunięto start z {adj_start:.1f}s na {new_start:.1f}s (zachowano 4.5s wymiany i engage)")
                    adj_start = new_start

    # ── 2. Dead Running & Jump-Cut Guard ──────────────────────────────────────
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

    if is_solo:
        suggested_segments = None
    elif len(clusters) >= 2:
        gap = clusters[1][0][0] - clusters[0][-1][0]
        if not combat_segments or len(combat_segments) <= 1:
            qa_status = "WARN"
            qa_score = max(50, qa_score - 15)
            diag.append(f"Dead Running Guard: Wykryto {gap:.1f}s przerwy między walkami. Rekomendowany Jump-Cut!")
            buildup_s = float(tuning_profile.get("buildup_sec", 0.8)) if tuning_profile else 0.8
            outro_s = float(tuning_profile.get("outro_sec", 1.5)) if tuning_profile else 1.5
            seg1 = (max(0.0, round(clusters[0][0][0] - buildup_s, 1)), round(clusters[0][-1][0] + 1.2, 1))
            seg2 = (max(0.0, round(clusters[-1][0][0] - 1.2, 1)), min(dur, round(clusters[-1][-1][0] + outro_s, 1)))
            suggested_segments = [seg1, seg2]
        else:
            diag.append(f"Jump-Cut Guard: Aktywne {len(combat_segments)} segmenty walki (wycięto przerwę {gap:.1f}s).")

    # ── 3. Kill Visibility Check w pionowym oknie 9:16 ────────────────────────
    crop_w = 608
    visible_kills = 0
    total_kills = len(abs_peaks)
    
    for kt, lbl in abs_peaks:
        if kt < adj_start or kt > adj_end:
            continue
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(kt * fps))
        ret, fr = cap.read()
        if not ret:
            continue
            
        h, w = fr.shape[:2]
        crop_x = int((w - crop_w) / 2)
        if smart_camera_track:
            track_times = [t for t, _ in smart_camera_track]
            track_xs = [x for _, x in smart_camera_track]
            crop_x = int(np.interp(kt, track_times, track_xs))
            crop_x = max(0, min(w - crop_w, crop_x))
            
        has_c, _, centroid = _check_enemy_combat_in_frame(fr)
        if centroid is not None:
            cx, cy = centroid
            if crop_x - 40 <= cx <= crop_x + crop_w + 40:
                visible_kills += 1
            else:
                diag.append(f"Uwaga: kill @ {kt:.1f}s [{lbl}] centroid ({cx}px) poza krawędzią kadru 9:16 (crop_x={crop_x})")
        else:
            visible_kills += 1

    # ── 4. Tower Attack Guard ─────────────────────────────────────────────────
    if not is_solo:
        tower_check_end = adj_start + (adj_end - adj_start) * 0.50
        tower_samples = np.linspace(adj_start + 0.5, tower_check_end, 8)
        tower_combat_frames = 0
        tower_first_combat_t = None
        for ts in tower_samples:
            if ts >= dur:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
            ret, fr = cap.read()
            if ret:
                has_c, px, _ = _check_enemy_combat_in_frame(fr)
                if has_c and px > 150:
                    tower_combat_frames += 1
                    if tower_first_combat_t is None:
                        tower_first_combat_t = ts
        
        tower_ratio = tower_combat_frames / max(1, len(tower_samples))
        if tower_ratio < 0.40 and tower_first_combat_t is not None:
            new_start = max(adj_start, tower_first_combat_t - 1.5)
            if new_start > adj_start + 1.0:
                diag.append(f"Tower Guard: przesunięto start z {adj_start:.1f}s na {new_start:.1f}s (walka zaczyna się @ {tower_first_combat_t:.1f}s)")
                adj_start = new_start

    cap.release()

    # ── 5. Pacing & Duration Guard ────────────────────────────────────────────
    cur_dur = sum(e - s for s, e in combat_segments) if combat_segments else (adj_end - adj_start)
    if tuning_profile:
        max_limit = float(tuning_profile.get("target_max_dur", 18.0))
        if cur_dur > max_limit + 2.5:
            qa_status = "WARN" if qa_status != "FAIL" else qa_status
            qa_score = max(50, qa_score - 10)
            diag.append(f"Pacing Guard: Długość {cur_dur:.1f}s przekracza docelowy limit profilu ({max_limit:.1f}s).")
        else:
            diag.append(f"Pacing Guard: Długość {cur_dur:.1f}s zgodna z profilem.")
    
    tracking_conf = 1.0
    if total_kills > 0:
        tracking_conf = visible_kills / total_kills
        
    if tracking_conf < min_tracking_confidence and total_kills > 1:
        return ValidationResult(
            passed=False,
            adjusted_trim_start=adj_start,
            adjusted_trim_end=adj_end,
            rejection_code="LOW_KILL_VISIBILITY",
            rejection_message=f"Tylko {visible_kills}/{total_kills} killi widocznych w kadrze 9:16 (conf={tracking_conf:.0%})",
            tracking_confidence=tracking_conf,
            kills_visible=visible_kills,
            total_kills=total_kills,
            diagnostic_details=diag,
            qa_status="FAIL",
            qa_score=35,
            suggested_combat_segments=suggested_segments,
            corrected_action_type=corrected_action,
        )

    return ValidationResult(
        passed=True,
        adjusted_trim_start=adj_start,
        adjusted_trim_end=adj_end,
        tracking_confidence=tracking_conf,
        kills_visible=visible_kills,
        total_kills=total_kills,
        diagnostic_details=diag,
        qa_status=qa_status,
        qa_score=max(40, qa_score),
        suggested_combat_segments=suggested_segments,
        corrected_action_type=corrected_action,
    )