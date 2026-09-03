"""
tests/test_smart_camera.py
==========================
Unit tests for Computer Vision tracking and FFmpeg pan expression generation in Smart Camera.
Tests run purely on synthetic numpy data without requiring video files or GPU.
"""

import numpy as np
import pytest
import sys
import os

# Allow importing from lol_agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lol_agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smart_camera import (
    generate_ffmpeg_pan_expression,
    compute_motion_map,
    _detect_fight_center_x,
)


class TestGenerateFfmpegPanExpression:
    def test_empty_points_returns_center_fallback(self):
        """Empty path should return default center crop for 1920x1080 (656px)."""
        expr = generate_ffmpeg_pan_expression([])
        assert expr == "656"

    def test_single_point_returns_static_x(self):
        """Single coordinate point should return constant pixel value."""
        expr = generate_ffmpeg_pan_expression([(0.0, 720)])
        assert expr == "720"

    def test_two_points_generates_linear_interpolation(self):
        """Two points should generate an if(lt(t, ...)) linear interpolation expression."""
        expr = generate_ffmpeg_pan_expression([(0.0, 400), (2.0, 600)])
        assert "if(lt(t,2.00)" in expr
        assert "400" in expr
        assert "600" in expr

    def test_multi_segment_expression_validity(self):
        """Multiple waypoints should generate nested conditionals covering all intervals."""
        points = [(0.0, 300), (1.5, 450), (3.0, 600)]
        expr = generate_ffmpeg_pan_expression(points)
        assert "if(lt(t,1.50)" in expr
        assert "if(lt(t,3.00)" in expr


class TestComputeMotionMap:
    def test_single_frame_returns_uniform_map(self):
        """Single frame should return uniform 2D array matching frame dimensions."""
        frame = np.zeros((100, 200, 3), dtype=np.float32)
        mmap = compute_motion_map([frame])
        assert mmap.shape == (100, 200)

    def test_static_frames_have_zero_motion(self):
        """Identical consecutive frames should produce zero motion diff."""
        frame1 = np.ones((50, 50, 3), dtype=np.float32) * 128
        frame2 = np.ones((50, 50, 3), dtype=np.float32) * 128
        mmap = compute_motion_map([frame1, frame2])
        assert np.all(mmap == 0)

    def test_motion_difference_is_detected(self):
        """Modified regions between frames must produce non-zero values."""
        frame1 = np.zeros((60, 60, 3), dtype=np.float32)
        frame2 = np.zeros((60, 60, 3), dtype=np.float32)
        frame2[20:30, 20:30, :] = 255.0  # Motion blob
        mmap = compute_motion_map([frame1, frame2])
        assert mmap[25, 25] > 0
        assert mmap[0, 0] == 0


class TestDetectFightCenterX:
    def test_blank_frame_returns_none(self):
        """Completely blank frame with no HP bars should return None for player and fight center."""
        blank = np.zeros((216, 384, 3), dtype=np.uint8)
        yellow_x, fight_x, count = _detect_fight_center_x(blank, hud_y_cutoff=180, top_cutoff=30)
        assert yellow_x is None
        assert count == 0

    def test_synthetic_yellow_hp_bar_detected(self):
        """Synthetic player HP bar (gold/yellow, aspect ratio >= 2.0) should be detected."""
        frame = np.zeros((216, 384, 3), dtype=np.uint8)
        # LoL player HP bar color: R>160, G>130, B<110, (r-b)>80, (g-b)>50
        # Aspect >= 2.0, cw >= 5, ch <= 5, area >= 5
        # Place at y=80..82 (ch=3), x=180..195 (cw=16), inside valid mask area
        frame[80:83, 180:196, 0] = 220  # R
        frame[80:83, 180:196, 1] = 180  # G
        frame[80:83, 180:196, 2] = 20   # B

        yellow_x, fight_x, count = _detect_fight_center_x(frame, hud_y_cutoff=180, top_cutoff=30)
        assert yellow_x is not None
        assert 175 <= yellow_x <= 200

    def test_ui_exclusion_mask_ignores_minimap_area(self):
        """HP bar pixels placed inside the minimap region (bottom-right) must be excluded."""
        frame = np.zeros((216, 384, 3), dtype=np.uint8)
        # Bottom-right corner (y > 0.62*h, x > 0.76*w) -> y > 134, x > 291
        frame[160:163, 320:336, 0] = 220
        frame[160:163, 320:336, 1] = 180
        frame[160:163, 320:336, 2] = 20

        yellow_x, fight_x, count = _detect_fight_center_x(frame, hud_y_cutoff=180, top_cutoff=30)
        assert yellow_x is None
