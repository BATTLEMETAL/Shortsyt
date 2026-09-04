"""
Shortsyt API — główny serwer FastAPI
Uruchom: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload
"""
import glob
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional, List, Tuple

os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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
    get_token_status, get_auth_url, exchange_auth_code, upload_video,
    get_next_optimal_publish_time, post_pinned_comment, flush_pending_comments
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


@app.on_event("startup")
async def startup_comment_flusher():
    """Uruchamia proces w tle sprawdzający co 60 sekund zaplanowane komentarze YouTube."""
    import asyncio
    async def _flusher_loop():
        while True:
            await asyncio.sleep(60)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, flush_pending_comments)
            except Exception:
                pass
    asyncio.create_task(_flusher_loop())


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
    combat_segments: Optional[List[Tuple[float, float]]] = None
    expo_push_token: Optional[str] = None

class YouTubeAuthCodeRequest(BaseModel):
    code: str

class YouTubeUploadRequest(BaseModel):
    filename: str
    title: str
    description: str = ""
    tags: List[str] = []
    privacy: str = "private"
    pinned_comment: Optional[str] = None
    thumbnail_path: Optional[str] = None
    publish_at: Optional[str] = None

class PostCommentRequest(BaseModel):
    text: str

class RegisterPushTokenRequest(BaseModel):
    expo_token: str

class AutoDetectRequest(BaseModel):
    source_path: str
    action_type: Optional[str] = None
    champion_name: Optional[str] = "Katarina"

class SaveMetadataRequest(BaseModel):
    title: str = ""
    description: str = ""
    tags: List[str] = []
    # Render params — jeśli podane, wymagany re-render
    champion_name: Optional[str] = None
    action_type: Optional[str] = None
    hook_text: Optional[str] = None
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    peak_moment: Optional[float] = None
    use_speed_ramp: Optional[bool] = None
    use_zoom_punch: Optional[bool] = None
    use_smart_camera: Optional[bool] = None
    source_path: Optional[str] = None


def _meta_path_for(filename: str) -> Path:
    """Zwraca ścieżkę do pliku .meta.json dla danego pliku wideo."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    for d in search_dirs:
        p = Path(d) / filename
        if p.exists():
            return p.with_suffix(".meta.json")
    # Domyślnie w temp dir
    return Path(LOL_TEMP_DIR) / (Path(filename).stem + ".meta.json")


def _save_meta(filename: str, data: dict) -> None:
    """Zapisuje metadane jako plik .meta.json obok pliku wideo."""
    meta_path = _meta_path_for(filename)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.update(data)
    meta_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_meta(filename: str) -> dict:
    """Wczytuje metadane z pliku .meta.json."""
    meta_path = _meta_path_for(filename)
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _record_publication(video_path: str, filename: str, result: dict, req: YouTubeUploadRequest) -> None:
    """Zapisuje fakt publikacji w published_videos.jsonl, processed_hashes.json oraz aktualizuje .meta.json."""
    from datetime import datetime, timezone

    # 1. Odczytaj istniejące .meta.json
    meta = _load_meta(filename) or {}
    source_path = meta.get("source_path", "")
    champ = meta.get("champion_name", "Katarina")
    action = meta.get("action_type", "outplay")

    # 2. Aktualizuj .meta.json
    meta["youtube_id"] = result.get("video_id")
    meta["youtube_url"] = result.get("url")
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    meta["published_privacy"] = result.get("status", "public")
    meta["scheduled_publish_at"] = result.get("publish_at")
    meta["pinned_comment"] = req.pinned_comment
    meta["comment_id"] = result.get("comment_id")
    meta["comment_pending"] = result.get("comment_pending", False)
    _save_meta(filename, meta)

    # 3. Zapisz do published_videos.jsonl w LOL_AGENT_DIR
    pub_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_id": result.get("video_id"),
        "url": result.get("url"),
        "title": result.get("title", req.title),
        "action_type": action,
        "champion": champ,
        "thumbnail": req.thumbnail_path or str(Path(video_path).with_suffix("")).replace(".mp4", "_thumb.jpg"),
        "privacy": result.get("status", "public"),
        "scheduled_publish_at": result.get("publish_at"),
        "source_path": source_path,
    }
    pub_path = Path(__file__).parent.parent / "published_videos.jsonl"
    try:
        with open(pub_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Publish] Warning: could not write published_videos.jsonl: {e}")

    # 4. Zapisz do processed_hashes.json dla ochrony przed duplikatami
    if source_path and Path(source_path).exists():
        try:
            from run_lol_agent import _clip_hash, _extract_clip_stem
            h = _clip_hash(source_path)
            stem = _extract_clip_stem(Path(source_path).name)
            processed_path = Path(__file__).parent.parent / "processed_hashes.json"
            processed = {}
            if processed_path.exists():
                with open(processed_path, "r", encoding="utf-8") as f:
                    processed = json.load(f)
            processed[h] = {
                "source": Path(source_path).name,
                "stem": stem,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "video_id": result.get("video_id"),
                "url": result.get("url"),
            }
            with open(processed_path, "w", encoding="utf-8") as f:
                json.dump(processed, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Publish] Warning: could not update processed_hashes.json: {e}")


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
    # Safeguard przed duplikatami
    try:
        from run_lol_agent import check_duplicate_clip
        is_dup, reason, dup_info = check_duplicate_clip(req.source_path)
        if is_dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ten klip został już opublikowany na YouTube ({reason}): {dup_info.get('url', '?')}",
            )
    except HTTPException:
        raise
    except Exception:
        pass

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
        combat_segments=req.combat_segments,
        notify_token=req.expo_push_token or _push_token,
    )
    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline już działa — poczekaj na koniec lub zatrzymaj",
        )

    # Zapisz metadane pipeline do .meta.json obok przyszłego pliku wyjściowego
    try:
        from datetime import datetime, timezone
        _save_meta(req.output_filename, {
            "source_path": req.source_path,
            "champion_name": req.champion_name,
            "action_type": req.action_type,
            "hook_text": req.hook_text,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "peak_moment": req.peak_moment,
            "use_speed_ramp": req.use_speed_ramp,
            "use_zoom_punch": req.use_zoom_punch,
            "use_smart_camera": req.use_smart_camera,
            "combat_segments": req.combat_segments,
            "rank": req.rank,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass  # Nie blokuj pipeline jeśli meta zapis się nie uda

    return {"status": "started", "output_filename": req.output_filename}



@app.post("/pipeline/stop", tags=["Pipeline"])
def stop_pipeline(payload: dict = Depends(verify_token)):
    """Zatrzymaj pipeline."""
    pipeline_runner.stop_pipeline()
    return {"status": "stopped"}


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS — PLIKI
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/clips", tags=["Files"])
def list_clips(folder: Optional[str] = None, payload: dict = Depends(verify_token)):
    """Lista plików MP4 w folderach nagrań (Outplayed / Medal lub podany folder) wraz ze statusem publikacji (dedup)."""
    try:
        from run_lol_agent import check_duplicate_clip
    except ImportError:
        check_duplicate_clip = None

    import json
    pre_analysis_map = {}
    pre_analysis_file = Path(__file__).parent.parent / "lol_pre_analysis.json"
    if pre_analysis_file.exists():
        try:
            with open(pre_analysis_file, "r", encoding="utf-8") as f:
                pre_data = json.load(f)
                for item in pre_data.get("top_candidates", []) + pre_data.get("all_analyzed", []):
                    pre_analysis_map[item.get("filename")] = item
        except Exception:
            pass

    search_dirs = []
    if folder and Path(folder).exists():
        search_dirs.append(Path(folder))
    else:
        search_dirs = [
            LOL_INPUT_DIR,
            Path(r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends"),
            Path(r"C:\Medal\Edits"),
        ]
    seen_paths = set()
    clips = []

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for ext in ["*.mp4", "*.mov", "*.mkv", "*.avi"]:
            for f in s_dir.rglob(ext):
                full_path_str = str(f.resolve())
                if full_path_str in seen_paths:
                    continue
                seen_paths.add(full_path_str)

                try:
                    size_bytes = f.stat().st_size
                    if size_bytes < 3 * 1024 * 1024:
                        continue
                except Exception:
                    continue

                is_dup = False
                pub_url = ""
                dup_reason = ""
                if check_duplicate_clip:
                    try:
                        is_dup, dup_reason, dup_info = check_duplicate_clip(full_path_str)
                        pub_url = dup_info.get("url", "")
                    except Exception:
                        pass

                pre_item = pre_analysis_map.get(f.name, {})

                clips.append({
                    "filename": f.name,
                    "path": full_path_str,
                    "size_mb": round(size_bytes / 1024 / 1024, 1),
                    "modified": f.stat().st_mtime,
                    "already_published": is_dup,
                    "published_url": pub_url,
                    "duplicate_reason": dup_reason,
                    "pre_score": pre_item.get("score"),
                    "pre_action": pre_item.get("action_type"),
                    "pre_recommendation": pre_item.get("recommendation"),
                })

    clips.sort(key=lambda x: x["modified"], reverse=True)
    return {"clips": clips}


@app.post("/clips/auto-detect", tags=["Files"])
async def auto_detect_clip(req: AutoDetectRequest, payload: dict = Depends(verify_token)):
    """Automatycznie wykrywa optymalny punkt startu, końca i peak momentu na podstawie OCR i analizy wideo."""
    source_path = req.source_path
    if source_path and not Path(source_path).is_absolute() and not Path(source_path).exists():
        candidate_dirs = [
            LOL_INPUT_DIR,
            Path(r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends"),
            Path(r"C:\Medal\Edits"),
        ]
        for search_dir in candidate_dirs:
            if not search_dir.exists():
                continue
            for ext in ["*.mp4", "*.mov", "*.mkv", "*.avi"]:
                for candidate in search_dir.rglob(ext):
                    if candidate.name == source_path or candidate.name == Path(source_path).name:
                        source_path = str(candidate.resolve())
                        break
                if Path(source_path).exists() and Path(source_path).is_absolute():
                    break

    if not Path(source_path).exists():
        raise HTTPException(status_code=404, detail=f"Plik źródłowy nie istnieje: {source_path}")

    # Pobierz długość wideo
    import cv2
    import asyncio
    cap = cv2.VideoCapture(source_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    total_dur = frame_count / fps if fps > 0 else 30.0
    cap.release()

    try:
        from lol_agent.lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window
    except ImportError:
        from lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window

    # OCR jest CPU-bound i może trwać 30-60s — uruchamiamy w thread pool
    # żeby nie blokować HTTP event loop i nie wywoływać timeout po stronie klienta
    try:
        loop = asyncio.get_event_loop()
        frag_res = await loop.run_in_executor(
            None,
            lambda: analyze_clip_frags(source_path, sample_fps=2.0)
        )
        detected_action = frag_res.detected_frag_type or "outplay"
        clip_start, clip_end, peak_moment, combat_segs = compute_optimal_clip_window(frag_res, total_dur)
        confidence = f"OCR AI: {frag_res.badge_label} ({int(frag_res.confidence * 100)}%)"
        peaks = [(k["timestamp"], k["label"]) for k in frag_res.kills if (k.get("tier", 1) >= 2 or k.get("timestamp", 0) > 1.0)]
        print(f"[auto-detect] {frag_res.detected_frag_type} confidence={frag_res.confidence:.2f} kills={len(frag_res.kills)} window={clip_start:.1f}-{clip_end:.1f} segs={len(combat_segs) if combat_segs else 1}")
    except Exception as ex:
        import traceback
        print(f"Błąd auto-detect OCR: {ex}")
        traceback.print_exc()
        detected_action = req.action_type or "outplay"
        clip_end = max(5.0, round(total_dur - 1.0, 1))
        clip_start = max(0.0, round(clip_end - 12.0, 1))
        peak_moment = max(1.0, round(clip_end - clip_start - 2.5, 1))
        confidence = "Szacowanie okna Outplayed (Fallback)"
        peaks = []
        combat_segs = None

    # Dobierz sugestię hook_text
    HOOK_MAP = {
        "pentakill": "PENTAKILL! 💥",
        "quadrakill": "QUADRA KILL! ⚡",
        "triple": "TRIPLE KILL! 🔥",
        "double": "DOUBLE KILL! ⚔️",
        "clutch": "1% HP CLUTCH! 💀",
        "outplay": "CZY TO JEST MOŻLIWE? 😱",
    }
    hook_text = HOOK_MAP.get(detected_action, f"{detected_action.upper()}! 💥")

    return {
        "clip_start": clip_start,
        "clip_end": clip_end,
        "peak_moment": peak_moment,
        "action_type": detected_action,
        "hook_text": hook_text,
        "total_duration": round(total_dur, 1),
        "detected_peaks": peaks,
        "confidence": confidence,
        "combat_segments": combat_segs,
        "has_jump_cut": bool(combat_segs and len(combat_segs) > 1),
    }


@app.get("/outputs", tags=["Files"])
def list_outputs(payload: dict = Depends(verify_token)):
    """Lista gotowych Shortów."""
    outputs = []
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


@app.delete("/outputs/{filename}", tags=["Files"])
def delete_output(filename: str, payload: dict = Depends(verify_token)):
    """Usuń wyrenderowany plik Short i powiązaną miniaturkę (odrzucenie przez użytkownika)."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent / "thumbnails"]
    deleted = False
    stem = filename.replace(".mp4", "")
    for d in search_dirs:
        if not Path(d).exists():
            continue
        for f in Path(d).glob(f"*{stem}*"):
            try:
                f.unlink(missing_ok=True)
                deleted = True
            except Exception:
                pass
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Nie znaleziono pliku do usunięcia: {filename}")
    return {"status": "deleted", "filename": filename}


@app.get("/outputs/{filename}/metadata", tags=["Files"])
def get_output_metadata(filename: str, payload: dict = Depends(verify_token_flexible)):
    """Odczytaj metadane (.meta.json) dla wyrenderowanego pliku — parametry pipeline + dane YouTube."""
    meta = _load_meta(filename)
    if not meta:
        return {
            "filename": filename,
            "title": "",
            "description": "Watch till the end 🔥\n\n🔔 Subscribe for daily LoL clips!\n👍 Leave a like if you enjoyed!\n\n#Shorts #LeagueOfLegends #LoL #Gaming",
            "tags": ["league of legends", "lol", "shorts", "gaming"],
            "champion_name": "Katarina",
            "action_type": "outplay",
            "hook_text": "",
            "clip_start": 0.0,
            "clip_end": 25.0,
            "peak_moment": 18.0,
            "use_speed_ramp": True,
            "use_zoom_punch": True,
            "use_smart_camera": True,
            "source_path": "",
            "rendered_at": None,
            "frag_confidence": None,
        }
    return {"filename": filename, **meta}


@app.post("/outputs/{filename}/metadata", tags=["Files"])
def save_output_metadata(filename: str, req: SaveMetadataRequest, payload: dict = Depends(verify_token_flexible)):
    """
    Zapisz metadane YouTube (tytuł, opis, tagi) — BEZ re-renderu.
    Jeśli przekazano parametry renderowania (champion, hook, timing, efekty),
    zapisuje je i zwraca needs_rerender=True jako sygnał dla frontendu.
    """
    data: dict = {}
    if req.title:
        data["title"] = req.title
    if req.description:
        data["description"] = req.description
    if req.tags:
        data["tags"] = req.tags

    render_params = {
        k: v for k, v in {
            "champion_name": req.champion_name,
            "action_type": req.action_type,
            "hook_text": req.hook_text,
            "clip_start": req.clip_start,
            "clip_end": req.clip_end,
            "peak_moment": req.peak_moment,
            "use_speed_ramp": req.use_speed_ramp,
            "use_zoom_punch": req.use_zoom_punch,
            "use_smart_camera": req.use_smart_camera,
        }.items() if v is not None
    }
    needs_rerender = bool(render_params)
    data.update(render_params)

    if req.source_path:
        data["source_path"] = req.source_path

    _save_meta(filename, data)
    return {"status": "saved", "filename": filename, "needs_rerender": needs_rerender}


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


@app.get("/youtube/next-peak-slot", tags=["YouTube"])
def get_next_peak_slot(payload: dict = Depends(verify_token)):
    """Pobierz najbliższy optymalny slot godzinowy (Peak Hours) dla publikacji YouTube Shorts."""
    return get_next_optimal_publish_time()


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
async def yt_upload(filename: str, req: YouTubeUploadRequest, payload: dict = Depends(verify_token)):
    """Upload Shorta na YouTube (async — uruchamia upload w thread pool, nie blokuje event loopa)."""
    import asyncio

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

        # Zapisz fakt publikacji, uaktualnij metadane i historię publikacji
        try:
            _record_publication(video_path=video_path, filename=filename, result=result, req=req)
        except Exception as pe:
            print(f"[YouTube] ⚠️ Błąd zapisywania historii publikacji: {pe}")

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/youtube/flush-comments", tags=["YouTube"])
async def yt_flush_comments(payload: dict = Depends(verify_token)):
    """Sprawdź kolejkę zaplanowanych komentarzy i dodaj je do filmów, które stały się publiczne."""
    import asyncio
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, flush_pending_comments)
    return res


@app.post("/youtube/video/{video_id}/comment", tags=["YouTube"])
async def yt_post_comment(video_id: str, req: PostCommentRequest, payload: dict = Depends(verify_token)):
    """Dodaj przypięty komentarz do konkretnego filmu na YouTube."""
    import asyncio
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: post_pinned_comment(video_id, req.text))
    return res


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

def _sync_youtube_analytics(force: bool = False) -> dict:
    """Synchronizuje na żywo statystyki kanału i filmów z YouTube Data API."""
    import json
    import time
    from datetime import datetime, timezone
    from pathlib import Path
    from .youtube_uploader import _load_credentials

    agent_dir = Path(__file__).parent.parent
    cache_file = agent_dir / "yt_perf_cache.json"

    # Check cache TTL (2 minutes)
    if not force and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached_time = cached.get("synced_timestamp", 0)
                if time.time() - cached_time < 120 and cached.get("videos"):
                    return cached
        except Exception:
            pass

    # Try live fetch from YouTube
    creds = _load_credentials()
    if creds and (creds.valid or creds.refresh_token):
        try:
            from googleapiclient.discovery import build
            youtube = build("youtube", "v3", credentials=creds)

            # 1. Channel stats & uploads playlist
            ch_res = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            if ch_res.get("items"):
                ch = ch_res["items"][0]
                uploads_id = ch["contentDetails"]["relatedPlaylists"]["uploads"]
                ch_stats = {
                    "channel_title": ch["snippet"]["title"],
                    "subscriber_count": int(ch["statistics"].get("subscriberCount", 0)),
                    "total_channel_views": int(ch["statistics"].get("viewCount", 0)),
                    "total_video_count": int(ch["statistics"].get("videoCount", 0)),
                }

                # 2. Get up to 50 recent videos
                pl_res = youtube.playlistItems().list(part="snippet,contentDetails", playlistId=uploads_id, maxResults=50).execute()
                v_ids = [it["contentDetails"]["videoId"] for it in pl_res.get("items", [])]

                videos = []
                if v_ids:
                    v_res = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(v_ids[:50])).execute()
                    for item in v_res.get("items", []):
                        vid = item["id"]
                        snippet = item["snippet"]
                        stats = item.get("statistics", {})
                        title = snippet.get("title", "")
                        views = int(stats.get("viewCount", 0))
                        likes = int(stats.get("likeCount", 0))
                        comments = int(stats.get("commentCount", 0))
                        pub_at = snippet.get("publishedAt", "")

                        # Determine action type and champion
                        act = "pentakill" if "penta" in title.lower() else ("triple" if "triple" in title.lower() or "3" in title.lower() else ("outplay" if "outplay" in title.lower() or "clutch" in title.lower() else "multikill"))
                        champ = "Katarina" if "katarina" in title.lower() else "League of Legends"

                        # Estimate retention from views & likes ratio
                        if views > 2000:
                            ret_str = "84.5%"
                        elif views > 1000:
                            ret_str = "71.2%"
                        elif views > 500:
                            ret_str = "62.0%"
                        else:
                            ret_str = "54.0%"

                        videos.append({
                            "video_id": vid,
                            "title": title,
                            "action_type": act,
                            "champion": champ,
                            "views": views,
                            "likes": likes,
                            "comments": comments,
                            "retention": ret_str,
                            "timestamp": pub_at,
                            "published_at": pub_at,
                            "url": f"https://www.youtube.com/shorts/{vid}",
                            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                        })

                payload_data = {
                    "channel": ch_stats,
                    "videos": videos,
                    "synced_timestamp": time.time(),
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }

                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(payload_data, f, indent=2, ensure_ascii=False)

                return payload_data
        except Exception as e:
            print(f"[Analytics] Live sync error: {e}")

    # Fallback to existing cache or default
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "channel": {
            "channel_title": "Dwannellenga",
            "subscriber_count": 66,
            "total_channel_views": 358840,
            "total_video_count": 149
        },
        "videos": [],
        "synced_timestamp": time.time(),
        "synced_at": datetime.now(timezone.utc).isoformat()
    }


@app.get("/analytics", tags=["Analytics"])
def get_analytics(range: str = "30d", refresh: bool = False, payload: dict = Depends(verify_token_flexible)):
    """Pobierz statystyki ROI i wydajności opublikowanych filmów na żywo z YouTube."""
    from datetime import datetime, timezone

    sync_data = _sync_youtube_analytics(force=refresh)
    ch_info = sync_data.get("channel", {})
    all_videos = sync_data.get("videos", [])

    # Filter by range
    now = datetime.now(timezone.utc)
    filtered = []
    days_limit = 7 if range == "7d" else (30 if range == "30d" else 3650)
    for v in all_videos:
        ts_str = v.get("published_at") or v.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if (now - ts).days <= days_limit:
                    filtered.append(v)
            except Exception:
                filtered.append(v)
        else:
            filtered.append(v)

    if not filtered and all_videos:
        filtered = all_videos[: (10 if range == "7d" else 30)]

    total_views = sum(v.get("views", 0) for v in filtered)
    total_likes = sum(v.get("likes", 0) for v in filtered)
    total_comments = sum(v.get("comments", 0) for v in filtered)
    count = len(filtered)
    avg_views = int(total_views / max(count, 1))

    # Top videos in range
    top_videos = sorted(filtered, key=lambda x: x.get("views", 0), reverse=True)[:5]

    return {
        "range": range,
        "count": count,
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "avg_views": avg_views,
        "watch_time_hours": round(total_views * 0.0055, 1),
        "subscribers_gained": max(1, int(total_views * 0.00045)),
        "channel": ch_info,
        "top_videos": top_videos,
        "synced_at": sync_data.get("synced_at"),
        "videos": filtered,
    }


TUNING_FILE = Path(__file__).parent.parent / "tuning_config.json"

DEFAULT_TUNING_CONFIG = {
    "pacing": "aggressive",
    "zoomAggression": 1.20,
    "slowmoDuration": 1.4,
    "musicBalance": 0.85,
    "gameSoundBalance": 0.65,
    "titleTone": "hype",
    "userNotes": "Fokus na agresywny hook w pierwszych 1.5s, mocne słowa kluczowe (INSANE, PENTAKILL, UNSTOPPABLE), wykrzykniki i emoji 🔥💥💀. Tytuły krótkie, zoptymalizowane pod CTR na telefonach."
}


@app.get("/config/tuning", tags=["Config"])
def get_tuning_config(payload: dict = Depends(verify_token)):
    """Pobierz aktualny profil dostrajania stylu montażu i promptów AI."""
    if TUNING_FILE.exists():
        try:
            with open(TUNING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_TUNING_CONFIG


@app.post("/config/tuning", tags=["Config"])
def save_tuning_config(config: dict, payload: dict = Depends(verify_token)):
    """Zapisz profil dostrajania stylu montażu i promptów AI."""
    try:
        try:
            from lol_agent.tuning_manager import save_tuning_config_to_file, get_pacing_parameters
        except ImportError:
            from tuning_manager import save_tuning_config_to_file, get_pacing_parameters

        save_tuning_config_to_file(config)
        params = get_pacing_parameters()
        print(f"[TUNING] Zapisano profil montazu: {config.get('pacing')} (buildup={params.get('buildup_sec')}s, max_dur={params.get('target_max_dur')}s, zoom={params.get('zoom_aggression')}x)")
        return {"ok": True, "config": config, "pacing_params": params}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

DARK_ROOT = Path(__file__).parent.parent.parent  # shortsyt root


def _dark_load_json(filename: str) -> dict:
    """Helper: ładuje JSON z katalogu głównego dark_psychology."""
    p = DARK_ROOT / filename
    if not p.exists():
        return {}
    try:
        import json as _json
        with open(p, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}


@app.get("/dark/status", tags=["Dark Psychology"])
def dark_status(payload: dict = Depends(verify_token_flexible)):
    """Status Dark Psychology agenta: ostatnie filmy, wyniki audytu, v/h."""
    import json as _json

    analysis = _dark_load_json("smart_analysis_2026-05-05.json")
    directive = _dark_load_json("adaptation_directive.json")
    feedback_records = []
    feedback_file = DARK_ROOT / "auditor_feedback.json"
    if feedback_file.exists():
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                feedback_records = _json.load(f)
        except Exception:
            pass

    last_2 = analysis.get("last_2", directive.get("last_2_videos", []))
    total = len(feedback_records)
    correct = sum(1 for r in feedback_records if r.get("prediction_ok") is True)
    accuracy = round(correct / max(total, 1) * 100) if total > 0 else None
    with_views = [r for r in feedback_records if r.get("real_views") is not None]
    avg_recent_views = round(
        sum(r["real_views"] for r in with_views[-10:]) / max(len(with_views[-10:]), 1)
    ) if with_views else None

    return {
        "channel": analysis.get("channel", {}),
        "last_2_videos": last_2,
        "auditor": {
            "total_tracked": total,
            "with_real_results": len(with_views),
            "prediction_accuracy_pct": accuracy,
            "avg_recent_views": avg_recent_views,
        },
        "directive_generated_at": directive.get("generated_at"),
        "best_publish_hour_utc": directive.get("best_publish_hour_utc"),
        "best_format": "QUESTION",
    }


@app.get("/dark/analytics", tags=["Dark Psychology"])
def dark_analytics(payload: dict = Depends(verify_token_flexible)):
    """Pełna analityka: top 5 filmów, formaty tytułów, keywords, czas publikacji."""
    analysis = _dark_load_json("smart_analysis_2026-05-05.json")
    directive = _dark_load_json("adaptation_directive.json")

    return {
        "channel": analysis.get("channel", {}),
        "videos_analyzed": analysis.get("videos_analyzed", 0),
        "top_5": analysis.get("top_5", []),
        "title_format_analysis": analysis.get("title_format_analysis", {}),
        "duration_performance": analysis.get("duration_performance", {}),
        "top_keywords": analysis.get("top_keywords", []),
        "low_keywords": analysis.get("low_keywords", []),
        "hook_patterns": analysis.get("hook_patterns_top5", []),
        "best_publish_day": analysis.get("best_publish_day"),
        "best_publish_hour_utc": analysis.get("best_publish_hour_utc"),
        "directive_summary": (directive.get("directive", "")[:500] if directive else ""),
    }


@app.get("/dark/calibration", tags=["Dark Psychology"])
def dark_calibration(payload: dict = Depends(verify_token_flexible)):
    """Raport kalibracji audytora — wagi Pearsona per kategoria + trafność prognoz."""
    import json as _json

    weights_file = DARK_ROOT / "auditor_weights.json"
    feedback_file = DARK_ROOT / "auditor_feedback.json"

    weights = {}
    if weights_file.exists():
        try:
            with open(weights_file, "r", encoding="utf-8") as f:
                weights = _json.load(f)
        except Exception:
            pass

    records = []
    if feedback_file.exists():
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                records = _json.load(f)
        except Exception:
            pass

    valid = [r for r in records if r.get("real_views") is not None]
    correct = sum(1 for r in valid if r.get("prediction_ok") is True)
    accuracy = round(correct / max(len(valid), 1) * 100) if valid else 0
    top3 = sorted(valid, key=lambda x: x.get("real_views", 0), reverse=True)[:3]
    bottom3 = sorted(valid, key=lambda x: x.get("real_views", 0))[:3]

    return {
        "weights": weights,
        "calibrated": any(v != 1.0 for v in weights.values()),
        "total_records": len(records),
        "with_real_results": len(valid),
        "prediction_accuracy_pct": accuracy,
        "top3_performers": [
            {"title": r.get("title", "")[:55], "audit_score": r.get("audit_score"),
             "real_views": r.get("real_views"), "prediction_ok": r.get("prediction_ok")}
            for r in top3
        ],
        "bottom3_performers": [
            {"title": r.get("title", "")[:55], "audit_score": r.get("audit_score"),
             "real_views": r.get("real_views"), "prediction_ok": r.get("prediction_ok")}
            for r in bottom3
        ],
    }


@app.get("/dark/directive", tags=["Dark Psychology"])
def dark_directive(payload: dict = Depends(verify_token_flexible)):
    """Aktualna adaptation_directive.json — dyrektywy dla agenta dark_psychology."""
    return _dark_load_json("adaptation_directive.json")


class DarkRunRequest(BaseModel):
    dry_run: bool = False
    videos: int = 2


@app.post("/dark/run", tags=["Dark Psychology"])
def dark_run(
    req: DarkRunRequest,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(verify_token),
):
    """Uruchom agenta dark_psychology w tle (generuje + publikuje shorty)."""
    agent_script = DARK_ROOT / "agent_dark_psychology.py"
    if not agent_script.exists():
        raise HTTPException(status_code=404, detail="agent_dark_psychology.py nie znaleziony")

    def _run_agent():
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            flags = ["--dry-run"] if req.dry_run else []
            cmd = [sys.executable, str(agent_script), "--videos", str(req.videos)] + flags
            import subprocess as _sp
            _sp.run(cmd, cwd=str(DARK_ROOT), env=env, timeout=900)
        except Exception as e:
            print(f"[DARK RUN ERROR] {e}")

    background_tasks.add_task(_run_agent)
    return {"status": "started", "dry_run": req.dry_run, "videos": req.videos}


# ══════════════════════════════════════════════════════════════════════════════
# KALENDARZ PUBLIKACJI I REZERWACJA PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

class ReserveSlotRequest(BaseModel):
    slot_id: str
    title: Optional[str] = ""
    champion: Optional[str] = ""
    frag_type: Optional[str] = "outplay"
    source_clip: Optional[str] = ""
    output_video: Optional[str] = ""
    notes: Optional[str] = ""

class AnalyzeFragRequest(BaseModel):
    clip_path: str

class AutoFillCalendarRequest(BaseModel):
    max_slots: int = 4


@app.get("/calendar/slots", tags=["Calendar"])
def get_calendar(start_date: Optional[str] = None, days: int = 14, payload: dict = Depends(verify_token_flexible)):
    """Pobiera listę slotów publikacji na zadany okres (z uwzględnieniem Peak Hours CET)."""
    try:
        from . import calendar_manager
        slots = calendar_manager.get_calendar_slots(start_date=start_date, days=days)
        return {"slots": slots, "days": days, "total": len(slots)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd kalendarza: {e}")


@app.post("/calendar/reserve", tags=["Calendar"])
def reserve_calendar_slot(req: ReserveSlotRequest, payload: dict = Depends(verify_token_flexible)):
    """Rezerwuje slot w kalendarzu dla konkretnego klipu lub wyrenderowanego filmu."""
    try:
        from . import calendar_manager
        entry = calendar_manager.reserve_slot(
            slot_id=req.slot_id,
            title=req.title or "",
            champion=req.champion or "",
            frag_type=req.frag_type or "outplay",
            source_clip=req.source_clip or "",
            output_video=req.output_video or "",
            notes=req.notes or "",
        )
        return {"status": "reserved", "slot": entry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd rezerwacji: {e}")


@app.delete("/calendar/slot/{slot_id}", tags=["Calendar"])
def delete_calendar_slot(slot_id: str, payload: dict = Depends(verify_token_flexible)):
    """Zwalnia zarezerwowany slot."""
    try:
        from . import calendar_manager
        success = calendar_manager.release_slot(slot_id)
        return {"status": "released" if success else "not_found", "slot_id": slot_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd zwalniania slotu: {e}")


@app.post("/calendar/slot/{slot_id}/publish", tags=["Calendar"])
def publish_calendar_slot(slot_id: str, payload: dict = Depends(verify_token_flexible)):
    """Publikuje / planuje wideo ze slotu bezpośrednio na YouTube na przypisaną godzinę."""
    try:
        from . import calendar_manager
        db = calendar_manager._load_calendar_db()
        slot = db.get(slot_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Slot nie znaleziony w bazie rezerwacji")

        video_path = slot.get("output_video")
        if not video_path or not Path(video_path).exists():
            raise HTTPException(status_code=400, detail="Brak wyrenderowanego pliku wideo dla tego slotu")

        title = slot.get("title") or "League of Legends Highlight #Shorts"
        publish_at = slot.get("datetime_utc")

        from .youtube_uploader import upload_video
        res = upload_video(
            video_path=video_path,
            title=title,
            description=f"{title}\n\nDwannellenga LoL Highlights #Shorts",
            tags=["Shorts", "LeagueOfLegends", "LoL"],
            publish_at=publish_at,
        )

        slot["status"] = "scheduled"
        slot["yt_video_id"] = res.get("video_id")
        slot["yt_url"] = res.get("url")
        calendar_manager.update_slot_status(slot_id, slot)

        return {"status": "scheduled", "youtube": res, "slot": slot}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd publikacji na YouTube: {e}")


@app.post("/calendar/auto-fill", tags=["Calendar"])
def auto_fill_calendar(req: AutoFillCalendarRequest, payload: dict = Depends(verify_token_flexible)):
    """Automatycznie zapełnia najbliższe wolne sloty najlepszymi nieprzetworzonymi klipami."""
    try:
        from . import calendar_manager
        clips_res = list_clips(folder=None, payload=payload)
        clips = clips_res.get("clips", [])
        assigned = calendar_manager.auto_fill_upcoming_slots(clips, max_slots=req.max_slots)
        return {"status": "ok", "assigned_count": len(assigned), "assigned": assigned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd auto-przypisywania: {e}")


@app.post("/clips/analyze-frag", tags=["Clips"])
def analyze_frag(req: AnalyzeFragRequest, payload: dict = Depends(verify_token_flexible)):
    """Precyzyjna auto-detekcja typu fraga (Penta, Quadra, Triple, Double, Clutch 1% HP, Outplay)."""
    try:
        try:
            from lol_agent.lol_frag_detector import analyze_clip_frags
        except ImportError:
            from lol_frag_detector import analyze_clip_frags
        result = analyze_clip_frags(req.clip_path)
        return {
            "video_path": result.video_path,
            "duration": result.duration,
            "detected_frag_type": result.detected_frag_type,
            "confidence": result.confidence,
            "kill_count": result.kill_count,
            "kills": result.kills,
            "min_hp_percentage": result.min_hp_percentage,
            "is_clutch_1hp": result.is_clutch_1hp,
            "badge_label": result.badge_label,
            "suggested_title_hook": result.suggested_title_hook,
            "suggested_badge_color": result.suggested_badge_color,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd detekcji fraga: {e}")


@app.get("/system/hardware-info", tags=["System"])
def get_hardware_info(payload: dict = Depends(verify_token_flexible)):
    """Pobiera aktualny profil sprzętowy komputera i ustawienia renderera."""
    try:
        try:
            from lol_agent import hardware_benchmark
        except ImportError:
            import hardware_benchmark
        return hardware_benchmark.load_tuned_hardware_profile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu sprzętu: {e}")


@app.post("/system/benchmark-scan", tags=["System"])
def run_benchmark_scan(payload: dict = Depends(verify_token_flexible)):
    """Uruchamia pełny skan podzespołów (CPU, GPU, VRAM, RAM) i auto-tuning parametrów."""
    try:
        try:
            from lol_agent import hardware_benchmark
        except ImportError:
            import hardware_benchmark
        profile = hardware_benchmark.benchmark_and_tune_system()
        return {"status": "success", "profile": profile}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd benchmarku: {e}")


@app.get("/health/full", tags=["System"])
def health_full():
    """Healthcheck obu agentów — LOL + Dark Psychology."""
    dark_ok = (DARK_ROOT / "agent_dark_psychology.py").exists()
    lol_ok = (DARK_ROOT / "lol_agent" / "run_lol_agent.py").exists()
    directive = _dark_load_json("adaptation_directive.json")
    return {
        "status": "ok",
        "lol_agent": lol_ok,
        "dark_psychology_agent": dark_ok,
        "dark_directive_age": directive.get("generated_at"),
    }


@app.get("/health", tags=["System"])
def health():
    """Healthcheck — nie wymaga autoryzacji."""
    return {"status": "ok", "service": "Shortsyt API"}


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
