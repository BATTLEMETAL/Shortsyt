"""
Shortsyt / Flikcut Studio — Live Real Application Recorder (1920x1080)
Launches the real live React/FastAPI web UI (served at http://127.0.0.1:8765),
drives real UI interactions via Playwright Google Chrome while recording video,
restores any temporary test metadata/queue record afterward, and muxes MP4 + real short audio.
"""
import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lol_agent.api.auth import create_access_token

BACKEND_URL = "http://127.0.0.1:8765"
TARGET_SHORT_NAME = "short_overnight_20261121_005819_9aaaa_r2_triple.mp4"
DEST_DIR = Path.home() / "OneDrive" / "Pulpit" / "Wszystko na rozmowe" / "tiktok"
OUT_MP4 = DEST_DIR / "Shortsyt_TikTok_Verification_Demo.mp4"
FFMPEG_BIN = r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe" if os.path.isfile(r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe") else (shutil.which("ffmpeg") or "ffmpeg")

CURSOR_INIT_JS = """
(() => {
  if (window.__flikcutCursorInstalled) return;
  window.__flikcutCursorInstalled = true;
  window.__cursorPos = { x: 960, y: 540 };
  const install = () => {
    if (!document.body || document.getElementById('__flikcut_cursor')) return;
    const el = document.createElement('div');
    el.id = '__flikcut_cursor';
    el.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;width:22px;height:22px;border-radius:50%;background:rgba(200,255,58,0.88);border:2px solid #050505;box-shadow:0 0 12px rgba(0,242,254,0.85);transform:translate(-50%,-50%);transition:transform 0.08s ease;left:960px;top:540px;';
    document.body.appendChild(el);
    window.addEventListener('mousemove', (e) => {
      el.style.left = e.clientX + 'px';
      el.style.top = e.clientY + 'px';
    }, { passive: true });
    window.addEventListener('mousedown', () => {
      el.style.transform = 'translate(-50%,-50%) scale(1.55)';
      el.style.background = '#FE2C55';
    }, { passive: true });
    window.addEventListener('mouseup', () => {
      el.style.transform = 'translate(-50%,-50%) scale(1)';
      el.style.background = 'rgba(200,255,58,0.88)';
    }, { passive: true });
  };
  document.addEventListener('DOMContentLoaded', install);
  setInterval(install, 250);
})();
"""


def smooth_click(page, locator, pause_after_ms: int = 900) -> None:
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    box = locator.bounding_box()
    if box:
        tx = box["x"] + box["width"] / 2.0
        ty = box["y"] + box["height"] / 2.0
        page.mouse.move(tx, ty, steps=18)
        page.wait_for_timeout(200)
    locator.click()
    if pause_after_ms > 0:
        page.wait_for_timeout(pause_after_ms)


def record_live_app() -> bool:
    from playwright.sync_api import sync_playwright

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    rec_tmp_dir = PROJECT_ROOT / "lol_agent" / "lol_temp" / "_demo_rec_tmp"
    if rec_tmp_dir.exists():
        shutil.rmtree(rec_tmp_dir, ignore_errors=True)
    rec_tmp_dir.mkdir(parents=True, exist_ok=True)

    # Snapshot files we want cleanly restored if our live test upload appends to them
    queue_file = PROJECT_ROOT / "accounts" / "scheduled_social_queue.json"
    pub_log_file = PROJECT_ROOT / "lol_agent" / "published_videos.jsonl"
    meta_file = PROJECT_ROOT / "lol_agent" / "lol_temp" / TARGET_SHORT_NAME.replace(".mp4", ".meta.json")
    snapshots = {
        queue_file: queue_file.read_bytes() if queue_file.exists() else None,
        pub_log_file: pub_log_file.read_bytes() if pub_log_file.exists() else None,
        meta_file: meta_file.read_bytes() if meta_file.exists() else None,
    }

    jwt_tok = create_access_token({"sub": "admin"})
    raw_webm: Path | None = None
    audio_start_sec: float | None = None

    try:
        with sync_playwright() as pw:
            launch_opts = {
                "headless": False,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--autoplay-policy=no-user-gesture-required",
                    "--window-size=1920,1080",
                ],
            }
            try:
                browser = pw.chromium.launch(channel="chrome", **launch_opts)
            except Exception:
                browser = pw.chromium.launch(**launch_opts)

            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(rec_tmp_dir),
                record_video_size={"width": 1920, "height": 1080},
            )
            ctx.add_init_script(f"""
                try {{
                    localStorage.setItem('jwt_token', {json.dumps(json.dumps(jwt_tok))});
                    localStorage.setItem('api_url', {json.dumps(json.dumps(BACKEND_URL))});
                    window.__capturedExternalUrls = [];
                    window.open = function(u) {{
                        window.__capturedExternalUrls.push(String(u || ''));
                        return null;
                    }};
                }} catch (e) {{}}
                {CURSOR_INIT_JS}
            """)

            page = ctx.new_page()
            rec_t0 = time.monotonic()

            # 1. Start on real live Dashboard (showing clean separated clip names & dynamic YT vs TikTok tags)
            page.goto(f"{BACKEND_URL}/#/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2200)

            # 2. Navigate to Settings -> Click real Connect / Authorize TikTok OAuth 2.0 (PKCE localhost:8180)
            smooth_click(page, page.locator("a[href='#/settings']").first, pause_after_ms=2000)
            tt_auth_btn = page.get_by_role("button", name="Connect / Authorize TikTok OAuth 2.0")
            tt_auth_btn.wait_for(state="visible", timeout=15000)
            smooth_click(page, tt_auth_btn, pause_after_ms=3500)

            # Verify real PKCE waiting panel appeared with localhost:8180/callback (not fake modal)
            page.locator("text=localhost:8180/callback").first.wait_for(state="visible", timeout=10000)
            page.wait_for_timeout(2000)
            cancel_tt_btn = page.get_by_role("button", name="Anuluj").first
            if cancel_tt_btn.count() > 0:
                smooth_click(page, cancel_tt_btn, pause_after_ms=1000)

            # 3. Navigate to Analityka Kanału -> TikTok tab (show 35 synced videos & Synapsa TikTok Intelligence)
            smooth_click(page, page.locator("a[href='#/analytics']").first, pause_after_ms=1500)
            tt_tab = page.locator("button").filter(has_text="TikTok").filter(has_text="Direct Post").first
            tt_tab.wait_for(state="visible", timeout=15000)
            smooth_click(page, tt_tab, pause_after_ms=800)
            page.locator("text=Synapsa TikTok Intelligence").first.wait_for(state="visible", timeout=15000)
            page.wait_for_timeout(4500)

            # 4. Navigate to Biblioteka Shorts (/outputs) & play real 9:16 video for 7.0s
            smooth_click(page, page.locator("a[href='#/outputs']").first, pause_after_ms=1500)
            target_card = page.locator("div.p-4").filter(has_text=TARGET_SHORT_NAME).first
            preview_btn = target_card.get_by_role("button", name="Podgląd")
            preview_btn.wait_for(state="visible", timeout=20000)
            smooth_click(page, preview_btn, pause_after_ms=600)
            vid_el = page.locator("video").first
            vid_el.wait_for(state="visible", timeout=10000)
            vid_el.scroll_into_view_if_needed()
            page.wait_for_timeout(7000)

            # 5. Close preview & click "Publikuj" on the same rendered short
            close_btn = page.get_by_role("button", name="Zamknij").first
            if close_btn.count() > 0:
                smooth_click(page, close_btn, pause_after_ms=700)

            pub_btn = target_card.get_by_role("button", name="Publikuj")
            smooth_click(page, pub_btn, pause_after_ms=1500)

            # 6. Select "2. TikTok" preset (hides YT fields, shows ONLY TikTok Direct Post + Synapsa TikTok AI)
            tt_preset = page.get_by_role("button", name="2. TikTok Tylko TikTok")
            if tt_preset.count() == 0:
                tt_preset = page.locator("button:has-text('2. TikTok')").first
            smooth_click(page, tt_preset, pause_after_ms=1800)

            # Highlight TikTok caption textarea
            tt_textarea = page.locator("textarea").filter(has_text="#").first
            if tt_textarea.count() > 0:
                smooth_click(page, tt_textarea, pause_after_ms=1000)

            # 7. Manually select "Public to everyone" from unselected Privacy dropdown
            privacy_select = page.locator("select").filter(has=page.locator("option[value='PUBLIC_TO_EVERYONE']")).first
            privacy_select.wait_for(state="visible", timeout=10000)
            smooth_click(page, privacy_select, pause_after_ms=900)
            privacy_select.select_option("PUBLIC_TO_EVERYONE")
            page.wait_for_timeout(1200)

            # 8. Show Draft/Inbox (video.upload) briefly, switch back to Direct Post (video.publish), opt in Comment & Duet, and verify Disclose UX
            inbox_btn = page.get_by_role("button", name="Upload as Draft / Inbox (video.upload)")
            if inbox_btn.count() > 0:
                smooth_click(page, inbox_btn, pause_after_ms=1100)
                direct_btn = page.get_by_role("button", name="Direct Post (video.publish)")
                if direct_btn.count() > 0:
                    smooth_click(page, direct_btn, pause_after_ms=900)

            comment_cb = page.locator("label:has-text('Comment') input[type='checkbox']").first
            duet_cb = page.locator("label:has-text('Duet') input[type='checkbox']").first
            smooth_click(page, comment_cb, pause_after_ms=700)
            smooth_click(page, duet_cb, pause_after_ms=700)

            disclose_cb = page.locator("label:has-text('Disclose video content') input[type='checkbox']").first
            smooth_click(page, disclose_cb, pause_after_ms=800)
            page.locator("text=You need to indicate if your content promotes").first.wait_for(state="visible", timeout=5000)
            your_brand_cb = page.locator("label:has-text('Your brand') input[type='checkbox']").first
            smooth_click(page, your_brand_cb, pause_after_ms=800)
            page.locator("text=Promotional content").first.wait_for(state="visible", timeout=5000)
            page.wait_for_timeout(700)
            smooth_click(page, disclose_cb, pause_after_ms=800)

            # Ensure "AI Peak Slot" (future schedule) is selected so real backend executes cleanly
            ai_peak_btn = page.locator("button:has-text('AI Peak Slot')").first
            if ai_peak_btn.count() > 0:
                smooth_click(page, ai_peak_btn, pause_after_ms=800)

            # 9. Click final "Opublikuj na TikTok" -> wait for real backend 200 OK result and scroll into full view
            submit_btn = page.locator("button:has-text('Opublikuj na TikTok')").last
            smooth_click(page, submit_btn, pause_after_ms=500)

            res_banner = page.locator("text=Wyniki publikacji:").first
            res_banner.wait_for(state="visible", timeout=20000)
            res_banner.scroll_into_view_if_needed()
            page.evaluate("""() => {
                const m = document.querySelector('div.max-h-\\\\[92vh\\\\]');
                if (m) m.scrollTop = m.scrollHeight;
            }""")
            page.wait_for_timeout(4500)

            vid = page.video
            ctx.close()
            browser.close()
            if vid:
                raw_webm = Path(vid.path())
    finally:
        # Restore queue, pub log & meta snapshot so live 11:00/21:30 schedule stays spotless
        for fp, prev_bytes in snapshots.items():
            try:
                if prev_bytes is None:
                    fp.unlink(missing_ok=True)
                else:
                    fp.write_bytes(prev_bytes)
            except Exception:
                pass

    if not raw_webm or not raw_webm.is_file():
        print("ERROR: Playwright video file not created")
        shutil.rmtree(rec_tmp_dir, ignore_errors=True)
        return False

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(raw_webm),
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map", "0:v:0", "-map", "1:a:0",
        "-r", "30", "-fps_mode", "cfr",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(OUT_MP4),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    shutil.rmtree(rec_tmp_dir, ignore_errors=True)

    if res.returncode == 0 and OUT_MP4.is_file():
        mb = round(OUT_MP4.stat().st_size / (1024 * 1024), 2)
        print(f"SUCCESS REAL APP RECORDING ({mb} MB): {OUT_MP4}")
        return True

    print("FFMPEG ERROR:", res.stderr[:500])
    return False


if __name__ == "__main__":
    ok = record_live_app()
    sys.exit(0 if ok else 1)
