"""
Shortsyt API — Router: Clips, Outputs, Thumbnails & Camera Preview
"""
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response

from ..auth import verify_token, verify_token_flexible
from ..config import LOL_INPUT_DIR, LOL_OUTPUT_DIR, LOL_TEMP_DIR
from ..helpers import _load_meta, _save_meta
from ..models import AutoDetectRequest, SaveMetadataRequest, AnalyzeFragRequest

router = APIRouter(tags=["Files", "Clips"])


def scan_available_clips(folder: Optional[str] = None) -> list:
    """Skanuje foldery z nagraniami (Outplayed / Medal / custom) i zwraca listę metadanych klipów."""
    try:
        try:
            from lol_agent.run_lol_agent import check_duplicate_clip
        except ImportError:
            from run_lol_agent import check_duplicate_clip
    except ImportError:
        check_duplicate_clip = None

    pre_analysis_map = {}
    pre_analysis_file = Path(__file__).parent.parent.parent / "lol_pre_analysis.json"
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
    return clips


@router.get("/clips")
def list_clips(folder: Optional[str] = None, payload: dict = Depends(verify_token)):
    """Lista plików MP4 w folderach nagrań (Outplayed / Medal lub podany folder) wraz ze statusem publikacji (dedup)."""
    return {"clips": scan_available_clips(folder)}


@router.post("/clips/auto-detect")
async def auto_detect_clip(req: AutoDetectRequest, payload: dict = Depends(verify_token)):
    """Automatycznie wykrywa optymalny punkt startu, końca i peak momentu na podstawie OCR i analizy wideo."""
    source_path = req.source_path
    if source_path and not Path(source_path).is_absolute() and not Path(source_path).exists():
        candidate_dirs = [
            LOL_INPUT_DIR,
            Path(r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends"),
            Path(r"C:\Medal\Edits"),
        ]
        target_name = Path(source_path).name
        found = None
        for search_dir in candidate_dirs:
            if not search_dir.exists():
                continue
            cand = search_dir / target_name
            if cand.is_file():
                found = str(cand.resolve())
                break
            try:
                for entry in os.scandir(search_dir):
                    if entry.is_dir():
                        sub_cand = Path(entry.path) / target_name
                        if sub_cand.is_file():
                            found = str(sub_cand.resolve())
                            break
            except Exception:
                pass
            if found:
                break
        if found:
            source_path = found

    if not Path(source_path).exists():
        raise HTTPException(status_code=404, detail=f"Plik źródłowy nie istnieje: {source_path}")

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

    try:
        loop = asyncio.get_event_loop()
        frag_res = await loop.run_in_executor(
            None,
            lambda: analyze_clip_frags(source_path, sample_fps=1.0)
        )
        detected_action = frag_res.detected_frag_type or "outplay"
        clip_start, clip_end, peak_moment, combat_segs = compute_optimal_clip_window(
            frag_res, total_dur, action_type=req.action_type or detected_action
        )
        if detected_action == "solo_bolo" or req.action_type == "solo_bolo":
            combat_segs = None
        confidence = f"OCR AI: {frag_res.badge_label} ({int(frag_res.confidence * 100)}%)"
        peaks = [(k["timestamp"], k["label"]) for k in frag_res.kills if (k.get("tier", 1) >= 2 or k.get("timestamp", 0) > 1.0)]
    except Exception as ex:
        import traceback
        traceback.print_exc()
        detected_action = req.action_type or "outplay"
        clip_end = max(5.0, round(total_dur - 1.0, 1))
        clip_start = max(0.0, round(clip_end - 12.0, 1))
        peak_moment = max(1.0, round(clip_end - clip_start - 2.5, 1))
        confidence = "Szacowanie okna Outplayed (Fallback)"
        peaks = []
        combat_segs = None

    suggested_hook = getattr(frag_res, "suggested_title_hook", "") if 'frag_res' in locals() and frag_res else ""
    if suggested_hook and suggested_hook.strip():
        hook_text = suggested_hook.strip()
    else:
        HOOK_MAP = {
            "pentakill": "PENTAKILL - DID ENEMY FF?",
            "quadrakill": "QUADRA KILL - ONE MORE LEFT",
            "triple": "TRIPLE KILL - ENEMY DIFF",
            "double": "DOUBLE KILL - CLEAN OR LUCKY?",
            "clutch": "1% HP CLUTCH - WATCH THIS",
            "solo_bolo": "CLEAN SOLO BOLO 1v1",
            "outplay": "HOW IS THIS POSSIBLE?",
        }
        hook_text = HOOK_MAP.get(detected_action, f"{detected_action.upper().replace('_', ' ')}!")

    map_zone_info = {"zone": "unknown", "zone_label": "", "confidence": 0.0}
    try:
        try:
            from lol_agent.lol_minimap_analyzer import detect_map_zone
        except ImportError:
            from lol_minimap_analyzer import detect_map_zone
        abs_peak = float(clip_start + peak_moment)
        map_zone_info = detect_map_zone(source_path, abs_peak, clip_start)
    except Exception:
        pass

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
        "map_zone": map_zone_info,
    }


@router.post("/clips/analyze-frag")
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


@router.get("/outputs")
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


@router.delete("/outputs/{filename}")
def delete_output(filename: str, payload: dict = Depends(verify_token)):
    """Usuń wyrenderowany plik Short i powiązaną miniaturkę (odrzucenie przez użytkownika)."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent.parent / "thumbnails"]
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

    try:
        from lol_agent.user_learning_memory import record_render_rejected
        record_render_rejected(filename, reason="Odrzucony i usunięty przez użytkownika w monitorze renderu")
    except Exception:
        pass

    return {"status": "deleted", "filename": filename}


@router.get("/outputs/{filename}/metadata")
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


@router.post("/outputs/{filename}/metadata")
def save_output_metadata(filename: str, req: SaveMetadataRequest, payload: dict = Depends(verify_token_flexible)):
    """
    Zapisz metadane YouTube (tytuł, opis, tagi) — BEZ re-renderu.
    Jeśli przekazano parametry renderowania, zapisuje je i zwraca needs_rerender=True.
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


@router.get("/outputs/{filename}")
def stream_output(
    filename: str,
    payload: dict = Depends(verify_token_flexible),
):
    """Streamuj gotowy Short do podglądu."""
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


@router.get("/thumbnails")
def list_thumbnails(payload: dict = Depends(verify_token)):
    """Lista wygenerowanych miniaturek Shorts."""
    thumbs = []
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent.parent / "thumbnails"]
    seen = set()
    for search_dir in search_dirs:
        if Path(search_dir).exists():
            for f in Path(search_dir).glob("*thumb*.jpg"):
                if f.name not in seen:
                    seen.add(f.name)
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


@router.get("/thumbnails/{filename}")
def stream_thumbnail(filename: str):
    """Pobierz plik miniaturki JPG (9:16)."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR, Path(__file__).parent.parent.parent / "thumbnails"]
    for d in search_dirs:
        fp = Path(d) / filename
        if fp.exists():
            return FileResponse(
                str(fp),
                media_type="image/jpeg",
            )
    raise HTTPException(status_code=404, detail=f"Miniaturka nie znaleziona: {filename}")


@router.get("/camera-preview")
def get_camera_preview(
    file_path: str,
    timestamp: float = 0.0,
    crop_x: Optional[int] = None,
    payload: dict = Depends(verify_token_flexible),
):
    """Zwraca klatkę podglądu z naniesionym prostokątem kadru 9:16 (608x1080)."""
    p = Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Klip nie istnieje: {file_path}")

    cmd = [
        "ffmpeg", "-y", "-ss", str(max(0.0, timestamp)),
        "-i", str(p),
        "-vframes", "1",
        "-vf", "scale=1920:1080",
        "-f", "image2pipe",
        "-vcodec", "rawvideo",
        "-pix_fmt", "bgr24",
        "-"
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=15)
        frame_bytes = proc.stdout
        frame = np.frombuffer(frame_bytes, np.uint8).reshape((1080, 1920, 3)).copy()

        cx = crop_x if crop_x is not None else (1920 - 608) // 2
        cx = max(0, min(cx, 1920 - 608))

        cv2.rectangle(frame, (cx, 0), (cx + 608, 1080), (0, 215, 255), 4)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (cx, 1080), (0, 0, 0), -1)
        cv2.rectangle(overlay, (cx + 608, 0), (1920, 1080), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        _, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        return Response(content=enc.tobytes(), media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd generowania podglądu kadru: {e}")
