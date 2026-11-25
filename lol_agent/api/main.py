"""
Shortsyt API — główny serwer FastAPI (Modular APIRouters)
Uruchom: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
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
from .routers import auth, pipeline, clips, youtube, calendar, learning, system, social, accounts, overnight, research, compilations
from .routers.clips import list_clips, auto_detect_clip, scan_available_clips


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza cyklem życia aplikacji — procesy w tle i czyszczenie."""
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("TESTING") == "true":
        yield
        return

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

                def _flush_scheduled():
                    try:
                        from lol_agent.scheduled_queue import check_and_flush_scheduled_posts
                        check_and_flush_scheduled_posts()
                    except Exception as sq_err:
                        import logging
                        logging.getLogger("shortsyt.flusher").debug("Scheduled queue check: %s", sq_err)

                await loop.run_in_executor(None, _flush_scheduled)
            except Exception as e:
                import logging
                logging.getLogger("shortsyt.flusher").debug("Comment flush check: %s", e)

    async def _tracker_loop():
        # Po 5 sekundach od startu uruchom wstępne sprawdzenie zaległych filmów
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass

        while not stop_event.is_set():
            try:
                loop = asyncio.get_running_loop()
                def _do_check():
                    try:
                        from lol_agent.lol_performance_tracker import reconcile_and_verify_published_videos, run_pending_checks
                        from lol_agent.learning_engine import run_channel_learning_cycle
                        n_rec = reconcile_and_verify_published_videos()
                        c_any = run_pending_checks()
                        if n_rec > 0 or c_any:
                            run_channel_learning_cycle(force_refresh=True)

                        # Automatyczna synchronizacja telemetrii na stronę (docs/ oraz Pulpit odpal/Shortsyt)
                        try:
                            from scripts.sync_website_stats import sync_stats
                            sync_stats(force_refresh_api=False)
                        except Exception as se:
                            import logging
                            logging.getLogger("shortsyt.sync").debug("Live stats sync: %s", se)

                        # Proaktywna rotacja lol_temp/ + utrzymanie ważności tokenów OAuth 24/7
                        try:
                            from lol_agent.temp_cleaner import cleanup_temp_directory
                            cleanup_temp_directory(max_age_days=14, dry_run=False)
                        except Exception as tc_err:
                            import logging
                            logging.getLogger("shortsyt.cleaner").debug("Temp cleaner: %s", tc_err)

                        try:
                            from .youtube_uploader import get_valid_credentials
                            from lol_agent.tiktok_publisher import load_tiktok_token
                            get_valid_credentials(require_token=False, ignore_refresh_error=True)
                            load_tiktok_token()
                        except Exception as tok_err:
                            import logging
                            logging.getLogger("shortsyt.tokens").debug("Token watchdog: %s", tok_err)
                    except Exception as pe:
                        import logging
                        logging.getLogger("shortsyt.tracker").debug("Tracker check: %s", pe)
                await loop.run_in_executor(None, _do_check)
            except Exception:
                pass

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=600)  # co 10 minut
                break
            except asyncio.TimeoutError:
                pass

    flusher_task = asyncio.create_task(_flusher_loop())
    tracker_task = asyncio.create_task(_tracker_loop())
    yield
    stop_event.set()
    try:
        from lol_agent.synapsa_overnight_batch import stop_overnight_batch
        stop_overnight_batch()
    except Exception:
        pass
    try:
        from . import pipeline_runner
        pipeline_runner.stop_pipeline(clear_queue=True)
    except Exception:
        pass
    flusher_task.cancel()
    tracker_task.cancel()
    try:
        await asyncio.gather(flusher_task, tracker_task, return_exceptions=True)
    except Exception:
        pass


tags_metadata = [
    {"name": "Auth", "description": "Uwierzytelnianie JWT i zarządzanie sesją (Bearer token & HttpOnly cookie)."},
    {"name": "Pipeline", "description": "Sterowanie asynchronicznym montażem Shorts i monitoring kolejki renderów."},
    {"name": "Clips", "description": "Skanowanie, detekcja killi, metadane, OCR i serwowanie plików wideo / miniatur."},
    {"name": "YouTube", "description": "Integracja z YouTube API: autoryzacja OAuth 2.0 na 127.0.0.1, publikacja i przypinanie komentarzy."},
    {"name": "Calendar", "description": "Harmonogram publikacji z auto-uzupełnianiem i optymalizacją peak hours."},
    {"name": "Learning", "description": "Silnik samouczący: retencja widzów, optymalizacja wag akcji, testy A/B i rekomendacje."},
    {"name": "System", "description": "Diagnostyka sprzętowa (GPU/NVENC), tuning parametrów i benchmarking."},
    {"name": "Accounts", "description": "Zarządzanie wieloma profilami kont, tokenami i wytycznymi kontentu."},
    {"name": "Overnight", "description": "Tryb nocny: skan folderu, lokalny montaż Top 5 (bez uploadu) i rekomendacja Synapsy."},
    {"name": "Research", "description": "Research nisz YT Shorts, dekonstrukcja montażu, anty-plagiat i podgląd pitch 9:16 DFY."},
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
app.include_router(social.router)
app.include_router(accounts.router)
app.include_router(overnight.router)
app.include_router(research.router)
app.include_router(compilations.router)

# ══════════════════════════════════════════════════════════════════════════════
# STATYCZNY FRONTEND SPA (Electron / Browser)
# ══════════════════════════════════════════════════════════════════════════════
DIST_DIR = DARK_ROOT / "shortsyt-desktop" / "dist"
if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    if (DIST_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        norm = full_path.replace("\\", "/")
        if norm.startswith(("thumbnails/", "outputs/", "research/media/", "research/niche/", "compilations/")):
            raise HTTPException(status_code=404, detail="Not found")
        dist_root = DIST_DIR.resolve()
        target = (dist_root / norm).resolve()
        if full_path and target.is_relative_to(dist_root) and target.is_file():
            return FileResponse(target)
        return FileResponse(dist_root / "index.html")
else:
    @app.get("/", tags=["System"])
    def root():
        return {"message": "Shortsyt API v1.0 — użyj /docs dla dokumentacji"}
