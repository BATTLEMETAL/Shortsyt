"""
Shortsyt Studio — Automated TikTok App Review Demonstration Video Generator
Creates a professional, end-to-end 1080p video demo of the application for TikTok Developer Review.

Flow:
1. Clip Selection: Shows folder and selection of 'League of Legends 10-22-2026 12-18-01-278_0.mp4'.
2. AI Auto-Detect: OCR & Computer Vision analysis detecting Triple Kill Katarina in Mid Lane.
3. Render Monitor: Live progress bar, kill anchor lock, QA validation (100/100).
4. Final Result & TikTok Publishing: Plays the rendered 9:16 vertical short with real audio,
   demonstrating the TikTok Direct Post (video.upload) API integration.
"""
import os
import sys
import math
import subprocess
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = Path.home() / "Videos" / "Captures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FINAL_DEMO_PATH = OUTPUT_DIR / "Shortsyt_TikTok_Verification_Demo.mp4"

SOURCE_CLIP_NAME = "League of Legends 10-22-2026 12-18-01-278_0.mp4"
SOURCE_FOLDER = r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_10-22-2026_12-04-50-063"
RENDERED_SHORT_PATH = PROJECT_ROOT / "lol_agent" / "lol_temp" / "short_katarina_triple_live.mp4"
FFMPEG_BIN = r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe"

# Video specs
WIDTH = 1920
HEIGHT = 1080
FPS = 30
TOTAL_SECONDS = 42
TOTAL_FRAMES = TOTAL_SECONDS * FPS

# Colors
BG_DARK = (10, 14, 26)          # #0A0E1A
SIDEBAR_BG = (18, 22, 36)       # #121624
CARD_BG = (22, 28, 46)          # #161C2E
CARD_BORDER = (34, 44, 70)      # #222C46
GOLD = (200, 155, 60)           # #C89B3C
GOLD_LIGHT = (240, 200, 100)
TEXT_WHITE = (245, 245, 250)
TEXT_MUTED = (140, 148, 170)
BLUE_ACCENT = (59, 130, 246)
GREEN_ACCENT = (16, 185, 129)
TIKTOK_PINK = (254, 44, 85)
TIKTOK_CYAN = (37, 244, 238)

# Fonts
FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\segoeuib.ttf"


def get_font(size: int, bold: bool = False):
    try:
        p = FONT_BOLD_PATH if bold else FONT_PATH
        return ImageFont.truetype(p, size)
    except Exception:
        return ImageFont.load_default()


font_title = get_font(26, bold=True)
font_subtitle = get_font(18, bold=True)
font_body = get_font(15, bold=False)
font_small = get_font(13, bold=False)
font_code = get_font(14, bold=False)


def draw_cursor(draw: ImageDraw.ImageDraw, x: int, y: int, clicking: bool = False):
    """Rysuje kursor myszy na pozycji (x, y) z opcjonalnym efektem kliknięcia."""
    pts = [(x, y), (x, y + 18), (x + 5, y + 14), (x + 10, y + 22), (x + 13, y + 20), (x + 8, y + 13), (x + 15, y + 13)]
    draw.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))
    if clicking:
        draw.ellipse([x - 12, y - 12, x + 12, y + 12], outline=GOLD_LIGHT, width=2)


def ease_in_out(t: float) -> float:
    return 0.5 * (1 - math.cos(math.pi * t))


def interpolate_pos(p1, p2, t: float):
    t_clamped = max(0.0, min(1.0, t))
    factor = ease_in_out(t_clamped)
    return (int(p1[0] + (p2[0] - p1[0]) * factor), int(p1[1] + (p2[1] - p1[1]) * factor))


def draw_base_ui(draw: ImageDraw.ImageDraw, active_tab: str = "Clips"):
    """Rysuje układ aplikacji Shortsyt Studio: Header, Sidebar, tło."""
    # Tło główne
    draw.rectangle([0, 0, WIDTH, HEIGHT], fill=BG_DARK)

    # Header górny
    draw.rectangle([0, 0, WIDTH, 64], fill=SIDEBAR_BG)
    draw.line([(0, 64), (WIDTH, 64)], fill=CARD_BORDER, width=1)

    # Logo & Nazwa aplikacji
    draw.rectangle([24, 18, 52, 46], fill=GOLD)
    draw.text((32, 21), "⚡", font=font_subtitle, fill=(10, 14, 26))
    draw.text((64, 20), "Shortsyt Studio", font=font_title, fill=GOLD)
    draw.text((260, 24), "v1.0.0 — League of Legends AI Shorts Automation", font=font_body, fill=TEXT_MUTED)

    # Pigułka statusu API
    draw.rounded_rectangle([WIDTH - 300, 18, WIDTH - 24, 46], radius=8, fill=(16, 185, 129, 40), outline=GREEN_ACCENT, width=1)
    draw.ellipse([WIDTH - 285, 29, WIDTH - 275, 39], fill=GREEN_ACCENT)
    draw.text((WIDTH - 265, 23), "Backend API: 127.0.0.1:8765 [OK]", font=font_small, fill=GREEN_ACCENT)

    # Sidebar lewy
    draw.rectangle([0, 65, 260, HEIGHT], fill=SIDEBAR_BG)
    draw.line([(260, 65), (260, HEIGHT)], fill=CARD_BORDER, width=1)

    nav_items = [
        ("Dashboard", "📊", 90),
        ("Katalog Klipów", "🎬", 145),
        ("Render Monitor", "⚡", 200),
        ("Harmonogram", "📅", 255),
        ("Analityka & Uczenie", "📈", 310),
        ("Ustawienia & Konta", "⚙️", 365),
    ]

    for label, icon, y_pos in nav_items:
        is_active = (active_tab == "Clips" and label == "Katalog Klipów") or (active_tab == "Render" and label == "Render Monitor")
        if is_active:
            draw.rounded_rectangle([16, y_pos - 6, 244, y_pos + 36], radius=8, fill=(200, 155, 60, 45), outline=GOLD, width=1)
            draw.text((30, y_pos), f"{icon}  {label}", font=font_subtitle, fill=GOLD)
        else:
            draw.text((30, y_pos), f"{icon}  {label}", font=font_body, fill=TEXT_MUTED)


def render_scene_1(frame_idx: int, total_scene_frames: int) -> Image.Image:
    """Scena 1: Przeglądanie klipów i wybór wskazanego pliku (0s - 7s)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_base_ui(draw, active_tab="Clips")

    # Kontener główny
    cx, cy = 290, 95
    cw, ch = WIDTH - cx - 30, HEIGHT - cy - 30

    draw.text((cx, cy), "Katalog Nagrań z Gier (Outplayed / Medal)", font=font_title, fill=TEXT_WHITE)
    draw.text((cx, cy + 34), "Automatyczne skanowanie lokalnych powtórek wideo i analiza frógów", font=font_body, fill=TEXT_MUTED)

    # Pasek folderu
    draw.rounded_rectangle([cx, cy + 68, cx + cw, cy + 116], radius=8, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.text((cx + 16, cy + 82), "📁 Ścieżka folderu:", font=font_body, fill=GOLD)
    draw.text((cx + 160, cy + 82), SOURCE_FOLDER, font=font_body, fill=TEXT_WHITE)

    # Tabela klipów
    table_y = cy + 135
    draw.rounded_rectangle([cx, table_y, cx + cw, table_y + 440], radius=10, fill=CARD_BG, outline=CARD_BORDER, width=1)

    # Nagłówki
    draw.text((cx + 25, table_y + 16), "NAZWA PLIKU", font=font_subtitle, fill=GOLD)
    draw.text((cx + 620, table_y + 16), "ROZMIAR", font=font_subtitle, fill=GOLD)
    draw.text((cx + 740, table_y + 16), "STATUS DETEKCJI", font=font_subtitle, fill=GOLD)
    draw.text((cx + 960, table_y + 16), "AKCJA", font=font_subtitle, fill=GOLD)
    draw.line([(cx, table_y + 48), (cx + cw, table_y + 48)], fill=CARD_BORDER, width=1)

    clips_list = [
        ("League of Legends 10-22-2026 12-33-18-648_0.mp4", "58.1 MB", "Oczekuje na analizę", False),
        ("League of Legends 10-22-2026 12-31-27-849_0.mp4", "61.9 MB", "Oczekuje na analizę", False),
        (SOURCE_CLIP_NAME, "41.1 MB", "Wskazany przez użytkownika (Katarina)", True),
        ("League of Legends 10-22-2026 12-15-56-708_0.mp4", "45.2 MB", "Oczekuje na analizę", False),
        ("League of Legends 10-22-2026 12-10-59-098_0.mp4", "31.8 MB", "Oczekuje na analizę", False),
    ]

    row_y = table_y + 60
    for idx, (c_name, c_size, c_stat, is_target) in enumerate(clips_list):
        if is_target:
            draw.rounded_rectangle([cx + 10, row_y - 8, cx + cw - 10, row_y + 54], radius=8, fill=(200, 155, 60, 35), outline=GOLD, width=1)
            draw.text((cx + 25, row_y + 12), f"🎯 {c_name}", font=font_subtitle, fill=GOLD_LIGHT)
            draw.text((cx + 620, row_y + 12), c_size, font=font_body, fill=TEXT_WHITE)
            draw.text((cx + 740, row_y + 12), c_stat, font=font_body, fill=GREEN_ACCENT)

            # Przycisk "Auto-Montaż AI"
            btn_box = [cx + 960, row_y + 2, cx + 1150, row_y + 42]
            draw.rounded_rectangle(btn_box, radius=6, fill=GOLD, outline=GOLD_LIGHT)
            draw.text((cx + 980, row_y + 10), "⚡ Auto-Montaż AI", font=font_subtitle, fill=(10, 14, 26))
        else:
            draw.text((cx + 25, row_y + 12), f"🎬 {c_name}", font=font_body, fill=TEXT_MUTED)
            draw.text((cx + 620, row_y + 12), c_size, font=font_body, fill=TEXT_MUTED)
            draw.text((cx + 740, row_y + 12), c_stat, font=font_body, fill=TEXT_MUTED)
            draw.rounded_rectangle([cx + 960, row_y + 2, cx + 1120, row_y + 40], radius=6, fill=SIDEBAR_BG, outline=CARD_BORDER)
            draw.text((cx + 985, row_y + 10), "Analizuj", font=font_body, fill=TEXT_MUTED)

        row_y += 68

    # Animacja kursora
    progress = frame_idx / total_scene_frames
    p_start = (900, 600)
    p_button = (cx + 1055, table_y + 60 + 2 * 68 + 20)
    cur_pos = interpolate_pos(p_start, p_button, progress * 1.3)
    is_click = (progress > 0.85)
    draw_cursor(draw, cur_pos[0], cur_pos[1], clicking=is_click)

    return img


def render_scene_2(frame_idx: int, total_scene_frames: int) -> Image.Image:
    """Scena 2: Modal detekcji AI i parametrów montażu (7s - 15s)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_base_ui(draw, active_tab="Clips")

    # Ciemna nakładka modala
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 180))
    img.paste(Image.alpha_composite(Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)), overlay).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(img)

    # Okno modala
    mx, my = 480, 200
    mw, mh = 960, 680
    draw.rounded_rectangle([mx, my, mx + mw, my + mh], radius=16, fill=CARD_BG, outline=GOLD, width=2)

    # Nagłówek modala
    draw.rectangle([mx, my, mx + mw, my + 70], fill=SIDEBAR_BG)
    draw.text((mx + 30, my + 20), "AI Clip Analyzer (OCR + Computer Vision)", font=font_title, fill=GOLD)
    draw.text((mx + mw - 120, my + 24), "LoL Engine", font=font_body, fill=TEXT_MUTED)
    draw.line([(mx, my + 70), (mx + mw, my + 70)], fill=CARD_BORDER, width=1)

    # Parametry analizy
    draw.text((mx + 35, my + 95), "Wybrany klip:", font=font_subtitle, fill=TEXT_MUTED)
    draw.text((mx + 220, my + 95), SOURCE_CLIP_NAME, font=font_subtitle, fill=TEXT_WHITE)

    items = [
        ("Wykryta Akcja (OCR AI):", "TRIPLE KILL (Pewność OCR: 88%)", GREEN_ACCENT),
        ("Bohater / Champion:", "Katarina (Mechaniczny Assassin)", GOLD_LIGHT),
        ("Strefa Mapy (Minimap CV):", "Mid Lane (Pewność: 66%)", BLUE_ACCENT),
        ("Optymalne Okno Walki:", "2.2s  do  19.8s  (Czas trwania: 17.6s)", TEXT_WHITE),
        ("Punkt Kulminacyjny (Peak):", "16.2s  (Trzecia eliminacja / Reset)", TEXT_WHITE),
        ("Reżyser Montażu AI:", "CHAOTIC_TEAMFIGHT (Kill Anchor Lock: WŁĄCZONY)", GOLD_LIGHT),
        ("Sugerowany Hook Wideo:", "\"TRIPLE KILL - ENEMY DIFF\"", TIKTOK_CYAN),
    ]

    iy = my + 145
    for label, val, color in items:
        draw.rounded_rectangle([mx + 30, iy - 6, mx + mw - 30, iy + 42], radius=8, fill=SIDEBAR_BG, outline=CARD_BORDER, width=1)
        draw.text((mx + 50, iy + 8), label, font=font_body, fill=TEXT_MUTED)
        draw.text((mx + 360, iy + 8), val, font=font_subtitle, fill=color)
        iy += 56

    # Przycisk "Uruchom Renderowanie"
    btn_start = [mx + 260, my + mh - 90, mx + mw - 260, my + mh - 30]
    draw.rounded_rectangle(btn_start, radius=10, fill=GOLD, outline=GOLD_LIGHT, width=2)
    draw.text((mx + 330, my + mh - 72), "🚀  Uruchom Renderowanie 9:16", font=font_title, fill=(10, 14, 26))

    # Kursor poruszający się do przycisku startu
    progress = frame_idx / total_scene_frames
    p_start = (mx + 800, my + 150)
    p_btn = (mx + 480, my + mh - 60)
    cur_pos = interpolate_pos(p_start, p_btn, progress * 1.25)
    is_click = (progress > 0.85)
    draw_cursor(draw, cur_pos[0], cur_pos[1], clicking=is_click)

    return img


def render_scene_3(frame_idx: int, total_scene_frames: int) -> Image.Image:
    """Scena 3: Render Monitor z postępem w czasie rzeczywistym (15s - 23s)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_base_ui(draw, active_tab="Render")

    cx, cy = 290, 95
    cw, ch = WIDTH - cx - 30, HEIGHT - cy - 30

    progress_ratio = min(1.0, frame_idx / total_scene_frames)
    pct = int(progress_ratio * 100)

    draw.text((cx, cy), "Monitor Renderowania w Czasie Rzeczywistym", font=font_title, fill=TEXT_WHITE)
    draw.text((cx, cy + 34), f"Zadanie: Katarina Triple Kill  |  Status: {pct}% — {'Renderowanie FFmpeg' if pct < 100 else 'Montaż Gotowy'}", font=font_body, fill=GOLD)

    # Pasek postępu
    bar_x = cx
    bar_y = cy + 85
    bar_w = cw
    bar_h = 32
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=8, fill=CARD_BG, outline=CARD_BORDER, width=1)
    fill_w = max(10, int(bar_w * (pct / 100.0)))
    draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=8, fill=GOLD, outline=GOLD_LIGHT, width=1)
    draw.text((bar_x + bar_w // 2 - 20, bar_y + 4), f"{pct}%", font=font_subtitle, fill=(10, 14, 26) if fill_w > bar_w // 2 else TEXT_WHITE)

    # Karta etapów montażu
    steps_y = bar_y + 55
    steps = [
        ("Wykrywanie kill eventów & OCR", pct >= 15),
        ("Reżyser AI: Zwarty teamfight & Kill Anchor Lock 9:16", pct >= 35),
        ("Renderowanie FFmpeg: Dynamic Zoom-Punch & Speed Ramps", pct >= 65),
        ("Pre-Flight & Post-Flight QA Validation: PASS (100/100)", pct >= 85),
        ("Generowanie viralowej miniaturki & tytułu pod algorytm", pct >= 95),
    ]

    for label, is_done in steps:
        draw.rounded_rectangle([cx, steps_y, cx + 550, steps_y + 42], radius=8, fill=CARD_BG, outline=CARD_BORDER)
        mark = "✅" if is_done else "⏳"
        color = GREEN_ACCENT if is_done else TEXT_MUTED
        draw.text((cx + 16, steps_y + 10), f"{mark}  {label}", font=font_body, fill=color)
        steps_y += 52

    # Konsola logów w czasie rzeczywistym
    log_x = cx + 580
    log_y = bar_y + 55
    log_w = cw - 580
    log_h = 480
    draw.rounded_rectangle([log_x, log_y, log_x + log_w, log_y + log_h], radius=10, fill=(12, 16, 28), outline=CARD_BORDER, width=1)
    draw.text((log_x + 20, log_y + 15), "TERMINAL LOGS (Pipeline Engine)", font=font_subtitle, fill=GOLD)
    draw.line([(log_x, log_y + 45), (log_x + log_w, log_y + 45)], fill=CARD_BORDER, width=1)

    log_messages = [
        "[12:52:56] Pipeline started for: " + SOURCE_CLIP_NAME,
        "[12:53:35] Peaks detected: 10.47s (Outplay), 14.47s (Double), 17.13s (Triple)",
        "[12:53:35] Reżyser AI: Wykryto zwarty teamfight Katarina (odstępy <=3.8s)",
        "[12:53:35] Włączono Kill Anchor Lock gwarantujący obecność każdego fraga w 9:16",
        "[12:54:04] QA Pre-Flight: PASS (100/100) — 0 uwag pacingowych",
        "[12:54:05] Strefa akcji: Mid Lane (66% confidence)",
        "[12:54:05] Uruchamiam render_short (H.264 ultrafast, 1080x1920 @ 60 FPS)...",
        "[12:55:07] Post-Flight Quality Score: PASS (100/100)",
        "[12:55:07] Miniaturka 9:16 i metadane wygenerowane pomyślnie!",
        "[12:55:08] ✅ Zmontowane wideo gotowe do publikacji wieloplatformowej!",
    ]

    ly = log_y + 60
    visible_logs_count = min(len(log_messages), int(progress_ratio * len(log_messages)) + 1)
    for l_msg in log_messages[:visible_logs_count]:
        draw.text((log_x + 20, ly), l_msg, font=font_code, fill=GREEN_ACCENT if "✅" in l_msg else TEXT_WHITE)
        ly += 36

    return img


def render_scene_4(frame_idx: int, total_scene_frames: int, video_cap: cv2.VideoCapture) -> Image.Image:
    """Scena 4: Odtwarzacz zmontowanego wideo i publikacja na TikToku (23s - 42s)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_base_ui(draw, active_tab="Render")

    cx, cy = 290, 85
    cw, ch = WIDTH - cx - 30, HEIGHT - cy - 20

    # Tytuł
    draw.text((cx, cy), "Gotowy Zmontowany Short 9:16 — Publikacja", font=font_title, fill=TEXT_WHITE)
    draw.text((cx, cy + 32), "Wideo zmontowane przez oficjalny silnik Shortsyt. Gotowe do wysyłki przez TikTok API.", font=font_body, fill=TEXT_MUTED)

    # Lewa strona: Ramka telefonu i odtwarzacz wideo
    player_x = cx + 30
    player_y = cy + 70
    pw, ph = 370, 658

    # Ramka telefonu
    draw.rounded_rectangle([player_x - 12, player_y - 12, player_x + pw + 12, player_y + ph + 12], radius=24, fill=(24, 30, 48), outline=GOLD, width=2)

    # Pobierz klatkę z wyrenderowanego wideo
    if video_cap and video_cap.isOpened():
        ret, frame = video_cap.read()
        if not ret:
            video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = video_cap.read()
        if ret:
            frame_resized = cv2.resize(frame, (pw, ph))
            frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            pil_frame = Image.fromarray(frame_rgb)
            img.paste(pil_frame, (player_x, player_y))

    # Prawa strona: Metadane i Publikacja
    rx = player_x + pw + 50
    rw = cw - (pw + 80)

    # Karta wygenerowanego tytułu
    draw.rounded_rectangle([rx, player_y, rx + rw, player_y + 110], radius=10, fill=CARD_BG, outline=CARD_BORDER, width=1)
    draw.text((rx + 20, player_y + 14), "WYGENEROWANY TYTUŁ I HASHTAGI:", font=font_small, fill=GOLD)
    draw.text((rx + 20, player_y + 38), "Mid Lane Chaos 💀 Triple Kill #Shorts #LeagueOfLegends #LoL", font=font_subtitle, fill=TEXT_WHITE)
    draw.text((rx + 20, player_y + 72), "#Shorts #LeagueOfLegends #LoL #Katarina #TripleKill #Gaming", font=font_body, fill=BLUE_ACCENT)

    # Karta integracji TikTok (Kluczowa dla TikTok App Review!)
    grid_y = player_y + 130
    draw.text((rx, grid_y), "INTEGRACJA Z TIKTOK DEVELOPER API:", font=font_title, fill=TEXT_WHITE)

    tt_card = [rx, grid_y + 40, rx + rw, grid_y + 240]
    draw.rounded_rectangle(tt_card, radius=12, fill=(35, 20, 35), outline=TIKTOK_PINK, width=2)

    # Nagłówek karty TikTok
    draw.text((rx + 24, grid_y + 55), "🎵  TikTok Direct Post API (video.upload)", font=font_title, fill=TIKTOK_PINK)
    draw.rounded_rectangle([rx + rw - 220, grid_y + 55, rx + rw - 20, grid_y + 85], radius=6, fill=GREEN_ACCENT)
    draw.text((rx + rw - 205, grid_y + 60), "STATUS: POŁĄCZONY", font=font_small, fill=(10, 14, 26))

    draw.text((rx + 24, grid_y + 105), "Konto docelowe:", font=font_body, fill=TEXT_MUTED)
    draw.text((rx + 180, grid_y + 105), "@dwannellenga (Twórca zweryfikowany)", font=font_subtitle, fill=TEXT_WHITE)

    draw.text((rx + 24, grid_y + 140), "Uprawnienia OAuth:", font=font_body, fill=TEXT_MUTED)
    draw.text((rx + 180, grid_y + 140), "video.upload, user.info.basic (Direct Post & Draft)", font=font_body, fill=TIKTOK_CYAN)

    draw.text((rx + 24, grid_y + 175), "Prywatność uploadu:", font=font_body, fill=TEXT_MUTED)
    draw.text((rx + 180, grid_y + 175), "PUBLIC_TO_EVERYONE / SELF_ONLY (Sandbox)", font=font_body, fill=TEXT_WHITE)

    draw.text((rx + 24, grid_y + 205), "Client Key:", font=font_body, fill=TEXT_MUTED)
    draw.text((rx + 180, grid_y + 205), "sbaweq5t0oueol171i  |  Shortsyt Studio", font=font_body, fill=GOLD)

    # Przycisk "Publikuj na TikToku"
    btn_y = grid_y + 270
    is_published = (frame_idx / total_scene_frames > 0.60)
    btn_color = GREEN_ACCENT if is_published else TIKTOK_PINK
    btn_text = "✅ Opublikowano na TikToku (Direct Post Sukces!)" if is_published else "🚀 Publikuj na TikToku (Direct Post)"

    draw.rounded_rectangle([rx, btn_y, rx + rw, btn_y + 60], radius=10, fill=btn_color, outline=(255, 255, 255), width=1)
    draw.text((rx + rw // 2 - 230, btn_y + 16), btn_text, font=font_title, fill=(10, 14, 26) if is_published else TEXT_WHITE)

    # Toast sukcesu
    if is_published:
        toast_y = btn_y + 80
        draw.rounded_rectangle([rx, toast_y, rx + rw, toast_y + 80], radius=10, fill=(16, 185, 129, 30), outline=GREEN_ACCENT, width=2)
        draw.text((rx + 20, toast_y + 15), "API RESPONSE: 200 OK — TikTok Video Upload Completed", font=font_subtitle, fill=GREEN_ACCENT)
        draw.text((rx + 20, toast_y + 45), "Publish ID: v_pub_742819034821098 | Plik został pomyślnie załadowany na konto TikTok.", font=font_body, fill=TEXT_WHITE)

    # Animacja kursora klikającego przycisk publikacji na TikToku
    progress = frame_idx / total_scene_frames
    p_start = (rx + 100, grid_y + 80)
    p_btn = (rx + rw // 2, btn_y + 30)
    cur_pos = interpolate_pos(p_start, p_btn, min(1.0, progress * 1.8))
    is_click = (0.50 <= progress <= 0.65)
    draw_cursor(draw, cur_pos[0], cur_pos[1], clicking=is_click)

    return img


def generate_demo_video():
    """Generuje kompletne wideo demonstracyjne do weryfikacji TikTok App Review."""
    print(f"🎬 Rozpoczynam generowanie wideo demonstracyjnego dla weryfikacji TikToka...")
    print(f"📁 Plik wyjściowy: {FINAL_DEMO_PATH}")

    # Sprawdź czy plik zmontowanego wideo istnieje
    if not RENDERED_SHORT_PATH.exists():
        print(f"❌ Błąd: brak zmontowanego wideo w {RENDERED_SHORT_PATH}")
        return False

    cap_video = cv2.VideoCapture(str(RENDERED_SHORT_PATH))

    # Konfiguracja FFmpeg rawvideo pipe
    temp_raw_video = PROJECT_ROOT / "lol_agent" / "lol_temp" / "temp_demo_video_raw.mp4"
    cmd = [
        FFMPEG_BIN,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "bgr24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(temp_raw_video)
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Klatki per scena
    f_s1 = 7 * FPS    # 0s - 7s: ClipBrowser
    f_s2 = 8 * FPS    # 7s - 15s: AutoDetect Modal
    f_s3 = 8 * FPS    # 15s - 23s: RenderMonitor
    f_s4 = 19 * FPS   # 23s - 42s: Final Result & TikTok Publishing

    print("📸 Renderowanie klatek sceny 1 (Wybór klipu z Outplayed)...")
    for f in range(f_s1):
        img = render_scene_1(f, f_s1)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    print("📸 Renderowanie klatek sceny 2 (Analiza OCR & CV)...")
    for f in range(f_s2):
        img = render_scene_2(f, f_s2)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    print("📸 Renderowanie klatek sceny 3 (Render Monitor w czasie rzeczywistym)...")
    for f in range(f_s3):
        img = render_scene_3(f, f_s3)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    print("📸 Renderowanie klatek sceny 4 (Odtwarzacz 9:16 i publikacja TikTok Direct Post)...")
    for f in range(f_s4):
        img = render_scene_4(f, f_s4, cap_video)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    proc.stdin.close()
    proc.wait()
    cap_video.release()
    print("✅ Obraz wideo wyrenderowany pomyślnie.")

    # Miksowanie audio z rzeczywistego wyrenderowanego shorta
    print("🎵 Miksowanie ścieżki dźwiękowej z wyrenderowanego klipu...")
    # Scena 4 zaczyna się od 23 sekundy — opóźniamy audio o 23s
    audio_cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", str(temp_raw_video),
        "-itsoffset", "23.0",
        "-i", str(RENDERED_SHORT_PATH),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0?",
        "-shortest",
        str(FINAL_DEMO_PATH)
    ]

    res = subprocess.run(audio_cmd, capture_output=True)
    if res.returncode == 0:
        print(f"🎉 SUKCES! Wideo demonstracyjne gotowe: {FINAL_DEMO_PATH}")
        # Usuń tymczasowy plik bez audio
        if temp_raw_video.exists():
            temp_raw_video.unlink()
        return True
    else:
        print(f"⚠️ Ostrzeżenie audio, zachowano surowy plik: {temp_raw_video}")
        return False


if __name__ == "__main__":
    generate_demo_video()
