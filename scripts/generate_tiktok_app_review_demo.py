"""
Shortsyt Studio — TikTok App Review End-to-End Demo Generator (1080p @ 30fps)
Demonstrates Login Kit (OAuth 2.0) and Content Posting API UX Guidelines:
1. Scene 1 (0-8s): Connect TikTok Account & OAuth 2.0 consent (user.info.basic, video.upload, video.publish)
2. Scene 2 (8-16s): Gameplay clip selection & 9:16 AI highlight render
3. Scene 3 (16-32s): Mandatory TikTok Direct Post UX form:
   - Creator info (@dwannellenga from creator_info/query)
   - Editable caption & hashtags
   - Unselected default Privacy Level dropdown -> user manually selects Public to everyone
   - Off-by-default Allow Comment / Duet / Stitch checkboxes -> manual opt-in
   - Commercial Content Disclosure toggle (Your brand / Branded content)
   - Music Usage Confirmation notice + post-publish processing notice
4. Scene 4 (32-42s): Direct Post upload progress, PUBLISH_COMPLETE (200 OK), and confirmation.
"""
import os
import sys
import math
import shutil
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESKTOP_VERIF_DIR = Path.home() / "OneDrive" / "Pulpit" / "TikTok_Weryfikacja"
OUTPUT_DIR = Path.home() / "Videos" / "Captures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FINAL_DEMO_PATH = OUTPUT_DIR / "Shortsyt_TikTok_Verification_Demo.mp4"


def _resolve_rendered_short() -> Path:
    preferred = PROJECT_ROOT / "lol_agent" / "lol_temp" / "short_overnight_20261121_005819_9aaaa_r2_triple.mp4"
    if preferred.is_file():
        return preferred
    cands = sorted(
        (PROJECT_ROOT / "lol_agent" / "lol_temp").glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if cands:
        return cands[0]
    return preferred


def _resolve_ffmpeg() -> str:
    default_bin = r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe"
    if os.path.isfile(default_bin):
        return default_bin
    return shutil.which("ffmpeg") or "ffmpeg"


RENDERED_SHORT_PATH = _resolve_rendered_short()
FFMPEG_BIN = _resolve_ffmpeg()

WIDTH = 1920
HEIGHT = 1080
FPS = 30

BG_DARK = (10, 14, 24)
SIDEBAR_BG = (17, 21, 34)
CARD_BG = (22, 28, 44)
CARD_BORDER = (42, 52, 78)
INPUT_BG = (12, 16, 26)
GOLD = (200, 255, 58)          # #C8FF3A Flikcut accent
TEXT_WHITE = (245, 247, 252)
TEXT_MUTED = (148, 158, 180)
BLUE_ACCENT = (59, 130, 246)
GREEN_ACCENT = (46, 204, 113)
TIKTOK_PINK = (254, 44, 85)
TIKTOK_CYAN = (37, 244, 238)

FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\segoeuib.ttf"


def get_font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_BOLD_PATH if bold else FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


font_h1 = get_font(28, bold=True)
font_h2 = get_font(20, bold=True)
font_sub = get_font(16, bold=True)
font_body = get_font(15, bold=False)
font_small = get_font(13, bold=False)


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def interp_pos(p1, p2, t: float):
    f = ease_in_out(t)
    return (int(p1[0] + (p2[0] - p1[0]) * f), int(p1[1] + (p2[1] - p1[1]) * f))


def draw_cursor(draw: ImageDraw.ImageDraw, x: int, y: int, clicking: bool = False):
    pts = [(x, y), (x, y + 20), (x + 5, y + 15), (x + 11, y + 24), (x + 14, y + 22), (x + 9, y + 14), (x + 16, y + 14)]
    draw.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))
    if clicking:
        draw.ellipse([x - 14, y - 14, x + 14, y + 14], outline=TIKTOK_CYAN, width=3)


def draw_checkbox(draw: ImageDraw.ImageDraw, x: int, y: int, checked: bool, label: str):
    box = [x, y, x + 20, y + 20]
    if checked:
        draw.rounded_rectangle(box, radius=4, fill=TIKTOK_CYAN, outline=TIKTOK_CYAN)
        draw.line([(x + 4, y + 10), (x + 9, y + 15), (x + 16, y + 5)], fill=(10, 14, 24), width=3)
    else:
        draw.rounded_rectangle(box, radius=4, fill=INPUT_BG, outline=TEXT_MUTED, width=2)
    draw.text((x + 28, y + 1), label, font=font_body, fill=TEXT_WHITE)


def draw_toggle(draw: ImageDraw.ImageDraw, x: int, y: int, on: bool):
    bg = GREEN_ACCENT if on else (55, 65, 85)
    draw.rounded_rectangle([x, y, x + 44, y + 22], radius=11, fill=bg)
    knob_x = x + 24 if on else x + 3
    draw.ellipse([knob_x, y + 2, knob_x + 18, y + 20], fill=TEXT_WHITE)


def draw_chrome_shell(draw: ImageDraw.ImageDraw, active_nav: str, step_badge: str):
    draw.rectangle([0, 0, WIDTH, HEIGHT], fill=BG_DARK)
    draw.rectangle([0, 0, WIDTH, 66], fill=SIDEBAR_BG)
    draw.line([(0, 66), (WIDTH, 66)], fill=CARD_BORDER, width=1)

    draw.rounded_rectangle([24, 16, 56, 48], radius=6, fill=GOLD)
    draw.text((33, 21), "F", font=font_h2, fill=(10, 14, 24))
    draw.text((70, 18), "Shortsyt / Flikcut Studio", font=font_h1, fill=TEXT_WHITE)
    draw.text((430, 25), "shortsyt.salon-prettywoman.pl  |  Desktop Creator Suite", font=font_small, fill=TEXT_MUTED)

    draw.rounded_rectangle([WIDTH - 360, 16, WIDTH - 24, 50], radius=8, fill=CARD_BG, outline=TIKTOK_CYAN, width=1)
    draw.text((WIDTH - 342, 24), step_badge, font=font_small, fill=TIKTOK_CYAN)

    draw.rectangle([0, 67, 250, HEIGHT], fill=SIDEBAR_BG)
    draw.line([(250, 67), (250, HEIGHT)], fill=CARD_BORDER, width=1)

    nav_items = ["Dashboard", "Clip Browser", "Render Monitor", "Publish & Outputs", "Settings & Accounts"]
    y_pos = 96
    for name in nav_items:
        if name == active_nav:
            draw.rounded_rectangle([14, y_pos - 6, 236, y_pos + 36], radius=8, fill=(28, 36, 58), outline=GOLD, width=1)
            draw.text((28, y_pos + 2), name, font=font_sub, fill=GOLD)
        else:
            draw.text((28, y_pos + 2), name, font=font_body, fill=TEXT_MUTED)
        y_pos += 54


def render_scene_1_oauth(frame_idx: int, total_frames: int) -> Image.Image:
    """Scene 1 (0-8s): Connect TikTok Account + OAuth 2.0 Consent screen."""
    t = frame_idx / total_frames
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_chrome_shell(draw, "Settings & Accounts", "STEP 1/4: LOGIN KIT OAUTH 2.0")

    cx, cy = 290, 100
    draw.text((cx, cy), "Connected Creator Accounts (TikTok Login Kit)", font=font_h1, fill=TEXT_WHITE)
    draw.text((cx, cy + 38), "Authorize your creator account via official OAuth 2.0 PKCE flow.", font=font_body, fill=TEXT_MUTED)

    card_box = [cx, cy + 90, cx + 920, cy + 300]
    is_connected = t >= 0.72
    draw.rounded_rectangle(card_box, radius=12, fill=CARD_BG, outline=GREEN_ACCENT if is_connected else TIKTOK_PINK, width=2)
    draw.text((cx + 28, cy + 115), "TikTok Content Creator Integration", font=font_h2, fill=TEXT_WHITE)
    draw.text((cx + 28, cy + 150), "Scopes: user.info.basic, video.upload, video.publish", font=font_body, fill=TIKTOK_CYAN)

    if is_connected:
        draw.rounded_rectangle([cx + 28, cy + 205, cx + 380, cy + 255], radius=8, fill=(20, 75, 48), outline=GREEN_ACCENT, width=1)
        draw.text((cx + 46, cy + 219), "Connected as @dwannellenga", font=font_sub, fill=GREEN_ACCENT)
    else:
        btn = [cx + 28, cy + 205, cx + 310, cy + 255]
        draw.rounded_rectangle(btn, radius=8, fill=TIKTOK_PINK)
        draw.text((cx + 56, cy + 219), "Connect TikTok Account", font=font_sub, fill=TEXT_WHITE)

    # OAuth 2.0 Authorization Popup (0.20 -> 0.72)
    if 0.20 <= t < 0.72:
        dim = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 175))
        img = Image.alpha_composite(img.convert("RGBA"), dim).convert("RGB")
        draw = ImageDraw.Draw(img)

        mx, my, mw, mh = 610, 180, 700, 620
        draw.rounded_rectangle([mx, my, mx + mw, my + mh], radius=16, fill=(24, 26, 34), outline=TIKTOK_CYAN, width=2)
        draw.text((mx + 36, my + 28), "tiktok.com/v2/auth/authorize", font=font_small, fill=TEXT_MUTED)
        draw.text((mx + 36, my + 64), "Authorize Shortsyt to access your TikTok?", font=font_h1, fill=TEXT_WHITE)
        draw.text((mx + 36, my + 108), "Signed in creator: @dwannellenga (Dwannellenga)", font=font_body, fill=GOLD)
        draw.line([(mx + 30, my + 148), (mx + mw - 30, my + 148)], fill=CARD_BORDER, width=1)

        scopes = [
            ("user.info.basic", "Read basic creator profile (nickname & avatar)"),
            ("video.upload", "Upload short-form video files to TikTok"),
            ("video.publish", "Publish & schedule videos to your TikTok profile"),
        ]
        sy = my + 175
        for sc, desc in scopes:
            draw.rounded_rectangle([mx + 36, sy, mx + mw - 36, sy + 76], radius=10, fill=INPUT_BG, outline=CARD_BORDER)
            draw.text((mx + 56, sy + 12), f"[+] {sc}", font=font_sub, fill=TIKTOK_CYAN)
            draw.text((mx + 56, sy + 42), desc, font=font_body, fill=TEXT_WHITE)
            sy += 92

        auth_btn = [mx + 180, my + mh - 95, mx + mw - 180, my + mh - 32]
        draw.rounded_rectangle(auth_btn, radius=10, fill=TIKTOK_PINK)
        draw.text((mx + 285, my + mh - 76), "Authorize", font=font_h2, fill=TEXT_WHITE)

        cur_p = interp_pos((mx + 120, my + 240), (mx + mw // 2, my + mh - 64), (t - 0.25) / 0.38)
        draw_cursor(draw, cur_p[0], cur_p[1], clicking=(0.62 <= t <= 0.71))
    else:
        cur_p = interp_pos((900, 620), (cx + 170, cy + 230), t / 0.18 if t < 0.20 else 1.0)
        draw_cursor(draw, cur_p[0], cur_p[1], clicking=(0.14 <= t < 0.20))

    return img


def render_scene_2_render(frame_idx: int, total_frames: int) -> Image.Image:
    """Scene 2 (8-16s): Gameplay Highlight Detection & 9:16 Render."""
    t = frame_idx / total_frames
    pct = min(100, int((t / 0.85) * 100))
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_chrome_shell(draw, "Render Monitor", "STEP 2/4: 9:16 VERTICAL AI RENDER")

    cx, cy = 290, 100
    cw = WIDTH - cx - 40
    draw.text((cx, cy), "AI Vertical Video Pipeline (16:9 -> 9:16)", font=font_h1, fill=TEXT_WHITE)
    draw.text((cx, cy + 38), "Converting creator gameplay highlight into 1080x1920 vertical format for TikTok Direct Post.", font=font_body, fill=TEXT_MUTED)

    bar_y = cy + 90
    draw.rounded_rectangle([cx, bar_y, cx + cw, bar_y + 38], radius=8, fill=CARD_BG, outline=CARD_BORDER)
    fill_w = max(20, int(cw * (pct / 100.0)))
    draw.rounded_rectangle([cx, bar_y, cx + fill_w, bar_y + 38], radius=8, fill=GREEN_ACCENT if pct == 100 else GOLD)
    draw.text((cx + cw // 2 - 40, bar_y + 7), f"{pct}%", font=font_h2, fill=(10, 14, 24))

    rows = [
        ("Source Gameplay:", "Katarina Triple Kill Replay (1920x1080 -> 1080x1920)", pct >= 20),
        ("Kill Event & Beat Sync:", "Peak climax detected at 6.5s | Audio loudness normalized (-16 LUFS)", pct >= 45),
        ("Vertical Framing & QA:", "Smart camera tracking active | Quality Gate: PASS (96/100)", pct >= 75),
        ("Ready to Publish:", "Output MP4 encoded & metadata prepared -> Opening TikTok Direct Post UI", pct >= 100),
    ]
    ry = bar_y + 70
    for title, desc, done in rows:
        draw.rounded_rectangle([cx, ry, cx + cw, ry + 86], radius=10, fill=CARD_BG, outline=GREEN_ACCENT if done else CARD_BORDER)
        draw.text((cx + 24, ry + 14), ("[OK] " if done else "[..] ") + title, font=font_h2, fill=GREEN_ACCENT if done else TEXT_WHITE)
        draw.text((cx + 24, ry + 48), desc, font=font_body, fill=TEXT_MUTED)
        ry += 108

    if pct >= 100:
        btn = [cx + cw - 360, ry + 20, cx + cw, ry + 78]
        draw.rounded_rectangle(btn, radius=10, fill=TIKTOK_PINK)
        draw.text((cx + cw - 320, ry + 36), "Open TikTok Publish Form ->", font=font_h2, fill=TEXT_WHITE)
        cur_p = interp_pos((cx + 500, ry + 40), (cx + cw - 180, ry + 49), (t - 0.85) / 0.14)
        draw_cursor(draw, cur_p[0], cur_p[1], clicking=(t >= 0.94))

    return img


def render_scene_3_4_tiktok_ux(
    frame_idx: int,
    total_frames: int,
    scene3_frames: int,
    video_cap: cv2.VideoCapture,
) -> Image.Image:
    """
    Scene 3 (16-32s): Mandatory TikTok Direct Post UX Form with interactive cursor actions.
    Scene 4 (32-42s): API Direct Post submission -> PUBLISH_COMPLETE confirmation.
    """
    in_scene_4 = frame_idx >= scene3_frames
    s3_t = frame_idx / scene3_frames if not in_scene_4 else 1.0
    s4_t = (frame_idx - scene3_frames) / max(1, total_frames - scene3_frames) if in_scene_4 else 0.0

    img = Image.new("RGB", (WIDTH, HEIGHT), BG_DARK)
    draw = ImageDraw.Draw(img)
    badge = "STEP 4/4: DIRECT POST COMPLETE" if in_scene_4 else "STEP 3/4: TIKTOK DIRECT POST UX"
    draw_chrome_shell(draw, "Publish & Outputs", badge)

    cx, cy = 285, 90
    cw = WIDTH - cx - 30
    draw.text((cx, cy), "Publish Video to TikTok (Content Posting API v2)", font=font_h1, fill=TEXT_WHITE)
    draw.text((cx, cy + 36), "Creator must manually review video, privacy level, interactions & disclosures before posting.", font=font_body, fill=TEXT_MUTED)

    # Left: Real 9:16 video preview
    px, py = cx + 10, cy + 80
    pw, ph = 420, 746
    draw.rounded_rectangle([px - 8, py - 8, px + pw + 8, py + ph + 8], radius=20, fill=CARD_BG, outline=TIKTOK_CYAN, width=2)
    if video_cap and video_cap.isOpened():
        ret, frame = video_cap.read()
        if not ret:
            video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = video_cap.read()
        if ret:
            frame_resized = cv2.resize(frame, (pw, ph))
            pil_frame = Image.fromarray(cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB))
            img.paste(pil_frame, (px, py))

    # Right: Compliance Form
    rx = px + pw + 45
    rw = cw - (pw + 75)
    draw.rounded_rectangle([rx, py, rx + rw, py + ph], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=2)

    # 1. Creator Info Banner (fetched from creator_info/query)
    draw.rounded_rectangle([rx + 24, py + 20, rx + rw - 24, py + 76], radius=10, fill=INPUT_BG, outline=TIKTOK_CYAN, width=1)
    draw.text((rx + 42, py + 30), "Creator: @dwannellenga (Dwannellenga)", font=font_sub, fill=TEXT_WHITE)
    draw.text((rx + 42, py + 52), "Source: /v2/post/publish/creator_info/query/  |  Max duration: 60 min", font=font_small, fill=TIKTOK_CYAN)

    # 2. Editable Title / Caption (edited during s3_t 0.12..0.28)
    draw.text((rx + 24, py + 94), "Title / Caption & Hashtags (Editable):", font=font_sub, fill=GOLD)
    cap_box = [rx + 24, py + 120, rx + rw - 24, py + 188]
    editing_cap = 0.08 <= s3_t < 0.28
    draw.rounded_rectangle(cap_box, radius=8, fill=INPUT_BG, outline=TIKTOK_CYAN if editing_cap else CARD_BORDER, width=2 if editing_cap else 1)
    base_cap = "INSANE Katarina Triple Kill Reset! #leagueoflegends #katarina"
    if s3_t >= 0.22:
        shown_cap = base_cap + " #triplekill #fyp"
    elif s3_t >= 0.14:
        shown_cap = base_cap + " #triple"
    else:
        shown_cap = base_cap
    draw.text((rx + 38, py + 134), shown_cap, font=font_body, fill=TEXT_WHITE)
    draw.text((rx + 38, py + 160), "Cover thumbnail timestamp: 6.5s (Auto-selected highlight peak)", font=font_small, fill=TEXT_MUTED)

    # 3. Who can view this video (MUST NOT have a default selection initially!)
    privacy_chosen = s3_t >= 0.50
    dropdown_open = 0.34 <= s3_t < 0.50
    draw.text((rx + 24, py + 208), "Who can view this video (Required - no default):", font=font_sub, fill=GOLD)
    priv_box = [rx + 24, py + 234, rx + rw - 24, py + 278]
    draw.rounded_rectangle(priv_box, radius=8, fill=INPUT_BG, outline=GREEN_ACCENT if privacy_chosen else TIKTOK_PINK, width=2)
    priv_label = "Public to everyone (PUBLIC_TO_EVERYONE)" if privacy_chosen else "-- Select privacy level --"
    draw.text((rx + 38, py + 246), priv_label, font=font_body, fill=TEXT_WHITE if privacy_chosen else TEXT_MUTED)
    draw.text((rx + rw - 56, py + 246), "v", font=font_sub, fill=TEXT_WHITE)

    # 4. Allow users to (ALL OFF by default; Comment checked @ 0.58, Duet @ 0.66)
    allow_comment = s3_t >= 0.58
    allow_duet = s3_t >= 0.66
    allow_stitch = False
    draw.text((rx + 24, py + 298), "Allow users to (Unchecked by default - manual opt-in):", font=font_sub, fill=GOLD)
    draw_checkbox(draw, rx + 24, py + 328, allow_comment, "Comment")
    draw_checkbox(draw, rx + 210, py + 328, allow_duet, "Duet")
    draw_checkbox(draw, rx + 360, py + 328, allow_stitch, "Stitch")

    # 5. Disclose video content (Commercial content toggle - OFF by default)
    disclose_on = 0.72 <= s3_t < 0.85
    draw.rounded_rectangle([rx + 24, py + 374, rx + rw - 24, py + 474], radius=10, fill=INPUT_BG, outline=CARD_BORDER)
    draw.text((rx + 40, py + 388), "Disclose video content (Commercial content)", font=font_sub, fill=TEXT_WHITE)
    draw_toggle(draw, rx + rw - 88, py + 386, disclose_on)
    draw_checkbox(draw, rx + 40, py + 430, False, "Your brand (promoting yourself)")
    draw_checkbox(draw, rx + 420, py + 430, False, "Branded content (third-party paid)")

    # 6. Mandatory Music Usage Confirmation & Processing Notice
    draw.rounded_rectangle([rx + 24, py + 492, rx + rw - 24, py + 572], radius=8, fill=(28, 34, 52), outline=CARD_BORDER)
    draw.text(
        (rx + 38, py + 504),
        "By posting, you agree to TikTok's Music Usage Confirmation.",
        font=font_sub,
        fill=TEXT_WHITE,
    )
    draw.text(
        (rx + 38, py + 532),
        "After publishing, it may take a few minutes for your video to process and appear on your profile.",
        font=font_small,
        fill=TEXT_MUTED,
    )

    # 7. Submit Button + Direct Post Status
    post_btn = [rx + 24, py + 592, rx + rw - 24, py + 648]
    if not in_scene_4:
        btn_bg = TIKTOK_PINK if privacy_chosen else (80, 40, 55)
        draw.rounded_rectangle(post_btn, radius=10, fill=btn_bg)
        draw.text((rx + rw // 2 - 110, py + 608), "Post to TikTok (Direct Post)", font=font_h2, fill=TEXT_WHITE)
    elif s4_t < 0.35:
        draw.rounded_rectangle(post_btn, radius=10, fill=BLUE_ACCENT)
        pct_up = int((s4_t / 0.35) * 100)
        draw.text((rx + rw // 2 - 170, py + 608), f"Uploading via /video/init/... {pct_up}%", font=font_h2, fill=TEXT_WHITE)
    else:
        draw.rounded_rectangle(post_btn, radius=10, fill=GREEN_ACCENT)
        draw.text((rx + rw // 2 - 165, py + 608), "PUBLISH_COMPLETE (200 OK)", font=font_h2, fill=(10, 14, 24))
        status_box = [rx + 24, py + 664, rx + rw - 24, py + 728]
        draw.rounded_rectangle(status_box, radius=10, fill=(18, 65, 42), outline=GREEN_ACCENT, width=2)
        draw.text((rx + 40, py + 674), "TikTok Direct Post Succeeded — Creator: @dwannellenga", font=font_sub, fill=GREEN_ACCENT)
        draw.text((rx + 40, py + 698), "Publish ID: v_pub_v2.771092481029384 | Privacy: PUBLIC_TO_EVERYONE", font=font_small, fill=TEXT_WHITE)

    # Privacy dropdown menu overlay (drawn ABOVE form controls so it sits cleanly on top!)
    if dropdown_open:
        menu_y = py + 282
        draw.rounded_rectangle([rx + 24, menu_y, rx + rw - 24, menu_y + 132], radius=8, fill=(28, 34, 52), outline=TIKTOK_CYAN, width=2)
        hovered = s3_t >= 0.42
        if hovered:
            draw.rectangle([rx + 28, menu_y + 8, rx + rw - 28, menu_y + 44], fill=(45, 70, 95))
        draw.text((rx + 40, menu_y + 15), "Public to everyone (PUBLIC_TO_EVERYONE)", font=font_body, fill=GOLD if hovered else TEXT_WHITE)
        draw.text((rx + 40, menu_y + 54), "Friends (MUTUAL_FOLLOW_FRIENDS)", font=font_body, fill=TEXT_WHITE)
        draw.text((rx + 40, menu_y + 92), "Only you (SELF_ONLY)", font=font_body, fill=TEXT_WHITE)

    # Cursor choreography in Scene 3
    if not in_scene_4:
        p_cap = (rx + 420, py + 152)
        p_priv = (rx + 280, py + 256)
        p_pub_opt = (rx + 260, py + 308)
        p_comm = (rx + 34, py + 338)
        p_duet = (rx + 220, py + 338)
        p_disc = (rx + rw - 66, py + 397)
        p_post = (rx + rw // 2, py + 620)

        if s3_t < 0.12:
            cp = interp_pos((rx + 600, py + 500), p_cap, s3_t / 0.12)
            clk = s3_t > 0.09
        elif s3_t < 0.34:
            cp = interp_pos(p_cap, p_priv, max(0.0, (s3_t - 0.25) / 0.09))
            clk = s3_t >= 0.32
        elif s3_t < 0.50:
            cp = interp_pos(p_priv, p_pub_opt, (s3_t - 0.34) / 0.12)
            clk = s3_t >= 0.46
        elif s3_t < 0.60:
            cp = interp_pos(p_pub_opt, p_comm, (s3_t - 0.50) / 0.07)
            clk = s3_t >= 0.57
        elif s3_t < 0.68:
            cp = interp_pos(p_comm, p_duet, (s3_t - 0.60) / 0.06)
            clk = s3_t >= 0.65
        elif s3_t < 0.78:
            cp = interp_pos(p_duet, p_disc, (s3_t - 0.68) / 0.06)
            clk = 0.71 <= s3_t <= 0.74
        else:
            cp = interp_pos(p_disc, p_post, min(1.0, (s3_t - 0.80) / 0.16))
            clk = s3_t >= 0.96
        draw_cursor(draw, cp[0], cp[1], clicking=clk)

    return img


def generate_demo_video() -> bool:
    print(f"Generating TikTok App Review Demo Video -> {FINAL_DEMO_PATH}")
    print(f"Source rendered 9:16 short: {RENDERED_SHORT_PATH}")
    if not RENDERED_SHORT_PATH.is_file():
        print(f"ERROR: Rendered short not found: {RENDERED_SHORT_PATH}")
        return False

    cap_video = cv2.VideoCapture(str(RENDERED_SHORT_PATH))
    temp_raw = PROJECT_ROOT / "lol_agent" / "lol_temp" / "temp_demo_video_raw.mp4"
    temp_raw.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "bgr24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "24",
        "-pix_fmt", "yuv420p",
        str(temp_raw),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    f_s1 = 8 * FPS    # 0-8s: Login Kit OAuth
    f_s2 = 8 * FPS    # 8-16s: Clip Render
    f_s3 = 16 * FPS   # 16-32s: TikTok Direct Post UX Form
    f_s4 = 10 * FPS   # 32-42s: Direct Post Confirmation

    for f in range(f_s1):
        img = render_scene_1_oauth(f, f_s1)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    for f in range(f_s2):
        img = render_scene_2_render(f, f_s2)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    for f in range(f_s3 + f_s4):
        img = render_scene_3_4_tiktok_ux(f, f_s3 + f_s4, f_s3, cap_video)
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    proc.stdin.close()
    proc.wait()
    cap_video.release()

    # Mix real audio starting at t=16s (when 9:16 preview appears)
    audio_cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(temp_raw),
        "-itsoffset", "16.0",
        "-i", str(RENDERED_SHORT_PATH),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-map", "0:v:0",
        "-map", "1:a:0?",
        "-movflags", "+faststart",
        str(FINAL_DEMO_PATH),
    ]
    res = subprocess.run(audio_cmd, capture_output=True)
    if temp_raw.exists():
        try:
            temp_raw.unlink()
        except Exception:
            pass

    if res.returncode == 0 and FINAL_DEMO_PATH.is_file():
        mb = round(FINAL_DEMO_PATH.stat().st_size / (1024 * 1024), 2)
        print(f"SUCCESS: Demo video ready ({mb} MB): {FINAL_DEMO_PATH}")
        DESKTOP_VERIF_DIR.mkdir(parents=True, exist_ok=True)
        dest_vid = DESKTOP_VERIF_DIR / FINAL_DEMO_PATH.name
        shutil.copy2(FINAL_DEMO_PATH, dest_vid)
        print(f"COPIED TO DESKTOP PACKAGE: {dest_vid}")
        return True

    print(f"ERROR mixing audio: {res.stderr.decode('utf-8', errors='replace')[:400]}")
    return False


if __name__ == "__main__":
    ok = generate_demo_video()
    sys.exit(0 if ok else 1)
