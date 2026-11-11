"""
Shortsyt API — Router: Multi-Platform Publishing (YouTube Shorts, TikTok, Instagram Reels)
"""
import asyncio
import os
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import verify_token, verify_token_flexible
from ..config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
from ..helpers import _record_publication, _load_meta, _save_meta
from ..models import (
    TikTokAuthCodeRequest,
    TikTokUploadRequest,
    InstagramUploadRequest,
    MultiPlatformUploadRequest
)
from ...tiktok_publisher import (
    get_tiktok_token_status, upload_tiktok_short, TIKTOK_CLIENT_KEY,
    ACCOUNTS_DIR, TIKTOK_TOKEN_PATH
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
# TIKTOK ENDPOINTS
# ==============================================================================

@router.get("/social/tiktok/token-status")
def tiktok_token_status(payload: dict = Depends(verify_token)):
    """Status połączenia konta TikTok."""
    return get_tiktok_token_status()


@router.get("/social/tiktok/auth-url")
def tiktok_auth_url(payload: dict = Depends(verify_token)):
    """Generuje URL do logowania OAuth 2.0 z TikTokiem."""
    if not TIKTOK_CLIENT_KEY:
        raise HTTPException(
            status_code=500,
            detail="Brak TIKTOK_CLIENT_KEY w konfiguracji środowiska (.env)."
        )

    redirect_uri = "https://battlemetal.github.io/Shortsyt/callback"
    scope = "user.info.basic,video.publish,video.upload"
    state = "shortsyt_api"

    url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={TIKTOK_CLIENT_KEY}"
        f"&scope={scope}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        f"&state={state}"
    )
    return {"auth_url": url}


@router.post("/social/tiktok/auth-code")
def tiktok_exchange_code(req: TikTokAuthCodeRequest, payload: dict = Depends(verify_token)):
    """Wymienia odebrany kod autoryzacji TikToka na access token."""
    from scripts.authorize_tiktok import exchange_code_for_token
    try:
        tokens = exchange_code_for_token(req.code)
        return {
            "success": True,
            "open_id": tokens.get("open_id"),
            "scope": tokens.get("scope")
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

    meta = _load_meta(filename) or {}
    champ = req.champion_name or meta.get("champion_name") or "Katarina"
    action = req.action_type or meta.get("action_type") or "pentakill"
    rnk = req.rank or meta.get("rank") or "Challenger"
    peak = meta.get("peak_moment") or meta.get("clip_peak")
    thumb_to_use = req.thumbnail_path or meta.get("thumbnail_path")

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
    import re
    title_to_use = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", req.title)
    desc_to_use = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", desc_to_use)

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: publish_multi_platform(
            video_path=video_path,
            title=title_to_use,
            description=desc_to_use,
            tags=tags_to_use,
            hashtags=req.hashtags,
            platforms=req.platforms,
            privacy_yt=req.privacy_yt,
            privacy_tiktok=req.privacy_tiktok,
            share_to_ig_feed=req.share_to_ig_feed,
            thumbnail_path=thumb_to_use,
            publish_at=req.publish_at,
            pinned_comment=pinned_to_use,
            champion_name=champ,
            action_type=action,
            rank=rnk,
            peak_moment=peak,
        )
    )

    # Zapisz rezultaty w metadanych wideo oraz w historii publikacji
    try:
        meta = _load_meta(filename) or {}
        meta["multi_results"] = results
        successful_platforms = []

        if results.get("youtube", {}).get("success"):
            meta["youtube_id"] = results["youtube"].get("video_id")
            meta["youtube_url"] = results["youtube"].get("url")
            successful_platforms.append("youtube")
        if results.get("tiktok", {}).get("success"):
            meta["tiktok_publish_id"] = results["tiktok"].get("publish_id")
            successful_platforms.append("tiktok")
        if results.get("instagram", {}).get("success"):
            meta["instagram_media_id"] = results["instagram"].get("media_id") or results["instagram"].get("id")
            meta["instagram_url"] = results["instagram"].get("url")
            successful_platforms.append("instagram")
        if results.get("facebook", {}).get("success"):
            meta["facebook_post_id"] = results["facebook"].get("post_id") or results["facebook"].get("video_id") or results["facebook"].get("id")
            meta["facebook_url"] = results["facebook"].get("url")
            successful_platforms.append("facebook")

        if successful_platforms:
            meta["published_at"] = datetime.now(timezone.utc).isoformat()
            meta["published_platforms"] = successful_platforms
            if req.publish_at:
                meta["scheduled_publish_at"] = req.publish_at
            _save_meta(filename, meta)

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
                "platforms": successful_platforms,
                "multi_results": results
            }
            pub_path = Path(__file__).resolve().parent.parent.parent / "published_videos.jsonl"
            with open(pub_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")
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

