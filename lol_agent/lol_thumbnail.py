"""
LOL Agent — Thumbnail Generator v2
Styl wzorowany na kanale Dwannellenga (reference channel analysis).

Kluczowe zmiany vs v1:
- Klatka z ORYGINALNEGO KLIPU (nie z przetworzonego shorta, ktory ma efekty i moze byc znieksztalcony)
- Kadr dynamicznie wybiera region z najwyzszym nasyeniciem (champion VFX / kills)
- Agresywny vignette + kolor grading (cinematic dark look)
- Zloty pasek na dole (signature Dwannellenga style)
- Duzy bold text akcji u gory, champion name ponizej

Styl referencyjny: dark gameplay frame + zlote/czerwone akcenty + Impact font.
"""
import os
import sys
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

THUMB_W = 1080
THUMB_H = 1920
_HERE = os.path.dirname(__file__)
_ROOT = os.path.dirname(_HERE)

# Auto-detect ffmpeg (działa bez systemowego PATH)
def _find_ffmpeg() -> str:
    candidates = [
        r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "ffmpeg"  # fallback — zakłada PATH

FFMPEG_BIN = _find_ffmpeg()

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
    text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    text = re.sub(r'[^\x00-\x7F\u00C0-\u024F]', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _logo() -> Optional[Image.Image]:
    for p in LOGO_CANDIDATES:
        if os.path.exists(p):
            try:
                return Image.open(p).convert("RGBA")
            except Exception:
                pass
    return None


def _extract_frame(video_path: str, t: float, out: str) -> bool:
    """Wyciaga klatke przez FFmpeg z danego czasu."""
    r = subprocess.run([
        FFMPEG_BIN, "-y",
        "-ss", f"{t:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        out
    ], capture_output=True)
    return r.returncode == 0 and os.path.exists(out)


def _find_best_crop_x(img_rgb: np.ndarray, crop_w_px: int, source_w: int = 1920) -> int:
    """
    W oryginalnym 16:9 frame (1920x1080) znajdz kolumne z najwyzszym nasyeniciem koloru.
    Champion ability VFX (czerwony dla Katariny) beda dominowac.
    Zwraca x lewy brzeg cropa.
    """
    # Konwertuj do HSV i wyciagnij kanal S (nasycenie)
    from PIL import Image as PilImage
    img_pil = PilImage.fromarray(img_rgb)
    hsv = np.array(img_pil.convert("HSV"))
    sat = hsv[:, :, 1].astype(float)  # (H, W)

    # Wyklucz HUD (dolne 18% = HUD bar)
    h = sat.shape[0]
    sat[int(h * 0.82):, :] = 0

    # Zsumuj nasycenie wzdluz kolumn
    col_sat = sat.sum(axis=0)  # (W,)

    # Wygladz
    kernel = np.ones(31) / 31
    col_sat = np.convolve(col_sat, kernel, mode='same')

    # Centrum ciezkosci nasycenia
    total = col_sat.sum()
    if total > 0:
        cx = int((col_sat * np.arange(len(col_sat))).sum() / total)
    else:
        cx = source_w // 2

    # 70% nasycenie + 30% centrum — champion jest blizej centrum niz skraje
    cx_blended = int(0.70 * cx + 0.30 * (source_w // 2))

    x = cx_blended - crop_w_px // 2
    return max(0, min(x, source_w - crop_w_px))


def _apply_cinematic_grade(img: Image.Image, action: str) -> Image.Image:
    """
    Cinematic color grade dopasowany do stylu kanalu:
    - Lekkie zwiekszenie kontrastu (+20%)
    - Lekkie zwiekszenie nasycenia (+30%) dla VFX
    - Sciemnienie (+40% dark) dla dramatyzmu
    """
    img = ImageEnhance.Contrast(img).enhance(1.20)
    img = ImageEnhance.Color(img).enhance(1.30)
    img = ImageEnhance.Brightness(img).enhance(0.70)
    return img


def _draw_text_stroke(draw, text, font, x, y, fill, stroke_color, stroke_w, anchor="mt"):
    draw.text((x, y), text, font=font, fill=stroke_color,
              stroke_width=stroke_w, align="center", anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill,
              stroke_width=0, align="center", anchor=anchor)


def _add_vignette(img: Image.Image) -> Image.Image:
    """Dodaje dramatyczny vignette (ciemne rogi jak w filmach)."""
    w, h = img.size
    vig = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vig)

    steps = 60
    for i in range(steps):
        ratio = i / steps
        alpha = int(200 * (1 - ratio) ** 1.8)
        margin_x = int(w * 0.55 * ratio)
        margin_y = int(h * 0.55 * ratio)
        
        x0 = margin_x
        y0 = margin_y
        x1 = w - margin_x
        y1 = h - margin_y
        
        # Zapobiegaj przecinaniu sie linii (x1 < x0 lub y1 < y0)
        if x0 >= x1 or y0 >= y1:
            continue
            
        vd.rectangle(
            [x0, y0, x1, y1],
            outline=(0, 0, 0, alpha), width=4
        )

    return Image.alpha_composite(img.convert("RGBA"), vig)


def generate_thumbnail(
    video_path: str,
    peak_moment: float,
    action_label: str,
    champion_name: str = "",
    output_path: str = None,
    source_clip_path: str = None,
    source_peak_moment: float = None,   # czas absolutny w source_clip (moze byc inny niz peak_moment)
) -> Optional[str]:
    """
    Generuje miniaturke 1080x1920 w stylu kanalu Dwannellenga.

    source_clip_path: jesli podany, uzyj oryinalnego klipu zamiast rendered shorta.
                      Daje czysty, nieznieksztalcony frame bez slow-mo artefaktow.
    """
    if output_path is None:
        output_path = os.path.join(os.path.dirname(video_path), "thumbnail.jpg")

    action_label  = _sanitize(action_label).upper()
    champion_name = _sanitize(champion_name)

    print(f"[THUMB] Generating: {action_label} | {champion_name}")

    # ── 1. Wyciagnij klatke ───────────────────────────────────────────────────
    frame_path = output_path.replace(".jpg", "_raw_frame.jpg")

    # Preferuj oryginalny klip — daje czystsza grafike bez post-processing artefaktow
    clip_for_frame = source_clip_path if source_clip_path and os.path.exists(source_clip_path) else video_path
    # Czas wyciagniecia klatki:
    # - source_clip: uzyj source_peak_moment (absolutny czas w oryginale)
    # - rendered short: uzyj peak_moment (czas wzgledem shorta)
    t_for_frame = source_peak_moment if (clip_for_frame == source_clip_path and source_peak_moment is not None) else peak_moment
    src_label = "oryginalny" if clip_for_frame == source_clip_path else "short"
    print(f"[THUMB] Frame source: {src_label} ({os.path.basename(clip_for_frame)}) @ {t_for_frame:.1f}s")

    success = _extract_frame(clip_for_frame, t_for_frame, frame_path)
    if not success:
        success = _extract_frame(clip_for_frame, t_for_frame * 0.5, frame_path)
    if not success or not os.path.exists(frame_path):
        print("[THUMB] Frame extraction failed — skip")
        return None

    # ── 2. Zaladuj i wyznacz crop 9:16 w 16:9 orygiale ───────────────────────
    with Image.open(frame_path) as raw:
        raw = raw.convert("RGB")
        raw_w, raw_h = raw.size

        if raw_w > raw_h:
            # 16:9 source — obetnij 20% dolu (HUD: items/skills bar) przed crop 9:16
            hud_cutoff = int(raw_h * 0.80)
            raw_no_hud = raw.crop((0, 0, raw_w, hud_cutoff))
            crop_h_no_hud = hud_cutoff
            crop_w_px = int(crop_h_no_hud * 9 / 16)

            arr = np.array(raw_no_hud)
            best_x = _find_best_crop_x(arr, crop_w_px, source_w=raw_w)

            frame_cropped = raw.crop((best_x, 0, best_x + crop_w_px, hud_cutoff))
        else:
            # Juz 9:16 (rendered short) — uzyj jak jest
            frame_cropped = raw

        bg = frame_cropped.resize((THUMB_W, THUMB_H), Image.LANCZOS)

    if os.path.exists(frame_path):
        os.remove(frame_path)

    # ── 3. Cinematic grade ────────────────────────────────────────────────────
    bg = _apply_cinematic_grade(bg, action_label)
    bg = bg.convert("RGBA")

    # ── 4. Vignette ───────────────────────────────────────────────────────────
    bg = _add_vignette(bg)

    # ── 5. Gradient od gory (dla czytelnosci tekstu) i od dolu ───────────────
    grad = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)

    # Gradient gorny (pierwsze 35% ekranu — tu bedzie tekst)
    for y in range(int(THUMB_H * 0.38)):
        ratio = 1.0 - y / (THUMB_H * 0.38)
        alpha = int(185 * ratio ** 1.2)
        gd.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))

    # Gradient dolny (ostatnie 30%)
    grad_start = int(THUMB_H * 0.70)
    for y in range(grad_start, THUMB_H):
        ratio = (y - grad_start) / (THUMB_H - grad_start)
        alpha = int(170 * ratio ** 1.5)
        gd.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))

    bg = Image.alpha_composite(bg, grad)

    # ── 6. Kolory zalezne od akcji ────────────────────────────────────────────
    if "PENTA" in action_label:
        text_color   = "#FFD700"   # zloty
        accent_color = "#FF4500"   # pomaranczowy glow
        bar_color    = (255, 215, 0, 230)
    elif "QUADRA" in action_label:
        text_color   = "#FF6B35"
        accent_color = "#CC0000"
        bar_color    = (255, 107, 53, 230)
    elif "TRIPLE" in action_label:
        text_color   = "#FFFFFF"
        accent_color = "#4169E1"
        bar_color    = (65, 105, 225, 230)
    else:
        text_color   = "#FFFFFF"
        accent_color = "#8A2BE2"
        bar_color    = (138, 43, 226, 230)

    draw = ImageDraw.Draw(bg)

    # ── 7. Zloty pasek u gory (signature style) ───────────────────────────────
    bar_h = 14
    draw.rectangle([(0, 0), (THUMB_W, bar_h)], fill=bar_color)

    # ── 8. Tekst akcji — duzy, centrowany w gornej 1/3 ───────────────────────
    font_big = _font(150)
    text_x = THUMB_W // 2
    text_y = int(THUMB_H * 0.06)

    # Podziel na dwie linie — TYLKO jesli jest naturalna spacja
    # Nigdy nie tnij slowa w polowie (QUADR/AKILL = amatorski wyglad)
    NATURAL_SPLITS = {
        "PENTAKILL":    ("PENTA",    "KILL"),
        "QUADRAKILL":   ("QUADRA",   "KILL"),
        "TRIPLE KILL":  ("TRIPLE",   "KILL"),
        "DOUBLE KILL":  ("DOUBLE",   "KILL"),
        "KILLING SPREE":("KILLING",  "SPREE"),
    }
    if action_label in NATURAL_SPLITS:
        line1, line2 = NATURAL_SPLITS[action_label]
        _draw_text_stroke(draw, line1, font_big, text_x, text_y,
                          fill=text_color, stroke_color="#000000", stroke_w=18)
        font_big2 = _font(140)
        _draw_text_stroke(draw, line2, font_big2, text_x, text_y + 165,
                          fill=text_color, stroke_color="#000000", stroke_w=12)
        champ_y = text_y + 165 + 150
    elif " " in action_label and len(action_label) > 9:
        parts = action_label.split()
        mid = len(parts) // 2
        line1 = " ".join(parts[:mid])
        line2 = " ".join(parts[mid:])
        _draw_text_stroke(draw, line1, font_big, text_x, text_y,
                          fill=text_color, stroke_color="#000000", stroke_w=18)
        font_big2 = _font(140)
        _draw_text_stroke(draw, line2, font_big2, text_x, text_y + 165,
                          fill=text_color, stroke_color="#000000", stroke_w=12)
        champ_y = text_y + 165 + 150
    else:
        font_size = max(90, 150 - max(0, len(action_label) - 8) * 8)
        font_adj = _font(font_size)
        _draw_text_stroke(draw, action_label, font_adj, text_x, text_y,
                          fill=text_color, stroke_color="#000000", stroke_w=18)
        champ_y = text_y + 180

    # ── 9. Tekst championa ────────────────────────────────────────────────────
    if champion_name:
        font_champ = _font(85)
        bbox_approx_w = len(champion_name) * 52
        box_x1 = THUMB_W // 2 - bbox_approx_w // 2 - 20
        box_x2 = THUMB_W // 2 + bbox_approx_w // 2 + 20
        box_overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_overlay)
        box_draw.rectangle(
            [(max(0, box_x1), champ_y - 5), (min(THUMB_W, box_x2), champ_y + 100)],
            fill=(0, 0, 0, 120)
        )
        bg = Image.alpha_composite(bg, box_overlay)
        draw = ImageDraw.Draw(bg)

        _draw_text_stroke(draw, champion_name.upper(), font_champ, text_x, champ_y,
                          fill="white", stroke_color="black", stroke_w=8)

    # ── 10. Logo kanalu — nad HUD, nie w samym rogu ───────────────────────────
    logo = _logo()
    if logo is not None:
        logo_size = 180
        logo.thumbnail((logo_size, logo_size))
        logo_x = THUMB_W - logo.width - 35
        logo_y = THUMB_H - logo.height - 200   # 200px od dolu = nad paskiem HUD
        bg.paste(logo, (logo_x, logo_y), logo)

    # ── 11. Dolny pasek kolorowy (signature) ─────────────────────────────────
    draw = ImageDraw.Draw(bg)
    draw.rectangle([(0, THUMB_H - bar_h), (THUMB_W, THUMB_H)], fill=bar_color)

    # ── 12. Zapisz ────────────────────────────────────────────────────────────
    bg.convert("RGB").save(output_path, "JPEG", quality=95, optimize=True)
    print(f"[THUMB] OK: {output_path} ({THUMB_W}x{THUMB_H}) | src={src_label}")
    return output_path
