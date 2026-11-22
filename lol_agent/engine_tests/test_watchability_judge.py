"""Testy sędziego oglądalności i weryfikatora hipotez Synapsy (Etap 10)."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import synapsa_watchability_judge as SWJ
import synapsa_conversation_learner as SCL


def _write_synthetic_short(
    tmp_path: Path,
    name: str,
    *,
    frame0_hook: bool = True,
    kill_zone: str = "upper_safe",
    hook_text: str = "TRIPLE KILL RESET",
    action_type: str = "triple",
    camera_peak_step_px: float = 320.0,
    first_kill_sec: float = 1.1,
    fps: int = 20,
    dur_s: float = 2.0,
) -> Path:
    w, h = 270, 480
    mp4_path = tmp_path / f"{name}.mp4"
    writer = cv2.VideoWriter(str(mp4_path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
    assert writer.isOpened()
    n_frames = int(fps * dur_s)

    for i in range(n_frames):
        t = i / float(fps)
        # Średnio jasne tło gry (V > 70, zero fałszywych trafień dark boxa i paska HP)
        frame = np.full((h, w, 3), (85, 115, 80), dtype=np.uint8)

        # Górny pasek hooka (y = 0.072..0.185)
        hx0, hx1 = int(w * 0.16), int(w * 0.84)
        hy0, hy1 = int(h * 0.08), int(h * 0.175)
        cv2.rectangle(frame, (hx0, hy0), (hx1, hy1), (15, 15, 15), -1)
        if frame0_hook or t >= 0.40:
            cv2.putText(
                frame,
                "QUADRA STEAL",
                (hx0 + 12, hy0 + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                3,
                cv2.LINE_AA,
            )

        # Baner killa: upper_safe (0.215..0.305) vs center_blocking (0.48..0.60)
        if kill_zone == "upper_safe":
            kx0, kx1 = int(w * 0.22), int(w * 0.78)
            ky0, ky1 = int(h * 0.22), int(h * 0.30)
            cv2.rectangle(frame, (kx0, ky0), (kx1, ky1), (15, 15, 15), -1)
            cv2.putText(frame, "KILL 1/3", (kx0 + 18, ky0 + 27), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 3)
        elif kill_zone == "center_blocking":
            kx0, kx1 = int(w * 0.22), int(w * 0.78)
            ky0, ky1 = int(h * 0.49), int(h * 0.59)
            cv2.rectangle(frame, (kx0, ky0), (kx1, ky1), (15, 15, 15), -1)
            cv2.putText(frame, "TRIPLE KILL", (kx0 + 8, ky0 + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 3)

        writer.write(frame)
    writer.release()

    recipe = {
        "source": "synthetic_clip.mp4",
        "action_type": action_type,
        "hook_text": hook_text,
        "camera_peak_step_px": camera_peak_step_px,
        "peaks_in_clip": [[first_kill_sec, "kill"]],
        "time_segments": [{"start": 0.0, "end": dur_s, "speed": 1.0}],
    }
    mp4_path.with_suffix(".recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
    return mp4_path


def test_inspect_detects_frame0_hook_and_overlay_zone(tmp_path):
    bad = _write_synthetic_short(tmp_path, "bad", frame0_hook=False, kill_zone="center_blocking")
    good = _write_synthetic_short(tmp_path, "good", frame0_hook=True, kill_zone="upper_safe")

    r_bad = SWJ.inspect_rendered_short(str(bad))
    r_good = SWJ.inspect_rendered_short(str(good))

    assert r_bad["frame0_hook_legible"] is False
    assert r_bad["kill_overlay_zone"] == "center_blocking"
    assert r_good["frame0_hook_legible"] is True
    assert r_good["kill_overlay_zone"] == "upper_safe"
    assert r_good["watchability_score"] > r_bad["watchability_score"] + 15.0


def test_compare_no_change_vs_better_worse_symmetry_and_mixed(tmp_path):
    bad = _write_synthetic_short(
        tmp_path, "clip_bad", frame0_hook=False, kill_zone="center_blocking", hook_text="INSANE OUTPLAY"
    )
    good = _write_synthetic_short(
        tmp_path, "clip_good", frame0_hook=True, kill_zone="upper_safe", hook_text="BARON STEAL RESET"
    )

    # Identical file -> NO_CHANGE & actually_changed=False + expected BETTER -> NO_EFFECT
    hyp_expect_better = SWJ.predict_change_effect(
        SWJ.inspect_rendered_short(str(good)),
        {"lead_in_max_s": 0.4},
        use_local_ai=False,
    )
    hyp_expect_better["expected_verdict"] = "BETTER"
    hyp_expect_better["expected_metric_shifts"] = {"watchability_score": "UP"}

    same_cmp = SWJ.compare_shorts_and_verify(
        str(good), str(good), hypothesis=hyp_expect_better, use_local_ai=False, log_path=tmp_path / "log.jsonl"
    )
    assert same_cmp["verdict"] == "NO_CHANGE"
    assert same_cmp["actually_changed"] is False
    assert same_cmp["visual_diff"]["mean_frame_mad"] == 0.0
    assert same_cmp["verification"]["hypothesis_status"] == "NO_EFFECT"

    # bad -> good (BETTER) and good -> bad (WORSE) symmetry
    better_cmp = SWJ.compare_shorts_and_verify(
        str(bad),
        str(good),
        proposed_changes={"hook_fade_in": False, "banner_kill_y_ratio": 0.235, "pre_render_synapsa_hook": True},
        use_local_ai=False,
        log_path=tmp_path / "log.jsonl",
    )
    assert better_cmp["verdict"] == "BETTER"
    assert better_cmp["actually_changed"] is True
    assert better_cmp["delta_watchability"] > 15.0
    assert better_cmp["verification"]["hypothesis_status"] == "CONFIRMED"

    worse_cmp = SWJ.compare_shorts_and_verify(
        str(good),
        str(bad),
        proposed_changes={"hook_fade_in": True, "banner_kill_y_ratio": 0.54},
        use_local_ai=False,
        log_path=tmp_path / "log.jsonl",
    )
    assert worse_cmp["verdict"] == "WORSE"
    assert worse_cmp["actually_changed"] is True
    assert worse_cmp["delta_watchability"] < -15.0
    assert worse_cmp["verification"]["hypothesis_status"] == "CONFIRMED"

    # MIXED: improvement (+hook specificity) balanced by non-critical camera regression
    base_m = _write_synthetic_short(
        tmp_path, "mix_a", frame0_hook=True, kill_zone="upper_safe", hook_text="INSANE OUTPLAY", camera_peak_step_px=450.0
    )
    mix_b = _write_synthetic_short(
        tmp_path, "mix_b", frame0_hook=True, kill_zone="upper_safe", hook_text="DRAKE STEAL + TRIPLE", camera_peak_step_px=700.0
    )
    mixed_cmp = SWJ.compare_shorts_and_verify(
        str(base_m), str(mix_b), use_local_ai=False, log_path=tmp_path / "log.jsonl"
    )
    assert mixed_cmp["verdict"] == "MIXED"
    assert mixed_cmp["actually_changed"] is True
    assert mixed_cmp["improvements"]
    assert mixed_cmp["regressions"]


def test_predict_and_verify_all_four_hypothesis_statuses(tmp_path):
    before_metrics = {
        "filename": "b.mp4",
        "watchability_score": 55.0,
        "frame0_hook_legible": False,
        "kill_overlay_zone": "center_blocking",
        "center_blocked_kills_ratio": 1.0,
        "audio_clip_gt_096": 30,
        "av_delta_s": 0.06,
        "camera_peak_step_px": 400.0,
        "player_edge_clip_ratio": 0.0,
        "hook_is_generic": True,
        "black_end_frame": False,
    }
    hyp = SWJ.predict_change_effect(
        before_metrics,
        {"hook_fade_in": False, "banner_kill_y_ratio": 0.235, "alimiter_limit": 0.85},
        use_local_ai=False,
    )
    assert hyp["expected_verdict"] == "BETTER"
    assert hyp["expected_metric_shifts"]["frame0_hook_legible"] == "UP"
    assert hyp["expected_metric_shifts"]["center_blocked_kills_ratio"] == "DOWN"

    # 1. CONFIRMED
    after_ok = dict(
        before_metrics,
        watchability_score=88.0,
        frame0_hook_legible=True,
        kill_overlay_zone="upper_safe",
        center_blocked_kills_ratio=0.0,
        audio_clip_gt_096=0,
    )
    v_conf = SWJ.verify_prediction(hyp, {"verdict": "BETTER", "before": before_metrics, "after": after_ok})
    assert v_conf["hypothesis_status"] == "CONFIRMED"

    # 2. PARTIAL (improved slightly, not all predicted metrics moved)
    after_part = dict(before_metrics, watchability_score=58.0, frame0_hook_legible=True)
    v_part = SWJ.verify_prediction(hyp, {"verdict": "MIXED", "before": before_metrics, "after": after_part})
    assert v_part["hypothesis_status"] == "PARTIAL"

    # 3. NO_EFFECT
    v_none = SWJ.verify_prediction(hyp, {"verdict": "NO_CHANGE", "before": before_metrics, "after": dict(before_metrics)})
    assert v_none["hypothesis_status"] == "NO_EFFECT"

    # 4. REFUTED (predicted BETTER, actual WORSE)
    after_bad = dict(before_metrics, watchability_score=35.0, audio_clip_gt_096=120, black_end_frame=True)
    v_ref = SWJ.verify_prediction(hyp, {"verdict": "WORSE", "before": before_metrics, "after": after_bad})
    assert v_ref["hypothesis_status"] == "REFUTED"


def test_build_watchability_training_examples_covers_all_verdicts_and_statuses(tmp_path):
    fake_log = tmp_path / "verif.jsonl"
    fake_log.write_text(
        json.dumps(
            {
                "before_file": "a.mp4",
                "after_file": "b.mp4",
                "action_type": "quadrakill",
                "verdict": "BETTER",
                "actually_changed": True,
                "before_score": 83.12,
                "after_score": 100.0,
                "delta_watchability": 16.88,
                "mean_frame_mad": 21.9,
                "improvements": ["av_delta_s: 0.067 -> 0.033"],
                "regressions": [],
                "proposed_changes": {"audio_atrim": True, "shunpo_edge_guard_px": 145},
                "expected_verdict": "BETTER",
                "hypothesis_status": "CONFIRMED",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    examples = SCL.build_watchability_training_examples(verification_log_path=fake_log, max_examples=18)
    assert len(examples) >= 10

    tasks = set()
    pred_verdicts = set()
    cmp_verdicts = set()
    hyp_statuses = set()
    for ex in examples:
        instr = ex["instruction"]
        out = json.loads(ex["output"])
        if "CHANGE_PROPOSAL:" in instr:
            tasks.add("predict_change_effect")
            pred_verdicts.add(out["expected_verdict"])
        elif "WATCHABILITY_DIFF:" in instr:
            tasks.add("watchability_compare")
            cmp_verdicts.add(out["verdict"])
            hyp_statuses.add(out["hypothesis_status"])

    assert tasks == {"predict_change_effect", "watchability_compare"}
    assert pred_verdicts == {"BETTER", "WORSE", "NO_CHANGE", "MIXED"}
    assert cmp_verdicts == {"BETTER", "WORSE", "NO_CHANGE", "MIXED"}
    assert hyp_statuses == {"CONFIRMED", "PARTIAL", "NO_EFFECT", "REFUTED"}


def test_pre_conversation_value_history_and_counterfactual_examples():
    hist = SCL.extract_pre_conversation_value_history()
    sources = {h["source_artifact"] for h in hist}
    assert "GOLDEN_BASELINE_PARAMS.json" in sources
    assert "engine_rules.json:edit_limits" in sources
    assert "learning_directive.json:monthly_2026" in sources
    assert "hardware_accel.py + instagram_publisher.py" in sources
    # Zabezpieczenie przed szumem testowym w user_feedback_history.json
    assert all("OLD TITLE" not in h["parameter_change"] and "api_test" not in h["parameter_change"] for h in hist)

    exs = SCL.build_historical_evolution_training_examples(max_examples=14)
    assert len(exs) == 14
    ce_cnt, cf_worse_cnt = 0, 0
    for ex in exs:
        out = json.loads(ex["output"])
        if "CAUSE_EFFECT_EVIDENCE:" in ex["instruction"]:
            ce_cnt += 1
            assert out["verdict"] == "IMPROVED"
        elif "CHANGE_PROPOSAL:" in ex["instruction"]:
            assert out["expected_verdict"] == "WORSE"
            cf_worse_cnt += 1
    assert ce_cnt >= 6
    assert cf_worse_cnt >= 4


def test_predict_historical_regressions_and_anti_sycophancy_guard(monkeypatch):
    import lol_agent.synapsa_engine as SE

    before_metrics = {
        "filename": "good.mp4",
        "watchability_score": 96.0,
        "frame0_hook_legible": True,
        "kill_overlay_zone": "upper_safe",
        "center_blocked_kills_ratio": 0.0,
        "audio_clip_gt_096": 0,
        "av_delta_s": 0.02,
        "camera_peak_step_px": 380.0,
        "player_edge_clip_ratio": 0.0,
        "hook_is_generic": False,
        "black_end_frame": False,
    }
    monkeypatch.setattr(SE, "is_synapsa_available", lambda: True)
    # Sykofancka odpowiedź 7B LoRA próbująca przełączyć werdykt na BETTER z krótkim "Test"
    monkeypatch.setattr(
        SE,
        "generate_with_synapsa",
        lambda task, pload, timeout=120: {
            "expected_verdict": "BETTER",
            "risks": ["Test"],
            "deduction_rationale": "Test",
        },
    )
    hyp = SWJ.predict_change_effect(
        before_metrics,
        {
            "smooth_win": 13,
            "max_pan_px": 25.0,
            "end_freeze_sec": 1.5,
            "min_sample_for_bucket": 2,
            "nvenc_unbounded_cq18": True,
            "video_bitrate_mbps": 29.24,
        },
        use_local_ai=True,
    )
    assert hyp["expected_verdict"] == "WORSE"
    assert hyp["source"] == "synapsa_causal_predictor"
    assert len(hyp["risks"]) >= 4
    assert "Test" not in hyp["risks"]
    assert hyp["deduction_rationale"] != "Test"
