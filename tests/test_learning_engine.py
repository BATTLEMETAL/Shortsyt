"""
Unit tests for lol_agent/learning_engine.py.
Verifies robust metric calculations, publication cadence detection, and title fatigue guards.
"""
from datetime import datetime, timezone, timedelta
from lol_agent.learning_engine import (
    _compute_robust_metric,
    _detect_publication_cadence,
    _detect_title_fatigue,
    _analyze_best_pub_hour,
    ZERO_VIEWS_THRESHOLD,
    MIN_SAMPLE_FOR_WEIGHT,
)


def test_compute_robust_metric_empty():
    res = _compute_robust_metric([])
    assert res["count_valid"] == 0
    assert res["median"] == 0.0
    assert res["mean"] == 0.0


def test_compute_robust_metric_filters_zero_and_low_views():
    # Views below threshold (50) must be discarded as non-distributed
    raw_views = [0, 12, 45, 1200, 1500, 1800]
    res = _compute_robust_metric(raw_views)
    assert res["count_valid"] == 3
    assert res["median"] == 1500.0


def test_compute_robust_metric_resists_viral_outlier():
    # 5 standard videos around ~1500 views + 1 massive viral hit at 100,000
    normal_views = [1400, 1500, 1550, 1600, 1650, 100_000]
    res = _compute_robust_metric(normal_views)
    # Median should be ~1575, NOT pulled up by 100,000
    assert 1500 <= res["median"] <= 1600
    # Trimmed mean removes the top outlier, staying realistic
    assert res["trimmed_mean"] < 2500


def test_compute_robust_metric_recency_weighting():
    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_date = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # An old 10,000 view video vs a recent 2,000 view video
    views = [10_000, 2_000]
    dates = [old_date, new_date]
    res = _compute_robust_metric(views, dates)
    # Old video has 0.5 weight, recent has 1.0 weight
    # Weighted mean: (10000*0.5 + 2000*1.0) / 1.5 = 7000 / 1.5 = 4666.67
    assert 4600 <= res["mean"] <= 4700


def test_detect_publication_cadence_insufficient_data():
    res = _detect_publication_cadence([{"published_at": "2026-09-01T10:00:00Z"}])
    assert res["status"] == "insufficient_data"
    assert res["gap_warning"] is False


def test_detect_publication_cadence_healthy_rhythm():
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    # 1 video per day for 5 days
    videos = [
        {"published_at": (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
        for i in range(5)
    ]
    res = _detect_publication_cadence(videos)
    assert res["status"] == "excellent"
    assert res["avg_gap_days"] == 1.0
    assert res["gap_warning"] is False


def test_detect_publication_cadence_warning_on_large_gap():
    base = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    # 4 day gap between publications
    videos = [
        {"published_at": base.strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"published_at": (base + timedelta(days=4.5)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    ]
    res = _detect_publication_cadence(videos)
    assert res["gap_warning"] is True


def test_detect_title_fatigue_no_repetitions():
    videos = [
        {"title": "Master Tier Outplay on Katarina #Shorts", "views": 2000},
        {"title": "Wrong Target Bad Decision 💀 #Shorts", "views": 2200},
        {"title": "Clean Reset in Mid Lane #Shorts", "views": 1800},
    ]
    res = _detect_title_fatigue(videos)
    assert res["fatigue_warning"] is False
    assert res["unique_repeated_count"] == 0


def test_detect_title_fatigue_detects_repeated_prefix():
    videos = [
        {"title": "They Really Thought They Could Win #Shorts 1", "views": 1500},
        {"title": "They Really Thought They Could Win #Shorts 2", "views": 1400},
        {"title": "They Really Thought They Could Escape #Shorts", "views": 1600},
        {"title": "Master Tier Solo Bolo #Shorts", "views": 3000},
        {"title": "Master Tier Solo Bolo Outplay #Shorts", "views": 2800},
    ]
    res = _detect_title_fatigue(videos)
    # Both "they really thought" and "master tier solo" repeat
    assert res["unique_repeated_count"] >= 2
    assert res["fatigue_warning"] is True


def test_analyze_best_pub_hour():
    videos = [
        {"published_at": "2026-09-01T08:30:00Z", "views": 3500},
        {"published_at": "2026-09-02T08:30:00Z", "views": 4000},
        {"published_at": "2026-09-03T18:30:00Z", "views": 2000},
    ]
    res = _analyze_best_pub_hour(videos)
    assert res["best_hour_utc"] == 8
    assert 8 in res["hour_stats"]
    assert res["hour_stats"][8]["median_views"] == 3750


def test_analyze_ab_title_experiments():
    from lol_agent.learning_engine import analyze_ab_title_experiments
    videos = [
        {
            "video_id": "vid_1",
            "title": "They Thought 4v1 Was Safe #Shorts #LeagueOfLegends #LoL",
            "title_variant_b": "Can You Survive This? #Shorts #LeagueOfLegends #LoL",
            "active_variant": "A",
            "views": 2500
        },
        {
            "video_id": "vid_2",
            "title": "Clean 1v1 Solo Bolo #Shorts #LeagueOfLegends #LoL",
            "title_variant_b": "Did Enemy FF After This? #Shorts #LeagueOfLegends #LoL",
            "active_variant": "A",
            "views": 4200
        },
        {
            "video_id": "vid_3",
            "title": "Can You Believe This Outplay? #Shorts #LeagueOfLegends #LoL",
            "views": 1800
        }
    ]
    res = analyze_ab_title_experiments(videos)
    assert res["status"] == "active"
    assert res["tracked_ab_experiments"] == 2
    assert "winning_title_structure" in res
    assert "title_structure_benchmark" in res
