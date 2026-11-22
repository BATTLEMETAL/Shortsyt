"""
Shortsyt API — Router: Tryb Nocny (Overnight Batch Top 5 + Rekomendacja Synapsy)
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import verify_token

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
    """Zwraca manifest ostatniej paczki nocnej z rekomendacją Synapsy #1..#5."""
    return {"batch": _ob.load_latest_overnight_batch()}


@router.get("/overnight/batches")
def overnight_batches(limit: int = 10, payload: dict = Depends(verify_token)):
    """Zwraca listę ostatnich paczek nocnych."""
    return {"batches": _ob.list_overnight_batches(limit=limit)}
