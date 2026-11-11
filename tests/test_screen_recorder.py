"""
Unit tests for Windows Screen Recorder and System API endpoints
"""
import time
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from scripts.screen_recorder import (
    switch_to_default_desktop,
    get_ffmpeg_path,
    find_window_geometry,
    record_screen,
)
from lol_agent.api.main import app
from lol_agent.api.config import API_PASSWORD


@pytest.fixture
def auth_headers():
    client = TestClient(app)
    res = client.post("/auth/login", json={"password": API_PASSWORD})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_switch_to_default_desktop_safe():
    """Weryfikuje bezpieczne wywołanie przełączenia pulpitu."""
    res = switch_to_default_desktop()
    assert isinstance(res, bool)


def test_get_ffmpeg_path():
    """Weryfikuje odnajdywanie ścieżki FFmpeg."""
    p = get_ffmpeg_path()
    assert p is not None
    assert len(p) > 0


def test_find_window_geometry_nonexistent():
    """Dla nieistniejącego okna zwraca None."""
    geom = find_window_geometry("__Non_Existent_Window_XYZ_12345__")
    assert geom is None


def test_record_screen_mocked():
    """Weryfikuje poprawną orkiestrację nagrywania z mockowanym FFmpeg."""
    with patch("subprocess.Popen") as mock_popen, \
         patch("scripts.screen_recorder.u32.GetSystemMetrics", return_value=1920), \
         patch("scripts.screen_recorder.g32.BitBlt", return_value=1), \
         patch("scripts.screen_recorder.g32.GetDIBits", return_value=1):

        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        res = record_screen(output_path="test_mock_rec.mp4", duration=0.1, fps=10)
        assert res is True
        assert mock_popen.called


def test_api_screen_recorder_lifecycle(auth_headers):
    """Weryfikuje działanie endpointów /system/record-screen/*."""
    client = TestClient(app)

    # 1. Status początkowy
    r_stat = client.get("/system/record-screen/status", headers=auth_headers)
    assert r_stat.status_code == 200
    assert "recording" in r_stat.json()

    def slow_record(*args, **kwargs):
        time.sleep(0.5)

    # 2. Start z opóźnionym workerem
    with patch("scripts.screen_recorder.record_screen", side_effect=slow_record):
        r_start = client.post(
            "/system/record-screen/start",
            json={
                "duration": 5.0,
                "fps": 30,
                "output_filename": "test_api_rec.mp4"
            },
            headers=auth_headers
        )
        assert r_start.status_code == 200
        data = r_start.json()
        assert data["status"] == "recording_started"
        assert "output_path" in data

        # 3. Ponowny start podczas nagrywania powinien zwrócić 409 Conflict
        r_start_dup = client.post("/system/record-screen/start", json={}, headers=auth_headers)
        assert r_start_dup.status_code == 409

        # 4. Stop
        r_stop = client.post("/system/record-screen/stop", headers=auth_headers)
        assert r_stop.status_code == 200
        assert r_stop.json()["status"] == "stopping"
