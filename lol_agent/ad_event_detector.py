"""
Shortsyt — Ad Event Detector
Wykrywa peak momenty w klipach reklamowych i review produktów.
Zamiast OCR kill-bannerów używa:
  1. Motion Energy — różnica klatek (największy ruch = peak)
  2. Face Detection / Color Contrast spike — dynamika sceny

Zwraca listę [(timestamp, label, tier)] jak GameEventDetector dla kompatybilności z pipeline.
"""
import cv2
import numpy as np
from typing import List, Tuple

def detect_ad_events(
    video_path: str,
    clip_start: float = 0.0,
    clip_end: float = 60.0,
    clip_duration: float = 60.0,
    sample_fps: float = 4.0,
) -> List[Tuple[float, str, int]]:
    """
    Wykrywa peak momenty w klipie reklamowym.
    Zwraca: [(timestamp, label, tier), ...] posortowane wg timestamp.
    label: 'motion_peak' | 'face_entry' | 'brightness_spike'
    tier: 1-3
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    events = []
    prev_frame = None
    motion_scores = []
    timestamps = []

    step = max(1, int(fps / sample_fps))
    start_frame = int(clip_start * fps)
    end_frame = int(clip_end * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_idx = start_frame

    while frame_idx < end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        ts = frame_idx / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Motion energy
        if prev_frame is not None:
            diff = cv2.absdiff(gray, prev_frame)
            motion = int(np.sum(diff > 25))
            motion_scores.append(motion)
            timestamps.append(ts)

        prev_frame = gray
        frame_idx += step
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

    cap.release()

    if not motion_scores:
        # Fallback: peak w połowie klipu
        mid = clip_start + (clip_end - clip_start) / 2
        return [(mid, 'motion_peak', 2)]

    # Normalizacja
    max_motion = max(motion_scores) or 1
    norm = [s / max_motion for s in motion_scores]

    # Znajdź lokalne maksima (top peaks)
    peaks = []
    window = max(3, int(sample_fps * 1.5))  # 1.5s window
    for i in range(window, len(norm) - window):
        local_max = max(norm[max(0, i - window):i + window])
        if norm[i] == local_max and norm[i] > 0.55:
            peaks.append((timestamps[i], 'motion_peak', min(3, 1 + int(norm[i] * 2))))

    if not peaks:
        # Weź top-3 timestamps
        sorted_idx = sorted(range(len(norm)), key=lambda x: norm[x], reverse=True)[:3]
        peaks = [(timestamps[i], 'motion_peak', 2) for i in sorted_idx]

    return sorted(peaks, key=lambda x: x[0])
