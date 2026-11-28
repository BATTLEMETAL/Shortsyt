"""
Shortsyt — Moduł publikacji na Facebook Page (Reels / Video).
Obsługuje publikację wideo na fanpage za pomocą Meta Graph API v21.0 (Video Reels & Resumable Upload),
weryfikację uprawnień pages_manage_posts oraz pełną izolację błędów.
"""

from __future__ import annotations

import os
import sys
import time
import json
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
FACEBOOK_TOKEN_PATH = ACCOUNTS_DIR / "facebook_token.json"


def _token_path():
    """Aktywna ścieżka tokenu facebook wg konta z account_manager (fallback: stała domyślna)."""
    try:
        try:
            from lol_agent.account_manager import get_active_platform_token_path
        except ImportError:
            from account_manager import get_active_platform_token_path
        return get_active_platform_token_path("facebook")
    except Exception:
        return FACEBOOK_TOKEN_PATH


GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
GRAPH_VIDEO_BASE = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"


def load_facebook_token() -> Optional[Dict[str, Any]]:
    """Wczytuje token i dane strony Facebook z accounts/facebook_token.json lub .env."""
    data: Dict[str, Any] = {}
    if _token_path().exists():
        try:
            data = json.loads(_token_path().read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ Błąd odczytu {_token_path()}: {e}")

    access_token = data.get("access_token") or os.getenv("FACEBOOK_ACCESS_TOKEN", "").strip()
    page_id = data.get("page_id") or os.getenv("FACEBOOK_PAGE_ID", "").strip()
    page_name = data.get("page_name", "Dwannellenga")
    can_publish = data.get("can_publish_posts", True)

    if not access_token or not page_id:
        return None

    return {
        "access_token": access_token,
        "page_id": page_id,
        "page_name": page_name,
        "can_publish_posts": can_publish,
        "scopes": data.get("scopes", []),
        "expires_at": data.get("expires_at", 0),
    }


_FB_STATUS_CACHE_LOCK = threading.Lock()
_FB_STATUS_CACHE: Dict[str, Any] = {"key": None, "ts": 0.0, "data": None}
_FB_STATUS_CACHE_TTL_S = 60.0


def invalidate_facebook_token_status_cache() -> None:
    """Czyści buforowany status tokenu Facebook."""
    with _FB_STATUS_CACHE_LOCK:
        _FB_STATUS_CACHE["key"] = None
        _FB_STATUS_CACHE["ts"] = 0.0
        _FB_STATUS_CACHE["data"] = None


def get_facebook_token_status(
    force_refresh: bool = False,
    _use_cache: Optional[bool] = None,
) -> Dict[str, Any]:
    """Zwraca czytelny status połączenia i uprawnień strony Facebook (z 60s TTL cache poza testami)."""
    tpath = _token_path()
    mtime_ns = 0
    try:
        mtime_ns = Path(tpath).stat().st_mtime_ns
    except Exception:
        mtime_ns = 0

    token_data = load_facebook_token()
    if not token_data:
        return {
            "connected": False,
            "valid": False,
            "can_publish": False,
            "message": "Brak konfiguracji Facebook Page w accounts/facebook_token.json"
        }

    access_token = token_data["access_token"]
    page_id = token_data["page_id"]
    use_cache = (not bool(os.environ.get("PYTEST_CURRENT_TEST"))) if _use_cache is None else bool(_use_cache)
    cache_key = (str(tpath), mtime_ns, str(access_token)[:16])

    if use_cache and not force_refresh:
        now_m = time.monotonic()
        with _FB_STATUS_CACHE_LOCK:
            if (
                _FB_STATUS_CACHE["key"] == cache_key
                and _FB_STATUS_CACHE["data"] is not None
                and (now_m - float(_FB_STATUS_CACHE["ts"])) < _FB_STATUS_CACHE_TTL_S
            ):
                return dict(_FB_STATUS_CACHE["data"])

    try:
        url = f"{GRAPH_API_BASE}/{page_id}"
        resp = requests.get(
            url,
            params={"fields": "name,about,fan_count", "access_token": access_token},
            timeout=10
        )
        if resp.status_code == 200:
            res_json = resp.json()
            page_name = res_json.get("name", token_data.get("page_name", "Fanpage"))
            can_publish = bool(token_data.get("can_publish_posts", True))
            result = {
                "connected": True,
                "valid": True,
                "can_publish": can_publish,
                "page_id": page_id,
                "page_name": page_name,
                "fan_count": res_json.get("fan_count", 0),
                "message": f"Strona Facebook połączona ({page_name}, ID: {page_id})"
            }
            if use_cache:
                with _FB_STATUS_CACHE_LOCK:
                    _FB_STATUS_CACHE["key"] = cache_key
                    _FB_STATUS_CACHE["ts"] = time.monotonic()
                    _FB_STATUS_CACHE["data"] = dict(result)
            return result
        else:
            result = {
                "connected": True,
                "valid": False,
                "can_publish": False,
                "error": resp.text,
                "message": f"Token Facebook nieprawidłowy (kod {resp.status_code})"
            }
            if use_cache:
                with _FB_STATUS_CACHE_LOCK:
                    _FB_STATUS_CACHE["key"] = cache_key
                    _FB_STATUS_CACHE["ts"] = time.monotonic()
                    _FB_STATUS_CACHE["data"] = dict(result)
            return result
    except Exception as e:
        return {
            "connected": True,
            "valid": False,
            "can_publish": False,
            "error": str(e),
            "message": f"Błąd weryfikacji strony Facebook: {e}"
        }


def upload_facebook_reel(
    video_path: str,
    caption: str,
    publish_at: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    timeout: int = 300,
    use_local_queue: bool = True,
) -> Dict[str, Any]:
    """
    Publikuje lub planuje wideo jako Facebook Reel na fanpage za pomocą Meta Video Reels API.

    Etapy:
    1. Dla przyszłych dat (> 10 min) kolejkuje wpis w lokalnej kolejce 24/7 (zapobiega burstowi w Meta API).
    2. Inicjalizacja uploadu (POST /{page_id}/video_reels?upload_phase=start).
    3. Bezpośredni upload binarny na serwer rupload.facebook.com.
    4. Finalizacja i publikacja lub planowanie (POST /{page_id}/video_reels?upload_phase=finish).
    5. Wgranie i przypięcie dedykowanej miniaturki (POST /{video_id}/thumbnails).
    6. Pobranie permalinku opublikowanego posta/reels.
    """
    vp = Path(video_path)
    if not vp.exists():
        return {"success": False, "error": f"Plik wideo nie istnieje: {video_path}", "platform": "facebook"}

    file_size = vp.stat().st_size
    if file_size == 0:
        return {"success": False, "error": f"Plik wideo jest pusty: {video_path}", "platform": "facebook"}

    if publish_at and use_local_queue:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            scheduled_ts = int(dt.timestamp())
            if scheduled_ts > int(time.time()) + 600:
                from lol_agent.scheduled_queue import queue_scheduled_post
                entry = queue_scheduled_post(
                    platform="facebook",
                    video_path=str(vp),
                    caption=caption,
                    publish_at=publish_at,
                    thumbnail_path=thumbnail_path,
                )
                print(f"⏰ Facebook Reel dodany do kolejki planowania na: {dt.isoformat()}")
                return {
                    "success": True,
                    "queued": True,
                    "is_scheduled": True,
                    "publish_at": publish_at,
                    "queue_id": entry["id"],
                    "platform": "facebook",
                    "page_name": "Queued",
                    "message": f"Zaplanowano w kolejce publikacji FB na {dt.strftime('%Y-%m-%d %H:%M')}",
                }
        except Exception as _qe:
            print(f"⚠️ Kolejka planowania Facebook ({publish_at}): {_qe}. Kontynuuję standardowy upload.")

    token_data = load_facebook_token()
    if not token_data:
        return {
            "success": False,
            "error": "Brak konfiguracji Facebook Page w accounts/facebook_token.json",
            "platform": "facebook"
        }

    access_token = token_data["access_token"]
    page_id = token_data["page_id"]
    page_name = token_data.get("page_name", "Fanpage")

    print(f"📘 Rozpoczynam publikację Reel na Facebook Page ({page_name}, ID: {page_id})...")
    print(f"📦 Rozmiar pliku: {file_size / (1024 * 1024):.2f} MB | {vp.name}")

    # ── Krok 1: Inicjalizacja uploadu Video Reels ────────────────────────────
    init_url = f"{GRAPH_API_BASE}/{page_id}/video_reels"
    init_params = {
        "upload_phase": "start",
        "access_token": access_token
    }

    try:
        resp = requests.post(init_url, data=init_params, timeout=30)
        res_json = resp.json()
        if resp.status_code != 200 or "video_id" not in res_json:
            err = res_json.get("error", {}).get("message", resp.text)
            print(f"❌ Błąd inicjalizacji Video Reel FB: {err}")
            # Fallback do standardowego endpointu /videos
            return _upload_facebook_video_fallback(vp, caption, access_token, page_id, publish_at=publish_at, thumbnail_path=thumbnail_path)

        video_id = res_json["video_id"]
        upload_url = res_json.get("upload_url")
        print(f"✅ Inicjalizacja FB Reel udana! Video ID: {video_id}")
    except Exception as e:
        print(f"❌ Wyjątek przy inicjalizacji FB Reel: {e}")
        return {"success": False, "error": str(e), "platform": "facebook"}

    # ── Krok 2: Upload binarny do rupload.facebook.com ───────────────────────
    if not upload_url:
        upload_url = f"https://rupload.facebook.com/video-upload/{GRAPH_API_VERSION}/{video_id}"

    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }

    print("🚀 Wysyłam strumień wideo do serwera Meta...")
    try:
        with open(vp, "rb") as video_file:
            up_resp = requests.post(
                upload_url,
                headers=upload_headers,
                data=video_file,
                timeout=timeout
            )
        if up_resp.status_code not in (200, 201):
            print(f"❌ Błąd przesyłania wideo FB ({up_resp.status_code}): {up_resp.text}")
            return {
                "success": False,
                "error": f"Błąd transferu pliku (kod {up_resp.status_code}): {up_resp.text}",
                "platform": "facebook"
            }
        print("✅ Plik wideo przesłany pomyślnie do Meta!")
    except Exception as e:
        print(f"❌ Wyjątek podczas wysyłania pliku: {e}")
        return {"success": False, "error": f"Błąd połączenia rupload: {e}", "platform": "facebook"}

    # ── Krok 3: Finalizacja i publikacja lub planowanie Reels ─────────────────
    finish_url = f"{GRAPH_API_BASE}/{page_id}/video_reels"
    finish_params = {
        "upload_phase": "finish",
        "video_id": video_id,
        "description": caption,
        "access_token": access_token
    }

    is_scheduled = False
    if publish_at:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            scheduled_ts = int(dt.timestamp())
            now_ts = int(time.time())
            # Meta wymaga daty planowania min. 10 minut i maks. 75 dni w przyszłości
            if scheduled_ts > now_ts + 600:
                finish_params["video_state"] = "SCHEDULED"
                finish_params["scheduled_publish_time"] = str(scheduled_ts)
                is_scheduled = True
                print(f"⏰ Planuję Facebook Reel na: {dt.strftime('%Y-%m-%d %H:%M UTC')} (timestamp: {scheduled_ts})")
            else:
                finish_params["video_state"] = "PUBLISHED"
        except Exception as _pe:
            print(f"⚠️ Nieprawidłowa data publish_at ({publish_at}): {_pe}. Publikuję od razu.")
            finish_params["video_state"] = "PUBLISHED"
    else:
        finish_params["video_state"] = "PUBLISHED"

    print("⏳ Finalizuję publikację Facebook Reel...")
    try:
        fin_resp = requests.post(finish_url, data=finish_params, timeout=30)
        fin_json = fin_resp.json()
        if fin_resp.status_code != 200 or not fin_json.get("success", False):
            err = fin_json.get("error", {}).get("message", fin_resp.text)
            print(f"❌ Błąd finalizacji FB Reel: {err}")
            return {"success": False, "error": f"Błąd finalizacji: {err}", "video_id": video_id, "platform": "facebook"}
        
        if is_scheduled:
            print(f"🎉 SUKCES! Facebook Reel ZAPLANOWANY na wybraną datę! Video ID: {video_id}")
        else:
            print(f"🎉 SUKCES! Facebook Reel opublikowany! Video ID: {video_id}")
    except Exception as e:
        print(f"❌ Wyjątek podczas finalizacji FB Reel: {e}")
        return {"success": False, "error": str(e), "platform": "facebook"}

    # ── Krok 4: Wgranie dedykowanej miniatury ────────────────────────────────
    if thumbnail_path and os.path.exists(thumbnail_path):
        print(f"🖼️ Wgrywam miniaturkę dla Facebook Reel: {Path(thumbnail_path).name}...")
        try:
            thumb_url = f"{GRAPH_API_BASE}/{video_id}/thumbnails"
            with open(thumbnail_path, "rb") as tf:
                files = {"source": (Path(thumbnail_path).name, tf, "image/jpeg")}
                data = {"is_preferred": "true", "access_token": access_token}
                t_resp = requests.post(thumb_url, files=files, data=data, timeout=30)
                if t_resp.status_code == 200:
                    print("✅ Miniaturka dla Facebook Reel dodana pomyślnie!")
                else:
                    print(f"⚠️ Odpowiedź uploadu miniatury FB: {t_resp.status_code} {t_resp.text}")
        except Exception as _terr:
            print(f"⚠️ Wyjątek wgrywania miniatury FB: {_terr}")

    # ── Krok 5: Pobranie permalinku posta ─────────────────────────────────────
    post_url = f"https://www.facebook.com/{page_id}/videos/{video_id}"
    try:
        info_resp = requests.get(
            f"{GRAPH_API_BASE}/{video_id}",
            params={"fields": "permalink_url", "access_token": access_token},
            timeout=10
        )
        if info_resp.status_code == 200:
            raw_perm = info_resp.json().get("permalink_url") or ""
            if raw_perm.startswith("/"):
                raw_perm = f"https://www.facebook.com{raw_perm}"
            if raw_perm:
                post_url = raw_perm
    except Exception:
        pass

    return {
        "success": True,
        "video_id": video_id,
        "url": post_url,
        "page_id": page_id,
        "page_name": page_name,
        "platform": "facebook",
        "caption": caption[:100],
        "is_scheduled": is_scheduled,
        "publish_at": publish_at if is_scheduled else None,
    }


def _upload_facebook_video_fallback(
    vp: Path,
    caption: str,
    access_token: str,
    page_id: str,
    publish_at: Optional[str] = None,
    thumbnail_path: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback publikacji przez standardowy endpoint /{page_id}/videos."""
    print("🔄 Próbuję alternatywnego uploadu przez /{page_id}/videos...")
    try:
        url = f"{GRAPH_VIDEO_BASE}/{page_id}/videos"
        with open(vp, "rb") as f:
            files = {"source": (vp.name, f, "video/mp4")}
            data: Dict[str, Any] = {"description": caption, "access_token": access_token}
            
            is_scheduled = False
            if publish_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
                    scheduled_ts = int(dt.timestamp())
                    if scheduled_ts > int(time.time()) + 600:
                        data["published"] = "false"
                        data["scheduled_publish_time"] = str(scheduled_ts)
                        is_scheduled = True
                except Exception:
                    pass

            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    with open(thumbnail_path, "rb") as tf:
                        files["thumb"] = (Path(thumbnail_path).name, tf.read(), "image/jpeg")
                except Exception:
                    pass

            r = requests.post(url, files=files, data=data, timeout=300)
        if r.status_code in (200, 201) and "id" in r.json():
            vid = r.json()["id"]
            return {
                "success": True,
                "video_id": vid,
                "url": f"https://www.facebook.com/{page_id}/videos/{vid}",
                "page_id": page_id,
                "platform": "facebook",
                "is_scheduled": is_scheduled,
                "publish_at": publish_at if is_scheduled else None,
            }
        return {"success": False, "error": r.text, "platform": "facebook"}
    except Exception as e:
        return {"success": False, "error": str(e), "platform": "facebook"}
