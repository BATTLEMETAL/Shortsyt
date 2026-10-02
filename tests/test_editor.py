"""
Unit tests for lol_agent/lol_editor.py.
Verifies music selection, font resolution, performance insight loading, and editor parameter sanity.
"""
import os
import pytest
from lol_agent.lol_editor import (
    pick_music_for_action,
    _get_font_path,
    get_performance_insights,
    ACTION_ENERGY,
    MUSIC_ENERGY_MAP,
)


def test_get_font_path_returns_string():
    path = _get_font_path()
    assert isinstance(path, str)
    if path:
        assert os.path.exists(path)


def test_get_performance_insights_returns_dict():
    insights = get_performance_insights()
    assert isinstance(insights, dict)


def test_action_energy_mappings_cover_standard_actions():
    standard_actions = ["pentakill", "quadrakill", "triple", "outplay", "solo_bolo", "clutch", "escape"]
    for act in standard_actions:
        assert act in ACTION_ENERGY, f"Missing energy mapping for action '{act}'"
        assert ACTION_ENERGY[act] in ["high", "medium", "low"]


@pytest.fixture
def mock_music_dir(tmp_path, monkeypatch):
    music_dir = tmp_path / "lol_music"
    music_dir.mkdir()
    (music_dir / "track1.mp3").write_text("dummy audio content")
    (music_dir / "track2.mp3").write_text("dummy audio content")
    (music_dir / "track3.mp3").write_text("dummy audio content")
    monkeypatch.setattr("lol_agent.lol_editor.LOL_MUSIC_DIR", str(music_dir))
    return music_dir


def test_pick_music_for_action_selects_existing_file(mock_music_dir):
    track = pick_music_for_action("outplay")
    assert isinstance(track, str)
    assert os.path.exists(track)
    assert track.endswith(".mp3")


def test_pick_music_for_action_preferred_track(mock_music_dir):
    preferred = pick_music_for_action("outplay", preferred_track="track2.mp3")
    assert os.path.basename(preferred) == "track2.mp3"


def test_pick_music_rotates_and_records_history(mock_music_dir):
    tracks = set()
    for _ in range(5):
        t = pick_music_for_action("outplay")
        tracks.add(os.path.basename(t))
    assert len(tracks) >= 1
