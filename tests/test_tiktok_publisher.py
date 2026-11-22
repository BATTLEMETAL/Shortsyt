"""
Unit testy dla modułu publikacji TikTok i multi-platform
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lol_agent.tiktok_publisher import (
    load_tiktok_token, refresh_tiktok_token, get_tiktok_token_status,
    upload_tiktok_short
)
from lol_agent.multi_publisher import publish_multi_platform


@pytest.fixture(autouse=True)
def _isolate_external_apis(tmp_path, monkeypatch):
    """Blokuje przypadkowe wywołania sieciowe do TikTok/YouTube podczas testów jednostkowych."""
    non_existent = tmp_path / "isolated_tiktok_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher.TIKTOK_TOKEN_PATH", non_existent)
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: non_existent)

    def _blocked_http(*args, **kwargs):
        raise AssertionError("Blocked real HTTP request in unit test")

    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.post", _blocked_http)
    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.put", _blocked_http)
    monkeypatch.setattr(
        "lol_agent.api.youtube_uploader.upload_video",
        MagicMock(side_effect=AssertionError("Blocked real YouTube upload in unit test")),
    )


def test_load_tiktok_token_missing_file(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: non_existent)
    assert load_tiktok_token() is None


def test_get_tiktok_token_status_disconnected(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: non_existent)
    status = get_tiktok_token_status()
    assert status["connected"] is False
    assert status["valid"] is False


def test_upload_tiktok_missing_file(tmp_path, monkeypatch):
    token_file = tmp_path / "fake_token.json"
    token_file.write_text(json.dumps({"access_token": "fake_act", "expires_at": 9999999999}))
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: token_file)

    res = upload_tiktok_short(
        video_path=str(tmp_path / "missing_video.mp4"),
        title="Test Title"
    )
    assert res["success"] is False
    assert "nie istnieje" in res["error"]


def test_upload_tiktok_no_token(tmp_path, monkeypatch):
    non_existent = tmp_path / "non_existent_token.json"
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: non_existent)

    fake_video = tmp_path / "test_video.mp4"
    fake_video.write_bytes(b"dummy video content")

    res = upload_tiktok_short(
        video_path=str(fake_video),
        title="Test Title"
    )
    assert res["success"] is False
    assert "Brak ważnego tokenu" in res["error"]


def test_refresh_tiktok_token_missing_refresh_key():
    token_data = {"access_token": "dummy"}
    assert refresh_tiktok_token(token_data) is None


def test_multi_publisher_handles_failures_gracefully(tmp_path, monkeypatch):
    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    # Mock obu uploadów na błędy (zarówno api.youtube_uploader.upload_video jak i fallback lol_publisher)
    with patch("lol_agent.api.youtube_uploader.upload_video", side_effect=RuntimeError("YT Auth Error")), \
         patch("lol_agent.multi_publisher.upload_lol_short", side_effect=RuntimeError("YT Auth Error")), \
         patch("lol_agent.multi_publisher.upload_tiktok_short", return_value={"success": False, "error": "No TikTok Token"}):

        results = publish_multi_platform(
            video_path=str(fake_video),
            title="Epic Katarina Outplay",
            platforms=["youtube", "tiktok"]
        )

        assert "youtube" in results
        assert "tiktok" in results
        assert results["youtube"]["success"] is False
        assert "YT Auth Error" in results["youtube"]["error"]
        assert results["tiktok"]["success"] is False


def test_multi_publisher_partial_success(tmp_path):
    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    with patch("lol_agent.api.youtube_uploader.upload_video", return_value={"video_id": "yt_123", "url": "https://yt.be/yt_123", "title": "Epic"}), \
         patch("lol_agent.multi_publisher.upload_lol_short", return_value={"video_id": "yt_123", "url": "https://yt.be/yt_123", "title": "Epic"}), \
         patch("lol_agent.multi_publisher.upload_tiktok_short", return_value={"success": False, "error": "TT Quota"}):

        results = publish_multi_platform(
            video_path=str(fake_video),
            title="Epic Katarina Outplay",
            platforms=["youtube", "tiktok"]
        )

        assert results["youtube"]["success"] is True
        assert results["youtube"]["video_id"] == "yt_123"
        assert results["tiktok"]["success"] is False


def test_upload_tiktok_scheduling(tmp_path):
    from datetime import datetime, timedelta, timezone

    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")

    future_time = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with patch("lol_agent.scheduled_queue.queue_scheduled_post") as mock_queue:
        res = upload_tiktok_short(
            video_path=str(fake_video),
            title="Future TikTok Video",
            publish_at=future_time
        )
        assert res["success"] is True
        assert res["is_scheduled"] is True
        assert res["platform"] == "tiktok"
        mock_queue.assert_called_once()


def test_scheduled_queue_flushes_tiktok(tmp_path, monkeypatch):
    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)

    fake_video = tmp_path / "scheduled_tt.mp4"
    fake_video.write_bytes(b"dummy content")

    from lol_agent.scheduled_queue import queue_scheduled_post, check_and_flush_scheduled_posts

    # Dodaj pozycję z przeszłą datą
    queue_scheduled_post(
        platform="tiktok",
        video_path=str(fake_video),
        caption="Scheduled Outplay",
        publish_at="2020-01-01T00:00:00Z"
    )

    with patch("lol_agent.tiktok_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "v_test_123"}):
        count = check_and_flush_scheduled_posts()
        assert count == 1

    # Sprawdź czy status w pliku to 'published'
    items = json.loads(queue_file.read_text(encoding="utf-8"))
    assert items[0]["status"] == "published"
    assert items[0]["result"]["publish_id"] == "v_test_123"


def test_scheduled_queue_thread_safe_concurrent_adds(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)

    fake_video = tmp_path / "concurrent.mp4"
    fake_video.write_bytes(b"dummy")

    from lol_agent.scheduled_queue import queue_scheduled_post

    platforms = ["tiktok", "instagram", "facebook"] * 4

    def _add(p):
        return queue_scheduled_post(
            platform=p,
            video_path=str(fake_video),
            caption=f"Post for {p}",
            publish_at="2099-01-01T10:00:00Z",
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(_add, platforms))

    items = json.loads(queue_file.read_text(encoding="utf-8"))
    assert len(items) == len(platforms)
    assert sum(1 for i in items if i["platform"] == "tiktok") == 4
    assert sum(1 for i in items if i["platform"] == "instagram") == 4


def test_upload_tiktok_scheduling_stores_peak_moment(tmp_path):
    from datetime import datetime, timedelta, timezone

    fake_video = tmp_path / "short_test.mp4"
    fake_video.write_bytes(b"dummy content")
    future_time = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    with patch("lol_agent.scheduled_queue.queue_scheduled_post") as mock_queue:
        res = upload_tiktok_short(
            video_path=str(fake_video),
            title="Scheduled with peak",
            publish_at=future_time,
            peak_moment=6.4,
        )
        assert res["success"] is True
        assert mock_queue.call_args.kwargs.get("peak_moment") == 6.4


def test_prune_noisy_hard_cases_filters_zero_and_one_kill(tmp_path):
    from lol_agent.hard_case_learner import record_hard_case, prune_noisy_hard_cases, load_hard_cases

    mem = tmp_path / "hard_cases.json"
    record_hard_case("zero.mp4", "outplay", [], 0.0, 10.0, "ally_banner_blocked", ally_banner_blocked=True, memory_path=mem)
    record_hard_case("one_no_obj.mp4", "solo_bolo", [{"timestamp": 4.0}], 1.0, 10.0, "ally_banner_blocked", ally_banner_blocked=True, memory_path=mem)
    record_hard_case("one_obj.mp4", "steal", [{"timestamp": 4.0}], 1.0, 10.0, "objective_steal_or_slain", objective_secured=True, memory_path=mem)
    record_hard_case("triple.mp4", "triple", [{"timestamp": 3.0}, {"timestamp": 6.0}, {"timestamp": 9.0}], 1.0, 12.0, "ally_banner_blocked", ally_banner_blocked=True, memory_path=mem)

    stats = prune_noisy_hard_cases(memory_path=mem)
    assert stats == {"before": 4, "kept": 2, "removed": 2}
    names = [x["source_name"] for x in load_hard_cases(memory_path=mem)]
    assert names == ["one_obj.mp4", "triple.mp4"]


def test_scheduled_queue_atomic_processing_and_retry_backoff(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from lol_agent import scheduled_queue as sq

    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr(sq, "QUEUE_FILE", queue_file)

    fake_video = tmp_path / "retry_tt.mp4"
    fake_video.write_bytes(b"dummy content")

    entry = sq.queue_scheduled_post(
        platform="tiktok",
        video_path=str(fake_video),
        caption="Retry Test",
        publish_at="2020-01-01T00:00:00Z",
    )

    seen_statuses = []

    def _fail_first(**kwargs):
        cur = json.loads(queue_file.read_text(encoding="utf-8"))
        seen_statuses.append(cur[0]["status"])
        return {"success": False, "error": "Temporary 503"}

    with patch("lol_agent.tiktok_publisher.upload_tiktok_short", side_effect=_fail_first):
        # Próba 1: w trakcie uploadu status musi być 'processing', po błędzie 'pending' + retry_count=1 + backoff
        assert sq.check_and_flush_scheduled_posts() == 0
        assert seen_statuses == ["processing"]
        items = json.loads(queue_file.read_text(encoding="utf-8"))
        assert items[0]["status"] == "pending"
        assert items[0]["retry_count"] == 1
        assert items[0].get("next_retry_at")

        # Natychmiastowe kolejne wywołanie musi pominąć wpis (backoff 5 min)
        assert sq.check_and_flush_scheduled_posts() == 0
        items = json.loads(queue_file.read_text(encoding="utf-8"))
        assert items[0]["retry_count"] == 1

        # Cofnij next_retry_at w przeszłość do próby 2 i 3 -> po 3 błędach 'failed'
        for expected_retry, expected_status in [(2, "pending"), (3, "failed")]:
            items[0]["next_retry_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
            queue_file.write_text(json.dumps(items), encoding="utf-8")
            assert sq.check_and_flush_scheduled_posts() == 0
            items = json.loads(queue_file.read_text(encoding="utf-8"))
            assert items[0]["retry_count"] == expected_retry
            assert items[0]["status"] == expected_status

    assert entry["id"] == items[0]["id"]


def test_scheduled_queue_blocks_concurrent_duplicate_flush(tmp_path, monkeypatch):
    from lol_agent import scheduled_queue as sq

    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr(sq, "QUEUE_FILE", queue_file)
    fake_video = tmp_path / "dup_tt.mp4"
    fake_video.write_bytes(b"dummy content")

    sq.queue_scheduled_post(
        platform="tiktok",
        video_path=str(fake_video),
        caption="No Dup",
        publish_at="2020-01-01T00:00:00Z",
    )

    sq._FLUSH_EXEC_LOCK.acquire()
    try:
        with patch("lol_agent.tiktok_publisher.upload_tiktok_short") as mock_up:
            assert sq.check_and_flush_scheduled_posts() == 0
            mock_up.assert_not_called()
    finally:
        sq._FLUSH_EXEC_LOCK.release()


def test_temp_cleaner_protects_pending_queue_and_removes_stale_and_intermediate(tmp_path):
    import time
    from lol_agent.temp_cleaner import cleanup_temp_directory

    temp_dir = tmp_path / "lol_temp"
    temp_dir.mkdir()
    batches_dir = tmp_path / "overnight_batches"
    batches_dir.mkdir()
    q_file = tmp_path / "scheduled_social_queue.json"

    protected_mp4 = temp_dir / "pending_video.mp4"
    protected_thumb = temp_dir / "pending_video_thumb.jpg"
    stale_mp4 = temp_dir / "old_unpublished.mp4"
    recent_mp4 = temp_dir / "fresh_render.mp4"
    inter_cut = temp_dir / "01_cut.mp4"
    inter_raw = temp_dir / "abc_raw_frame.jpg"

    for p in (protected_mp4, protected_thumb, stale_mp4, recent_mp4, inter_cut, inter_raw):
        p.write_bytes(b"123456")

    old_ts = time.time() - 20 * 86400
    inter_ts = time.time() - 3600
    os.utime(protected_mp4, (old_ts, old_ts))
    os.utime(protected_thumb, (old_ts, old_ts))
    os.utime(stale_mp4, (old_ts, old_ts))
    os.utime(inter_cut, (inter_ts, inter_ts))
    os.utime(inter_raw, (inter_ts, inter_ts))

    q_file.write_text(json.dumps([
        {
            "id": "tt_1",
            "status": "pending",
            "video_path": str(protected_mp4),
            "thumbnail_path": str(protected_thumb),
        }
    ]), encoding="utf-8")

    stats = cleanup_temp_directory(
        max_age_days=14,
        intermediate_min_age_minutes=30,
        dry_run=False,
        temp_dir=temp_dir,
        queue_file=q_file,
        batches_dir=batches_dir,
    )
    assert stats["removed_intermediate"] == 2
    assert stats["removed_stale"] == 1
    assert protected_mp4.exists()
    assert protected_thumb.exists()
    assert recent_mp4.exists()
    assert not stale_mp4.exists()
    assert not inter_cut.exists()
    assert not inter_raw.exists()




