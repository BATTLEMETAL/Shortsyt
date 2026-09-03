"""
LOL Agent — Thumbnail Generator v3 (Pro Esports / Viral Gaming Edition)
Styl dopasowany do YouTube Shorts & Channel Grid.

Ulepszenia v3:
- Bezpieczny margines Y (y = 190px) — zapobiega ucinaniu tekstu przez interfejs YouTube
- Profesjonalna typografia 3D (3-warstwowy cień, 20px czarny obrys, złoty/neonowy specular highlight)
- Dynamiczne skalowanie czcionki do szerokości tekstu
- Elegancki Sub-Badge championa (zaokrąglony glass pill z kolorowym obrysem)
- Gładki, kinowy vignette (filtr Gaussian Blur zamiast schodkowych prostokątów)
- Niezawodna ekstrakcja klatek przez OpenCV (z automatycznym clampem do długości wideo)
"""
import os
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

THUMB_W = 1080
THUMB_H = 1920
_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)

FONT_CANDIDATES = [
    os.path.join(_HERE, "impact.ttf"),
    os.path.join(_ROOT, "impact.ttf"),
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\Impact.ttf",
]

LOGO_CANDIDATES = [
    os.path.join(_HERE, "logo.png"),
    os.path.join(_ROOT, "logo.png"),
]


def _sanitize(text: str) -> str:
    import re
    text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    text = re.sub(r"[^\x00-\x7F\u00C0-\u024F]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _extract_frame(video_path: str, t: float, out: str) -> bool:
    """Wyciąga klatkę przez OpenCV z automatycznym zabezpieczeniem czasu trwania."""
    if not os.path.exists(video_path):
        return False
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1.0
        duration = total_frames / fps
        target_t = min(max(0.2, t), max(0.2, duration - 0.3))
        cap.set(cv2.CAP_PROP_POS_MSEC, target_t * 1000.0)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None and frame.size > 0:
            cv2.imwrite(out, frame)
            return os.path.exists(out)
    except Exception as e:
        print(f"[THUMB] OpenCV extract error: {e}")
    return False


def _find_best_crop_x(img_rgb: np.ndarray, crop_w_px: int, source_w: int = 1920) -> int:
    """Wyszukuje centrum akcji/walki w klatce."""
    from PIL import Image as PilImage
    img_pil = PilImage.fromarray(img_rgb)
    hsv = np.array(img_pil.convert("HSV"))
    sat = hsv[:, :, 1].astype(float)
    h = sat.shape[0]
    sat[int(h * 0.82):, :] = 0  # wyklucz dolny HUD

    col_sat = sat.sum(axis=0)
    kernel = np.ones(31) / 31
    col_sat = np.convolve(col_sat, kernel, mode="same")
    total = col_sat.sum()
    if total > 0:
        cx = int((col_sat * np.arange(len(col_sat))).sum() / total)
    else:
        cx = source_w // 2

    cx_blended = int(0.70 * cx + 0.30 * (source_w // 2))
    x = cx_blended - crop_w_px // 2
    return max(0, min(x, source_w - crop_w_px))


def _apply_cinematic_grade(img: Image.Image, action: str) -> Image.Image:
    """Cinematic color grade dla dynamicznych barw LoL."""
    img = ImageEnhance.Contrast(img).enhance(1.22)
    img = ImageEnhance.Color(img).enhance(1.30)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    return img


def _add_vignette(img: Image.Image) -> Image.Image:
    """Dodaje gładki, kinowy radialny vignette."""
    w, h = img.size
    vig_mask = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig_mask)
    vd.ellipse([(int(w * 0.08), int(h * 0.06)), (int(w * 0.92), int(h * 0.94))], fill=255)
    vig_mask = vig_mask.filter(ImageFilter.GaussianBlur(190))
    vig_inv = Image.fromarray(255 - np.array(vig_mask))
    black_layer = Image.new("RGBA", (w, h), (0, 0, 0, 150))
    black_layer.putalpha(Image.fromarray((np.array(vig_inv) * 0.70).astype(np.uint8)))
    return Image.alpha_composite(img.convert("RGBA"), black_layer)


def _find_best_hero_frame(video_path: str, center_t: float, search_window: float = 3.0) -> float:
    """
    Skanuje klatki w oknie walki i wybiera najbardziej widowiskowy moment (Hero-Frame):
    - Widoczność gracza w akcji (złoty pasek HP)
    - Wysokie nasycenie efektami czarów / walki (VFX)
    - Wykluczenie czarnych klatek i ekranu Victory/Defeat
    """
    if not os.path.exists(video_path):
        return center_t
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return center_t
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps

        start_t = max(0.5, center_t - search_window / 2)
        end_t = min(max(0.5, dur - 1.0), center_t + search_window / 2)

        if end_t <= start_t:
            cap.release()
            return center_t

        candidates = np.linspace(start_t, end_t, 10)
        best_t = center_t
        best_score = -1.0

        for t in candidates:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ret, fr = cap.read()
            if not ret or fr is None:
                continue

            h, w = fr.shape[:2]
            fr_nohud = fr[:int(h * 0.82), :]
            hsv = cv2.cvtColor(fr_nohud, cv2.COLOR_BGR2HSV)

            r, g, b = fr_nohud[:, :, 2].astype(np.int16), fr_nohud[:, :, 1].astype(np.int16), fr_nohud[:, :, 0].astype(np.int16)
            gold_mask = ((r > 160) & (g > 130) & (b < 115) & ((r - b) > 40) & ((g - b) > 15))
            gold_pts = int(cv2.countNonZero(gold_mask.astype(np.uint8)))

            sat = hsv[:, :, 1]
            high_sat = sat > 140
            vfx_score = float(np.mean(sat[high_sat])) if high_sat.any() else 0.0

            val = hsv[:, :, 2]
            avg_bright = float(np.mean(val))
            if avg_bright < 30 or avg_bright > 240:
                continue

            score = vfx_score + (150.0 if gold_pts >= 10 else 0.0)
            if score > best_score:
                best_score = score
                best_t = float(t)

        cap.release()
        return best_t
    except Exception as e:
        print(f"[THUMB] Hero-frame search error: {e}")
        return center_t


def generate_thumbnail(
    video_path: str,
    peak_moment: float,
    action_label: str,
    champion_name: str = "",
    output_path: str = None,
    source_clip_path: str = None,
    source_peak_moment: float = None,
) -> Optional[str]:
    """
    Generuje profesjonalną miniaturkę 1080x1920 z czytelną typografią i bezpiecznym marginesem.
    """
    if output_path is None:
        output_path = os.path.join(os.path.dirname(video_path), "thumbnail.jpg")

    action_label  = _sanitize(action_label).upper()
    champion_name = _sanitize(champion_name)
    print(f"[THUMB] Generating: {action_label} | {champion_name}")

    frame_path = output_path.replace(".jpg", "_raw_frame.jpg")
    clip_for_frame = source_clip_path if source_clip_path and os.path.exists(source_clip_path) else video_path
    base_t = source_peak_moment if (clip_for_frame == source_clip_path and source_peak_moment is not None) else peak_moment
    
    # Inteligentny wybór najatrakcyjniejszej klatki (Hero-Frame) w oknie walki
    t_for_frame = _find_best_hero_frame(clip_for_frame, base_t, search_window=3.5)
    
    src_label = "oryginalny" if clip_for_frame == source_clip_path else "short"
    print(f"[THUMB] Hero-frame source: {src_label} ({os.path.basename(clip_for_frame)}) @ {t_for_frame:.1f}s (peak={base_t:.1f}s)")

    success = _extract_frame(clip_for_frame, t_for_frame, frame_path)
    if not success:
        success = _extract_frame(clip_for_frame, max(0.5, base_t), frame_path)
    if not success or not os.path.exists(frame_path):
        print("[THUMB] Frame extraction failed -- skip")
        return None

    with Image.open(frame_path) as raw:
        raw = raw.convert("RGB")
        raw_w, raw_h = raw.size
        if raw_w > raw_h:
            hud_cutoff = int(raw_h * 0.82)
            raw_no_hud = raw.crop((0, 0, raw_w, hud_cutoff))
            crop_h_no_hud = hud_cutoff
            crop_w_px = int(crop_h_no_hud * 9 / 16)
            arr = np.array(raw_no_hud)
            best_x = _find_best_crop_x(arr, crop_w_px, source_w=raw_w)
            frame_cropped = raw.crop((best_x, 0, best_x + crop_w_px, hud_cutoff))
        else:
            frame_cropped = raw
        bg = frame_cropped.resize((THUMB_W, THUMB_H), Image.LANCZOS)

    if os.path.exists(frame_path):
        try:
            os.remove(frame_path)
        except Exception:
            pass

    bg = _apply_cinematic_grade(bg, action_label)
    bg = bg.convert("RGBA")
    bg = _add_vignette(bg)

    # Gradienty czytelności
    grad = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(int(THUMB_H * 0.26)):
        ratio = 1.0 - y / (THUMB_H * 0.26)
        alpha = int(200 * ratio ** 1.3)
        gd.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))
    for y in range(int(THUMB_H * 0.85), THUMB_H):
        ratio = (y - int(THUMB_H * 0.85)) / (THUMB_H * 0.15)
        alpha = int(180 * ratio ** 1.4)
        gd.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))
    bg = Image.alpha_composite(bg, grad)

    # Kolory akcji
    if "PENTA" in action_label:
        text_fill = "#FFD700"
        stroke_inner = "#FFF580"
        accent_color = "#FFD700"
        bar_color = (255, 215, 0, 240)
    elif "QUADRA" in action_label:
        text_fill = "#FF6B00"
        stroke_inner = "#FFA855"
        accent_color = "#FF6B00"
        bar_color = (255, 107, 0, 240)
    elif "TRIPLE" in action_label:
        text_fill = "#FFD700"
        stroke_inner = "#FFF8A0"
        accent_color = "#FFD700"
        bar_color = (255, 215, 0, 240)
    elif "OUTPLAY" in action_label:
        text_fill = "#FF2A55"
        stroke_inner = "#FFA0B5"
        accent_color = "#FF2A55"
        bar_color = (255, 42, 85, 240)
    else:
        text_fill = "#00E5FF"
        stroke_inner = "#A0F8FF"
        accent_color = "#00E5FF"
        bar_color = (0, 229, 255, 240)

    draw = ImageDraw.Draw(bg)
    bar_h = 10
    draw.rectangle([(0, 0), (THUMB_W, bar_h)], fill=bar_color)
    draw.rectangle([(0, THUMB_H - bar_h), (THUMB_W, THUMB_H)], fill=bar_color)

    # Bezpieczna pozycja Y (z dala od odcięcia górnego interfejsu YouTube)
    title_y = 190
    max_text_w = 940
    fsize = 155
    font_title = _font(fsize)
    bbox = draw.textbbox((THUMB_W // 2, title_y), action_label, font=font_title, anchor="mt")
    while (bbox[2] - bbox[0]) > max_text_w and fsize > 85:
        fsize -= 8
        font_title = _font(fsize)
        bbox = draw.textbbox((THUMB_W // 2, title_y), action_label, font=font_title, anchor="mt")

    # 3D Drop Shadow
    for off_x, off_y in [(0, 8), (4, 10), (-4, 10)]:
        draw.text((THUMB_W // 2 + off_x, title_y + off_y), action_label, font=font_title, fill=(0, 0, 0, 240), anchor="mt")
    # Zewnętrzny obrys 20px
    draw.text((THUMB_W // 2, title_y), action_label, font=font_title, fill="#000000", stroke_width=20, stroke_fill="#000000", anchor="mt")
    # Wewnętrzne wypełnienie + specular
    draw.text((THUMB_W // 2, title_y), action_label, font=font_title, fill=text_fill, stroke_width=4, stroke_fill=stroke_inner, anchor="mt")

    # Sub-Badge Championa (zaokrąglony glass pill)
    if champion_name:
        font_sub = _font(62)
        sub_text = champion_name.upper()
        sub_y = title_y + fsize + 15
        sub_bbox = draw.textbbox((THUMB_W // 2, sub_y), sub_text, font=font_sub, anchor="mt")
        pw = (sub_bbox[2] - sub_bbox[0]) + 64
        ph = (sub_bbox[3] - sub_bbox[1]) + 20
        px0 = THUMB_W // 2 - pw // 2
        px1 = THUMB_W // 2 + pw // 2
        py0 = sub_y - 6
        py1 = py0 + ph

        pill = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle([(px0, py0), (px1, py1)], radius=16, fill=(15, 15, 22, 220), outline=accent_color, width=3)
        bg = Image.alpha_composite(bg, pill)
        draw = ImageDraw.Draw(bg)
        draw.text((THUMB_W // 2, sub_y + 4), sub_text, font=font_sub, fill="#FFFFFF", stroke_width=5, stroke_fill="#000000", anchor="mt")

    bg.convert("RGB").save(output_path, "JPEG", quality=96, optimize=True)
    print(f"[THUMB] OK: {output_path} ({THUMB_W}x{THUMB_H}) | src={src_label}")
    return output_path
