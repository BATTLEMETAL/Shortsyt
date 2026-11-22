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
BEAT_CACHE_VERSION = 2


def _load_raw_cache() -> dict:
    if os.path.exists(BEAT_CACHE_PATH):
        try:
            with open(BEAT_CACHE_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and int(raw.get("_version", 0)) == BEAT_CACHE_VERSION:
                return raw
        except Exception:
            pass
    return {"_version": BEAT_CACHE_VERSION, "drops": {}, "_profiles": {}}


def _load_cache() -> dict:
    raw = _load_raw_cache()
    drops = raw.get("drops")
    return dict(drops) if isinstance(drops, dict) else {}


def _save_cache(cache: dict, profiles: dict = None):
    raw = _load_raw_cache()
    prof_out = dict(raw.get("_profiles") or {})
    if isinstance(profiles, dict):
        prof_out.update(profiles)
    payload = {"_version": BEAT_CACHE_VERSION, "drops": cache, "_profiles": prof_out}
    with open(BEAT_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def detect_beat_drop(music_path: str, manual_fallback: float = 0.0) -> float:
    """
    Wykrywa dokładny początek basowego dropu (STFT 35–160 Hz + kontrast RMS).

    Zastępuje stary argmax(onset_strength), który często trafiał w hi-hat w intro (np. 134s)
    albo pierwszy wokal (34s) zamiast właściwego wejścia basu.
    """
    if not LIBROSA_OK:
        return manual_fallback

    fname = os.path.basename(music_path)
    cache = _load_cache()

    if fname in cache:
        print(f"   Beat cache hit: {fname} → drop @ {cache[fname]:.2f}s")
        return float(cache[fname])

    print(f"   Detecting beat drop (sub-bass + RMS) in: {fname}...")
    try:
        y, sr = librosa.load(music_path, sr=22050, mono=True, duration=150.0)
        hop_length = 256
        hop_s = hop_length / sr
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop_length))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        bass_mask = (freqs >= 35.0) & (freqs <= 160.0)
        bass_e = np.sqrt(np.mean(S[bass_mask, :] ** 2, axis=0))
        full_e = librosa.feature.rms(S=S)[0]
        times = librosa.times_like(full_e, sr=sr, hop_length=hop_length)

        w_pre = max(4, int(3.5 / hop_s))
        w_post = max(4, int(3.5 / hop_s))
        start_idx = max(w_pre, int(14.0 / hop_s))
        end_idx = min(len(full_e) - w_post, int(88.0 / hop_s))
        if end_idx <= start_idx:
            return manual_fallback

        b_p60 = float(np.percentile(bass_e, 60))
        f_p55 = float(np.percentile(full_e, 55))
        best_i = -1
        best_sc = -1.0
        for i in range(start_idx, end_idx, 4):
            pre_b = float(np.mean(bass_e[i - w_pre : i]))
            post_b = float(np.mean(bass_e[i : i + w_post]))
            pre_f = float(np.mean(full_e[i - w_pre : i]))
            post_f = float(np.mean(full_e[i : i + w_post]))
            if post_b > b_p60 and post_f > f_p55:
                sc = max(0.0, post_b - pre_b) * (post_b / max(pre_b, 1e-4)) * (post_f / max(pre_f, 1e-4))
                if sc > best_sc:
                    best_sc = sc
                    best_i = i

        if best_i < 0:
            drop_time = manual_fallback
            print(f"   Drop region not found -> fallback {manual_fallback:.2f}s")
        else:
            # Doprecyzuj moment gwałtownego wejścia basu (zbocze narastające w oknie [-1.2s .. +1.0s])
            post_b_ref = float(np.mean(bass_e[best_i : best_i + w_post]))
            pre_local = float(np.mean(bass_e[max(0, best_i - int(1.5 / hop_s)) : best_i]))
            thresh = pre_local + 0.50 * max(1e-4, post_b_ref - pre_local)
            w_tiny = max(2, int(0.16 / hop_s))
            lo = max(w_tiny, best_i - int(1.2 / hop_s))
            hi = min(len(bass_e) - w_tiny, best_i + int(1.0 / hop_s))
            exact_i = best_i
            for j in range(lo, hi):
                if float(np.mean(bass_e[j : j + w_tiny])) >= thresh and float(np.mean(bass_e[j - w_tiny : j])) < thresh:
                    exact_i = j
                    break

            drop_time = float(times[exact_i])
            if not 14.0 <= drop_time <= 120.0:
                drop_time = manual_fallback
            else:
                # Przyciągnij lekko do najbliższego silnego onetu basu w +-0.25s dla dokładności klatkowej
                try:
                    bass_onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length, fmax=180.0, n_mels=32)
                    win = int(0.25 / hop_s)
                    s0, s1 = max(0, exact_i - win), min(len(bass_onset), exact_i + win + 1)
                    if s1 > s0:
                        snap_i = s0 + int(np.argmax(bass_onset[s0:s1]))
                        drop_time = float(times[snap_i])
                except Exception:
                    pass
                print(f"   Beat drop detected @ {drop_time:.2f}s")

        if drop_time > 0.0:
            cache[fname] = round(drop_time, 2)
            _save_cache(cache)
        return round(float(drop_time), 2)

    except Exception as e:
        print(f"   Beat detection error: {e} -> fallback {manual_fallback:.2f}s")
        return manual_fallback


def get_drop_time(music_path: str, manual_map: dict = None) -> float:
    """
    Main entry point: returns drop time using librosa if available,
    falls back to manual_map, then to 30.0s default.
    """
    fname = os.path.basename(music_path)

    known = float((manual_map or {}).get(fname, 0.0) or 0.0)

    # librosa first; when it fails or lands out of range, the map's value for THIS track is the fallback
    if LIBROSA_OK:
        return detect_beat_drop(music_path, manual_fallback=known)

    # No librosa: the manual map, else 0.0 = "no drop known" (the editor then plays the track from its start).
    # Before 11 Nov 2026 this returned 30.0 for any unknown track: a made-up drop that put the music off the hit.
    return known


def get_track_beat_profile(music_path: str, manual_map: dict = None) -> dict:
    """
    Zwraca pełny profil rytmiczny utworu (Beat-Sync v3):
      - `drop_time`: dokładny moment wejścia głównego sub-basu (STFT 35-160 Hz)
      - `bpm`: estymowane tempo utworu
      - `beat_interval`: odstęp jednego bitu w sekundach (60 / bpm)
      - `beat_times`: lista precyzyjnych uderzeń bitu przez pierwsze 25s od dropu
    """
    fname = os.path.basename(music_path)
    drop_time = get_drop_time(music_path, manual_map=manual_map)

    raw = _load_raw_cache()
    cached_profiles = raw.get("_profiles") or {}
    if fname in cached_profiles and isinstance(cached_profiles[fname], dict):
        prof = dict(cached_profiles[fname])
        if prof.get("drop_time") is not None and prof.get("beat_times"):
            return prof

    bpm = 128.0
    beat_times = []
    if LIBROSA_OK and os.path.exists(music_path):
        try:
            offset_s = max(0.0, float(drop_time) - 2.0)
            y, sr = librosa.load(music_path, sr=22050, mono=True, offset=offset_s, duration=28.0)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env, hop_length=256)
            tempo_val = float(np.atleast_1d(tempo)[0]) if hasattr(tempo, "__len__") else float(tempo)
            if 70.0 <= tempo_val <= 200.0:
                bpm = round(tempo_val, 1)
            raw_times = [round(offset_s + float(t), 3) for t in librosa.frames_to_time(beats, sr=sr, hop_length=256)]
            beat_times = [t for t in raw_times if (drop_time - 0.15) <= t <= (drop_time + 25.0)]
        except Exception:
            beat_times = []

    beat_interval = round(60.0 / max(60.0, bpm), 3)
    if not beat_times:
        start_b = float(drop_time)
        beat_times = [round(start_b + i * beat_interval, 3) for i in range(40) if i * beat_interval <= 25.0]

    profile = {
        "drop_time": round(float(drop_time), 2),
        "bpm": bpm,
        "beat_interval": beat_interval,
        "beat_times": beat_times,
    }
    try:
        drops_cache = _load_cache()
        if fname not in drops_cache and drop_time > 0.0:
            drops_cache[fname] = round(float(drop_time), 2)
        _save_cache(drops_cache, profiles={fname: profile})
    except Exception:
        pass
    return profile


# ─── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import glob
    music_dir = os.path.join(os.path.dirname(__file__), "lol_music")
    files = glob.glob(os.path.join(music_dir, "*.mp3"))
    print(f"\nAnalyzing {len(files)} music files...\n")
    for f in files:
        drop = detect_beat_drop(f)
        print(f"  {os.path.basename(f):<50} drop @ {drop:.1f}s")
