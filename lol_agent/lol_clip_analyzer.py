"""
LOL Agent — Analiza klipu i wykrywanie najlepszej akcji
Używa OpenCV do analizy ruchu i detekcji peak moments
"""
import os
import glob
import cv2
import numpy as np
from typing import Optional, Tuple, List
from lol_config import (
    LOL_INPUT_DIR, LOL_ARCHIVE_DIR, SUPPORTED_FORMATS,
    SHORT_MAX_DURATION
)
import shutil


def scan_input_folder() -> Optional[str]:
    """Skanuje folder input, zwraca najnowszy klip."""
    print(f"📂 Skanowanie folderu: {LOL_INPUT_DIR}")

    if not os.path.exists(LOL_INPUT_DIR):
        os.makedirs(LOL_INPUT_DIR, exist_ok=True)
        print(f"📁 Utworzono folder input: {LOL_INPUT_DIR}")

    video_files = []
    for fmt in SUPPORTED_FORMATS:
        video_files.extend(glob.glob(os.path.join(LOL_INPUT_DIR, fmt)))

    if not video_files:
        print("✅ Brak nowych klipów do przetworzenia.")
        return None

    latest = max(video_files, key=os.path.getmtime)
    print(f"🎮 Znaleziono klip: {os.path.basename(latest)}")
    return latest


def analyze_motion(video_path: str, sample_rate: int = 5) -> List[Tuple[float, float]]:
    """
    Analizuje intensywność ruchu w każdej klatce.
    Zwraca listę (timestamp_sekundy, motion_score).
    """
    print(f"🔍 Analizuję ruch w klipie: {os.path.basename(video_path)}")
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Nie można otworzyć pliku: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    print(f"   📊 FPS: {fps:.1f} | Klatki: {total_frames} | Czas: {duration:.1f}s")

    motion_scores = []
    prev_gray = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_rate == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                score = float(np.mean(diff))
                timestamp = frame_idx / fps
                motion_scores.append((timestamp, score))

            prev_gray = gray

        frame_idx += 1

    cap.release()
    print(f"   ✅ Przeanalizowano {len(motion_scores)} próbek ruchu")
    return motion_scores


def find_peak_action(
    motion_scores: List[Tuple[float, float]],
    video_duration: float,
    target_duration: float = SHORT_MAX_DURATION,
    smoothing_window: int = 10
) -> Tuple[float, float]:
    """
    Znajduje okno czasowe z najbardziej intensywną akcją.
    Zwraca (start_sekunda, end_sekunda).
    """
    if not motion_scores:
        # Fallback: środek nagrania
        mid = video_duration / 2
        start = max(0, mid - target_duration / 2)
        end = min(video_duration, start + target_duration)
        return start, end

    timestamps = np.array([s[0] for s in motion_scores])
    scores = np.array([s[1] for s in motion_scores])

    # Wygładzanie — rolling average
    if len(scores) > smoothing_window:
        kernel = np.ones(smoothing_window) / smoothing_window
        scores_smooth = np.convolve(scores, kernel, mode='same')
    else:
        scores_smooth = scores

    # Oblicz skumulowany score dla okna o długości target_duration
    step = timestamps[1] - timestamps[0] if len(timestamps) > 1 else 1.0
    window_frames = int(target_duration / step)
    window_frames = max(1, min(window_frames, len(scores_smooth)))

    # Przesuń okno i znajdź max sumę
    best_start_idx = 0
    best_score = -1

    for i in range(len(scores_smooth) - window_frames + 1):
        window_score = np.sum(scores_smooth[i:i + window_frames])
        if window_score > best_score:
            best_score = window_score
            best_start_idx = i

    start_time = timestamps[best_start_idx]
    end_time = min(start_time + target_duration, video_duration)

    # Upewnij się że okno ma target_duration
    if end_time - start_time < target_duration:
        start_time = max(0, end_time - target_duration)

    print(f"   🎯 Peak akcja: {start_time:.1f}s → {end_time:.1f}s ({end_time - start_time:.1f}s)")
    return start_time, end_time


def detect_action_type(motion_scores: List[Tuple[float, float]], peak_start: float, peak_end: float) -> str:
    """
    Heurystycznie wykrywa typ akcji na podstawie intensywności.
    """
    if not motion_scores:
        return "outplay"

    peak_scores = [s for t, s in motion_scores if peak_start <= t <= peak_end]
    if not peak_scores:
        return "outplay"

    max_score = max(peak_scores)
    avg_score = np.mean(peak_scores)
    spikes = sum(1 for s in peak_scores if s > avg_score * 1.5)

    # Klasyfikacja na podstawie intensywności
    if max_score > 60 and spikes >= 5:
        return "pentakill"
    elif max_score > 50 and spikes >= 4:
        return "quadrakill"
    elif max_score > 40 and spikes >= 3:
        return "triple"
    elif max_score > 35 and spikes >= 2:
        return "double"
    elif max_score > 45:
        return "oneshot"
    elif spikes >= 3:
        return "clutch"
    else:
        return "outplay"


def get_video_duration(video_path: str) -> float:
    """Zwraca długość wideo w sekundach."""
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return frames / fps if fps > 0 else 0


def archive_clip(source_path: str) -> str:
    """Przenosi klip do archiwum po przetworzeniu."""
    os.makedirs(LOL_ARCHIVE_DIR, exist_ok=True)
    dest = os.path.join(LOL_ARCHIVE_DIR, os.path.basename(source_path))
    shutil.move(source_path, dest)
    print(f"📦 Zarchiwizowano: {os.path.basename(dest)}")
    return dest


def analyze_clip(video_path: str) -> dict:
    """
    Główna funkcja analizy klipu.
    Zwraca słownik z wynikami analizy.
    """
    print(f"\n{'='*50}")
    print(f"🎮 LOL CLIP ANALYZER")
    print(f"{'='*50}")

    duration = get_video_duration(video_path)
    print(f"⏱️  Długość klipu: {duration:.1f}s")

    # Jeśli klip jest krótszy niż max short duration — bierzemy całość
    if duration <= SHORT_MAX_DURATION:
        print(f"✅ Klip już jest krótki ({duration:.1f}s) — używam całości")
        peak_start, peak_end = 0.0, duration
        motion_scores = []
        action_type = "outplay"
    else:
        motion_scores = analyze_motion(video_path)
        peak_start, peak_end = find_peak_action(motion_scores, duration)
        action_type = detect_action_type(motion_scores, peak_start, peak_end)

    result = {
        "video_path": video_path,
        "duration": duration,
        "peak_start": peak_start,
        "peak_end": peak_end,
        "action_type": action_type,
        "clip_duration": peak_end - peak_start,
    }

    print(f"\n📋 WYNIK ANALIZY:")
    print(f"   🎯 Typ akcji:   {action_type.upper()}")
    print(f"   ⏱️  Okno akcji: {peak_start:.1f}s → {peak_end:.1f}s")
    print(f"   📐 Długość:     {peak_end - peak_start:.1f}s")

    return result


if __name__ == "__main__":
    # Test na pliku z katalogu głównego projektu
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else r"c:\Users\mz100\PycharmProjects\shortsyt\League of Legends_10-01-2025_3-26-40-0.mp4"

    if os.path.exists(test_file):
        result = analyze_clip(test_file)
        print(f"\n✅ Analiza zakończona!")
    else:
        print(f"❌ Nie znaleziono pliku: {test_file}")
        # Spróbuj skanować folder input
        clip = scan_input_folder()
        if clip:
            result = analyze_clip(clip)
