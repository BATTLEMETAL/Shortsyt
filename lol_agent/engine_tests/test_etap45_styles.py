"""
Testy jednostkowe Etapu 45:
  - Zgodność engine_rules.json["style_profiles"] <-> lol_timeline.STYLE_PROFILES <-> lol_montage_director
  - build_speed_segments z nadpisaniami stylu (buildup_speed=1.45, slowmo_window_max=1.35)
  - apply_editor_effects FFmpeg filtergraph (ARENA_WIDE / BEAT_VELOCITY / STORY_RAW_POV + segmentowe minterpolate na GPU)
  - apply_overlays_unified / build_text_overlay_filters (brak ghost boxa przy fade, biały banner, impact flash)
  - _detect_death_or_tab_end na syntetycznym wideo (szary ekran śmierci)
  - _apply_outplayed_anchor na pojedynczym podwójnym timestampie bez martwego outro +6.4s
  - run_overnight_batch(..., montage_preset="auto_fallback" / "compare_all_3") oraz POST /overnight/restyle
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import lol_timeline as TL
from lol_agent import lol_montage_director as MD
from lol_agent import lol_editor as E
from lol_agent import synapsa_overnight_batch as ob
from lol_agent.api.config import API_PASSWORD
from lol_agent.api.main import app


def test_style_profiles_match_engine_rules_and_keep_legacy_fallback_isolated():
    rules_path = ROOT / "lol_agent" / "engine_rules.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    rule_profiles = rules["style_profiles"]

    assert set(rule_profiles.keys()) == {"ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV"}
    assert tuple(TL.VIRAL_STYLES) == ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV")

    for style_name, expected in rule_profiles.items():
        prof = TL.get_style_profile(style_name)
        assert prof == expected, f"Rozbieżność profilu {style_name}: {prof} != {expected}"

    assert TL.get_style_profile("PRIMARY") is None
    assert set(MD.VIRAL_STYLE_DESCS.keys()) == set(TL.VIRAL_STYLES)
    assert set(MD.FALLBACK_STYLES.keys()) == {
        "SPEED_RAMP_FLOW",
        "IN_MEDIA_RES",
        "CINEMATIC_DUEL",
        "BEAT_REALIGN",
    }

    dec = MD.direct_clip_montage(
        action_type="double",
        champion_name="Katarina",
        duration=12.0,
        peaks=[(3.0, "KILL"), (8.5, "DOUBLE KILL")],
        force_style="ARENA_WIDE",
    )
    assert dec.archetype == "ARENA_WIDE"
    assert dec.tuning_profile["preferred_montage_style"] == "ARENA_WIDE"
    assert dec.tuning_profile["drop_anchor"] == "climax_final_kill"


def test_beat_velocity_timeline_buildup_and_slowmo_overrides():
    segs = TL.build_speed_segments(
        clip_duration=12.0,
        peak_moment=8.0,
        slowmo_speed=0.40,
        slowmo_duration=1.35,
        zoom_duration=0.65,
        intermediate_peaks=None,
        use_easing=True,
        slowmo_window_max=1.35,
        zoom_window_max=0.65,
        buildup_speed=1.45,
    )
    assert any(abs(float(s["speed"]) - 1.45) < 1e-3 for s in segs), f"Brak buildup 1.45x w {segs}"
    slow_segs = [s for s in segs if abs(float(s["speed"]) - 0.40) < 1e-3]
    assert slow_segs, f"Brak slow-mo 0.40x w {segs}"
    total_slow_src = sum(float(s["end"]) - float(s["start"]) for s in slow_segs)
    assert total_slow_src >= 1.20, f"Slow-mo nie dostało nadpisanego okna 1.35s: {total_slow_src}"


def test_apply_editor_effects_filtergraphs_for_all_3_styles_with_gpu_minterpolate(monkeypatch, tmp_path):
    src = tmp_path / "dummy_src.mp4"
    src.write_bytes(b"src_bytes")

    captured: Dict[str, str] = {}

    monkeypatch.setattr(E, "detect_hardware", lambda: ("h264_nvenc", "NVIDIA RTX 3060"))
    monkeypatch.setattr(E, "get_optimal_encoder_args", lambda quality="high": ["-c:v", "h264_nvenc", "-preset", "p5"])

    def _fake_run(cmd, timeout=180.0, desc=""):
        if "-filter_complex_script" in cmd:
            fc_path = cmd[cmd.index("-filter_complex_script") + 1]
            captured["script"] = Path(fc_path).read_text(encoding="utf-8")
        Path(cmd[-1]).write_bytes(b"rendered_mp4")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(E, "_run_ffmpeg", _fake_run)

    # 1. ARENA_WIDE
    captured.clear()
    tl_arena: Dict[str, Any] = {}
    E.apply_editor_effects(
        str(src), str(tmp_path / "out_arena.mp4"), 11.0, "240",
        peak_moment=7.5, slowmo_speed=0.45, slowmo_duration=1.15,
        timeline_out=tl_arena, montage_style="ARENA_WIDE",
    )
    fc_arena = captured["script"]
    assert "boxblur=24:2" in fc_arena
    assert "crop=1280:940:" in fc_arena
    assert "scale=1080:880" in fc_arena
    assert "minterpolate=fps=60:mi_mode=blend" in fc_arena
    assert tl_arena["output_duration"] > 11.0

    # 2. BEAT_VELOCITY
    captured.clear()
    tl_beat: Dict[str, Any] = {}
    E.apply_editor_effects(
        str(src), str(tmp_path / "out_beat.mp4"), 11.0, "656",
        peak_moment=7.5, zoom_level=1.14, zoom_duration=0.55,
        slowmo_speed=0.40, slowmo_duration=1.00,
        timeline_out=tl_beat, montage_style="BEAT_VELOCITY",
    )
    fc_beat = captured["script"]
    assert "crop=608:" in fc_beat
    assert "vignette=" in fc_beat
    assert "minterpolate=fps=60:mi_mode=blend" in fc_beat
    assert tl_beat["output_duration"] > 11.0

    # 3. STORY_RAW_POV
    captured.clear()
    tl_story: Dict[str, Any] = {}
    E.apply_editor_effects(
        str(src), str(tmp_path / "out_story.mp4"), 11.0, "480",
        peak_moment=8.0, slowmo_speed=0.55, slowmo_duration=0.55,
        timeline_out=tl_story, montage_style="STORY_RAW_POV",
    )
    fc_story = captured["script"]
    assert "crop=960:940:" in fc_story
    assert "boxblur=28:2" in fc_story
    assert "scale=1080:1150" in fc_story
    assert "overlay=0:385" in fc_story
    assert len(tl_story["segments"]) >= 2


def test_overlays_fix_ghost_black_box_and_differentiate_3_styles(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "_get_font_path", lambda: "C:/Windows/Fonts/arialbd.ttf")

    hook_arena = E.build_text_overlay_filters(
        "GREEDY 2V1 UNDER TOWER", peak_moment=0.0, video_duration=12.0,
        show_duration=2.0, style_mode="ARENA_WIDE",
    )
    # drawbox nie może mieć końca równego t_end=2.00 (zostawiało pusty czarny pasek w t=2.0s)
    box_filters = [f for f in hook_arena if f.startswith("drawbox=")]
    assert box_filters, "ARENA_WIDE powinien mieć banner kontenerowy"
    assert all("between(t,0.00,2.00)" not in bf for bf in box_filters), box_filters
    assert any("between(t,0.00,1.84)" in bf for bf in box_filters), box_filters

    hook_story = E.build_text_overlay_filters(
        "CLEAN KATARINA DOUBLE", peak_moment=0.0, video_duration=12.0,
        show_duration=2.6, style_mode="STORY_RAW_POV",
    )
    assert any("color=0xF5F6F8@0.97" in f for f in hook_story)
    assert any("fontcolor=0x0D0F12" in f for f in hook_story)

    # CAPTURE unified filtergraph dla BEAT_VELOCITY (biały impact flash na kulminacji)
    captured_cmds: List[List[str]] = []

    def _fake_ov_ffmpeg(cmd, timeout=180.0, desc=""):
        captured_cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"ov_mp4")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(E, "_run_ffmpeg", _fake_ov_ffmpeg)
    monkeypatch.setattr(E, "get_optimal_encoder_args", lambda quality="high": ["-c:v", "libx264"])
    in_v = tmp_path / "in.mp4"
    in_v.write_bytes(b"in")
    out_v = tmp_path / "out.mp4"
    E.apply_overlays_unified(
        video_path=str(in_v),
        output_path=str(out_v),
        peaks=[(3.2, "KILL"), (7.5, "DOUBLE KILL")],
        trim_start=0.0,
        video_duration=12.0,
        peak_moment=7.5,
        slowmo_speed=0.40,
        slowmo_duration=1.35,
        action_type="double",
        hook_text="1V2 TURN AROUND",
        cta_text="SUBSCRIBE FOR MORE",
        style_mode="BEAT_VELOCITY",
    )
    assert captured_cmds
    vf_arg = captured_cmds[0][captured_cmds[0].index("-filter_complex_script") + 1] if "-filter_complex_script" in captured_cmds[0] else ""
    vf_inline = captured_cmds[0][captured_cmds[0].index("-vf") + 1] if "-vf" in captured_cmds[0] else vf_arg
    assert "color=white@0.42" in vf_inline, f"Brak białego impact flasha w BEAT_VELOCITY: {vf_inline[:500]}"


def test_detect_death_or_tab_end_catches_synthetic_grey_death_screen(tmp_path):
    vid_path = tmp_path / "death_tail.mp4"
    w, h, fps = 640, 360, 20.0
    writer = cv2.VideoWriter(str(vid_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    try:
        vivid = np.full((h, w, 3), (40, 180, 90), dtype=np.uint8)
        grey = np.full((h, w, 3), (65, 65, 65), dtype=np.uint8)
        for _ in range(int(6.0 * fps)):
            writer.write(vivid)
        for _ in range(int(2.5 * fps)):
            writer.write(grey)
    finally:
        writer.release()

    det_t, det_kind = E._detect_death_or_tab_end(str(vid_path), 0.0, 8.5, last_peak_abs=5.2)
    assert det_kind == "death_screen"
    assert det_t is not None and 5.75 <= det_t <= 6.45


def test_outplayed_anchor_single_timestamp_double_prevents_dead_tower_outro(monkeypatch, tmp_path):
    vid = tmp_path / "r2_src.mp4"
    vid.write_bytes(b"video")
    monkeypatch.setattr(ob, "_check_trailing_survival", lambda *_a, **_kw: True)
    entry = {
        "path": str(vid),
        "filename": vid.name,
        "duration": 55.0,
        "fps": 60.0,
        "action_type": "double",
        "event_tier": "double",
        "event_tier_rank": 2,
        "event_source": "outplayed_highlights",
        "best_event_time_s": 45.49,
        "kill_timestamps": [],
        "combat_segments": None,
        "events_summary": [],
    }
    _, det, new_s, new_e, new_pk, _ = ob._apply_outplayed_anchor(
        entry, [], "double", 33.0, 53.0, 45.49, None, 55.0
    )
    assert det == "double"
    # Bez starego błędu clip_end=51.89 (+6.4s bicia wieży po 45.49)
    assert new_e - 45.49 <= 4.15, (new_s, new_e, new_pk)
    assert 45.49 - new_s >= 3.75, (new_s, new_e, new_pk)
    assert 8.0 <= (new_e - new_s) <= 10.5, (new_s, new_e, new_pk)


def test_overnight_auto_fallback_and_compare_all_3(monkeypatch, tmp_path):
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", tmp_path / "latest_batch.json")
    monkeypatch.setattr(ob, "_persist_batch_manifest", lambda m: (tmp_path / "latest_batch.json").write_text(json.dumps(m), encoding="utf-8") or str(tmp_path / "latest_batch.json"))
    monkeypatch.setattr(ob, "_probe_ig_compliance", lambda _p: {"ig_ready": True, "ig_issues": []})
    monkeypatch.setattr(ob, "_annotate_output_metas", lambda *_a, **_kw: None)

    src_vid = tmp_path / "src_double.mp4"
    src_vid.write_bytes(b"src_bytes")
    fake_scan = {
        "folder": str(tmp_path),
        "total_clips_found": 1,
        "skipped_published": 0,
        "scanned_unpublished": 1,
        "qualified_count": 1,
        "rejected_count": 0,
        "rejection_breakdown": {},
        "selected": [{
            "filename": src_vid.name,
            "path": str(src_vid),
            "action_type": "double",
            "champion": "Katarina",
            "event_source": "outplayed_highlights",
            "clip_start": 10.0,
            "clip_end": 22.0,
            "peak_moment": 18.0,
            "combat_segments": None,
            "hook_text": "CLEAN DOUBLE",
            "hype_score": 84.0,
            "fallback_mediocre": False,
        }],
    }
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **kw: fake_scan)

    from lol_agent.api import pipeline_runner
    fake_state: Dict[str, Any] = {"status": "idle", "output_path": None}
    style_calls: List[str] = []

    def _fake_pipe(**kwargs):
        st = str(kwargs.get("montage_style_override") or "PRIMARY")
        style_calls.append(st)
        out_p = tmp_path / kwargs["output_filename"]
        out_p.write_bytes(b"mp4")
        fake_state.clear()
        fake_state.update({
            "status": "done",
            "output_path": str(out_p),
            "thumbnail_path": None,
            "action_type": kwargs["action_type"],
            "clip_start": kwargs["clip_start"],
            "clip_end": kwargs["clip_end"],
            "title": f"Test Title {st}",
            "qa_status": "PASS",
            "qa_score": 92,
        })

    def _fake_insp(mp4_path: str):
        fn = Path(mp4_path).name
        is_alt_or_arena = ("arena_wide" in fn)
        # Pierwszy pass (BEAT_VELOCITY dla double) ma skok kamery i <76 -> musi uruchomic fallback ARENA_WIDE!
        return {
            "watchability_score": 91.0 if is_alt_or_arena else 68.0,
            "frame0_hook_legible": True,
            "kill_overlay_zone": "upper_safe",
            "player_visible_ratio": 0.92 if is_alt_or_arena else 0.65,
            "player_edge_clip_ratio": 0.04,
            "audio_clip_gt_096": 0,
            "av_delta_s": 0.02,
            "black_end_frame": False,
            "hook_is_generic": False,
            "hook_text": "CLEAN DOUBLE",
            "video_dur_s": 11.4 if is_alt_or_arena else 10.6,
            "first_kill_out_sec": 2.4,
            "longest_gap_out_sec": 2.8,
            "camera_peak_step_px": 110.0 if is_alt_or_arena else 360.0,
        }

    monkeypatch.setattr(pipeline_runner, "_run_pipeline", _fake_pipe)
    monkeypatch.setattr(pipeline_runner, "get_state", lambda: dict(fake_state))
    monkeypatch.setattr("lol_agent.synapsa_watchability_judge.inspect_rendered_short", _fake_insp)

    # 1. auto_fallback
    manifest_fb = ob.run_overnight_batch(top_n=1, use_local_ai=False, montage_preset="auto_fallback")
    assert style_calls == ["BEAT_VELOCITY", "ARENA_WIDE"], style_calls
    item_fb = manifest_fb["items"][0]
    assert item_fb["montage_style"] == "ARENA_WIDE"
    assert item_fb["fallback_triggered"] is True
    assert item_fb["fallback_from_style"] == "BEAT_VELOCITY"
    assert len(item_fb["alternate_renders"]) == 2
    assert item_fb["publish_recommended"] is True

    # 2. compare_all_3
    style_calls.clear()
    manifest_cmp = ob.run_overnight_batch(top_n=1, use_local_ai=False, montage_preset="compare_all_3")
    assert style_calls == ["ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV"], style_calls
    assert len(manifest_cmp["items"][0]["alternate_renders"]) == 3


def test_overnight_restyle_endpoint_validation_and_success(monkeypatch):
    def _mock_restyle(output_filename: str, target_style: str):
        if target_style not in ob.VIRAL_STYLE_ORDER:
            raise ValueError("Invalid style")
        return {
            "status": "done",
            "target_style": target_style,
            "item": {"output_filename": "short_test_style_arena_wide.mp4", "montage_style": target_style, "render_ok": True},
            "variant": {"output_filename": "short_test_style_arena_wide.mp4", "montage_style": target_style, "is_selected": True},
            "batch_updated": True,
        }

    monkeypatch.setattr(ob, "restyle_overnight_short", _mock_restyle)
    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        r_bad = client.post("/overnight/restyle", json={"output_filename": "short_a.mp4", "target_style": "BAD_STYLE"}, headers=headers)
        assert r_bad.status_code == 422

        r_ok = client.post("/overnight/restyle", json={"output_filename": "short_a.mp4", "target_style": "ARENA_WIDE"}, headers=headers)
        assert r_ok.status_code == 200
        body = r_ok.json()
        assert body["target_style"] == "ARENA_WIDE"
        assert body["batch_updated"] is True


def test_canonicalize_to_source_time_prevents_inverted_double_kill():
    # Regresja dla r3_double: clip_start=8.5, clip_end=21.6 (dur=13.1), peaks=[(3.5,'KILL'),(9.5,'DOUBLE KILL')], peak_moment=9.1
    # Per-element `>= clip_start` błędnie zostawiało 3.5+8.5=12.0 i traktowało 9.5 jako 9.5s (1.0s w klipie)!
    abs_peaks, abs_pm = E._canonicalize_to_source_time(
        [(3.5, "KILL"), (9.5, "DOUBLE KILL")],
        peak_m=9.1,
        clip_s=8.5,
        clip_d=13.1,
    )
    assert abs_peaks == [(12.0, "KILL"), (18.0, "DOUBLE KILL")], abs_peaks
    assert abs_pm == 17.6, abs_pm


def test_pipeline_runner_backfills_outplayed_est_first_kill(monkeypatch, tmp_path):
    from unittest.mock import patch
    from lol_agent.api import pipeline_runner

    dummy_video = tmp_path / "r2_double_clip.mp4"
    dummy_video.write_bytes(b"video_bytes")
    rendered_mp4 = tmp_path / "short_r2_out.mp4"
    rendered_mp4.write_bytes(b"out_bytes")

    captured: Dict[str, Any] = {}

    def _fake_render(**kwargs):
        captured["peaks"] = list(kwargs.get("peaks") or [])
        captured["peak_moment"] = kwargs.get("peak_moment")
        return str(rendered_mp4)

    monkeypatch.setattr(
        "lol_agent.outplayed_db.get_outplayed_clip_info",
        lambda _p: {
            "source": "outplayed_backup",
            "event_tier": "double",
            "event_tier_rank": 2,
            "est_first_kill_s": 43.49,
            "est_last_kill_s": 45.49,
            "total_kills_in_clip": 2,
        },
    )
    with patch("lol_agent.game_event_detector.detect_kill_events", return_value=[(5.51, "DOUBLE KILL")]), \
         patch("lol_agent.lol_editor.render_short", side_effect=_fake_render), \
         patch("lol_agent.lol_thumbnail.generate_thumbnail", return_value=str(tmp_path / "t.jpg")), \
         patch("lol_agent.lol_metadata_generator.generate_metadata_universal", return_value={"title": "Clean Double", "description": "d", "pinned_comment": "c"}), \
         patch("lol_agent.lol_quality_validator.validate_rendered_short") as mock_qa:
        mock_qa.return_value.rejection_code = None
        mock_qa.return_value.qa_status = "PASS"
        mock_qa.return_value.qa_score = 92
        pipeline_runner._cancel_event.clear()
        pipeline_runner._run_pipeline(
            source_path=str(dummy_video),
            clip_start=40.49,
            clip_end=48.99,
            action_type="double",
            champion_name="Katarina",
            rank="Master",
            peak_moment=45.49,
            hook_text="CLEAN DOUBLE",
            output_filename="short_r2_out.mp4",
            use_speed_ramp=True,
            use_zoom_punch=True,
            use_smart_camera=True,
            notify_token=None,
            montage_style_override="ARENA_WIDE",
        )

    assert len(captured["peaks"]) == 2, captured
    assert abs(captured["peaks"][0][0] - 3.00) <= 0.05 and captured["peaks"][0][1] == "KILL"
    assert abs(captured["peaks"][1][0] - 5.51) <= 0.05 and captured["peaks"][1][1] == "DOUBLE KILL"
