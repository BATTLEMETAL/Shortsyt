"""
Testy regresyjne Etapu 47:
  - pipeline_runner.stop_pipeline() + InterruptedError -> PipelineStatus.IDLE i error=None (koniec fałszywego ■ BŁĄD)
  - synapsa_overnight_batch.run_overnight_batch() przy przerwaniu (_OVERNIGHT_CANCEL):
      * pusty wynik nie nadpisuje latest_batch.json
      * częściowy wynik zapisuje ukończone karty + alternate_renders do batch_*.json i latest_batch.json
  - lol_editor.build_cta_overlay_filters() w STORY_RAW_POV -> górna strefa (y=200), zero kolizji z dolnym napisem FINAL KILL
  - lol_thumbnail._find_best_crop_x() + _find_ranked_hero_frames() -> odrzucanie szarego ekranu śmierci i centrowanie na paskach HP
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lol_agent import lol_editor as E
from lol_agent import lol_thumbnail as T
from lol_agent import synapsa_overnight_batch as ob
from lol_agent.api import pipeline_runner as pr


def test_stop_pipeline_sets_idle_not_error(monkeypatch):
    class _FakeProc:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    proc = _FakeProc()
    with pr._lock:
        pr._cancel_event.clear()
        pr._job_queue.append({"output_filename": "queued.mp4"})
        pr._active_proc = proc
        pr._state.status = pr.PipelineStatus.RUNNING
        pr._state.progress = 90
        pr._state.error = None

    pr.stop_pipeline()
    st = pr.get_state()
    assert proc.terminated is True
    assert st["status"] == pr.PipelineStatus.IDLE.value
    assert st["error"] is None
    assert st["progress"] == 0
    assert pr._job_queue == []

    # Również rzucenie InterruptedError w _run_pipeline (z anulowania) musi kończyć w IDLE z error=None
    monkeypatch.setattr(pr, "_update", lambda *_a, **_kw: (_ for _ in ()).throw(InterruptedError("Przerwano przez użytkownika")))
    pr._run_pipeline(
        source_path="missing.mp4",
        clip_start=0.0,
        clip_end=10.0,
        action_type="double",
        champion_name="Katarina",
        rank="Master",
        peak_moment=5.0,
        hook_text="WAIT FOR THE RESET",
        output_filename="out.mp4",
        use_speed_ramp=True,
        use_zoom_punch=True,
        use_smart_camera=True,
        notify_token=None,
    )
    st_after = pr.get_state()
    assert st_after["status"] == pr.PipelineStatus.IDLE.value
    assert st_after["error"] is None
    assert st_after["progress"] == 0


def test_overnight_cancel_persists_partial_batch(tmp_path, monkeypatch):
    batches_dir = tmp_path / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    latest_fp = batches_dir / "latest_batch.json"
    sentinel = {"batch_id": "prev_keep", "items": [{"output_filename": "old.mp4"}]}
    latest_fp.write_text(json.dumps(sentinel), encoding="utf-8")

    monkeypatch.setattr(ob, "OVERNIGHT_DIR", batches_dir)
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", latest_fp)
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
                "combat_segments": None, "hook_text": "WAIT FOR THE RESET",
                "hype_score": 82.0, "fallback_mediocre": False,
            },
            {
                "filename": src2.name, "path": str(src2), "action_type": "double",
                "champion": "Katarina", "event_source": "outplayed_live",
                "clip_start": 4.0, "clip_end": 15.0, "peak_moment": 11.0,
                "combat_segments": None, "hook_text": "NEVER CHASE KATARINA",
                "hype_score": 80.0, "fallback_mediocre": False,
            },
        ],
    }

    # Przypadek A: anulowanie w skanie (0 ukończonych klipów) -> nie nadpisuje latest_batch.json
    def _scan_cancelled(**_kw):
        ob._OVERNIGHT_CANCEL.set()
        return fake_scan

    monkeypatch.setattr(ob, "scan_and_rank_all_clips", _scan_cancelled)
    res_empty = ob.run_overnight_batch(top_n=2, use_local_ai=False)
    assert res_empty["status"] == "stopped"
    assert res_empty["items"] == []
    assert json.loads(latest_fp.read_text(encoding="utf-8"))["batch_id"] == "prev_keep"

    # Przypadek A2: anulowanie w trakcie 1. klipu bez żadnego render_ok=True -> też nie nadpisuje latest_batch.json
    ob._OVERNIGHT_CANCEL.clear()
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **_kw: fake_scan)
    monkeypatch.setattr(pr, "_run_pipeline", lambda **_kw: ob._OVERNIGHT_CANCEL.set())
    monkeypatch.setattr(pr, "get_state", lambda: {"status": "idle", "error": None, "output_path": None})
    res_failed_only = ob.run_overnight_batch(top_n=1, use_local_ai=False)
    assert res_failed_only["status"] == "stopped"
    assert json.loads(latest_fp.read_text(encoding="utf-8"))["batch_id"] == "prev_keep"

    # Przypadek B: anulowanie po ukończeniu 1. klipu (compare_all_3) -> zapisuje częściowy manifest z 3 wariantami
    ob._OVERNIGHT_CANCEL.clear()
    monkeypatch.setattr(ob, "scan_and_rank_all_clips", lambda **_kw: fake_scan)

    fake_state: Dict[str, Any] = {"status": "idle", "output_path": None}
    renders_called: List[str] = []

    def _fake_pipe(**kwargs):
        out_fn = str(kwargs["output_filename"])
        renders_called.append(out_fn)
        out_p = tmp_path / out_fn
        out_p.write_bytes(b"mp4")
        thumb_p = tmp_path / f"{out_p.stem}_thumb.jpg"
        thumb_p.write_bytes(b"jpg")
        fake_state.clear()
        fake_state.update({
            "status": "done",
            "output_path": str(out_p),
            "thumbnail_path": str(thumb_p),
            "action_type": kwargs["action_type"],
            "clip_start": kwargs["clip_start"],
            "clip_end": kwargs["clip_end"],
            "title": "Clean Base Gates Reset 🔥 #shorts #leagueoflegends #lol",
            "qa_status": "PASS",
            "qa_score": 91,
        })
        if len(renders_called) == 3:
            ob._OVERNIGHT_CANCEL.set()

    monkeypatch.setattr(pr, "_run_pipeline", _fake_pipe)
    monkeypatch.setattr(pr, "get_state", lambda: dict(fake_state))
    monkeypatch.setattr(
        "lol_agent.synapsa_watchability_judge.inspect_rendered_short",
        lambda _p: {
            "watchability_score": 94.0,
            "frame0_hook_legible": True,
            "kill_overlay_zone": "upper_safe",
            "player_visible_ratio": 0.90,
            "player_edge_clip_ratio": 0.0,
            "audio_clip_gt_096": 0,
            "av_delta_s": 0.01,
            "black_end_frame": False,
            "hook_is_generic": False,
            "hook_text": "WAIT FOR THE RESET",
            "video_dur_s": 10.6,
            "first_kill_out_sec": 2.8,
            "longest_gap_out_sec": 2.5,
            "camera_peak_step_px": 92.0,
        },
    )

    res_partial = ob.run_overnight_batch(top_n=2, use_local_ai=False)
    assert res_partial["status"] == "stopped"
    assert len(res_partial["items"]) == 1
    assert len(res_partial["items"][0].get("alternate_renders") or []) == 3
    assert res_partial["summary_pl"].startswith("[Przerwano po 1 klipach]")

    persisted_latest = json.loads(latest_fp.read_text(encoding="utf-8"))
    assert persisted_latest["batch_id"] == res_partial["batch_id"]
    assert persisted_latest["status"] == "stopped"
    assert len(persisted_latest["items"]) == 1
    assert (batches_dir / f"batch_{res_partial['batch_id']}.json").is_file()


def test_story_raw_pov_cta_no_overlap_with_kill_banner():
    filters = E.build_cta_overlay_filters(
        video_duration=11.0,
        cta_text="SPOT THE MISTAKE BELOW",
        show_duration=2.2,
        style_mode="STORY_RAW_POV",
    )
    assert filters, "Brak filtrów CTA dla STORY_RAW_POV"
    drawbox = filters[0]
    assert "y=200:" in drawbox, f"CTA dla STORY_RAW_POV nadal koliduje z dołem: {drawbox}"
    assert "y=1660" not in drawbox
    # Dolny baner FINAL KILL w STORY_RAW_POV leży w strefie h*0.822..h*0.896 (~1578..1720px na 1920)
    assert all(":y=2" in dt or ":y=200" in dt or int(dt.split(":y=")[1].split(":")[0]) < 400 for dt in filters[1:])


def test_thumbnail_rejects_grey_death_screen_and_centers_on_hp_bars(tmp_path):
    # 1) _find_best_crop_x powinno wycentrować kadr na walce z zielonym + czerwonym paskiem HP (prawa strona),
    #    zamiast na jaskrawej fioletowej tarczy/drzewie po lewej stronie.
    rgb = np.full((1080, 1920, 3), (30, 50, 75), dtype=np.uint8)
    # Lewy wabik (fioletowa plama bez HP)
    rgb[300:460, 180:320] = (180, 40, 210)
    # Prawa walka: zielony pasek gracza + czerwony pasek wroga
    rgb[360:376, 1410:1510] = (40, 215, 50)
    rgb[410:426, 1440:1540] = (220, 35, 35)

    crop_w = 500
    x0 = T._find_best_crop_x(rgb, crop_w, source_w=1920)
    crop_center = x0 + crop_w / 2.0
    assert crop_center > 1050.0, f"Crop nie wycentrował na paskach HP po prawej: cx={crop_center}, x0={x0}"

    # 2) _find_ranked_hero_frames odrzuca szary ekran śmierci BACK IN (nawet z małym czerwonym znaczkiem)
    #    i preferuje klatkę walki nad pustym śniegiem
    mp4_path = tmp_path / "hero_test.mp4"
    writer = cv2.VideoWriter(str(mp4_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (1920, 1080))
    assert writer.isOpened()
    try:
        # 0.0-1.8s: akcja w centrum (zielony + czerwony + złoty pasek + kolorowe VFX)
        combat_fr = np.full((1080, 1920, 3), (85, 65, 45), dtype=np.uint8)  # BGR
        combat_fr[280:650, 620:1300] = (170, 80, 220)
        combat_fr[400:420, 840:1020] = (50, 220, 40)    # green HP
        combat_fr[440:460, 900:1060] = (35, 35, 225)    # red HP
        combat_fr[360:380, 880:1040] = (50, 195, 235)   # gold
        for _ in range(18):
            writer.write(combat_fr)

        # 1.8-3.0s: pusty niebieski śnieg bez postaci
        snow_fr = np.full((1080, 1920, 3), (185, 130, 85), dtype=np.uint8)
        for _ in range(12):
            writer.write(snow_fr)

        # 3.0-5.0s: szary ekran śmierci (niski saturation w centrum + drobna czerwona kropka timerka)
        grey_fr = np.full((1080, 1920, 3), (95, 95, 98), dtype=np.uint8)
        grey_fr[780:800, 940:960] = (15, 20, 230)
        for _ in range(20):
            writer.write(grey_fr)
    finally:
        writer.release()

    picked = T._find_ranked_hero_frames(str(mp4_path), center_t=3.5, search_window=5.0, max_candidates=1)
    assert picked and picked[0] < 1.9, f"Wybrano szary ekran śmierci lub pusty śnieg zamiast klatki akcji: t={picked}"
