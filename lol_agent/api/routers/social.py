"""
Shortsyt API — Router: Multi-Platform Publishing (YouTube Shorts, TikTok, Instagram Reels)
"""
import asyncio
import html
import os
import json
import re
import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import verify_token, verify_token_flexible
from ..config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
from ..helpers import _record_publication, _load_meta, _save_meta, _archive_and_schedule_48h
from ..models import (
    TikTokAuthCodeRequest,
    TikTokUploadRequest,
    InstagramUploadRequest,
    MultiPlatformUploadRequest
)
from ...tiktok_publisher import (
    get_tiktok_token_status, get_tiktok_creator_info, get_tiktok_user_info,
    upload_tiktok_short, TIKTOK_CLIENT_KEY, ACCOUNTS_DIR, TIKTOK_TOKEN_PATH
)
from ...instagram_publisher import (
    get_instagram_token_status, upload_instagram_reel
)
from ...facebook_publisher import (
    get_facebook_token_status, upload_facebook_reel
)
from ..models import FacebookUploadRequest
from ...multi_publisher import publish_multi_platform
from ..youtube_uploader import get_token_status as get_yt_token_status

router = APIRouter(tags=["Social & Multi-Platform"])
PUBLISHED_VIDEOS_PATH = Path(__file__).resolve().parent.parent.parent / "published_videos.jsonl"


@router.get("/social/status")
def social_overview(payload: dict = Depends(verify_token)):
    """Przegląd statusu połączenia wszystkich platform (YouTube, TikTok, Instagram)."""
    yt_stat = get_yt_token_status()
    tt_stat = get_tiktok_token_status()
    ig_stat = get_instagram_token_status()
    fb_stat = get_facebook_token_status()
    return {
        "youtube": yt_stat,
        "tiktok": tt_stat,
        "instagram": ig_stat,
        "facebook": fb_stat
    }


class MetaTokenSetupRequest(BaseModel):
    user_token: str


@router.post("/social/meta/setup-token")
def setup_meta_token_endpoint(req: MetaTokenSetupRequest, payload: dict = Depends(verify_token)):
    """Wymienia User Token z Graph API Explorer na wieczny Page Token dla FB i IG."""
    from scripts.authorize_instagram import setup_instagram_token
    try:
        token_payload = setup_instagram_token(req.user_token.strip())
        return {
            "success": True,
            "username": token_payload.get("username"),
            "page_id": token_payload.get("page_id"),
            "message": "Token Meta pomyślnie odświeżony!"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==============================================================================
# TIKTOK ENDPOINTS (Real OAuth 2.0 PKCE + localhost:8180 Callback)
# ==============================================================================

TIKTOK_OAUTH_REDIRECT_URI = "http://localhost:8180/callback"
TIKTOK_OAUTH_PORT = 8180
TIKTOK_OAUTH_SCOPE = "user.info.basic,video.publish,video.upload"
_PKCE_TTL_SECONDS = 600.0

_TIKTOK_PKCE_LOCK = threading.Lock()
_TIKTOK_PKCE_STORE: Dict[str, Tuple[str, float]] = {}
_TIKTOK_OAUTH_SERVER: Optional[HTTPServer] = None
_TIKTOK_OAUTH_THREAD: Optional[threading.Thread] = None
_TIKTOK_OAUTH_STOP_EVENT: Optional[threading.Event] = None
_TIKTOK_OAUTH_STATE: Dict[str, Any] = {
    "listening": False,
    "last_status": "idle",
    "last_error": None,
}


class _ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


def _prune_expired_pkce_locked(now: Optional[float] = None) -> None:
    ts = now if now is not None else time.time()
    expired = [k for k, (_, created) in _TIKTOK_PKCE_STORE.items() if ts - created > _PKCE_TTL_SECONDS]
    for k in expired:
        _TIKTOK_PKCE_STORE.pop(k, None)


def _create_tiktok_pkce_auth_url() -> Dict[str, str]:
    from scripts.authorize_tiktok import generate_pkce_pair

    client_key = os.getenv("TIKTOK_CLIENT_KEY", "").strip() or TIKTOK_CLIENT_KEY
    if not client_key:
        raise HTTPException(
            status_code=500,
            detail="Brak TIKTOK_CLIENT_KEY w konfiguracji środowiska (.env).",
        )

    verifier, challenge = generate_pkce_pair()
    state = f"shortsyt_{secrets.token_urlsafe(12)}"
    with _TIKTOK_PKCE_LOCK:
        _prune_expired_pkce_locked()
        _TIKTOK_PKCE_STORE[state] = (verifier, time.time())

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={urllib.parse.quote(client_key, safe='')}"
        f"&scope={TIKTOK_OAUTH_SCOPE}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(TIKTOK_OAUTH_REDIRECT_URI, safe='')}"
        f"&state={urllib.parse.quote(state, safe='')}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )
    return {
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": TIKTOK_OAUTH_REDIRECT_URI,
    }


def _stop_tiktok_oauth_listener_locked() -> None:
    global _TIKTOK_OAUTH_SERVER, _TIKTOK_OAUTH_THREAD, _TIKTOK_OAUTH_STOP_EVENT
    if _TIKTOK_OAUTH_STOP_EVENT is not None:
        _TIKTOK_OAUTH_STOP_EVENT.set()
    if _TIKTOK_OAUTH_SERVER is not None:
        try:
            _TIKTOK_OAUTH_SERVER.server_close()
        except Exception:
            pass
        _TIKTOK_OAUTH_SERVER = None
    old_thread = _TIKTOK_OAUTH_THREAD
    _TIKTOK_OAUTH_THREAD = None
    if old_thread is not None and old_thread.is_alive() and old_thread is not threading.current_thread():
        old_thread.join(timeout=1.5)
    _TIKTOK_OAUTH_STATE["listening"] = False


def _start_tiktok_oauth_callback_listener(timeout_sec: float = 180.0) -> Tuple[bool, Optional[str]]:
    global _TIKTOK_OAUTH_SERVER, _TIKTOK_OAUTH_THREAD, _TIKTOK_OAUTH_STOP_EVENT
    from scripts.authorize_tiktok import exchange_code_for_token

    with _TIKTOK_PKCE_LOCK:
        _stop_tiktok_oauth_listener_locked()
        stop_event = threading.Event()
        _TIKTOK_OAUTH_STOP_EVENT = stop_event

        class _OAuthCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return

                params = urllib.parse.parse_qs(parsed.query)
                if "error" in params:
                    err_raw = params.get("error_description", params.get("error", ["OAuth error"]))[0]
                    err_safe = html.escape(str(err_raw))
                    _TIKTOK_OAUTH_STATE["last_status"] = "error"
                    _TIKTOK_OAUTH_STATE["last_error"] = str(err_raw)
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    body = (
                        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>TikTok OAuth Error</title></head>"
                        "<body style='background:#050505;color:#FF5C5C;font-family:sans-serif;text-align:center;padding:48px;'>"
                        f"<h1>Błąd autoryzacji TikTok</h1><p>{err_safe}</p></body></html>"
                    )
                    self.wfile.write(body.encode("utf-8"))
                    stop_event.set()
                    return

                code = (params.get("code") or [""])[0].strip()
                state_param = (params.get("state") or [""])[0].strip()
                if not code:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"Missing authorization code.")
                    return

                verifier = None
                with _TIKTOK_PKCE_LOCK:
                    _prune_expired_pkce_locked()
                    if state_param:
                        entry = _TIKTOK_PKCE_STORE.pop(state_param, None)
                        if entry:
                            verifier = entry[0]
                    elif _TIKTOK_PKCE_STORE:
                        latest_key = max(_TIKTOK_PKCE_STORE.keys(), key=lambda k: _TIKTOK_PKCE_STORE[k][1])
                        verifier = _TIKTOK_PKCE_STORE.pop(latest_key)[0]

                if not verifier:
                    _TIKTOK_OAUTH_STATE["last_status"] = "error"
                    _TIKTOK_OAUTH_STATE["last_error"] = "Invalid or expired PKCE OAuth state."
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    body = (
                        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>TikTok OAuth State Error</title></head>"
                        "<body style='background:#050505;color:#FF5C5C;font-family:sans-serif;text-align:center;padding:48px;'>"
                        "<h1>Sesja OAuth wygasła lub ma nieprawidłowy state</h1>"
                        "<p>Wróć do Flikcut Studio i kliknij Connect / Authorize ponownie.</p></body></html>"
                    )
                    self.wfile.write(body.encode("utf-8"))
                    stop_event.set()
                    return

                try:
                    exchange_code_for_token(code, verifier)
                    _TIKTOK_OAUTH_STATE["last_status"] = "authorized"
                    _TIKTOK_OAUTH_STATE["last_error"] = None
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    body = (
                        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>TikTok OAuth Sukces</title></head>"
                        "<body style='background:#050505;color:#C8FF3A;font-family:sans-serif;text-align:center;padding:48px;'>"
                        "<h1>Autoryzacja TikTok OAuth 2.0 zakończona!</h1>"
                        "<p style='color:#E5E7EB;'>Token zapisany bezpiecznie w Flikcut Studio. Możesz zamknąć tę kartę.</p>"
                        "</body></html>"
                    )
                    self.wfile.write(body.encode("utf-8"))
                except Exception as exc:
                    _TIKTOK_OAUTH_STATE["last_status"] = "error"
                    _TIKTOK_OAUTH_STATE["last_error"] = str(exc)
                    err_safe = html.escape(str(exc))
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    body = (
                        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Błąd wymiany tokenu</title></head>"
                        "<body style='background:#050505;color:#FF5C5C;font-family:sans-serif;text-align:center;padding:48px;'>"
                        f"<h1>Nie udało się wymienić kodu na token</h1><p>{err_safe}</p></body></html>"
                    )
                    self.wfile.write(body.encode("utf-8"))
                finally:
                    stop_event.set()

        try:
            server = _ReusableHTTPServer(("127.0.0.1", TIKTOK_OAUTH_PORT), _OAuthCallbackHandler)
        except OSError as exc:
            _TIKTOK_OAUTH_STATE["listening"] = False
            _TIKTOK_OAUTH_STATE["last_status"] = "error"
            _TIKTOK_OAUTH_STATE["last_error"] = str(exc)
            return False, f"Port {TIKTOK_OAUTH_PORT} jest zajęty: {exc}"

        server.timeout = 1.0
        _TIKTOK_OAUTH_SERVER = server
        _TIKTOK_OAUTH_STATE["listening"] = True
        _TIKTOK_OAUTH_STATE["last_status"] = "waiting"
        _TIKTOK_OAUTH_STATE["last_error"] = None

        def _serve_until_done():
            global _TIKTOK_OAUTH_SERVER
            deadline = time.monotonic() + max(10.0, float(timeout_sec))
            try:
                while not stop_event.is_set() and time.monotonic() < deadline:
                    try:
                        server.handle_request()
                    except OSError:
                        break
                    except Exception as exc:
                        _TIKTOK_OAUTH_STATE["last_error"] = str(exc)
                        break
                if not stop_event.is_set() and time.monotonic() >= deadline:
                    _TIKTOK_OAUTH_STATE["last_status"] = "timeout"
            finally:
                try:
                    server.server_close()
                except Exception:
                    pass
                with _TIKTOK_PKCE_LOCK:
                    if _TIKTOK_OAUTH_SERVER is server:
                        _TIKTOK_OAUTH_SERVER = None
                    _TIKTOK_OAUTH_STATE["listening"] = False

        th = threading.Thread(target=_serve_until_done, name="TikTokOAuthCallback8180", daemon=True)
        _TIKTOK_OAUTH_THREAD = th
        th.start()
        return True, None


@router.get("/social/tiktok/token-status")
def tiktok_token_status(payload: dict = Depends(verify_token)):
    """Status połączenia konta TikTok oraz bieżącej sesji OAuth 2.0 PKCE."""
    status = dict(get_tiktok_token_status())
    status["oauth_state"] = dict(_TIKTOK_OAUTH_STATE)
    return status


@router.get("/social/tiktok/creator-info")
def tiktok_creator_info(payload: dict = Depends(verify_token)):
    """Pobiera bieżące limity i dozwolone ustawienia prywatności z /v2/post/publish/creator_info/query/."""
    return get_tiktok_creator_info()


@router.get("/social/tiktok/user-info")
def tiktok_user_info(payload: dict = Depends(verify_token)):
    """Pobiera profil twórcy (avatar_url, display_name) z /v2/user/info/ w zakresie user.info.basic."""
    return get_tiktok_user_info()


@router.get("/social/tiktok/auth-url")
def tiktok_auth_url(payload: dict = Depends(verify_token)):
    """Generuje realny URL logowania TikTok OAuth 2.0 z PKCE (http://localhost:8180/callback)."""
    return _create_tiktok_pkce_auth_url()


@router.post("/social/tiktok/oauth/start")
def tiktok_oauth_start(payload: dict = Depends(verify_token)):
    """Generuje URL PKCE i uruchamia jednorazowy lokalny callback na porcie 8180."""
    auth_payload = _create_tiktok_pkce_auth_url()
    if os.getenv("PYTEST_CURRENT_TEST"):
        listener_started, listener_error = False, None
    else:
        listener_started, listener_error = _start_tiktok_oauth_callback_listener(timeout_sec=180.0)
    return {
        **auth_payload,
        "listening_port": TIKTOK_OAUTH_PORT,
        "listener_started": listener_started,
        "listener_error": listener_error,
    }


@router.post("/social/tiktok/auth-code")
def tiktok_exchange_code(req: TikTokAuthCodeRequest, payload: dict = Depends(verify_token)):
    """Wymienia odebrany kod autoryzacji TikToka na access token z użyciem PKCE code_verifier."""
    from scripts.authorize_tiktok import exchange_code_for_token

    verifier = (req.code_verifier or "").strip()
    with _TIKTOK_PKCE_LOCK:
        _prune_expired_pkce_locked()
        if not verifier and req.state and req.state in _TIKTOK_PKCE_STORE:
            verifier = _TIKTOK_PKCE_STORE.pop(req.state)[0]
        elif not verifier and _TIKTOK_PKCE_STORE:
            latest_key = max(_TIKTOK_PKCE_STORE.keys(), key=lambda k: _TIKTOK_PKCE_STORE[k][1])
            verifier = _TIKTOK_PKCE_STORE.pop(latest_key)[0]

    if not verifier:
        raise HTTPException(
            status_code=400,
            detail="Brak aktywnej sesji PKCE — najpierw wygeneruj link OAuth.",
        )

    try:
        tokens = exchange_code_for_token(req.code, verifier)
        return {
            "success": True,
            "open_id": tokens.get("open_id"),
            "scope": tokens.get("scope"),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/social/tiktok/upload/{filename}")
async def upload_to_tiktok(
    filename: str,
    req: TikTokUploadRequest,
    payload: dict = Depends(verify_token)
):
    """Upload pliku wideo bezpośrednio do TikToka."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    video_path = None
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            video_path = str(fp)
            break

    if not video_path:
        raise HTTPException(status_code=404, detail=f"Plik wideo nie istnieje: {filename}")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: upload_tiktok_short(
            video_path=video_path,
            title=req.title,
            hashtags=req.hashtags,
            privacy_level=req.privacy_level
        )
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Błąd uploadu na TikTok"))

    return result


# ==============================================================================
# INSTAGRAM ENDPOINTS
# ==============================================================================

@router.get("/social/instagram/token-status")
def instagram_token_status(payload: dict = Depends(verify_token)):
    """Status połączenia konta Instagram Reels."""
    return get_instagram_token_status()


@router.post("/social/instagram/upload/{filename}")
async def upload_to_instagram(
    filename: str,
    req: InstagramUploadRequest,
    payload: dict = Depends(verify_token)
):
    """Upload pliku wideo bezpośrednio do Instagram Reels."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    video_path = None
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            video_path = str(fp)
            break

    if not video_path:
        raise HTTPException(status_code=404, detail=f"Plik wideo nie istnieje: {filename}")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: upload_instagram_reel(
            video_path=video_path,
            caption=req.caption,
            share_to_feed=req.share_to_feed
        )
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Błąd uploadu na Instagram"))

    return result


# ==============================================================================
# FACEBOOK ENDPOINTS
# ==============================================================================

@router.get("/social/facebook/token-status")
def facebook_token_status(payload: dict = Depends(verify_token)):
    """Status połączenia i uprawnień strony Facebook."""
    return get_facebook_token_status()


@router.post("/social/facebook/upload/{filename}")
async def upload_to_facebook(
    filename: str,
    req: FacebookUploadRequest,
    payload: dict = Depends(verify_token)
):
    """Upload pliku wideo jako Facebook Reel / Post na fanpage."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    video_path = None
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            video_path = str(fp)
            break

    if not video_path:
        raise HTTPException(status_code=404, detail=f"Plik wideo nie istnieje: {filename}")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: upload_facebook_reel(
            video_path=video_path,
            caption=req.caption
        )
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Błąd uploadu na Facebook"))

    return result


# ==============================================================================
# MULTI-PLATFORM UNIFIED PUBLISH
# ==============================================================================

@router.post("/social/publish/{filename}")
async def publish_all(
    filename: str,
    req: MultiPlatformUploadRequest,
    payload: dict = Depends(verify_token)
):
    """Jednoczesna publikacja na wielu platformach (YouTube + TikTok + Instagram) w tle."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    video_path = None
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            video_path = str(fp)
            break

    if not video_path:
        raise HTTPException(status_code=404, detail=f"Plik wideo nie istnieje: {filename}")

    tt_post_mode = (req.tiktok_post_mode or "direct").strip().lower()
    if tt_post_mode not in {"direct", "inbox"}:
        raise HTTPException(
            status_code=400,
            detail="Nieprawidłowy tryb TikTok (tiktok_post_mode): dozwolone 'direct' lub 'inbox'.",
        )

    tt_privacy = (req.privacy_tiktok or "").strip()
    if "tiktok" in req.platforms and tt_post_mode == "direct":
        allowed_tt_privacy = {
            "PUBLIC_TO_EVERYONE",
            "MUTUAL_FOLLOW_FRIENDS",
            "FOLLOWER_OF_CREATOR",
            "SELF_ONLY",
        }
        if not tt_privacy or tt_privacy not in allowed_tt_privacy:
            raise HTTPException(
                status_code=400,
                detail="Wybierz prawidłowy poziom prywatności TikTok (privacy_tiktok).",
            )
        if req.tiktok_disclose_content and not (req.tiktok_brand_organic or req.tiktok_branded_content):
            raise HTTPException(
                status_code=400,
                detail="Przy włączonym Disclose video content wybierz Your brand i/lub Branded content.",
            )
        if req.tiktok_disclose_content and req.tiktok_branded_content and tt_privacy == "SELF_ONLY":
            raise HTTPException(
                status_code=400,
                detail="Branded content nie może mieć widoczności Only you (SELF_ONLY).",
            )

    meta = _load_meta(filename) or {}

    # Twarda blokada duplikatów: sprawdź czy wszystkie wybrane platformy zostały już opublikowane lub zakolejkowane
    done_plats: set[str] = set()
    try:
        done_plats = {str(p).strip().lower() for p in (meta.get("published_platforms") or []) if p}
        if meta.get("youtube_id"):
            done_plats.add("youtube")
        from ...scheduled_queue import QUEUE_FILE as _Q_FILE, _load_queue as _load_q
        if _Q_FILE.exists():
            vp_resolved = str(Path(video_path).resolve()).lower()
            for q_it in _load_q():
                if q_it.get("status") not in ("pending", "processing", "published"):
                    continue
                q_vp = str(q_it.get("video_path") or "").strip()
                if not q_vp:
                    continue
                try:
                    q_resolved = str(Path(q_vp).resolve()).lower()
                except Exception:
                    q_resolved = q_vp.lower()
                if q_resolved == vp_resolved:
                    done_plats.add(str(q_it.get("platform") or "").strip().lower())
        req_plats = {str(p).strip().lower() for p in (req.platforms or []) if p}
        if req_plats and req_plats.issubset(done_plats):
            raise HTTPException(
                status_code=409,
                detail="Ten klip został już opublikowany lub zakolejkowany na wszystkich wybranych platformach.",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    skipped_plats = [str(p).strip().lower() for p in (req.platforms or []) if str(p).strip().lower() in done_plats]
    active_plats = [str(p).strip().lower() for p in (req.platforms or []) if str(p).strip().lower() not in done_plats]
    if not active_plats:
        active_plats = list(req.platforms or [])

    champ = req.champion_name or meta.get("champion_name") or "Katarina"
    action = req.action_type or meta.get("action_type") or "pentakill"
    rnk = req.rank or meta.get("rank") or "Challenger"
    peak = meta.get("peak_moment") or meta.get("clip_peak")
    thumb_to_use = req.thumbnail_path or meta.get("thumbnail_path")
    if not thumb_to_use or not Path(str(thumb_to_use)).is_file():
        thumb_stem = Path(filename).stem
        for d in (LOL_TEMP_DIR, LOL_OUTPUT_DIR):
            cand_thumb = Path(d) / f"{thumb_stem}_thumb.jpg"
            if cand_thumb.is_file():
                thumb_to_use = str(cand_thumb)
                break

    # Gwarancja bogatych tagów YouTube (450+ znaków, canonical, bez #)
    tags_to_use = req.tags or meta.get("tags") or []
    if len(tags_to_use) < 10:
        try:
            from ...lol_metadata_generator import build_rich_youtube_tags
            tags_to_use = build_rich_youtube_tags(champ, action, rnk)
        except Exception:
            pass

    # Gwarancja przypiętego komentarza z lejkiem do FB, IG, TikTok
    pinned_to_use = req.pinned_comment or meta.get("pinned_comment")
    if not pinned_to_use:
        try:
            from ...lol_metadata_generator import build_pinned_comment
            pinned_to_use = build_pinned_comment(champ, action)
        except Exception:
            pass

    # Gwarancja opisu z linkami społecznościowymi
    desc_to_use = req.description or meta.get("description") or ""
    if "facebook.com/Dwannellenga" not in desc_to_use:
        try:
            from ...lol_metadata_generator import build_channel_description
            desc_to_use = build_channel_description(champ, action, desc_to_use)
        except Exception:
            pass

    # Normalizuj wszystkie hasztagi w tytule i opisie na kanoniczne małe litery
    title_to_use = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", req.title)
    desc_to_use = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", desc_to_use)

    has_custom_copy = any(
        bool(val and val.strip())
        for val in (req.tiktok_caption, req.instagram_caption, req.facebook_caption)
    )
    copy_override = None
    if has_custom_copy:
        try:
            from ...multi_platform_copywriter import generate_all_platform_copy
            copy_override = generate_all_platform_copy(
                champion=champ,
                action_type=action,
                base_metadata={"title": title_to_use, "description": desc_to_use, "tags": tags_to_use},
                platforms=active_plats,
            ) or {}
        except Exception:
            copy_override = {}

        if req.tiktok_caption and req.tiktok_caption.strip():
            raw_tt = req.tiktok_caption.strip()
            extracted_tags = [m.lower() for m in re.findall(r"#([a-zA-Z0-9_]+)", raw_tt)]
            clean_tt_line = re.sub(r"#\S+", "", raw_tt).strip()
            tt_entry = copy_override.setdefault("tiktok", {})
            tt_entry["title"] = clean_tt_line[:180] or title_to_use
            tt_entry["caption"] = raw_tt
            if extracted_tags:
                tt_entry["hashtags"] = extracted_tags[:8]

        if req.instagram_caption and req.instagram_caption.strip():
            raw_ig = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", req.instagram_caption.strip())
            copy_override.setdefault("instagram", {})["caption"] = raw_ig

        if req.facebook_caption and req.facebook_caption.strip():
            copy_override.setdefault("facebook", {})["caption"] = req.facebook_caption.strip()

    tt_brand_organic = bool(req.tiktok_disclose_content and req.tiktok_brand_organic)
    tt_brand_content = bool(req.tiktok_disclose_content and req.tiktok_branded_content)

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: publish_multi_platform(
            video_path=video_path,
            title=title_to_use,
            description=desc_to_use,
            tags=tags_to_use,
            hashtags=req.hashtags,
            platforms=active_plats,
            privacy_yt=req.privacy_yt,
            privacy_tiktok=tt_privacy if ("tiktok" in active_plats and tt_post_mode == "direct") else (tt_privacy or "PUBLIC_TO_EVERYONE"),
            share_to_ig_feed=req.share_to_ig_feed,
            thumbnail_path=thumb_to_use,
            publish_at=req.publish_at,
            copy_by_platform=copy_override,
            pinned_comment=pinned_to_use,
            champion_name=champ,
            action_type=action,
            rank=rnk,
            peak_moment=peak,
            tiktok_disable_comment=not req.tiktok_allow_comment,
            tiktok_disable_duet=not req.tiktok_allow_duet,
            tiktok_disable_stitch=not req.tiktok_allow_stitch,
            tiktok_brand_organic=tt_brand_organic,
            tiktok_brand_content=tt_brand_content,
            tiktok_post_mode=tt_post_mode,
        )
    )
    if not isinstance(results, dict):
        results = {}
    for sp in skipped_plats:
        results.setdefault(sp, {"success": True, "skipped_already_published": True, "message": "Już wcześniej opublikowano / w kolejce"})

    # Zapisz rezultaty w metadanych wideo oraz w historii publikacji
    try:
        meta = _load_meta(filename) or {}
        meta["multi_results"] = results
        successful_platforms = []

        if "youtube" in active_plats and results.get("youtube", {}).get("success"):
            meta["youtube_id"] = results["youtube"].get("video_id")
            meta["youtube_url"] = results["youtube"].get("url")
            successful_platforms.append("youtube")
        if "tiktok" in active_plats and results.get("tiktok", {}).get("success"):
            meta["tiktok_publish_id"] = results["tiktok"].get("publish_id")
            successful_platforms.append("tiktok")
        if "instagram" in active_plats and results.get("instagram", {}).get("success"):
            meta["instagram_media_id"] = results["instagram"].get("media_id") or results["instagram"].get("id")
            meta["instagram_url"] = results["instagram"].get("url")
            successful_platforms.append("instagram")
        if "facebook" in active_plats and results.get("facebook", {}).get("success"):
            meta["facebook_post_id"] = results["facebook"].get("post_id") or results["facebook"].get("video_id") or results["facebook"].get("id")
            meta["facebook_url"] = results["facebook"].get("url")
            successful_platforms.append("facebook")

        newly_failed = {
            p: str((results.get(p) or {}).get("error") or "Błąd publikacji")
            for p in active_plats
            if not (results.get(p) or {}).get("success")
        }
        existing_failed = {
            str(k).strip().lower(): str(v)
            for k, v in (meta.get("failed_platforms") or {}).items()
            if k
        }
        for sp_ok in successful_platforms:
            existing_failed.pop(sp_ok, None)
        for sp_skip in skipped_plats:
            existing_failed.pop(sp_skip, None)
        existing_failed.update(newly_failed)

        existing_plats = {str(p).strip().lower() for p in (meta.get("published_platforms") or []) if p}
        if meta.get("youtube_id"):
            existing_plats.add("youtube")
        merged_plats = sorted(existing_plats | set(successful_platforms))

        meta["failed_platforms"] = existing_failed
        if successful_platforms:
            meta["published_at"] = datetime.now(timezone.utc).isoformat()
            meta["published_platforms"] = merged_plats
            if req.publish_at:
                meta["scheduled_publish_at"] = req.publish_at
        _save_meta(filename, meta)

        if successful_platforms:
            pub_log = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "video_id": results.get("youtube", {}).get("video_id") or meta.get("youtube_id"),
                "url": results.get("youtube", {}).get("url") or meta.get("youtube_url") or results.get("facebook", {}).get("url") or results.get("instagram", {}).get("url"),
                "title": req.title,
                "action_type": meta.get("action_type", "outplay"),
                "champion": meta.get("champion_name", "Katarina"),
                "thumbnail": req.thumbnail_path or meta.get("thumbnail_path"),
                "status": "scheduled" if req.publish_at else "published",
                "privacy": req.privacy_yt,
                "scheduled_publish_at": req.publish_at,
                "source_path": meta.get("source_path", ""),
                "initial_qa_score": int(meta.get("qa_score") or 100),
                "qa_status": meta.get("qa_status", "PASS"),
                "duration_s": float(meta.get("duration") or 15.0),
                "hook_text": meta.get("hook_text", ""),
                "platforms": merged_plats,
                "multi_results": results
            }
            pub_path = PUBLISHED_VIDEOS_PATH
            with open(pub_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")

            # Archiwizacja .recipe.json (ID wszystkich platform) + Bramka 48h — jak w /youtube/upload
            try:
                primary_id = results.get("youtube", {}).get("video_id")
                if primary_id:
                    platform_ids = {
                        "video_id": primary_id,
                        "url": results["youtube"].get("url"),
                        "tiktok": results.get("tiktok") if results.get("tiktok", {}).get("success") else None,
                        "instagram": results.get("instagram") if results.get("instagram", {}).get("success") else None,
                        "facebook": results.get("facebook") if results.get("facebook", {}).get("success") else None,
                        "scheduled_publish_at": req.publish_at,
                    }
                    platform_ids = {k: v for k, v in platform_ids.items() if v is not None}
                    _archive_and_schedule_48h(
                        video_path,
                        primary_id,
                        results["youtube"],
                        results["youtube"].get("title") or title_to_use,
                        meta,
                        platform_ids=platform_ids,
                    )
            except Exception as arch_err:
                print(f"⚠️ [social.publish] Błąd archiwizacji recipe / Bramki 48h: {arch_err}")

            if ("youtube" in merged_plats) or (not existing_failed and bool(merged_plats)):
                try:
                    from ..helpers import record_processed_source_hash
                    src_p = str(meta.get("source_path") or "")
                    if src_p:
                        record_processed_source_hash(
                            src_p,
                            video_id=results.get("youtube", {}).get("video_id") or meta.get("youtube_id") or meta.get("tiktok_publish_id"),
                            url=pub_log.get("url"),
                        )
                except Exception:
                    pass

            if not existing_failed:
                try:
                    from lol_agent.temp_cleaner import cleanup_published_video_if_idle
                    from ...scheduled_queue import QUEUE_FILE as _SQ_QUEUE_FILE
                    cleanup_published_video_if_idle(video_path, queue_file=_SQ_QUEUE_FILE)
                except Exception as clean_err:
                    print(f"⚠️ [social.publish] Auto-czyszczenie .mp4 pominięte: {clean_err}")

            try:
                from lol_agent.api.youtube_uploader import invalidate_publish_cache
                invalidate_publish_cache()
            except Exception:
                pass
    except Exception as save_err:
        print(f"⚠️ [social.publish] Błąd zapisu historii: {save_err}")

    return {
        "filename": filename,
        "results": results
    }

@router.get("/social/analytics")
def get_social_analytics(platform: str = "all", refresh: bool = False, payload: dict = Depends(verify_token_flexible)):
    """Pobiera rzeczywiste statystyki z wybranej platformy społecznościowej lub panelu Omnichannel."""
    from ...social_analytics import (
        get_instagram_analytics, get_facebook_analytics,
        get_tiktok_analytics, get_omnichannel_analytics
    )
    if platform == "instagram":
        return get_instagram_analytics(force_refresh=refresh)
    elif platform == "facebook":
        return get_facebook_analytics(force_refresh=refresh)
    elif platform == "tiktok":
        return get_tiktok_analytics(force_refresh=refresh)
    else:
        return get_omnichannel_analytics(force_refresh=refresh)


class SocialCopyPreviewRequest(BaseModel):
    title: str
    champion_name: str = "Katarina"
    action_type: str = "outplay"


@router.get("/social/queue")
def get_social_queue(payload: dict = Depends(verify_token_flexible)):
    """Zwraca kolejkę zaplanowanych publikacji TikTok/Instagram/Facebook wraz z podsumowaniem."""
    from ...scheduled_queue import _load_queue, _QUEUE_LOCK
    with _QUEUE_LOCK:
        items = list(_load_queue())
    items.sort(key=lambda x: str(x.get("publish_at") or ""), reverse=True)
    summary = {
        "total": len(items),
        "pending": sum(1 for i in items if i.get("status") == "pending"),
        "published": sum(1 for i in items if i.get("status") == "published"),
        "failed": sum(1 for i in items if i.get("status") == "failed"),
    }
    return {"items": items, "summary": summary}


@router.post("/social/queue/flush")
async def flush_social_queue_endpoint(payload: dict = Depends(verify_token_flexible)):
    """Ręcznie uruchamia wysyłkę zaległych pozycji z kolejki TikTok/IG/FB oraz przypiętych komentarzy YT."""
    from ...scheduled_queue import check_and_flush_scheduled_posts
    from ..youtube_uploader import flush_pending_comments

    loop = asyncio.get_event_loop()
    flushed_posts = await loop.run_in_executor(None, check_and_flush_scheduled_posts)
    flushed_comments = await loop.run_in_executor(None, flush_pending_comments)
    fc_count = (
        len(flushed_comments.get("sent") or [])
        if isinstance(flushed_comments, dict)
        else int(flushed_comments or 0)
    )
    return {
        "ok": True,
        "flushed_posts": int(flushed_posts or 0),
        "flushed_comments": fc_count,
    }


@router.post("/social/preview-copy")
def preview_social_copy(req: SocialCopyPreviewRequest, payload: dict = Depends(verify_token_flexible)):
    """Generuje deterministyczny podgląd opisu + hashtagów dla TikTok, Instagram i Facebooka."""
    from ...multi_platform_copywriter import generate_all_platform_copy
    copies = generate_all_platform_copy(
        champion=req.champion_name or "Katarina",
        action_type=req.action_type or "outplay",
        base_metadata={"title": req.title or ""},
        platforms=["tiktok", "instagram", "facebook"],
    )
    tt = copies.get("tiktok", {})
    tt_tags = " ".join(f"#{t}" for t in (tt.get("hashtags") or []))
    tt_copy_text = f"{tt.get('title', '').strip()}\n{tt_tags}".strip()
    return {
        "tiktok_copy_text": tt_copy_text,
        "copies": copies,
    }

