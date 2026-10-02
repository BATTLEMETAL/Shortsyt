"""
Unit tests for lol_agent/api/calendar_manager.py.
Verifies publication calendar scheduling, slot reservation, atomic DB persistence,
release/update lifecycle, and intelligent auto-fill.
"""
import os
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from lol_agent.api.calendar_manager import (
    _load_calendar_db,
    _save_calendar_db,
    get_calendar_slots,
    reserve_slot,
    release_slot,
    update_slot_status,
    auto_fill_upcoming_slots,
    PEAK_HOURS_CET,
)


@pytest.fixture
def mock_calendar_db(tmp_path, monkeypatch):
    """Isolates calendar JSON DB to a temporary directory."""
    db_file = tmp_path / "test_publishing_calendar.json"
    monkeypatch.setattr("lol_agent.api.calendar_manager.CALENDAR_FILE", db_file)
    return db_file


class TestCalendarDBPersistence:
    """Tests for low-level calendar database file loading and atomic saving."""

    def test_load_empty_when_file_not_found(self, mock_calendar_db):
        assert _load_calendar_db() == {}

    def test_save_and_load_roundtrip(self, mock_calendar_db):
        data = {"slot_1": {"title": "Test Pentakill", "status": "reserved"}}
        _save_calendar_db(data)
        loaded = _load_calendar_db()
        assert loaded == data

    def test_load_handles_corrupt_json(self, mock_calendar_db):
        mock_calendar_db.write_text("{corrupt-json", encoding="utf-8")
        assert _load_calendar_db() == {}


class TestCalendarSlotLifecycle:
    """Tests for reserving, updating, and releasing publication slots."""

    def test_reserve_slot_standard_peak_hour(self, mock_calendar_db):
        slot_id = "slot_2026-10-25_18-30"
        entry = reserve_slot(
            slot_id=slot_id,
            title="Katarina Outplay #Shorts",
            champion="Katarina",
            frag_type="outplay",
            source_clip="C:/Clips/outplay1.mp4",
            output_video="",
            notes="Ready for review"
        )
        assert entry["slot_id"] == slot_id
        assert entry["status"] == "reserved"
        assert entry["is_peak"] is True
        assert entry["time"] == "18:30"
        assert entry["champion"] == "Katarina"

        # Verify persisted in DB
        db = _load_calendar_db()
        assert slot_id in db
        assert db[slot_id]["title"] == "Katarina Outplay #Shorts"

    def test_reserve_slot_with_output_video_sets_ready_status(self, mock_calendar_db):
        slot_id = "slot_2026-10-25_08-30"
        entry = reserve_slot(
            slot_id=slot_id,
            title="Zed Shadow Outplay",
            output_video="C:/Outputs/final_zed.mp4"
        )
        assert entry["status"] == "ready"

    def test_reserve_slot_custom_dt_cet(self, mock_calendar_db):
        custom_iso = "2026-11-01T14:15:00"
        entry = reserve_slot(
            slot_id="custom_reserve",
            title="Custom Time Short",
            custom_dt_cet=custom_iso
        )
        assert entry["date"] == "2026-11-01"
        assert entry["time"] == "14:15"
        assert entry["is_peak"] is False  # 14:15 is not in standard PEAK_HOURS_CET

    def test_update_slot_status_existing(self, mock_calendar_db):
        slot_id = "slot_2026-10-26_18-30"
        reserve_slot(slot_id=slot_id, title="Initial Title")

        updated = update_slot_status(slot_id, {"status": "scheduled", "yt_video_id": "dQw4w9WgXcQ"})
        assert updated is not None
        assert updated["status"] == "scheduled"
        assert updated["yt_video_id"] == "dQw4w9WgXcQ"

    def test_update_slot_status_missing_returns_none(self, mock_calendar_db):
        assert update_slot_status("nonexistent_slot", {"status": "ready"}) is None

    def test_release_slot_success_and_missing(self, mock_calendar_db):
        slot_id = "slot_2026-10-27_08-30"
        reserve_slot(slot_id=slot_id, title="To Release")

        assert release_slot(slot_id) is True
        assert slot_id not in _load_calendar_db()
        assert release_slot(slot_id) is False


class TestCalendarSlotsGrid:
    """Tests for generating publication slots grid with merged YouTube data."""

    def test_get_calendar_slots_generates_two_slots_per_day(self, mock_calendar_db, monkeypatch):
        # Mock youtube performance query to avoid external API calls
        monkeypatch.setattr(
            "lol_agent.api.youtube_uploader.get_channel_videos_and_performance",
            lambda *args, **kwargs: {"scheduled": {}, "published": [], "avg_views": 0}
        )
        days = 3
        slots = get_calendar_slots(start_date="2026-10-10", days=days)
        # 3 days * 2 peak hours = 6 slots
        assert len(slots) >= 6
        dates = {s["date"] for s in slots if s.get("is_peak")}
        assert "2026-10-10" in dates
        assert "2026-10-11" in dates
        assert "2026-10-12" in dates


class TestCalendarAutoFill:
    """Tests for automatic assignment of top clips to upcoming free slots."""

    def test_auto_fill_skips_published_and_assigns_free_slots(self, mock_calendar_db, monkeypatch):
        # Mock get_calendar_slots to return 2 free slots
        fake_slots = [
            {
                "slot_id": "slot_2026-10-15_08-30",
                "date": "2026-10-15",
                "time": "08:30",
                "datetime_local": "2026-10-15 08:30 CET",
                "datetime_utc": "2026-10-15T06:30:00Z",
                "is_peak": True,
                "is_past": False,
                "status": "free",
                "source_clip": "",
            },
            {
                "slot_id": "slot_2026-10-15_18-30",
                "date": "2026-10-15",
                "time": "18:30",
                "datetime_local": "2026-10-15 18:30 CET",
                "datetime_utc": "2026-10-15T16:30:00Z",
                "is_peak": True,
                "is_past": False,
                "status": "free",
                "source_clip": "",
            }
        ]
        monkeypatch.setattr(
            "lol_agent.api.calendar_manager.get_calendar_slots",
            lambda *args, **kwargs: fake_slots
        )

        test_clips = [
            {
                "path": "c:/videos/already_pub.mp4",
                "already_published": True,
                "champion": "Akali",
                "pre_action": "pentakill",
            },
            {
                "path": "c:/videos/candidate_penta.mp4",
                "already_published": False,
                "champion": "Katarina",
                "pre_action": "pentakill",
                "pre_score": 95.0,
            },
            {
                "path": "c:/videos/candidate_solo.mp4",
                "already_published": False,
                "champion": "Zed",
                "pre_action": "solo_bolo",
                "pre_score": 90.0,
            },
        ]

        assigned = auto_fill_upcoming_slots(test_clips, max_slots=2)
        assert len(assigned) == 2
        assigned_paths = [a["source_clip"] for a in assigned]
        assert "c:/videos/candidate_solo.mp4" in assigned_paths
        assert "c:/videos/candidate_penta.mp4" in assigned_paths
        assert "c:/videos/already_pub.mp4" not in assigned_paths
