"""
Testy Etapu 54:
  Auto-pruning powtarzających się niezaakceptowanych klipów w trybie nocnym:
  - 1 paczka (nawet compare_all_3 = 3 warianty) zachowuje 2. szansę
  - >= 2 paczki z render_ok=True bez publikacji/kolejki -> wykluczenie, usunięcie starych
    short_overnight_*.mp4 + .meta.json + miniaturki, przeniesienie oryginału do Kosza Windows
  - klipy is_favorite=True traktowane identycznie jak zwykłe
  - bezwzględna ochrona klipów zaakceptowanych w published_videos.jsonl lub scheduled_social_queue.json
  - render_ok=False nie zużywa limitu 2 szans
  - ponowny skan i /overnight/catalog respektują dismissed_clips.json
  - brak fallbacku unlink() przy błędzie Kosza Windows + realny smoke SHFileOperationW na Win32
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import scheduled_queue as sq
from lol_agent import synapsa_overnight_batch as ob
from lol_agent import user_learning_memory as ulm
from lol_agent.api import config as api_config
from lol_agent.api.auth import API_PASSWORD
from lol_agent.api.main import app
from lol_agent.api.routers import clips as clips_router
from lol_agent.api.routers import overnight as overnight_router


def _setup_isolated_env(tmp_path: Path, monkeypatch):
    overnight_dir = tmp_path / "overnight_batches"
    overnight_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "outputs"
    temp_dir = tmp_path / "temp"
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    dismissed_file = overnight_dir / "dismissed_clips.json"
    pub_file = tmp_path / "published_videos.jsonl"
    queue_file = tmp_path / "scheduled_social_queue.json"
    queue_file.write_text("[]", encoding="utf-8")
    cache_file = tmp_path / "scan_cache.json"

    monkeypatch.setattr(ob, "OVERNIGHT_DIR", overnight_dir)
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", overnight_dir / "latest_batch.json")
    monkeypatch.setattr(ob, "DISMISSED_CLIPS_FILE", dismissed_file)
    monkeypatch.setattr(ob, "PUBLISHED_VIDEOS_FILE", pub_file)
    monkeypatch.setattr(ob, "SCAN_CACHE_FILE", cache_file)
    monkeypatch.setattr(sq, "QUEUE_FILE", queue_file)
    monkeypatch.setattr(api_config, "LOL_TEMP_DIR", str(temp_dir))
    monkeypatch.setattr(api_config, "LOL_OUTPUT_DIR", str(out_dir))
    monkeypatch.setattr(clips_router, "invalidate_clips_cache", lambda: None)

    return {
        "overnight_dir": overnight_dir,
        "out_dir": out_dir,
        "temp_dir": temp_dir,
        "dismissed_file": dismissed_file,
        "pub_file": pub_file,
        "queue_file": queue_file,
    }


def _mock_fast_analyzer(monkeypatch):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    def _cap_get(prop):
        if prop == 5:
            return 60.0
        if prop == 7:
            return 900.0
        if prop == 3:
            return 1920.0
        if prop == 4:
            return 1080.0
        return 0.0

    mock_cap.get.side_effect = _cap_get
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: mock_cap)

    def _fake_analyze(video_path, *_a, **_kw):
        return SimpleNamespace(
            kills=[
                {"timestamp": 3.0, "label": "KILL", "tier": 1},
                {"timestamp": 4.5, "label": "DOUBLE KILL", "tier": 2},
                {"timestamp": 6.0, "label": "TRIPLE KILL", "tier": 3},
            ],
            detected_frag_type="triple",
            min_hp_percentage=30.0,
            is_clutch_1hp=False,
            objective_secured=False,
            objective_label="",
            ally_banner_blocked=False,
            confidence=0.92,
            suggested_title_hook="TRIPLE KILL",
        )

    monkeypatch.setattr("lol_agent.lol_frag_detector.analyze_clip_frags", _fake_analyze)
    monkeypatch.setattr(
        "lol_agent.lol_frag_detector.compute_optimal_clip_window",
        lambda *_a, **_kw: (1.5, 13.5, 7.0, None),
    )
    monkeypatch.setattr("lol_agent.lol_quality_validator.is_raw_material_viable", lambda **_kw: (True, None, "ok"))
    monkeypatch.setattr(ob, "_check_trailing_survival", lambda *_a, **_kw: False)


def _write_batch(overnight_dir: Path, batch_id: str, items: list[dict]) -> Path:
    bf = overnight_dir / f"batch_{batch_id}.json"
    bf.write_text(json.dumps({"batch_id": batch_id, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    return bf


def _make_clip(tmp_path: Path, name: str, *, is_favorite: bool = False, already_published: bool = False) -> dict:
    p = tmp_path / "src" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake-mp4-data")
    return {
        "filename": name,
        "path": str(p),
        "size_mb": 12.0,
        "modified": 1700000000.0,
        "already_published": already_published,
        "champion": "Katarina",
        "is_favorite": is_favorite,
        "event_tier": "triple",
        "event_tier_rank": 3,
        "event_source": "outplayed_live",
        "best_event_time_s": 7.0,
        "total_kills_in_clip": 3,
        "match_folder": "match_1",
        "match_date": "2026-11-26",
        "clip_base_key": name.lower(),
        "match_kda": "12/2/5",
    }


def test_single_batch_compare_all_3_retains_second_chance(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    _mock_fast_analyzer(monkeypatch)
    clip = _make_clip(tmp_path, "clip_once.mp4")

    _write_batch(
        env["overnight_dir"],
        "20261126_010000_aaaaa",
        [
            {
                "source_filename": "clip_once.mp4",
                "source_path": clip["path"],
                "render_ok": True,
                "output_filename": "short_overnight_b1_r1_triple.mp4",
                "output_path": str(env["temp_dir"] / "short_overnight_b1_r1_triple.mp4"),
                "alternate_renders": [
                    {"output_filename": "short_overnight_b1_r1_triple.mp4", "montage_style": "ARENA_WIDE"},
                    {"output_filename": "short_overnight_b1_r1_triple_alt_beat_velocity.mp4", "montage_style": "BEAT_VELOCITY"},
                    {"output_filename": "short_overnight_b1_r1_triple_alt_story_raw_pov.mp4", "montage_style": "STORY_RAW_POV"},
                ],
            }
        ],
    )

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [clip])
    recycled: list[str] = []
    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", lambda p: (recycled.append(str(p)) or True, "recycled"))

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 0
    assert res["skipped_dismissed"] == 0
    assert [c["filename"] for c in res["selected"]] == ["clip_once.mp4"]
    assert recycled == []
    assert Path(clip["path"]).exists()
    assert not env["dismissed_file"].exists()


def test_two_unaccepted_batches_prunes_artifacts_recycles_source_and_records_rejection(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    clip = _make_clip(tmp_path, "clip_repeat_2x.mp4")

    mp4_1 = env["temp_dir"] / "short_overnight_b1_r1_double.mp4"
    meta_1 = env["temp_dir"] / "short_overnight_b1_r1_double.meta.json"
    thumb_1 = env["temp_dir"] / "short_overnight_b1_r1_double_thumb.jpg"
    mp4_2 = env["out_dir"] / "short_overnight_b2_r1_double.mp4"
    meta_2 = env["out_dir"] / "short_overnight_b2_r1_double.meta.json"
    for f in (mp4_1, meta_1, thumb_1, mp4_2, meta_2):
        f.write_bytes(b"artifact")

    _write_batch(
        env["overnight_dir"],
        "20261125_010000_11111",
        [{
            "source_filename": "clip_repeat_2x.mp4",
            "source_path": clip["path"],
            "render_ok": True,
            "output_filename": mp4_1.name,
            "output_path": str(mp4_1),
            "thumbnail_filename": thumb_1.name,
            "thumbnail_path": str(thumb_1),
        }],
    )
    _write_batch(
        env["overnight_dir"],
        "20261126_010000_22222",
        [{
            "source_filename": "clip_repeat_2x.mp4",
            "source_path": clip["path"],
            "render_ok": True,
            "output_filename": mp4_2.name,
            "output_path": str(mp4_2),
        }],
    )

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [clip])
    recycled: list[str] = []
    rejected_calls: list[tuple] = []

    def _fake_recycle(p: Path):
        recycled.append(str(p))
        p.unlink(missing_ok=True)
        return True, "recycled"

    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", _fake_recycle)
    monkeypatch.setattr(ulm, "record_render_rejected", lambda fn, reason=None, qa_details=None: rejected_calls.append((fn, reason, qa_details)))

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 1
    assert res["pruned_clip_filenames"] == ["clip_repeat_2x.mp4"]
    assert res["skipped_dismissed"] == 1
    assert res["rejection_breakdown"]["REJECT_UNACCEPTED_REPEAT_2X"] == 1
    assert res["selected"] == []
    assert recycled == [clip["path"]]
    assert not Path(clip["path"]).exists()
    for f in (mp4_1, meta_1, thumb_1, mp4_2, meta_2):
        assert not f.exists()

    dismissed = json.loads(env["dismissed_file"].read_text(encoding="utf-8"))["clips"]
    assert "clip_repeat_2x.mp4" in dismissed
    assert dismissed["clip_repeat_2x.mp4"]["source_recycled"] is True
    assert dismissed["clip_repeat_2x.mp4"]["render_count"] == 2
    assert len(rejected_calls) == 1
    assert rejected_calls[0][0] == "clip_repeat_2x.mp4"


def test_favorite_clip_treated_identically_after_two_unaccepted_batches(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    fav_clip = _make_clip(tmp_path, "fav_repeat_2x.mp4", is_favorite=True)

    _write_batch(env["overnight_dir"], "20261125_01", [{"source_filename": "fav_repeat_2x.mp4", "render_ok": True, "output_filename": "short_overnight_f1.mp4"}])
    _write_batch(env["overnight_dir"], "20261126_01", [{"source_filename": "fav_repeat_2x.mp4", "render_ok": True, "output_filename": "short_overnight_f2.mp4"}])

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [fav_clip])
    recycled: list[str] = []
    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", lambda p: (recycled.append(str(p)) or p.unlink(missing_ok=True) or True, "recycled"))
    monkeypatch.setattr(ulm, "record_render_rejected", lambda *_a, **_kw: None)

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 1
    assert recycled == [fav_clip["path"]]
    assert not Path(fav_clip["path"]).exists()
    assert res["selected"] == []


def test_accepted_clips_in_queue_or_published_jsonl_are_strictly_protected(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    q_clip = _make_clip(tmp_path, "queued_repeat_3x.mp4", already_published=False)
    p_clip = _make_clip(tmp_path, "published_repeat_2x.mp4", already_published=True)

    q_mp4 = env["temp_dir"] / "short_overnight_q3.mp4"
    q_mp4.write_bytes(b"keep-queued")
    old_unpicked = env["temp_dir"] / "short_overnight_q1_old.mp4"
    old_unpicked.write_bytes(b"keep-history")

    env["queue_file"].write_text(json.dumps([
        {"id": "tiktok_1", "status": "pending", "video_path": str(q_mp4)},
    ]), encoding="utf-8")
    env["pub_file"].write_text(json.dumps({
        "source_path": p_clip["path"],
        "video_path": str(env["out_dir"] / "short_overnight_pub2.mp4"),
    }) + "\n", encoding="utf-8")

    _write_batch(env["overnight_dir"], "20261124_01", [
        {"source_filename": "queued_repeat_3x.mp4", "render_ok": True, "output_filename": old_unpicked.name, "output_path": str(old_unpicked)},
        {"source_filename": "published_repeat_2x.mp4", "render_ok": True, "output_filename": "short_overnight_pub1.mp4"},
    ])
    _write_batch(env["overnight_dir"], "20261125_01", [
        {"source_filename": "queued_repeat_3x.mp4", "render_ok": True, "output_filename": "short_overnight_q2.mp4"},
        {"source_filename": "published_repeat_2x.mp4", "render_ok": True, "output_filename": "short_overnight_pub2.mp4"},
    ])
    _write_batch(env["overnight_dir"], "20261126_01", [
        {"source_filename": "queued_repeat_3x.mp4", "render_ok": True, "output_filename": q_mp4.name, "output_path": str(q_mp4)},
    ])

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [q_clip, p_clip])
    recycled: list[str] = []
    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", lambda p: (recycled.append(str(p)) or True, "recycled"))

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 0
    assert res["skipped_published"] == 2
    assert recycled == []
    assert Path(q_clip["path"]).exists()
    assert Path(p_clip["path"]).exists()
    assert q_mp4.exists()
    assert not env["dismissed_file"].exists()


def test_failed_renders_do_not_consume_two_batch_limit(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    _mock_fast_analyzer(monkeypatch)
    clip = _make_clip(tmp_path, "clip_one_ok_one_fail.mp4")

    _write_batch(env["overnight_dir"], "20261125_01", [{"source_filename": "clip_one_ok_one_fail.mp4", "render_ok": False, "output_filename": "short_overnight_err.mp4"}])
    _write_batch(env["overnight_dir"], "20261126_01", [{"source_filename": "clip_one_ok_one_fail.mp4", "render_ok": True, "output_filename": "short_overnight_ok1.mp4"}])

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [clip])
    recycled: list[str] = []
    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", lambda p: (recycled.append(str(p)) or True, "recycled"))

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 0
    assert [c["filename"] for c in res["selected"]] == ["clip_one_ok_one_fail.mp4"]
    assert recycled == []


def test_subsequent_scan_and_overnight_catalog_exclude_dismissed_clip(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    _mock_fast_analyzer(monkeypatch)
    dismissed_clip = _make_clip(tmp_path, "already_dismissed.mp4")
    fresh_clip = _make_clip(tmp_path, "fresh_clip.mp4")

    ob._save_dismissed_clips({"already_dismissed.mp4": {"source_filename": "already_dismissed.mp4", "render_count": 2}})
    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [dismissed_clip, fresh_clip])
    monkeypatch.setattr(overnight_router, "scan_available_clips", lambda *_a, **_kw: [dismissed_clip, fresh_clip])

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["skipped_dismissed"] == 1
    assert res["rejection_breakdown"]["REJECT_DISMISSED_REPEAT"] == 1
    assert [c["filename"] for c in res["selected"]] == ["fresh_clip.mp4"]

    client = TestClient(app)
    token = client.post("/auth/login", json={"password": API_PASSWORD}).json()["access_token"]
    cat_resp = client.get("/overnight/catalog", headers={"Authorization": f"Bearer {token}"})
    assert cat_resp.status_code == 200
    body = cat_resp.json()
    assert body["dismissed_count"] == 1
    assert body["total_clips"] == 1


def test_recycle_bin_failure_never_unlinks_source_file(tmp_path, monkeypatch):
    env = _setup_isolated_env(tmp_path, monkeypatch)
    clip = _make_clip(tmp_path, "protected_on_recycle_err.mp4")

    _write_batch(env["overnight_dir"], "20261125_01", [{"source_filename": "protected_on_recycle_err.mp4", "render_ok": True, "output_filename": "short_overnight_r1.mp4"}])
    _write_batch(env["overnight_dir"], "20261126_01", [{"source_filename": "protected_on_recycle_err.mp4", "render_ok": True, "output_filename": "short_overnight_r2.mp4"}])

    monkeypatch.setattr(clips_router, "scan_available_clips", lambda *_a, **_kw: [clip])
    monkeypatch.setattr(ob, "_move_file_to_recycle_bin", lambda _p: (False, "shfileop_rc_5_aborted_False"))
    monkeypatch.setattr(ulm, "record_render_rejected", lambda *_a, **_kw: None)

    res = ob.scan_and_rank_all_clips(use_cache=False, auto_prune_unaccepted_repeats=True)
    assert res["pruned_unaccepted_repeats"] == 1
    assert Path(clip["path"]).exists(), "Źródło w Outplayed nie może zostać trwale usunięte przez unlink() przy błędzie Kosza"
    dismissed = json.loads(env["dismissed_file"].read_text(encoding="utf-8"))["clips"]
    assert dismissed["protected_on_recycle_err.mp4"]["source_recycled"] is False
    assert dismissed["protected_on_recycle_err.mp4"]["recycle_status"] == "shfileop_rc_5_aborted_False"


@pytest.mark.skipif(sys.platform != "win32", reason="Real Win32 SHFileOperationW Recycle Bin test only runs on Windows")
def test_real_windows_recycle_bin_moves_temp_file(tmp_path):
    temp_file = tmp_path / "etap54_recycle_smoke_test.tmp"
    temp_file.write_text("recycle-bin-smoke", encoding="utf-8")
    assert temp_file.exists()

    ok, status = ob._move_file_to_recycle_bin(temp_file)
    assert ok is True
    assert status == "recycled"
    assert not temp_file.exists()


def test_run_overnight_batch_forwards_auto_prune_flag(tmp_path, monkeypatch):
    _setup_isolated_env(tmp_path, monkeypatch)
    captured: dict = {}

    def _fake_scan(**kwargs):
        captured.update(kwargs)
        ob._OVERNIGHT_CANCEL.set()
        return {
            "folder": str(tmp_path),
            "total_clips_found": 0,
            "skipped_published": 0,
            "skipped_dismissed": 0,
            "pruned_unaccepted_repeats": 0,
            "scanned_unpublished": 0,
            "qualified_count": 0,
            "rejected_count": 0,
            "rejection_breakdown": {},
            "selected": [],
        }

    monkeypatch.setattr(ob, "scan_and_rank_all_clips", _fake_scan)
    res = ob.run_overnight_batch(top_n=3, skip_published=True, use_local_ai=False)
    assert res["status"] == "stopped"
    assert captured["skip_dismissed_repeats"] is True
    assert captured["auto_prune_unaccepted_repeats"] is True
    assert captured["max_unaccepted_renders"] == ob.MAX_UNACCEPTED_OVERNIGHT_RENDERS

