"""
Unit testy dla modułu publikacji Instagram Reels i multi-platform
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lol_agent.instagram_publisher import (
    load_instagram_token,
    get_instagram_token_status,
    upload_instagram_reel
)
from lol_agent.multi_publisher import publish_multi_platform


def test_load_instagram_token_missing_file(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.instagram_publisher.INSTAGRAM_TOKEN_PATH", non_existent)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)
    assert load_instagram_token() is None


def test_load_instagram_token_from_file(tmp_path, monkeypatch):
    token_file = tmp_path / "ig_token.json"
    token_file.write_text(json.dumps({
        "access_token": "test_token_123",
        "instagram_account_id": "999888777",
        "page_id": "111222",
        "username": "testuser"
    }), encoding="utf-8")
    monkeypatch.setattr("lol_agent.instagram_publisher.INSTAGRAM_TOKEN_PATH", token_file)

    loaded = load_instagram_token()
    assert loaded is not None
    assert loaded["access_token"] == "test_token_123"
    assert loaded["instagram_account_id"] == "999888777"
    assert loaded["username"] == "testuser"


def test_get_instagram_token_status_disconnected(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.instagram_publisher.INSTAGRAM_TOKEN_PATH", non_existent)
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_ACCOUNT_ID", raising=False)

    status = get_instagram_token_status()
    assert status["connected"] is False
    assert status["valid"] is False


def test_get_instagram_token_status_success(monkeypatch):
    fake_token = {
        "access_token": "valid_token",
        "instagram_account_id": "123456",
        "username": "tester",
        "page_id": "789"
    }
    monkeypatch.setattr("lol_agent.instagram_publisher.load_instagram_token", lambda: fake_token)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"username": "tester", "id": "123456"}

    with patch("requests.get", return_value=mock_resp):
        status = get_instagram_token_status()
        assert status["connected"] is True
        assert status["valid"] is True
        assert status["username"] == "tester"


def test_upload_instagram_missing_file(tmp_path, monkeypatch):
    fake_token = {
        "access_token": "valid_token",
        "instagram_account_id": "123456",
        "username": "tester",
        "page_id": "789"
    }
    monkeypatch.setattr("lol_agent.instagram_publisher.load_instagram_token", lambda: fake_token)

    res = upload_instagram_reel(
        video_path=str(tmp_path / "non_existent.mp4"),
        caption="Epic Reel"
    )
    assert res["success"] is False
    assert "nie istnieje" in res["error"]


def test_upload_instagram_no_token(tmp_path, monkeypatch):
    monkeypatch.setattr("lol_agent.instagram_publisher.load_instagram_token", lambda: None)
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"dummy video data")

    res = upload_instagram_reel(
        video_path=str(fake_video),
        caption="Epic Reel"
    )
    assert res["success"] is False
    assert "Brak konfiguracji" in res["error"]


def test_upload_instagram_success_flow(tmp_path, monkeypatch):
    fake_video = tmp_path / "reel.mp4"
    fake_video.write_bytes(b"video data content" * 100)

    fake_token = {
        "access_token": "valid_token_xyz",
        "instagram_account_id": "999888",
        "username": "lol_shorts",
        "page_id": "777"
    }
    monkeypatch.setattr("lol_agent.instagram_publisher.load_instagram_token", lambda: fake_token)

    # 1. Container response
    container_resp = MagicMock()
    container_resp.status_code = 200
    container_resp.json.return_value = {
        "id": "container_123",
        "uri": "https://rupload.facebook.com/ig-api-upload/v19.0/container_123"
    }

    # 2. Binary upload response
    upload_resp = MagicMock()
    upload_resp.status_code = 200
    upload_resp.text = '{"success": true}'

    # 3. Status check response
    status_resp = MagicMock()
    status_resp.status_code = 200
    status_resp.json.return_value = {"status_code": "FINISHED", "id": "container_123"}

    # 4. Publish response
    publish_resp = MagicMock()
    publish_resp.status_code = 200
    publish_resp.json.return_value = {"id": "media_999"}

    # 5. Permalink response
    media_resp = MagicMock()
    media_resp.status_code = 200
    media_resp.json.return_value = {"permalink": "https://www.instagram.com/reel/Cxxxxxx/"}

    def mock_post(url, *args, **kwargs):
        if "media_publish" in url:
            return publish_resp
        elif "rupload.facebook.com" in url:
            return upload_resp
        else:
            return container_resp

    def mock_get(url, *args, **kwargs):
        if "container_123" in url:
            return status_resp
        elif "media_999" in url:
            return media_resp
        return MagicMock(status_code=200, json=lambda: {})

    with patch("requests.post", side_effect=mock_post), \
         patch("requests.get", side_effect=mock_get):

        res = upload_instagram_reel(
            video_path=str(fake_video),
            caption="Test #lol #gaming"
        )

        assert res["success"] is True
        assert res["media_id"] == "media_999"
        assert res["permalink"] == "https://www.instagram.com/reel/Cxxxxxx/"


def test_upload_instagram_processing_failed(tmp_path, monkeypatch):
    fake_video = tmp_path / "reel.mp4"
    fake_video.write_bytes(b"dummy video data")

    fake_token = {
        "access_token": "valid_token",
        "instagram_account_id": "999888",
        "username": "lol_shorts",
        "page_id": "777"
    }
    monkeypatch.setattr("lol_agent.instagram_publisher.load_instagram_token", lambda: fake_token)

    container_resp = MagicMock(status_code=200, json=lambda: {"id": "c_fail", "uri": "https://rupload.test"})
    upload_resp = MagicMock(status_code=200, text="ok")
    status_resp = MagicMock(status_code=200, json=lambda: {"status_code": "ERROR", "status": "Transcoding failed"})

    with patch("requests.post", side_effect=[container_resp, upload_resp]), \
         patch("requests.get", return_value=status_resp):

        res = upload_instagram_reel(
            video_path=str(fake_video),
            caption="Fail test"
        )
        assert res["success"] is False
        assert "Transcoding failed" in res["error"]


def test_multi_publisher_three_platforms(tmp_path):
    fake_video = tmp_path / "short_tri.mp4"
    fake_video.write_bytes(b"dummy content")

    with patch("lol_agent.multi_publisher.upload_lol_short", return_value={"video_id": "yt_1", "url": "https://yt.be/1"}), \
         patch("lol_agent.multi_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "tt_1"}), \
         patch("lol_agent.multi_publisher.upload_instagram_reel", return_value={"success": True, "media_id": "ig_1"}):

        results = publish_multi_platform(
            video_path=str(fake_video),
            title="Triple Threat Outplay",
            platforms=["youtube", "tiktok", "instagram"]
        )

        assert "youtube" in results
        assert "tiktok" in results
        assert "instagram" in results
        assert results["youtube"]["success"] is True
        assert results["tiktok"]["success"] is True
        assert results["instagram"]["success"] is True
