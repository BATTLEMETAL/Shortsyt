"""
Integration tests for FastAPI endpoints in lol_agent/api/main.py.
Verifies authentication, pipeline status, hardware profiling, tuning configurations,
clips listing, outputs, thumbnails, calendar, and learning status across APIRouters.
"""
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

