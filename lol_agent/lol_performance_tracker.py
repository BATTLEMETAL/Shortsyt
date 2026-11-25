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
                from lol_agent.api.youtube_analytics import fetch_video_retention_data, fetch_bulk_video_analytics
            except ImportError:
                from api.youtube_analytics import fetch_video_retention_data, fetch_bulk_video_analytics
            r_data = fetch_video_retention_data(video_id, duration_s=duration_s)
            if r_data and r_data.get("status") == "success":
                base_stats["hook_retention_pct"] = r_data.get("hook_retention_pct")
                base_stats["swiped_away_pct"] = r_data.get("swiped_away_pct")
                base_stats["completion_rate_pct"] = r_data.get("completion_rate_pct")
                base_stats["avg_view_pct"] = r_data.get("avg_view_pct")
            bulk = fetch_bulk_video_analytics()
            yb = bulk.get(video_id) if isinstance(bulk, dict) else None
            if yb:
                if base_stats.get("avg_view_pct") is None and yb.get("avg_view_pct") is not None:
                    base_stats["avg_view_pct"] = yb.get("avg_view_pct")
                base_stats["engaged_views"] = yb.get("engaged_views")
                base_stats["engaged_view_rate_pct"] = yb.get("engaged_view_rate_pct")
                base_stats["shares"] = yb.get("shares", 0)
                base_stats["subscribers_gained"] = yb.get("subscribers_gained", 0)
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


def _piecewise_score(val: float, low_x: float, mid_x: float, high_x: float) -> float:
    """Mapuje metrykę na skalę 0-100: low_x -> 30, mid_x -> 80, high_x -> 100."""
    if val <= low_x:
        return max(0.0, round(30.0 * (val / max(low_x, 1e-6)), 1))
    if val <= mid_x:
        return round(30.0 + 50.0 * ((val - low_x) / max(mid_x - low_x, 1e-6)), 1)
    if val <= high_x:
        return round(80.0 + 20.0 * ((val - mid_x) / max(high_x - mid_x, 1e-6)), 1)
    return 100.0


def evaluate_48h_post_publish_gate(
    entry: Dict[str, Any],
    stats: Dict[str, Any],
    channel_median_views: float = 1640.0,
) -> Dict[str, Any]:
    """
    Bramka 48h (Reality Gate): mierzy Real Watchability Index (RWI 0-100) oraz wykonuje
    Definition Match Audit — sprawdza, czy realny odbiór po 48h potwierdził hipotezę montażową (t=0h).
    """
    views = int(stats.get("views") or entry.get("views") or 0)
    likes = int(stats.get("likes") or entry.get("likes") or 0)
    comments = int(stats.get("comments") or entry.get("comments") or 0)
    shares = int(stats.get("shares") or entry.get("shares") or 0)
    subs_gained = int(stats.get("subscribers_gained") or entry.get("subscribers_gained") or 0)

    hook_ret = stats.get("hook_retention_pct")
    if hook_ret is None:
        hook_ret = entry.get("hook_retention_pct")
    swiped = stats.get("swiped_away_pct")
    if swiped is None:
        swiped = entry.get("swiped_away_pct")
    if hook_ret is None and swiped is not None and float(swiped) > 0:
        hook_ret = round(100.0 - float(swiped), 1)

    engaged_rate = stats.get("engaged_view_rate_pct")
    if engaged_rate is None:
        engaged_rate = entry.get("engaged_view_rate_pct")

    avd_pct = stats.get("avg_view_pct")
    if avd_pct is None:
        avd_pct = entry.get("avg_view_pct")

    # 1. Składniki Real Watchability Index (RWI)
    reach_48h_score = round(min(100.0, (views / max(float(channel_median_views), 1.0)) * 70.0), 1)

    if hook_ret is not None and float(hook_ret) > 0:
        hook_watch_score = _piecewise_score(float(hook_ret), 65.0, 83.5, 90.0)
        hook_signal_source = "hook_retention_pct"
    elif engaged_rate is not None and float(engaged_rate) > 0:
        hook_watch_score = _piecewise_score(float(engaged_rate), 35.0, 50.0, 60.0)
        hook_signal_source = "engaged_view_rate_pct"
    else:
        hook_watch_score = round(min(85.0, max(35.0, reach_48h_score)), 1)
        hook_signal_source = "reach_fallback"

    if avd_pct is not None and float(avd_pct) > 0:
        avd_loop_score = _piecewise_score(float(avd_pct), 75.0, 100.0, 115.0)
        avd_signal_source = "avg_view_pct"
    else:
        avd_loop_score = round(min(85.0, max(35.0, reach_48h_score)), 1)
        avd_signal_source = "reach_fallback"

    weighted_eng_pct = ((likes + comments * 3 + shares * 5) / max(views, 1)) * 100.0
    engagement_sub_score = round(
        min(100.0, weighted_eng_pct * 45.0 + (20.0 if subs_gained > 0 else 0.0)),
        1,
    )

    rwi_score = round(
        0.35 * hook_watch_score
        + 0.35 * avd_loop_score
        + 0.20 * reach_48h_score
        + 0.10 * engagement_sub_score,
        1,
    )

    if rwi_score >= 80.0:
        watchability_tier = "EXCELLENT"
    elif rwi_score >= 65.0:
        watchability_tier = "GOOD"
    elif rwi_score >= 50.0:
        watchability_tier = "AVERAGE"
    else:
        watchability_tier = "POOR"

    # 2. Definition Match Audit (czy realne oglądanie po 48h pasuje do założeń z montażu)
    pre_qa_score = float(entry.get("quality_score") or entry.get("initial_qa_score") or 85.0)
    mei = entry.get("mei") or {}

    pred_hook_score = float(mei.get("hook_score") if mei.get("hook_score") is not None else pre_qa_score)
    hook_latency = float(mei.get("hook_latency_s") if mei.get("hook_latency_s") is not None else 1.0)
    pred_hook_good = (pred_hook_score >= 75.0) and (hook_latency <= 1.8)
    real_hook_good = hook_watch_score >= 70.0

    if pred_hook_good and real_hook_good:
        hook_verdict = "HOOK_CONFIRMED"
    elif pred_hook_good and not real_hook_good:
        hook_verdict = "OVERESTIMATED_HOOK"
    elif not pred_hook_good and real_hook_good:
        hook_verdict = "UNDERESTIMATED_HOOK"
    else:
        hook_verdict = "HOOK_WEAK"

    pred_pacing_score = float(mei.get("pacing_score") if mei.get("pacing_score") is not None else pre_qa_score)
    pred_density = float(mei.get("combat_density_pct") if mei.get("combat_density_pct") is not None else 75.0)
    pred_pacing_good = (pred_pacing_score >= 70.0) and (pred_density >= 65.0)
    real_pacing_good = avd_loop_score >= 70.0

    if pred_pacing_good and real_pacing_good:
        pacing_verdict = "PACING_CONFIRMED"
    elif pred_pacing_good and not real_pacing_good:
        pacing_verdict = "OVERESTIMATED_PACING"
    elif not pred_pacing_good and real_pacing_good:
        pacing_verdict = "UNDERESTIMATED_PACING"
    else:
        pacing_verdict = "PACING_WEAK"

    pred_good = pre_qa_score >= 75.0
    real_good = rwi_score >= 68.0
    if pred_good and real_good:
        overall_verdict = "FIT_CONFIRMED"
    elif pred_good and not real_good:
        overall_verdict = "FALSE_POSITIVE_MONTAGE"
    elif not pred_good and real_good:
        overall_verdict = "SURPRISE_VIRAL"
    else:
        overall_verdict = "TRUE_NEGATIVE"

    recommended_adjustments: Dict[str, Any] = {}
    if hook_verdict in ("OVERESTIMATED_HOOK", "HOOK_WEAK"):
        recommended_adjustments["buildup_sec_delta"] = -0.3
        recommended_adjustments["prefer_style"] = "IN_MEDIA_RES"
    if pacing_verdict in ("OVERESTIMATED_PACING", "PACING_WEAK"):
        recommended_adjustments["outro_sec_delta"] = -0.4
        recommended_adjustments.setdefault("prefer_style", "SPEED_RAMP_FLOW")

    return {
        "rwi_score": rwi_score,
        "watchability_tier": watchability_tier,
        "components": {
            "hook_watch_score": hook_watch_score,
            "avd_loop_score": avd_loop_score,
            "reach_48h_score": reach_48h_score,
            "engagement_sub_score": engagement_sub_score,
        },
        "signal_sources": {
            "hook": hook_signal_source,
            "avd": avd_signal_source,
        },
        "definition_audit": {
            "pre_qa_score": round(pre_qa_score, 1),
            "hook_verdict": hook_verdict,
            "pacing_verdict": pacing_verdict,
            "overall_verdict": overall_verdict,
            "recommended_adjustments": recommended_adjustments,
        },
    }


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

        gate_48h = evaluate_48h_post_publish_gate(entry, stats)
        gate_48h["ready_48h"] = bool(elapsed_hours >= 48.0)

        log_entry = {
            **entry,
            **stats,
            "elapsed_hours": round(elapsed_hours, 1),
            "views_per_hour": views_per_hour,
            "result": result,
            "prediction_eval": prediction_eval,
            "gate_48h": gate_48h,
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
    if checked_any:
        try:
            from lol_agent.viral_vault import evaluate_and_promote_vault
            all_logs = _load_performance_log()
            v_sorted = sorted(int(e.get("views") or 0) for e in all_logs if e.get("views") is not None)
            med_v = float(v_sorted[len(v_sorted) // 2]) if v_sorted else 1593.5
            evaluate_and_promote_vault(all_logs, channel_median_views=med_v)
        except Exception:
            pass
    return checked_any


def _parse_iso_utc(ts: Any) -> Optional[Any]:
    """Parsuje timestamp ISO8601 do timezone-aware datetime UTC."""
    from datetime import datetime, timezone
    if not ts or not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def sync_performance_log_with_live_videos(live_videos: list) -> int:
    """Synchronizuje istniejące wpisy performance_log.jsonl z aktualnymi metrykami YouTube.

    Aktualizuje wyświetlenia, lajki, komentarze, tytuł, dostępne metryki retencji,
    przelicza elapsed_hours, views_per_hour, result, prediction_eval i gate_48h,
    zapisując log atomowo (tmp + os.replace).
    """
    from datetime import datetime, timezone

    if not live_videos:
        return 0

    live_by_id: Dict[str, Dict[str, Any]] = {}
    for lv in live_videos:
        if isinstance(lv, dict) and lv.get("video_id"):
            live_by_id[str(lv["video_id"])] = lv
    if not live_by_id:
        return 0

    entries = _load_performance_log()
    if not entries:
        return 0

    # Deduplikacja ewentualnych powtórzonych video_id z zachowaniem kolejności
    deduped_entries: list = []
    idx_by_vid: Dict[str, int] = {}
    collapsed_dups = False
    for raw_entry in entries:
        vid = raw_entry.get("video_id")
        if not vid:
            deduped_entries.append(raw_entry)
            continue
        if vid in idx_by_vid:
            collapsed_dups = True
            prev = deduped_entries[idx_by_vid[vid]]
            merged = {**prev, **{k: v for k, v in raw_entry.items() if v is not None}}
            deduped_entries[idx_by_vid[vid]] = merged
        else:
            idx_by_vid[vid] = len(deduped_entries)
            deduped_entries.append(raw_entry)

    # Mediana wyświetleń kanału obliczona na aktualnych metrykach
    live_view_samples = []
    for e in deduped_entries:
        vid = e.get("video_id")
        lv = live_by_id.get(vid) if vid else None
        if lv and lv.get("views") is not None:
            live_view_samples.append(int(lv["views"]))
        elif e.get("views") is not None:
            live_view_samples.append(int(e["views"]))
    live_view_samples.sort()
    med_v = float(live_view_samples[len(live_view_samples) // 2]) if live_view_samples else 1640.0

    now_utc = datetime.now(timezone.utc)
    analytics_fields = (
        "avg_view_pct",
        "engaged_views",
        "engaged_view_rate_pct",
        "shares",
        "subscribers_gained",
        "hook_retention_pct",
        "swiped_away_pct",
        "completion_rate_pct",
    )
    updated_count = 0

    for entry in deduped_entries:
        vid = entry.get("video_id")
        if not vid or vid not in live_by_id:
            continue
        lv = live_by_id[vid]

        old_views = int(entry.get("views") or 0)
        old_likes = int(entry.get("likes") or 0)
        old_comments = int(entry.get("comments") or 0)
        old_title = entry.get("title")
        old_gate_ready = (entry.get("gate_48h") or {}).get("ready_48h") if isinstance(entry.get("gate_48h"), dict) else None
        old_rwi = (entry.get("gate_48h") or {}).get("rwi_score") if isinstance(entry.get("gate_48h"), dict) else None

        new_views = int(lv["views"]) if lv.get("views") is not None else old_views
        new_likes = int(lv["likes"]) if lv.get("likes") is not None else old_likes
        new_comments = int(lv["comments"]) if lv.get("comments") is not None else old_comments

        entry["views"] = new_views
        entry["likes"] = new_likes
        entry["comments"] = new_comments
        if lv.get("title"):
            entry["title"] = lv["title"]

        analytics_changed = False
        for field in analytics_fields:
            if lv.get(field) is not None and entry.get(field) != lv.get(field):
                entry[field] = lv[field]
                analytics_changed = True

        pub_dt = _parse_iso_utc(entry.get("published_at") or lv.get("published_at"))
        if pub_dt is not None:
            elapsed_hours = round(max(0.0, (now_utc - pub_dt).total_seconds() / 3600.0), 1)
        else:
            elapsed_hours = float(entry.get("elapsed_hours") or 48.0)

        entry["elapsed_hours"] = elapsed_hours
        entry["views_per_hour"] = round(new_views / max(elapsed_hours, 0.1), 1)

        avg_vp = entry.get("avg_view_pct")
        hook_ret = entry.get("hook_retention_pct")
        is_breakout = elapsed_hours <= 18.0 and (entry["views_per_hour"] >= 80.0 or new_views >= 1000)
        is_viral_loop = avg_vp is not None and float(avg_vp) >= 95.0
        is_high_ret = hook_ret is not None and float(hook_ret) >= 75.0 and new_views >= 1000

        if new_views >= VIEWS_SUCCESS_48H or is_breakout or is_viral_loop or is_high_ret:
            result = "SUCCESS"
        elif elapsed_hours >= 48.0 and new_views < VIEWS_FAIL_48H:
            result = "FAIL"
        else:
            result = "AVERAGE"
        entry["result"] = result
        entry["last_result"] = result

        qs = float(entry.get("quality_score") or entry.get("initial_qa_score") or 75.0)
        if qs >= 78.0:
            pred_eval = "ACCURATE_HIGH" if result == "SUCCESS" else ("OVERESTIMATED" if result == "FAIL" else "NEUTRAL")
        else:
            pred_eval = "UNDERESTIMATED" if result == "SUCCESS" else ("ACCURATE_LOW" if result == "FAIL" else "NEUTRAL")
        entry["prediction_eval"] = pred_eval

        stats_for_gate = dict(lv)
        for field in analytics_fields:
            if entry.get(field) is not None and stats_for_gate.get(field) is None:
                stats_for_gate[field] = entry[field]
        stats_for_gate["views"] = new_views
        stats_for_gate["likes"] = new_likes
        stats_for_gate["comments"] = new_comments
        stats_for_gate["elapsed_hours"] = elapsed_hours

        gate_48h = evaluate_48h_post_publish_gate(entry, stats_for_gate, channel_median_views=med_v)
        entry["gate_48h"] = gate_48h
        if elapsed_hours >= 48.0:
            entry["checked"] = True

        changed = (
            new_views != old_views
            or new_likes != old_likes
            or new_comments != old_comments
            or entry.get("title") != old_title
            or analytics_changed
            or gate_48h.get("ready_48h") != old_gate_ready
            or gate_48h.get("rwi_score") != old_rwi
        )
        if changed:
            entry["checked_at"] = now_utc.replace(tzinfo=None).isoformat()
            updated_count += 1

    if updated_count > 0 or collapsed_dups:
        tmp_path = PERFORMANCE_LOG + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for entry in deduped_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.replace(tmp_path, PERFORMANCE_LOG)

        if not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                try:
                    from lol_agent.viral_vault import evaluate_and_promote_vault
                except ImportError:
                    from viral_vault import evaluate_and_promote_vault
                evaluate_and_promote_vault(deduped_entries, channel_median_views=med_v)
            except Exception:
                pass

    return updated_count


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
        if (
            entry.get("video_id")
            and int(entry.get("views") or 0) > 0
            and entry.get("gate_48h") is not None
        ):
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
