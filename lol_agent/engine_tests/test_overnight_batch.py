"""
Testy jednostkowe Trybu Nocnego (Etap 12) + napraw evaluatora HP/Hype + endpointow /overnight/*.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import synapsa_overnight_batch as ob
from lol_agent.autonomous import evaluator as ev
from lol_agent.api.config import API_PASSWORD
from lol_agent.api.main import app


def _make_green_hp_frame(w: int = 1280, h: int = 720, green_bar: bool = True) -> np.ndarray:
    """Tworzy syntetyczna klatke 720p z zielonym (Standard Mode) paskiem HP w centrum akcji."""
    fr = np.zeros((h, w, 3), dtype=np.uint8)
    fr[:, :] = (60, 75, 95)  # kolorowe tlo (wysoka saturacja > 45, brak szarego ekranu smierci)
    if green_bar:
        # Zielony pasek HP Standard Mode (#42bb27 -> BGR (39, 187, 66))
        fr[310:324, 580:700] = (39, 187, 66)
    return fr


def test_evaluator_green_hp_bar_not_marked_dead_and_multikill_outranks_1kill(tmp_path, monkeypatch):
    """Standardowy zielony pasek HP chroni przed falszywym zgonem, a Quadra wygrywa z przecietnym 1-killem."""
    vid = tmp_path / "green_clip.mp4"
    vid.write_bytes(b"dummy")

    green_fr = _make_green_hp_frame(green_bar=True)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 420.0  # 14.0s
    mock_cap.read.return_value = (True, green_fr)
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: mock_cap)

    monkeypatch.setattr(ev, "_get_evaluator_cfg", lambda: {
        "base_kill_weights": {
            "PENTAKILL": 100.0,
            "QUADRAKILL": 88.0,
            "TRIPLE KILL": 74.0,
            "DOUBLE KILL": 56.0,
            "SOLO BOLO": 95.0,  # nawet gdyby dyrektywa miala stare 95, evaluator ma twardy limit <=58!
            "OUTPLAY": 80.0,
            "KILL": 10.0,
        },
        "demoted_formats": [],
        "demoted_penalty_points": 8.0,
        "s_tier_min": 82.0,
        "a_tier_min": 68.0,
        "b_tier_min": 50.0,
    })

    # 1. Zwykly pojedynczy kill przy pelnym zielonym HP
    fake_1kill = SimpleNamespace(
        kills=[{"timestamp": 6.0, "label": "OUTPLAY", "tier": 1}],
        detected_frag_type="outplay",
        min_hp_percentage=92.0,
        is_clutch_1hp=False,
    )
    monkeypatch.setattr("lol_agent.lol_frag_detector.analyze_clip_frags", lambda *a, **kw: fake_1kill)
    res_1kill = ev.evaluate_clip_quality(str(vid))
    assert res_1kill["action_type"] != "died"
    assert res_1kill["score"] < 65.0

    # 2. Quadrakill przy pelnym zielonym HP -> musi miec wyzszy wynik niz 1-kill i NIE byc marked dead
    fake_quadra = SimpleNamespace(
        kills=[
            {"timestamp": 3.0, "label": "KILL", "tier": 1},
            {"timestamp": 4.2, "label": "DOUBLE KILL", "tier": 2},
            {"timestamp": 5.4, "label": "TRIPLE KILL", "tier": 3},
            {"timestamp": 6.6, "label": "QUADRAKILL", "tier": 4},
        ],
        detected_frag_type="quadrakill",
        min_hp_percentage=62.0,
        is_clutch_1hp=False,
    )
    monkeypatch.setattr("lol_agent.lol_frag_detector.analyze_clip_frags", lambda *a, **kw: fake_quadra)
    res_quadra = ev.evaluate_clip_quality(str(vid))
    assert res_quadra["action_type"] == "quadrakill"
    assert res_quadra["worthy"] is True
    assert res_quadra["score"] > res_1kill["score"]


def test_scan_and_rank_rejects_mediocre_and_caches(tmp_path, monkeypatch):
    """Skaner pomija opublikowane, odrzuca 0-kill i przecietne 1-kille, wybiera hype multi-kille i korzysta z cache."""
    cache_path = tmp_path / "scan_cache.json"
    monkeypatch.setattr(ob, "SCAN_CACHE_FILE", cache_path)

    clips_files = {}
    for name in ("pub.mp4", "zero_kill.mp4", "mediocre_1k.mp4", "died_1k.mp4", "triple_hype.mp4", "quadra_steal.mp4"):
        p = tmp_path / name
        p.write_bytes(b"video_payload_" + name.encode("utf-8"))
        clips_files[name] = str(p)

    monkeypatch.setattr("lol_agent.api.routers.clips.scan_available_clips", lambda _f=None: [
        {"filename": "pub.mp4", "path": clips_files["pub.mp4"], "size_mb": 12.0, "modified": 100.0, "already_published": True},
        {"filename": "zero_kill.mp4", "path": clips_files["zero_kill.mp4"], "size_mb": 12.0, "modified": 200.0, "already_published": False},
        {"filename": "mediocre_1k.mp4", "path": clips_files["mediocre_1k.mp4"], "size_mb": 12.0, "modified": 300.0, "already_published": False},
        {"filename": "died_1k.mp4", "path": clips_files["died_1k.mp4"], "size_mb": 12.0, "modified": 400.0, "already_published": False},
        {"filename": "triple_hype.mp4", "path": clips_files["triple_hype.mp4"], "size_mb": 12.0, "modified": 500.0, "already_published": False},
        {"filename": "quadra_steal.mp4", "path": clips_files["quadra_steal.mp4"], "size_mb": 12.0, "modified": 600.0, "already_published": False},
    ])

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    def _cap_get(prop):
        if prop == 5:
            return 60.0
        if prop == 7:
            return 900.0  # 15s
        if prop == 3:
            return 1920.0
        if prop == 4:
            return 1080.0
        return 0.0
    mock_cap.get.side_effect = _cap_get
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: mock_cap)

    analyze_calls = {"count": 0}
    def _fake_analyze(path, sample_fps=1.0):
        analyze_calls["count"] += 1
        fn = Path(path).name
        if fn == "zero_kill.mp4":
            return SimpleNamespace(
                kills=[], detected_frag_type="outplay", min_hp_percentage=90.0, is_clutch_1hp=False,
                objective_secured=False, objective_label="", ally_banner_blocked=False, confidence=0.80, suggested_title_hook="",
            )
        if fn == "mediocre_1k.mp4":
            return SimpleNamespace(
                kills=[{"timestamp": 6.0, "label": "OUTPLAY", "tier": 1}], detected_frag_type="solo_bolo",
                min_hp_percentage=78.0, is_clutch_1hp=False, objective_secured=False, objective_label="",
                ally_banner_blocked=False, confidence=0.88, suggested_title_hook="CLEAN",
            )
        if fn == "died_1k.mp4":
            return SimpleNamespace(
                kills=[{"timestamp": 6.0, "label": "KILL", "tier": 1}], detected_frag_type="outplay",
                min_hp_percentage=0.0, is_clutch_1hp=False, objective_secured=False, objective_label="",
                ally_banner_blocked=False, confidence=0.80, suggested_title_hook="",
            )
        if fn == "triple_hype.mp4":
            return SimpleNamespace(
                kills=[
                    {"timestamp": 3.5, "label": "KILL", "tier": 1},
                    {"timestamp": 5.0, "label": "DOUBLE KILL", "tier": 2},
                    {"timestamp": 6.2, "label": "TRIPLE KILL", "tier": 3},
                ],
                detected_frag_type="triple", min_hp_percentage=32.0, is_clutch_1hp=False,
                objective_secured=False, objective_label="", ally_banner_blocked=False, confidence=0.90,
                suggested_title_hook="3 KILLS IN 2.7S",
            )
        return SimpleNamespace(
            kills=[
                {"timestamp": 3.0, "label": "KILL", "tier": 1},
                {"timestamp": 4.5, "label": "DOUBLE KILL", "tier": 2},
                {"timestamp": 6.0, "label": "TRIPLE KILL", "tier": 3},
                {"timestamp": 7.5, "label": "QUADRAKILL", "tier": 4},
            ],
            detected_frag_type="quadrakill", min_hp_percentage=18.0, is_clutch_1hp=True,
            objective_secured=True, objective_label="DRAGON", ally_banner_blocked=False, confidence=0.95,
            suggested_title_hook="DRAGON STEAL + QUADRA",
        )

    monkeypatch.setattr("lol_agent.lol_frag_detector.analyze_clip_frags", _fake_analyze)
    monkeypatch.setattr("lol_agent.lol_frag_detector.compute_optimal_clip_window", lambda frag, dur, action_type=None: (1.5, 13.5, 7.0, None))
    monkeypatch.setattr("lol_agent.lol_quality_validator.is_raw_material_viable", lambda **kw: (True, None, "ok"))
    monkeypatch.setattr(ob, "_check_trailing_survival", lambda path, _e, _fps: Path(path).name == "died_1k.mp4")

    res = ob.scan_and_rank_all_clips(top_n=5, skip_published=True, use_cache=True, max_workers=2)
    assert res["total_clips_found"] == 6
    assert res["skipped_published"] == 1
    assert res["qualified_count"] == 2
    assert res["rejected_count"] == 3
    assert analyze_calls["count"] == 5
    # Top 2 to quadra + triple, a mediocre_1k dopuszczony wylacznie z flaga fallback_mediocre=True (nigdy 0-kill/zgon!)
    sel_names = [s["filename"] for s in res["selected"]]
    assert sel_names[:2] == ["quadra_steal.mp4", "triple_hype.mp4"]
    assert "zero_kill.mp4" not in sel_names
    assert "died_1k.mp4" not in sel_names
    assert res["selected"][2]["filename"] == "mediocre_1k.mp4"
    assert res["selected"][2]["fallback_mediocre"] is True

    # Drugi przebieg powinien uzyc cache (0 nowych wywolan analyze_clip_frags)
    res_cached = ob.scan_and_rank_all_clips(top_n=5, skip_published=True, use_cache=True, max_workers=2)
    assert analyze_calls["count"] == 5
    assert [s["filename"] for s in res_cached["selected"]] == sel_names


def test_run_overnight_batch_no_upload_and_antisycophancy_guard(tmp_path, monkeypatch):
    """Pelny batch nocny renderuje lokalnie bez uploadu, a straznik odrzuca wadliwy short wskazany przez LLM."""
    monkeypatch.setattr(ob, "OVERNIGHT_DIR", tmp_path / "batches")
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", tmp_path / "batches" / "latest_batch.json")

    fake_scan = {
        "folder": str(tmp_path),
        "total_clips_found": 10,
        "skipped_published": 2,
        "scanned_unpublished": 8,
        "qualified_count": 2,
        "rejected_count": 6,
        "rejection_breakdown": {"REJECT_NO_KILLS": 4, "REJECT_MEDIOCRE_1KILL": 2},
        "selected": [
            {
                "filename": "clip_a.mp4", "path": str(tmp_path / "clip_a.mp4"),
                "action_type": "triple", "kill_count": 3, "kill_span_s": 4.2,
                "objective_secured": False, "is_clutch_1hp": False, "min_hp_percentage": 55.0,
                "clip_start": 2.0, "clip_end": 16.0, "peak_moment": 8.0, "combat_segments": None,
                "hook_text": "3 KILLS IN 4.2S", "hype_score": 77.0, "fallback_mediocre": False,
            },
            {
                "filename": "clip_b.mp4", "path": str(tmp_path / "clip_b.mp4"),
                "action_type": "quadrakill", "kill_count": 4, "kill_span_s": 5.0,
                "objective_secured": True, "is_clutch_1hp": True, "min_hp_percentage": 14.0,
                "clip_start": 1.0, "clip_end": 19.0, "peak_moment": 9.0, "combat_segments": None,
                "hook_text": "DRAGON STEAL + QUADRA", "hype_score": 94.0, "fallback_mediocre": False,
            },
        ],
    }
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **kw: fake_scan)

    # Mock pipeline_runner tak, by zapisywal atrapy mp4 bez FFmpeg i bez sieci
    from lol_agent.api import pipeline_runner
    fake_state = {"status": "idle", "output_path": None}

    def _fake_run_pipe(**kwargs):
        out_p = tmp_path / kwargs["output_filename"]
        out_p.write_bytes(b"mp4_stub")
        fake_state.clear()
        fake_state.update({
            "status": "done",
            "output_path": str(out_p),
            "thumbnail_path": None,
            "action_type": kwargs["action_type"],
            "clip_start": kwargs["clip_start"],
            "clip_end": kwargs["clip_end"],
            "title": f"{kwargs['action_type'].upper()} Test Title",
            "title_variant_b": "Alt Title",
            "description": "Test desc",
            "pinned_comment": "Test comment?",
            "qa_status": "PASS",
            "qa_score": 92,
        })

    monkeypatch.setattr(pipeline_runner, "_run_pipeline", _fake_run_pipe)
    monkeypatch.setattr(pipeline_runner, "get_state", lambda: dict(fake_state))

    # clip_a dostaje krytyczny defekt black_end_frame=True, clip_b jest czysty (watchability=95)
    def _fake_inspect(mp4_path: str):
        is_a = "_r1_" in Path(mp4_path).name
        return {
            "watchability_score": 58.0 if is_a else 95.0,
            "frame0_hook_legible": True,
            "kill_overlay_zone": "upper_safe",
            "player_visible_ratio": 0.90,
            "player_edge_clip_ratio": 0.05,
            "audio_clip_gt_096": 0,
            "av_delta_s": 0.02,
            "black_end_frame": is_a,
            "hook_is_generic": False,
            "hook_text": "TEST HOOK",
            "video_dur_s": 14.0,
        }

    monkeypatch.setattr("lol_agent.synapsa_watchability_judge.inspect_rendered_short", _fake_inspect)
    monkeypatch.setattr(ob, "_probe_ig_compliance", lambda _p: {"ig_ready": True, "ig_issues": []})
    monkeypatch.setattr(ob, "_annotate_output_metas", lambda *_a, **_kw: None)

    # Symuluj ze lokalna Synapsa blednie wybrala clip_a z black_end_frame=True -> straznik MUSI wymusic clip_b!
    fake_syn_mod = types.ModuleType("lol_agent.synapsa_engine")
    fake_syn_mod.is_synapsa_available = lambda: True
    def _bad_ai_rank(_task, payload, timeout=120):
        cands = payload["candidates"]
        bad_fn = [c["filename"] for c in cands if c.get("black_end_frame")][0]
        return {
            "recommended_filename": bad_fn,
            "summary_pl": "Wybrano pierwszy short bez analizy defektów.",
            "per_short_pl": {bad_fn: "Super idealny montaż!"},
        }
    fake_syn_mod.generate_with_synapsa = _bad_ai_rank
    monkeypatch.setitem(sys.modules, "lol_agent.synapsa_engine", fake_syn_mod)

    manifest = ob.run_overnight_batch(top_n=2, use_local_ai=True)
    assert manifest["auto_publish"] is False
    assert manifest["guard_override"] is True
    assert manifest["recommendation_source"] == "synapsa_guard_override"
    assert "_r2_quadrakill" in manifest["recommended_filename"]
    assert manifest["items"][0]["verdict"] == "PICK_WINNER"
    assert manifest["items"][1]["has_critical_defect"] is True
    assert ob.LATEST_BATCH_FILE.is_file()
    loaded = ob.load_latest_overnight_batch()
    assert loaded["recommended_filename"] == manifest["recommended_filename"]


def test_overnight_api_endpoints(monkeypatch, tmp_path):
    """FastAPI endpointy /overnight/status, /latest, /start, /stop dzialaja z JWT i respektuja mocki modulowe."""
    latest_file = tmp_path / "latest_batch.json"
    latest_file.write_text(json.dumps({"batch_id": "test_123", "recommended_filename": "short_test.mp4", "items": []}), encoding="utf-8")
    calls = {"start": 0, "stop": 0}
    def _mock_start(**_kw):
        calls["start"] += 1
        return True
    def _mock_stop():
        calls["stop"] += 1
        return True
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", latest_file)
    monkeypatch.setattr(ob, "start_overnight_batch_async", _mock_start)
    monkeypatch.setattr(ob, "stop_overnight_batch", _mock_stop)

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        r_stat = client.get("/overnight/status", headers=headers)
        assert r_stat.status_code == 200
        assert "status" in r_stat.json()

        r_lat = client.get("/overnight/latest", headers=headers)
        assert r_lat.status_code == 200
        assert r_lat.json()["batch"]["batch_id"] == "test_123"

        r_start = client.post("/overnight/start", json={"top_n": 5, "skip_published": True}, headers=headers)
        assert r_start.status_code == 200
        assert r_start.json()["auto_publish"] is False

        r_stop = client.post("/overnight/stop", headers=headers)
        assert r_stop.status_code == 200
        assert r_stop.json()["status"] == "stopping"

    assert calls["start"] == 1
    assert calls["stop"] == 1


def test_windowed_action_classification_prevents_inflated_tiers():
    """Klasyfikacja musi bazowac na killach w oknie i ich realnym tierze, bez zawyzania Triple do Pentakill."""
    # 1. Klip 47s: 3 kille w oknie (max tier=3 -> triple), a 2 dalsze kille daleko poza oknem -> MUSI byc 'triple'
    entry_47s = {
        "filename": "long_47s.mp4",
        "path": "C:/tmp/long_47s.mp4",
        "modified": 100.0,
        "clip_start": 7.3,
        "clip_end": 23.8,
        "window_dur": 16.5,
        "kills": [
            {"timestamp": 11.5, "label": "OUTPLAY", "tier": 1},
            {"timestamp": 18.0, "label": "DOUBLE KILL", "tier": 2},
            {"timestamp": 22.5, "label": "TRIPLE KILL", "tier": 3},
            {"timestamp": 35.5, "label": "OUTPLAY", "tier": 1},
            {"timestamp": 39.0, "label": "DOUBLE KILL", "tier": 2},
        ],
        "confidence": 0.88,
        "min_hp_percentage": 24.9,
        "is_clutch_1hp": False,
        "objective_secured": False,
        "ally_banner_blocked": True,
        "player_died": False,
        "raw_viable": True,
        "hook_text": "PENTAKILL FAKE",
    }
    res_triple = ob._score_and_classify_candidate(entry_47s)
    assert res_triple["action_type"] == "triple"
    assert res_triple["kill_count"] == 3
    assert res_triple["hook_text"] == ""  # oczyszczony niepasujacy hook PENTA

    # 2. Klip z 3 zdarzeniami ale max_tier=2 (DOUBLE KILL) -> MUSI pozostac 'double', NIE 'triple'!
    entry_double3 = {
        "filename": "double_with_extra_outplay.mp4",
        "path": "C:/tmp/double3.mp4",
        "modified": 101.0,
        "clip_start": 4.3,
        "clip_end": 16.2,
        "window_dur": 11.9,
        "kills": [
            {"timestamp": 8.5, "label": "OUTPLAY", "tier": 1},
            {"timestamp": 12.5, "label": "KILL", "tier": 1},
            {"timestamp": 15.0, "label": "DOUBLE KILL", "tier": 2},
        ],
        "confidence": 0.85,
        "min_hp_percentage": 26.8,
        "is_clutch_1hp": False,
        "objective_secured": False,
        "ally_banner_blocked": False,
        "player_died": False,
        "raw_viable": True,
        "hook_text": "DOUBLE KILL - 2v1 TURNAROUND",
    }
    res_double = ob._score_and_classify_candidate(entry_double3)
    assert res_double["action_type"] == "double"
    assert res_triple["hype_score"] > res_double["hype_score"]


def test_check_trailing_survival_catches_grey_death_even_with_fake_hud_hp(tmp_path, monkeypatch):
    """Dwie koncowe klatki o niskiej saturacji (<38) muszą oznaczac zgon mimo szumu HUD HP."""
    vid = tmp_path / "died_tail.mp4"
    vid.write_bytes(b"dummy")

    alive_fr = np.full((720, 1280, 3), (40, 180, 70), dtype=np.uint8)
    gray_fr = np.full((720, 1280, 3), 90, dtype=np.uint8)  # saturacja = 0.0 < 38.0
    frames = [alive_fr, gray_fr, gray_fr, gray_fr, gray_fr]
    idx = {"i": 0}

    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = lambda prop: 60.0 if prop == 5 else 1000.0
    def _read():
        f = frames[min(idx["i"], len(frames) - 1)]
        idx["i"] += 1
        return True, f
    mock_cap.read.side_effect = _read
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: mock_cap)
    monkeypatch.setattr("lol_agent.lol_frag_detector._measure_player_hp", lambda _fr: 23.4)

    assert ob._check_trailing_survival(str(vid), clip_end=16.0, fps=60.0) is True


def test_pipeline_start_blocked_while_overnight_active(monkeypatch):
    """POST /pipeline/start zwraca 409 Conflict gdy Tryb Nocny aktywnie pracuje."""
    monkeypatch.setitem(ob._OVERNIGHT_STATE, "status", "scanning")
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        resp = client.post("/pipeline/start", json={
            "source_path": "C:/nonexistent/clip.mp4",
            "clip_start": 0.0,
            "clip_end": 12.0,
            "action_type": "triple",
            "champion_name": "Katarina",
            "rank": "Master",
            "peak_moment": 6.0,
            "hook_text": "TEST",
            "output_filename": "short_conflict_test.mp4",
        }, headers=headers)
        assert resp.status_code == 409
        assert "Tryb nocny" in resp.json()["detail"]


def test_overnight_cancel_on_last_clip_exits_rendering_and_stop_idle_noop(monkeypatch, tmp_path):
    """stop_overnight_batch() na stanie idle nie ustawia flagi cancel, a przerwanie ostatniego klipu zamyka stan jako stopped."""
    monkeypatch.setitem(ob._OVERNIGHT_STATE, "status", "idle")
    ob._OVERNIGHT_CANCEL.clear()
    assert ob.stop_overnight_batch() is False
    assert not ob._OVERNIGHT_CANCEL.is_set()

    fake_scan = {
        "folder": str(tmp_path),
        "total_clips_found": 1,
        "skipped_published": 0,
        "scanned_unpublished": 1,
        "qualified_count": 1,
        "rejected_count": 0,
        "rejection_breakdown": {},
        "selected": [{
            "filename": "last_clip.mp4", "path": str(tmp_path / "last_clip.mp4"),
            "action_type": "triple", "kill_count": 3, "kill_span_s": 3.0,
            "objective_secured": False, "is_clutch_1hp": False, "min_hp_percentage": 70.0,
            "clip_start": 1.0, "clip_end": 12.0, "peak_moment": 6.0, "combat_segments": None,
            "hook_text": "TRIPLE", "hype_score": 76.0, "fallback_mediocre": False,
        }],
    }
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **kw: fake_scan)
    from lol_agent.api import pipeline_runner
    fake_state = {"status": "error", "error": "Anulowano", "output_path": None}

    def _cancel_mid_render(**kwargs):
        # Symulacja Stop kliknietego podczas renderu jedynego (ostatniego) klipu
        ob.stop_overnight_batch()

    monkeypatch.setattr(pipeline_runner, "_run_pipeline", _cancel_mid_render)
    monkeypatch.setattr(pipeline_runner, "stop_pipeline", lambda clear_queue=True: None)
    monkeypatch.setattr(pipeline_runner, "get_state", lambda: dict(fake_state))

    try:
        res = ob.run_overnight_batch(top_n=1, use_local_ai=False)
        assert res["status"] == "stopped"
        assert ob.get_overnight_status()["status"] == "stopped"
    finally:
        ob._OVERNIGHT_CANCEL.clear()
        monkeypatch.setitem(ob._OVERNIGHT_STATE, "status", "idle")


def test_videocapture_always_released_on_exceptions(monkeypatch, tmp_path):
    """Wszystkie 4 sciezki OpenCV VideoCapture zwalniaja uchwyt w finally mimo wyjatku."""
    from lol_agent import synapsa_watchability_judge as wj

    vid = tmp_path / "stub.mp4"
    vid.write_bytes(b"stub_mp4")

    def _make_failing_cap(fail_on_read=True):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: 60.0 if prop == 5 else (900.0 if prop == 7 else 1080.0)
        if fail_on_read:
            cap.read.side_effect = RuntimeError("simulated decode crash")
        else:
            cap.read.return_value = (True, np.zeros((720, 1280, 3), dtype=np.uint8))
        return cap

    # 1. _check_trailing_survival
    cap1 = _make_failing_cap(fail_on_read=True)
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: cap1)
    assert ob._check_trailing_survival(str(vid), clip_end=14.0, fps=60.0) is False
    assert cap1.release.call_count == 1

    # 2. _analyze_single_clip_for_overnight (get rzuca wyjatek)
    cap2 = MagicMock()
    cap2.isOpened.return_value = True
    cap2.get.side_effect = RuntimeError("broken header")
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: cap2)
    with pytest.raises(RuntimeError):
        ob._analyze_single_clip_for_overnight({"path": str(vid), "filename": "stub.mp4"})
    assert cap2.release.call_count == 1

    # 3. evaluate_clip_quality (frag_detector + fallback rzucaja wyjatek)
    cap3 = _make_failing_cap(fail_on_read=False)
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: cap3)
    monkeypatch.setattr("lol_agent.lol_frag_detector.analyze_clip_frags", MagicMock(side_effect=RuntimeError("ocr boom")))
    monkeypatch.setattr("lol_agent.lol_momentum_analyzer._compute_kill_scores", MagicMock(side_effect=RuntimeError("fallback boom")))
    with pytest.raises(RuntimeError):
        ev.evaluate_clip_quality(str(vid))
    assert cap3.release.call_count == 1

    # 4. inspect_rendered_short
    cap4 = _make_failing_cap(fail_on_read=True)
    monkeypatch.setattr("cv2.VideoCapture", lambda _p: cap4)
    monkeypatch.setattr(wj, "_probe_video_and_audio", lambda _p: {
        "video_dur_s": 14.0, "audio_dur_s": 14.0, "av_delta_s": 0.0,
        "audio_clip_gt_096": 0, "audio_max_peak": 0.8, "audio_mean_rms_db": -18.0,
    })
    with pytest.raises(RuntimeError):
        wj.inspect_rendered_short(str(vid))
    assert cap4.release.call_count == 1


def test_atomic_write_text_leaves_no_tmp(tmp_path):
    """_atomic_write_text zapisuje UTF-8 czysto i nie pozostawia plikow .tmp."""
    target = tmp_path / "sub" / "manifest.json"
    payload = json.dumps({"ok": True, "pl": "Zażółć gęślą jaźń"}, ensure_ascii=False)
    ob._atomic_write_text(target, payload)
    assert target.read_text(encoding="utf-8") == payload
    assert list(target.parent.glob("*.tmp")) == []


def test_player_in_frame_rejects_vertical_cta_and_grass_accepts_hp_bar():
    """Pionowa klatka 9:16 ze zlotym CTA na y=1380 i ciemna trawa zwraca False, a prawdziwy pasek HP -> True."""
    import cv2
    from lol_agent.lol_quality_validator import _check_player_in_frame

    fr_bad = np.full((1920, 1080, 3), (38, 128, 42), dtype=np.uint8)  # zielonkawa trawa dzungli BGR
    # Zloty napis CTA (0xFFD700 -> BGR (0, 215, 255)) w dolnej strefie y=1380
    cv2.putText(fr_bad, "CLEAN RESET OR LUCKY?", (120, 1410), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 215, 255), 4)
    # Zloty FINAL KILL u gory y=340 (< 0.30*1920 = 576)
    cv2.putText(fr_bad, "FINAL KILL 4/4", (320, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 215, 255), 3)
    vis_bad, px_bad, pt_bad = _check_player_in_frame(fr_bad)
    assert vis_bad is False and px_bad == 0 and pt_bad is None

    fr_good = fr_bad.copy()
    # Prawdziwy pasek HP gracza (BGR (49, 185, 76) -> RGB (76, 185, 49)) w srodku kadru 120x14
    cv2.rectangle(fr_good, (460, 960), (580, 974), (49, 185, 76), -1)
    vis_good, px_good, pt_good = _check_player_in_frame(fr_good)
    assert vis_good is True and px_good > 500
    assert pt_good is not None and 480 <= pt_good[0] <= 560 and 950 <= pt_good[1] <= 985


def test_score_title_candidate_blocks_tier_mismatch_and_nonsense():
    """Tytul z blednym tierem (Triple przy Quadra) lub belkotem 'damage away 🧵' musi przegrac."""
    from lol_agent.synapsa_engine import score_title_candidate

    s_wrong_tier = score_title_candidate(
        "Cleanest Angle Check Triple Kill 🔥 #shorts #leagueoflegends #lol",
        action_type="quadrakill",
        directive={"avoid_keywords": ["KATA"], "winning_keywords": []},
    )
    s_nonsense = score_title_candidate(
        "They Thought We Were Just Three Damage Away 🧵 #shorts #leagueoflegends #lol",
        action_type="triple",
        directive={"avoid_keywords": ["KATA"], "winning_keywords": []},
    )
    s_clean_quadra = score_title_candidate(
        "All Four Down Before They Reacted ⚡ Katarina #shorts #leagueoflegends #lol",
        action_type="quadrakill",
        directive={"avoid_keywords": ["KATA"], "winning_keywords": []},
    )
    assert s_wrong_tier < 0.0
    assert s_nonsense < 0.0
    assert s_clean_quadra > 40.0


def test_monotonic_quadra_captions_and_champion_aware_outro_cta(tmp_path):
    """Duplikat DOUBLE KILL na 3. killu jest awansowany do TRIPLE KILL, a Yone nie dostaje CTA o Shunpo."""
    from lol_agent.lol_editor import build_dynamic_captions_filters, select_non_repeating_outro_cta

    filters = build_dynamic_captions_filters(
        peaks=[(1.0, "KILL"), (3.5, "DOUBLE KILL"), (10.5, "DOUBLE KILL"), (12.0, "QUADRAKILL")],
        trim_start=0.0,
        video_duration=13.5,
        action_type="quadrakill",
    )
    joined = "\n".join(filters)
    assert ":text='TRIPLE KILL'" in joined
    assert joined.count(":text='DOUBLE KILL'") == 1

    hist = str(tmp_path / "cap_hist.json")
    for _ in range(15):
        cta = select_non_repeating_outro_cta(history_path=hist, action_type="quadrakill", champion_name="Yone")
        assert cta["id"] not in ("debate_shunpo", "debate_lucky")


def test_overnight_ranking_defects_and_lora_timestamp_hallucination_guard(tmp_path):
    """Reprodukuje r1 vs r2 z paczki 082153: wykrywa wady montażowe i blokuje halucynowane czasy 3.0s/4.5s/8.2s."""
    # 1. _score_and_classify_candidate obniża przewagę niepotwierdzonego OCR triple z rozciągniętym spanem 15.5s
    r1_raw = {
        "filename": "20-21-23-947_0.mp4",
        "path": "C:/tmp/r1.mp4",
        "clip_start": 5.5,
        "clip_end": 25.2,
        "kills": [
            {"timestamp": 8.0, "label": "KILL", "tier": 1},
            {"timestamp": 15.5, "label": "DOUBLE KILL", "tier": 2},
            {"timestamp": 23.5, "label": "TRIPLE KILL", "tier": 3},
        ],
        "raw_detected_frag_type": "triple",
        "objective_secured": True,
        "confidence": 0.90,
        "min_hp_percentage": 45.0,
        "player_died": False,
        "event_source": "ocr_only",
    }
    r2_raw = {
        "filename": "16-32-37-217_0.mp4",
        "path": "C:/tmp/r2.mp4",
        "clip_start": 9.0,
        "clip_end": 23.8,
        "kills": [
            {"timestamp": 12.1, "label": "KILL", "tier": 1},
            {"timestamp": 15.5, "label": "DOUBLE KILL", "tier": 2},
            {"timestamp": 19.6, "label": "TRIPLE KILL", "tier": 3},
        ],
        "raw_detected_frag_type": "triple",
        "event_tier": "triple",
        "event_tier_rank": 3,
        "event_source": "outplayed_backup",
        "objective_secured": False,
        "confidence": 0.90,
        "min_hp_percentage": 34.0,
        "player_died": False,
    }
    s1 = ob._score_and_classify_candidate(r1_raw)
    s2 = ob._score_and_classify_candidate(r2_raw)
    # Kara za kill_span_s=15.5s i bonus Outplayed +3.0 zbliżają/przewyższają r2 nad niepotwierdzonym r1
    assert s2["hype_score"] >= s1["hype_score"]

    # 2. _extract_defects wyłapuje dead_gap_gt_3.8s, moderate_edge_clipping i camera_jump_gt_220px na metrykach r1
    r1_insp = {
        "video_dur_s": 12.666,
        "player_visible_ratio": 0.722,
        "player_edge_clip_ratio": 0.154,
        "camera_peak_step_px": 290.0,
        "longest_gap_out_sec": 4.097,
        "first_kill_out_sec": 3.03,
        "frame0_hook_legible": True,
        "audio_clip_gt_096": 0,
        "av_delta_s": 0.0,
        "black_end_frame": False,
    }
    defects_r1, crit_r1 = ob._extract_defects(r1_insp, ig_ready=True, item={})
    assert crit_r1 is False
    assert "dead_gap_gt_3.8s" in defects_r1
    assert "moderate_edge_clipping" in defects_r1
    assert "camera_jump_gt_220px" in defects_r1

    # 3. Ranker przelicza wagi (0.35/0.50/0.15) + kary za defekty tak, że czystszy short (r2 po poprawie czasu) wygrywa z wadliwym r1
    p1 = tmp_path / "r1.mp4"
    p2 = tmp_path / "r2.mp4"
    p1.write_bytes(b"stub1")
    p2.write_bytes(b"stub2")
    ranked = ob.rank_rendered_overnight_shorts([
        {
            "render_ok": True,
            "output_path": str(p1),
            "output_filename": "r1.mp4",
            "champion_name": "Katarina",
            "action_type": "triple",
            "hype_score": s1["hype_score"],
            "watchability_score": 88.47,
            "qa_score": 90,
            "player_visible_ratio": 0.722,
            "player_edge_clip_ratio": 0.154,
            "camera_peak_step_px": 290.0,
            "longest_gap_out_sec": 4.097,
            "defects": defects_r1,
            "has_critical_defect": False,
        },
        {
            "render_ok": True,
            "output_path": str(p2),
            "output_filename": "r2.mp4",
            "champion_name": "Katarina",
            "action_type": "triple",
            "hype_score": s2["hype_score"],
            "watchability_score": 91.22,
            "qa_score": 91,
            "player_visible_ratio": 0.778,
            "player_edge_clip_ratio": 0.0,
            "camera_peak_step_px": 120.0,
            "longest_gap_out_sec": 2.4,
            "defects": [],
            "has_critical_defect": False,
        },
    ], scan_stats={"qualified_count": 2}, use_local_ai=False)
    assert ranked["recommended_filename"] == "r2.mp4"

    # 4. Strażnik _is_clean_consistent_polish_note blokuje halucynowane szablony LoRA z paczki 082153
    r1_item = {
        "action_type": "triple",
        "overnight_rank": 1,
        "final_score": 74.2,
        "hype_score": 72.0,
        "watchability_score": 88.47,
        "qa_score": 90,
        "duration_s": 12.666,
        "first_kill_out_sec": 3.03,
        "kill_span_s": 15.5,
        "longest_gap_out_sec": 4.097,
        "kill_timestamps_out": [0.5, 7.4, 11.3],
        "defects": defects_r1,
        "has_critical_defect": False,
    }
    assert ob._is_clean_consistent_polish_note(
        "Zabójstwa w 3.0s, 4.5s i 8.2s; player_visible_ratio=0.722",
        r1_item,
    ) is False
    assert ob._is_clean_consistent_polish_note(
        "Wielokrotne zabójstwo w 3.0s, 4.5s i 8.2s z solidnym tempem",
        r1_item,
    ) is False
    assert ob._is_clean_consistent_polish_note(
        "Wygrana multikillowa z 3 zabójstwami w 8.2s — obiektywnie najlepszy klip na ten film.",
        r1_item,
    ) is False
    assert ob._is_clean_consistent_polish_note(
        "Wygrana multikillowa z 3 zabójstwami w 8.2s, mocne tempo w drugiej połowie klipu.",
        r1_item,
    ) is False
    assert ob._is_clean_consistent_polish_note(
        "Katarina TRIPLE (watch=88.5, qa=90): pierwsza eliminacja w 3.0s, ostatnia w 11.3s, widoczne wady kadru.",
        r1_item,
    ) is True


def test_etap27_viral_titles_publish_gate_and_speed_bridge(tmp_path):
    """Sprawdza kare AI-zargonu, odblokowanie 'bad idea', SCHEMA_VERSION=4, publish_recommended i speed_bridge_gap_s."""
    from lol_agent.synapsa_engine import score_title_candidate

    # 1. Potoczny curiosity gap musi wygrac z AI-zargonem (Reset Chain / Relentless / Rampage / Execution)
    s_viral = score_title_candidate("They Grouped For Free 💀 #shorts #leagueoflegends #lol", action_type="triple")
    s_jargon1 = score_title_candidate("Relentless Reset Chain Triple 💥 #shorts #leagueoflegends #lol", action_type="triple")
    s_jargon2 = score_title_candidate("Pixel-Perfect Rampage Execution ⚡ #shorts #leagueoflegends #lol", action_type="triple")
    s_bad_idea = score_title_candidate("Chasing Katarina Is a Bad Idea 💀 #shorts #leagueoflegends #lol", action_type="triple")
    assert s_viral > s_jargon1 + 30.0
    assert s_viral > s_jargon2 + 30.0
    assert s_bad_idea > 0.0  # usuniety bledny ban na 'bad idea'

    # 2. Schema cache musi byc podbita >= 5 (uniewaznienie starych wpisow po P0.2)
    assert ob.SCAN_CACHE_SCHEMA_VERSION >= 5

    # 3. Bramka publish_recommended blokuje dlugie dziury (>=5.5s), wolne intra (>4.0s) i za niskie final (<76)
    p_good = tmp_path / "good.mp4"
    p_gap = tmp_path / "gap.mp4"
    p_good.write_bytes(b"ok")
    p_gap.write_bytes(b"gap")
    ranked = ob.rank_rendered_overnight_shorts([
        {
            "render_ok": True, "output_path": str(p_good), "output_filename": "good.mp4",
            "champion_name": "Katarina", "action_type": "triple",
            "hype_score": 76.0, "watchability_score": 90.0, "qa_score": 92,
            "duration_s": 13.8, "first_kill_out_sec": 2.4, "longest_gap_out_sec": 3.1,
            "player_visible_ratio": 0.85, "defects": [], "has_critical_defect": False,
        },
        {
            "render_ok": True, "output_path": str(p_gap), "output_filename": "gap.mp4",
            "champion_name": "Katarina", "action_type": "triple",
            "hype_score": 76.0, "watchability_score": 88.0, "qa_score": 91,
            "duration_s": 16.0, "first_kill_out_sec": 4.5, "longest_gap_out_sec": 6.8,
            "player_visible_ratio": 0.80, "defects": ["slow_intro_gt_3.5s", "dead_gap_gt_3.8s"], "has_critical_defect": False,
        },
    ], scan_stats={"qualified_count": 2}, use_local_ai=False)
    items = ranked["items"]
    assert items[0]["output_filename"] == "good.mp4" and items[0]["publish_recommended"] is True
    assert items[1]["output_filename"] == "gap.mp4" and items[1]["publish_recommended"] is False
    assert any("dead_gap_" in r for r in items[1]["publish_block_reasons"])
    assert any("slow_intro_" in r for r in items[1]["publish_block_reasons"])

    # 4. Opcja A w lol_editor: PRIMARY z speed_bridge_gap_s=4.5 przyspiesza luke 10s, bez dotykania domyslnego kontraktu None
    import test_editor_pipeline as tep
    tep._render("double", [(3.0, "KILL"), (13.0, "DOUBLE KILL")], 13.0, speed_bridge_gap_s=4.5)
    r_bridged = tep._recipe_of()
    assert r_bridged["montage_style"] == "PRIMARY"
    assert any(abs(float(s.get("speed", 1.0)) - 2.2) < 0.05 for s in r_bridged["time_segments"])


def test_batch_96960_loophole_guards():
    """Regresja dla luk wykrytych w batchu 96960: Part #1, Three na double, wieze, 'bez wad' i champion_mismatch."""
    from lol_agent.synapsa_engine import score_title_candidate, score_and_select_best_titles

    # Part #1 musi przegrac po sprawdzeniu surowego raw_low (zanim _strip_tags_clean obetnie #1)
    s_part = score_title_candidate(
        "When The Enemy Overextended Too Far 😈 Part #1 #shorts #leagueoflegends #lol",
        action_type="triple",
    )
    s_clean = score_title_candidate(
        "When The Enemy Overextended Too Far 😈 #shorts #leagueoflegends #lol",
        action_type="triple",
    )
    assert s_part < 0.0 and s_clean > 40.0

    # Jesli jedyny kandydat z LoRA zawiera Part #1, sanityzer post-selekcji musi go usunac
    best_a, best_b = score_and_select_best_titles(
        [
            "When The Enemy Overextended Too Far 😈 Part #1 #shorts #leagueoflegends #lol",
            "Enemy Team Grouped For Free Part 2 #shorts #leagueoflegends #lol",
        ],
        action_type="triple",
    )
    assert "part" not in best_a.lower()
    assert "part" not in best_b.lower()
    assert best_a == "Enemy Team Grouped For Free #shorts #leagueoflegends #lol"
    assert best_b == "When The Enemy Overextended Too Far 😈 #shorts #leagueoflegends #lol"

    # Tier liczbowy ('Three' na DOUBLE) i halucynowane 'DOUBLE TOWER DOWN' musza byc ukarane
    assert score_title_candidate(
        "Eliminating Three Before They Reacted 👑 #shorts #leagueoflegends #lol",
        action_type="double",
    ) < 0.0
    assert score_title_candidate(
        "Two For The Price Of One 💀 DOUBLE TOWER DOWN! #shorts #leagueoflegends #lol",
        action_type="double",
    ) < 0.0

    # 'bez wad' odrzucone przy obecnych realnych wadach
    assert ob._is_clean_consistent_polish_note(
        "Hype 82.0, Watchability 97.3 — bez wad.",
        {
            "final_score": 81.4,
            "hype_score": 82.0,
            "watchability_score": 97.3,
            "defects": ["camera_jump_gt_220px", "dead_gap_gt_3.8s", "slow_intro_gt_3.5s"],
            "has_critical_defect": False,
            "overnight_rank": 1,
            "action_type": "triple",
        },
    ) is False

    # Notatka wychwalajaca lub przywolujaca Katarine bez Evelynn przy champion_mismatch musi byc odrzucona
    assert ob._is_clean_consistent_polish_note(
        "Podsumowanie zagrania na Katarinę: podwójne zabójstwo ze słabym wstępem i niską widocznością.",
        {
            "final_score": 61.7,
            "champion_name": "Evelynn",
            "requested_champion": "Katarina",
            "champion_mismatch": True,
            "defects": ["wrong_champion:Evelynn!=Katarina"],
            "has_critical_defect": False,
            "overnight_rank": 5,
            "action_type": "double",
        },
    ) is False
    # Notatka szczerze wskazujaca Evelynn i mismatch przechodzi jesli dluga i bez falszywych pochwal
    assert ob._is_clean_consistent_polish_note(
        "Evelynn DOUBLE (final 61.7): slabe tempo w porownaniu do klipow Katariny, brak akcji na poczatku.",
        {
            "final_score": 61.7,
            "champion_name": "Evelynn",
            "requested_champion": "Katarina",
            "champion_mismatch": True,
            "defects": ["slow_intro_gt_4.8s", "wrong_champion:Evelynn!=Katarina"],
            "has_critical_defect": False,
            "overnight_rank": 5,
            "action_type": "double",
        },
    ) is True







