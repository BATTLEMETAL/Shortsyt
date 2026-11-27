"""
Testy regresyjne Etapu 50:
  - youtube_analytics.fetch_bulk_video_analytics() -> podział na roczne okna dat (bez HTTP 400 startIndex=201),
    agregacja ważona i zachowanie częściowych danych przy błędzie pojedynczego okna
  - lol_montage_director._apply_48h_gate_adjustments() -> realna adaptacja tempa 3 stylów bez psucia layoutu
  - synapsa_overnight_batch -> konsumpcja action_weights, kary za low EVR + slow hook i zwycięzcy stylu
  - scheduled_queue -> rozróżnienie `published_to_inbox` od realnego `published` + licznik ostatnich 14d
  - routers/social.py -> blokada HTTP 409 dla `publish_recommended=False` bez `force_publish=True`
  - routers/system.py -> strażnik `data_integrity` w /system/reliability (degraded przy 0% AVP/EVR, alert TikTok INBOX)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import lol_montage_director as director
from lol_agent import scheduled_queue as sq
from lol_agent import synapsa_overnight_batch as ob
from lol_agent.api import helpers as api_helpers
from lol_agent.api import youtube_analytics as ya
from lol_agent.api.auth import API_PASSWORD
from lol_agent.api.main import app
from lol_agent.api.routers import social as social_router
from lol_agent.api.routers import system as system_router


def test_bulk_analytics_uses_yearly_windows_without_start_index_201_and_aggregates(monkeypatch):
    windows = ya._build_analytics_date_windows("2022-01-01", "2024-06-15")
    assert windows == [
        ("2022-01-01", "2022-12-31"),
        ("2023-01-01", "2023-12-31"),
        ("2024-01-01", "2024-06-15"),
    ]
    assert ya._build_analytics_date_windows("2026-01-01", "2026-11-27") == [("2026-01-01", "2026-11-27")]

    ya.invalidate_analytics_cache()
    captured_calls: List[Dict[str, Any]] = []

    class _FakeExec:
        def __init__(self, kwargs: Dict[str, Any]):
            self.kwargs = kwargs

        def execute(self) -> Dict[str, Any]:
            sd = str(self.kwargs.get("startDate") or "")
            if sd.startswith("2022-"):
                raise RuntimeError("Simulated 400 window failure")
            cols = [
                "video", "views", "engagedViews", "averageViewDuration",
                "averageViewPercentage", "estimatedMinutesWatched",
                "likes", "dislikes", "comments", "shares", "subscribersGained", "subscribersLost",
            ]
            if sd.startswith("2023-"):
                rows = [["vidA", 100, 40, 10.0, 80.0, 20.0, 2, 0, 1, 0, 1, 0]]
            else:
                rows = [["vidA", 300, 180, 14.0, 120.0, 60.0, 8, 1, 2, 1, 3, 0]]
            return {
                "columnHeaders": [{"name": c} for c in cols],
                "rows": rows,
            }

    class _FakeReports:
        def query(self, **kwargs):
            captured_calls.append(kwargs)
            return _FakeExec(kwargs)

    class _FakeYta:
        def reports(self):
            return _FakeReports()

    monkeypatch.setattr(ya, "_get_services", lambda: (object(), _FakeYta(), "UC_TEST"))
    # Przytnij zakres okien testowych do 2022-2024 niezależnie od roku systemowego
    monkeypatch.setattr(
        ya,
        "_build_analytics_date_windows",
        lambda _s, _e: [("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31")],
    )

    out = ya.fetch_bulk_video_analytics(days=3650, force_refresh=True)
    assert len(captured_calls) == 3
    assert all("startIndex" not in c for c in captured_calls)
    assert "vidA" in out
    assert out["vidA"]["views"] == 400
    assert out["vidA"]["engaged_views"] == 220
    assert out["vidA"]["engaged_view_rate_pct"] == 55.0
    assert out["vidA"]["avg_view_pct"] == 110.0  # (80*100 + 120*300) / 400
    assert out["vidA"]["avg_view_duration_s"] == 13.0
    assert out["vidA"]["subscribers_gained"] == 4
    health = ya.get_bulk_analytics_health()
    assert health["cached_videos"] == 1
    assert "2022-01-01..2022-12-31" in str(health["last_error"])

    # Gdy wszystkie okna kończą się sukcesem, last_error wraca na None
    monkeypatch.setattr(
        ya,
        "_build_analytics_date_windows",
        lambda _s, _e: [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31")],
    )
    out_ok = ya.fetch_bulk_video_analytics(days=3650, force_refresh=True)
    assert out_ok["vidA"]["views"] == 400
    assert ya.get_bulk_analytics_health()["last_error"] is None


def test_montage_director_applies_48h_adjustments_to_viral_styles_without_breaking_layout(monkeypatch):
    fake_directive = {
        "post_48h_gate_summary": {
            "director_adjustments_by_action": {
                "double": {"buildup_sec_delta": -0.2, "outro_sec_delta": -0.4},
            }
        },
        "learning_progression": {
            "monthly_2026": {
                "2026-11": {"count": 10, "median_engaged_rate_pct": 44.0},
            }
        },
    }
    monkeypatch.setattr(director, "_get_learning_directive_safe", lambda: fake_directive)

    dec = director.direct_clip_montage(
        action_type="double",
        champion_name="Katarina",
        duration=14.0,
        peaks=[(4.0, "KILL"), (7.0, "DOUBLE KILL")],
        force_style="ARENA_WIDE",
    )
    assert dec.archetype == "ARENA_WIDE"
    assert dec.camera_mode == "arena_wide"
    assert dec.zoom_aggression == 1.08
    assert dec.slowmo_duration == 0.9
    assert dec.buildup_sec == 0.55  # 0.9 - 0.2 (48h) - 0.15 (EVR < 48%)
    assert dec.outro_sec == 1.6     # 2.0 - 0.4 (48h)
    assert dec.tuning_profile["learning_48h_applied"] is True
    assert dec.tuning_profile["learning_48h_adjustments"]["recent_evr_pct"] == 44.0


def test_overnight_scanner_and_style_selector_consume_learning_directive():
    directive = {
        "action_weights": {"double": 0.90, "triple": 1.12},
        "learning_progression": {
            "monthly_2026": {
                "2026-11": {"count": 12, "median_engaged_rate_pct": 44.0},
            }
        },
        "recipe_experiments": {
            "dimensions": {
                "montage_style": {
                    "reliable": True,
                    "winner": "STORY_RAW_POV",
                }
            }
        },
    }
    raw_entry = {
        "clip_start": 0.0,
        "clip_end": 15.0,
        "kills": [
            {"timestamp": 5.5, "tier": 1, "label": "KILL"},
            {"timestamp": 7.5, "tier": 2, "label": "DOUBLE KILL"},
        ],
        "raw_detected_frag_type": "double",
        "confidence": 0.9,
        "min_hp_percentage": 55.0,
        "raw_viable": True,
    }
    base_res = ob._score_and_classify_candidate(raw_entry, directive={})
    learned_res = ob._score_and_classify_candidate(raw_entry, directive=directive)
    assert learned_res["learning_action_multiplier"] == 0.9
    assert learned_res["hype_score"] < base_res["hype_score"]
    assert any("action_mult:double=0.90" in s for s in learned_res["learning_signals_applied"])
    assert any("low_evr_slow_hook" in s for s in learned_res["learning_signals_applied"])

    cand_short_double = {"action_type": "double", "kill_count": 2, "kill_span_s": 2.0}
    st, fb = ob._choose_primary_and_fallback_styles(cand_short_double, montage_preset="auto_fallback", directive=directive)
    assert (st, fb) == ("STORY_RAW_POV", "ARENA_WIDE")


def test_scheduled_queue_marks_tiktok_inbox_as_published_to_inbox_not_published(tmp_path, monkeypatch):
    q_file = tmp_path / "scheduled_social_queue.json"
    monkeypatch.setattr(sq, "QUEUE_FILE", q_file)
    monkeypatch.setenv("TIKTOK_USE_WEB_STUDIO", "0")

    vid_inb = tmp_path / "tt_inbox.mp4"
    vid_pub = tmp_path / "tt_direct.mp4"
    vid_inb.write_bytes(b"inbox")
    vid_pub.write_bytes(b"direct")

    sq.queue_scheduled_post(
        platform="tiktok",
        video_path=str(vid_inb),
        caption="Inbox Clip",
        publish_at="2020-01-01T00:00:00Z",
        extra={"post_mode": "inbox"},
    )
    with monkeypatch.context() as m:
        m.setattr("lol_agent.tiktok_publisher.upload_tiktok_short", lambda **_kw: {
            "success": True,
            "publish_id": "v_inbox_file~v2.999",
            "inbox": True,
            "post_mode": "inbox",
        })
        assert sq.check_and_flush_scheduled_posts() == 1

    items_after_inb = json.loads(q_file.read_text(encoding="utf-8"))
    assert items_after_inb[0]["status"] == "published_to_inbox"
    assert items_after_inb[0]["delivery_mode"] == "inbox_draft"
    assert items_after_inb[0]["requires_manual_publish"] is True
    sum_inb = sq.summarize_queue_statuses(items_after_inb)
    assert sum_inb["published_to_inbox"] == 1
    assert sum_inb["published"] == 0
    assert sq.count_recent_tiktok_inbox(items_after_inb, days=14) == 1

    # Oddzielna kolejka dla prawdziwego Direct Post -> status musi zostać `published`
    q_file2 = tmp_path / "scheduled_social_queue_direct.json"
    monkeypatch.setattr(sq, "QUEUE_FILE", q_file2)
    sq.queue_scheduled_post(
        platform="tiktok",
        video_path=str(vid_pub),
        caption="Direct Clip",
        publish_at="2020-01-01T00:00:00Z",
        extra={"post_mode": "direct"},
    )
    with monkeypatch.context() as m:
        m.setattr("lol_agent.tiktok_publisher.upload_tiktok_short", lambda **_kw: {
            "success": True,
            "publish_id": "pub_direct_123",
            "inbox": False,
            "post_mode": "direct",
        })
        assert sq.check_and_flush_scheduled_posts() == 1

    items_after_pub = json.loads(q_file2.read_text(encoding="utf-8"))
    assert items_after_pub[0]["status"] == "published"
    assert items_after_pub[0]["delivery_mode"] == "public"
    assert items_after_pub[0]["requires_manual_publish"] is False
    sum_pub = sq.summarize_queue_statuses(items_after_pub)
    assert sum_pub["published"] == 1
    assert sum_pub["published_to_inbox"] == 0


def test_social_publish_blocks_not_recommended_without_force_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(social_router, "LOL_TEMP_DIR", tmp_path)
    monkeypatch.setattr(social_router, "LOL_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(social_router, "PUBLISHED_VIDEOS_PATH", tmp_path / "published_videos.jsonl")
    batch_file = tmp_path / "latest_batch.json"
    monkeypatch.setattr(social_router, "LATEST_BATCH_FILE", batch_file)
    monkeypatch.setattr(sq, "QUEUE_FILE", tmp_path / "scheduled_social_queue.json")
    monkeypatch.setattr(social_router, "_save_meta", lambda *_a, **_kw: None)
    monkeypatch.setattr(social_router, "_record_publication", lambda *_a, **_kw: None)
    monkeypatch.setattr(social_router, "_archive_and_schedule_48h", lambda *_a, **_kw: None)

    bad_mp4 = tmp_path / "bad_short.mp4"
    bad_mp4.write_bytes(b"0000")
    batch_only_mp4 = tmp_path / "batch_only.mp4"
    batch_only_mp4.write_bytes(b"1111")

    batch_file.write_text(
        json.dumps({
            "items": [{
                "output_filename": "batch_only.mp4",
                "publish_recommended": False,
                "publish_block_reasons": ["camera_jump_607px>220px"],
            }]
        }),
        encoding="utf-8",
    )

    def _fake_load_meta(fn: str):
        if fn == "bad_short.mp4":
            return {
                "champion_name": "Katarina",
                "action_type": "triple",
                "publish_recommended": False,
                "publish_block_reasons": ["slow_intro_5.1s>4.0s"],
            }
        return {"champion_name": "Katarina", "action_type": "double"}

    monkeypatch.setattr(social_router, "_load_meta", _fake_load_meta)
    calls: List[str] = []

    def _mock_publish(**kwargs):
        calls.append(str(kwargs.get("video_path")))
        return {"youtube": {"success": True, "video_id": "yt_ok", "url": "https://youtu.be/yt_ok"}}

    monkeypatch.setattr(social_router, "publish_multi_platform", _mock_publish)

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        r_block_meta = client.post(
            "/social/publish/bad_short.mp4",
            json={"title": "Test Blocked #shorts", "platforms": ["youtube"]},
            headers=headers,
        )
        assert r_block_meta.status_code == 409
        assert "slow_intro_5.1s>4.0s" in r_block_meta.json()["detail"]

        r_block_batch = client.post(
            "/social/publish/batch_only.mp4",
            json={"title": "Test Batch Blocked #shorts", "platforms": ["youtube"]},
            headers=headers,
        )
        assert r_block_batch.status_code == 409
        assert "camera_jump_607px>220px" in r_block_batch.json()["detail"]
        assert calls == []

        r_force = client.post(
            "/social/publish/bad_short.mp4",
            json={"title": "Test Force #shorts", "platforms": ["youtube"], "force_publish": True},
            headers=headers,
        )
        assert r_force.status_code == 200
        assert len(calls) == 1


def test_system_reliability_flags_empty_yt_analytics_as_degraded_and_reports_tiktok_inbox(tmp_path, monkeypatch):
    acc_dir = tmp_path / "accounts"
    acc_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(system_router, "LOL_AGENT_DIR", tmp_path)
    monkeypatch.setattr(system_router, "ACCOUNTS_DIR", acc_dir)
    monkeypatch.setattr(system_router, "DARK_ROOT", tmp_path)
    monkeypatch.setattr(system_router, "LOL_TEMP_DIR", tmp_path / "lol_temp")

    (tmp_path / "yt_perf_cache.json").write_text(
        json.dumps({
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "videos": [
                {"video_id": f"v{i}", "views": 1200, "avg_view_pct": None, "engaged_view_rate_pct": None}
                for i in range(25)
            ],
        }),
        encoding="utf-8",
    )
    (tmp_path / "learning_directive.json").write_text(
        json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "learning_progression": {
                "monthly_2026": {
                    "2026-11": {"count": 10, "median_engaged_rate_pct": None}
                }
            },
            "synapsa_retrain_status": {"retrain_ready": True, "new_examples_since_train": 12},
        }),
        encoding="utf-8",
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    (acc_dir / "scheduled_social_queue.json").write_text(
        json.dumps([
            {
                "id": "tt_1",
                "platform": "tiktok",
                "status": "published",
                "published_at": now_iso,
                "result": {"success": True, "inbox": True, "publish_id": "v_inbox_file~v2.1"},
            },
            {
                "id": "tt_2",
                "platform": "tiktok",
                "status": "published_to_inbox",
                "published_at": now_iso,
                "result": {"success": True, "inbox": True, "publish_id": "v_inbox_file~v2.2"},
            },
        ]),
        encoding="utf-8",
    )

    monkeypatch.setattr("lol_agent.api.youtube_uploader.get_token_status", lambda: {"is_valid": True, "days_remaining": 7})
    monkeypatch.setattr("lol_agent.tiktok_publisher.get_tiktok_token_status", lambda: {"valid": True, "days_remaining": 300})
    monkeypatch.setattr("lol_agent.instagram_publisher.get_instagram_token_status", lambda: {"valid": True})
    monkeypatch.setattr("lol_agent.facebook_publisher.get_facebook_token_status", lambda: {"valid": True})
    monkeypatch.setattr("lol_agent.api.youtube_analytics.get_bulk_analytics_health", lambda: {"cached_videos": 0, "last_error": None})

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        res = client.get("/system/reliability", headers=headers)
        assert res.status_code == 200
        body = res.json()

    assert body["status"] == "degraded"
    di = body["data_integrity"]
    assert di["yt_perf_cache"]["ok"] is False
    assert di["yt_perf_cache"]["total_videos"] == 25
    assert di["yt_perf_cache"]["videos_with_avp"] == 0
    assert di["learning_directive"]["ok"] is False
    assert di["tiktok_inbox_recent_14d"] == 2
    assert body["queue"]["published_to_inbox"] == 2
    assert body["queue"]["published"] == 0
    warnings_joined = " | ".join(body["warnings"])
    assert "yt_perf_cache.json" in warnings_joined
    assert "learning_directive.json" in warnings_joined
    assert "INBOX" in warnings_joined


def test_sync_youtube_analytics_preserves_prev_metrics_when_bulk_fails(tmp_path, monkeypatch):
    from types import SimpleNamespace

    prev_metrics = {
        "avg_view_pct": 112.5,
        "engaged_views": 840,
        "engaged_view_rate_pct": 51.2,
        "watch_time_hours": 12.4,
        "shares": 3,
        "subscribers_gained": 4,
        "retention": "112.5%",
    }
    kept = api_helpers._merge_yt_analytics_metrics({}, prev_metrics, None)
    assert kept["avg_view_pct"] == 112.5
    assert kept["engaged_view_rate_pct"] == 51.2
    assert kept["subscribers_gained"] == 4
    assert kept["retention"] == "112.5%"

    updated = api_helpers._merge_yt_analytics_metrics(
        {"avg_view_pct": 120.0, "subscribers_gained": 6},
        prev_metrics,
        None,
    )
    assert updated["avg_view_pct"] == 120.0
    assert updated["subscribers_gained"] == 6
    assert updated["engaged_view_rate_pct"] == 51.2
    assert updated["retention"] == "120.0%"

    fake_api_dir = tmp_path / "api"
    fake_api_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(api_helpers, "__file__", str(fake_api_dir / "helpers.py"))
    cache_path = tmp_path / "yt_perf_cache.json"
    cache_path.write_text(
        json.dumps({
            "channel": {"channel_title": "Test"},
            "videos": [{"video_id": "vid_keep", **prev_metrics}],
            "synced_timestamp": 0,
        }),
        encoding="utf-8",
    )

    class _FakeExec:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class _FakeChannels:
        def list(self, **_kwargs):
            return _FakeExec({
                "items": [{
                    "snippet": {"title": "Dwannellenga"},
                    "statistics": {"subscriberCount": "100", "viewCount": "500000", "videoCount": "1"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU_TEST"}},
                }]
            })

    class _FakePlaylistItems:
        def list(self, **_kwargs):
            return _FakeExec({"items": [{"contentDetails": {"videoId": "vid_keep"}}]})

    class _FakeVideos:
        def list(self, **_kwargs):
            return _FakeExec({
                "items": [{
                    "id": "vid_keep",
                    "snippet": {"title": "Katarina Triple #shorts", "publishedAt": "2026-11-25T12:00:00Z"},
                    "statistics": {"viewCount": "2400", "likeCount": "60", "commentCount": "5"},
                }]
            })

    class _FakeYouTube:
        def channels(self):
            return _FakeChannels()

        def playlistItems(self):
            return _FakePlaylistItems()

        def videos(self):
            return _FakeVideos()

    monkeypatch.setattr(
        "lol_agent.api.youtube_uploader._load_credentials",
        lambda: SimpleNamespace(valid=True, refresh_token="dummy"),
    )
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *_a, **_kw: _FakeYouTube())

    def _boom_bulk(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("lol_agent.api.youtube_analytics.fetch_bulk_video_analytics", _boom_bulk)
    monkeypatch.setattr(
        "lol_agent.api.youtube_analytics.fetch_video_retention_data",
        lambda *_a, **_kw: {"status": "no_data"},
    )

    res = api_helpers._sync_youtube_analytics(force=True)
    assert len(res["videos"]) == 1
    vid = res["videos"][0]
    assert vid["views"] == 2400
    assert vid["avg_view_pct"] == 112.5
    assert vid["engaged_view_rate_pct"] == 51.2
    assert vid["subscribers_gained"] == 4
    assert vid["retention"] == "112.5%"

    on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
    assert on_disk["videos"][0]["avg_view_pct"] == 112.5
    assert on_disk["videos"][0]["engaged_view_rate_pct"] == 51.2
    assert on_disk["videos"][0]["subscribers_gained"] == 4
