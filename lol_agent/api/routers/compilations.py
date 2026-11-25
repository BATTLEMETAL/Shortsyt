"""
Shortsyt API — Router: Tygodniowe/Miesięczne Kompilacje Poziome 16:9 & Viral Vault (`Etap 31.5`)
"""
from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import verify_token_flexible

router = APIRouter(tags=["Compilations"])

_STATE_LOCK = threading.Lock()
_COMP_STATE: Dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "step": "",
    "error": None,
    "latest": None,
}


class BootstrapRequest(BaseModel):
    champion: str = Field(default="Katarina", max_length=60)
    limit: int = Field(default=12, ge=1, le=40)


class RenderCompilationRequest(BaseModel):
    mode: str = Field(default="weekly", pattern="^(weekly|monthly)$")
    champion: str = Field(default="Katarina", max_length=60)
    max_clips: Optional[int] = Field(default=None, ge=2, le=40)
    auto_bootstrap: bool = True
    use_local_ai: bool = True


class PublishCompilationRequest(BaseModel):
    comp_id: Optional[str] = None
    output_filename: str = Field(..., min_length=3, max_length=200)
    title: str = Field(..., min_length=4, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = Field(default_factory=list)
    thumbnail_filename: Optional[str] = None
    privacy: str = Field(default="private", pattern="^(public|private|unlisted)$")
    publish_at: Optional[str] = None


def _rendered_dir() -> Path:
    from ...viral_vault import DEFAULT_VAULT_DIR
    d = DEFAULT_VAULT_DIR / "rendered"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/compilations/vault")
def compilations_vault(payload: dict = Depends(verify_token_flexible)):
    """Zwraca stan skarbca Viral Vault, kolekcję zatwierdzonych klipów i linki Studio Related Video."""
    from ...viral_vault import get_vault_summary
    from ..youtube_uploader import get_related_video_studio_links

    return {
        "ok": True,
        "vault": get_vault_summary(),
        "related_links": get_related_video_studio_links(limit=10),
    }


@router.post("/compilations/vault/bootstrap")
def compilations_vault_bootstrap(req: BootstrapRequest, payload: dict = Depends(verify_token_flexible)):
    """Zasila Viral Vault z najlepszych istniejących klipów w Outplayed."""
    from ...viral_vault import bootstrap_vault_from_outplayed, get_vault_summary

    res = bootstrap_vault_from_outplayed(champion=req.champion, limit=req.limit)
    return {"ok": True, "bootstrap": res, "vault": get_vault_summary()}


@router.post("/compilations/vault/sync")
def compilations_vault_sync(payload: dict = Depends(verify_token_flexible)):
    """Uruchamia ocenę wyników z performance_log.jsonl i promuje hity staging -> approved."""
    from ...lol_performance_tracker import _load_performance_log
    from ...viral_vault import evaluate_and_promote_vault, get_vault_summary

    rows = _load_performance_log()
    v_sorted = sorted(int(r.get("views") or 0) for r in rows if r.get("views") is not None)
    med = float(v_sorted[len(v_sorted) // 2]) if v_sorted else 1593.5
    res = evaluate_and_promote_vault(rows, channel_median_views=med)
    return {"ok": True, "promotion": res, "vault": get_vault_summary()}


@router.get("/compilations/status")
def compilations_status(payload: dict = Depends(verify_token_flexible)):
    with _STATE_LOCK:
        return dict(_COMP_STATE)


@router.get("/compilations/list")
def compilations_list(payload: dict = Depends(verify_token_flexible)):
    """Zwraca wyrenderowane kompilacje 16:9 z katalogu rendered/ + SQLite."""
    from ...state_db import list_compilations_db

    rdir = _rendered_dir()
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for row in list_compilations_db():
        cid = str(row.get("comp_id") or "")
        if cid:
            items_by_id[cid] = row

    for mf in sorted(rdir.glob("*.comp.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            row = json.loads(mf.read_text(encoding="utf-8", errors="ignore"))
            cid = str(row.get("comp_id") or mf.stem)
            items_by_id[cid] = row
        except Exception:
            continue

    items = sorted(items_by_id.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True)
    for it in items:
        fn = str(it.get("output_filename") or Path(str(it.get("output_path") or "")).name)
        tfn = str(it.get("thumbnail_filename") or Path(str(it.get("thumbnail_path") or "")).name)
        it["output_filename"] = fn
        it["thumbnail_filename"] = tfn
        it["video_exists"] = bool(fn and (rdir / fn).is_file())
        it["thumbnail_exists"] = bool(tfn and (rdir / tfn).is_file())
    return {"ok": True, "items": items, "total": len(items)}


@router.get("/compilations/media/{filename}")
def compilations_media(filename: str, payload: dict = Depends(verify_token_flexible)):
    """Bezpieczne serwowanie wyrenderowanego MP4 / miniatury 1280x720 z katalogu rendered/."""
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")
    rdir = _rendered_dir().resolve()
    target = (rdir / filename).resolve()
    if not target.is_relative_to(rdir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Plik nie istnieje")
    media_type = "video/mp4" if target.suffix.lower() == ".mp4" else "image/jpeg"
    return FileResponse(path=str(target), media_type=media_type, filename=target.name)


def build_compilation_sync(
    mode: str = "weekly",
    champion: str = "Katarina",
    max_clips: Optional[int] = None,
    auto_bootstrap: bool = True,
    use_local_ai: bool = True,
    progress_cb=None,
) -> Dict[str, Any]:
    """Synchroniczny pełny przebieg kompilacji 16:9 (render + miniatura 1280x720 + metadane SEO)."""
    from ...lol_longform_montage import render_longform_compilation
    from ...lol_longform_thumbnail import generate_longform_thumbnail
    from ...lol_metadata_generator import generate_longform_metadata
    from ...state_db import upsert_compilation_db
    from ...viral_vault import bootstrap_vault_from_outplayed, select_clips_for_compilation

    clips = select_clips_for_compilation(mode=mode, champion=champion, max_clips=max_clips)
    if len(clips) < 2 and auto_bootstrap:
        bootstrap_vault_from_outplayed(champion=champion, limit=12)
        clips = select_clips_for_compilation(mode=mode, champion=champion, max_clips=max_clips)
    if not clips:
        raise ValueError("Brak zatwierdzonych klipów w Viral Vault")

    rdir = _rendered_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_mp4 = rdir / f"lol_{mode}_{champion.lower()}_{ts}.mp4"
    manifest = render_longform_compilation(
        clips=clips,
        output_path=out_mp4,
        mode=mode,
        champion=champion,
        progress_cb=progress_cb,
    )
    meta = generate_longform_metadata(
        champion=champion,
        clips_meta=clips,
        duration_s=manifest["duration_s"],
        chapters=manifest.get("chapters"),
        tracks_used=manifest.get("tracks_used"),
        use_local_ai=use_local_ai,
    )
    hero = manifest.get("hero_clip") or {}
    thumb_path = out_mp4.with_name(out_mp4.stem + "_thumb_1280x720.jpg")
    generate_longform_thumbnail(
        video_path=hero.get("source_path") or str(out_mp4),
        peak_time_s=float(hero.get("peak_time_s") or 4.0),
        headline=meta["thumbnail_headline"],
        subline=meta["thumbnail_subline"],
        output_path=thumb_path,
    )

    full_record = {
        **manifest,
        "status": "rendered",
        "title": meta["title"],
        "description": meta["description"],
        "tags": meta["tags"],
        "hashtags": meta["hashtags"],
        "thumbnail_headline": meta["thumbnail_headline"],
        "thumbnail_subline": meta["thumbnail_subline"],
        "chapters_included": meta["chapters_included"],
        "thumbnail_path": str(thumb_path),
        "thumbnail_filename": thumb_path.name,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar = out_mp4.with_suffix(".comp.json")
    sidecar.write_text(json.dumps(full_record, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        upsert_compilation_db(full_record)
    except Exception:
        pass
    return full_record


@router.post("/compilations/render")
def compilations_render(req: RenderCompilationRequest, payload: dict = Depends(verify_token_flexible)):
    """Uruchamia renderowanie nowej kompilacji 16:9 w wątku tła (ZERO auto-upload)."""
    with _STATE_LOCK:
        if _COMP_STATE.get("status") == "running":
            return {"ok": False, "already_running": True, "state": dict(_COMP_STATE)}
        _COMP_STATE.update({
            "status": "running",
            "progress": 5,
            "step": f"Start kompilacji {req.mode} ({req.champion})...",
            "error": None,
        })

    def _runner():
        def _cb(pct: int, msg: str):
            with _STATE_LOCK:
                _COMP_STATE["progress"] = int(pct)
                _COMP_STATE["step"] = msg

        try:
            rec = build_compilation_sync(
                mode=req.mode,
                champion=req.champion,
                max_clips=req.max_clips,
                auto_bootstrap=req.auto_bootstrap,
                use_local_ai=req.use_local_ai,
                progress_cb=_cb,
            )
            with _STATE_LOCK:
                _COMP_STATE.update({
                    "status": "done",
                    "progress": 100,
                    "step": "Gotowe",
                    "error": None,
                    "latest": rec,
                })
        except Exception as exc:
            with _STATE_LOCK:
                _COMP_STATE.update({
                    "status": "error",
                    "progress": 0,
                    "step": "Błąd",
                    "error": str(exc),
                })

    threading.Thread(target=_runner, daemon=True).start()
    return {"ok": True, "started": True}


@router.post("/compilations/publish")
async def compilations_publish(req: PublishCompilationRequest, payload: dict = Depends(verify_token_flexible)):
    """Ręcznie publikuje lub planuje wyrenderowaną kompilację 16:9 jako film YouTube (is_short=False)."""
    from ..youtube_uploader import upload_video
    from ...state_db import record_published_video_db, upsert_compilation_db

    if "/" in req.output_filename or "\\" in req.output_filename or ".." in req.output_filename:
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")
    rdir = _rendered_dir().resolve()
    mp4_path = (rdir / req.output_filename).resolve()
    if not mp4_path.is_relative_to(rdir) or not mp4_path.is_file():
        raise HTTPException(status_code=404, detail="Plik kompilacji nie istnieje")

    thumb_path = None
    if req.thumbnail_filename:
        if "/" in req.thumbnail_filename or "\\" in req.thumbnail_filename or ".." in req.thumbnail_filename:
            raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa miniatury")
        tp = (rdir / req.thumbnail_filename).resolve()
        if tp.is_relative_to(rdir) and tp.is_file():
            thumb_path = str(tp)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: upload_video(
            video_path=str(mp4_path),
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy=req.privacy,
            thumbnail_path=thumb_path,
            publish_at=req.publish_at,
            is_short=False,
        ),
    )

    try:
        pub_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "video_id": result.get("video_id"),
            "url": result.get("url"),
            "video_format": "longform",
            "title": result.get("title"),
            "status": "scheduled" if result.get("publish_at") else "published",
            "privacy": result.get("status"),
            "scheduled_publish_at": result.get("publish_at"),
            "source_path": str(mp4_path),
        }
        pub_file = Path(__file__).resolve().parent.parent.parent / "published_videos.jsonl"
        with open(pub_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")
        record_published_video_db(pub_log)

        sidecar = mp4_path.with_suffix(".comp.json")
        if sidecar.is_file():
            rec = json.loads(sidecar.read_text(encoding="utf-8", errors="ignore"))
            rec["status"] = "scheduled" if result.get("publish_at") else "published"
            rec["youtube_id"] = result.get("video_id")
            rec["youtube_url"] = result.get("url")
            sidecar.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
            upsert_compilation_db(rec)
    except Exception:
        pass

    return {"ok": True, **result}
