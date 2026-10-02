"""
tests/test_thumbnail.py
========================
Unit tests for lol_agent/lol_thumbnail.py.
Verifies typography, hero-frame selection, saturation crop centering,
vignette grading, and end-to-end thumbnail rendering.
"""
import os
import cv2
import numpy as np
import pytest
from PIL import Image

from lol_agent.lol_thumbnail import (
    _sanitize,
    _font,
    _find_best_crop_x,
    _apply_cinematic_grade,
    _add_vignette,
    generate_thumbnail,
    THUMB_W,
    THUMB_H,
)


def test_sanitize_cleans_text():
    raw = "  \n  PENTAKILL   OUTPLAY !!!  \t "
    clean = _sanitize(raw)
    assert clean == "PENTAKILL OUTPLAY !!!"


def test_font_returns_valid_imagefont():
    f = _font(48)
    assert f is not None


def test_find_best_crop_x_centers_on_high_saturation():
    """Synthetic frame with colorful saturated fight blob at x=1300 must attract crop center."""
    h, w = 1080, 1920
    frame = np.ones((h, w, 3), dtype=np.uint8) * 80  # dull background
    # Colorful fight action cluster around x=1300, y=500
    frame[450:550, 1250:1350, 0] = 255  # bright red / gold
    frame[450:550, 1250:1350, 1] = 200
    frame[450:550, 1250:1350, 2] = 20

    crop_w_px = int(h * 0.82 * 9 / 16)
    best_x = _find_best_crop_x(frame, crop_w_px=crop_w_px, source_w=w)
    # The action cluster is at 1300, so best_x should position crop around it
    center_of_crop = best_x + crop_w_px // 2
    assert 1100 <= center_of_crop <= 1450


def test_apply_cinematic_grade_penta():
    img = Image.new("RGB", (200, 300), color=(100, 100, 100))
    graded = _apply_cinematic_grade(img, "PENTAKILL")
    assert graded.size == (200, 300)
    assert graded.mode == "RGB"


def test_add_vignette():
    img = Image.new("RGBA", (200, 300), color=(150, 150, 150, 255))
    vignetted = _add_vignette(img)
    assert vignetted.size == (200, 300)
    assert vignetted.mode == "RGBA"


@pytest.fixture
def synthetic_video(tmp_path):
    """Creates a short 2-second 1920x1080 synthetic mp4 file for thumbnail testing."""
    video_path = tmp_path / "test_clip.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 30.0, (1920, 1080))
    for i in range(60):
        frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 90
        # Draw some gold / colored action
        cv2.circle(frame, (960, 540), 60 + i, (30, 215, 255), -1)
        out.write(frame)
    out.release()
    return str(video_path)


def test_generate_thumbnail_creates_valid_pro_image(synthetic_video, tmp_path):
    """Full end-to-end thumbnail generation test."""
    thumb_out = str(tmp_path / "outplay_thumb.jpg")
    result = generate_thumbnail(
        video_path=synthetic_video,
        peak_moment=1.0,
        action_label="SOLO BOLO",
        champion_name="Katarina",
        output_path=thumb_out,
    )
    assert result == thumb_out
    assert os.path.exists(thumb_out)

    with Image.open(thumb_out) as thumb:
        assert thumb.size == (THUMB_W, THUMB_H)
        assert thumb.format == "JPEG"
