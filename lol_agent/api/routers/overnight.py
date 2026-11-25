"""
Shortsyt API — Router: Tryb Nocny (Overnight Batch Top 5 + Rekomendacja Synapsy)
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import verify_token
from ..helpers import _load_meta, compute_publish_status_flags

try:
    from lol_agent import synapsa_overnight_batch as _ob
    from lol_agent.api.routers.clips import scan_available_clips
    from lol_agent.outplayed_db import summarize_clip_catalog
except ImportError:
    import synapsa_overnight_batch as _ob  # type: ignore
    from api.routers.clips import scan_available_clips  # type: ignore
    from outplayed_db import summarize_clip_catalog  # type: ignore

router = APIRouter(tags=["Overnight"])


class OvernightStartRequest(BaseModel):
    folder: Optional[str] = None
    top_n: int = Field(5, ge=1, le=10)
    skip_published: bool = True
    champion_name: str = "Katarina"
    rank: str = "Master"
    use_local_ai: bool = True
    tier_filter: Literal["auto", "all", "any_kill", "double_plus", "triple_plus", "quadra_plus"] = "auto"
    only_channel_champion: bool = True


@router.post("/overnight/start")
def overnight_start(req: OvernightStartRequest, payload: dict = Depends(verify_token)):
    """Uruchamia tryb nocny w tle: skanuje folder, montuje Top N shortów bez uploadu i wyłania #1."""
    ok = _ob.start_overnight_batch_async(
        folder=req.folder,
        top_n=req.top_n,
        champion_name=req.champion_name,
        rank=req.rank,
        skip_published=req.skip_published,
        use_local_ai=req.use_local_ai,
        tier_filter=req.tier_filter,
        only_channel_champion=req.only_channel_champion,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tryb nocny lub zwykły render już działa — poczekaj na koniec lub zatrzymaj.",
        )
    return {
        "status": "started",
        "top_n": req.top_n,
        "tier_filter": req.tier_filter,
        "only_channel_champion": req.only_channel_champion,
        "auto_publish": False,
    }


@router.get("/overnight/catalog")
def overnight_catalog(
    folder: Optional[str] = None,
    champion_name: Optional[str] = "Katarina",
    skip_published: bool = True,
    payload: dict = Depends(verify_token),
):
    """Zwraca katalog klipów pogrupowany wg tierów Riot API, ulubionych, bohaterów i meczów."""
    all_clips = scan_available_clips(folder)
    filtered = [
        c for c in all_clips
        if not (skip_published and c.get("already_published"))
    ]
    if champion_name and champion_name.strip():
        req_ch = champion_name.strip().lower()
        champ_filtered = [
            c for c in filtered
            if not str(c.get("champion") or "").strip()
            or str(c.get("champion") or "").strip().lower() == req_ch
        ]
    else:
        champ_filtered = filtered

    summary = summarize_clip_catalog(champ_filtered)
    summary["all_champions_summary"] = summarize_clip_catalog(all_clips)
    summary["requested_champion"] = champion_name or ""
    summary["skip_published"] = skip_published
    return summary


@router.get("/overnight/status")
def overnight_status(payload: dict = Depends(verify_token)):
    """Zwraca bieżący postęp pracy trybu nocnego (skanowanie / montaż / ocena)."""
    return _ob.get_overnight_status()


@router.post("/overnight/stop")
def overnight_stop(payload: dict = Depends(verify_token)):
    """Zatrzymuje bieżącą sesję trybu nocnego."""
    _ob.stop_overnight_batch()
    return {"status": "stopping"}


@router.get("/overnight/latest")
def overnight_latest(payload: dict = Depends(verify_token)):
    """Zwraca manifest ostatniej paczki nocnej wzbogacony o stan publikacji/kolejki i istnienie pliku .mp4."""
    import json
    from pathlib import Path
    from ..helpers import _load_meta

    batch = _ob.load_latest_overnight_batch()
    if not isinstance(batch, dict):
        return {"batch": batch}

    pub_sources: dict[str, dict] = {}
    try:
        pub_file = Path(__file__).resolve().parent.parent.parent / "published_videos.jsonl"
        if pub_file.is_file():
            for line in pub_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                sp = str(rec.get("source_path") or "").strip().lower()
                if sp:
                    pub_sources[sp] = rec
                    pub_sources[Path(sp).name.lower()] = rec
    except Exception:
        pass

    queue_by_name: dict[str, dict] = {}
    try:
        from ...scheduled_queue import QUEUE_FILE, _load_queue
        if QUEUE_FILE.exists():
            for q_it in _load_queue():
                if q_it.get("status") not in ("pending", "processing", "published"):
                    continue
                q_name = Path(str(q_it.get("video_path") or "")).name.lower()
                if not q_name:
                    continue
                slot = queue_by_name.setdefault(q_name, {"platforms": set(), "scheduled": None})
                plat = str(q_it.get("platform") or "").strip().lower()
                if plat:
                    slot["platforms"].add(plat)
                if q_it.get("status") == "pending" and q_it.get("publish_at") and not slot["scheduled"]:
                    slot["scheduled"] = q_it.get("publish_at")
    except Exception:
        pass

    for it in (batch.get("items") or []):
        if not isinstance(it, dict):
            continue
        out_name = str(it.get("output_filename") or "")
        out_path = str(it.get("output_path") or "")
        meta = _load_meta(out_name) or {} if out_name else {}
        q_info = queue_by_name.get(out_name.lower(), {})
        extra_plats = set(q_info.get("platforms") or set())

        src_raw = str(it.get("source_path") or meta.get("source_path") or "").strip().lower()
        src_name = Path(src_raw).name.lower() if src_raw else str(it.get("source_filename") or "").strip().lower()
        pub_rec = pub_sources.get(src_raw) or pub_sources.get(src_name)
        if pub_rec:
            for p_k in (pub_rec.get("platforms") or []):
                extra_plats.add(str(p_k).lower())
            if pub_rec.get("video_id"):
                extra_plats.add("youtube")

        file_exists = bool(out_path and Path(out_path).is_file())
        pub_flags = compute_publish_status_flags(
            meta,
            queued_plats=extra_plats,
            file_exists=file_exists,
        )
        it["file_exists"] = file_exists
        it["scheduled_publish_at"] = (
            meta.get("scheduled_publish_at")
            or q_info.get("scheduled")
            or (pub_rec or {}).get("scheduled_publish_at")
        )
        it.update(pub_flags)

    return {"batch": batch}


@router.get("/overnight/batches")
def overnight_batches(limit: int = 10, payload: dict = Depends(verify_token)):
    """Zwraca listę ostatnich paczek nocnych."""
    return {"batches": _ob.list_overnight_batches(limit=limit)}
