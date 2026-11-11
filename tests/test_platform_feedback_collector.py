"""
Unit tests for lol_agent/platform_feedback_collector.py.
Verifies metrics ingestion, schema updates, and execution flow with mocked APIs.
"""

import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lol_agent.platform_feedback_collector import (
    ingest_youtube_metric,
    ingest_instagram_metric,
    ingest_facebook_metric,
    collect_all_platform_metrics,
)


class TestMetricIngestion:
    def test_ingest_youtube_metric(self, tmp_path, monkeypatch):
        fake_states_dir = tmp_path / "learning_states"
        monkeypatch.setattr("lol_agent.platform_feedback_collector.LEARNING_STATES_DIR", fake_states_dir)

        metric = {
            "views": 2500,
            "likes": 180,
            "title": "Insane Katarina Pentakill",
            "avg_view_duration": 18.5
        }
        ingest_youtube_metric(metric, action_type="pentakill")

        target = fake_states_dir / "learning_youtube.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["videos_analysed"] == 1
        assert len(data["title_patterns"]["top_performers"]) == 1
        assert data["title_patterns"]["top_performers"][0]["views"] == 2500
        # Check action weight boost for viral video
        assert data["action_type_weights"]["pentakill"] > 1.0

    def test_ingest_instagram_metric(self, tmp_path, monkeypatch):
        fake_states_dir = tmp_path / "learning_states"
        monkeypatch.setattr("lol_agent.platform_feedback_collector.LEARNING_STATES_DIR", fake_states_dir)

        metric = {
            "media_id": "18000123456",
            "reach": 3400,
            "likes": 210,
            "total_interactions": 240
        }
        ingest_instagram_metric(metric, action_type="outplay")

        target = fake_states_dir / "learning_instagram.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["videos_analysed"] == 1
        assert len(data["metrics_collected"]["entries"]) == 1
        assert data["metrics_collected"]["entries"][0]["reach"] == 3400

    def test_ingest_facebook_metric(self, tmp_path, monkeypatch):
        fake_states_dir = tmp_path / "learning_states"
        monkeypatch.setattr("lol_agent.platform_feedback_collector.LEARNING_STATES_DIR", fake_states_dir)

        metric = {
            "video_id": "999888777",
            "views": 1500,
            "reactions": 85,
            "comments": 22,
            "shares": 10
        }
        ingest_facebook_metric(metric, action_type="clutch")

        target = fake_states_dir / "learning_facebook.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["videos_analysed"] == 1
        assert len(data["metrics_collected"]["entries"]) == 1
        assert data["metrics_collected"]["entries"][0]["reactions"] == 85


class TestCollectAllPlatformMetrics:
    def test_empty_log_returns_cleanly(self, tmp_path, monkeypatch):
        fake_log = tmp_path / "empty_log.jsonl"
        monkeypatch.setattr("lol_agent.platform_feedback_collector.PUB_LOG_FILE", fake_log)

        res = collect_all_platform_metrics()
        assert res["status"] == "no_pub_log" or res["analysed"] == 0

    @patch("lol_agent.platform_feedback_collector.fetch_youtube_video_metrics")
    @patch("lol_agent.platform_feedback_collector.fetch_instagram_reel_metrics")
    @patch("lol_agent.platform_feedback_collector.fetch_facebook_reel_metrics")
    @patch("lol_agent.platform_feedback_collector.fetch_tiktok_metrics")
    def test_collect_all_platforms_flow(
        self, mock_tt, mock_fb, mock_ig, mock_yt, tmp_path, monkeypatch
    ):
        fake_states_dir = tmp_path / "learning_states"
        fake_log = tmp_path / "published_videos.jsonl"
        monkeypatch.setattr("lol_agent.platform_feedback_collector.LEARNING_STATES_DIR", fake_states_dir)
        monkeypatch.setattr("lol_agent.platform_feedback_collector.PUB_LOG_FILE", fake_log)

        entry = {
            "timestamp": "2026-10-22T08:00:00",
            "video_id": "yt_123",
            "instagram_media_id": "ig_456",
            "facebook_video_id": "fb_789",
            "tiktok_publish_id": "tt_000",
            "action_type": "pentakill"
        }
        fake_log.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        mock_yt.return_value = {"views": 1000, "likes": 50, "title": "YT Video"}
        mock_ig.return_value = {"reach": 500, "likes": 30}
        mock_fb.return_value = {"views": 800, "reactions": 40}
        mock_tt.return_value = {"status": "PUBLISHED"}

        report = collect_all_platform_metrics(max_videos=5)
        assert report["total_checked"] == 1
        assert report["youtube_updated"] == 1
        assert report["instagram_updated"] == 1
        assert report["facebook_updated"] == 1
        assert report["tiktok_queried"] == 1
