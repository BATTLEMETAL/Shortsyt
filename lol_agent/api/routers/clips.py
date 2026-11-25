"""
Shortsyt API — Router: Clips, Outputs, Thumbnails & Camera Preview
"""
import io
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps

from ..auth import verify_token, verify_token_flexible
from ..config import LOL_INPUT_DIR, LOL_OUTPUT_DIR, LOL_TEMP_DIR
from ..helpers import _load_meta, _save_meta, compute_publish_status_flags
from ..models import AutoDetectRequest, SaveMetadataRequest, AnalyzeFragRequest

try:
    from lol_agent.outplayed_db import (
        TIER_RANKS as _TIER_RANKS,
        get_outplayed_clip_info,
        load_outplayed_index,
        parse_outplayed_path_info,
    )
except ImportError:
    from outplayed_db import (  # type: ignore
        TIER_RANKS as _TIER_RANKS,
        get_outplayed_clip_info,
        load_outplayed_index,
        parse_outplayed_path_info,
    )

try:
    from lol_agent.medal_db import get_clip_metadata as _get_medal_metadata
except ImportError:
    try:
        from medal_db import get_clip_metadata as _get_medal_metadata  # type: ignore
    except ImportError:
        _get_medal_metadata = None  # type: ignore

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
            Path.home() / "Videos" / "Overwolf" / "Outplayed" / "League of Legends",
            Path(r"C:\Medal\Edits"),
        ]
    seen_paths = set()
    clips = []

    try:
        outplayed_index = load_outplayed_index()
    except Exception:
        outplayed_index = {}

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for ext in ["*.mp4", "*.mov", "*.mkv", "*.avi"]:
            for f in s_dir.rglob(ext):
                if any("recently deleted" in part.lower() for part in f.parts):
                    continue
                full_path_str = str(f.resolve())
                if full_path_str in seen_paths:
                    continue
                seen_paths.add(full_path_str)

                try:
                    stat_res = f.stat()
                    size_bytes = stat_res.st_size
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
                path_info = parse_outplayed_path_info(full_path_str)
                op_info = get_outplayed_clip_info(full_path_str, index=outplayed_index)

                champion = ""
                is_favorite = False
                event_tier = ""
                event_tier_rank: Optional[int] = None
                event_source = "none"
                best_event_time_s: Optional[float] = None
                est_first_kill_s: Optional[float] = None
                est_last_kill_s: Optional[float] = None
                total_kills_in_clip: Optional[int] = None
                match_kda = ""

                if op_info:
                    champion = str(op_info.get("champion") or "")
                    is_favorite = bool(op_info.get("is_favorite", False))
                    event_tier = str(op_info.get("event_tier") or "")
                    event_tier_rank = op_info.get("event_tier_rank")
                    event_source = str(op_info.get("source") or "outplayed_backup")
                    best_event_time_s = op_info.get("best_event_time_s")
                    est_first_kill_s = op_info.get("est_first_kill_s")
                    est_last_kill_s = op_info.get("est_last_kill_s")
                    total_kills_in_clip = op_info.get("total_kills_in_clip")
                    match_kda = str(op_info.get("match_kda") or "")
                elif _get_medal_metadata is not None and "medal" in full_path_str.lower():
                    try:
                        medal_info = _get_medal_metadata(full_path_str) or {}
                    except Exception:
                        medal_info = {}
                    if medal_info:
                        champion = str(medal_info.get("champion") or "")
                        raw_act = str(medal_info.get("action_type") or "").lower()
                        for m_kw, m_tier in (
                            ("penta", "pentakill"),
                            ("quadra", "quadrakill"),
                            ("triple", "triple"),
                            ("double", "double"),
                            ("kill", "single_kill"),
                        ):
                            if m_kw in raw_act:
                                event_tier = m_tier
                                event_tier_rank = _TIER_RANKS.get(m_tier)
                                event_source = "medal_db"
                                break

                if not event_tier and pre_item.get("action_type"):
                    pre_act = str(pre_item.get("action_type") or "").strip().lower()
                    if pre_act in _TIER_RANKS:
                        event_tier = pre_act
                        event_tier_rank = _TIER_RANKS[pre_act]
                        if event_source == "none":
                            event_source = "scan_cache"

                if not champion and pre_item.get("champion"):
                    champion = str(pre_item.get("champion") or "")

                clips.append({
                    "filename": f.name,
                    "path": full_path_str,
                    "size_mb": round(size_bytes / 1024 / 1024, 1),
                    "modified": stat_res.st_mtime,
                    "already_published": is_dup,
                    "published_url": pub_url,
                    "duplicate_reason": dup_reason,
                    "pre_score": pre_item.get("score"),
                    "pre_action": pre_item.get("action_type"),
                    "pre_recommendation": pre_item.get("recommendation"),
                    "match_folder": (op_info or {}).get("match_folder") or path_info["match_folder"],
                    "match_date": (op_info or {}).get("match_date") or path_info["match_date"],
                    "clip_base_key": (op_info or {}).get("clip_base_key") or path_info["clip_base_key"],
                    "champion": champion,
                    "is_favorite": is_favorite,
                    "event_tier": event_tier,
                    "event_tier_rank": event_tier_rank,
                    "event_source": event_source,
                    "best_event_time_s": best_event_time_s,
                    "est_first_kill_s": est_first_kill_s,
                    "est_last_kill_s": est_last_kill_s,
                    "total_kills_in_clip": total_kills_in_clip,
                    "match_kda": match_kda,
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
            Path.home() / "Videos" / "Overwolf" / "Outplayed" / "League of Legends",
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
    """Lista gotowych Shortów wraz ze statusem publikacji / kolejki i blokadą duplikatów."""
    queued_by_path: dict[str, dict] = {}
    try:
        from ...scheduled_queue import QUEUE_FILE, _load_queue
        if QUEUE_FILE.exists():
            for q_it in _load_queue():
                if q_it.get("status") not in ("pending", "processing", "published"):
                    continue
                q_vp = str(q_it.get("video_path") or "").strip()
                if not q_vp:
                    continue
                try:
                    key = str(Path(q_vp).resolve()).lower()
                except Exception:
                    key = q_vp.lower()
                slot = queued_by_path.setdefault(key, {"platforms": set(), "scheduled": None})
                plat = str(q_it.get("platform") or "").strip().lower()
                if plat:
                    slot["platforms"].add(plat)
                if q_it.get("status") == "pending" and q_it.get("publish_at") and not slot["scheduled"]:
                    slot["scheduled"] = q_it.get("publish_at")
    except Exception:
        pass

    outputs = []
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    for search_dir in search_dirs:
        if Path(search_dir).exists():
            for f in Path(search_dir).glob("*.mp4"):
                if "short" in f.name.lower() or "test" in f.name.lower():
                    meta = _load_meta(f.name) or {}
                    try:
                        f_key = str(f.resolve()).lower()
                    except Exception:
                        f_key = str(f).lower()
                    q_info = queued_by_path.get(f_key, {})
                    pub_flags = compute_publish_status_flags(
                        meta,
                        queued_plats=set(q_info.get("platforms") or set()),
                        file_exists=True,
                    )
                    outputs.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "modified": f.stat().st_mtime,
                        "scheduled_publish_at": meta.get("scheduled_publish_at") or q_info.get("scheduled"),
                        "file_exists": True,
                        **pub_flags,
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


def _sanitize_single_filename(name: str) -> str:
    """Waliduje pojedynczą nazwę pliku (bez path traversal)."""
    raw = str(name or "").strip()
    if (
        not raw
        or raw in (".", "..")
        or "\x00" in raw
        or "/" in raw
        or "\\" in raw
        or ".." in raw
        or Path(raw).name != raw
    ):
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku.")
    return raw


def _thumbnail_search_dirs() -> list[Path]:
    return [Path(LOL_TEMP_DIR), Path(LOL_OUTPUT_DIR), Path(__file__).resolve().parent.parent.parent / "thumbnails"]


def _find_output_video(safe_filename: str) -> Path:
    for d in (Path(LOL_TEMP_DIR), Path(LOL_OUTPUT_DIR)):
        fp = d / safe_filename
        if fp.is_file():
            return fp
    raise HTTPException(status_code=404, detail=f"Plik wideo nie znaleziony: {safe_filename}")


def _cleanup_stale_thumbnails(thumb_name: str, keep_path: Path) -> None:
    try:
        keep_resolved = keep_path.resolve()
    except Exception:
        keep_resolved = keep_path
    for d in _thumbnail_search_dirs():
        cand = d / thumb_name
        try:
            if cand.is_file() and cand.resolve() != keep_resolved:
                cand.unlink(missing_ok=True)
        except Exception:
            pass


def _persist_thumbnail_links(video_filename: str, thumb_path: Path) -> None:
    _save_meta(video_filename, {
        "thumbnail_path": str(thumb_path),
        "thumbnail_filename": thumb_path.name,
    })
    try:
        try:
            from lol_agent.synapsa_overnight_batch import update_overnight_item_thumbnail
        except ImportError:
            from synapsa_overnight_batch import update_overnight_item_thumbnail  # type: ignore
        update_overnight_item_thumbnail(video_filename, str(thumb_path))
    except Exception:
        pass


@router.get("/outputs/{filename}")
def stream_output(
    filename: str,
    payload: dict = Depends(verify_token_flexible),
):
    """Streamuj gotowy Short do podglądu."""
    safe_name = _sanitize_single_filename(filename)
    fp = _find_output_video(safe_name)
    return FileResponse(
        str(fp),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/thumbnails")
def list_thumbnails(payload: dict = Depends(verify_token)):
    """Lista wygenerowanych miniaturek Shorts."""
    thumbs = []
    search_dirs = _thumbnail_search_dirs()
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
    safe_name = _sanitize_single_filename(filename)
    for d in _thumbnail_search_dirs():
        fp = Path(d) / safe_name
        if fp.is_file():
            return FileResponse(
                str(fp),
                media_type="image/jpeg",
                headers={"Cache-Control": "no-cache, max-age=0"},
            )
    raise HTTPException(status_code=404, detail=f"Miniaturka nie znaleziona: {safe_name}")


@router.post("/outputs/{filename}/thumbnail")
async def upload_output_thumbnail(
    filename: str,
    file: UploadFile = File(...),
    payload: dict = Depends(verify_token),
):
    """Wgrywa własną miniaturkę (JPG/PNG/WebP), konwertuje do 1080x1920 JPG i podpina pod Shorta."""
    safe_video = _sanitize_single_filename(filename)
    video_fp = _find_output_video(safe_video)

    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext and ext not in allowed_exts:
            raise HTTPException(status_code=400, detail=f"Obsługiwane formaty miniaturek: JPG, PNG, WebP (otrzymano {ext}).")

    max_bytes = 15 * 1024 * 1024
    raw_bytes = await file.read(max_bytes + 1)
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Przesłany plik miniaturki jest pusty.")
    if len(raw_bytes) > max_bytes:
        raise HTTPException(status_code=413, detail="Plik miniaturki przekracza limit 15 MB.")

    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            norm = ImageOps.exif_transpose(img).convert("RGB")
            fitted = ImageOps.fit(norm, (1080, 1920), method=Image.Resampling.LANCZOS)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Nieprawidłowy plik graficzny: {exc}")

    dest = video_fp.with_name(f"{video_fp.stem}_thumb.jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        fitted.save(tmp, format="JPEG", quality=92, optimize=True)
        os.replace(tmp, dest)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    _cleanup_stale_thumbnails(dest.name, dest)
    _persist_thumbnail_links(safe_video, dest)
    return {
        "status": "ok",
        "thumbnail_filename": dest.name,
        "thumbnail_path": str(dest),
        "size_kb": round(dest.stat().st_size / 1024, 1),
    }


@router.post("/outputs/{filename}/thumbnail/regenerate")
def regenerate_output_thumbnail(
    filename: str,
    variant: Optional[int] = None,
    payload: dict = Depends(verify_token),
):
    """Generuje ponownie miniaturkę 9:16 z klatki akcji, rotując warianty przy kolejnych kliknięciach."""
    safe_video = _sanitize_single_filename(filename)
    video_fp = _find_output_video(safe_video)
    meta = _load_meta(safe_video) or {}
    try:
        prev_variant = int(meta.get("thumbnail_variant_index") or 0)
    except (TypeError, ValueError):
        prev_variant = 0
    next_variant = max(0, int(variant)) if variant is not None else (prev_variant + 1)

    overnight_item = None
    try:
        try:
            from lol_agent.synapsa_overnight_batch import load_latest_overnight_batch
        except ImportError:
            from synapsa_overnight_batch import load_latest_overnight_batch  # type: ignore
        batch = load_latest_overnight_batch() or {}
        for it in (batch.get("items") or []):
            if Path(str(it.get("output_filename") or "")).name == safe_video:
                overnight_item = it
                break
    except Exception:
        overnight_item = None

    action_type = str(meta.get("action_type") or (overnight_item or {}).get("action_type") or "outplay")
    champion_name = str(meta.get("champion_name") or (overnight_item or {}).get("champion_name") or "Katarina")
    clip_start = meta.get("clip_start") if meta.get("clip_start") is not None else (overnight_item or {}).get("clip_start")
    peak_moment = meta.get("peak_moment") if meta.get("peak_moment") is not None else (overnight_item or {}).get("peak_moment")

    dur_s = 0.0
    cap = cv2.VideoCapture(str(video_fp))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        if fps > 0.0 and frames > 0.0:
            dur_s = frames / fps
    finally:
        cap.release()
    if dur_s <= 0.0:
        dur_s = float(meta.get("duration") or (overnight_item or {}).get("duration_s") or 15.0)

    thumb_time = max(0.5, min(max(0.8, dur_s - 0.8), dur_s * 0.55))
    if peak_moment is not None:
        try:
            rel_peak = float(peak_moment) - (float(clip_start) if clip_start is not None else 0.0)
            if 0.2 <= rel_peak <= max(0.5, dur_s - 0.5):
                thumb_time = rel_peak
        except (TypeError, ValueError):
            pass

    try:
        try:
            from lol_agent.lol_thumbnail import generate_thumbnail
        except ImportError:
            from lol_thumbnail import generate_thumbnail  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Moduł miniaturek niedostępny: {exc}")

    dest = video_fp.with_name(f"{video_fp.stem}_thumb.jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_jpg = dest.with_name(f"{dest.stem}.regen_{os.getpid()}_{threading.get_ident()}.jpg")
    src_path = meta.get("source_path") or (overnight_item or {}).get("source_path")
    has_clean_src = bool(src_path and Path(str(src_path)).is_file())
    if has_clean_src:
        src_peak = (
            float(peak_moment)
            if peak_moment is not None
            else (float(clip_start or 0.0) + float(thumb_time))
        )
    else:
        src_peak = None
    try:
        generated = generate_thumbnail(
            video_path=str(video_fp),
            peak_moment=thumb_time,
            action_label=action_type.upper().replace("_", " "),
            champion_name=champion_name,
            output_path=str(tmp_jpg),
            source_clip_path=str(src_path) if has_clean_src else None,
            source_peak_moment=src_peak,
            variant_index=next_variant,
        )
        if not generated or not Path(generated).is_file():
            raise HTTPException(status_code=500, detail="Nie udało się wygenerować miniaturki z wideo.")
        os.replace(generated, dest)
    except HTTPException:
        try:
            tmp_jpg.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            tmp_jpg.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Błąd generowania miniaturki: {exc}")

    _cleanup_stale_thumbnails(dest.name, dest)
    _persist_thumbnail_links(safe_video, dest)
    _save_meta(safe_video, {"thumbnail_variant_index": next_variant})
    return {
        "status": "ok",
        "thumbnail_filename": dest.name,
        "thumbnail_path": str(dest),
        "size_kb": round(dest.stat().st_size / 1024, 1),
        "variant_index": next_variant,
    }


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
