"""
tests/test_quality_validator.py
===============================
Unit tests for lol_quality_validator.py checking pre-flight validation logic and rejection guards.
"""

import pytest
import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lol_agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lol_quality_validator import (
    ValidationResult,
    validate_pre_flight,
    _check_enemy_combat_in_frame,
)


class TestQualityValidator:
    def test_validation_result_defaults(self):
        """ValidationResult dataclass should initialize with sensible defaults."""
        res = ValidationResult(
            passed=True,
            adjusted_trim_start=10.0,
            adjusted_trim_end=25.0,
        )
        assert res.passed is True
        assert res.adjusted_trim_start == 10.0
        assert res.adjusted_trim_end == 25.0
        assert res.qa_status == "PASS"
        assert res.qa_score == 95
        assert res.rejection_code is None

    def test_missing_video_fails_validation_gracefully(self):
        """Non-existent video file should be rejected cleanly without unhandled exceptions."""
        result = validate_pre_flight(
            video_path="non_existent_clip_12345.mp4",
            trim_start=0.0,
            trim_end=15.0,
            peaks=[(5.0, "kill")],
        )
        assert result.passed is False
        assert result.rejection_code == "FILE_ERROR"

    def test_blank_frame_has_no_combat_detected(self):
        """Blank frame should detect zero enemy combat pixels."""
        blank_bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
        is_combat, enemy_pixels, centroid = _check_enemy_combat_in_frame(blank_bgr)
        assert enemy_pixels == 0
