"""
Testy regresyjne Etapu 51:
  - platform_feedback_collector: odczyt 3-kolumnowego YTA v2, deduplikacja po video_id oraz
    zbieranie ID Instagrama i Facebooka z scheduled_social_queue.json
  - instagram_publisher / facebook_publisher: 60s TTL cache statusu tokena i force_refresh
  - routers/clips.py: pojedynczy os.walk z pominięciem Recently Deleted, 15s TTL cache i invalidate
  - run_lol_agent.check_duplicate_clip: cache MD5 / processed_hashes.json / published_videos.jsonl z inwalidacją
  - api/helpers._sync_youtube_analytics: 600s TTL zgrany z _tracker_loop
  - kontrakt OpenAPI (FastAPI app.routes) <-> shortsyt-desktop/src/lib/api.ts
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import facebook_publisher as fb_pub
from lol_agent import instagram_publisher as ig_pub
from lol_agent import platform_feedback_collector as pfc
from lol_agent.api import helpers as api_helpers
from lol_agent.api.auth import API_PASSWORD
from lol_agent.api.main import app
from lol_agent.api.routers import clips as clips_router


def _import_real_run_lol_agent(monkeypatch):
    """Ładuje prawdziwy moduł run_lol_agent nawet jeśli wcześniejsze testy użyły stubów _stubs.py."""
    from lol_agent import lol_config as real_cfg
    monkeypatch.setitem(sys.modules, "lol_config", real_cfg)
    hw_mod = sys.modules.get("hardware_accel")
    if hw_mod is not None and not getattr(hw_mod, "__file__", None):
        from lol_agent import hardware_accel as real_hw
        monkeypatch.setitem(sys.modules, "hardware_accel", real_hw)
    from lol_agent import run_lol_agent
    return run_lol_agent


def test_feedback_collector_reads_3col_yta_and_deduplicates_yt_and_reads_queue_ig_fb(tmp_path, monkeypatch):
    # Bug 1: _extract_yta_video_metrics_row + fetch_youtube_video_metrics dla 3 kolumn YTA
    assert pfc._extract_yta_video_metrics_row({"rows": [[1200, 35.5, 18.2]]}) == (35.5, 18.2)
    assert pfc._extract_yta_video_metrics_row({
        "columnHeaders": [{"name": "views"}, {"name": "averageViewDuration"}, {"name": "estimatedMinutesWatched"}],
        "rows": [[900, 19.4, 22.1]],
    }) == (22.1, 19.4)

    fake_pickle = tmp_path / "lol_token.pickle"
    fake_pickle.write_bytes(b"pickle-stub")
    monkeypatch.setattr(pfc, "TOKEN_PICKLE", fake_pickle)
    monkeypatch.setattr("pickle.load", lambda _f: SimpleNamespace(valid=True))

    fake_yt = MagicMock()
    fake_yt.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"snippet": {"title": "Kat Quadra", "publishedAt": "2026-11-20T12:00:00Z"}, "statistics": {"viewCount": "1200", "likeCount": "40", "commentCount": "3"}}]
    }
    fake_yt.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "UC123"}]}
    fake_yta = MagicMock()
    fake_yta.reports.return_value.query.return_value.execute.return_value = {"rows": [[1200, 35.5, 18.2]]}
    monkeypatch.setattr("googleapiclient.discovery.build", lambda svc, *_a, **_kw: fake_yt if svc == "youtube" else fake_yta)

    yt_res = pfc.fetch_youtube_video_metrics("vid_3col")
    assert yt_res is not None
    assert yt_res["estimated_minutes_watched"] == 35.5
    assert yt_res["avg_view_duration"] == 18.2

    # Bug 2: deduplikacja powtórnych sprawdzeń tego samego video_id w ingest_youtube_metric
    states_dir = tmp_path / "learning_states"
    monkeypatch.setattr(pfc, "LEARNING_STATES_DIR", states_dir)
    pfc.ingest_youtube_metric(
        {"video_id": "vid_dup_1", "views": 1000, "title": "Kata #shorts", "avg_view_duration": 15.0},
        action_type="triple",
        pub_ts="2026-11-27T15:00:00Z",
    )
    pfc.ingest_youtube_metric(
        {"video_id": "vid_dup_1", "views": 1450, "title": "Kata #shorts", "avg_view_duration": 16.2},
        action_type="triple",
        pub_ts="2026-11-27T15:00:00Z",
    )
    lyt = json.loads((states_dir / "learning_youtube.json").read_text(encoding="utf-8"))
    assert lyt["videos_analysed"] == 1
    assert len(lyt["title_patterns"]["top_performers"]) == 1
    assert lyt["title_patterns"]["top_performers"][0]["views"] == 1450
    assert lyt["publish_time"]["hour_stats"]["16"]["count"] == 1
    assert lyt["publish_time"]["hour_stats"]["16"]["views_total"] == 1450

    # Bug 3: zbieranie ID IG i FB z scheduled_social_queue.json w collect_all_platform_metrics
    pub_log = tmp_path / "published_videos.jsonl"
    pub_log.write_text("", encoding="utf-8")
    q_file = tmp_path / "scheduled_social_queue.json"
    q_file.write_text(
        json.dumps([
            {
                "id": "ig_1",
                "platform": "instagram",
                "status": "published",
                "published_at": "2026-11-27T10:01:00+00:00",
                "result": {"success": True, "media_id": "ig_q_1"},
                "extra": {"action_type": "quadra"},
            },
            {
                "id": "fb_1",
                "platform": "facebook",
                "status": "published",
                "published_at": "2026-11-27T10:02:00+00:00",
                "result": {"success": True, "video_id": "fb_q_1"},
                "extra": {"action_type": "double"},
            },
            {
                "id": "ig_pending",
                "platform": "instagram",
                "status": "pending",
                "result": {"media_id": "ig_should_skip"},
            },
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(pfc, "PUB_LOG_FILE", pub_log)
    monkeypatch.setattr(pfc, "SCHEDULED_QUEUE_FILE", q_file)
    monkeypatch.setattr(pfc, "ACCOUNTS_DIR", tmp_path)
    monkeypatch.setattr(pfc, "fetch_instagram_reel_metrics", lambda mid: {"media_id": mid, "reach": 700, "likes": 12})
    monkeypatch.setattr(pfc, "fetch_facebook_reel_metrics", lambda fid: {"video_id": fid, "views": 320, "reactions": 5})

    rep = pfc.collect_all_platform_metrics(max_videos=5)
    assert rep["instagram_updated"] == 1
    assert rep["facebook_updated"] == 1
    assert (states_dir / "learning_instagram.json").exists()
    assert (states_dir / "learning_facebook.json").exists()


def test_ig_fb_token_status_ttl_cache_and_force_refresh(tmp_path, monkeypatch):
    ig_tok = tmp_path / "instagram_token.json"
    ig_tok.write_text(json.dumps({"access_token": "tok_ig_1234567890", "instagram_account_id": "ig_id_1"}), encoding="utf-8")
    fb_tok = tmp_path / "facebook_token.json"
    fb_tok.write_text(json.dumps({"access_token": "tok_fb_1234567890", "page_id": "fb_id_1"}), encoding="utf-8")

    monkeypatch.setattr(ig_pub, "_token_path", lambda: ig_tok)
    monkeypatch.setattr(fb_pub, "_token_path", lambda: fb_tok)
    ig_pub.invalidate_instagram_token_status_cache()
    fb_pub.invalidate_facebook_token_status_cache()

    calls = {"ig": 0, "fb": 0}

    def _fake_get(url, **_kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "ig_id_1" in url:
            calls["ig"] += 1
            resp.json.return_value = {"username": "dwannellenga"}
        else:
            calls["fb"] += 1
            resp.json.return_value = {"name": "Dwannellenga", "fan_count": 42}
        return resp

    monkeypatch.setattr(ig_pub.requests, "get", _fake_get)
    monkeypatch.setattr(fb_pub.requests, "get", _fake_get)

    assert ig_pub.get_instagram_token_status(_use_cache=True)["valid"] is True
    assert ig_pub.get_instagram_token_status(_use_cache=True)["valid"] is True
    assert calls["ig"] == 1
    assert ig_pub.get_instagram_token_status(force_refresh=True, _use_cache=True)["valid"] is True
    assert calls["ig"] == 2

    assert fb_pub.get_facebook_token_status(_use_cache=True)["valid"] is True
    assert fb_pub.get_facebook_token_status(_use_cache=True)["valid"] is True
    assert calls["fb"] == 1
    fb_pub.invalidate_facebook_token_status_cache()
    assert fb_pub.get_facebook_token_status(_use_cache=True)["valid"] is True
    assert calls["fb"] == 2


def test_clips_scan_single_walk_skips_recently_deleted_and_uses_cache(tmp_path, monkeypatch):
    match_dir = tmp_path / "Match_1"
    trash_dir = tmp_path / "Recently Deleted"
    match_dir.mkdir(parents=True)
    trash_dir.mkdir(parents=True)

    payload_3mb = b"0" * (3 * 1024 * 1024 + 64)
    (match_dir / "play_1.mp4").write_bytes(payload_3mb)
    (trash_dir / "deleted_1.mp4").write_bytes(payload_3mb)

    run_lol_agent = _import_real_run_lol_agent(monkeypatch)
    monkeypatch.setattr(clips_router, "load_outplayed_index", lambda: {})
    monkeypatch.setattr(run_lol_agent, "check_duplicate_clip", lambda *_a, **_kw: (False, "", {}))
    clips_router.invalidate_clips_cache()

    first = clips_router.scan_available_clips(str(tmp_path), _use_cache=True)
    assert [c["filename"] for c in first] == ["play_1.mp4"]

    (match_dir / "play_2.mp4").write_bytes(payload_3mb)
    cached = clips_router.scan_available_clips(str(tmp_path), _use_cache=True)
    assert [c["filename"] for c in cached] == ["play_1.mp4"]

    refreshed = clips_router.scan_available_clips(str(tmp_path), force_refresh=True, _use_cache=True)
    assert sorted(c["filename"] for c in refreshed) == ["play_1.mp4", "play_2.mp4"]

    # Endpoint /clips?refresh=true zwalnia cache
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        r = client.get(f"/clips?folder={tmp_path}&refresh=true", headers=headers)
        assert r.status_code == 200
        assert sorted(c["filename"] for c in r.json()["clips"]) == ["play_1.mp4", "play_2.mp4"]


def test_check_duplicate_clip_caches_files_and_invalidates_on_change(tmp_path, monkeypatch):
    run_lol_agent = _import_real_run_lol_agent(monkeypatch)
    monkeypatch.setattr(run_lol_agent, "__file__", str(tmp_path / "run_lol_agent.py"))
    run_lol_agent._CLIP_HASH_CACHE.clear()
    run_lol_agent._PROCESSED_HASHES_CACHE.update({"path": "", "mtime_ns": -1, "size": -1, "raw": {}, "by_name": {}, "by_stem": {}})
    run_lol_agent._PUB_LOG_DEDUP_CACHE.update({"path": "", "mtime_ns": -1, "size": -1, "items": []})

    clip_path = tmp_path / "katarina_clip_01.mp4"
    clip_path.write_bytes(b"test-clip-bytes-123456")
    proc_file = tmp_path / "processed_hashes.json"
    proc_file.write_text(json.dumps({}), encoding="utf-8")

    load_calls = {"count": 0}
    orig_loader = run_lol_agent._load_processed_hashes_cached

    def _spy_loader(p):
        before_mtime = run_lol_agent._PROCESSED_HASHES_CACHE["mtime_ns"]
        res = orig_loader(p)
        if run_lol_agent._PROCESSED_HASHES_CACHE["mtime_ns"] != before_mtime:
            load_calls["count"] += 1
        return res

    monkeypatch.setattr(run_lol_agent, "_load_processed_hashes_cached", _spy_loader)

    assert run_lol_agent.check_duplicate_clip(str(clip_path))[0] is False
    assert run_lol_agent.check_duplicate_clip(str(clip_path))[0] is False
    assert load_calls["count"] == 1

    # Modyfikacja pliku processed_hashes.json wymusza re-parsowanie i wykrywa duplikat
    proc_file.write_text(
        json.dumps({"other_hash": {"source": "katarina_clip_01.mp4", "url": "https://youtu.be/abc"}}),
        encoding="utf-8",
    )
    os.utime(proc_file, ns=(proc_file.stat().st_atime_ns, proc_file.stat().st_mtime_ns + 1_000_000))
    is_dup, _reason, info = run_lol_agent.check_duplicate_clip(str(clip_path))
    assert is_dup is True
    assert info["url"] == "https://youtu.be/abc"
    assert load_calls["count"] == 2


def test_sync_youtube_analytics_uses_600s_ttl(tmp_path, monkeypatch):
    fake_api_dir = tmp_path / "api"
    fake_api_dir.mkdir(parents=True)
    monkeypatch.setattr(api_helpers, "__file__", str(fake_api_dir / "helpers.py"))
    (tmp_path / "yt_perf_cache.json").write_text(
        json.dumps({
            "channel": {"channel_title": "Dwannellenga"},
            "videos": [{"video_id": "v_cached", "views": 3210}],
            "synced_timestamp": time.time() - 300,
        }),
        encoding="utf-8",
    )

    def _should_not_call():
        raise AssertionError("Nie powinien wywoływać API przed upływem 600s TTL")

    monkeypatch.setattr("lol_agent.api.youtube_uploader._load_credentials", _should_not_call)
    res = api_helpers._sync_youtube_analytics(force=False)
    assert res["videos"][0]["video_id"] == "v_cached"
    assert res["videos"][0]["views"] == 3210


def test_frontend_api_ts_contract_matches_fastapi_routes():
    backend_paths = {
        re.sub(r"\{[^}]+\}", "{param}", path)
        for path in app.openapi().get("paths", {}).keys()
    }

    api_ts = (ROOT / "shortsyt-desktop" / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
    url_hits = re.findall(r"['\"`](/[a-zA-Z0-9_\-/{}$.?=&:]+)['\"`]", api_ts)
    unmatched = []
    for raw in sorted(set(url_hits)):
        if raw in ("/", "/api") or raw.startswith("//"):
            continue
        base = raw.split("?")[0]
        norm = re.sub(r"\$\{[^}]+\}", "{param}", base)
        # W api.ts ścieżki mogą występować z parametrem wbudowanym w template string lub z końcowym `/`
        if norm not in backend_paths and (norm + "{param}") not in backend_paths:
            unmatched.append((raw, norm))

    assert unmatched == []
