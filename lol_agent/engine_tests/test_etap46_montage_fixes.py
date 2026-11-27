"""
Testy regresyjne Etapu 46:
  - TL.compute_adaptive_gap_speed(): chroni długość wyjściową (>= 9.4s) przy redukcji długich przerw w STORY_RAW_POV
  - E._damp_camera_path(): zbija gwałtowne skoki kamery >= 220px do <= 195px z zachowaniem celu
  - pipeline_runner._run_pipeline(): brak dopisywania fałszywego est_last_kill_s i wydłużania końca na kraba, gdy OCR wykrył DOUBLE KILL (regresja r5)
  - ob.run_overnight_batch(): domyślny preset compare_all_3 (3 warianty gotowe rano), unikalne tytuły między kandydatami i bez-spoilerowe hooki
  - GET /overnight/latest: wzbogacanie alternate_renders o file_exists i miniaturki
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import lol_timeline as TL
from lol_agent import lol_editor as E
from lol_agent import synapsa_overnight_batch as ob
from lol_agent.api.config import API_PASSWORD
from lol_agent.api.main import app


def test_compute_adaptive_gap_speed_preserves_min_output_duration():
    # Regresja r3 STORY_RAW_POV: clip_dur=10.15s, kille @ 3.5s i 9.5s (luka 6.0s); 2.4x skracało poniżej 8.9s
    base = TL.build_speed_segments(
        clip_duration=10.15,
        peak_moment=8.95,
        slowmo_speed=0.55,
        slowmo_duration=0.55,
        zoom_duration=0.35,
        intermediate_peaks=[3.0],
        use_easing=True,
        slowmo_window_max=0.55,
        zoom_window_max=0.35,
    )
    spd = TL.compute_adaptive_gap_speed(
        base, [3.5, 9.5], base_speed=2.4, min_output_dur=9.4, tail=0.65, lead=0.65
    )
    bridged = TL.apply_fast_forward(base, [3.5, 9.5], speed=spd, tail=0.65, lead=0.65)
    out_dur = TL.output_duration(bridged)
    assert spd <= 2.4
    assert out_dur >= 9.4 - 1e-3, (spd, out_dur)


def test_damp_camera_path_limits_step_without_losing_target():
    raw = [(0.0, 200), (0.25, 650), (0.50, 650), (0.75, 650), (1.00, 650)]
    damped = E._damp_camera_path(raw, max_step_px=195.0)
    steps = [abs(b[1] - a[1]) for a, b in zip(damped, damped[1:])]
    assert max(steps) <= 195.0, steps
    assert damped[-1][1] == 650, damped


def test_pipeline_runner_does_not_overwrite_verified_ocr_double_kill_with_est_last(monkeypatch, tmp_path):
    from lol_agent.api import pipeline_runner

    dummy_video = tmp_path / "r5_double_clip.mp4"
    dummy_video.write_bytes(b"video_bytes")
    rendered_mp4 = tmp_path / "short_r5_out.mp4"
    rendered_mp4.write_bytes(b"out_bytes")

    captured: Dict[str, Any] = {}

    def _fake_render(**kwargs):
        captured["clip_end"] = kwargs.get("clip_end")
        captured["peaks"] = list(kwargs.get("peaks") or [])
        return str(rendered_mp4)

    monkeypatch.setattr(
        "lol_agent.outplayed_db.get_outplayed_clip_info",
        lambda _p: {
            "source": "outplayed_live",
            "event_tier": "double",
            "event_tier_rank": 2,
            "best_event_time_s": 12.9,
            "est_first_kill_s": 12.9,
            "est_last_kill_s": 15.92,
            "total_kills_in_clip": 2,
            "events_summary": [{"type": "kill", "label": "double_kill", "time_s": 12.9}],
        },
    )
    with patch("lol_agent.game_event_detector.detect_kill_events", return_value=[(0.9, "DOUBLE KILL")]), \
         patch("lol_agent.lol_editor.render_short", side_effect=_fake_render), \
         patch("lol_agent.lol_thumbnail.generate_thumbnail", return_value=str(tmp_path / "t.jpg")), \
         patch("lol_agent.lol_metadata_generator.generate_metadata_universal", return_value={"title": "Clean", "description": "d", "pinned_comment": "c"}), \
         patch("lol_agent.lol_quality_validator.validate_rendered_short") as mock_qa:
        mock_qa.return_value.rejection_code = None
        mock_qa.return_value.qa_status = "PASS"
        mock_qa.return_value.qa_score = 92
        pipeline_runner._cancel_event.clear()
        pipeline_runner._run_pipeline(
            source_path=str(dummy_video),
            clip_start=10.88,
            clip_end=15.20,
            action_type="double",
            champion_name="Katarina",
            rank="Master",
            peak_moment=12.9,
            hook_text="DOUBLE KILL - CLEAN OR LUCKY?",
            output_filename="short_r5_out.mp4",
            use_speed_ramp=True,
            use_zoom_punch=True,
            use_smart_camera=True,
            notify_token=None,
            montage_style_override="ARENA_WIDE",
        )

    assert captured["clip_end"] == 15.20, captured
    assert len(captured["peaks"]) == 1, captured["peaks"]
    assert captured["peaks"][0][1] == "DOUBLE KILL"


def test_overnight_defaults_to_compare_all_3_dedups_titles_and_enriches_latest(monkeypatch, tmp_path):
    monkeypatch.setattr(ob, "OVERNIGHT_DIR", tmp_path / "batches")
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", tmp_path / "batches" / "latest_batch.json")
    monkeypatch.setattr(ob, "_probe_ig_compliance", lambda _p: {"ig_ready": True, "ig_issues": []})
    monkeypatch.setattr(ob, "_annotate_output_metas", lambda *_a, **_kw: None)

    src1 = tmp_path / "c1.mp4"
    src2 = tmp_path / "c2.mp4"
    src1.write_bytes(b"v1")
    src2.write_bytes(b"v2")

    fake_scan = {
        "folder": str(tmp_path),
        "total_clips_found": 2,
        "skipped_published": 0,
        "scanned_unpublished": 2,
        "qualified_count": 2,
        "rejected_count": 0,
        "rejection_breakdown": {},
        "selected": [
            {
                "filename": src1.name, "path": str(src1), "action_type": "double",
                "champion": "Katarina", "event_source": "outplayed_live",
                "clip_start": 5.0, "clip_end": 16.0, "peak_moment": 12.0,
                "combat_segments": None, "hook_text": "DOUBLE KILL - CLEAN OR LUCKY?",
                "hype_score": 82.0, "fallback_mediocre": False,
            },
            {
                "filename": src2.name, "path": str(src2), "action_type": "double",
                "champion": "Katarina", "event_source": "outplayed_live",
                "clip_start": 4.0, "clip_end": 15.0, "peak_moment": 11.0,
                "combat_segments": None, "hook_text": "DOUBLE KILL - CLEAN OR LUCKY?",
                "hype_score": 80.0, "fallback_mediocre": False,
            },
        ],
    }
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **kw: fake_scan)

    from lol_agent.api import pipeline_runner
    fake_state: Dict[str, Any] = {"status": "idle", "output_path": None}
    hooks_seen: List[str] = []

    def _fake_pipe(**kwargs):
        hooks_seen.append(str(kwargs.get("hook_text") or ""))
        out_p = tmp_path / kwargs["output_filename"]
        out_p.write_bytes(b"mp4")
        thumb_p = tmp_path / f"{Path(kwargs['output_filename']).stem}_thumb.jpg"
        thumb_p.write_bytes(b"jpg")
        fake_state.clear()
        fake_state.update({
            "status": "done",
            "output_path": str(out_p),
            "thumbnail_path": str(thumb_p),
            "action_type": kwargs["action_type"],
            "clip_start": kwargs["clip_start"],
            "clip_end": kwargs["clip_end"],
            "title": "Cleanest 2v1 Spacing Trap 🔥 #shorts #leagueoflegends #lol",
            "title_variant_b": "Greedy 2v1 Turned Around 😈 #shorts #leagueoflegends #lol",
            "qa_status": "PASS",
            "qa_score": 92,
        })

    def _fake_insp(mp4_path: str):
        return {
            "watchability_score": 93.0,
            "frame0_hook_legible": True,
            "kill_overlay_zone": "upper_safe",
            "player_visible_ratio": 0.92,
            "player_edge_clip_ratio": 0.0,
            "audio_clip_gt_096": 0,
            "av_delta_s": 0.01,
            "black_end_frame": False,
            "hook_is_generic": False,
            "hook_text": hooks_seen[-1] if hooks_seen else "WAIT FOR THE SECOND RESET",
            "video_dur_s": 10.8,
            "first_kill_out_sec": 2.6,
            "longest_gap_out_sec": 2.4,
            "camera_peak_step_px": 95.0,
        }

    monkeypatch.setattr(pipeline_runner, "_run_pipeline", _fake_pipe)
    monkeypatch.setattr(pipeline_runner, "get_state", lambda: dict(fake_state))
    monkeypatch.setattr("lol_agent.synapsa_watchability_judge.inspect_rendered_short", _fake_insp)

    manifest = ob.run_overnight_batch(top_n=2, use_local_ai=False)
    assert manifest["montage_preset"] == "compare_all_3"
    assert len(manifest["items"]) == 2
    assert all(len(it.get("alternate_renders") or []) == 3 for it in manifest["items"])
    assert all(all(a.get("file_exists") is True for a in it["alternate_renders"]) for it in manifest["items"])

    titles = [ob._normalize_title_key(it["title"]) for it in manifest["items"]]
    assert len(set(titles)) == 2, f"Duplikat tytułów w jednej paczce: {[it['title'] for it in manifest['items']]}"
    assert all(not h.upper().startswith("DOUBLE KILL - ") for h in hooks_seen), hooks_seen

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = client.get("/overnight/latest", headers=headers)
        assert resp.status_code == 200
        latest = resp.json()["batch"]
        for it in latest["items"]:
            assert len(it["alternate_renders"]) == 3
            assert all(alt.get("file_exists") is True for alt in it["alternate_renders"])
