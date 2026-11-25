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
    os.path.join(_ROOT, "assets", "fonts", "impact.ttf"),
    os.path.join(_HERE, "..", "assets", "fonts", "impact.ttf"),
    os.path.join(_HERE, "impact.ttf"),
    os.path.join(_ROOT, "impact.ttf"),
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
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


# Compatibility alias
extract_peak_frame = _extract_frame


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
    ranked = _find_ranked_hero_frames(
        video_path,
        center_t,
        search_window=search_window,
        max_candidates=1,
        min_gap_s=0.0,
    )
    return ranked[0] if ranked else center_t


def _find_ranked_hero_frames(
    video_path: str,
    center_t: float,
    search_window: float = 3.5,
    max_candidates: int = 6,
    min_gap_s: float = 1.0,
) -> list[float]:
    """
    Zwraca listę najlepszych, wzajemnie odległych momentów akcji w oknie klipu,
    posortowaną malejąco po atrakcyjności (VFX + pasek HP + bliskość peaku).
    Dla max_candidates == 1 zachowuje klasyczne skanowanie center_t +- search_window/2.
    """
    if not os.path.exists(video_path):
        return [center_t]
    cap = None
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return [center_t]
        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        dur = total_frames / fps if fps > 0 else 0.0
        if dur <= 0.6:
            return [center_t]

        if max_candidates <= 1:
            start_t = max(0.5, center_t - search_window / 2.0)
            end_t = min(max(0.5, dur - 1.0), center_t + search_window / 2.0)
            sample_count = 10
        else:
            half_w = max(4.5, search_window * 0.75)
            start_t = max(0.5, min(center_t - half_w, dur * 0.10))
            end_t = min(max(0.5, dur - 0.8), max(center_t + half_w, dur * 0.90))
            sample_count = 24

        if end_t <= start_t:
            return [center_t]

        candidates = np.linspace(start_t, end_t, sample_count)
        scored: list[tuple[float, float]] = []

        for t in candidates:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            ret, fr = cap.read()
            if not ret or fr is None:
                continue

            h, w_fr = fr.shape[:2]
            fr_nohud = fr[:int(h * 0.82), :]
            hsv = cv2.cvtColor(fr_nohud, cv2.COLOR_BGR2HSV)

            r = fr_nohud[:, :, 2].astype(np.int16)
            g = fr_nohud[:, :, 1].astype(np.int16)
            b = fr_nohud[:, :, 0].astype(np.int16)
            gold_mask = ((r > 160) & (g > 130) & (b < 115) & ((r - b) > 40) & ((g - b) > 15))
            gold_pts = int(cv2.countNonZero(gold_mask.astype(np.uint8)))

            # Premia za złotą/kolorową akcję bliżej środka kadru zamiast uciętych krawędzi
            center_roi = fr_nohud[int(h * 0.14):int(h * 0.72), int(w_fr * 0.25):int(w_fr * 0.75)]
            if center_roi.size > 0:
                cr_sat = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)[:, :, 1]
                center_vfx = float(np.mean(cr_sat > 130)) * 60.0
            else:
                center_vfx = 0.0

            # Lekka kara za ciężki popup/tekst UI w prawym dolnym rogu (np. Mid Lane Quest Reward)
            br_roi = fr[int(h * 0.64):int(h * 0.84), int(w_fr * 0.68):]
            popup_penalty = 0.0
            if br_roi.size > 0:
                br_gray = cv2.cvtColor(br_roi, cv2.COLOR_BGR2GRAY)
                bright_txt_ratio = float(np.mean(br_gray > 195))
                dark_box_ratio = float(np.mean(br_gray < 42))
                if bright_txt_ratio > 0.06 and dark_box_ratio > 0.45:
                    popup_penalty = 35.0

            sat = hsv[:, :, 1]
            high_sat = sat > 140
            vfx_score = float(np.mean(sat[high_sat])) if high_sat.any() else 0.0

            val = hsv[:, :, 2]
            avg_bright = float(np.mean(val))
            avg_sat = float(np.mean(sat))
            # Odrzuć czarne/prześwietlone klatki oraz szary ekran śmierci (grey screen)
            if avg_bright < 35 or avg_bright > 240 or avg_sat < 25.0:
                continue

            proximity_bonus = 0.0 if max_candidates <= 1 else max(0.0, 25.0 - abs(float(t) - center_t) * 4.0)
            score = vfx_score + center_vfx + (150.0 if gold_pts >= 10 else 0.0) + proximity_bonus - popup_penalty
            scored.append((score, float(t)))

        if not scored:
            return [center_t]

        scored.sort(key=lambda pair: pair[0], reverse=True)
        if max_candidates <= 1:
            return [scored[0][1]]

        def _pick_spaced(gap_s: float) -> list[float]:
            chosen: list[float] = []
            for _sc, ts in scored:
                if all(abs(ts - existing) >= gap_s for existing in chosen):
                    chosen.append(ts)
                    if len(chosen) >= max_candidates:
                        break
            return chosen

        picked = _pick_spaced(max(0.0, float(min_gap_s)))
        if len(picked) < min(3, max_candidates):
            picked = _pick_spaced(0.5)

        if len(picked) < min(3, max_candidates):
            low_t = max(0.5, min(start_t, dur * 0.15))
            high_t = max(low_t + 0.5, min(dur - 0.5, end_t))
            for fallback_t in np.linspace(low_t, high_t, max_candidates):
                ft = float(fallback_t)
                if all(abs(ft - existing) >= 0.45 for existing in picked):
                    picked.append(ft)
                    if len(picked) >= max_candidates:
                        break

        return picked if picked else [center_t]
    except Exception as e:
        print(f"[THUMB] Hero-frame search error: {e}")
        return [center_t]
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


def _render_thumbnail_typography_and_fx(
    bg: Image.Image,
    action_label: str,
    champion_name: str,
    style_idx: int,
) -> Image.Image:
    """Nakłada kolorystykę, winietę, gradienty, typografię 3D i badge zgodnie z wariantem stylu."""
    if style_idx == 1:
        bg = ImageEnhance.Contrast(bg).enhance(1.30)
        bg = ImageEnhance.Color(bg).enhance(1.38)
        bg = ImageEnhance.Sharpness(bg).enhance(1.32)
        bg = ImageEnhance.Brightness(bg).enhance(0.95)
    elif style_idx == 2:
        bg = ImageEnhance.Contrast(bg).enhance(1.24)
        bg = ImageEnhance.Color(bg).enhance(1.26)
        bg = ImageEnhance.Sharpness(bg).enhance(1.22)
        bg = ImageEnhance.Brightness(bg).enhance(0.90)
        # Delikatnie cieplejszy cinematic tint
        warm = Image.new("RGB", bg.size, (255, 200, 140))
        bg = Image.blend(bg, warm, 0.08)
    elif style_idx == 3:
        bg = ImageEnhance.Contrast(bg).enhance(1.26)
        bg = ImageEnhance.Color(bg).enhance(1.22)
        bg = ImageEnhance.Sharpness(bg).enhance(1.28)
        bg = ImageEnhance.Brightness(bg).enhance(0.86)
        cool = Image.new("RGB", bg.size, (125, 190, 255))
        bg = Image.blend(bg, cool, 0.07)
    else:
        bg = _apply_cinematic_grade(bg, action_label)

    bg = bg.convert("RGBA")
    bg = _add_vignette(bg)
    if style_idx == 3:
        bg = _add_vignette(bg)

    # Gradienty czytelności zależne od położenia tekstu
    grad = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top_end = int(THUMB_H * (0.28 if style_idx != 2 else 0.16))
    for y in range(top_end):
        ratio = 1.0 - y / max(1, top_end)
        alpha = int((210 if style_idx != 2 else 130) * ratio ** 1.3)
        gd.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))

    bot_start = int(THUMB_H * (0.58 if style_idx == 2 else 0.85))
    bot_span = max(1, THUMB_H - bot_start)
    for y in range(bot_start, THUMB_H):
        ratio = (y - bot_start) / bot_span
        alpha = int((230 if style_idx == 2 else 180) * ratio ** 1.35)
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
    elif "TRIPLE" in action_label or "DOUBLE" in action_label:
        text_fill = "#FFD700"
        stroke_inner = "#FFF8A0"
        accent_color = "#FFD700"
        bar_color = (255, 215, 0, 240)
    elif "OUTPLAY" in action_label:
        text_fill = "#FF2A55"
        stroke_inner = "#FFA0B5"
        accent_color = "#FF2A55"
        bar_color = (255, 42, 85, 240)
    elif "SOLO" in action_label or "BOLO" in action_label:
        text_fill = "#FF1744"
        stroke_inner = "#FF8A80"
        accent_color = "#FF1744"
        bar_color = (255, 23, 68, 240)
    else:
        text_fill = "#00E5FF"
        stroke_inner = "#A0F8FF"
        accent_color = "#00E5FF"
        bar_color = (0, 229, 255, 240)

    if style_idx == 1 and "PENTA" not in action_label and "QUADRA" not in action_label:
        text_fill = "#C8FF3A"
        stroke_inner = "#ECFFB8"
        accent_color = "#C8FF3A"
        bar_color = (200, 255, 58, 240)
    elif style_idx == 3:
        text_fill = "#FFFFFF"
        stroke_inner = accent_color

    draw = ImageDraw.Draw(bg)
    bar_h = 14 if style_idx == 1 else 10
    draw.rectangle([(0, 0), (THUMB_W, bar_h)], fill=bar_color)
    draw.rectangle([(0, THUMB_H - bar_h), (THUMB_W, THUMB_H)], fill=bar_color)

    if style_idx == 1:
        title_y = 230
    elif style_idx == 2:
        title_y = 1300
    elif style_idx == 3:
        title_y = 195
    else:
        title_y = 190

    max_text_w = 940
    fsize = 155 if style_idx != 1 else 162
    font_title = _font(fsize)
    bbox = draw.textbbox((THUMB_W // 2, title_y), action_label, font=font_title, anchor="mt")
    while (bbox[2] - bbox[0]) > max_text_w and fsize > 85:
        fsize -= 8
        font_title = _font(fsize)
        bbox = draw.textbbox((THUMB_W // 2, title_y), action_label, font=font_title, anchor="mt")

    if style_idx == 3:
        banner_h = fsize + (110 if champion_name else 44)
        banner_top = max(bar_h + 12, title_y - 26)
        banner_bot = min(THUMB_H - bar_h - 12, banner_top + banner_h)
        banner = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(banner)
        bd.rectangle([(0, banner_top), (THUMB_W, banner_bot)], fill=(10, 12, 18, 175))
        bd.line([(0, banner_top), (THUMB_W, banner_top)], fill=bar_color, width=4)
        bd.line([(0, banner_bot), (THUMB_W, banner_bot)], fill=bar_color, width=4)
        bg = Image.alpha_composite(bg, banner)
        draw = ImageDraw.Draw(bg)

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
        sub_y = (title_y - 95) if style_idx == 2 else (title_y + fsize + 15)
        sub_bbox = draw.textbbox((THUMB_W // 2, sub_y), sub_text, font=font_sub, anchor="mt")
        pw = (sub_bbox[2] - sub_bbox[0]) + 64
        ph = (sub_bbox[3] - sub_bbox[1]) + 20
        px0 = THUMB_W // 2 - pw // 2
        px1 = THUMB_W // 2 + pw // 2
        py0 = sub_y - 6
        py1 = py0 + ph

        pill = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pill_fill = (20, 24, 14, 230) if style_idx == 1 else (15, 15, 22, 220)
        pd.rounded_rectangle([(px0, py0), (px1, py1)], radius=16, fill=pill_fill, outline=accent_color, width=3)
        bg = Image.alpha_composite(bg, pill)
        draw = ImageDraw.Draw(bg)
        draw.text((THUMB_W // 2, sub_y + 4), sub_text, font=font_sub, fill="#FFFFFF", stroke_width=5, stroke_fill="#000000", anchor="mt")

    return bg


def generate_thumbnail(
    video_path: str,
    peak_moment: float,
    action_label: str,
    champion_name: str = "",
    output_path: str = None,
    source_clip_path: str = None,
    source_peak_moment: float = None,
    variant_index: int = 0,
) -> Optional[str]:
    """
    Generuje profesjonalną miniaturkę 1080x1920 z czytelną typografią i bezpiecznym marginesem.
    variant_index > 0 obraca klatkami Hero-Frame i stylami kompozycji, aby każde ponowne
    generowanie tworzyło wyraźnie inny wariant.
    """
    if output_path is None:
        output_path = os.path.join(os.path.dirname(video_path), "thumbnail.jpg")

    variant_idx = max(0, int(variant_index or 0))
    style_idx = variant_idx % 4
    action_label  = _sanitize(action_label).upper()
    champion_name = _sanitize(champion_name)
    print(f"[THUMB] Generating: {action_label} | {champion_name} | variant={variant_idx}")

    frame_path = output_path.replace(".jpg", "_raw_frame.jpg")
    clip_for_frame = source_clip_path if source_clip_path and os.path.exists(source_clip_path) else video_path
    base_t = source_peak_moment if (clip_for_frame == source_clip_path and source_peak_moment is not None) else peak_moment

    if variant_idx == 0:
        t_for_frame = _find_best_hero_frame(clip_for_frame, base_t, search_window=3.5)
    else:
        cands = _find_ranked_hero_frames(
            clip_for_frame,
            base_t,
            search_window=6.0,
            max_candidates=6,
            min_gap_s=1.0,
        )
        t_for_frame = cands[variant_idx % len(cands)] if cands else base_t

    src_label = "oryginalny" if clip_for_frame == source_clip_path else "short"
    print(f"[THUMB] Hero-frame source: {src_label} ({os.path.basename(clip_for_frame)}) @ {t_for_frame:.1f}s (peak={base_t:.1f}s, variant={variant_idx})")

    success = extract_peak_frame(clip_for_frame, t_for_frame, frame_path)
    if not success:
        success = extract_peak_frame(clip_for_frame, max(0.5, base_t), frame_path)
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
            crop_top = 0
            crop_bottom = hud_cutoff
            if style_idx == 1:
                zoom_w = max(320, int(crop_w_px / 1.16))
                zoom_h = max(480, int(crop_h_no_hud / 1.16))
                best_x = max(0, min(best_x + (crop_w_px - zoom_w) // 2, raw_w - zoom_w))
                crop_top = max(0, (crop_h_no_hud - zoom_h) // 2)
                crop_bottom = crop_top + zoom_h
                crop_w_px = zoom_w
            elif style_idx == 2:
                best_x = max(0, min(best_x + int(raw_w * 0.06), raw_w - crop_w_px))
            elif style_idx == 3:
                best_x = max(0, min(best_x - int(raw_w * 0.06), raw_w - crop_w_px))
            frame_cropped = raw.crop((best_x, crop_top, best_x + crop_w_px, crop_bottom))
        else:
            if style_idx == 1:
                zw = max(360, int(raw_w / 1.16))
                zh = max(640, int(raw_h / 1.16))
                x0 = max(0, (raw_w - zw) // 2)
                y0 = max(0, (raw_h - zh) // 2)
                frame_cropped = raw.crop((x0, y0, x0 + zw, y0 + zh))
            elif style_idx in (2, 3):
                zw = max(360, int(raw_w * 0.92))
                zh = max(640, int(raw_h * 0.92))
                x0 = int((raw_w - zw) * (0.85 if style_idx == 2 else 0.15))
                y0 = max(0, (raw_h - zh) // 2)
                frame_cropped = raw.crop((x0, y0, x0 + zw, y0 + zh))
            else:
                frame_cropped = raw
        bg = frame_cropped.resize((THUMB_W, THUMB_H), Image.LANCZOS)

    if os.path.exists(frame_path):
        try:
            os.remove(frame_path)
        except Exception:
            pass

    bg = _render_thumbnail_typography_and_fx(bg, action_label, champion_name, style_idx)

    bg.convert("RGB").save(output_path, "JPEG", quality=96, optimize=True)
    print(f"[THUMB] OK: {output_path} ({THUMB_W}x{THUMB_H}) | src={src_label} | variant={variant_idx}")
    return output_path
