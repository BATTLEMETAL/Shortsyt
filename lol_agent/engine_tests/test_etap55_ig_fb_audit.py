"""
Testy Etapu 55 (55.1 Instagram Reels + 55.2 Facebook Page Reels):
- Pełna paginacja Meta Graph API v21.0 w social_analytics.py (40 mediów IG, 43 wideo FB)
- Czytanie instagram_account_id + zbieranie saved, shares, avg_watch_time_s, skip_rate_pct z fallbackiem
- Poprawne pola FB v21.0 (likes.summary, comments.summary, bez nieistniejącego reactions) i flaga read_insights
- fetch_instagram_reel_metrics / fetch_facebook_reel_metrics w platform_feedback_collector.py (v21.0, bez plays/reactions/shares)
- Pełna agregacja learning_instagram.json i learning_facebook.json + usuwanie fałszywego _warning
- Inferencja action_type w _load_queue_social_entries z .meta.json i nazwy pliku
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import platform_feedback_collector as pfc
from lol_agent import social_analytics as sa


class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


def test_get_instagram_analytics_paginates_all_40_and_extracts_extended_insights(tmp_path, monkeypatch):
    tok_file = tmp_path / "instagram_token.json"
    tok_file.write_text(
        json.dumps(
            {
                "access_token": "ig_tok_test",
                "instagram_account_id": "17841499999999999",
                "scopes": ["instagram_basic", "instagram_manage_insights"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sa, "ACCOUNTS_DIR", tmp_path)
    monkeypatch.setattr(sa, "IG_TOKEN_FILE", tok_file)
    monkeypatch.setattr(sa, "IG_CACHE_FILE", tmp_path / "ig_cache.json")

    page1_media = [
        {
            "id": f"ig_m_{i}",
            "caption": f"Hook #{i} ⚡\n#katarina #leagueoflegends",
            "like_count": 1,
            "comments_count": 0,
            "permalink": f"https://www.instagram.com/reel/R{i}/",
            "timestamp": "2026-11-27T10:00:00+0000",
            "media_type": "VIDEO",
            "media_product_type": "REELS",
        }
        for i in range(25)
    ]
    page2_media = [
        {
            "id": f"ig_m_{i}",
            "caption": f"Old Hook #{i}\n#lol",
            "like_count": 2,
            "comments_count": 1,
            "permalink": f"https://www.instagram.com/reel/R{i}/",
            "timestamp": "2026-11-20T10:00:00+0000",
            "media_type": "VIDEO",
            "media_product_type": "REELS",
        }
        for i in range(25, 40)
    ]

    ext_calls = []

    def _fake_get(url, params=None, timeout=12):
        assert "/v21.0/" in url or "next_page=2" in url
        if url == "https://graph.facebook.com/v21.0/17841499999999999":
            return _FakeResp(
                {
                    "username": "dwannellenga",
                    "name": "Dwannellenga",
                    "followers_count": 5,
                    "follows_count": 1,
                    "media_count": 40,
                    "profile_picture_url": "",
                }
            )
        if url == "https://graph.facebook.com/v21.0/17841499999999999/media":
            return _FakeResp(
                {
                    "data": page1_media,
                    "paging": {"next": "https://graph.facebook.com/v21.0/17841499999999999/media?next_page=2"},
                }
            )
        if "next_page=2" in url:
            return _FakeResp({"data": page2_media})
        if url.endswith("/insights"):
            metric = (params or {}).get("metric", "")
            mid = url.split("/")[-2]
            ext_calls.append((mid, metric))
            # Dla ig_m_39 symulujemy brak rozszerzonych metryk i sprawdzamy fallback bazowy
            if mid == "ig_m_39" and "reels_skip_rate" in metric:
                return _FakeResp({"error": {"message": "unsupported for legacy media", "code": 100}})
            if "reels_skip_rate" in metric:
                return _FakeResp(
                    {
                        "data": [
                            {"name": "views", "values": [{"value": 200}]},
                            {"name": "reach", "values": [{"value": 150}]},
                            {"name": "saved", "values": [{"value": 3}]},
                            {"name": "shares", "values": [{"value": 2}]},
                            {"name": "total_interactions", "values": [{"value": 6}]},
                            {"name": "ig_reels_avg_watch_time", "values": [{"value": 8500}]},
                            {"name": "ig_reels_video_view_total_time", "values": [{"value": 500000}]},
                            {"name": "reels_skip_rate", "values": [{"value": 24.5}]},
                        ]
                    }
                )
            return _FakeResp(
                {
                    "data": [
                        {"name": "views", "values": [{"value": 100}]},
                        {"name": "reach", "values": [{"value": 80}]},
                        {"name": "saved", "values": [{"value": 1}]},
                        {"name": "shares", "values": [{"value": 1}]},
                        {"name": "total_interactions", "values": [{"value": 4}]},
                    ]
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(sa.requests, "get", _fake_get)
    res = sa.get_instagram_analytics(force_refresh=True)

    assert res["connected"] is True
    assert res["count"] == 40
    assert res["media_count_mismatch"] is False
    assert res["insights_errors"] == 0
    assert res["total_views"] == 39 * 200 + 100
    assert res["total_reach"] == 39 * 150 + 80
    assert res["total_saved"] == 39 * 3 + 1
    assert res["total_shares"] == 39 * 2 + 1
    assert res["avg_watch_time_s"] == 8.5
    assert res["avg_skip_rate_pct"] == 24.5
    assert any(m == "ig_m_39" and "reels_skip_rate" not in met for m, met in ext_calls)


def test_get_facebook_analytics_paginates_43_uses_likes_summary_and_flags_missing_read_insights(tmp_path, monkeypatch):
    tok_file = tmp_path / "facebook_token.json"
    tok_file.write_text(
        json.dumps(
            {
                "access_token": "fb_tok_test",
                "page_id": "1398423656686108",
                "scopes": ["pages_read_engagement", "pages_manage_posts"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sa, "ACCOUNTS_DIR", tmp_path)
    monkeypatch.setattr(sa, "FB_TOKEN_FILE", tok_file)
    monkeypatch.setattr(sa, "FB_CACHE_FILE", tmp_path / "fb_cache.json")

    def _make_vid(idx: int) -> dict:
        return {
            "id": f"fb_v_{idx}",
            "description": f"Clip {idx}\n#leagueoflegends #katarina",
            "permalink_url": f"/reel/fb_v_{idx}/",
            "created_time": "2026-11-27T21:00:00+0000",
            "length": 12.5,
            "views": 3 if idx < 30 else 1,
            "likes": {"summary": {"total_count": 1 if idx < 13 else 0}},
            "comments": {"summary": {"total_count": 0}},
        }

    p1 = [_make_vid(i) for i in range(25)]
    p2 = [_make_vid(i) for i in range(25, 43)]
    requested_fields = []

    def _fake_get(url, params=None, timeout=12):
        if params and "fields" in params:
            requested_fields.append(params["fields"])
            assert "reactions" not in params["fields"]
        if url == "https://graph.facebook.com/v21.0/1398423656686108":
            return _FakeResp({"name": "Dwannellenga", "followers_count": 2, "fan_count": 2, "picture": {"data": {"url": ""}}})
        if url == "https://graph.facebook.com/v21.0/1398423656686108/videos":
            return _FakeResp({"data": p1, "paging": {"next": "https://graph.facebook.com/v21.0/1398423656686108/videos?after=abc"}})
        if "after=abc" in url:
            return _FakeResp({"data": p2})
        raise AssertionError(f"Unexpected N+1 or unknown URL: {url}")

    monkeypatch.setattr(sa.requests, "get", _fake_get)
    res = sa.get_facebook_analytics(force_refresh=True)

    assert res["connected"] is True
    assert res["count"] == 43
    assert res["total_views"] == 30 * 3 + 13 * 1
    assert res["total_likes"] == 13
    assert res["total_reactions"] == 13
    assert res["has_read_insights_permission"] is False
    assert "read_insights" in (res["metrics_limitation"] or "")
    assert res["videos"][0]["url"] == "https://www.facebook.com/reel/fb_v_0/"
    assert res["videos"][0]["length_s"] == 12.5


def test_fetch_ig_and_fb_metrics_use_v21_valid_fields(tmp_path, monkeypatch):
    ig_tok = tmp_path / "instagram_token.json"
    ig_tok.write_text(json.dumps({"access_token": "ig_t"}), encoding="utf-8")
    fb_tok = tmp_path / "facebook_token.json"
    fb_tok.write_text(json.dumps({"access_token": "fb_t", "scopes": ["pages_read_engagement"]}), encoding="utf-8")
    monkeypatch.setattr(pfc, "IG_TOKEN_FILE", ig_tok)
    monkeypatch.setattr(pfc, "FB_TOKEN_FILE", fb_tok)

    seen_calls = []

    def _fake_get(url, params=None, timeout=10):
        seen_calls.append((url, dict(params or {})))
        assert "/v21.0/" in url
        if url.endswith("/ig_123"):
            return _FakeResp({"like_count": 4, "comments_count": 1, "permalink": "https://ig/r/1", "caption": "Best Dagger\n#katarina #lol"})
        if url.endswith("/ig_123/insights"):
            assert "plays" not in (params or {}).get("metric", "")
            return _FakeResp(
                {
                    "data": [
                        {"name": "views", "values": [{"value": 240}]},
                        {"name": "reach", "values": [{"value": 160}]},
                        {"name": "saved", "values": [{"value": 2}]},
                        {"name": "shares", "values": [{"value": 1}]},
                        {"name": "total_interactions", "values": [{"value": 8}]},
                        {"name": "ig_reels_avg_watch_time", "values": [{"value": 9100}]},
                        {"name": "ig_reels_video_view_total_time", "values": [{"value": 600000}]},
                        {"name": "reels_skip_rate", "values": [{"value": 19.5}]},
                    ]
                }
            )
        if url.endswith("/fb_456"):
            flds = (params or {}).get("fields", "")
            assert "reactions" not in flds and "shares" not in flds
            return _FakeResp(
                {
                    "views": 18,
                    "description": "Turret Trap\n#leagueoflegends #katarina",
                    "permalink_url": "/reel/fb_456/",
                    "length": 11.2,
                    "likes": {"summary": {"total_count": 3}},
                    "comments": {"summary": {"total_count": 1}},
                }
            )
        raise AssertionError(f"Unexpected GET: {url}")

    monkeypatch.setattr(pfc.requests, "get", _fake_get)

    ig_m = pfc.fetch_instagram_reel_metrics("ig_123")
    assert ig_m is not None
    assert ig_m["views"] == 240 and ig_m["reach"] == 160 and ig_m["saved"] == 2 and ig_m["shares"] == 1
    assert ig_m["avg_watch_time_s"] == 9.1 and ig_m["skip_rate_pct"] == 19.5 and ig_m["insights_ok"] is True

    fb_m = pfc.fetch_facebook_reel_metrics("fb_456")
    assert fb_m is not None
    assert fb_m["views"] == 18 and fb_m["likes"] == 3 and fb_m["reactions"] == 3 and fb_m["comments"] == 1
    assert fb_m["permalink_url"] == "https://www.facebook.com/reel/fb_456/"
    assert fb_m["has_read_insights_permission"] is False


def test_ingest_ig_and_fb_populate_learning_summaries_and_clear_stale_warning(tmp_path, monkeypatch):
    states = tmp_path / "learning_states"
    states.mkdir(parents=True)
    # Wstrzyknij stary fałszywy _warning do learning_instagram.json
    (states / "learning_instagram.json").write_text(
        json.dumps(
            {
                "_schema_version": 1,
                "_warning": "instagram_manage_insights permission is currently MISSING from token.",
                "videos_analysed": 0,
                "metrics_collected": {"entries": []},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pfc, "LEARNING_STATES_DIR", states)

    pfc.ingest_instagram_metric(
        {
            "media_id": "m1",
            "views": 450,
            "reach": 300,
            "likes": 9,
            "comments": 1,
            "caption": "Never Chase Katarina 🔥\n#katarina #leagueoflegends",
            "avg_watch_time_s": 9.2,
            "skip_rate_pct": 18.0,
            "insights_ok": True,
        },
        action_type="double",
    )
    # Powtórzenie tego samego media_id aktualizuje wpis bez podwójnego videos_analysed
    pfc.ingest_instagram_metric(
        {
            "media_id": "m1",
            "views": 500,
            "reach": 330,
            "likes": 10,
            "comments": 1,
            "caption": "Never Chase Katarina 🔥\n#katarina #leagueoflegends",
            "avg_watch_time_s": 9.4,
            "skip_rate_pct": 17.5,
            "insights_ok": True,
        },
        action_type="double",
    )

    ig_state = json.loads((states / "learning_instagram.json").read_text(encoding="utf-8"))
    assert "_warning" not in ig_state
    assert ig_state["videos_analysed"] == 1
    assert ig_state["retention_summary"]["avg_views"] == 500.0
    assert ig_state["retention_summary"]["avg_watch_time_s"] == 9.4
    assert ig_state["retention_summary"]["samples_with_insights"] == 1
    assert ig_state["caption_patterns"]["top_hooks"][0]["hook"] == "Never Chase Katarina 🔥"
    assert ig_state["hashtag_performance"]["by_tag"]["katarina"]["avg_views"] == 500.0
    assert ig_state["action_type_weights"]["double"] == 1.05

    pfc.ingest_facebook_metric(
        {
            "video_id": "fb1",
            "views": 28,
            "likes": 2,
            "reactions": 2,
            "comments": 0,
            "description": "Turret Outplay\n#katarina #reels",
            "has_read_insights_permission": False,
        },
        action_type="triple",
        pub_ts="2026-11-27T21:00:00Z",
    )
    fb_state = json.loads((states / "learning_facebook.json").read_text(encoding="utf-8"))
    assert fb_state["videos_analysed"] == 1
    assert "read_insights" in fb_state["_warning"]
    assert fb_state["post_patterns"]["top_posts"][0]["title"] == "Turret Outplay"
    assert fb_state["hashtag_performance"]["by_tag"]["reels"]["count"] == 1
    assert fb_state["best_post_time"]["best_hour"] == 22


def test_load_queue_social_entries_infers_action_type_when_extra_empty(tmp_path):
    v_path = tmp_path / "short_overnight_20261126_152000_00144_r2_double.mp4"
    v_path.write_bytes(b"mp4")
    v_path.with_suffix(".meta.json").write_text(json.dumps({"action_type": "triple"}), encoding="utf-8")
    v2_path = tmp_path / "short_20261127_r1_quadra.mp4"

    q_file = tmp_path / "scheduled_social_queue.json"
    q_file.write_text(
        json.dumps(
            [
                {
                    "id": "ig_a",
                    "platform": "instagram",
                    "status": "published",
                    "video_path": str(v_path),
                    "published_at": "2026-11-28T08:01:00Z",
                    "extra": {},
                    "result": {"success": True, "media_id": "ig_1"},
                },
                {
                    "id": "fb_a",
                    "platform": "facebook",
                    "status": "published",
                    "video_path": str(v2_path),
                    "published_at": "2026-11-28T08:02:00Z",
                    "extra": {},
                    "result": {"success": True, "video_id": "fb_1"},
                },
            ]
        ),
        encoding="utf-8",
    )

    ig_entries, fb_entries = pfc._load_queue_social_entries(q_file, set(), set(), max_videos=10)
    assert ig_entries[0]["action_type"] == "triple"  # z .meta.json
    assert fb_entries[0]["action_type"] == "quadrakill"  # z nazwy pliku
