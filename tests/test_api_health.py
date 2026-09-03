"""
tests/test_api_health.py
========================
Tests for FastAPI backend endpoints (/health, root) in lol_agent/api/main.py.
"""

import sys
import os
import pytest
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lol_agent"))

from lol_agent.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """GET /health should return 200 and valid service metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "Shortsyt API"


def test_health_full_endpoint(client):
    """GET /health/full should return 200 with agent status flags."""
    response = client.get("/health/full")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "lol_agent" in data
