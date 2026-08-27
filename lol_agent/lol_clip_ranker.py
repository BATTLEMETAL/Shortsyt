"""
LOL Agent — Clip Ranker
Scans all clips in the input folder, scores each one, and returns
a ranked list so the pipeline processes the best clips first.

Scoring formula (0-100):
  kill_score      (40%) — kill count × type weight (penta=10, quadra=7, triple=4)
  intensity_score (30%) — average momentum / VFX score in the clip
  resolution_score(15%) — is source >= 1080p?
  duration_score  (15%) — how close is clip length to optimal Short duration (20-30s)

Uses PySceneDetect for scene density analysis to find action-rich segments.
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import glob
import json
import subprocess
import re
from datetime import datetime
from typing import Optional

try:
    from scenedetect import open_video, SceneManager, ContentDetector
    SCENEDETECT_OK = True
except ImportError:
    SCENEDETECT_OK = False
    print("  PySceneDetect not available — scene scoring disabled (pip install scenedetect)")

from lol_config import LOL_INPUT_DIR, SUPPORTED_FORMATS, SHORT_MAX_DURATION

# Kill type weights for scoring
KILL_WEIGHTS = {
    "PENTAKILL": 10,
    "QUADRAKILL": 7,
    "TRIPLE KILL": 4,
    "DOUBLE KILL": 2,
    "KILL": 1,
}

# Optimal Short duration range (seconds)
OPTIMAL_MIN = 18.0
OPTIMAL_MAX = 30.0

# Minimum score to be considered for upload (0-100)
# Note: without pytesseract+PySceneDetect, max reachable score = ~30
# (resolution 15% + duration 15%). Keep below 30 until deps installed.
RANKABLE_THRESHOLD = 20

RANK_CACHE_PATH = os.path.join(os.path.dirname(__file__), "clip_rank_cache.json")


# ─── Video metadata via FFprobe ────────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    """Returns duration, width, height, fps via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)

        info = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0}
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                info["width"] = stream.get("width", 0)
                info["height"] = stream.get("height", 0)
                fps_str = stream.get("r_frame_rate", "0/1")
                try:
                    num, den = fps_str.split("/")
                    info["fps"] = round(float(num) / float(den), 2)
                except Exception:
                    pass
        info["duration"] = float(data.get("format", {}).get("duration", 0))
        return info
    except Exception as e:
        print(f"  ffprobe error: {e}")
        return {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0}


# ─── OCR kill detection (fast, frame-sampled) ──────────────────────────────────

def fast_kill_scan(video_path: str, sample_every_n_seconds: float = 0.5) -> list:
    """
    Quick OCR scan — samples frames every N seconds, looks for kill text.
    Returns list of (timestamp, kill_type) tuples.
    Faster than full momentum analysis — used for initial ranking only.
    """
    try:
        import cv2
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
        return []

    KILL_PATTERNS = {
        "PENTAKILL":   re.compile(r"PENTA", re.IGNORECASE),
        "QUADRAKILL":  re.compile(r"QUADRA", re.IGNORECASE),
        "TRIPLE KILL": re.compile(r"TRIPLE", re.IGNORECASE),
        "DOUBLE KILL": re.compile(r"DOUBLE", re.IGNORECASE),
        "SHUTDOWN":    re.compile(r"SHUT", re.IGNORECASE),
        "FIRST BLOOD": re.compile(r"FIRST\s*BLOOD", re.IGNORECASE),
        "KILL":        re.compile(r"(\+([1-9]\d{2,3})|slain|dwannellenga)", re.IGNORECASE),
    }

    kills = []
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_step = max(1, int(fps * sample_every_n_seconds))

        for frame_idx in range(0, total_frames, sample_step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            # Center announcement banner region
            crop = frame[int(h * 0.12):int(h * 0.36), int(w * 0.20):int(w * 0.80)]

            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY)
            thresh_big = cv2.resize(thresh, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            text = pytesseract.image_to_string(thresh_big, config="--psm 6")

            ts = frame_idx / fps
            for kill_type, pattern in KILL_PATTERNS.items():
                if pattern.search(text):
                    # Avoid duplicates within 1.2s window
                    if not kills or (ts - kills[-1][0]) > 1.2:
                        kills.append((ts, kill_type))
                    break

        cap.release()
    except Exception as e:
        print(f"  fast_kill_scan error: {e}")

    return kills



# ─── Scene density via PySceneDetect ──────────────────────────────────────────

def get_scene_density(video_path: str) -> float:
    """
    Uses PySceneDetect ContentDetector to count scene changes per minute.
    High scene density = high action = better clip.
    Returns scenes_per_minute (float).
    """
    if not SCENEDETECT_OK:
        return 0.0

    try:
        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(video, show_progress=False)
        scenes = scene_manager.get_scene_list()
        duration = video.duration.get_seconds()
        if duration > 0:
            return round(len(scenes) / (duration / 60.0), 2)
        return 0.0
    except Exception as e:
        print(f"  SceneDetect error: {e}")
        return 0.0


# ─── Scoring ───────────────────────────────────────────────────────────────────

def score_clip(video_path: str, verbose: bool = True) -> dict:
    """
    Score a single clip. Returns a dict with all metrics and composite score.
    """
    fname = os.path.basename(video_path)
    if verbose:
        print(f"\n  Scoring: {fname}")

    info = get_video_info(video_path)
    duration = info.get("duration", 0.0)
    width = info.get("width", 0)
    height = info.get("height", 0)

    # Try smart autonomous clutch evaluator first
    try:
        from autonomous.evaluator import evaluate_clip_quality
        eval_res = evaluate_clip_quality(video_path)
        if "score" in eval_res and "error" not in eval_res:
            result = {
                "path": video_path,
                "filename": fname,
                "score": eval_res["score"],
                "tier": eval_res.get("tier", "REJECT"),
                "kill_score": eval_res.get("sub_scores", {}).get("kill_weight", 0),
                "intensity_score": eval_res.get("sub_scores", {}).get("motion_vfx", 0),
                "resolution_score": 100.0 if width >= 1920 else 70.0,
                "duration_score": eval_res.get("sub_scores", {}).get("pacing", 0),
                "kills": eval_res.get("kills", []),
                "highest_kill": eval_res.get("highest_kill", "NONE"),
                "duration": round(duration, 1),
                "resolution": f"{width}x{height}",
                "scenes_per_min": 0.0,
                "worthy": eval_res.get("worthy", False),
                "is_clutch": eval_res.get("is_clutch", False),
                "scanned_at": datetime.now().isoformat(),
            }
            if verbose:
                print(f"    Score: {result['score']:.1f}/100 [{result['tier']}] | Kills: {result['highest_kill']} ({len(result['kills'])}) | {width}x{height} | {duration:.1f}s | Clutch={result['is_clutch']}")
            return result
    except Exception as _eval_err:
        pass

    # ── Kill score (40%) fallback with death check ──────────────────────────────
    kills = fast_kill_scan(video_path)
    
    # Fast trailing death check
    player_died = False
    try:
        import cv2, numpy as np
        cap_chk = cv2.VideoCapture(video_path)
        fps_chk = cap_chk.get(cv2.CAP_PROP_FPS) or 30.0
        tot_f = int(cap_chk.get(cv2.CAP_PROP_FRAME_COUNT))
        if tot_f > 10:
            trail_f = int(tot_f * 0.90)
            cap_chk.set(cv2.CAP_PROP_POS_FRAMES, trail_f)
            ret_c, frame_c = cap_chk.read()
            if ret_c and frame_c is not None:
                h_c, w_c = frame_c.shape[:2]
                roi_c = frame_c[int(h_c * 0.2):int(h_c * 0.8), int(w_c * 0.2):int(w_c * 0.8)]
                hsv_c = cv2.cvtColor(roi_c, cv2.COLOR_BGR2HSV)
                if float(np.mean(hsv_c[:, :, 1])) < 38.0:
                    player_died = True
        cap_chk.release()
    except Exception:
        pass

    if player_died and len(kills) <= 1:
        kill_score = 0.0
        highest_kill = "NONE (PLAYER DIED)"
    else:
        kill_score_raw = sum(KILL_WEIGHTS.get(k, 1) for _, k in kills)
        kill_score = min(100, kill_score_raw * 10)  # normalize: penta alone = 100
        highest_kill = (
            max(kills, key=lambda x: KILL_WEIGHTS.get(x[1], 0))[1]
            if kills else "none"
        )

    # ── Duration score (15%) ─────────────────────────────────────────────────
    if OPTIMAL_MIN <= duration <= OPTIMAL_MAX:
        duration_score = 100.0
    elif duration < OPTIMAL_MIN:
        duration_score = max(0, (duration / OPTIMAL_MIN) * 100)
    else:
        # Too long — penalize
        duration_score = max(0, 100 - ((duration - OPTIMAL_MAX) / OPTIMAL_MAX) * 100)

    # ── Resolution score (15%) ───────────────────────────────────────────────
    if width >= 1920:
        resolution_score = 100.0
    elif width >= 1280:
        resolution_score = 70.0
    elif width > 0:
        resolution_score = 40.0
    else:
        resolution_score = 0.0

    # ── Scene density score (30%) — PySceneDetect ────────────────────────────
    scenes_per_min = get_scene_density(video_path)
    # 10+ scenes/min = very action-heavy, normalize 0-100
    intensity_score = min(100, scenes_per_min * 10)

    # If scenedetect unavailable, use kill count as proxy
    if not SCENEDETECT_OK and kills and not player_died:
        intensity_score = min(100, len(kills) * 25)
    elif player_died:
        intensity_score = 10.0

    # ── Composite score ───────────────────────────────────────────────────────
    if player_died and len(kills) <= 1:
        composite = 0.0
        worthy = False
    else:
        composite = (
            kill_score      * 0.40 +
            intensity_score * 0.30 +
            resolution_score* 0.15 +
            duration_score  * 0.15
        )
        worthy = composite >= RANKABLE_THRESHOLD and len(kills) >= 2

    result = {
        "path": video_path,
        "filename": fname,
        "score": round(composite, 1),
        "kill_score": round(kill_score, 1),
        "intensity_score": round(intensity_score, 1),
        "resolution_score": round(resolution_score, 1),
        "duration_score": round(duration_score, 1),
        "kills": kills,
        "highest_kill": highest_kill,
        "duration": round(duration, 1),
        "resolution": f"{width}x{height}",
        "scenes_per_min": scenes_per_min,
        "worthy": worthy,
        "scanned_at": datetime.now().isoformat(),
    }

    if verbose:
        print(f"    Score: {composite:.0f}/100 | Kills: {kills} | {width}x{height} | {duration:.1f}s")
        if not result["worthy"]:
            print(f"    SKIP — score below threshold ({RANKABLE_THRESHOLD})")

    return result


# ─── Multi-clip scanner ────────────────────────────────────────────────────────

def scan_and_rank(
    folder: str = None,
    top_n: int = 5,
    use_cache: bool = True,
    cache_max_age_hours: float = 24.0
) -> list:
    """
    Scan all clips in folder, score each, return sorted list (best first).

    Args:
        folder: folder to scan (defaults to LOL_INPUT_DIR)
        top_n: return only top N clips
        use_cache: skip re-scoring clips scanned recently
        cache_max_age_hours: how old a cache entry can be before re-scoring

    Returns:
        List of score dicts, sorted by score descending.
    """
    folder = folder or LOL_INPUT_DIR
    print(f"\n{'='*55}")
    print(f"  CLIP RANKER — scanning: {folder}")
    print(f"{'='*55}")

    # Find all video files
    all_files = []
    for fmt in SUPPORTED_FORMATS:
        all_files.extend(glob.glob(os.path.join(folder, fmt)))
        all_files.extend(glob.glob(os.path.join(folder, "**", fmt), recursive=True))
    all_files = list(set(all_files))

    if not all_files:
        print(f"  No clips found in: {folder}")
        return []

    print(f"  Found {len(all_files)} clip(s) to evaluate\n")

    # Load cache
    cache = {}
    if use_cache and os.path.exists(RANK_CACHE_PATH):
        try:
            with open(RANK_CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    results = []
    import time
    now = time.time()
    max_age_seconds = cache_max_age_hours * 3600

    for path in all_files:
        fname = os.path.basename(path)
        mtime = os.path.getmtime(path)

        # Use cache if entry exists and clip hasn't been modified
        if fname in cache:
            entry = cache[fname]
            cached_mtime = entry.get("mtime", 0)
            cached_at = entry.get("cached_at", 0)
            age = now - cached_at

            if abs(mtime - cached_mtime) < 1.0 and age < max_age_seconds:
                print(f"  Cache hit: {fname} → score {entry['score']}")
                results.append(entry)
                continue

        # Score fresh
        scored = score_clip(path, verbose=True)
        scored["mtime"] = mtime
        scored["cached_at"] = now
        cache[fname] = scored
        results.append(scored)

    # Save updated cache
    try:
        with open(RANK_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'─'*55}")
    print(f"  RANKING (top {min(top_n, len(results))}):")
    for i, r in enumerate(results[:top_n], 1):
        worthy_str = "UPLOAD" if r["worthy"] else "SKIP"
        print(f"  #{i} [{worthy_str}] {r['filename']:<40} score={r['score']}")
    print(f"{'─'*55}\n")

    return results


def get_best_clip(folder: str = None) -> Optional[str]:
    """Return path of the single best clip to process, or None if none qualify."""
    ranked = scan_and_rank(folder=folder, top_n=1)
    if ranked and ranked[0]["worthy"]:
        return ranked[0]["path"]
    return None


# ─── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else LOL_INPUT_DIR
    results = scan_and_rank(folder=folder, top_n=10, use_cache=False)
    print(f"\nTotal clips evaluated: {len(results)}")
    worthy = [r for r in results if r["worthy"]]
    print(f"Worthy for upload: {len(worthy)}")
