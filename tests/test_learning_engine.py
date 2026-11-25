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


def test_analyze_best_pub_hour_penalizes_morning_flops_and_picks_spaced_evening_slots():
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    tz_pl = ZoneInfo("Europe/Warsaw")
    now_pl = datetime.now(tz_pl).replace(minute=0, second=0, microsecond=0)
    videos = []

    # 5 ostatnich porannych wrzutek o 11:00 PL z niskim zasięgiem (<1000)
    for i, views in enumerate([660, 720, 810, 900, 740], start=2):
        ts = (now_pl - timedelta(days=i)).replace(hour=11).astimezone(timezone.utc)
        videos.append({"published_at": ts.isoformat(), "views": views, "title": f"Morn {i} #Shorts"})

    # 5 popołudniowych o 15:00 PL z wysokimi zasięgami
    for i, views in enumerate([2200, 2400, 2100, 2350, 2500], start=2):
        ts = (now_pl - timedelta(days=i)).replace(hour=15).astimezone(timezone.utc)
        videos.append({"published_at": ts.isoformat(), "views": views, "title": f"Aft {i} #Shorts"})

    # 5 wieczornych o 21:30 PL (w tym viral >4k)
    for i, views in enumerate([2600, 2900, 6100, 2450, 2700], start=2):
        ts = (now_pl - timedelta(days=i)).replace(hour=21, minute=30).astimezone(timezone.utc)
        videos.append({"published_at": ts.isoformat(), "views": views, "title": f"Eve {i} #Shorts"})

    res = _analyze_best_pub_hour(videos)
    weights = res["hour_weights_cet"]
    assert weights[15] > weights[11]
    assert weights[21] > weights[11]
    assert 11 in res["avoid_hours_cet"]
    assert res["recommended_slots_source"] == "empirical_bayes_60d"
    slots = res["recommended_slots_cet"]
    assert len(slots) == 2
    h1 = int(slots[0].split(":")[0])
    h2 = int(slots[1].split(":")[0])
    assert h2 - h1 >= 4
    assert h1 >= 14 and h2 >= 20


def test_calibrate_quality_gate_reads_initial_qa_score_and_evr_corr():
    from lol_agent.learning_engine import calibrate_quality_gate
    from lol_agent.lol_metadata_generator import sanitize_pinned_comment

    videos = [
        {
            "video_id": f"qa_{i}",
            "initial_qa_score": 60 + i * 3,
            "views": 900 if i < 5 else 2800 + i * 100,
            "avg_view_pct": 80.0 if i < 5 else 108.0,
            "engaged_view_rate_pct": 25.0 + i * 2.5,
        }
        for i in range(10)
    ]
    cal = calibrate_quality_gate(videos, current_threshold=70.0)
    assert cal["sample_size"] == 10
    assert cal["reliable"] is True
    assert cal["correlation_qs_evr"] is not None and cal["correlation_qs_evr"] > 0.8

    assert sanitize_pinned_comment("Nice play! Tell us what you think! 👇", {}) == ""
    assert sanitize_pinned_comment("X" * 145, {}) == ""
    assert "daggers" in sanitize_pinned_comment("Did they walk right onto Katarina daggers here? 👇", {})


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


def test_legacy_pentakill_protection_and_viral_blueprint(tmp_path, monkeypatch):
    """Verify legacy pentakills before 2026-11-20 do not demote pentakill weight below 1.0, and check YT blueprint."""
    from lol_agent.learning_engine import run_channel_learning_cycle
    from lol_agent.lol_yt_pattern_miner import _parse_iso8601_duration_sec, _derive_viral_edit_blueprint

    # Synthetic channel: high solo_bolo views + 4 pre-Etap-16 low-view pentakills
    videos = [
        {"video_id": f"sb_{i}", "title": "Clean 1v1 Solo Bolo", "action_type": "solo_bolo", "views": 3000, "published_at": "2026-11-10T10:00:00Z", "is_48h_verified": True}
        for i in range(6)
    ] + [
        {"video_id": f"pk_{i}", "title": "Katarina Pentakill", "action_type": "pentakill", "views": 1100, "published_at": "2026-11-05T10:00:00Z", "is_48h_verified": True}
        for i in range(4)
    ]

    monkeypatch.setattr("lol_agent.learning_engine.LEARNING_DIR", tmp_path)
    monkeypatch.setattr("lol_agent.learning_engine.DIRECTIVE_FILE", tmp_path / "learning_directive.json")
    monkeypatch.setattr("lol_agent.learning_engine.TUNING_FILE", tmp_path / "tuning_config.json")
    monkeypatch.setattr("lol_agent.learning_engine.PUB_LOG_FILE", tmp_path / "published_videos.jsonl")
    monkeypatch.setattr("lol_agent.api.youtube_uploader.get_channel_videos_and_performance", lambda max_results=250, force_refresh=False: {"published": videos})
    monkeypatch.setattr("lol_agent.api.youtube_analytics.fetch_channel_retention_overview", lambda max_videos=20: {"videos": []})
    monkeypatch.setattr("lol_agent.api.youtube_analytics.fetch_bulk_video_analytics", lambda force_refresh=False: {})
    monkeypatch.setattr("lol_agent.api.youtube_analytics.fetch_channel_audience_insights", lambda force_refresh=False: {})
    monkeypatch.setattr("lol_agent.lol_performance_tracker.reconcile_and_verify_published_videos", lambda: None)
    monkeypatch.setattr("lol_agent.lol_performance_tracker.run_pending_checks", lambda: False)

    out = run_channel_learning_cycle(force_refresh=False)
    directive = out["directive"]
    assert directive["action_weights"]["pentakill"] >= 1.0
    assert directive["action_stats"]["pentakill"]["effective_weight"] >= 1.0
    assert directive["action_stats"]["pentakill"]["legacy_protected"] is True
    assert directive["action_stats"]["pentakill"]["weight"] < 1.0
    assert directive["action_stats"]["pentakill"]["legacy_count"] == 4
    assert directive["action_stats"]["pentakill"]["post_etap16_count"] == 0
    assert directive["evaluator_config"]["base_kill_weights"]["PENTAKILL"] >= 80.0

    assert _parse_iso8601_duration_sec("PT14S") == 14.0
    assert _parse_iso8601_duration_sec("PT1M5S") == 65.0

    bp_penta = _derive_viral_edit_blueprint("POV: Five Enemies Reset In 3 Seconds 💀 #shorts", 14.0, 2500000, 5.2, 0.14)
    assert bp_penta["hook_type"] == "POV"
    assert bp_penta["pacing_bucket"] == "balanced_13_20s"
    assert bp_penta["recommended_drop_anchor"] == "first_kill_engage"

    bp_solo = _derive_viral_edit_blueprint("How Did They Lose This 1v1? 💀", 11.0, 400000, 4.1, 0.09)
    assert bp_solo["hook_type"] == "QUESTION"
    assert bp_solo["pacing_bucket"] == "ultra_fast_<=12s"
    assert bp_solo["recommended_drop_anchor"] == "climax_final_kill"


def test_analyze_best_pub_hour_per_weekday_adapts_by_day():
    """Harmonogram 7-dniowy dopasowuje sloty indywidualnie pod rozkład Wtorku vs Piątku."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    tz_pl = ZoneInfo("Europe/Warsaw")
    # Wtorki (2026-11-03, 10, 17) mocne o 09:00 i 18:00, słabe o 21:30; Piątki (2026-11-06, 13, 20) mocne o 10:00 i 21:30, słabe o 18:00
    videos = []
    for day_str in ("2026-11-03", "2026-11-10", "2026-11-17"):
        base = datetime.fromisoformat(f"{day_str}T00:00:00").replace(tzinfo=tz_pl)
        for h, vw in ((9, 3600), (14, 1400), (18, 3900), (21, 550)):
            videos.append({"published_at": base.replace(hour=h).astimezone(timezone.utc).isoformat(), "views": vw, "title": "Tue #Shorts"})
    for day_str in ("2026-11-06", "2026-11-13", "2026-11-20"):
        base = datetime.fromisoformat(f"{day_str}T00:00:00").replace(tzinfo=tz_pl)
        for h, vw in ((10, 3800), (13, 1300), (18, 600), (21, 4600)):
            videos.append({"published_at": base.replace(hour=h, minute=30 if h == 21 else 0).astimezone(timezone.utc).isoformat(), "views": vw, "title": "Fri #Shorts"})

    res = _analyze_best_pub_hour(videos, include_omnichannel=False)
    weekly = res["recommended_slots_by_weekday_cet"]
    assert len(weekly) == 7
    assert all(len(weekly[str(d)]) == 2 for d in range(7))
    tue_slots = weekly["1"]
    fri_slots = weekly["4"]
    assert tue_slots != fri_slots
    tue_h1, tue_h2 = int(tue_slots[0][:2]), int(tue_slots[1][:2])
    fri_h1, fri_h2 = int(fri_slots[0][:2]), int(fri_slots[1][:2])
    assert tue_h2 - tue_h1 >= 5 and fri_h2 - fri_h1 >= 5
    assert tue_h2 in (18, 19)
    assert fri_h2 in (21, 22)

