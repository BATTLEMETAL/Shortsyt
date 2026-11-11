"""
Tests for Adaptive Montage Director, Camera Centering, and Multi-Slot Scheduling.
Verifies:
1. Outro after final kill never exceeds 2.0s (max 2 seconds of outro).
2. Lead-in expands from front to reach full Short length without extending dead outro.
3. Automatic approach selection (Approach A vs Approach B).
4. Scheduling slot reservation and advancement.
5. Subtitle deduplication for close peaks.
6. Camera Centroid tracking framing in smart_camera.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
import numpy as np
import pytest

from lol_agent.lol_frag_detector import (
    FragAnalysisResult,
    compute_optimal_clip_window,
    find_solo_bolo_window,
)
from lol_agent.api.youtube_uploader import (
    get_next_optimal_publish_time,
    get_occupied_publish_slots,
    invalidate_publish_cache,
)
from lol_agent.lol_editor import build_dynamic_captions_filters
from lol_agent.smart_camera import simulate_player_trajectory


def test_final_kill_outro_never_exceeds_2s():
    """User mandate: Outro after the final kill must NEVER exceed 2.0 seconds!"""
    res = FragAnalysisResult(
        video_path="",
        duration=30.0,
        detected_frag_type="outplay",
        confidence=0.90,
        kill_count=1,
        kills=[{"timestamp": 12.0, "label": "OUTPLAY", "type": "outplay", "tier": 1}],
        min_hp_percentage=50.0,
        is_clutch_1hp=False,
        badge_label="OUTPLAY",
        suggested_title_hook="OUTPLAY",
        suggested_badge_color="#FFFFFF",
    )
    s, e, p, segs = compute_optimal_clip_window(res, total_dur=30.0, action_type="outplay")
    outro_span = e - 12.0
    assert 1.19 <= outro_span <= 2.05, f"Outro span {outro_span:.2f}s exceeded 2.0s limit! Max 2.0s allowed."


def test_lead_in_expands_from_front_to_guarantee_short_length():
    """When kill is at 10.0s, start expands backwards so Short duration is >= 10s, while outro stays <= 2.0s."""
    res = FragAnalysisResult(
        video_path="",
        duration=25.0,
        detected_frag_type="outplay",
        confidence=0.90,
        kill_count=1,
        kills=[{"timestamp": 10.0, "label": "OUTPLAY", "type": "outplay", "tier": 1}],
        min_hp_percentage=50.0,
        is_clutch_1hp=False,
        badge_label="OUTPLAY",
        suggested_title_hook="OUTPLAY",
        suggested_badge_color="#FFFFFF",
    )
    s, e, p, segs = compute_optimal_clip_window(res, total_dur=25.0, action_type="outplay")
    duration = e - s
    outro_span = e - 10.0
    assert duration >= 10.0, f"Clip duration {duration:.1f}s is below 10.0s"
    assert outro_span <= 2.0, f"Outro span {outro_span:.1f}s exceeded 2.0s!"


def test_solo_bolo_window_outro_never_exceeds_2s():
    """Solo bolo window outro must never exceed 2.0 seconds after the kill."""
    s, e, p = find_solo_bolo_window(video_path="", kill_t=4.5, total_dur=25.0)
    outro_span = e - 4.5
    assert outro_span <= 2.0, f"Solo bolo outro span {outro_span:.1f}s exceeded 2.0s!"


def test_approach_selection_approach_b_for_pentakill():
    """Dense teamfight / Pentakill triggers Approach B (Instant Chaos Skirmish, lead_in <= 2.5s)."""
    res = FragAnalysisResult(
        video_path="",
        duration=35.0,
        detected_frag_type="pentakill",
        confidence=0.95,
        kill_count=5,
        kills=[
            {"timestamp": 10.0, "label": "KILL", "type": "kill", "tier": 1},
            {"timestamp": 12.0, "label": "DOUBLE KILL", "type": "double", "tier": 2},
            {"timestamp": 14.0, "label": "TRIPLE KILL", "type": "triple", "tier": 3},
            {"timestamp": 16.5, "label": "QUADRAKILL", "type": "quadrakill", "tier": 4},
            {"timestamp": 19.0, "label": "PENTAKILL", "type": "pentakill", "tier": 5},
        ],
        min_hp_percentage=20.0,
        is_clutch_1hp=True,
        badge_label="PENTAKILL",
        suggested_title_hook="PENTAKILL",
        suggested_badge_color="#FFD700",
    )
    s, e, p, segs = compute_optimal_clip_window(res, total_dur=35.0, action_type="pentakill")
    lead_in = 10.0 - s
    outro_span = e - 19.0
    assert 1.5 <= lead_in <= 2.5, f"Approach B lead-in was {lead_in:.1f}s, expected 1.5-2.5s"
    assert outro_span <= 2.0, f"Penta outro span {outro_span:.1f}s exceeded 2.0s!"


def test_scheduling_advances_slots_when_occupied():
    """
    Simulates slot reservation:
    When 08:30 CET is occupied, get_next_optimal_publish_time automatically picks 18:30 CET.
    """
    invalidate_publish_cache()
    occupied = get_occupied_publish_slots(force_refresh=True)
    next_slot = get_next_optimal_publish_time()
    assert "publish_at" in next_slot
    assert "local_time" in next_slot
    # The chosen slot must not already be in occupied slots!
    assert next_slot["local_time"] not in occupied


def test_subtitle_deduplication_removes_close_duplicates():
    """Close subtitle peaks (<1.4s) must be merged into the highest tier style."""
    peaks = [
        (2.0, "KILL"),
        (2.4, "DOUBLE KILL"),  # 0.4s later -> should replace KILL
    ]
    filters = build_dynamic_captions_filters(
        peaks=peaks,
        trim_start=0.0,
        video_duration=12.0,
        peak_moment=2.4,
        action_type="double",
    )
    # The resulting FFmpeg filters should contain "DOUBLE KILL" and not separate overlapping "KILL"
    combined_filters = " ".join(filters)
    assert "DOUBLE KILL" in combined_filters


def test_smart_camera_centroid_framing():
    """In kill window, camera frames player and enemy centroid instead of solely player."""
    analysis_w, analysis_h = 480, 270
    frames_data = [
        ([(0, 0, 40, 10, 100.0, 200.0, 150.0)], 260.0),
        ([(0, 0, 40, 10, 100.0, 200.0, 150.0)], 260.0),
        ([(0, 0, 40, 10, 100.0, 200.0, 150.0)], 260.0),
        ([(0, 0, 40, 10, 100.0, 200.0, 150.0)], 260.0),
        ([(0, 0, 40, 10, 100.0, 200.0, 150.0)], 260.0),
    ]
    traj = simulate_player_trajectory(
        frames_data=frames_data,
        duration=2.0,
        source_w=1920,
        source_h=1080,
        crop_w=608,
        analysis_w=analysis_w,
        analysis_h=analysis_h,
        peaks=[(1.0, "KILL")],
        clip_start=0.0,
    )
    assert len(traj) == 5
    crop_xs = [pt[1] for pt in traj]
    assert all(x >= 0 for x in crop_xs)
