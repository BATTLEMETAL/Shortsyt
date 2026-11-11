"""
Unit tests for lol_agent/facebook_publisher.py.
Verifies token loading, status reporting, error handling, and upload flow with mocked Graph API.
"""

import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lol_agent.facebook_publisher import (
    load_facebook_token,
    get_facebook_token_status,
    upload_facebook_reel,
)


class TestFacebookTokenLoading:
    def test_load_facebook_token_missing_file(self, tmp_path, monkeypatch):
        fake_path = tmp_path / "nonexistent_fb_token.json"
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", fake_path)
        monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "")
        monkeypatch.setenv("FACEBOOK_PAGE_ID", "")
        token = load_facebook_token()
        assert token is None

    def test_load_facebook_token_valid_file(self, tmp_path, monkeypatch):
        token_file = tmp_path / "facebook_token.json"
        token_file.write_text(json.dumps({
            "access_token": "EAAtesttoken123",
            "page_id": "123456789",
            "page_name": "TestPage",
            "can_publish_posts": True
        }), encoding="utf-8")
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", token_file)

        data = load_facebook_token()
        assert data is not None
        assert data["access_token"] == "EAAtesttoken123"
        assert data["page_id"] == "123456789"
        assert data["page_name"] == "TestPage"
        assert data["can_publish_posts"] is True


class TestFacebookTokenStatus:
    def test_status_when_no_token(self, tmp_path, monkeypatch):
        fake_path = tmp_path / "empty.json"
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", fake_path)
        monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "")
        monkeypatch.setenv("FACEBOOK_PAGE_ID", "")

        status = get_facebook_token_status()
        assert status["connected"] is False
        assert status["valid"] is False
        assert status["can_publish"] is False

    @patch("requests.get")
    def test_status_when_api_ok(self, mock_get, tmp_path, monkeypatch):
        token_file = tmp_path / "facebook_token.json"
        token_file.write_text(json.dumps({
            "access_token": "valid_token",
            "page_id": "111222333",
            "page_name": "Dwannellenga",
            "can_publish_posts": True
        }), encoding="utf-8")
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", token_file)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "Dwannellenga", "fan_count": 42}
        mock_get.return_value = mock_resp

        status = get_facebook_token_status()
        assert status["connected"] is True
        assert status["valid"] is True
        assert status["can_publish"] is True
        assert status["fan_count"] == 42


class TestFacebookUpload:
    def test_upload_missing_file(self):
        res = upload_facebook_reel("/nonexistent/video.mp4", "caption")
        assert res["success"] is False
        assert "nie istnieje" in res["error"]
        assert res["platform"] == "facebook"

    def test_upload_no_token(self, tmp_path, monkeypatch):
        fake_video = tmp_path / "test.mp4"
        fake_video.write_bytes(b"dummy video content")

        fake_path = tmp_path / "empty.json"
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", fake_path)
        monkeypatch.setenv("FACEBOOK_ACCESS_TOKEN", "")
        monkeypatch.setenv("FACEBOOK_PAGE_ID", "")

        res = upload_facebook_reel(str(fake_video), "caption")
        assert res["success"] is False
        assert "Brak konfiguracji" in res["error"]

    @patch("requests.get")
    @patch("requests.post")
    def test_upload_success_flow(self, mock_post, mock_get, tmp_path, monkeypatch):
        fake_video = tmp_path / "test.mp4"
        fake_video.write_bytes(b"dummy video content 12345")

        token_file = tmp_path / "facebook_token.json"
        token_file.write_text(json.dumps({
            "access_token": "valid_token",
            "page_id": "111222333",
            "page_name": "Dwannellenga",
            "can_publish_posts": True
        }), encoding="utf-8")
        monkeypatch.setattr("lol_agent.facebook_publisher.FACEBOOK_TOKEN_PATH", token_file)

        # 1. Init response
        init_resp = MagicMock()
        init_resp.status_code = 200
        init_resp.json.return_value = {"video_id": "fb_vid_999", "upload_url": "https://rupload.facebook.com/mock"}

        # 2. Upload binary response
        up_resp = MagicMock()
        up_resp.status_code = 200

        # 3. Finish response
        fin_resp = MagicMock()
        fin_resp.status_code = 200
        fin_resp.json.return_value = {"success": True}

        mock_post.side_effect = [init_resp, up_resp, fin_resp]

        # 4. Info response
        info_resp = MagicMock()
        info_resp.status_code = 200
        info_resp.json.return_value = {"permalink_url": "https://www.facebook.com/111222333/videos/fb_vid_999"}
        mock_get.return_value = info_resp

        res = upload_facebook_reel(str(fake_video), "Test Facebook caption")
        assert res["success"] is True
        assert res["video_id"] == "fb_vid_999"
        assert res["platform"] == "facebook"
        assert "fb_vid_999" in res["url"]
