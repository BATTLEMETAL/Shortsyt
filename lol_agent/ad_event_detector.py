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
from pathlib import Path
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
    prev_frame = None
    prev_luma = None
    motion_scores = []
    luma_deltas = []
    timestamps = []
    face_events: List[Tuple[float, str, int]] = []
    last_face_ts = -999.0

    face_cascade = None
    try:
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        clf = cv2.CascadeClassifier(cascade_path)
        if not clf.empty():
            face_cascade = clf
    except Exception:
        face_cascade = None

    step = max(1, int(fps / sample_fps))
    start_frame = max(0, int(clip_start * fps))
    end_frame = max(start_frame + 1, int(clip_end * fps))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_idx = start_frame

    while frame_idx < end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        ts = frame_idx / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_luma = float(np.mean(gray))

        if prev_luma is not None:
            luma_deltas.append(abs(mean_luma - prev_luma))
        prev_luma = mean_luma

        if face_cascade is not None and (ts - last_face_ts) >= 2.0:
            try:
                small_gray = cv2.resize(gray, (320, max(180, int(320 * gray.shape[0] / max(1, gray.shape[1])))))
                faces = face_cascade.detectMultiScale(small_gray, scaleFactor=1.15, minNeighbors=4, minSize=(28, 28))
                if len(faces) > 0:
                    face_events.append((ts, "face_entry", 2))
                    last_face_ts = ts
            except Exception:
                pass

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
        mid = clip_start + (clip_end - clip_start) / 2
        return [(mid, "motion_peak", 2)]

    # Brightness / scene reveal spikes
    brightness_events: List[Tuple[float, str, int]] = []
    if len(luma_deltas) == len(motion_scores):
        last_bright_ts = -999.0
        for idx_b, ld in enumerate(luma_deltas):
            if ld >= 28.0 and (timestamps[idx_b] - last_bright_ts) >= 0.8:
                brightness_events.append((timestamps[idx_b], "brightness_spike", 3 if ld >= 48.0 else 2))
                last_bright_ts = timestamps[idx_b]

    # Normalizacja ruchu
    max_motion = max(motion_scores) or 1
    norm = [s / max_motion for s in motion_scores]

    peaks = []
    window = max(3, int(sample_fps * 1.5))  # 1.5s window
    for i in range(window, max(window, len(norm) - window)):
        local_max = max(norm[max(0, i - window):i + window])
        if norm[i] == local_max and norm[i] > 0.55:
            peaks.append((timestamps[i], "motion_peak", min(3, 1 + int(norm[i] * 2))))

    if not peaks and not brightness_events and not face_events:
        sorted_idx = sorted(range(len(norm)), key=lambda x: norm[x], reverse=True)[:3]
        peaks = [(timestamps[i], "motion_peak", 2) for i in sorted_idx]

    combined = sorted(peaks + brightness_events + face_events, key=lambda x: x[0])
    return combined or [(clip_start + (clip_end - clip_start) / 2, "motion_peak", 2)]
