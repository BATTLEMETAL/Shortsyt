"""
LOL Agent — Smart Clutch & Action Quality Evaluator
Odróżnia spektakularne, emocjonujące akcje od nudnych stomp-killi.

Kluczowe sygnały jakości (0-100):
  1. Kill Weight       (35%) — PENTA (100), QUADRA (75), TRIPLE (50), DOUBLE (25)
  2. Pacing Density    (25%) — Czas między 1. a ostatnim killem (<6s = 100, >15s = 20)
  3. Clutch Factor     (20%) — Czy HP gracza spadło <30% przed serią killów (dramaturgia)
  4. Motion & VFX      (20%) — Chaos i dynamika czarów na ekranie (motion + vfx)
"""
import os
import sys
import re
import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Add lol_agent root and project root to sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_lol_agent_dir = os.path.dirname(_current_dir)
_project_root = os.path.dirname(_lol_agent_dir)
for _p in (_lol_agent_dir, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Tesseract setup
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
except ImportError:
    pass

KILL_WEIGHTS = {
    "PENTAKILL": 100.0,
    "QUADRAKILL": 75.0,
    "TRIPLE KILL": 50.0,
    "DOUBLE KILL": 25.0,
    "KILL": 10.0,
}


def evaluate_clip_quality(video_path: str, fast_mode: bool = False) -> dict:
    """
    Pełna ocena merytoryczna i emocjonalna klipu z League of Legends.
    Zwraca słownik z composite_score (0-100), tier (S/A/B/REJECT) i szczegółowymi metrykami.
    """
    if not os.path.exists(video_path):
        return {"error": f"File not found: {video_path}", "worthy": False, "score": 0}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": f"Cannot open video: {video_path}", "worthy": False, "score": 0}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    if duration < 5.0:
        cap.release()
        return {"error": "Clip too short (<5s)", "worthy": False, "score": 0, "tier": "REJECT"}

    # ── 1. OCR Kills Scan ──────────────────────────────────────────────────────
    from lol_momentum_analyzer import _compute_kill_scores
    scores_list, detected_kills = _compute_kill_scores(cap, fps, use_ocr=True)

    # ── 2. Kill Weight Score (35%) ─────────────────────────────────────────────
    highest_kill = "NONE"
    kill_weight_score = 0.0
    if detected_kills:
        for _, label in detected_kills:
            w = KILL_WEIGHTS.get(label.upper(), 10.0)
            if w > kill_weight_score:
                kill_weight_score = w
                highest_kill = label.upper()

    # ── 3. Pacing Density Score (25%) ──────────────────────────────────────────
    # Im szybciej fragi padają po sobie, tym większa dynamika dla widza
    pacing_score = 0.0
    pacing_delta = 0.0
    if len(detected_kills) >= 2:
        pacing_delta = detected_kills[-1][0] - detected_kills[0][0]
        if pacing_delta <= 4.5:
            pacing_score = 100.0   # Błyskawiczny reset (np. Katarina Shunpo combo)
        elif pacing_delta <= 7.5:
            pacing_score = 85.0    # Bardzo dynamiczna walka
        elif pacing_delta <= 12.0:
            pacing_score = 65.0    # Typowy teamfight
        elif pacing_delta <= 18.0:
            pacing_score = 40.0    # Rozciągnięty pościg
        else:
            pacing_score = 15.0    # Zbyt wolne fragi
    elif len(detected_kills) == 1:
        pacing_score = 40.0
    else:
        pacing_score = 10.0

    # ── 4. Clutch HP Factor (20%) ──────────────────────────────────────────────
    # Sprawdza czy gracz był bliski śmierci (żółty pasek HP) w trakcie walki
    clutch_score = 50.0   # domyślnie neutralne 50 pkt
    is_clutch = False
    lowest_hp_ratio = 1.0

    try:
        # Próbkuj klatki wokół pierwszego killa
        sample_start_t = max(0.0, (detected_kills[0][0] - 3.0) if detected_kills else (duration * 0.2))
        sample_end_t   = min(duration, (detected_kills[-1][0] + 1.0) if detected_kills else (duration * 0.8))
        
        start_f = int(sample_start_t * fps)
        end_f   = int(sample_end_t * fps)
        step_f  = max(1, int(fps * 0.4))  # co ~0.4s

        hp_widths = []
        for f_idx in range(start_f, end_f, step_f):
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            
            # Wytnij żółty pasek HP gracza
            h, w = frame.shape[:2]
            # Maska żółtego paska gracza: R>160, G>130, B<110
            r, g, b = frame[:, :, 2], frame[:, :, 1], frame[:, :, 0]
            yellow_mask = (r > 160) & (g > 130) & (b < 110) & ((r.astype(int) - b.astype(int)) > 80)
            
            # Wyklucz górny HUD i minimapę
            yellow_mask[:int(h * 0.10), :] = 0
            yellow_mask[int(h * 0.82):, :] = 0
            
            non_zeros = np.count_nonzero(yellow_mask)
            if non_zeros > 10:
                hp_widths.append(non_zeros)

        # Check if player is alive at the end of the clip (aftermath + trailing frames)
        player_died = False
        
        # Check trailing frames (last 2.5s of clip)
        trail_start_t = max(0.0, duration - 2.5)
        trail_f_indices = [int(t * fps) for t in np.linspace(trail_start_t, duration - 0.2, 5)]
        
        trailing_hp_counts = []
        trailing_saturations = []
        
        for f_idx in trail_f_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret_t, frame_t = cap.read()
            if ret_t and frame_t is not None:
                h_t, w_t = frame_t.shape[:2]
                r_t, g_t, b_t = frame_t[:, :, 2], frame_t[:, :, 1], frame_t[:, :, 0]
                
                # HP bar check
                y_mask_t = (r_t > 160) & (g_t > 130) & (b_t < 110) & ((r_t.astype(int) - b_t.astype(int)) > 80)
                y_mask_t[:int(h_t * 0.10), :] = 0
                y_mask_t[int(h_t * 0.82):, :] = 0
                trailing_hp_counts.append(np.count_nonzero(y_mask_t))
                
                # Gray screen check (center gameplay area saturation)
                roi_center = frame_t[int(h_t * 0.2):int(h_t * 0.8), int(w_t * 0.2):int(w_t * 0.8)]
                hsv_roi = cv2.cvtColor(roi_center, cv2.COLOR_BGR2HSV)
                mean_sat = float(np.mean(hsv_roi[:, :, 1]))
                trailing_saturations.append(mean_sat)

        # Player is dead if:
        # 1. Zero player HP detected in trailing frames, OR
        # 2. Trailing screen saturation drops < 38 (monochrome gray death screen)
        if trailing_hp_counts and max(trailing_hp_counts) < 6:
            player_died = True
        elif trailing_saturations and min(trailing_saturations) < 38.0:
            player_died = True

        if hp_widths and not player_died:
            max_hp_px = max(hp_widths)
            min_hp_px = min(hp_widths)
            if max_hp_px > 30:
                lowest_hp_ratio = min_hp_px / float(max_hp_px)
                if lowest_hp_ratio < 0.35:
                    clutch_score = 100.0   # Przeżycie na <35% HP = MEGA CLUTCH!
                    is_clutch = True
                elif lowest_hp_ratio < 0.60:
                    clutch_score = 80.0
                    is_clutch = True
                elif lowest_hp_ratio > 0.90:
                    clutch_score = 40.0    # 100% HP przez cały czas = mniejsze emocje
        elif player_died:
            clutch_score = 0.0
    except Exception as e:
        pass

    cap.release()

    # ── 5. Motion & VFX Intensity (20%) ────────────────────────────────────────
    # Proporcjonalne do gęstości akcji i wykrytych killów
    motion_vfx_score = min(100.0, 40.0 + (len(detected_kills) * 20.0))

    # ── 6. Wynik Końcowy (Composite Score 0-100) ──────────────────────────────
    num_kills = len(detected_kills)
    
    if player_died:
        if num_kills <= 1:
            composite = 0.0
            tier = "REJECT"
            worthy = False
            highest_kill = f"NONE (DIED 0-1 KILLS)"
        elif num_kills == 2:
            composite = 25.0
            tier = "REJECT"
            worthy = False
            highest_kill = f"DOUBLE (2-FOR-1 TRADE - REJECT)"
        else: # 3+ kills and died = acceptable multi-kill clutch
            composite = round(35.0 + (kill_weight_score * 0.45), 1)
            tier = "B_TIER"
            worthy = True
            highest_kill = f"{highest_kill} (DIED BUT 3+ KILLS)"
    else:
        # Player survived!
        if num_kills == 0:
            composite = 25.0
            tier = "REJECT"
            worthy = False
        else:
            composite = (
                kill_weight_score * 0.35 +
                pacing_score      * 0.25 +
                clutch_score      * 0.20 +
                motion_vfx_score  * 0.20
            )
            composite = round(min(100.0, max(0.0, composite)), 1)
            if composite >= 85.0:
                tier = "S_TIER"
                worthy = True
            elif composite >= 70.0:
                tier = "A_TIER"
                worthy = True
            elif composite >= 50.0:
                tier = "B_TIER"
                worthy = True
            else:
                tier = "REJECT"
                worthy = False

        # ── 7. Przypisanie Tieru ───────────────────────────────────────────────────
        if composite >= 82.0 or highest_kill == "PENTAKILL":
            tier = "S_TIER"     # Gotowe do natychmiastowej publikacji
            worthy = True
        elif composite >= 68.0:
            tier = "A_TIER"     # Bardzo dobra akcja (Quadra / dynamiczny Triple)
            worthy = True
        elif composite >= 50.0:
            tier = "B_TIER"     # Średnia akcja (wymaga decyzji lub kolejkowania)
            worthy = False
        else:
            tier = "REJECT"     # Nudna akcja / stomp / brak fragów
            worthy = False

    result = {
        "video_path": video_path,
        "filename": os.path.basename(video_path),
        "score": composite,
        "tier": tier,
        "worthy": worthy,
        "highest_kill": highest_kill,
        "kills_count": len(detected_kills),
        "kills": detected_kills,
        "pacing_delta_s": round(pacing_delta, 1),
        "is_clutch": is_clutch,
        "lowest_hp_ratio": round(lowest_hp_ratio, 2),
        "sub_scores": {
            "kill_weight": round(kill_weight_score, 1),
            "pacing": round(pacing_score, 1),
            "clutch": round(clutch_score, 1),
            "motion_vfx": round(motion_vfx_score, 1),
        }
    }
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test Evaluatora Akcji")
    parser.add_argument("file", type=str, help="Ścieżka do klipu MP4")
    args = parser.parse_args()
    
    print(f"\nEvaluating: {args.file}...")
    res = evaluate_clip_quality(args.file)
    print("\n" + "="*50)
    print(f"📊 WYNIK OCENY: {res.get('score', 0)}/100 | TIER: {res.get('tier', '?')}")
    print(f"   🏆 Highest Kill: {res.get('highest_kill', '?')} ({res.get('kills_count', 0)} kills)")
    print(f"   ⚡ Pacing Delta: {res.get('pacing_delta_s', 0)}s | Clutch: {res.get('is_clutch', False)}")
    print(f"   🎯 Kwalifikacja do Shorta: {'TAK ✅' if res.get('worthy') else 'NIE ❌'}")
    print("="*50)
