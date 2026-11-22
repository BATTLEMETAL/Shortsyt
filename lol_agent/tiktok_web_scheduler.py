"""
Shortsyt — Opcjonalny Auto-Scheduler TikTok Studio Web (Playwright).

Gdy aplikacja TikTok API działa w trybie niezaudytowanym (Inbox/Drafts bez automatycznego opisu/schedule),
ten moduł pozwala zautomatyzować upload, wklejenie opisu + hashtagów oraz natywny harmonogram
bezpośrednio w TikTok Studio Web (`tiktok.com/tiktokstudio/upload`) na trwałym profilu Chromium.
Aktywacja w kolejce: `TIKTOK_USE_WEB_STUDIO=1` (po jednorazowym zalogowaniu profilu).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_PROFILE_DIR = ROOT_DIR / "accounts" / "tiktok_web_profile"
TIKTOK_STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?lang=en"


def is_web_scheduler_ready() -> bool:
    """Sprawdza, czy Playwright i profil Chromium są dostępne."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    try:
        import importlib.util
        return bool(importlib.util.find_spec("playwright"))
    except Exception:
        return False


def _release_profile_lock(prof: Path) -> None:
    """Zwalnia procesy Chrome trzymające blokadę profilu automatyzacji przed startem kolejki."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    needle = prof.name
    if not needle:
        return
    try:
        import subprocess
        ps_cmd = (
            f"$p = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            f"Where-Object {{ $_.CommandLine -match '{needle}' }}; "
            f"if ($p) {{ "
            f"$p | ForEach-Object {{ (Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue).CloseMainWindow() | Out-Null }}; "
            f"Start-Sleep -Seconds 2; "
            f"$p | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }} "
            f"}}"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(0.5)
    except Exception:
        pass

    for lock_name in ("lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            lp = prof / lock_name
            if lp.exists() or lp.is_symlink():
                lp.unlink()
        except Exception:
            pass


def _launch_tiktok_browser_context(pw: Any, prof: Path, headless: bool) -> Any:
    """Uruchamia trwały kontekst prawdziwego Google Chrome (fallback: Chromium)."""
    _release_profile_lock(prof)
    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(prof),
        "headless": headless,
        "viewport": {"width": 1280, "height": 900},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    try:
        return pw.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
    except Exception:
        return pw.chromium.launch_persistent_context(**launch_kwargs)


def open_tiktok_web_login_window(
    wait_seconds: int = 300,
    profile_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Otwiera widoczne okno Google Chrome na profilu accounts/tiktok_web_profile
    pod adresem TikTok Studio w celu jednorazowego zalogowania użytkownika.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {"success": False, "error": "Pominięto Playwright w testach jednostkowych"}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "error": "Playwright nie jest zainstalowany w venv313."}

    prof = Path(profile_dir) if profile_dir else WEB_PROFILE_DIR
    prof.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = _launch_tiktok_browser_context(pw, prof, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(TIKTOK_STUDIO_UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            deadline = time.monotonic() + max(10, int(wait_seconds))
            logged_in = False
            while time.monotonic() < deadline:
                if not ctx.pages:
                    break
                cur_url = (page.url or "").lower()
                if "tiktokstudio" in cur_url and "login" not in cur_url:
                    try:
                        if page.locator("input[type='file']").count() > 0:
                            logged_in = True
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass
                time.sleep(1.0)
            return {"success": logged_in, "profile_dir": str(prof), "url": page.url if ctx.pages else ""}
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def schedule_tiktok_via_web_studio(
    video_path: str,
    caption: str,
    publish_at: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    headless: bool = False,
    profile_dir: Optional[Path] = None,
    timeout_ms: int = 90000,
) -> Dict[str, Any]:
    """
    Wysyła czysty plik wideo do TikTok Studio Web (bez doklejania klatki 0.08s),
    wypełnia opis + hashtagi i opcjonalnie ustawia natywne planowanie `Schedule`.
    """
    vp = Path(video_path)
    if not vp.is_file():
        return {"success": False, "error": f"Plik wideo nie istnieje: {video_path}"}

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {"success": False, "error": "Pominięto Playwright w testach jednostkowych"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "success": False,
            "error": "Playwright nie jest zainstalowany w venv313 (fallback do TikTok API).",
        }

    if os.environ.get("TIKTOK_EMBED_INTRO_COVER", "").strip() == "1":
        from lol_agent.tiktok_publisher import _prepare_tiktok_video_with_cover
        upload_vp, temp_cover_path = _prepare_tiktok_video_with_cover(vp, thumbnail_path)
    else:
        upload_vp, temp_cover_path = vp, None

    prof = Path(profile_dir) if profile_dir else WEB_PROFILE_DIR
    prof.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as pw:
            ctx = _launch_tiktok_browser_context(pw, prof, headless=headless)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(TIKTOK_STUDIO_UPLOAD_URL, wait_until="domcontentloaded", timeout=timeout_ms)

                # Sprawdź, czy użytkownik jest zalogowany do TikTok Studio
                if "login" in page.url.lower():
                    return {
                        "success": False,
                        "needs_login": True,
                        "profile_dir": str(prof),
                        "error": "Profil Chromium nie jest zalogowany w TikTok Studio. Zaloguj się raz ręcznie w oknie przeglądarki.",
                    }

                file_input = page.locator("input[type='file']").first
                file_input.wait_for(state="attached", timeout=30000)
                file_input.set_input_files(str(upload_vp))

                # Poczekaj na edytor opisu
                caption_box = page.locator("[contenteditable='true']").first
                caption_box.wait_for(state="visible", timeout=60000)
                caption_box.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(caption[:2200], delay=8)

                if publish_at:
                    dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00")).astimezone(timezone.utc)
                    schedule_radio = page.get_by_text("Schedule", exact=False).first
                    if schedule_radio.count() > 0:
                        schedule_radio.click()
                        page.wait_for_timeout(800)

                # Kliknij Post / Schedule jeśli przycisk stał się aktywny
                submit_btn = page.locator("button:has-text('Post'), button:has-text('Schedule')").last
                submit_btn.wait_for(state="visible", timeout=60000)
                submit_btn.click()
                page.wait_for_timeout(5000)

                return {
                    "success": True,
                    "platform": "tiktok",
                    "mode": "web_studio",
                    "caption": caption[:2200],
                    "publish_at": publish_at,
                    "cover_embedded": temp_cover_path is not None,
                    "message": "Opublikowano / zaplanowano przez TikTok Studio Web",
                }
            finally:
                ctx.close()
    except Exception as exc:
        return {"success": False, "platform": "tiktok", "mode": "web_studio", "error": str(exc)}
    finally:
        if temp_cover_path and temp_cover_path.exists():
            try:
                temp_cover_path.unlink()
            except Exception:
                pass
