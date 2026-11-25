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


def test_generate_thumbnail_variants_produce_distinct_images(tmp_path):
    """Successive variant_index values (0..3) must produce genuinely distinct thumbnails."""
    import hashlib

    video_path = tmp_path / "varied_clip.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 15.0, (1920, 1080))
    # 6s video with visibly distinct colors and action positions across segments
    palettes = [
        ((30, 50, 210), (320, 420)),
        ((200, 190, 40), (700, 520)),
        ((50, 210, 80), (1180, 450)),
        ((215, 70, 190), (1500, 560)),
    ]
    for f_idx in range(90):
        seg = min(3, f_idx // 23)
        bg_bgr, center = palettes[seg]
        frame = np.full((1080, 1920, 3), bg_bgr, dtype=np.uint8)
        cv2.circle(frame, center, 180, (25, 220, 255), -1)
        cv2.rectangle(frame, (center[0] - 90, center[1] - 220), (center[0] + 90, center[1] - 190), (20, 210, 240), -1)
        out.write(frame)
    out.release()

    hashes = []
    arrays = []
    for v_idx in range(4):
        out_jpg = str(tmp_path / f"thumb_v{v_idx}.jpg")
        res = generate_thumbnail(
            video_path=str(video_path),
            peak_moment=2.5,
            action_label="TRIPLE KILL",
            champion_name="Katarina",
            output_path=out_jpg,
            variant_index=v_idx,
        )
        assert res == out_jpg and os.path.isfile(out_jpg)
        hashes.append(hashlib.sha256(open(out_jpg, "rb").read()).hexdigest())
        with Image.open(out_jpg) as img:
            assert img.size == (THUMB_W, THUMB_H)
            arrays.append(np.asarray(img.convert("RGB"), dtype=np.float32))

    assert len(set(hashes)) == 4
    for i in range(len(arrays)):
        for j in range(i + 1, len(arrays)):
            mean_diff = float(np.mean(np.abs(arrays[i] - arrays[j])))
            assert mean_diff > 5.0
