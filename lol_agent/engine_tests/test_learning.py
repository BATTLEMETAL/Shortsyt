"""Silnik uczenia: wnioski muszą wynikać z danych, nie z przypadku. Część testów liczy na danych z learning_directive.json."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import learning_engine as LE

def test_weight_follows_the_ratio():
    assert LE.shrunk_weight(0.95, 26) < 1.0          # triple: stosunek 0.95 → waga poniżej 1 (dawniej 1.34)
    assert LE.shrunk_weight(0.86, 20) < 1.0          # double (dawniej 1.25)
    assert 1.0 < LE.shrunk_weight(1.29, 9) < 1.29    # solo bolo: powyżej 1, ale 9 filmów nie daje pełnych 1.29
    assert abs(LE.shrunk_weight(1.5, 0) - 1.0) < 1e-9

def test_bootstrap_interval_is_wide_for_small_groups():
    lo, hi = LE.bootstrap_median_ratio_ci([2120, 1472, 2066, 1641, 2978, 3900, 2500, 1900, 3800], 1641.0)
    assert lo < hi and hi - lo > 0.3                 # 9 filmów: przedział szeroki, wniosek tylko wstępny

def test_retention_median_not_mean():
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_retention.json"), encoding="utf-8"))
    r = LE.summarize_retention(d["retention_analysis"]["videos"])
    assert r["avg_view_pct"]["median"] < 110 < d["retention_analysis"]["channel_avg_view_pct"]   # 122.9 % to średnia z odstającym 474.7 %
    assert 474.7 in r["avg_view_pct"]["outliers"]
    assert r["swiped_away_pct"]["median"] > d["retention_analysis"]["channel_avg_swiped_away_pct"]  # zera i film bez wyświetleń zaniżały

def test_tuning_respects_the_user():
    cur = {"pacing": "balanced", "zoomAggression": 1.2}
    prop = {"pacing": "cinematic", "zoomAggression": 1.1, "slowmoDuration": 2.0}
    assert LE.plan_tuning_update(cur, prop, clear_winner=False, locked=set()) == {}
    assert LE.plan_tuning_update(cur, prop, True, {"zoomAggression"}) == {"pacing": "cinematic", "slowmoDuration": 2.0}
    assert LE.plan_tuning_update(prop, prop, True, set()) == {}

def test_recency_weight_reads_datetimes():
    from datetime import datetime, timezone, timedelta
    old = datetime.now(timezone.utc) - timedelta(days=200)
    new = datetime.now(timezone.utc) - timedelta(days=2)
    m = LE._compute_robust_metric([1000, 3000], [old, new])
    assert abs(m["mean"] - (1000 * 0.5 + 3000 * 1.0) / 1.5) < 1.0   # dawniej wagi zawsze 1.0 → średnia 2000

def test_best_hour_needs_samples():
    vids = [{"views": 3000, "published_at": "2026-10-01T08:00:00Z"}, {"views": 3100, "published_at": "2026-10-02T08:00:00Z"}]
    vids += [{"views": 1500 + i, "published_at": f"2026-10-{3 + i:02d}T17:00:00Z"} for i in range(8)]
    r = LE._analyze_best_pub_hour(vids)
    assert r["best_hour_utc"] != 8                    # dwa filmy o 8:00 nie robią "najlepszej godziny"

def test_duration_buckets_use_all_videos():
    vids = [{"views": 2000 + i, "duration_s": 15.0} for i in range(10)] + [{"views": 2600, "duration_s": 21.0} for _ in range(3)]
    r = LE.correlate_viral_duration_and_pacing([v for v in vids if v["views"] > 2500], vids, 2005.0)
    assert r["bucket_stats"]["balanced_14_17s"]["count"] == 10 and r["bucket_stats"]["cinematic_18_25s"]["reliable"] is False
    assert r["best_bucket"] == "balanced_14_17s" and r["clear_winner"] is False
