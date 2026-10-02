"""
Unit tests for lol_agent/lol_frag_detector.py.
Verifies HP measurement, vignette detection, FragAnalysisResult invariants,
and optimal clip window computations (including the Solo Bolo zero-cut guarantee).
"""
import numpy as np
import pytest

from lol_agent.lol_frag_detector import (
    FragAnalysisResult,
    _measure_player_hp,
    _detect_critical_low_hp_vignette,
    find_solo_bolo_window,
    compute_optimal_clip_window,
    HP_BAR_ROI,
)


def test_frag_analysis_result_structure():
    res = FragAnalysisResult(
        video_path="test.mp4",
        duration=30.0,
        detected_frag_type="pentakill",
        confidence=0.95,
        kill_count=5,
        kills=[{"timestamp": 12.0, "label": "PENTAKILL", "type": "pentakill"}],
        min_hp_percentage=15.0,
        is_clutch_1hp=True,
        badge_label="PENTAKILL",
        suggested_title_hook="PENTAKILL - DID ENEMY FF?",
        suggested_badge_color="#FFD700",
    )
    assert res.detected_frag_type == "pentakill"
    assert res.kill_count == 5
    assert res.is_clutch_1hp is True
    assert res.combat_segments is None
    assert res.has_jump_cut is False


def test_measure_player_hp_blank_frame():
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    hp = _measure_player_hp(blank)
    assert hp == 0.0


def test_measure_player_hp_synthetic_green_bar():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    ys = int(1080 * HP_BAR_ROI[0])
    ye = int(1080 * HP_BAR_ROI[1])
    xs = int(1920 * HP_BAR_ROI[2])
    xe = int(1920 * HP_BAR_ROI[3])

    # Paint half of the HP bar with typical LoL green (BGR ~ (50, 200, 50))
    bar_width = xe - xs
    half_w = bar_width // 2
    frame[ys:ye, xs:xs + half_w] = (50, 200, 50)

    hp = _measure_player_hp(frame)
    assert hp is not None
    assert 40.0 <= hp <= 60.0


def test_detect_critical_low_hp_vignette_blank_frame():
    blank = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert _detect_critical_low_hp_vignette(blank) is False


def test_detect_critical_low_hp_vignette_red_flash():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # Paint top border with intense red (BGR ~ (0, 0, 220))
    frame[10:100, 400:1500] = (20, 20, 230)
    assert _detect_critical_low_hp_vignette(frame) is True


def test_find_solo_bolo_window_early_kill():
    """Solo Bolo kill in first 5.5s must start at 0.0s with no cut."""
    start_t, end_t, peak_m = find_solo_bolo_window(
        video_path="", kill_t=4.0, total_dur=25.0
    )
    assert start_t == 0.0
    assert end_t <= 15.0
    assert peak_m == 4.0


def test_compute_optimal_clip_window_solo_bolo_zero_cuts():
    """Rule 6: Solo Bolo = zero jump cuts."""
    res = FragAnalysisResult(
        video_path="",
        duration=30.0,
        detected_frag_type="solo_bolo",
        confidence=0.90,
        kill_count=1,
        kills=[{"timestamp": 4.5, "label": "SOLO BOLO", "type": "solo_bolo", "tier": 1}],
        min_hp_percentage=50.0,
        is_clutch_1hp=False,
        badge_label="SOLO BOLO",
        suggested_title_hook="CLEAN SOLO BOLO 1v1",
        suggested_badge_color="#00FFAA",
    )
    start_t, end_t, peak_m, segs = compute_optimal_clip_window(res, total_dur=30.0, action_type="solo_bolo")
    assert segs is None
    assert start_t == 0.0
    assert end_t <= 15.0
    assert peak_m == 4.5


def test_compute_optimal_clip_window_fallback_when_no_kills():
    """When no OCR kills detected, returns valid fallback window."""
    res = FragAnalysisResult(
        video_path="",
        duration=25.0,
        detected_frag_type="outplay",
        confidence=0.50,
        kill_count=0,
        kills=[],
        min_hp_percentage=100.0,
        is_clutch_1hp=False,
        badge_label="OUTPLAY",
        suggested_title_hook="HOW IS THIS POSSIBLE?",
        suggested_badge_color="#FFFFFF",
    )
    start_t, end_t, peak_m, segs = compute_optimal_clip_window(res, total_dur=25.0, action_type="outplay")
    assert start_t >= 0.0
    assert end_t > start_t
    assert end_t <= 25.0
    assert peak_m > 0.0
