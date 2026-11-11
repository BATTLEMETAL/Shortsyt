"""
Unit testy dla modułu publikacji TikTok i multi-platform
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lol_agent.tiktok_publisher import (
    load_tiktok_token, refresh_tiktok_token, get_tiktok_token_status,
    upload_tiktok_short
)
from lol_agent.multi_publisher import publish_multi_platform


def test_load_tiktok_token_missing_file(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher.TIKTOK_TOKEN_PATH", non_existent)
    assert load_tiktok_token() is None


def test_get_tiktok_token_status_disconnected(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher.TIKTOK_TOKEN_PATH", non_existent)
    status = get_tiktok_token_status()
    assert status["connected"] is False
    assert status["valid"] is False


def test_upload_tiktok_missing_file(tmp_path, monkeypatch):
    token_file = tmp_path / "fake_token.json"
    token_file.write_text(json.dumps({"access_token": "fake_act", "expires_at": 9999999999}))
    monkeypatch.setattr("lol_agent.tiktok_publisher.TIKTOK_TOKEN_PATH", token_file)

    res = upload_tiktok_short(
        video_path=str(tmp_path / "missing_video.mp4"),
        title="Test Title"
    )
    assert res["success"] is False
    assert "nie istnieje" in res["error"]


def test_upload_tiktok_no_token(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher.TIKTOK_TOKEN_PATH", non_existent)

    fake_video = tmp_path / "test_video.mp4"
    fake_video.write_bytes(b"dummy video content")

    res = upload_tiktok_short(
        video_path=str(fake_video),
        title="Test Title"
    )
    assert res["success"] is False
    assert "Brak ważnego tokenu" in res["error"]


def test_refresh_tiktok_token_missing_refresh_key():
    token_data = {"access_token": "dummy"}
    assert refresh_tiktok_token(token_data) is None


def test_multi_publisher_handles_failures_gracefully(tmp_path, monkeypatch):
    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    # Mock obu uploadów na błędy
    with patch("lol_agent.multi_publisher.upload_lol_short", side_effect=RuntimeError("YT Auth Error")), \
         patch("lol_agent.multi_publisher.upload_tiktok_short", return_value={"success": False, "error": "No TikTok Token"}):

        results = publish_multi_platform(
            video_path=str(fake_video),
            title="Epic Katarina Outplay",
            platforms=["youtube", "tiktok"]
        )

        assert "youtube" in results
        assert "tiktok" in results
        assert results["youtube"]["success"] is False
        assert "YT Auth Error" in results["youtube"]["error"]
        assert results["tiktok"]["success"] is False


def test_multi_publisher_partial_success(tmp_path):
    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    with patch("lol_agent.multi_publisher.upload_lol_short", return_value={"video_id": "yt_123", "url": "https://yt.be/yt_123", "title": "Epic"}), \
         patch("lol_agent.multi_publisher.upload_tiktok_short", return_value={"success": False, "error": "TT Quota"}):

        results = publish_multi_platform(
            video_path=str(fake_video),
            title="Epic Katarina Outplay",
            platforms=["youtube", "tiktok"]
        )

        assert results["youtube"]["success"] is True
        assert results["youtube"]["video_id"] == "yt_123"
        assert results["tiktok"]["success"] is False


def test_upload_tiktok_scheduling(tmp_path):
    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    future_time = "2026-11-20T10:00:00Z"
    with patch("lol_agent.scheduled_queue.queue_scheduled_post") as mock_queue:
        res = upload_tiktok_short(
            video_path=str(fake_video),
            title="Future TikTok Video",
            publish_at=future_time
        )
        assert res["success"] is True
        assert res["is_scheduled"] is True
        assert res["platform"] == "tiktok"
        mock_queue.assert_called_once()


def test_scheduled_queue_flushes_tiktok(tmp_path, monkeypatch):
    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)

    fake_video = tmp_path / "scheduled_tt.mp4"
    fake_video.write_bytes(b"dummy content")

    from lol_agent.scheduled_queue import queue_scheduled_post, check_and_flush_scheduled_posts

    # Dodaj pozycję z przeszłą datą
    queue_scheduled_post(
        platform="tiktok",
        video_path=str(fake_video),
        caption="Scheduled Outplay",
        publish_at="2020-01-01T00:00:00Z"
    )

    with patch("lol_agent.tiktok_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "v_test_123"}):
        count = check_and_flush_scheduled_posts()
        assert count == 1

    # Sprawdź czy status w pliku to 'published'
    items = json.loads(queue_file.read_text(encoding="utf-8"))
    assert items[0]["status"] == "published"
    assert items[0]["result"]["publish_id"] == "v_test_123"

