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
from datetime import datetime, timezone
from typing import Optional, Dict, Any

try:
    from lol_agent.lol_config import TOKEN_PATH, GEMINI_API_KEY, GEMINI_MODEL
except ImportError:
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
    """Return authenticated YouTube Data API client (strictly non-interactive)."""
    try:
        try:
            from lol_agent.lol_publisher import get_lol_youtube_service
        except ImportError:
            from lol_publisher import get_lol_youtube_service
        return get_lol_youtube_service(allow_interactive=False)
    except Exception as e:
        print(f"  YT auth error: {e}")
    return None


def fetch_video_stats(video_id: str, duration_s: float = 15.0) -> Optional[dict]:
    """Pobiera wyświetlenia, polubienia, komentarze oraz realną retencję z YouTube Analytics API."""
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
            return {"not_found": True}
        stats = items[0].get("statistics", {})
        base_stats = {
            "views":    int(stats.get("viewCount", 0)),
            "likes":    int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
        }

        # Dołącz realne dane retencji z YouTube Analytics API jeśli dostępne
        try:
            try:
                from lol_agent.api.youtube_analytics import fetch_video_retention_data
            except ImportError:
                from api.youtube_analytics import fetch_video_retention_data
            r_data = fetch_video_retention_data(video_id, duration_s=duration_s)
            if r_data and r_data.get("status") == "success":
                base_stats["hook_retention_pct"] = r_data.get("hook_retention_pct")
                base_stats["swiped_away_pct"] = r_data.get("swiped_away_pct")
                base_stats["completion_rate_pct"] = r_data.get("completion_rate_pct")
                base_stats["avg_view_pct"] = r_data.get("avg_view_pct")
        except Exception:
            pass

        return base_stats
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
    duration_s: float = 15.0,
    mei: Optional[dict] = None,
):
    """
    Wywoływane tuż po udanym uploadzie na YouTube.
    Zapisuje zadanie wielostopniowej weryfikacji w pending_checks.json.
    Pierwsze sprawdzenie tempa (Stage 1: Launch Velocity) po 6 godzinach.
    """
    pending = _load_pending()
    check_at = time.time() + 6.0 * 3600  # Stage 1: wczesne sprawdzenie po 6h

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
        "duration_s":        duration_s,
        "mei":               mei or {},
        "stage":             1,
        "published_at":      datetime.now().isoformat(),
        "check_at":          check_at,
        "checked":           False,
    }
    _save_pending(pending)
    eta = datetime.fromtimestamp(check_at).strftime("%Y-%m-%d %H:%M")
    print(f"  [PerformanceTracker] Weryfikacja tempa (Stage 1) zaplanowana na: {eta}")


def run_pending_checks(force_all: bool = False) -> bool:
    """
    Sprawdza filmy w pending_checks.json z uwzględnieniem tempa (Views Per Hour)
    i wczesnej retencji AVD%.
    Zapisuje zweryfikowane dane do performance_log.jsonl.
    """
    pending = _load_pending()
    now = time.time()
    checked_any = False

    for video_id, entry in list(pending.items()):
        if entry.get("checked") and not force_all:
            continue
        if not force_all and now < entry.get("check_at", 0):
            eta_str = datetime.fromtimestamp(entry["check_at"]).strftime("%H:%M %d/%m")
            print(f"  [Pending] {video_id} ({entry.get('title','')[:30]}) zaplanowane na {eta_str}")
            continue

        print(f"\n  [PerformanceTracker] Weryfikacja statystyk dla: {entry['title'][:40]}")
        stats = fetch_video_stats(video_id, duration_s=float(entry.get("duration_s", 15.0)))
        if not stats:
            print(f"  [PerformanceTracker] Błąd odczytu statystyk YT dla {video_id} — próba w kolejnym cyklu")
            if _get_youtube() is None:
                print("  [PerformanceTracker] YouTube API niedostępne (brak tokenu OAuth) — wstrzymuję sprawdzanie kolejki.")
                break
            continue

        if stats.get("not_found"):
            print(f"  [PerformanceTracker] Wideo {video_id} nie istnieje na YouTube (usunięte/prywatne) — oznaczam jako sprawdzone.")
            entry["checked"] = True
            entry["result"] = "NOT_FOUND"
            _save_pending(pending)
            continue

        views = stats["views"]
        likes = stats["likes"]
        hook_ret = stats.get("hook_retention_pct")
        avg_view_pct = stats.get("avg_view_pct")

        # Oblicz wiek publikacji i tempo wyświetleń na godzinę (Views Per Hour - VPH)
        pub_str = entry.get("published_at")
        elapsed_hours = 48.0
        if pub_str:
            try:
                dt_pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)
                if dt_pub.tzinfo is None:
                    dt_pub = dt_pub.replace(tzinfo=timezone.utc)
                elapsed_hours = max(0.5, (now_utc - dt_pub).total_seconds() / 3600.0)
            except Exception:
                pass

        views_per_hour = round(views / elapsed_hours, 1)

        # Wielowymiarowe progi sukcesu uwzględniające tempo (VPH) oraz retencję (AVD%)
        is_breakout = (elapsed_hours <= 18.0 and (views_per_hour >= 80.0 or views >= 1000))
        is_viral_loop = (avg_view_pct is not None and avg_view_pct >= 95.0)
        is_high_ret = (hook_ret is not None and hook_ret >= 75.0 and views >= 1000)

        if views >= VIEWS_SUCCESS_48H or is_breakout or is_viral_loop or is_high_ret:
            result = "SUCCESS"
        elif elapsed_hours >= 36.0 and views <= VIEWS_FAIL_48H and (hook_ret is None or hook_ret < 62.0):
            result = "FAIL"
        else:
            result = "AVERAGE"

        # Ocena trafności estymacji algorytmu (Quality Score vs realny wynik)
        qs = float(entry.get("quality_score", 80.0))
        if views >= 2000 and qs < 75.0:
            prediction_eval = "UNDERESTIMATED"
        elif views <= 500 and qs >= 85.0 and elapsed_hours >= 24.0:
            prediction_eval = "OVERESTIMATED"
        elif views >= 1500 and qs >= 80.0:
            prediction_eval = "ACCURATE_HIGH"
        elif views <= 700 and qs < 75.0 and elapsed_hours >= 24.0:
            prediction_eval = "ACCURATE_LOW"
        else:
            prediction_eval = "NEUTRAL"

        log_entry = {
            **entry,
            **stats,
            "elapsed_hours": round(elapsed_hours, 1),
            "views_per_hour": views_per_hour,
            "result": result,
            "prediction_eval": prediction_eval,
            "checked_at": datetime.now().isoformat()
        }
        _append_performance_log(log_entry)

        # Wielostopniowy cykl sprawdzania (Stage 1 @ 6h -> Stage 2 @ 24h -> Stage 3 @ 48h)
        current_stage = int(entry.get("stage", 1))
        if elapsed_hours < 18.0 and not force_all:
            pending[video_id]["stage"] = 2
            pending[video_id]["check_at"] = time.time() + 18.0 * 3600
            pending[video_id]["checked"] = False
            pending[video_id]["last_result"] = result
        elif elapsed_hours < 36.0 and not force_all:
            pending[video_id]["stage"] = 3
            pending[video_id]["check_at"] = time.time() + 24.0 * 3600
            pending[video_id]["checked"] = False
            pending[video_id]["last_result"] = result
        else:
            pending[video_id]["checked"] = True
            pending[video_id]["last_result"] = result

        ret_info = f" | Hook: {hook_ret:.1f}%" if hook_ret else ""
        avd_info = f" | AVD: {avg_view_pct:.1f}%" if avg_view_pct else ""
        vph_info = f" | VPH: {views_per_hour}/h"
        print(f"  [{result}] {views:,} views{vph_info} ({elapsed_hours:.1f}h){ret_info}{avd_info} | Predykcja: {prediction_eval}")
        checked_any = True

    _save_pending(pending)
    return checked_any


def reconcile_and_verify_published_videos() -> int:
    """
    Skanuje published_videos.jsonl i porównuje z performance_log.jsonl.
    Wszystkie opublikowane filmy (zwłaszcza te z ostatnich tygodni), które nie
    zostały jeszcze sprawdzone, dodaje do pending_checks i odpytuje o realne statystyki.
    Zwraca liczbę zaktualizowanych filmów.
    """
    pub_log_file = os.path.join(TRACKER_DIR, "published_videos.jsonl")
    if not os.path.exists(pub_log_file):
        return 0

    existing_logged_ids = set()
    for entry in _load_performance_log():
        if entry.get("video_id"):
            existing_logged_ids.add(entry["video_id"])

    pending = _load_pending()
    count_reconciled = 0

    with open(pub_log_file, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                pub_item = json.loads(line.strip())
            except Exception:
                continue

            vid = pub_item.get("video_id")
            if not vid or vid in existing_logged_ids:
                continue

            qs = float(pub_item.get("initial_qa_score", 85.0))
            if vid not in pending or not pending[vid].get("checked"):
                pending[vid] = {
                    "video_id": vid,
                    "url": pub_item.get("url", f"https://www.youtube.com/shorts/{vid}"),
                    "title": pub_item.get("title", ""),
                    "action_type": pub_item.get("action_type", "outplay"),
                    "champion": pub_item.get("champion", "Katarina"),
                    "quality_score": qs,
                    "music_file": "",
                    "beat_sync_error": 0.0,
                    "kill_coverage_pct": 100.0,
                    "duration_s": float(pub_item.get("duration_s", 15.0)),
                    "published_at": pub_item.get("timestamp", datetime.now().isoformat()),
                    "check_at": time.time() - 1,  # gotowe do natychmiastowej weryfikacji
                    "checked": False,
                }
                count_reconciled += 1

    if count_reconciled > 0:
        _save_pending(pending)
        print(f"  [PerformanceTracker] Dodano {count_reconciled} filmów do kolejki weryfikacji.")
        if _get_youtube() is not None:
            print("  [PerformanceTracker] Uruchamiam sprawdzenie statystyk...")
            run_pending_checks(force_all=True)
        else:
            print("  [PerformanceTracker] YouTube API niedostępne (brak aktywnego tokenu) — weryfikacja nastąpi po autoryzacji.")

    return count_reconciled


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
    # Aktualizacja in-place per video_id z atomic write (zapobiega rozrostowi pliku do wielu megabajtow)
    entries = _load_performance_log()
    vid = entry.get("video_id")
    updated = False
    if vid:
        for i, existing in enumerate(entries):
            if existing.get("video_id") == vid:
                entries[i] = entry
                updated = True
                break
    if not updated:
        entries.append(entry)

    tmp_path = PERFORMANCE_LOG + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp_path, PERFORMANCE_LOG)


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
