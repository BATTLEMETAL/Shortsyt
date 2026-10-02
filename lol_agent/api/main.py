"""
Shortsyt API — główny serwer FastAPI (Modular APIRouters)
Uruchom: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from .config import ALLOWED_ORIGINS
from .helpers import (
    DARK_ROOT, _meta_path_for, _save_meta, _load_meta,
    _record_publication, _push_token, _dark_load_json,
    _sync_youtube_analytics, TUNING_FILE, DEFAULT_TUNING_CONFIG
)
from .models import (
    LoginRequest, LoginResponse, PipelineStartRequest,
    YouTubeAuthCodeRequest, YouTubeUploadRequest, PostCommentRequest,
    RegisterPushTokenRequest, AutoDetectRequest, SaveMetadataRequest,
    UserCorrectionRequest, DarkRunRequest, ReserveSlotRequest,
    AnalyzeFragRequest, AutoFillCalendarRequest
)
from .youtube_uploader import flush_pending_comments

# Routers
from .routers import auth, pipeline, clips, youtube, calendar, learning, system
from .routers.clips import list_clips, auto_detect_clip, scan_available_clips


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza cyklem życia aplikacji — procesy w tle i czyszczenie."""
    import asyncio
    stop_event = asyncio.Event()

    async def _flusher_loop():
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
                break
            except asyncio.TimeoutError:
                pass
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, flush_pending_comments)
            except Exception as e:
                import logging
                logging.getLogger("shortsyt.flusher").debug("Comment flush check: %s", e)

    flusher_task = asyncio.create_task(_flusher_loop())
    yield
    stop_event.set()
    flusher_task.cancel()
    try:
        await flusher_task
    except asyncio.CancelledError:
        pass


tags_metadata = [
    {"name": "Auth", "description": "Uwierzytelnianie JWT i zarządzanie sesją (Bearer token & HttpOnly cookie)."},
    {"name": "Pipeline", "description": "Sterowanie asynchronicznym montażem Shorts i monitoring kolejki renderów."},
    {"name": "Clips", "description": "Skanowanie, detekcja killi, metadane, OCR i serwowanie plików wideo / miniatur."},
    {"name": "YouTube", "description": "Integracja z YouTube API: autoryzacja OAuth 2.0 na 127.0.0.1, publikacja i przypinanie komentarzy."},
    {"name": "Calendar", "description": "Harmonogram publikacji z auto-uzupełnianiem i optymalizacją peak hours."},
    {"name": "Learning", "description": "Silnik samouczący: retencja widzów, optymalizacja wag akcji, testy A/B i rekomendacje."},
    {"name": "System", "description": "Diagnostyka sprzętowa (GPU/NVENC), tuning parametrów i benchmarking."},
]

app = FastAPI(
    title="Shortsyt Studio Backend API",
    description="Kompleksowy silnik autonomicznego montażu i publikacji YouTube Shorts dla League of Legends.",
    version="1.1.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════════════════════
# REJESTRACJA MODUŁÓW APIRouter
# ══════════════════════════════════════════════════════════════════════════════
app.include_router(auth.router)
app.include_router(pipeline.router)
app.include_router(clips.router)
app.include_router(youtube.router)
app.include_router(calendar.router)
app.include_router(learning.router)
app.include_router(system.router)

# ══════════════════════════════════════════════════════════════════════════════
# STATYCZNY FRONTEND SPA (Electron / Browser)
# ══════════════════════════════════════════════════════════════════════════════
DIST_DIR = DARK_ROOT / "shortsyt-desktop" / "dist"
if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    if (DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        target = DIST_DIR / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST_DIR / "index.html")
else:
    @app.get("/", tags=["System"])
    def root():
        return {"message": "Shortsyt API v1.0 — użyj /docs dla dokumentacji"}
