"""
LOL Agent — Performance Tracker
Checks YouTube analytics 48h after each upload and builds a performance log
that drives parameter optimization recommendations.

Run modes:
  1. schedule_check(video_id, ...) — call right after upload, queues a 48h check
  2. run_pending_checks()          — call at pipeline start to process any due checks
  3. generate_recommendations()    — reads performance_log and suggests config changes
"""
import os
import json
import pickle
import time
from datetime import datetime
from typing import Optional

from lol_config import TOKEN_PATH, GEMINI_API_KEY, GEMINI_MODEL

# ─── Paths ─────────────────────────────────────────────────────────────────────
TRACKER_DIR       = os.path.dirname(__file__)
PENDING_PATH      = os.path.join(TRACKER_DIR, "pending_checks.json")
PERFORMANCE_LOG   = os.path.join(TRACKER_DIR, "performance_log.jsonl")
RECOMMENDATIONS   = os.path.join(TRACKER_DIR, "optimization_report.json")

# ─── Thresholds for SUCCESS/FAIL classification ────────────────────────────────
VIEWS_SUCCESS_48H  = 3000   # views after 48h to classify as SUCCESS
VIEWS_FAIL_48H     = 800    # views after 48h to classify as FAIL (else AVERAGE)
CHECK_AFTER_HOURS  = 48.0   # how many hours after upload to check


# ─── YouTube API helper ────────────────────────────────────────────────────────

def _get_youtube():
    """Return authenticated YouTube Data API client."""
    try:
        from googleapiclient.discovery import build
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "rb") as f:
                creds = pickle.load(f)
            return build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"  YT auth error: {e}")
    return None


def fetch_video_stats(video_id: str) -> Optional[dict]:
    """Fetch views, likes, comments for a video via YT Data API."""
    yt = _get_youtube()
    if not yt:
        return None
    try:
        resp = yt.videos().list(
            part="statistics,snippet",
            id=video_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            return None
        stats = items[0].get("statistics", {})
        return {
            "views":    int(stats.get("viewCount", 0)),
            "likes":    int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
        }
    except Exception as e:
        print(f"  fetch_video_stats error: {e}")
        return None


# ─── Schedule / check ──────────────────────────────────────────────────────────

def schedule_check(
    video_id: str,
    video_url: str,
    title: str,
    action_type: str,
    champion: str,
    quality_score: float,
    music_file: str,
    beat_sync_error: float,
    kill_coverage_pct: float,
):
    """
    Called right after a successful upload.
    Adds an entry to pending_checks.json with the scheduled check time.
    """
    pending = _load_pending()
    check_at = time.time() + CHECK_AFTER_HOURS * 3600

    pending[video_id] = {
        "video_id":          video_id,
        "url":               video_url,
        "title":             title,
        "action_type":       action_type,
        "champion":          champion,
        "quality_score":     quality_score,
        "music_file":        music_file,
        "beat_sync_error":   beat_sync_error,
        "kill_coverage_pct": kill_coverage_pct,
        "published_at":      datetime.now().isoformat(),
        "check_at":          check_at,
        "checked":           False,
    }
    _save_pending(pending)
    eta = datetime.fromtimestamp(check_at).strftime("%Y-%m-%d %H:%M")
    print(f"  Performance check scheduled for: {eta}")


def run_pending_checks():
    """
    Check all pending videos that are due for their 48h stats fetch.
    Call this at the START of each pipeline run.
    """
    pending = _load_pending()
    now = time.time()
    checked_any = False

    for video_id, entry in list(pending.items()):
        if entry.get("checked"):
            continue
        if now < entry.get("check_at", 0):
            eta_str = datetime.fromtimestamp(entry["check_at"]).strftime("%H:%M %d/%m")
            print(f"  Pending check for {video_id} scheduled at {eta_str} — not yet due")
            continue

        print(f"\n  Checking stats for: {entry['title'][:40]}")
        stats = fetch_video_stats(video_id)
        if not stats:
            print(f"  Could not fetch stats — will retry next run")
            continue

        views = stats["views"]
        likes = stats["likes"]

        if views >= VIEWS_SUCCESS_48H:
            result = "SUCCESS"
        elif views <= VIEWS_FAIL_48H:
            result = "FAIL"
        else:
            result = "AVERAGE"

        log_entry = {**entry, **stats, "result": result,
                     "checked_at": datetime.now().isoformat()}
        _append_performance_log(log_entry)

        pending[video_id]["checked"] = True
        print(f"  {result}: {views:,} views | {likes} likes | {entry['action_type']} | {entry['champion']}")
        checked_any = True

    _save_pending(pending)
    return checked_any


# ─── Optimization recommendations ─────────────────────────────────────────────

def generate_recommendations() -> dict:
    """
    Read performance_log and generate simple rule-based recommendations.
    Compares SUCCESS vs FAIL entries to find what parameters correlate with views.

    Returns a dict of recommendations.
    """
    entries = _load_performance_log()
    if len(entries) < 3:
        print(f"  Not enough data yet ({len(entries)} entries, need 3+)")
        return {}

    successes = [e for e in entries if e.get("result") == "SUCCESS"]
    failures  = [e for e in entries if e.get("result") == "FAIL"]
    all_e     = entries

    recs = {
        "generated_at":  datetime.now().isoformat(),
        "total_entries": len(entries),
        "successes":     len(successes),
        "failures":      len(failures),
        "insights":      [],
        "action_rankings": {},
        "music_rankings":  {},
    }

    # ── Action type performance ────────────────────────────────────────────────
    action_views = {}
    for e in all_e:
        at = e.get("action_type", "unknown")
        v  = e.get("views", 0)
        action_views.setdefault(at, []).append(v)

    action_avg = {
        at: round(sum(vs) / len(vs))
        for at, vs in action_views.items() if vs
    }
    recs["action_rankings"] = dict(
        sorted(action_avg.items(), key=lambda x: -x[1])
    )

    if action_avg:
        best_action = max(action_avg, key=action_avg.get)
        worst_action = min(action_avg, key=action_avg.get)
        recs["insights"].append(
            f"Best action type: {best_action} ({action_avg[best_action]:,} avg views) — "
            f"prioritize these clips"
        )
        if action_avg[worst_action] < action_avg[best_action] * 0.4:
            recs["insights"].append(
                f"Underperforming: {worst_action} ({action_avg[worst_action]:,} avg views) — "
                f"consider raising quality threshold for this type"
            )

    # ── Music performance ──────────────────────────────────────────────────────
    music_views = {}
    for e in all_e:
        mf = os.path.basename(e.get("music_file", "unknown"))
        v  = e.get("views", 0)
        music_views.setdefault(mf, []).append(v)

    music_avg = {
        mf: round(sum(vs) / len(vs))
        for mf, vs in music_views.items() if vs
    }
    recs["music_rankings"] = dict(
        sorted(music_avg.items(), key=lambda x: -x[1])
    )

    if music_avg and len(music_avg) > 1:
        best_music = max(music_avg, key=music_avg.get)
        recs["insights"].append(
            f"Best music: {best_music} ({music_avg[best_music]:,} avg views)"
        )

    # ── Beat sync analysis ─────────────────────────────────────────────────────
    sync_success = [e.get("beat_sync_error", 999) for e in successes]
    sync_fail    = [e.get("beat_sync_error", 999) for e in failures]
    if sync_success and sync_fail:
        avg_sync_s = sum(sync_success) / len(sync_success)
        avg_sync_f = sum(sync_fail) / len(sync_fail)
        if avg_sync_f > avg_sync_s + 0.5:
            recs["insights"].append(
                f"Beat sync matters: success avg error {avg_sync_s:.1f}s vs "
                f"fail avg {avg_sync_f:.1f}s — tighten BEAT_SYNC_MAX_ERROR"
            )

    # ── Quality score correlation ──────────────────────────────────────────────
    qs_success = [e.get("quality_score", 0) for e in successes]
    qs_fail    = [e.get("quality_score", 0) for e in failures]
    if qs_success and qs_fail:
        avg_qs_s = sum(qs_success) / len(qs_success)
        avg_qs_f = sum(qs_fail) / len(qs_fail)
        recs["insights"].append(
            f"Quality score: successful videos avg {avg_qs_s:.0f} vs failed {avg_qs_f:.0f} — "
            f"{'threshold is well calibrated' if avg_qs_s > avg_qs_f else 'threshold may need adjustment'}"
        )

    # Save
    with open(RECOMMENDATIONS, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)

    print(f"\n  OPTIMIZATION REPORT ({len(entries)} videos analyzed):")
    print(f"  Success: {len(successes)} | Fail: {len(failures)} | Average: {len(entries)-len(successes)-len(failures)}")
    for insight in recs["insights"]:
        print(f"  > {insight}")
    if recs["action_rankings"]:
        print(f"\n  Action type rankings (avg views):")
        for at, avg in list(recs["action_rankings"].items())[:5]:
            print(f"    {at:<15} {avg:>6,} views")
    print(f"\n  Full report: {RECOMMENDATIONS}\n")

    return recs


# ─── I/O helpers ───────────────────────────────────────────────────────────────

def _load_pending() -> dict:
    if os.path.exists(PENDING_PATH):
        try:
            with open(PENDING_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_pending(data: dict):
    with open(PENDING_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _append_performance_log(entry: dict):
    with open(PERFORMANCE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _load_performance_log() -> list:
    entries = []
    if os.path.exists(PERFORMANCE_LOG):
        with open(PERFORMANCE_LOG, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    return entries


# ─── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print("Running pending performance checks...")
        run_pending_checks()
    elif cmd == "report":
        print("Generating optimization report...")
        generate_recommendations()
    elif cmd == "log":
        entries = _load_performance_log()
        print(f"Performance log: {len(entries)} entries")
        for e in entries[-5:]:
            print(f"  {e.get('result','?')} | {e.get('views',0):,}v | {e.get('action_type','?')} | {e.get('title','?')[:40]}")
