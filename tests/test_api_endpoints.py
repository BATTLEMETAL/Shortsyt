"""
Integration tests for FastAPI endpoints in lol_agent/api/main.py.
Verifies authentication, pipeline status, hardware profiling, tuning configurations,
clips listing, outputs, thumbnails, calendar, and learning status across APIRouters.
"""
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from lol_agent.api.main import app
from lol_agent.api.config import API_PASSWORD


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    res = client.post("/auth/login", json={"password": API_PASSWORD})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_success(client):
    res = client.post("/auth/login", json={"password": API_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_invalid_password(client):
    res = client.post("/auth/login", json={"password": "wrong_password_12345"})
    assert res.status_code == 401


def test_auth_me_endpoint(client, auth_headers):
    res = client.get("/auth/me", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "ok"
    assert data.get("user") == "user"


def test_status_requires_auth(client):
    res = client.get("/status")
    # Missing credentials must be rejected
    assert res.status_code in [401, 403]


def test_status_with_auth(client, auth_headers):
    res = client.get("/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "progress" in data
    assert "current_step" in data
    assert "logs" in data


def test_hardware_info_endpoint(client, auth_headers):
    res = client.get("/system/hardware-info", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "tier" in data
    assert "hardware" in data
    assert "tuned_settings" in data
    assert "cpu_name" in data["hardware"]
    assert "gpu_name" in data["hardware"]
    assert "detected_encoder" in data["hardware"]


def test_tuning_config_endpoint(client, auth_headers):
    res = client.get("/config/tuning", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "pacing" in data


def test_tuning_config_endpoint_without_auth(client):
    """Lokalny panel desktopowy musi mieć możliwość odczytu tuningu bez autoryzacji tokenem."""
    res = client.get("/config/tuning")
    assert res.status_code == 200
    data = res.json()
    assert "pacing" in data


def test_clips_list_endpoint(client, auth_headers):
    res = client.get("/clips", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "clips" in data
    assert isinstance(data["clips"], list)


def test_outputs_list_endpoint(client, auth_headers):
    res = client.get("/outputs", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "outputs" in data
    assert isinstance(data["outputs"], list)


def test_thumbnails_list_endpoint(client, auth_headers):
    res = client.get("/thumbnails", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "thumbnails" in data
    assert isinstance(data["thumbnails"], list)


def test_youtube_token_status_endpoint(client, auth_headers):
    res = client.get("/youtube/token-status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "has_token" in data
    assert "is_valid" in data


def test_calendar_slots_endpoint(client, auth_headers):
    res = client.get("/calendar/slots?days=3", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "slots" in data
    assert isinstance(data["slots"], list)


def test_learning_status_endpoint(client, auth_headers):
    res = client.get("/learning/status", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert "directive" in data


def test_login_sets_httponly_cookie(client):
    """Verify that POST /auth/login sets jwt_token cookie."""
    res = client.post("/auth/login", json={"password": API_PASSWORD})
    assert res.status_code == 200
    assert "jwt_token" in res.cookies
    cookie_val = res.cookies["jwt_token"]
    assert len(cookie_val) > 20


def test_flexible_auth_via_cookie(client):
    """
    Task F3: Verify endpoints with verify_token_flexible accept authentication
    via HttpOnly cookie without requiring token query parameters or Authorization headers.
    """
    login_res = client.post("/auth/login", json={"password": API_PASSWORD})
    assert login_res.status_code == 200

    # Call endpoint with cookie only (no Authorization header, no query param)
    client.cookies.set("jwt_token", login_res.cookies["jwt_token"])
    res = client.get("/system/hardware-info")
    assert res.status_code == 200
    data = res.json()
    assert "hardware" in data


def test_flexible_auth_via_query_fallback(client):
    """Verify legacy query parameter ?token= fallback works when neither header nor cookie is present."""
    client.cookies.clear()
    login_res = client.post("/auth/login", json={"password": API_PASSWORD})
    token = login_res.json()["access_token"]

    res = client.get(f"/system/hardware-info?token={token}")
    assert res.status_code == 200
    assert "hardware" in res.json()


def test_calendar_reserve_and_release_flow(client, auth_headers):
    """Test reserving and releasing calendar publication slot."""
    slot_id = "slot_2026-10-15_18-30"
    payload = {
        "slot_id": slot_id,
        "title": "Clean Katarina Pentakill",
        "champion": "Katarina",
        "frag_type": "pentakill",
        "notes": "Test reservation"
    }
    # Reserve slot
    res = client.post("/calendar/reserve", json=payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json().get("status") == "reserved"
    assert res.json()["slot"]["slot_id"] == slot_id

    # Release slot
    del_res = client.delete(f"/calendar/slot/{slot_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json().get("status") == "released"

    # Release non-existent slot
    del_again = client.delete(f"/calendar/slot/{slot_id}", headers=auth_headers)
    assert del_again.status_code == 200
    assert del_again.json().get("status") == "not_found"


def test_calendar_publish_slot_validation(client, auth_headers):
    """Test validation errors when trying to publish non-existent or unrendered slots."""
    res_404 = client.post("/calendar/slot/nonexistent_slot/publish", headers=auth_headers)
    assert res_404.status_code == 404

    # Reserve slot without rendered output video
    slot_id = "slot_2026-10-20_08-30"
    client.post("/calendar/reserve", json={"slot_id": slot_id, "output_video": ""}, headers=auth_headers)
    res_400 = client.post(f"/calendar/slot/{slot_id}/publish", headers=auth_headers)
    assert res_400.status_code == 400
    assert "Brak wyrenderowanego pliku" in res_400.json()["detail"]
    client.delete(f"/calendar/slot/{slot_id}", headers=auth_headers)


def test_calendar_auto_fill_endpoint(client, auth_headers, monkeypatch):
    """Test /calendar/auto-fill endpoint with mocked clips."""
    mock_clips = [
        {
            "path": "c:/mock/clip1.mp4",
            "filename": "clip1.mp4",
            "champion": "Katarina",
            "pre_action": "pentakill",
            "pre_score": 95.0,
            "already_published": False,
        }
    ]
    monkeypatch.setattr(
        "lol_agent.api.routers.calendar.scan_available_clips",
        lambda folder=None: mock_clips
    )
    res = client.post("/calendar/auto-fill", json={"max_slots": 2}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json().get("status") == "ok"
    assert "assigned" in res.json()


def test_config_tuning_get_and_post(client, auth_headers):
    """Test reading and writing tuning configuration."""
    get_res = client.get("/config/tuning", headers=auth_headers)
    assert get_res.status_code == 200
    initial_config = get_res.json()

    # Update tuning
    post_res = client.post("/config/tuning", json={"pacing": "balanced", "zoom_aggression": 1.18}, headers=auth_headers)
    assert post_res.status_code == 200
    assert post_res.json().get("ok") is True


def test_learning_preferences_and_correction(client, auth_headers):
    """Test user learning preferences and correction recording endpoint."""
    pref_res = client.get("/learning/preferences", headers=auth_headers)
    assert pref_res.status_code == 200
    assert pref_res.json().get("ok") is True

    corr_payload = {
        "param_name": "title",
        "old_value": "OLD TITLE",
        "new_value": "NEW TITLE",
        "source": "api_test",
        "reason": "testing correction"
    }
    corr_res = client.post("/learning/correction", json=corr_payload, headers=auth_headers)
    assert corr_res.status_code == 200
    assert corr_res.json().get("ok") is True


def test_pipeline_stop_endpoint(client, auth_headers):
    """Test stopping the rendering pipeline."""
    res = client.post("/pipeline/stop", headers=auth_headers)
    assert res.status_code == 200
    assert res.json().get("status") == "stopped"


def test_clips_folder_scan_and_auto_detect_validation(client, auth_headers, tmp_path):
    """Test scanning a custom clips folder and validating missing clip auto-detection."""
    # Create a mock mp4 file > 3MB in tmp_path (to pass the min clip size threshold)
    mock_clip = tmp_path / "mock_gameplay.mp4"
    mock_clip.write_bytes(b"0" * (4 * 1024 * 1024))

    res = client.get(f"/clips?folder={str(tmp_path)}", headers=auth_headers)
    assert res.status_code == 200
    clips = res.json().get("clips", [])
    assert any(c.get("filename") == "mock_gameplay.mp4" for c in clips)

    # Missing file auto-detect should 404
    detect_res = client.post("/clips/auto-detect", json={"source_path": "missing_video_123.mp4"}, headers=auth_headers)
    assert detect_res.status_code == 404


def test_social_queue_and_preview_copy_endpoints(client, auth_headers):
    """Test /social/queue and /social/preview-copy and /social/queue/flush (no 500 error)."""
    q_res = client.get("/social/queue", headers=auth_headers)
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert "items" in q_data and "summary" in q_data

    prev_res = client.post(
        "/social/preview-copy",
        json={"title": "Greedy Chase Punished 🔥 #shorts #lol", "champion_name": "Katarina", "action_type": "double"},
        headers=auth_headers,
    )
    assert prev_res.status_code == 200
    prev_data = prev_res.json()
    assert "Greedy Chase Punished" in prev_data.get("tiktok_copy_text", "")
    assert "#shorts" not in prev_data.get("tiktok_copy_text", "").lower()

    with patch("lol_agent.scheduled_queue.check_and_flush_scheduled_posts", return_value=0), \
         patch("lol_agent.api.youtube_uploader.flush_pending_comments", return_value={"sent": [], "still_pending": []}):
        fl_res = client.post("/social/queue/flush", headers=auth_headers)
        assert fl_res.status_code == 200
        assert fl_res.json() == {"ok": True, "flushed_posts": 0, "flushed_comments": 0}


def test_system_reliability_and_cleanup_temp(client, auth_headers):
    with patch("lol_agent.api.youtube_uploader.get_token_status", return_value={"is_valid": True, "days_remaining": 7}), \
         patch("lol_agent.tiktok_publisher.get_tiktok_token_status", return_value={"valid": True, "days_remaining": 300}), \
         patch("lol_agent.instagram_publisher.get_instagram_token_status", return_value={"valid": True, "username": "dwannellenga"}), \
         patch("lol_agent.facebook_publisher.get_facebook_token_status", return_value={"valid": True, "can_publish": True}):
        res = client.get("/system/reliability", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("healthy", "degraded")
        assert set(data["tokens"].keys()) == {"youtube", "tiktok", "instagram", "facebook"}
        assert "disk" in data and "queue" in data and "gpu" in data

    dry_res = client.post("/system/cleanup-temp?dry_run=true&max_age_days=14", headers=auth_headers)
    assert dry_res.status_code == 200
    assert dry_res.json().get("dry_run") is True


def test_tiktok_oauth_pkce_endpoints(client, auth_headers, monkeypatch):
    """Verify real TikTok OAuth 2.0 PKCE URL generation, start endpoint, and verifier forwarding."""
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "sbaweq5t0oueol171i")

    url_res = client.get("/social/tiktok/auth-url", headers=auth_headers)
    assert url_res.status_code == 200
    url_data = url_res.json()
    assert "auth_url" in url_data and "state" in url_data
    assert "http%3A%2F%2Flocalhost%3A8180%2Fcallback" in url_data["auth_url"]
    assert "code_challenge=" in url_data["auth_url"]
    assert "code_challenge_method=S256" in url_data["auth_url"]
    assert "battlemetal.github.io" not in url_data["auth_url"]

    start_res = client.post("/social/tiktok/oauth/start", headers=auth_headers)
    assert start_res.status_code == 200
    start_data = start_res.json()
    assert start_data["listening_port"] == 8180
    assert start_data["listener_started"] is False  # Guarded under PYTEST_CURRENT_TEST
    assert "client_key=sbaweq5t0oueol171i" in start_data["auth_url"]

    captured = {}

    def _mock_exchange(code: str, verifier: str):
        captured["code"] = code
        captured["verifier"] = verifier
        return {"open_id": "oid_test", "scope": "user.info.basic,video.publish,video.upload"}

    with patch("scripts.authorize_tiktok.exchange_code_for_token", side_effect=_mock_exchange):
        ex_res = client.post(
            "/social/tiktok/auth-code",
            json={"code": "auth_code_123", "state": start_data["state"]},
            headers=auth_headers,
        )
        assert ex_res.status_code == 200
        assert ex_res.json()["success"] is True
        assert captured["code"] == "auth_code_123"
        assert len(captured["verifier"]) == 64


def test_social_publish_multi_validation_and_flags(client, auth_headers, tmp_path, monkeypatch):
    """Verify strict TikTok Direct Post UX validation and IG/FB caption + Direct Post flag forwarding."""
    vid = tmp_path / "test_multi_short.mp4"
    vid.write_bytes(b"0" * 1024)
    monkeypatch.setattr("lol_agent.api.routers.social.LOL_TEMP_DIR", str(tmp_path))

    # 1. Missing privacy level -> 400
    bad_priv = client.post(
        "/social/publish/test_multi_short.mp4",
        json={"title": "Test", "platforms": ["tiktok"], "privacy_tiktok": ""},
        headers=auth_headers,
    )
    assert bad_priv.status_code == 400

    # 2. Disclose enabled without Your brand / Branded content -> 400
    bad_disc = client.post(
        "/social/publish/test_multi_short.mp4",
        json={
            "title": "Test",
            "platforms": ["tiktok"],
            "privacy_tiktok": "PUBLIC_TO_EVERYONE",
            "tiktok_disclose_content": True,
            "tiktok_brand_organic": False,
            "tiktok_branded_content": False,
        },
        headers=auth_headers,
    )
    assert bad_disc.status_code == 400

    # 3. Branded content + SELF_ONLY -> 400
    bad_self = client.post(
        "/social/publish/test_multi_short.mp4",
        json={
            "title": "Test",
            "platforms": ["tiktok"],
            "privacy_tiktok": "SELF_ONLY",
            "tiktok_disclose_content": True,
            "tiktok_branded_content": True,
        },
        headers=auth_headers,
    )
    assert bad_self.status_code == 400

    # 4. Valid publish forwards IG/FB captions and all 5 Direct Post flags
    captured_call = {}

    def _mock_publish(**kwargs):
        captured_call.update(kwargs)
        return {
            "tiktok": {"success": False, "error": "mock_dry_run"},
            "instagram": {"success": False, "error": "mock_dry_run"},
            "facebook": {"success": False, "error": "mock_dry_run"},
        }

    with patch("lol_agent.api.routers.social.publish_multi_platform", side_effect=_mock_publish):
        ok_res = client.post(
            "/social/publish/test_multi_short.mp4",
            json={
                "title": "Katarina Triple",
                "platforms": ["tiktok", "instagram", "facebook"],
                "privacy_tiktok": "MUTUAL_FOLLOW_FRIENDS",
                "tiktok_caption": "TT custom caption #katarina",
                "instagram_caption": "IG Custom Caption #LoL #Katarina",
                "facebook_caption": "FB Custom Fanpage Post",
                "tiktok_allow_comment": True,
                "tiktok_allow_duet": False,
                "tiktok_allow_stitch": True,
                "tiktok_disclose_content": True,
                "tiktok_brand_organic": True,
                "tiktok_branded_content": False,
            },
            headers=auth_headers,
        )
        assert ok_res.status_code == 200
        assert captured_call["privacy_tiktok"] == "MUTUAL_FOLLOW_FRIENDS"
        assert captured_call["tiktok_disable_comment"] is False
        assert captured_call["tiktok_disable_duet"] is True
        assert captured_call["tiktok_disable_stitch"] is False
        assert captured_call["tiktok_brand_organic"] is True
        assert captured_call["tiktok_brand_content"] is False
        c_by_p = captured_call["copy_by_platform"]
        assert c_by_p["instagram"]["caption"] == "IG Custom Caption #lol #katarina"
        assert c_by_p["facebook"]["caption"] == "FB Custom Fanpage Post"
        assert c_by_p["tiktok"]["caption"] == "TT custom caption #katarina"


def test_tiktok_creator_user_endpoints_and_inbox_publish(client, auth_headers, tmp_path, monkeypatch):
    """Verify /social/tiktok/creator-info, /social/tiktok/user-info, and tiktok_post_mode='inbox'."""
    with patch("lol_agent.api.routers.social.get_tiktok_creator_info", return_value={"ok": True, "creator_nickname": "Dwannellenga", "max_video_post_duration_sec": 3600}):
        c_res = client.get("/social/tiktok/creator-info", headers=auth_headers)
        assert c_res.status_code == 200
        assert c_res.json()["ok"] is True
        assert c_res.json()["creator_nickname"] == "Dwannellenga"

    with patch("lol_agent.api.routers.social.get_tiktok_user_info", return_value={"ok": True, "display_name": "Dwannellenga", "avatar_url": "https://cdn.example.com/a.jpg"}):
        u_res = client.get("/social/tiktok/user-info", headers=auth_headers)
        assert u_res.status_code == 200
        assert u_res.json()["display_name"] == "Dwannellenga"

    vid = tmp_path / "inbox_api_short.mp4"
    vid.write_bytes(b"0" * 1024)
    monkeypatch.setattr("lol_agent.api.routers.social.LOL_TEMP_DIR", str(tmp_path))

    captured = {}

    def _mock_publish(**kwargs):
        captured.update(kwargs)
        return {"tiktok": {"success": False, "error": "mock_dry_run"}}

    with patch("lol_agent.api.routers.social.publish_multi_platform", side_effect=_mock_publish):
        res = client.post(
            "/social/publish/inbox_api_short.mp4",
            json={
                "title": "Draft Mode Short",
                "platforms": ["tiktok"],
                "privacy_tiktok": "",
                "tiktok_post_mode": "inbox",
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert captured["tiktok_post_mode"] == "inbox"




