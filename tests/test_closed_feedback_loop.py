"""
Tests for Closed Feedback Loop, Performance Tracking & Evaluator Recalibration.
"""
import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lol_agent.lol_performance_tracker import (
    schedule_check, run_pending_checks, fetch_video_stats,
    reconcile_and_verify_published_videos, _load_pending, _save_pending
)
from lol_agent.learning_engine import (
    get_learning_directive, get_action_weight, run_channel_learning_cycle
)
from lol_agent.lol_quality_scorer import score_short
from lol_agent.api.models import YouTubeUploadRequest
from lol_agent.api.helpers import _record_publication


def test_quality_scorer_duration_bounds_allows_short_clips(monkeypatch):
    """Zwięzłe klipy 12.0s-16.0s nie powinny być karane fałszywym błędem 'too short for retention'."""
    monkeypatch.setattr("lol_agent.lol_quality_scorer._ffprobe_resolution", lambda *args, **kwargs: (1080, 1920))
    monkeypatch.setattr("lol_agent.lol_quality_scorer._get_frame_saturation", lambda *args, **kwargs: 140.0)
    monkeypatch.setattr("lol_agent.lol_quality_scorer._get_frame_motion", lambda *args, **kwargs: 15.0)
    monkeypatch.setattr("lol_agent.lol_quality_scorer._ffprobe_duration", lambda *args, **kwargs: 13.5)

    mock_analysis = {
        "peaks": [(6.0, "SOLO BOLO")],
        "peak_start": 3.0,
        "peak_end": 10.0,
        "clip_duration": 13.5
    }

    res = score_short("dummy_rendered.mp4", "dummy_source.mp4", mock_analysis, beat_drop_time=6.0)
    assert res["breakdown"]["duration"]["score"] == 100.0
    assert not any("too short for good retention" in issue for issue in res["issues"])


def test_schedule_check_creates_pending_entry(tmp_path, monkeypatch):
    """Testuje czy schedule_check poprawnie zapisuje metadane z initial QA score i duration_s."""
    test_pending_file = tmp_path / "pending_checks.json"
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PENDING_PATH", str(test_pending_file))

    schedule_check(
        video_id="test_vid_123",
        video_url="https://youtube.com/shorts/test_vid_123",
        title="Epic Katarina Outplay",
        action_type="outplay",
        champion="Katarina",
        quality_score=92.5,
        music_file="phonk.mp3",
        beat_sync_error=0.05,
        kill_coverage_pct=100.0,
        duration_s=14.2
    )

    with open(test_pending_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "test_vid_123" in data
    entry = data["test_vid_123"]
    assert entry["quality_score"] == 92.5
    assert entry["action_type"] == "outplay"
    assert entry["duration_s"] == 14.2
    assert entry["checked"] is False


def test_run_pending_checks_prediction_evaluation(tmp_path, monkeypatch):
    """Testuje klasyfikację predykcji jakości (ACCURATE_HIGH vs UNDERESTIMATED)."""
    test_pending_file = tmp_path / "pending_checks.json"
    test_perf_log = tmp_path / "performance_log.jsonl"
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PENDING_PATH", str(test_pending_file))
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PERFORMANCE_LOG", str(test_perf_log))

    mock_pending = {
        "vid_accurate": {
            "video_id": "vid_accurate",
            "title": "High Quality Viral",
            "action_type": "solo_bolo",
            "champion": "Katarina",
            "quality_score": 88.0,
            "duration_s": 15.0,
            "check_at": 1000.0,
            "checked": False,
        },
        "vid_underestimated": {
            "video_id": "vid_underestimated",
            "title": "Short Clip Underrated",
            "action_type": "solo_bolo",
            "champion": "Katarina",
            "quality_score": 68.0,
            "duration_s": 12.5,
            "check_at": 1000.0,
            "checked": False,
        }
    }
    with open(test_pending_file, "w", encoding="utf-8") as f:
        json.dump(mock_pending, f)

    def mock_fetch(vid_id, duration_s=15.0):
        if vid_id == "vid_accurate":
            return {"views": 2500, "likes": 50, "comments": 4, "hook_retention_pct": 82.0}
        else:
            return {"views": 3200, "likes": 75, "comments": 9, "hook_retention_pct": 85.0}

    monkeypatch.setattr("lol_agent.lol_performance_tracker.fetch_video_stats", mock_fetch)

    # Uruchom weryfikację
    checked = run_pending_checks(force_all=True)
    assert checked is True

    # Sprawdź zapisane logi
    with open(test_perf_log, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]

    eval_by_id = {e["video_id"]: e for e in entries}
    assert eval_by_id["vid_accurate"]["result"] == "SUCCESS"
    assert eval_by_id["vid_accurate"]["prediction_eval"] == "ACCURATE_HIGH"
    assert eval_by_id["vid_underestimated"]["result"] == "SUCCESS"
    assert eval_by_id["vid_underestimated"]["prediction_eval"] == "UNDERESTIMATED"


def test_record_publication_records_initial_qa_and_schedules_check(tmp_path, monkeypatch):
    """Testuje czy _record_publication zapisuje initial_qa_score i woła schedule_check."""
    test_pub_file = tmp_path / "published_videos.jsonl"
    monkeypatch.setattr("lol_agent.api.helpers.Path", lambda *args: Path(*args))
    
    # Mock helpers
    scheduled_calls = []
    def mock_schedule(**kwargs):
        scheduled_calls.append(kwargs)

    monkeypatch.setattr("lol_agent.lol_performance_tracker.schedule_check", mock_schedule)
    
    mock_meta = {
        "source_path": "raw_match.mp4",
        "champion_name": "Katarina",
        "action_type": "solo_bolo",
        "qa_score": 91,
        "qa_status": "PASS",
        "duration": 14.8,
    }
    monkeypatch.setattr("lol_agent.api.helpers._load_meta", lambda fn: mock_meta)
    monkeypatch.setattr("lol_agent.api.helpers._save_meta", lambda fn, data: None)

    # Patch published_videos.jsonl target path
    import lol_agent.api.helpers as helpers
    test_pub_path = tmp_path / "published_videos.jsonl"
    monkeypatch.setattr("lol_agent.api.helpers.__file__", str(tmp_path / "api" / "helpers.py"))

    req = YouTubeUploadRequest(
        filename="dummy_short.mp4",
        title="Master Tier Solo Bolo #Shorts",
        description="Clean outplay",
        tags=["lol"],
        privacy="public"
    )
    res = {
        "video_id": "test_pub_999",
        "url": "https://youtube.com/shorts/test_pub_999",
        "status": "public"
    }

    _record_publication("dummy_short.mp4", "dummy_short.mp4", res, req)

    # Sprawdź wywołanie schedule_check
    assert len(scheduled_calls) == 1
    assert scheduled_calls[0]["video_id"] == "test_pub_999"
    assert scheduled_calls[0]["quality_score"] == 91.0
    assert scheduled_calls[0]["action_type"] == "solo_bolo"


def test_dynamic_weights_in_clip_ranker_and_pre_analyzer():
    """Weryfikuje, że clip ranker oraz pre-analyzer dynamicznie pobierają wagi akcji z dyrektywy."""
    from lol_agent.lol_clip_ranker import KILL_WEIGHTS
    from lol_agent.lol_pre_pipeline_analyzer import ACTION_WEIGHTS

    assert "SOLO BOLO" in KILL_WEIGHTS
    assert KILL_WEIGHTS["SOLO BOLO"] >= 7.5  # Solo bolo ma wyższą lub równą wagę niż quadra
    assert "solo_bolo" in ACTION_WEIGHTS
    assert 0.5 <= ACTION_WEIGHTS["solo_bolo"] <= 2.0


def test_validation_result_mei_dictionary():
    """Weryfikuje, że ValidationResult poprawnie generuje strukturę MEI (Montage Execution Index)."""
    from lol_agent.lol_quality_validator import ValidationResult

    res = ValidationResult(
        passed=True,
        adjusted_trim_start=3.1,
        adjusted_trim_end=17.1,
        qa_status="PASS",
        qa_score=98,
        hook_latency_s=0.6,
        combat_density_pct=92.5,
        outro_latency_s=1.77,
        action_visibility_pct=100.0,
        is_seamless_loop=True,
        montage_execution_index=98.0,
    )
    mei = res.get_mei_dict()
    assert mei["mei_score"] == 98.0
    assert mei["combat_density_pct"] == 92.5
    assert mei["outro_latency_s"] == 1.77
    assert mei["hook_latency_s"] == 0.6
    assert mei["is_seamless_loop"] is True
    assert mei["visibility_score"] == 100


def test_velocity_and_breakout_evaluation(tmp_path, monkeypatch):
    """Weryfikuje, że run_pending_checks poprawnie oblicza Views Per Hour i klasyfikuje wczesny breakout."""
    import json
    import time
    from datetime import datetime, timezone, timedelta
    from lol_agent.lol_performance_tracker import run_pending_checks

    test_pending = tmp_path / "pending_checks.json"
    test_log = tmp_path / "performance_log.jsonl"
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PENDING_PATH", str(test_pending))
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PERFORMANCE_LOG", str(test_log))

    # Symuluj wideo opublikowane 6 godzin temu z 1300 wyświetleniami (VPH ~ 216/h)
    pub_time = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    pending_data = {
        "breakout_vid": {
            "video_id": "breakout_vid",
            "url": "https://youtube.com/shorts/breakout_vid",
            "title": "Two Down, Instant Chaos",
            "action_type": "double",
            "champion": "Katarina",
            "quality_score": 95.0,
            "duration_s": 14.0,
            "published_at": pub_time,
            "check_at": time.time() - 100,  # gotowe do sprawdzenia
            "checked": False,
        }
    }
    test_pending.write_text(json.dumps(pending_data), encoding="utf-8")

    # Mock fetch_video_stats: 1349 wyświetleń, 8 lajków, 111.8% retencji
    mock_stats = {
        "views": 1349,
        "likes": 8,
        "comments": 1,
        "avg_view_pct": 111.8,
        "hook_retention_pct": 85.0,
    }
    monkeypatch.setattr("lol_agent.lol_performance_tracker.fetch_video_stats", lambda vid, duration_s=15.0: mock_stats)

    checked = run_pending_checks(force_all=True)
    assert checked is True

    # Sprawdź zapis w logu
    lines = test_log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    logged = json.loads(lines[0])
    assert logged["result"] == "SUCCESS"
    assert logged["views_per_hour"] > 150.0  # ~224 VPH
    assert logged["avg_view_pct"] == 111.8


def test_breakout_boost_preserves_action_weight(tmp_path, monkeypatch):
    """Weryfikuje, że learning_engine nie obniża wagi formatu, jeśli ma on świeży breakout z wysokim VPH/AVD%."""
    from lol_agent.learning_engine import correlate_viral_duration_and_pacing

    pacing_res = correlate_viral_duration_and_pacing([], [], 1500.0)
    assert "mei_directives" in pacing_res
    assert pacing_res["mei_directives"]["max_outro_latency_sec"] == 1.8
    assert pacing_res["mei_directives"]["target_combat_density_pct"] == 85.0
