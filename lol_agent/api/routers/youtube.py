"""
Shortsyt API — Router: YouTube Upload, OAuth, Peak Slots & Comments
"""
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException

from ..auth import verify_token
from ..config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
from ..helpers import _record_publication, set_push_token
from ..models import (
    YouTubeAuthCodeRequest, YouTubeUploadRequest,
    PostCommentRequest, RegisterPushTokenRequest
)
from ..youtube_uploader import (
    get_token_status, get_auth_url, exchange_auth_code, upload_video,
    get_next_optimal_publish_time, post_pinned_comment, flush_pending_comments
)

router = APIRouter(tags=["YouTube"])


@router.get("/youtube/token-status")
def yt_token_status(payload: dict = Depends(verify_token)):
    """Status tokenu YouTube — ile dni do wygaśnięcia."""
    return get_token_status()


@router.get("/youtube/auth-url")
def yt_auth_url(payload: dict = Depends(verify_token)):
    """Pobierz URL do autoryzacji YouTube OAuth."""
    try:
        url = get_auth_url()
        return {"auth_url": url}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/youtube/auth-code")
def yt_exchange_code(req: YouTubeAuthCodeRequest, payload: dict = Depends(verify_token)):
    """Wymień kod autoryzacji YouTube na token."""
    try:
        result = exchange_auth_code(req.code)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/youtube/upload/{filename}")
async def yt_upload(filename: str, req: YouTubeUploadRequest, payload: dict = Depends(verify_token)):
    """Upload Shorta na YouTube (async — uruchamia upload w thread pool)."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    video_path = None
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            video_path = str(fp)
            break

    if not video_path:
        raise HTTPException(status_code=404, detail=f"Plik nie znaleziony: {filename}")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: upload_video(
                video_path=video_path,
                title=req.title,
                description=req.description,
                tags=req.tags,
                privacy=req.privacy,
                pinned_comment=req.pinned_comment,
                thumbnail_path=req.thumbnail_path,
                publish_at=req.publish_at,
            )
        )

        try:
            _record_publication(video_path=video_path, filename=filename, result=result, req=req)
        except Exception as pe:
            print(f"[YouTube] ⚠️ Błąd zapisywania historii publikacji: {pe}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/youtube/flush-comments")
async def yt_flush_comments(payload: dict = Depends(verify_token)):
    """Sprawdź kolejkę zaplanowanych komentarzy i dodaj je do filmów, które stały się publiczne."""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, flush_pending_comments)
    return res


@router.post("/youtube/video/{video_id}/comment")
async def yt_post_comment(video_id: str, req: PostCommentRequest, payload: dict = Depends(verify_token)):
    """Dodaj przypięty komentarz do konkretnego filmu na YouTube."""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: post_pinned_comment(video_id, req.text))
    return res


@router.get("/youtube/next-peak-slot")
def get_next_peak_slot(payload: dict = Depends(verify_token)):
    """Pobierz najbliższy optymalny slot godzinowy (Peak Hours) dla publikacji YouTube Shorts."""
    return get_next_optimal_publish_time()


@router.post("/push/register", tags=["Notifications"])
def register_push_token(req: RegisterPushTokenRequest, payload: dict = Depends(verify_token)):
    """Zarejestruj Expo Push Token urządzenia."""
    set_push_token(req.expo_token)
    return {"status": "registered", "token": req.expo_token}
