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
    filter_temporal_vfx_particles,
    is_tab_overlay_active,
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


class TestPlayerTrajectoryTracking:
    """
    Task A3: Multi-champion camera validation for dash-heavy champions (Zed, Akali, LeBlanc, Katarina).
    Tests kinematic tracking properties: SNAP_DELTA, DEADBAND, LERP, and Teleport guards.
    """

    def _make_hp_bar(self, cen_x: float, cen_y: float = 540.0, score: float = 500.0):
        # Format: (cx, cy, cw, ch, score, cen_x, cen_y)
        return [(int(cen_x - 30), int(cen_y - 10), 60, 20, score, float(cen_x), float(cen_y))]

    def test_tracking_empty_frames_returns_center_fallback(self):
        from lol_agent.smart_camera import simulate_player_trajectory
        pts = simulate_player_trajectory([], duration=10.0, source_w=1920, crop_w=608)
        assert len(pts) == 2
        default_x = (1920 - 608) // 2
        assert pts[0][1] == default_x
        assert pts[1][1] == default_x

    def test_tracking_zed_shadow_swap_instant_snap(self):
        """
        Zed W shadow swap: position instantaneously shifts by ~260px (> SNAP_DELTA 220px).
        The camera must immediately snap without sluggish multi-frame lag.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        # First 10 frames: Zed at x=800
        for _ in range(10):
            frames.append(self._make_hp_bar(cen_x=800.0))
        # Zed casts W2 to shadow at x=1060 (delta = 260px > SNAP_DELTA=220)
        for _ in range(10):
            frames.append(self._make_hp_bar(cen_x=1060.0))

        pts = simulate_player_trajectory(frames, duration=10.0, source_w=1920, crop_w=608)
        assert len(pts) == 20

        # Before swap: camera centers around 800 - 304 = 496
        x_before = pts[9][1]
        assert 480 <= x_before <= 510

        # At swap (frame 10): camera snapped to ~1060 - 304 = 756
        x_after = pts[10][1]
        assert 740 <= x_after <= 770

        # Difference must reflect the snap
        assert abs(x_after - x_before) > 200

    def test_tracking_leblanc_distortion_and_snapback(self):
        """
        LeBlanc W distortion dash forward and return snapback.
        Both transitions (> SNAP_DELTA) must snap cleanly.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        # Stationary at 960 (center)
        for _ in range(8):
            frames.append(self._make_hp_bar(cen_x=960.0))
        # W forward to 1240 (delta = 280 > SNAP_DELTA)
        for _ in range(8):
            frames.append(self._make_hp_bar(cen_x=1240.0))
        # W snapback to 960 (delta = 280 > SNAP_DELTA)
        for _ in range(8):
            frames.append(self._make_hp_bar(cen_x=960.0))

        pts = simulate_player_trajectory(frames, duration=12.0, source_w=1920, crop_w=608)
        assert len(pts) == 24

        # Verify initial position
        assert 640 <= pts[7][1] <= 670
        # Verify forward snap
        assert pts[8][1] >= 900
        # Verify return snapback
        assert 640 <= pts[16][1] <= 670

    def test_tracking_akali_shroud_invisibility_streak(self):
        """
        Akali enters Twilight Shroud: HP bar is missing for 2 frames.
        Camera must preserve momentum decay and freeze, NOT drift onto faraway objects or center.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        # Walking right at ~40px per frame
        pos = 700.0
        for _ in range(10):
            frames.append(self._make_hp_bar(cen_x=pos))
            pos += 40.0
        last_known_pos = pos - 40.0

        # Invisible in shroud for 2 frames
        frames.append([])
        frames.append([])

        # Re-appears near shroud exit
        frames.append(self._make_hp_bar(cen_x=last_known_pos + 60.0))

        pts = simulate_player_trajectory(frames, duration=6.5, source_w=1920, crop_w=608)
        assert len(pts) == 13
        # Invisibility frames should stay smoothly near last known position
        assert abs(pts[10][1] - pts[9][1]) < 80
        assert abs(pts[11][1] - pts[10][1]) < 80

    def test_tracking_deadband_micro_jitter_suppressed(self):
        """
        Micro-movements < DEADBAND_PX (30px) must be suppressed so camera does not jitter.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        base_x = 900.0
        # Jitter +/- 10px
        for i in range(15):
            jitter = 10.0 if (i % 2 == 0) else -10.0
            frames.append(self._make_hp_bar(cen_x=base_x + jitter))

        pts = simulate_player_trajectory(frames, duration=7.5, source_w=1920, crop_w=608)
        crops = [p[1] for p in pts]
        # Camera crop variation should be minimal (< 10px across entire sequence)
        max_diff = max(crops) - min(crops)
        assert max_diff <= 10

    def test_tracking_teleport_cutoff_protects_against_hud_leak(self):
        """
        Anomalous jump > MAX_TELEPORT_DELTA (480px) represents a false positive (HUD leak / tower)
        and must be rejected rather than causing a disorienting camera warp.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        for _ in range(8):
            frames.append(self._make_hp_bar(cen_x=700.0))
        # Single frame glitch on right edge of screen (x=1600, delta = 900px > 480px)
        frames.append(self._make_hp_bar(cen_x=1600.0))
        # Player resumes at x=720.0
        for _ in range(8):
            frames.append(self._make_hp_bar(cen_x=720.0))

        pts = simulate_player_trajectory(frames, duration=8.5, source_w=1920, crop_w=608)
        # Glitch frame crop must NOT warp to right edge
        glitch_crop = pts[8][1]
        assert glitch_crop < 600  # Stays close to ~700 - 304 = 396

    def test_tracking_outro_end_freeze(self):
        """
        Last 0.6s of clip must have stationary camera crop (outro freeze requirement).
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        pos = 600.0
        for _ in range(20):
            frames.append(self._make_hp_bar(cen_x=pos))
            pos += 30.0

        # Duration 10s -> last 0.6s is 6% of frames (last ~2 frames frozen)
        pts = simulate_player_trajectory(frames, duration=10.0, source_w=1920, crop_w=608)
        last_crop = pts[-1][1]
        second_last_crop = pts[-2][1]
        assert last_crop == second_last_crop


class TestDeathLotusVfxFilter:
    """
    Task A4: Temporal Consistency Filter tests for Death Lotus and transient VFX particles.
    """

    def _hp(self, cen_x: float, cen_y: float = 540.0, score: float = 500.0):
        return (int(cen_x - 30), int(cen_y - 10), 60, 20, score, float(cen_x), float(cen_y))

    def test_transient_particle_pruned_when_true_hp_persists(self):
        """
        Death Lotus particle appears on frame 5 at x=980 with high score, but disappears on frame 6.
        True Katarina HP bar is at x=800 across frames 4, 5, 6.
        The filter must discard the transient particle from frame 5.
        """
        frames_data = [
            [self._hp(cen_x=800.0, cen_y=540.0)],
            [self._hp(cen_x=802.0, cen_y=540.0)],
            [self._hp(cen_x=801.0, cen_y=541.0)],
            [self._hp(cen_x=799.0, cen_y=539.0)],
            [self._hp(cen_x=800.0, cen_y=540.0)],  # frame 4
            [
                self._hp(cen_x=800.0, cen_y=540.0, score=400.0),  # Katarina
                self._hp(cen_x=980.0, cen_y=410.0, score=900.0),  # Death Lotus particle spike
            ],  # frame 5
            [self._hp(cen_x=801.0, cen_y=540.0)],  # frame 6
            [self._hp(cen_x=803.0, cen_y=542.0)],
            [self._hp(cen_x=802.0, cen_y=541.0)],
        ]
        filtered = filter_temporal_vfx_particles(frames_data, max_drift=140.0, window=2)

        # Frame 5 must now contain only Katarina
        assert len(filtered[5]) == 1
        assert filtered[5][0][5] == 800.0

    def test_dash_landing_preserved_via_forward_temporal_support(self):
        """
        Katarina casts Shunpo at frame 3 from x=700 to x=950.
        She remains at x=952 in frame 4 and x=955 in frame 5.
        Even with multiple candidates in frame 3, her landing position must be preserved.
        """
        frames_data = [
            [self._hp(cen_x=700.0)],
            [self._hp(cen_x=702.0)],
            [self._hp(cen_x=705.0)],  # frame 2
            [
                self._hp(cen_x=650.0),  # Enemy minion / ally
                self._hp(cen_x=950.0),  # Katarina Shunpo landing
            ],  # frame 3
            [self._hp(cen_x=952.0)],  # frame 4
            [self._hp(cen_x=955.0)],  # frame 5
        ]
        filtered = filter_temporal_vfx_particles(frames_data, max_drift=140.0, window=2)
        # Both minion (supported by frame 2) and Katarina (supported by frame 4) preserved
        assert len(filtered[3]) == 2
        xs = [c[5] for c in filtered[3]]
        assert 950.0 in xs

    def test_single_candidate_frames_always_retained(self):
        """Frames with single candidate must never be pruned by the filter."""
        frames_data = [
            [self._hp(cen_x=500.0)],
            [self._hp(cen_x=510.0)],
            [self._hp(cen_x=520.0)],
        ]
        filtered = filter_temporal_vfx_particles(frames_data)
        assert len(filtered) == 3
        for f in filtered:
            assert len(f) == 1

    def test_simulate_trajectory_ignores_death_lotus_spike(self):
        """
        End-to-end: simulate_player_trajectory with a Death Lotus spike on frame 5
        must produce smooth panning without any snap to x=980.
        """
        from lol_agent.smart_camera import simulate_player_trajectory
        frames = []
        for _ in range(5):
            frames.append([self._hp(cen_x=800.0, cen_y=540.0)])
        # Frame 5: Death Lotus particle with higher score
        frames.append([
            self._hp(cen_x=800.0, cen_y=540.0, score=300.0),
            self._hp(cen_x=980.0, cen_y=410.0, score=999.0),
        ])
        for _ in range(5):
            frames.append([self._hp(cen_x=800.0, cen_y=540.0)])

        pts = simulate_player_trajectory(frames, duration=5.0, source_w=1920, crop_w=608)
        # Center crop around 800px is: 800 - 304 = 496. All points must stay near 496!
        crops = [p[1] for p in pts]
        assert all(480 <= c <= 515 for c in crops)


class TestTabOverlayScoreboard:
    """
    Task A5: Tab / Scoreboard overlay detection and exclusion mask tests.
    """

    def test_is_tab_overlay_active_detects_dark_scoreboard_panel(self):
        """Frame with dark scoreboard panel in top-center region must return True."""
        # 1080p frame
        frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 120  # bright gameplay terrain
        # Fill Tab scoreboard region (y: 100-360, x: 460-1460) with dark slate (RGB: 30, 35, 40)
        frame[100:360, 460:1460] = np.array([30, 35, 40], dtype=np.uint8)

        active = is_tab_overlay_active(frame, sw=1.0, sh=1.0)
        assert active is True

    def test_is_tab_overlay_active_returns_false_for_normal_gameplay(self):
        """Normal gameplay frame with grass/river colors must return False."""
        frame = np.ones((1080, 1920, 3), dtype=np.uint8)
        frame[:, :, 0] = 90   # R
        frame[:, :, 1] = 130  # G (green Summoner Rift terrain)
        frame[:, :, 2] = 85   # B

        active = is_tab_overlay_active(frame, sw=1.0, sh=1.0)
        assert active is False

