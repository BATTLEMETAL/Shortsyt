"""
LOL Agent — Minimap Zone Detector
==================================
Wykrywa pozycję gracza na minimapie w klatce peak_moment i zwraca strefę mapy.
Używany przez pipeline do generowania tytułów adekwatnych do miejsca akcji.

Metoda: ffmpeg wyciąga 1 klatkę → cv2 wykrywa ikonę gracza (HSV) → lookup table → zone name

Wyjście przykładowe:
    {
        "zone": "mid_lane",
        "zone_label": "Mid Lane",
        "confidence": 0.82,
        "nx": 0.51, "ny": 0.49,
        "method": "color_hsv"
    }
"""
import os
import subprocess
import tempfile
from typing import Optional

# ─── Strefa mapy → czytelna etykieta ─────────────────────────────────────────
ZONE_LABELS = {
    "blue_base":    "Base",
    "red_base":     "Base",
    "top_lane":     "Top Lane",
    "mid_lane":     "Mid Lane",
    "bot_lane":     "Bot Lane",
    "top_jungle":   "Top Jungle",
    "bot_jungle":   "Bot Jungle",
    "baron_pit":    "Baron Pit",
    "dragon_pit":   "Dragon Pit",
    "top_river":    "River",
    "bot_river":    "River",
    "unknown":      "",
}

# ─── Lookup table: (nx_min, nx_max, ny_min, ny_max) → zone ───────────────────
# nx=0 = lewa krawędź minimapki (Blue Base), nx=1 = prawa (Red Base)
# ny=0 = górna krawędź (Top), ny=1 = dolna (Bot)
# Kolejność ma znaczenie — bardziej szczegółowe strefy najpierw
ZONE_MAP = [
    # Bazy
    (0.00, 0.18, 0.82, 1.00, "blue_base"),
    (0.82, 1.00, 0.00, 0.18, "red_base"),

    # Obiekty
    (0.22, 0.38, 0.22, 0.40, "baron_pit"),
    (0.60, 0.78, 0.60, 0.78, "dragon_pit"),

    # River (wąski pas ukośny)
    (0.22, 0.45, 0.40, 0.60, "bot_river"),
    (0.45, 0.68, 0.20, 0.45, "top_river"),

    # Lanes
    (0.00, 0.30, 0.00, 0.30, "top_lane"),
    (0.35, 0.65, 0.33, 0.67, "mid_lane"),
    (0.70, 1.00, 0.70, 1.00, "bot_lane"),

    # Jungle
    (0.15, 0.45, 0.45, 0.75, "bot_jungle"),
    (0.55, 0.85, 0.15, 0.45, "top_jungle"),
]

# ─── HSV zakresy kolorów ikony gracza ────────────────────────────────────────
# Niebieski team (blue side): jasnoniebieski z białym centre
# Czerwony team (red side): czerwony/pomarańczowy
PLAYER_HSV = [
    # (H_lo, H_hi, S_lo, S_hi, V_lo, V_hi, name)
    (95,  130, 80,  255, 160, 255, "blue_team"),    # niebieski (blue side)
    (0,   10,  120, 255, 180, 255, "red_team_lo"),  # czerwony (red side) dolny zakres H
    (165, 180, 120, 255, 180, 255, "red_team_hi"),  # czerwony (red side) górny zakres H
    (0,   180, 0,   50,  220, 255, "white_bright"), # biały highlight (oba teamy)
]

# Minimapa: prawym dolnym rogu 1920×1080
# Koordynaty sprawdzone na screenach LoL 1920×1080
MINIMAP_1080 = {
    "x1": 1596, "y1": 800,
    "x2": 1910, "y2": 1075,
}


def _auto_scale_minimap(frame_w: int, frame_h: int) -> dict:
    """Skaluje koordynaty minimapki do aktualnej rozdzielczości wideo."""
    scale_x = frame_w / 1920.0
    scale_y = frame_h / 1080.0
    return {
        "x1": int(MINIMAP_1080["x1"] * scale_x),
        "y1": int(MINIMAP_1080["y1"] * scale_y),
        "x2": int(MINIMAP_1080["x2"] * scale_x),
        "y2": int(MINIMAP_1080["y2"] * scale_y),
    }


def _get_video_size(video_path: str):
    """Zwraca (width, height) wideo przez ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        parts = r.stdout.decode().strip().split("x")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1920, 1080  # fallback


def _extract_frame(video_path: str, timestamp: float, out_path: str) -> bool:
    """Wyciąga pojedynczą klatkę z wideo przy zadanym timestampie."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{max(0.0, timestamp):.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        out_path
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        return r.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


def _detect_player_position(minimap_bgr) -> Optional[tuple]:
    """
    Wykrywa ikonę gracza na minimapie przez detekcję koloru HSV.
    Zwraca (nx, ny, confidence) lub None.
    nx, ny ∈ [0,1]: znormalizowane koordynaty w minimapie.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    h, w = minimap_bgr.shape[:2]
    hsv = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2HSV)

    best_px, best_py, best_area, best_name = None, None, 0, ""

    for (h_lo, h_hi, s_lo, s_hi, v_lo, v_hi, name) in PLAYER_HSV:
        lo = np.array([h_lo, s_lo, v_lo], dtype=np.uint8)
        hi = np.array([h_hi, s_hi, v_hi], dtype=np.uint8)
        mask = cv2.inRange(hsv, lo, hi)

        # Szukaj centroidu największego bloba
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Ikona gracza: 30–800 px² (za małe = szum, za duże = HUD element)
            if 30 <= area <= 800 and area > best_area:
                M = cv2.moments(cnt)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    best_px, best_py, best_area, best_name = cx, cy, area, name

    if best_px is None:
        return None

    nx = best_px / w
    ny = best_py / h

    # Confidence: zależy od rozmiaru bloba (im bliżej 150px², tym lepiej) i od jasności
    area_conf = min(1.0, best_area / 150.0) if best_area <= 150 else max(0.3, 1.0 - (best_area - 150) / 650.0)
    # Penalty za "biały" — może być szum HUD
    name_conf = 0.7 if best_name == "white_bright" else 0.9

    confidence = round(area_conf * name_conf, 2)
    return (nx, ny, confidence)


def _coords_to_zone(nx: float, ny: float) -> str:
    """Mapuje znormalizowane koordynaty (0-1, 0-1) na nazwę strefy LoL."""
    for (x1, x2, y1, y2, zone) in ZONE_MAP:
        if x1 <= nx <= x2 and y1 <= ny <= y2:
            return zone
    return "unknown"


def detect_map_zone(
    video_path: str,
    peak_time: float,
    clip_start: float = 0.0,
) -> dict:
    """
    Główna funkcja — wykrywa strefę mapy LoL w momencie akcji.

    Args:
        video_path:  Ścieżka do pliku MP4 nagrania.
        peak_time:   Czas peak momentu w sekundach (ABSOLUTNY w oryg. wideo).
        clip_start:  Czas początku klipu (dla debugowania, nieużywany w detekcji).

    Returns:
        dict z kluczami: zone, zone_label, confidence, nx, ny, method
        Gdy detekcja się nie powiodła: zone="unknown", confidence=0.0
    """
    _default = {
        "zone": "unknown",
        "zone_label": "",
        "confidence": 0.0,
        "nx": -1.0,
        "ny": -1.0,
        "method": "failed",
    }

    if not video_path or not os.path.exists(video_path):
        print(f"[Minimap] Brak pliku: {video_path}")
        return _default

    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[Minimap] cv2/numpy niedostępne — pomijam detekcję")
        return _default

    # 1. Wyciągnij klatkę przy peak_time
    with tempfile.TemporaryDirectory() as tmpdir:
        frame_path = os.path.join(tmpdir, "minimap_frame.jpg")

        if not _extract_frame(video_path, peak_time, frame_path):
            print(f"[Minimap] Nie udało się wyciągnąć klatki @ {peak_time:.2f}s")
            return _default

        # 2. Wczytaj klatkę i pobierz rozdzielczość
        frame = cv2.imread(frame_path)
        if frame is None:
            print("[Minimap] Nie można odczytać klatki")
            return _default

        fh, fw = frame.shape[:2]
        coords = _auto_scale_minimap(fw, fh)

        # 3. Crop minimapki
        minimap = frame[coords["y1"]:coords["y2"], coords["x1"]:coords["x2"]]
        if minimap.size == 0:
            print(f"[Minimap] Pusty crop minimapki ({coords})")
            return _default

        # 4. Wykryj pozycję gracza
        result = _detect_player_position(minimap)
        if result is None:
            print(f"[Minimap] Nie wykryto ikony gracza na minimapie ({fw}×{fh})")
            return _default

        nx, ny, confidence = result

        # 5. Mapuj na strefę
        zone = _coords_to_zone(nx, ny)
        zone_label = ZONE_LABELS.get(zone, "")

        print(f"[Minimap] Wykryto: {zone} ({zone_label}) @ ({nx:.2f}, {ny:.2f}) conf={confidence:.0%} | frame={fw}×{fh} | t={peak_time:.1f}s")

        return {
            "zone": zone,
            "zone_label": zone_label,
            "confidence": confidence,
            "nx": round(nx, 3),
            "ny": round(ny, 3),
            "method": "color_hsv",
        }

    return _default


def visualize_detection(video_path: str, peak_time: float, out_img: str = "minimap_debug.jpg"):
    """
    DEBUG: Zapisuje klatkę z zaznaczoną minimapą i wykrytą pozycją gracza.
    Użycie: python lol_minimap_analyzer.py <clip.mp4> <peak_time>
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("cv2 niedostępne")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_path = os.path.join(tmpdir, "frame.jpg")
        if not _extract_frame(video_path, peak_time, frame_path):
            print("Nie wyciągnięto klatki")
            return

        frame = cv2.imread(frame_path)
        if frame is None:
            return

        fh, fw = frame.shape[:2]
        coords = _auto_scale_minimap(fw, fh)

        # Zaznacz obszar minimapki
        cv2.rectangle(frame,
                      (coords["x1"], coords["y1"]),
                      (coords["x2"], coords["y2"]),
                      (0, 255, 0), 2)

        minimap = frame[coords["y1"]:coords["y2"], coords["x1"]:coords["x2"]]
        result = _detect_player_position(minimap)

        if result:
            nx, ny, conf = result
            mw = coords["x2"] - coords["x1"]
            mh = coords["y2"] - coords["y1"]
            px = coords["x1"] + int(nx * mw)
            py = coords["y1"] + int(ny * mh)
            cv2.circle(frame, (px, py), 12, (0, 0, 255), 3)
            zone = _coords_to_zone(nx, ny)
            cv2.putText(frame, f"{zone} ({conf:.0%})", (px - 60, py - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imwrite(out_img, frame)
        print(f"[Minimap Debug] Zapisano: {out_img}")
        # Otwórz w domyślnej przeglądarce
        os.startfile(out_img)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        vpath = sys.argv[1]
        ptime = float(sys.argv[2])
        out = sys.argv[3] if len(sys.argv) >= 4 else "minimap_debug.jpg"
        visualize_detection(vpath, ptime, out)
    else:
        print("Usage: python lol_minimap_analyzer.py <video.mp4> <peak_time_sec> [out_debug.jpg]")
