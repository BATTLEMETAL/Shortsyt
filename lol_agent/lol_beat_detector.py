"""
LOL Agent — Beat Drop Detector
Uses librosa to auto-detect the beat drop timestamp in any music file.
Replaces the manual MUSIC_DROP_MAP in lol_editor.py.

Install: pip install librosa soundfile
"""
import os
import json
import sys

# Windows cp1250 fix
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import librosa
    import numpy as np
    LIBROSA_OK = True
except ImportError:
    LIBROSA_OK = False
    print("  librosa not installed — using manual drop map (pip install librosa)")

# Cache file — stores detected drops so we only analyze once per file
BEAT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "beat_drop_cache.json")


def _load_cache() -> dict:
    if os.path.exists(BEAT_CACHE_PATH):
        try:
            with open(BEAT_CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict):
    with open(BEAT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def detect_beat_drop(music_path: str, manual_fallback: float = 30.0) -> float:
    """
    Detect the timestamp (seconds) of the beat drop in a music file.

    Strategy:
    1. Load audio with librosa
    2. Compute onset envelope (energy over time)
    3. Find the single largest energy spike after the 10s mark
       (drops rarely happen in the first 10s of a track)
    4. Cache result to avoid re-analyzing the same file

    Returns: float — timestamp in seconds of the beat drop
    """
    if not LIBROSA_OK:
        return manual_fallback

    fname = os.path.basename(music_path)
    cache = _load_cache()

    if fname in cache:
        print(f"   Beat cache hit: {fname} → drop @ {cache[fname]:.1f}s")
        return cache[fname]

    print(f"   Detecting beat drop in: {fname}...")
    try:
        # Load at reduced sample rate for speed (mono, 22050Hz), up to 180s
        y, sr = librosa.load(music_path, sr=22050, mono=True, duration=180.0)

        # Onset strength envelope — measures energy change over time
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        times = librosa.times_like(onset_env, sr=sr)

        # Look for drops only after 15s (skip intros and sound effects)
        start_idx = int(15.0 * sr / 512)
        onset_trimmed = onset_env[start_idx:]
        times_trimmed = times[start_idx:]

        # Smooth with a rolling window to find sustained energy peaks (not single beats)
        window = 30  # ~0.35s window
        smoothed = np.convolve(onset_trimmed, np.ones(window) / window, mode='same')

        # Find the global maximum of the smoothed curve -> that's the drop
        peak_idx = int(np.argmax(smoothed))
        drop_time = float(times_trimmed[peak_idx])

        # Sanity check: drop should be between 15s and 150s
        # (NCS tracks with long intros can drop at 90-120s)
        if not 15.0 <= drop_time <= 150.0:
            drop_time = manual_fallback
            print(f"   Drop out of range -> using fallback {manual_fallback:.1f}s")
        else:
            print(f"   Beat drop detected @ {drop_time:.1f}s")

        cache[fname] = round(drop_time, 2)
        _save_cache(cache)
        return drop_time

    except Exception as e:
        print(f"   Beat detection error: {e} -> fallback {manual_fallback:.1f}s")
        return manual_fallback


def get_drop_time(music_path: str, manual_map: dict = None) -> float:
    """
    Main entry point: returns drop time using librosa if available,
    falls back to manual_map, then to 30.0s default.
    """
    fname = os.path.basename(music_path)

    # Try librosa first
    if LIBROSA_OK:
        return detect_beat_drop(music_path)

    # Fall back to manual map
    if manual_map and fname in manual_map:
        return manual_map[fname]

    return 30.0  # last resort default


# ─── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import glob
    music_dir = os.path.join(os.path.dirname(__file__), "lol_music")
    files = glob.glob(os.path.join(music_dir, "*.mp3"))
    print(f"\nAnalyzing {len(files)} music files...\n")
    for f in files:
        drop = detect_beat_drop(f)
        print(f"  {os.path.basename(f):<50} drop @ {drop:.1f}s")
