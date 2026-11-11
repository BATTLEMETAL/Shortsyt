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
    assert formatted.endswith("#shorts #leagueoflegends #lol")
    assert "Clean Solo Bolo on Katarina" in formatted


def test_format_final_title_deduplicates_existing_tags():
    raw = "Two Enemies Down #Shorts #LoL"
    formatted = _format_final_title(raw)
    # Must only have one instance of each tag at the end, in lowercase
    assert formatted.count("#shorts") == 1
    assert formatted.count("#leagueoflegends") == 1
    assert formatted.count("#lol") == 1
    assert formatted.endswith("#shorts #leagueoflegends #lol")


def test_get_next_optimal_publish_time_structure():
    slot = get_next_optimal_publish_time()
    assert isinstance(slot, dict)
    assert "publish_at" in slot
    assert "label" in slot
    # Must be one of the two peak slots: 08:30 or 18:30
    assert any(h in slot["label"] for h in ["08:30", "18:30"])


def test_get_lol_youtube_service_non_interactive_returns_none(tmp_path, monkeypatch):
    """Gdy brak tokenu a tryb jest nieinteraktywny (allow_interactive=False), funkcja zwraca None bez otwierania przeglądarki."""
    from lol_agent.lol_publisher import get_lol_youtube_service
    fake_token = tmp_path / "non_existent_token.pickle"
    monkeypatch.setattr("lol_agent.lol_publisher.TOKEN_PATH", str(fake_token))

    browser_opened = []
    monkeypatch.setattr("webbrowser.open", lambda *a, **kw: browser_opened.append(True))

    svc = get_lol_youtube_service(allow_interactive=False)
    assert svc is None
    assert len(browser_opened) == 0


def test_get_lol_youtube_service_non_tty_returns_none(tmp_path, monkeypatch):
    """Gdy allow_interactive=True ale brak TTY (tło/GUI/uvicorn), funkcja zwraca None bez otwierania przeglądarki."""
    import sys
    from lol_agent.lol_publisher import get_lol_youtube_service
    fake_token = tmp_path / "non_existent_token.pickle"
    monkeypatch.setattr("lol_agent.lol_publisher.TOKEN_PATH", str(fake_token))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    browser_opened = []
    monkeypatch.setattr("webbrowser.open", lambda *a, **kw: browser_opened.append(True))

    svc = get_lol_youtube_service(allow_interactive=True)
    assert svc is None
    assert len(browser_opened) == 0


def test_run_pending_checks_breaks_early_when_auth_missing(tmp_path, monkeypatch):
    """Gdy YouTube API jest niezautoryzowane, run_pending_checks natychmiast przerywa pętlę i nie męczy kolejki."""
    from lol_agent.lol_performance_tracker import run_pending_checks
    fake_pending_file = tmp_path / "pending_checks.json"
    fake_perf_log = tmp_path / "performance_log.jsonl"
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PENDING_PATH", str(fake_pending_file))
    monkeypatch.setattr("lol_agent.lol_performance_tracker.PERFORMANCE_LOG", str(fake_perf_log))

    # 10 wpisów w kolejce
    mock_pending = {
        f"vid_{i}": {
            "video_id": f"vid_{i}",
            "title": f"Video {i}",
            "action_type": "outplay",
            "champion": "Katarina",
            "quality_score": 85.0,
            "duration_s": 15.0,
            "check_at": 100.0,
            "checked": False,
        }
        for i in range(10)
    }
    import json
    with open(fake_pending_file, "w", encoding="utf-8") as f:
        json.dump(mock_pending, f)

    fetch_call_count = [0]
    def mock_fetch(vid_id, duration_s=15.0):
        fetch_call_count[0] += 1
        return None

    monkeypatch.setattr("lol_agent.lol_performance_tracker.fetch_video_stats", mock_fetch)
    monkeypatch.setattr("lol_agent.lol_performance_tracker._get_youtube", lambda: None)

    run_pending_checks(force_all=True)

    # Obwód bezpiecznika: przy braku YouTube API pętla powinna przerwać po pierwszym nieudanym sprawdzeniu
    assert fetch_call_count[0] == 1

