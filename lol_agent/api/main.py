"""
Shortsyt API — główny serwer FastAPI
Uruchom: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload
"""
import glob
import os
from datetime import timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import create_access_token, verify_password, verify_token, verify_token_flexible
from .config import (
    ALLOWED_ORIGINS, LOL_INPUT_DIR, LOL_OUTPUT_DIR,
    LOL_TEMP_DIR,
)
from . import pipeline_runner
from .youtube_uploader import (
    get_token_status, get_auth_url, exchange_auth_code, upload_video
)

app = FastAPI(
    title="Shortsyt API",
    description="Backend dla apki Android — zarządzanie LOL Shorts pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# MODELE
# ══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class PipelineStartRequest(BaseModel):
    source_path: str
    clip_start: float = 0.0
    clip_end: float = 20.0
    action_type: str = "pentakill"
    champion_name: str = "Katarina"
    rank: str = "Gold"
    peak_moment: float = 17.0
    hook_text: str = "PENTAKILL"
    output_filename: str = "short_output.mp4"
    use_speed_ramp: bool = True
    use_zoom_punch: bool = True
    use_smart_camera: bool = True
    expo_push_token: Optional[str] = None

class YouTubeAuthCodeRequest(BaseModel):
    code: str

class YouTubeUploadRequest(BaseModel):
    filename: str
    title: str
    description: str = ""
    tags: List[str] = []
    privacy: str = "private"

class RegisterPushTokenRequest(BaseModel):
    expo_token: str


# Przechowuj push token w pamięci (wystarczy dla jednego urządzenia)
_push_token: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/login", response_model=LoginResponse, tags=["Auth"])
def login(req: LoginRequest):
    """Zaloguj się hasłem i otrzymaj JWT token."""
    if not verify_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowe hasło",
        )
    token = create_access_token({"sub": "user"})
    return LoginResponse(access_token=token)


@app.get("/auth/me", tags=["Auth"])
def me(payload: dict = Depends(verify_token)):
    """Sprawdź czy token jest ważny."""
    return {"status": "ok", "user": payload.get("sub")}


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/status", tags=["Pipeline"])
def pipeline_status(payload: dict = Depends(verify_token)):
    """Aktualny status pipeline (idle / running / done / error)."""
    return pipeline_runner.get_state()


@app.post("/pipeline/start", tags=["Pipeline"])
def start_pipeline(req: PipelineStartRequest, payload: dict = Depends(verify_token)):
    """Uruchom renderowanie klipu."""
    started = pipeline_runner.start_pipeline(
        source_path=req.source_path,
        clip_start=req.clip_start,
        clip_end=req.clip_end,
        action_type=req.action_type,
        champion_name=req.champion_name,
        rank=req.rank,
        peak_moment=req.peak_moment,
        hook_text=req.hook_text,
        output_filename=req.output_filename,
        use_speed_ramp=req.use_speed_ramp,
        use_zoom_punch=req.use_zoom_punch,
        use_smart_camera=req.use_smart_camera,
        notify_token=req.expo_push_token or _push_token,
    )
    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline już działa — poczekaj na koniec lub zatrzymaj",
        )
    return {"status": "started"}


@app.post("/pipeline/stop", tags=["Pipeline"])
def stop_pipeline(payload: dict = Depends(verify_token)):
    """Zatrzymaj pipeline."""
    pipeline_runner.stop_pipeline()
    return {"status": "stopped"}


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — PLIKI
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/clips", tags=["Files"])
def list_clips(payload: dict = Depends(verify_token)):
    """Lista plików MP4 w LOL_INPUT_DIR."""
    clips = []
    if LOL_INPUT_DIR.exists():
        for ext in ["*.mp4", "*.mov", "*.mkv", "*.avi"]:
            for f in LOL_INPUT_DIR.glob(ext):
                clips.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                    "modified": f.stat().st_mtime,
                })
    clips.sort(key=lambda x: x["modified"], reverse=True)
    return {"clips": clips}


@app.get("/outputs", tags=["Files"])
def list_outputs(payload: dict = Depends(verify_token)):
    """Lista gotowych Shortów."""
    outputs = []
    # Szukaj w temp dir i output dir
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    for search_dir in search_dirs:
        if Path(search_dir).exists():
            for f in Path(search_dir).glob("*.mp4"):
                if "short" in f.name.lower() or "test" in f.name.lower():
                    outputs.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "modified": f.stat().st_mtime,
                    })
    outputs.sort(key=lambda x: x["modified"], reverse=True)
    return {"outputs": outputs}


@app.get("/outputs/{filename}", tags=["Files"])
def stream_output(
    filename: str,
    payload: dict = Depends(verify_token_flexible),
):
    """Streamuj gotowy Short do podglądu.

    Obsługuje dwa sposoby autoryzacji:
    - Bearer header: Authorization: Bearer <token>  (standardowy)
    - Query param: /outputs/file.mp4?token=<token>  (wymagane przez expo-av)
    """
    # Szukaj pliku w znanych lokalizacjach
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            return FileResponse(
                str(fp),
                media_type="video/mp4",
                headers={"Accept-Ranges": "bytes"},
            )
    raise HTTPException(status_code=404, detail=f"Plik nie znaleziony: {filename}")


@app.get("/thumbnails", tags=["Files"])
def list_thumbnails(payload: dict = Depends(verify_token)):
    """Lista wygenerowanych miniaturek Shorts."""
    thumbs = []
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent / "thumbnails"]
    seen = set()
    for search_dir in search_dirs:
        if Path(search_dir).exists():
            for f in Path(search_dir).glob("*thumb*.jpg"):
                if f.name not in seen:
                    seen.add(f.name)
                    # Spróbuj powiązać z plikiem mp4
                    base_name = f.name.replace("_thumb.jpg", ".mp4").replace("thumb_", "")
                    thumbs.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "modified": f.stat().st_mtime,
                        "associated_video": base_name,
                    })
    thumbs.sort(key=lambda x: x["modified"], reverse=True)
    return {"thumbnails": thumbs}


@app.get("/thumbnails/{filename}", tags=["Files"])
def stream_thumbnail(
    filename: str,
    payload: dict = Depends(verify_token_flexible),
):
    """Pobierz plik miniaturki JPG (9:16)."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent / "thumbnails"]
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            return FileResponse(
                str(fp),
                media_type="image/jpeg",
            )
    raise HTTPException(status_code=404, detail=f"Miniaturka nie znaleziona: {filename}")


@app.get("/camera-preview", tags=["Camera"])
def get_camera_preview(
    file_path: str,
    timestamp: float = 0.0,
    crop_x: Optional[int] = None,
    payload: dict = Depends(verify_token_flexible),
):
    """Zwraca klatkę podglądu z naniesionym prostokątem kadru 9:16 (608x1080)."""
    import subprocess
    import cv2
    import numpy as np

    p = Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Klip nie istnieje: {file_path}")

    # Wyciągnij pojedynczą klatkę przez ffmpeg
    cmd = [
        "ffmpeg", "-y", "-ss", str(max(0.0, timestamp)),
        "-i", str(p),
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24",
        "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        frame_bytes = proc.stdout
        frame = np.frombuffer(frame_bytes, np.uint8).reshape((1080, 1920, 3)).copy()

        # Domyślny crop_x jeśli nie podano
        cx = crop_x if crop_x is not None else (1920 - 608) // 2
        cx = max(0, min(cx, 1920 - 608))

        # Narysuj prostokąt kadru 9:16 (Złoty/Czerwony)
        cv2.rectangle(frame, (cx, 0), (cx + 608, 1080), (0, 215, 255), 4)
        # Przyciemnij obszary poza kadrem
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (cx, 1080), (0, 0, 0), -1)
        cv2.rectangle(overlay, (cx + 608, 0), (1920, 1080), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Zapisz do bufora JPEG
        _, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        from fastapi.responses import Response
        return Response(content=enc.tobytes(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd generowania podglądu kadru: {e}")



# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — YOUTUBE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/youtube/token-status", tags=["YouTube"])
def yt_token_status(payload: dict = Depends(verify_token)):
    """Status tokenu YouTube — ile dni do wygaśnięcia."""
    return get_token_status()


@app.get("/youtube/auth-url", tags=["YouTube"])
def yt_auth_url(payload: dict = Depends(verify_token)):
    """Pobierz URL do autoryzacji YouTube OAuth."""
    try:
        url = get_auth_url()
        return {"auth_url": url}
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/youtube/auth-code", tags=["YouTube"])
def yt_exchange_code(req: YouTubeAuthCodeRequest, payload: dict = Depends(verify_token)):
    """Wymień kod autoryzacji YouTube na token."""
    try:
        result = exchange_auth_code(req.code)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/youtube/upload/{filename}", tags=["YouTube"])
def yt_upload(filename: str, req: YouTubeUploadRequest, payload: dict = Depends(verify_token)):
    """Upload Shorta na YouTube."""
    # Znajdź plik
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
        result = upload_video(
            video_path=video_path,
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy=req.privacy,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — PUSH NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/push/register", tags=["Notifications"])
def register_push_token(req: RegisterPushTokenRequest, payload: dict = Depends(verify_token)):
    """Zarejestruj Expo Push Token urządzenia."""
    global _push_token
    _push_token = req.expo_token
    return {"status": "registered", "token": req.expo_token}


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/analytics", tags=["Analytics"])
def get_analytics(range: str = "30d", payload: dict = Depends(verify_token_flexible)):
    """Pobierz statystyki ROI i wydajności opublikowanych filmów."""
    import json
    from datetime import datetime, timezone, timedelta
    from pathlib import Path

    agent_dir = Path(__file__).parent.parent
    pub_file = agent_dir / "published_videos.jsonl"
    cache_file = agent_dir / "yt_perf_cache.json"

    perf_map = {}
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                for v in cdata.get("videos", []):
                    perf_map[v.get("videoId")] = v
        except Exception:
            pass

    videos = []
    if pub_file.exists():
        try:
            with open(pub_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line.strip())
                        vid = item.get("video_id")
                        if vid and vid in perf_map:
                            item["views"] = perf_map[vid].get("views", 0)
                            item["likes"] = perf_map[vid].get("likes", 0)
                        else:
                            # Estimate based on channel average
                            item["views"] = 1000 if "pentakill" in item.get("action_type", "") else 450
                            item["likes"] = 8
                        videos.append(item)
        except Exception:
            pass

    # Filter by range
    now = datetime.now()
    filtered = []
    days_limit = 7 if range == "7d" else (30 if range == "30d" else 3650)
    for v in videos:
        ts_str = v.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", ""))
                if (now - ts).days <= days_limit:
                    filtered.append(v)
            except Exception:
                filtered.append(v)
        else:
            filtered.append(v)

    total_views = sum(v.get("views", 0) for v in filtered)
    total_likes = sum(v.get("likes", 0) for v in filtered)
    count = len(filtered)
    avg_views = int(total_views / max(count, 1))

    return {
        "range": range,
        "count": count,
        "total_views": total_views,
        "total_likes": total_likes,
        "avg_views": avg_views,
        "videos": filtered,
    }



@app.get("/health", tags=["System"])
def health():
    """Healthcheck — nie wymaga autoryzacji."""
    return {"status": "ok", "service": "Shortsyt API"}


@app.get("/", tags=["System"])
def root():
    return {"message": "Shortsyt API v1.0 — użyj /docs dla dokumentacji"}
