"""
Unit tests for YouTube uploading and scheduling helpers.
Verifies tag limits, schedule time parsing, title formatting, and optimal publish slot dispatching.
"""
import pytest
from lol_agent.lol_publisher import _limit_tags, parse_schedule_time
from lol_agent.lol_metadata_generator import _format_final_title
from lol_agent.api.youtube_uploader import get_next_optimal_publish_time


def test_limit_tags_under_500_chars():
    tags = [f"tag_{i}" for i in range(50)]
    limited = _limit_tags(tags)
    total_len = sum(len(t) + 1 for t in limited)
    assert total_len <= 500
    assert len(limited) <= 30


def test_limit_tags_strips_empty_entries():
    tags = ["katarina", "", "  ", "outplay", ""]
    limited = _limit_tags(tags)
    assert limited == ["katarina", "outplay"]


def test_parse_schedule_time_morning():
    rfc, local = parse_schedule_time("morning")
    assert "08:30" in local
    assert rfc.endswith("Z")


def test_parse_schedule_time_evening():
    rfc, local = parse_schedule_time("evening")
    assert "18:00" in local
    assert rfc.endswith("Z")


def test_parse_schedule_time_custom_hh_mm():
    rfc, local = parse_schedule_time("14:45")
    assert "14:45" in local
    assert rfc.endswith("Z")


def test_parse_schedule_time_invalid_raises_error():
    with pytest.raises(ValueError):
        parse_schedule_time("invalid-time-format-xyz")


def test_format_final_title_guarantees_viral_hashtags():
    raw = "Clean Solo Bolo on Katarina"
    formatted = _format_final_title(raw)
    assert formatted.endswith("#Shorts #LeagueOfLegends #LoL")
    assert "Clean Solo Bolo on Katarina" in formatted


def test_format_final_title_deduplicates_existing_tags():
    raw = "Two Enemies Down #Shorts #LoL"
    formatted = _format_final_title(raw)
    # Must only have one instance of each tag at the end
    assert formatted.count("#Shorts") == 1
    assert formatted.count("#LeagueOfLegends") == 1
    assert formatted.count("#LoL") == 1
    assert formatted.endswith("#Shorts #LeagueOfLegends #LoL")


def test_get_next_optimal_publish_time_structure():
    slot = get_next_optimal_publish_time()
    assert isinstance(slot, dict)
    assert "publish_at" in slot
    assert "label" in slot
    # Must be one of the two peak slots: 08:30 or 18:30
    assert any(h in slot["label"] for h in ["08:30", "18:30"])
