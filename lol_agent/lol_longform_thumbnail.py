"""
Flikcut / Shortsyt — Generator Miniaturek Long-Form 16:9 (`Etap 31.3`)
======================================================================
Generuje miniatury `1280x720` pod CTR 4-8% z klatki kulminacji `#1`:
  - usunięcie paska HUD i minimapy,
  - kadrowanie 16:9, podbicie kontrastu/nasycenia + kinowa winieta i glow,
  - czytelna typografia Impact (max 3 słowa narracyjne + subline badge),
  - gwarantowany rozmiar pliku JPEG `< 2 MB` (limit YouTube Data API).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

LONGFORM_W = 1280
LONGFORM_H = 720
MAX_THUMB_BYTES = 2_000_000

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\Impact.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _ascii_clean(text: str) -> str:
    cleaned = re.sub(r"[^\x20-\x7E]", "", str(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_action_frame_no_hud(video_path: str, peak_time_s: float) -> Image.Image:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Nie można otworzyć pliku wideo: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        total_f = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1.0
        dur = total_f / fps
        target_t = min(max(0.2, float(peak_time_s)), max(0.2, dur - 0.3))
        cap.set(cv2.CAP_PROP_POS_MSEC, target_t * 1000.0)
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            raise RuntimeError("Nie udało się odczytać klatki z wideo")
    finally:
        cap.release()

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    # Przytnij dolny HUD (14%) oraz prawą minimapę (14%) zachowując proporcję 16:9
    crop_h = max(120, int(h * 0.86))
    crop_w = min(int(w * 0.86), int(round(crop_h * 16.0 / 9.0)))
    crop_h = min(crop_h, int(round(crop_w * 9.0 / 16.0)))
    y0 = max(0, (int(h * 0.86) - crop_h) // 2)
    x0 = max(0, int((w * 0.86 - crop_w) * 0.45))
    cropped = rgb[y0 : y0 + crop_h, x0 : x0 + crop_w]
    return Image.fromarray(cropped).resize((LONGFORM_W, LONGFORM_H), Image.Resampling.LANCZOS)


def generate_longform_thumbnail(
    video_path: str | Path,
    peak_time_s: float = 4.0,
    headline: str = "1V4 RESET",
    subline: str = "KATARINA WEEKLY #1",
    output_path: Optional[str | Path] = None,
) -> str:
    """Tworzy miniaturę 1280x720 JPEG (< 2 MB) bez HUD/minimapy i z maksymalnie 3 słowami tekstu."""
    img = _extract_action_frame_no_hud(str(video_path), peak_time_s)
    img = ImageEnhance.Contrast(img).enhance(1.24)
    img = ImageEnhance.Color(img).enhance(1.30)
    img = ImageEnhance.Sharpness(img).enhance(1.35)

    # Kinowa radialna winieta + lekkie podbicie krawędzi
    yy, xx = np.ogrid[:LONGFORM_H, :LONGFORM_W]
    cx, cy = LONGFORM_W * 0.50, LONGFORM_H * 0.48
    dist = np.sqrt(((xx - cx) / (LONGFORM_W * 0.56)) ** 2 + ((yy - cy) / (LONGFORM_H * 0.58)) ** 2)
    vig = np.clip(1.08 - 0.55 * (dist ** 1.7), 0.38, 1.0)
    arr = (np.asarray(img, dtype=np.float32) * vig[..., None]).clip(0, 255).astype(np.uint8)
    base = Image.fromarray(arr).convert("RGBA")

    # Ciemny dolny gradient pod napisy
    grad = Image.new("RGBA", (LONGFORM_W, LONGFORM_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(int(LONGFORM_H * 0.52), LONGFORM_H):
        alpha = int(205 * ((y - LONGFORM_H * 0.52) / (LONGFORM_H * 0.48)))
        gd.line([(0, y), (LONGFORM_W, y)], fill=(6, 8, 14, min(215, alpha)))
    base = Image.alpha_composite(base, grad)

    draw = ImageDraw.Draw(base)

    # Złoty / czerwony badge w lewym górnym rogu
    badge_txt = _ascii_clean(subline).upper()[:28] or "WEEKLY BEST PLAYS"
    badge_font = _load_font(34)
    bx0, by0 = 48, 38
    bw = draw.textlength(badge_txt, font=badge_font) + 42
    draw.rounded_rectangle([(bx0, by0), (bx0 + bw, by0 + 56)], radius=10, fill=(14, 17, 24, 225), outline=(255, 215, 0, 255), width=3)
    draw.text((bx0 + 21, by0 + 10), badge_txt, font=badge_font, fill=(255, 215, 0, 255))

    # Maksymalnie 3 wyraźne słowa w głównym nagłówku
    words = _ascii_clean(headline).upper().split()[:3]
    clean_head = " ".join(words) or "UNSTOPPABLE"
    font_sz = 126
    head_font = _load_font(font_sz)
    while draw.textlength(clean_head, font=head_font) > (LONGFORM_W - 110) and font_sz > 68:
        font_sz -= 6
        head_font = _load_font(font_sz)

    hx = 54
    hy = LONGFORM_H - font_sz - 58
    # Poświata pod napisem + gruby obrys 3D
    glow = Image.new("RGBA", (LONGFORM_W, LONGFORM_H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((hx, hy), clean_head, font=head_font, fill=(255, 195, 0, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12))
    base = Image.alpha_composite(base, glow)
    draw = ImageDraw.Draw(base)

    draw.text((hx + 7, hy + 8), clean_head, font=head_font, fill=(0, 0, 0, 235))
    draw.text((hx, hy), clean_head, font=head_font, fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))

    out = Path(output_path) if output_path else Path(video_path).with_name(Path(video_path).stem + "_thumb_1280x720.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)

    rgb_final = base.convert("RGB")
    for q in (92, 86, 78, 70):
        rgb_final.save(str(out), format="JPEG", quality=q, optimize=True)
        if out.stat().st_size <= MAX_THUMB_BYTES:
            break
    return str(out)
