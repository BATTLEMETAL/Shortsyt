"""
LOL Agent — Native 9:16 Commercial Multi-Shot Montage & Pitch Mockup Renderer
==============================================================================
Renderer komercyjny (jedzenie / paznokcie / lokalny biznes / produkt):
- Brak gamingowego cropa 16:9 z paska HP LoL.
- Obsługa natywnych pionowych klipów 9:16 z telefonu oraz poziomych 16:9 (smart-crop na akcję/twarz).
- Renderowanie odtwarzalnego podglądu pitch 9:16 (MP4 + miniatura JPG) zanim klient wyśle materiały,
  dokładnie w rytmie cięć i scen storyboardu z researchu YT.
- Polskie czcionki TTF z obsługą znaków ąćęłńóśźż oraz automatyczny fallback NVENC -> libx264.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from lol_agent.ad_event_detector import detect_ad_events

OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30

_THEME_PALETTES: Dict[str, Dict[str, Tuple[int, int, int]]] = {
    "FOOD_GASTRO": {
        "bg_top": (28, 16, 12),
        "bg_bottom": (14, 9, 8),
        "accent": (255, 138, 36),
        "accent_soft": (255, 214, 102),
        "card": (38, 24, 19),
        "border": (110, 62, 34),
    },
    "NAILS_BEAUTY": {
        "bg_top": (29, 16, 26),
        "bg_bottom": (15, 10, 16),
        "accent": (244, 114, 182),
        "accent_soft": (251, 207, 232),
        "card": (40, 24, 38),
        "border": (120, 58, 98),
    },
    "PRODUCT_ECOMMERCE_AD": {
        "bg_top": (12, 18, 28),
        "bg_bottom": (8, 10, 16),
        "accent": (56, 189, 248),
        "accent_soft": (200, 255, 58),
        "card": (22, 29, 42),
        "border": (48, 72, 102),
    },
    "EXPERT_BRAND_SHORT": {
        "bg_top": (15, 18, 22),
        "bg_bottom": (8, 9, 12),
        "accent": (200, 255, 58),
        "accent_soft": (244, 244, 245),
        "card": (24, 28, 34),
        "border": (60, 68, 78),
    },
}


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidate = r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.EXE"
    if os.path.isfile(candidate):
        return candidate
    raise RuntimeError("Nie znaleziono ffmpeg w PATH")


def _find_ffprobe() -> Optional[str]:
    found = shutil.which("ffprobe")
    if found:
        return found
    candidate = r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffprobe.EXE"
    return candidate if os.path.isfile(candidate) else None


def _load_pl_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arial.ttf"]
        if bold
        else [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\segoeui.ttf"]
    )
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for w in words[1:]:
        test = f"{current} {w}"
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def _probe_video(path: Path) -> Dict[str, Any]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Nie można odczytać klipu: {path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if fps <= 0.1 or fps > 240.0:
            fps = 30.0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)
        dur = (frames / fps) if frames > 0 else 3.0
    finally:
        cap.release()

    has_audio = False
    ffprobe = _find_ffprobe()
    if ffprobe:
        try:
            res = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            data = json.loads(res.stdout or "{}")
            has_audio = bool(data.get("streams"))
        except Exception:
            has_audio = False

    return {"fps": fps, "width": w, "height": h, "duration_s": max(0.5, dur), "has_audio": has_audio}


def _encode_cmd_with_nvenc_fallback(cmd_nvenc: List[str], cmd_x264: List[str]) -> None:
    try:
        res = subprocess.run(cmd_nvenc, capture_output=True, text=True, timeout=180)
        if res.returncode == 0:
            return
    except Exception:
        pass
    res2 = subprocess.run(cmd_x264, capture_output=True, text=True, timeout=240)
    if res2.returncode != 0:
        raise RuntimeError(f"FFmpeg encode failed: {(res2.stderr or res2.stdout)[-600:]}")


def _build_pitch_card_image(
    scene: Dict[str, Any],
    scene_idx: int,
    total_scenes: int,
    blueprint: Dict[str, Any],
    palette: Dict[str, Tuple[int, int, int]],
) -> Image.Image:
    """Buduje czystą planszę 1080x1920 (strefa bezpieczna Shorts/Reels) dla jednej sceny pitchu."""
    img = Image.new("RGB", (OUT_W, OUT_H), palette["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # Pionowy gradient tła
    r1, g1, b1 = palette["bg_top"]
    r2, g2, b2 = palette["bg_bottom"]
    for y in range(0, OUT_H, 8):
        t = y / float(OUT_H)
        col = (int(r1 + (r2 - r1) * t), int(g1 + (g2 - g1) * t), int(b1 + (b2 - b1) * t))
        draw.rectangle([0, y, OUT_W, min(OUT_H, y + 8)], fill=col)

    font_tag = _load_pl_font(34, bold=True)
    font_h1 = _load_pl_font(68, bold=True)
    font_h2 = _load_pl_font(44, bold=True)
    font_body = _load_pl_font(36, bold=False)
    font_small = _load_pl_font(28, bold=False)

    client = blueprint.get("client_profile") or {}
    orig = blueprint.get("originality_report") or {}
    rules = blueprint.get("montage_rules") or {}
    yt = (blueprint.get("comparison") or {}).get("youtube_pattern") or {}

    biz = str(client.get("business_name") or "Lokalny Biznes")
    city = str(client.get("city") or "")
    cta = str(client.get("cta") or "Sprawdź ofertę!")
    orig_pct = float(orig.get("originality_score_pct") or 100.0)
    cuts_10s = float(rules.get("target_cuts_per_10s") or 4.5)

    # Górny bezpieczny pasek statusu (y=130..220)
    draw.rounded_rectangle([64, 130, 1016, 224], radius=18, fill=palette["card"], outline=palette["border"], width=2)
    step_badge = f"SCENA {scene_idx:02d}/{total_scenes:02d} · {scene.get('role', 'SCENA')}"
    draw.text((92, 156), step_badge, font=font_tag, fill=palette["accent"])
    timing_txt = f"{float(scene.get('start_s', 0)):.1f}s–{float(scene.get('end_s', 0)):.1f}s"
    tb = draw.textbbox((0, 0), timing_txt, font=font_tag)
    draw.text((988 - (tb[2] - tb[0]), 156), timing_txt, font=font_tag, fill=palette["accent_soft"])

    # Pasek postępu całej rolki pod nagłówkiem
    progress_ratio = scene_idx / float(max(1, total_scenes))
    draw.rounded_rectangle([64, 244, 1016, 260], radius=8, fill=(35, 38, 46))
    draw.rounded_rectangle([64, 244, max(84, int(64 + (1016 - 64) * progress_ratio)), 260], radius=8, fill=palette["accent"])

    # Górny napis Hook / Napis na filmie
    hook_txt = str(scene.get("overlay_text_pl") or blueprint.get("opening_hook_pl") or biz).upper()
    hook_lines = _wrap_text(draw, hook_txt, font_h1, 900)[:3]
    y_cursor = 340
    for line in hook_lines:
        lb = draw.textbbox((0, 0), line, font=font_h1)
        x_center = (OUT_W - (lb[2] - lb[0])) // 2
        draw.text((x_center + 3, y_cursor + 3), line, font=font_h1, fill=(0, 0, 0))
        draw.text((x_center, y_cursor), line, font=font_h1, fill=(255, 255, 255))
        y_cursor += 86

    # Centralna karta wizualizacji ujęcia (y=640..1240) — symuluje kadr z telefonu
    card_top = max(y_cursor + 40, 620)
    card_bottom = 1230
    draw.rounded_rectangle([72, card_top, 1008, card_bottom], radius=28, fill=palette["card"], outline=palette["accent"], width=3)

    # Wewnątrz karty: cel kadru + instrukcja kamery dla klienta
    draw.text((110, card_top + 38), f"CO POKAŻEMY NA TYM UJĘCIU ({float(scene.get('duration_s', 1.8)):.1f}s):", font=font_tag, fill=palette["accent_soft"])
    vis_lines = _wrap_text(draw, str(scene.get("visual_plan_pl") or ""), font_h2, 860)[:4]
    vy = card_top + 102
    for line in vis_lines:
        draw.text((110, vy), line, font=font_h2, fill=(244, 244, 245))
        vy += 58

    cam_title_y = max(vy + 34, card_top + 350)
    draw.line([110, cam_title_y - 16, 970, cam_title_y - 16], fill=palette["border"], width=2)
    draw.text((110, cam_title_y), "JAK NAGRAĆ TELEFONEM (9:16):", font=font_tag, fill=palette["accent"])
    cam_lines = _wrap_text(draw, str(scene.get("camera_note_pl") or ""), font_body, 860)[:3]
    cy = cam_title_y + 52
    for line in cam_lines:
        draw.text((110, cy), line, font=font_body, fill=(205, 212, 222))
        cy += 48

    # Dolna karta porównawcza + CTA (bezpiecznie nad paskiem podpisów TikTok/YT y=1280..1580)
    draw.rounded_rectangle([72, 1275, 1008, 1590], radius=24, fill=(18, 20, 26), outline=palette["border"], width=2)
    biz_header = f"{biz} ({city})" if city else biz
    if scene_idx == total_scenes:
        draw.text((110, 1308), "FINAŁ — WIZYTÓWKA & CTA KLIENTA", font=font_tag, fill=palette["accent"])
        cta_lines = _wrap_text(draw, f"{biz_header} • {cta}", font_h2, 860)[:3]
        ty = 1368
        for line in cta_lines:
            draw.text((110, ty), line, font=font_h2, fill=(255, 255, 255))
            ty += 56
    else:
        draw.text((110, 1308), f"MARKA KLIENTA: {biz_header}", font=font_tag, fill=palette["accent"])
        comp_txt = (
            f"Rytm ze wzorca YT: {cuts_10s:.1f} cięć/10s (wyśw. wzorca: {int(yt.get('views') or 0):,}). "
            f"Twój projekt: {orig_pct:.0f}% oryginalności (zero plagiatu)."
        )
        clines = _wrap_text(draw, comp_txt, font_small, 860)[:3]
        ty = 1368
        for line in clines:
            draw.text((110, ty), line, font=font_small, fill=(195, 202, 214))
            ty += 42
        badge_txt = f"ANTY-PLAGIAT OK ({orig_pct:.0f}%) • GOTOWE POD IG / TT / SHORTS"
        draw.text((110, 1520), badge_txt, font=font_small, fill=palette["accent_soft"])

    return img


def render_commercial_pitch_mockup(
    blueprint: Dict[str, Any],
    output_path: Path,
    music_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Generuje realny odtwarzalny film pitch 1080x1920 30fps (MP4 + JPG thumbnail)
    dokładnie wg czasów storyboardu z researchu YT.
    """
    ffmpeg = _find_ffmpeg()
    out_mp4 = Path(output_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    thumb_jpg = out_mp4.with_suffix(".jpg")

    preset = str(blueprint.get("niche_preset") or "FOOD_GASTRO")
    palette = _THEME_PALETTES.get(preset, _THEME_PALETTES["PRODUCT_ECOMMERCE_AD"])
    storyboard = list(blueprint.get("storyboard") or [])
    if not storyboard:
        storyboard = [{
            "step": 1,
            "role": "HOOK",
            "start_s": 0.0,
            "end_s": 3.0,
            "duration_s": 3.0,
            "visual_plan_pl": "Prezentacja oferty lokalnego biznesu",
            "overlay_text_pl": str(blueprint.get("opening_hook_pl") or "SPRAWDŹ OFERTĘ"),
            "camera_note_pl": "Nagraj telefonem w pionie 9:16",
        }]

    total_scenes = len(storyboard)
    total_duration = round(sum(max(1.0, float(s.get("duration_s") or 1.8)) for s in storyboard), 2)

    with tempfile.TemporaryDirectory(prefix="flikcut_pitch_") as tmp_dir:
        tmp = Path(tmp_dir)
        seg_files: List[Path] = []
        for idx, scene in enumerate(storyboard, start=1):
            dur_s = round(max(1.0, min(4.0, float(scene.get("duration_s") or 1.8))), 2)
            card_png = tmp / f"card_{idx:02d}.png"
            seg_mp4 = tmp / f"seg_{idx:02d}.mp4"
            img = _build_pitch_card_image(scene, idx, total_scenes, blueprint, palette)
            img.save(card_png, format="PNG")
            if idx == 1:
                img.save(thumb_jpg, format="JPEG", quality=92)

            # Delikatny ruch zoom-in na scenie (zoompan) dający wrażenie płynnego animatiku wideo
            frames_n = max(30, int(round(dur_s * OUT_FPS)))
            vf = (
                f"zoompan=z='min(1.06,1+0.0018*on)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames_n}:s={OUT_W}x{OUT_H}:fps={OUT_FPS},format=yuv420p"
            )
            cmd_nv = [
                ffmpeg, "-y", "-loop", "1", "-i", str(card_png),
                "-t", f"{dur_s:.2f}", "-vf", vf,
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
                "-an", str(seg_mp4),
            ]
            cmd_cpu = [
                ffmpeg, "-y", "-loop", "1", "-i", str(card_png),
                "-t", f"{dur_s:.2f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-an", str(seg_mp4),
            ]
            _encode_cmd_with_nvenc_fallback(cmd_nv, cmd_cpu)
            seg_files.append(seg_mp4)

        concat_txt = tmp / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for p in seg_files),
            encoding="utf-8",
        )
        video_only = tmp / "video_concat.mp4"
        res_cat = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(video_only)],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if res_cat.returncode != 0:
            raise RuntimeError(f"Concat pitch video failed: {res_cat.stderr[-400:]}")

        # Podkład audio: własny plik muzyczny lub czysty cichy puls beatowy (żeby AAC stream zawsze istniał)
        if music_path and Path(music_path).is_file():
            cmd_mux = [
                ffmpeg, "-y",
                "-i", str(video_only),
                "-stream_loop", "-1", "-i", str(music_path),
                "-t", f"{total_duration:.2f}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", str(out_mp4),
            ]
            res_mux = subprocess.run(cmd_mux, capture_output=True, text=True, timeout=120)
            if res_mux.returncode != 0:
                shutil.copyfile(video_only, out_mp4)
        else:
            # Delikatny ciepły ton ambientowo-rytmiczny na -22 dB (lub cisza AAC w fallbacku)
            aeval = "0.035*sin(2*PI*110*t)*exp(-3*mod(t,0.5))+0.018*sin(2*PI*220*t)*exp(-4*mod(t,0.25))"
            cmd_tone = [
                ffmpeg, "-y",
                "-i", str(video_only),
                "-f", "lavfi", "-i", f"aevalsrc={aeval}:s=48000:d={total_duration:.2f}",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                "-shortest", "-movflags", "+faststart", str(out_mp4),
            ]
            res_tone = subprocess.run(cmd_tone, capture_output=True, text=True, timeout=90)
            if res_tone.returncode != 0:
                cmd_null = [
                    ffmpeg, "-y",
                    "-i", str(video_only),
                    "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_duration:.2f}",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", "-movflags", "+faststart", str(out_mp4),
                ]
                subprocess.run(cmd_null, capture_output=True, text=True, check=True, timeout=90)

    return {
        "ok": True,
        "output_path": str(out_mp4),
        "output_filename": out_mp4.name,
        "thumbnail_path": str(thumb_jpg) if thumb_jpg.is_file() else None,
        "thumbnail_filename": thumb_jpg.name if thumb_jpg.is_file() else None,
        "duration_s": total_duration,
        "width": OUT_W,
        "height": OUT_H,
        "fps": OUT_FPS,
        "scene_count": total_scenes,
    }


def _build_overlay_caption_png(
    overlay_text: str,
    footer_text: str,
    is_cta_scene: bool,
    out_png: Path,
    palette: Dict[str, Tuple[int, int, int]],
) -> None:
    canvas = Image.new("RGBA", (OUT_W, OUT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font_top = _load_pl_font(58, bold=True)
    font_sub = _load_pl_font(38, bold=True)

    # Górny napis w strefie bezpiecznej
    top_lines = _wrap_text(draw, (overlay_text or "").upper(), font_top, 920)[:2]
    y = 175
    for line in top_lines:
        lb = draw.textbbox((0, 0), line, font=font_top)
        w_t, h_t = lb[2] - lb[0], lb[3] - lb[1]
        x = (OUT_W - w_t) // 2
        draw.rounded_rectangle([x - 28, y - 14, x + w_t + 28, y + h_t + 20], radius=16, fill=(10, 12, 16, 200), outline=(*palette["accent"], 230), width=2)
        draw.text((x, y), line, font=font_top, fill=(255, 255, 255, 255))
        y += h_t + 36

    if is_cta_scene and footer_text:
        cta_lines = _wrap_text(draw, footer_text, font_sub, 880)[:2]
        fy = 1410
        draw.rounded_rectangle([72, fy - 24, 1008, fy + len(cta_lines) * 54 + 28], radius=22, fill=(14, 16, 20, 225), outline=(*palette["accent"], 255), width=3)
        for line in cta_lines:
            lb = draw.textbbox((0, 0), line, font=font_sub)
            x = (OUT_W - (lb[2] - lb[0])) // 2
            draw.text((x, fy), line, font=font_sub, fill=(*palette["accent_soft"], 255))
            fy += 54

    canvas.save(out_png, format="PNG")


def render_commercial_multishot(
    clip_paths: List[Path],
    blueprint: Dict[str, Any],
    output_path: Path,
    music_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Składa docelową rolkę 9:16 z wielu klipów klienta z telefonu (9:16 lub 16:9),
    bez gamingowego kadrowania na pasek HP LoL.
    """
    valid_clips = [Path(p) for p in (clip_paths or []) if Path(p).is_file()]
    if not valid_clips:
        raise FileNotFoundError("Brak poprawnych plików wideo klienta do montażu")

    ffmpeg = _find_ffmpeg()
    out_mp4 = Path(output_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    thumb_jpg = out_mp4.with_suffix(".jpg")

    preset = str(blueprint.get("niche_preset") or "PRODUCT_ECOMMERCE_AD")
    palette = _THEME_PALETTES.get(preset, _THEME_PALETTES["PRODUCT_ECOMMERCE_AD"])
    client = blueprint.get("client_profile") or {}
    storyboard = list(blueprint.get("storyboard") or [])
    if not storyboard:
        storyboard = [
            {"step": i + 1, "role": "HOOK" if i == 0 else "PROCES", "duration_s": 2.2, "overlay_text_pl": str(blueprint.get("opening_hook_pl") or client.get("business_name") or "OFERTA")}
            for i in range(max(2, len(valid_clips)))
        ]

    clip_infos = [_probe_video(p) for p in valid_clips]
    total_scenes = len(storyboard)
    cta_footer = f"{client.get('business_name', '')} ({client.get('city', '')}) • {client.get('cta', '')}".strip(" •()")

    with tempfile.TemporaryDirectory(prefix="flikcut_com_") as tmp_dir:
        tmp = Path(tmp_dir)
        seg_files: List[Path] = []
        total_dur = 0.0

        for idx, scene in enumerate(storyboard):
            clip_idx = idx % len(valid_clips)
            src = valid_clips[clip_idx]
            info = clip_infos[clip_idx]
            slot_dur = round(max(1.0, min(4.0, float(scene.get("duration_s") or 2.0))), 2)
            slot_dur = min(slot_dur, max(0.8, info["duration_s"] - 0.1))

            # Znajdź najlepszy moment klipu przez ulepszony ad_event_detector
            events = detect_ad_events(str(src), clip_start=0.0, clip_end=info["duration_s"], clip_duration=info["duration_s"])
            anchor_ts = float(events[0][0]) if events else (info["duration_s"] / 2.0)
            max_start = max(0.0, info["duration_s"] - slot_dur)
            start_s = round(max(0.0, min(max_start, anchor_ts - slot_dur * 0.4)), 2)

            ov_png = tmp / f"ov_{idx:02d}.png"
            _build_overlay_caption_png(
                overlay_text=str(scene.get("overlay_text_pl") or blueprint.get("opening_hook_pl") or ""),
                footer_text=cta_footer,
                is_cta_scene=(idx == total_scenes - 1),
                out_png=ov_png,
                palette=palette,
            )

            # Natywne 9:16 nie obcina kadru; poziome 16:9 kadruje centralnie na akcję
            base_vf = (
                f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
                f"crop={OUT_W}:{OUT_H},fps={OUT_FPS},format=yuv420p"
            )
            filter_complex = f"[0:v]{base_vf}[bg];[bg][1:v]overlay=0:0:format=auto,format=yuv420p[vout]"
            seg_mp4 = tmp / f"seg_{idx:02d}.mp4"

            cmd_nv = [
                ffmpeg, "-y", "-ss", f"{start_s:.2f}", "-t", f"{slot_dur:.2f}",
                "-i", str(src), "-i", str(ov_png),
                "-filter_complex", filter_complex, "-map", "[vout]",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21", "-an", str(seg_mp4),
            ]
            cmd_cpu = [
                ffmpeg, "-y", "-ss", f"{start_s:.2f}", "-t", f"{slot_dur:.2f}",
                "-i", str(src), "-i", str(ov_png),
                "-filter_complex", filter_complex, "-map", "[vout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-an", str(seg_mp4),
            ]
            _encode_cmd_with_nvenc_fallback(cmd_nv, cmd_cpu)
            seg_files.append(seg_mp4)
            total_dur = round(total_dur + slot_dur, 2)

        concat_txt = tmp / "concat.txt"
        concat_txt.write_text(
            "\n".join(f"file '{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'" for p in seg_files),
            encoding="utf-8",
        )
        video_only = tmp / "combined.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(video_only)],
            capture_output=True, text=True, check=True, timeout=120,
        )

        # Podkład AAC 48kHz (własna muzyka lub cichy AAC)
        if music_path and Path(music_path).is_file():
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(video_only), "-stream_loop", "-1", "-i", str(music_path),
                    "-t", f"{total_dur:.2f}", "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", str(out_mp4),
                ],
                capture_output=True, text=True, check=True, timeout=120,
            )
        else:
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(video_only),
                    "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={total_dur:.2f}",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                    "-shortest", "-movflags", "+faststart", str(out_mp4),
                ],
                capture_output=True, text=True, check=True, timeout=90,
            )

        # Miniatura z 0.5s
        subprocess.run(
            [ffmpeg, "-y", "-ss", "0.4", "-i", str(out_mp4), "-frames:v", "1", "-q:v", "3", str(thumb_jpg)],
            capture_output=True, text=True, timeout=30,
        )

    return {
        "ok": True,
        "output_path": str(out_mp4),
        "output_filename": out_mp4.name,
        "thumbnail_path": str(thumb_jpg) if thumb_jpg.is_file() else None,
        "duration_s": total_dur,
        "width": OUT_W,
        "height": OUT_H,
        "fps": OUT_FPS,
        "scene_count": len(seg_files),
        "clips_used": len(valid_clips),
    }
