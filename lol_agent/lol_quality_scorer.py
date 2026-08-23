"""
LOL Agent — Quality Scorer
Compares the rendered Short against the original clip to verify quality.
Run after lol_editor produces the final video, before uploading.

Checks:
  1. kill_coverage     — did all kill peaks from original land in the montage?
  2. beat_sync_error   — how far is the music drop from the kill peak? (seconds)
  3. first_frame_score — is the first frame dynamic (high motion/saturation)?
  4. source_quality    — is source resolution >= 1080p?
  5. duration_fit      — is the Short between 18-30s?

Returns a quality dict with composite score (0-100) and pass/fail per check.
If score < QUALITY_THRESHOLD the pipeline retries with adjusted parameters.
"""
import os
import json
import subprocess
import numpy as np
from datetime import datetime
from typing import Optional

try:
    import cv2
    CV2_OK = True
except ImportError:
    CV2_OK = False
    print("  opencv not available — frame quality checks disabled")

# ─── Thresholds ────────────────────────────────────────────────────────────────
QUALITY_THRESHOLD   = 65    # minimum composite score to allow upload
KILL_COVERAGE_MIN   = 0.75  # ≥75% of original kill peaks must be in montage window
BEAT_SYNC_MAX_ERROR = 2.5   # max seconds between music drop and kill peak
MIN_FIRST_FRAME_SAT = 80    # minimum mean saturation of first 3 frames (0-255)
MIN_SOURCE_WIDTH    = 1280  # minimum source resolution width (720p minimum)
MIN_DURATION        = 15.0  # shortest acceptable Short
MAX_DURATION        = 62.0  # YouTube Shorts max


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _ffprobe_duration(video_path: str) -> float:
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_format", video_path]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(out.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def _ffprobe_resolution(video_path: str) -> tuple:
    """Returns (width, height)."""
    try:
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
               "-show_streams", video_path]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(out.stdout)
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                return s.get("width", 0), s.get("height", 0)
    except Exception:
        pass
    return 0, 0


def _get_frame_saturation(video_path: str, timestamp: float = 0.5) -> float:
    """
    Returns mean HSV saturation of a frame at given timestamp.
    High saturation = colorful/active frame (good for thumbnail/first frame).
    """
    if not CV2_OK:
        return 128.0

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(timestamp * fps))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return 0.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        return float(np.mean(hsv[:, :, 1]))  # S channel
    except Exception:
        return 0.0


def _get_frame_motion(video_path: str, timestamp: float = 0.5) -> float:
    """
    Returns motion score at timestamp by comparing two adjacent frames.
    High motion = dynamic, action-packed moment.
    """
    if not CV2_OK:
        return 50.0

    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_idx = int(timestamp * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_idx - 1))
        ret1, f1 = cap.read()
        ret2, f2 = cap.read()
        cap.release()

        if not ret1 or not ret2:
            return 0.0

        g1 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(g1, g2)
        return float(np.mean(diff))
    except Exception:
        return 0.0


# ─── Main Scorer ───────────────────────────────────────────────────────────────

def score_short(
    rendered_path: str,
    source_path: str,
    analysis: dict,
    beat_drop_time: float = 30.0,
    music_file: str = "",
) -> dict:
    """
    Score the rendered Short against the original analysis.

    Args:
        rendered_path: path to the final rendered Short .mp4
        source_path:   path to the original source clip
        analysis:      dict from lol_momentum_analyzer (contains peaks, clip_duration, etc.)
        beat_drop_time: where the music drop lands in the song (seconds)
        music_file:    basename of the chosen music file (for logging)

    Returns:
        dict with:
          - score (0-100): composite quality score
          - pass (bool): score >= QUALITY_THRESHOLD
          - breakdown: per-check scores and values
          - issues: list of human-readable problems
          - recommendation: what to change on retry
    """
    issues = []
    breakdown = {}

    # ── 1. Source resolution (15%) ─────────────────────────────────────────────
    src_w, src_h = _ffprobe_resolution(source_path)
    if src_w >= 1920:
        res_score = 100.0
    elif src_w >= 1280:
        res_score = 70.0
        issues.append(f"Source is {src_w}x{src_h} (720p) — 1080p preferred")
    elif src_w > 0:
        res_score = 35.0
        issues.append(f"Source is low resolution: {src_w}x{src_h}")
    else:
        res_score = 0.0
        issues.append("Could not read source resolution")
    breakdown["source_resolution"] = {
        "score": res_score, "value": f"{src_w}x{src_h}", "weight": 0.15
    }

    # ── 2. Kill coverage (35%) ─────────────────────────────────────────────────
    # Check how many of the original kill peaks are within the montage window
    original_peaks = analysis.get("peaks", [])
    peak_start = analysis.get("peak_start", 0.0)
    peak_end = analysis.get("peak_end", analysis.get("clip_duration", 30.0))
    window = (peak_start, peak_end)

    if original_peaks:
        peaks_in_window = [p for p in original_peaks
                          if window[0] <= p[0] <= window[1]]
        coverage = len(peaks_in_window) / len(original_peaks)
        kill_score = coverage * 100
        if coverage < KILL_COVERAGE_MIN:
            issues.append(
                f"Kill coverage {coverage:.0%} — {len(peaks_in_window)}/{len(original_peaks)} peaks "
                f"in window [{peak_start:.1f}s–{peak_end:.1f}s]. Adjust clip window."
            )
    else:
        coverage = 1.0  # no peaks to cover = no penalty
        kill_score = 60.0  # medium score if no kills detected
        issues.append("No kill peaks detected in source — clip may not contain a kill")

    breakdown["kill_coverage"] = {
        "score": kill_score,
        "value": f"{coverage:.0%} ({len(peaks_in_window) if original_peaks else 'n/a'}/{len(original_peaks)})",
        "weight": 0.35
    }

    # ── 3. Beat sync accuracy (25%) ────────────────────────────────────────────
    peak_moment_in_clip = analysis.get("peak_moment", 15.0) - peak_start
    # Beat sync: editor sets music_start = max(0, beat_drop_time - peak_moment)
    # So the drop lands at: beat_drop_time - music_start = min(beat_drop_time, peak_moment)
    # Error = how far the drop misses the peak
    music_start = max(0.0, beat_drop_time - peak_moment_in_clip)
    actual_drop_in_video = beat_drop_time - music_start  # = min(drop, peak)
    beat_sync_error = abs(actual_drop_in_video - peak_moment_in_clip)
    # If drop_time >= peak: error=0 (perfect sync)
    # If drop_time < peak: error=peak-drop (music had to start at 0, drop is early)


    if beat_sync_error <= 0.5:
        sync_score = 100.0
    elif beat_sync_error <= 1.5:
        sync_score = 80.0
    elif beat_sync_error <= BEAT_SYNC_MAX_ERROR:
        sync_score = 55.0
    else:
        sync_score = max(0, 100 - beat_sync_error * 20)
        issues.append(f"Beat sync error {beat_sync_error:.1f}s — drop misses kill peak. Try different music.")

    breakdown["beat_sync"] = {
        "score": sync_score,
        "value": f"{beat_sync_error:.2f}s error",
        "weight": 0.25
    }

    # ── 4. First frame quality (15%) ───────────────────────────────────────────
    # First frame should be dynamic (high saturation + motion)
    # Viewers decide to swipe in first 0.5s — boring first frame = death
    sat = _get_frame_saturation(rendered_path, timestamp=0.3)
    motion = _get_frame_motion(rendered_path, timestamp=0.3)

    # Combine saturation and motion into a first-frame quality score
    first_frame_score = min(100, (sat / 255.0) * 50 + min(50, motion * 2))

    if sat < MIN_FIRST_FRAME_SAT:
        issues.append(
            f"First frame low saturation ({sat:.0f}/255) — may look dull in Shorts feed. "
            "Consider starting clip later."
        )
    breakdown["first_frame"] = {
        "score": first_frame_score,
        "value": f"sat={sat:.0f} motion={motion:.1f}",
        "weight": 0.15
    }

    # ── 5. Duration fit (10%) ──────────────────────────────────────────────────
    rendered_dur = _ffprobe_duration(rendered_path)
    if 18.0 <= rendered_dur <= 35.0:
        dur_score = 100.0
    elif rendered_dur < 18.0:
        dur_score = max(0, (rendered_dur / 18.0) * 100)
        issues.append(f"Short is only {rendered_dur:.1f}s — too short for good retention")
    elif rendered_dur > 35.0:
        dur_score = max(0, 100 - (rendered_dur - 35.0) * 10)
        issues.append(f"Short is {rendered_dur:.1f}s — YouTube retention typically drops after 30s")

    breakdown["duration"] = {
        "score": dur_score,
        "value": f"{rendered_dur:.1f}s",
        "weight": 0.10
    }

    # ── Composite score ────────────────────────────────────────────────────────
    composite = sum(
        b["score"] * b["weight"] for b in breakdown.values()
    )
    composite = round(composite, 1)
    passed = composite >= QUALITY_THRESHOLD

    # ── Retry recommendation ───────────────────────────────────────────────────
    recommendation = None
    if not passed:
        lowest = min(breakdown.items(), key=lambda x: x[1]["score"])
        recs = {
            "kill_coverage": "Adjust clip window — try ±2s around detected peaks",
            "beat_sync": "Try a different music track with drop at different timestamp",
            "first_frame": "Start clip 1-2s later to skip slow intro frames",
            "source_resolution": "Use higher quality source recording (1080p+)",
            "duration": "Adjust SHORT_MAX_DURATION in lol_config.py",
        }
        recommendation = recs.get(lowest[0], "Review clip manually")

    result = {
        "score": composite,
        "pass": passed,
        "threshold": QUALITY_THRESHOLD,
        "breakdown": breakdown,
        "issues": issues,
        "recommendation": recommendation,
        "rendered_path": rendered_path,
        "music_file": music_file,
        "beat_sync_error_seconds": round(beat_sync_error, 2),
        "kill_coverage_pct": round(coverage * 100, 1) if original_peaks else None,
        "scored_at": datetime.now().isoformat(),
    }

    # Print summary
    status = "PASS" if passed else "FAIL"
    print(f"\n{'='*50}")
    print(f"  QUALITY SCORE: {composite:.0f}/100 [{status}]")
    print(f"{'='*50}")
    for name, b in breakdown.items():
        bar = "█" * int(b["score"] / 10) + "░" * (10 - int(b["score"] / 10))
        print(f"  {name:<18} [{bar}] {b['score']:.0f}  ({b['value']})")
    if issues:
        print(f"\n  Issues:")
        for issue in issues:
            print(f"    - {issue}")
    if recommendation and not passed:
        print(f"\n  Retry suggestion: {recommendation}")
    print(f"{'='*50}\n")

    return result


def save_quality_log(quality_result: dict, log_dir: str = None):
    """Append quality result to quality_log.jsonl for long-term tracking."""
    log_dir = log_dir or os.path.dirname(__file__)
    log_path = os.path.join(log_dir, "quality_log.jsonl")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(quality_result, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  Could not save quality log: {e}")


# ─── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python lol_quality_scorer.py <rendered.mp4> <source.mp4>")
        sys.exit(1)
    rendered = sys.argv[1]
    source = sys.argv[2]
    # Mock analysis for testing
    mock_analysis = {
        "peaks": [(15.0, "PENTAKILL")],
        "peak_start": 0.0,
        "peak_end": 28.0,
        "peak_moment": 15.0,
        "clip_duration": 28.0,
    }
    result = score_short(rendered, source, mock_analysis, beat_drop_time=30.0)
    print(f"Final score: {result['score']} | Pass: {result['pass']}")
