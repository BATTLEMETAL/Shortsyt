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


def test_tiktok_upload_skips_intro_cover_embedding_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("TIKTOK_EMBED_INTRO_COVER", raising=False)
    token_file = tmp_path / "tt_tok.json"
    token_file.write_text(json.dumps({"access_token": "act.valid", "expires_at": 9999999999}))
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: token_file)

    fake_video = tmp_path / "clean_short.mp4"
    fake_video.write_bytes(b"0" * 50000)
    fake_thumb = tmp_path / "clean_short_thumb.jpg"
    fake_thumb.write_bytes(b"jpgdata")

    captured_payloads = []

    def _mock_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        if "video/init" in url:
            captured_payloads.append(json)
            resp.json.return_value = {"data": {"publish_id": "pub_1", "upload_url": "https://upload.tiktok.test/put"}}
        else:
            resp.json.return_value = {"data": {"status": "SEND_TO_USER_INBOX"}}
        return resp

    def _mock_put(url, headers=None, data=None, timeout=None):
        r = MagicMock()
        r.status_code = 200
        return r

    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.post", _mock_post)
    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.put", _mock_put)
    monkeypatch.setattr("lol_agent.tiktok_publisher.time.sleep", lambda s: None)

    with patch("lol_agent.tiktok_publisher._prepare_tiktok_video_with_cover") as mock_prep:
        res = upload_tiktok_short(
            video_path=str(fake_video),
            title="Clean Start",
            thumbnail_path=str(fake_thumb),
            peak_moment=6.5,
        )
        mock_prep.assert_not_called()

    assert res["success"] is True
    assert res["cover_embedded"] is False
    assert captured_payloads[0]["post_info"]["video_cover_timestamp_ms"] == 6500


def test_tiktok_direct_post_flags_and_queue_roundtrip(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from lol_agent.scheduled_queue import check_and_flush_scheduled_posts

    token_file = tmp_path / "tt_tok.json"
    token_file.write_text(json.dumps({"access_token": "act.valid", "expires_at": 9999999999}))
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: token_file)

    fake_video = tmp_path / "direct_flags.mp4"
    fake_video.write_bytes(b"0" * 50000)

    captured_payloads = []

    def _mock_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        if "video/init" in url:
            captured_payloads.append(json)
            resp.json.return_value = {"data": {"publish_id": "pub_flags_1", "upload_url": "https://upload.tiktok.test/put"}}
        else:
            resp.json.return_value = {"data": {"status": "PUBLISH_COMPLETE"}}
        return resp

    def _mock_put(url, headers=None, data=None, timeout=None):
        r = MagicMock()
        r.status_code = 200
        return r

    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.post", _mock_post)
    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.put", _mock_put)
    monkeypatch.setattr("lol_agent.tiktok_publisher.time.sleep", lambda s: None)

    res = upload_tiktok_short(
        video_path=str(fake_video),
        title="Flags Direct",
        privacy_level="MUTUAL_FOLLOW_FRIENDS",
        disable_comment=True,
        disable_duet=True,
        disable_stitch=False,
        brand_organic_toggle=True,
        brand_content_toggle=False,
    )
    assert res["success"] is True
    post_info = captured_payloads[0]["post_info"]
    assert post_info["privacy_level"] == "MUTUAL_FOLLOW_FRIENDS"
    assert post_info["disable_comment"] is True
    assert post_info["disable_duet"] is True
    assert post_info["disable_stitch"] is False
    assert post_info["brand_organic_toggle"] is True
    assert post_info["brand_content_toggle"] is False

    # Queue roundtrip preserves all 5 flags through scheduled_queue._execute_single_upload
    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)
    monkeypatch.setenv("TIKTOK_USE_WEB_STUDIO", "0")

    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sched = upload_tiktok_short(
        video_path=str(fake_video),
        title="Queued Flags",
        privacy_level="PUBLIC_TO_EVERYONE",
        disable_comment=True,
        disable_duet=False,
        disable_stitch=True,
        brand_organic_toggle=False,
        brand_content_toggle=True,
        publish_at=future_time,
    )
    assert sched["is_scheduled"] is True

    items = json.loads(queue_file.read_text(encoding="utf-8"))
    extra = items[0]["extra"]
    assert extra["disable_comment"] is True
    assert extra["disable_duet"] is False
    assert extra["disable_stitch"] is True
    assert extra["brand_organic_toggle"] is False
    assert extra["brand_content_toggle"] is True

    # Rewind publish_at and flush via scheduled_queue
    items[0]["publish_at"] = "2020-01-01T00:00:00Z"
    queue_file.write_text(json.dumps(items), encoding="utf-8")

    with patch("lol_agent.tiktok_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "q_ok"}) as mock_upload:
        flushed = check_and_flush_scheduled_posts()
        assert flushed == 1
        kw = mock_upload.call_args.kwargs
        assert kw["disable_comment"] is True
        assert kw["disable_duet"] is False
        assert kw["disable_stitch"] is True
        assert kw["brand_organic_toggle"] is False
        assert kw["brand_content_toggle"] is True


def test_tiktok_creator_and_user_info_and_inbox_mode(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from lol_agent.tiktok_publisher import get_tiktok_creator_info, get_tiktok_user_info
    from lol_agent.scheduled_queue import check_and_flush_scheduled_posts

    token_file = tmp_path / "tt_tok.json"
    token_file.write_text(json.dumps({"access_token": "act.valid", "expires_at": 9999999999}))
    monkeypatch.setattr("lol_agent.tiktok_publisher._token_path", lambda: token_file)

    posted_urls = []

    def _mock_post(url, headers=None, json=None, timeout=None):
        posted_urls.append(url)
        resp = MagicMock()
        if "creator_info/query" in url:
            resp.json.return_value = {
                "data": {
                    "creator_username": "dwannellenga",
                    "creator_nickname": "Dwannellenga",
                    "creator_avatar_url": "https://cdn.example.com/av.jpg",
                    "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
                    "comment_disabled": False,
                    "duet_disabled": True,
                    "stitch_disabled": False,
                    "max_video_post_duration_sec": 600,
                },
                "error": {"code": "ok", "message": ""},
            }
        elif "inbox/video/init" in url:
            resp.json.return_value = {
                "data": {"publish_id": "inbox_pub_1", "upload_url": "https://upload.tiktok.test/inbox_put"},
                "error": {"code": "ok", "message": ""},
            }
        else:
            resp.json.return_value = {"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok", "message": ""}}
        return resp

    def _mock_get(url, params=None, headers=None, timeout=None):
        assert "username" not in str((params or {}).get("fields", ""))
        resp = MagicMock()
        resp.json.return_value = {
            "data": {"user": {"open_id": "oid_1", "display_name": "Dwannellenga", "avatar_url": "https://cdn.example.com/av.jpg"}},
            "error": {"code": "ok", "message": ""},
        }
        return resp

    def _mock_put(url, headers=None, data=None, timeout=None):
        r = MagicMock()
        r.status_code = 200
        return r

    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.post", _mock_post)
    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.get", _mock_get)
    monkeypatch.setattr("lol_agent.tiktok_publisher.requests.put", _mock_put)
    monkeypatch.setattr("lol_agent.tiktok_publisher.time.sleep", lambda s: None)

    cinfo = get_tiktok_creator_info()
    assert cinfo["ok"] is True
    assert cinfo["duet_disabled"] is True
    assert cinfo["privacy_level_options"] == ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]

    uinfo = get_tiktok_user_info()
    assert uinfo["ok"] is True
    assert uinfo["display_name"] == "Dwannellenga"

    fake_video = tmp_path / "inbox_short.mp4"
    fake_video.write_bytes(b"0" * 50000)

    inbox_res = upload_tiktok_short(
        video_path=str(fake_video),
        title="Draft Short",
        post_mode="inbox",
    )
    assert inbox_res["success"] is True
    assert inbox_res["post_mode"] == "inbox"
    assert inbox_res["inbox"] is True
    assert any("inbox/video/init" in u for u in posted_urls)
    assert not any("post/publish/video/init" in u for u in posted_urls)

    # Queue roundtrip preserves post_mode='inbox'
    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)
    monkeypatch.setenv("TIKTOK_USE_WEB_STUDIO", "0")
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    upload_tiktok_short(video_path=str(fake_video), title="Queued Inbox", post_mode="inbox", publish_at=future_time)
    items = json.loads(queue_file.read_text(encoding="utf-8"))
    assert items[0]["extra"]["post_mode"] == "inbox"
    items[0]["publish_at"] = "2020-01-01T00:00:00Z"
    queue_file.write_text(json.dumps(items), encoding="utf-8")

    with patch("lol_agent.tiktok_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "q_inb"}) as mock_upload:
        assert check_and_flush_scheduled_posts() == 1
        assert mock_upload.call_args.kwargs["post_mode"] == "inbox"


def test_scheduled_queue_blocks_duplicate_published_and_enforces_spacing(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from lol_agent.scheduled_queue import check_and_flush_scheduled_posts

    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)

    v1 = tmp_path / "clip1.mp4"
    v2 = tmp_path / "clip2.mp4"
    v1.write_bytes(b"video-one")
    v2.write_bytes(b"video-two")

    now_iso = datetime.now(timezone.utc).isoformat()
    items = [
        {
            "id": "ig_already_pub",
            "platform": "instagram",
            "video_path": str(v1.resolve()),
            "caption": "Old copy",
            "publish_at": "2020-01-01T00:00:00Z",
            "published_at": "2020-01-01T00:01:00Z",
            "status": "published",
        },
        {
            "id": "ig_dup_pending",
            "platform": "instagram",
            "video_path": str(v1.resolve()),
            "caption": "Dup copy",
            "publish_at": "2020-01-02T00:00:00Z",
            "status": "pending",
        },
        {
            "id": "ig_fresh_pending_1",
            "platform": "instagram",
            "video_path": str(v2.resolve()),
            "caption": "Fresh 2",
            "publish_at": now_iso,
            "status": "pending",
        },
        {
            "id": "ig_fresh_pending_2",
            "platform": "instagram",
            "video_path": str((tmp_path / "clip3.mp4").resolve()),
            "caption": "Fresh 3",
            "publish_at": now_iso,
            "status": "pending",
        },
    ]
    (tmp_path / "clip3.mp4").write_bytes(b"video-three")
    queue_file.write_text(json.dumps(items), encoding="utf-8")

    with patch("lol_agent.instagram_publisher.upload_instagram_reel", return_value={"success": True, "media_id": "ig_ok"}) as mock_ig:
        flushed = check_and_flush_scheduled_posts()
        assert flushed == 1
        assert mock_ig.call_count == 1

    after = {it["id"]: it for it in json.loads(queue_file.read_text(encoding="utf-8"))}
    assert after["ig_dup_pending"]["status"] == "skipped_duplicate"
    assert after["ig_fresh_pending_1"]["status"] == "published"
    assert after["ig_fresh_pending_2"]["status"] == "pending"
    assert after["ig_fresh_pending_2"].get("next_retry_at") is not None


def test_cleanup_published_video_respects_pending_queue_and_deletes_when_idle(tmp_path):
    from lol_agent.temp_cleaner import cleanup_published_video_if_idle, cleanup_temp_directory

    temp_dir = tmp_path / "lol_temp"
    temp_dir.mkdir()
    batches_dir = tmp_path / "overnight_batches"
    batches_dir.mkdir()
    q_file = tmp_path / "scheduled_social_queue.json"

    mp4 = temp_dir / "short_test_clean.mp4"
    thumb = temp_dir / "short_test_clean_thumb.jpg"
    meta = temp_dir / "short_test_clean.meta.json"
    mp4.write_bytes(b"video-bytes" * 100)
    thumb.write_bytes(b"thumb")
    meta.write_text(json.dumps({"published_at": "2026-11-22T18:00:00Z", "published_platforms": ["youtube", "tiktok"]}), encoding="utf-8")

    # 1. Wpis 'pending' w kolejce chroni .mp4 przed usunięciem
    q_file.write_text(json.dumps([
        {"id": "tt_p", "platform": "tiktok", "status": "pending", "video_path": str(mp4), "thumbnail_path": str(thumb)}
    ]), encoding="utf-8")

    res_pending = cleanup_published_video_if_idle(str(mp4), queue_file=q_file)
    assert res_pending["deleted"] is False
    assert res_pending["reason"] == "pending_in_queue"
    assert mp4.exists()

    # Również cleanup_temp_directory nie kasuje oczekującego pliku
    stats_pending = cleanup_temp_directory(temp_dir=temp_dir, queue_file=q_file, batches_dir=batches_dir)
    assert stats_pending["removed_published"] == 0
    assert mp4.exists()

    # 2. Po zmianie kolejki na 'published' .mp4 znika, ale .meta.json i _thumb.jpg zostają
    q_file.write_text(json.dumps([
        {"id": "tt_p", "platform": "tiktok", "status": "published", "video_path": str(mp4), "thumbnail_path": str(thumb)}
    ]), encoding="utf-8")
    res_idle = cleanup_published_video_if_idle(str(mp4), queue_file=q_file)
    assert res_idle["deleted"] is True
    assert not mp4.exists()
    assert meta.exists() and json.loads(meta.read_text(encoding="utf-8")).get("video_cleaned") is True
    assert thumb.exists()


def test_scheduled_queue_logs_tiktok_web_error_and_falls_back(tmp_path, monkeypatch, capsys):
    from lol_agent.scheduled_queue import check_and_flush_scheduled_posts

    queue_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr("lol_agent.scheduled_queue.QUEUE_FILE", queue_file)
    monkeypatch.setenv("TIKTOK_USE_WEB_STUDIO", "1")

    vid = tmp_path / "short_web_fallback.mp4"
    vid.write_bytes(b"0" * 512)
    queue_file.write_text(json.dumps([
        {
            "id": "tt_fb_1",
            "platform": "tiktok",
            "video_path": str(vid),
            "caption": "Katarina Triple",
            "publish_at": "2020-01-01T00:00:00Z",
            "status": "pending",
            "extra": {"hashtags": ["katarina", "fyp"]},
        }
    ]), encoding="utf-8")

    with patch("lol_agent.tiktok_web_scheduler.schedule_tiktok_via_web_studio", return_value={"success": False, "error": "captcha_blocked"}):
        with patch("lol_agent.tiktok_publisher.upload_tiktok_short", return_value={"success": True, "publish_id": "fb_api_1"}) as mock_api:
            flushed = check_and_flush_scheduled_posts()
            assert flushed == 1
            assert mock_api.call_count == 1

    out = capsys.readouterr().out
    assert "captcha_blocked" in out
    assert not vid.exists()  # Po sukcesie fallbacku plik .mp4 został automatycznie posprzątany!


def test_clamp_cover_timestamp_ms_within_real_clip_duration(tmp_path):
    from lol_agent.tiktok_publisher import _clamp_cover_timestamp_ms
    import cv2

    vid = tmp_path / "short_12s.mp4"
    vid.write_bytes(b"mp4")

    class _FakeCap:
        def __init__(self, _p): pass
        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 60.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 718.0  # ~11.966s
            return 0.0
        def release(self): pass

    with patch.object(cv2, "VideoCapture", _FakeCap):
        # 25220ms na 11.96s klipie musi zostać przycięte do środka filmu (~5384ms)
        clamped = _clamp_cover_timestamp_ms(vid, 25220)
        assert 1000 <= clamped < 11500
        assert _clamp_cover_timestamp_ms(vid, 3380) == 3380







