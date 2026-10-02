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
