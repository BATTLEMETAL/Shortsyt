"""
Shortsyt API — Router: Niche Research, Anti-Plagiarism & Client DFY Preview
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import verify_token_flexible

router = APIRouter(tags=["Research"])


class NicheResearchRequest(BaseModel):
    niche_query: str = Field(..., min_length=2, max_length=120)
    business_name: str = Field(..., min_length=2, max_length=120)
    city: str = ""
    offer: str = ""
    cta: str = ""
    niche_preset: str = "AUTO"
    reference_url: Optional[str] = None
    analyze_video_count: int = Field(default=1, ge=0, le=3)
    use_synapsa: bool = True
    force_refresh: bool = False


class PreviewMockupRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)


class CommercialRenderRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    clip_paths: List[str] = Field(..., min_length=1)
    output_name: Optional[str] = None
    music_path: Optional[str] = None


@router.post("/research/niche")
def run_niche_research(req: NicheResearchRequest, payload: dict = Depends(verify_token_flexible)):
    """Analizuje niszę na YT Shorts, uruchamia adaptację Synapsy + anty-plagiat i generuje blueprint + HTML pitch."""
    try:
        from ...niche_research_engine import build_niche_research_blueprint, generate_client_pitch_html

        bp = build_niche_research_blueprint(
            niche_query=req.niche_query,
            business_name=req.business_name,
            city=req.city,
            offer=req.offer,
            cta=req.cta,
            niche_preset=req.niche_preset,
            reference_url=req.reference_url,
            analyze_video_count=req.analyze_video_count,
            use_synapsa=req.use_synapsa,
            force_refresh=req.force_refresh,
        )
        pitch_html = generate_client_pitch_html(bp)
        bp["pitch_html_filename"] = pitch_html.name
        bp["pitch_html_url"] = f"/research/media/{pitch_html.name}"
        return {"ok": True, "blueprint": bp}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd researchu niszy: {e}")


@router.get("/research/niches")
def list_researches(payload: dict = Depends(verify_token_flexible)):
    """Zwraca listę zapisanych blueprintów badawczych dla klientów DFY."""
    try:
        from ...niche_research_engine import list_niche_blueprints

        items = list_niche_blueprints()
        return {"ok": True, "items": items, "total": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu listy researchów: {e}")


@router.get("/research/niche/{slug}")
def get_research_detail(slug: str, payload: dict = Depends(verify_token_flexible)):
    """Zwraca szczegóły zapisanego blueprintu dla danego sluga."""
    try:
        from ...niche_research_engine import load_niche_blueprint

        bp = load_niche_blueprint(slug)
        if bp.get("preview_video_filename"):
            bp["preview_video_url"] = f"/research/media/{bp['preview_video_filename']}"
        if bp.get("pitch_html_filename"):
            bp["pitch_html_url"] = f"/research/media/{bp['pitch_html_filename']}"
        return {"ok": True, "blueprint": bp}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd ładowania blueprintu: {e}")


@router.post("/research/preview-mockup")
def create_pitch_preview_mockup(req: PreviewMockupRequest, payload: dict = Depends(verify_token_flexible)):
    """Renderuje odtwarzalne wideo pitch 9:16 (MP4) dla klienta zgodnie ze storyboardem z researchu YT."""
    try:
        from ...commercial_montage import render_commercial_pitch_mockup
        from ...niche_research_engine import (
            NICHE_RESEARCH_DIR,
            generate_client_pitch_html,
            load_niche_blueprint,
            slugify_niche,
        )

        safe_slug = slugify_niche(req.slug)
        bp = load_niche_blueprint(safe_slug)
        out_mp4 = NICHE_RESEARCH_DIR / f"{safe_slug}_pitch_preview.mp4"
        render_res = render_commercial_pitch_mockup(bp, out_mp4)
        pitch_html = generate_client_pitch_html(bp, preview_video_filename=out_mp4.name)

        return {
            "ok": True,
            "slug": safe_slug,
            "preview_video_filename": out_mp4.name,
            "preview_video_url": f"/research/media/{out_mp4.name}",
            "thumbnail_filename": render_res.get("thumbnail_filename"),
            "pitch_html_filename": pitch_html.name,
            "pitch_html_url": f"/research/media/{pitch_html.name}",
            "render": render_res,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd generowania podglądu wideo: {e}")


@router.get("/research/media/{filename}")
def serve_research_media(filename: str, payload: dict = Depends(verify_token_flexible)):
    """Bezpiecznie serwuje pliki .mp4 / .jpg / .html z katalogu niche_research."""
    from ...niche_research_engine import NICHE_RESEARCH_DIR

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")

    base_dir = NICHE_RESEARCH_DIR.resolve()
    target = (base_dir / filename).resolve()
    if not target.is_relative_to(base_dir) or not target.is_file():
        raise HTTPException(status_code=404, detail="Plik nie istnieje")

    ext = target.suffix.lower()
    media_type = (
        "video/mp4"
        if ext == ".mp4"
        else "image/jpeg"
        if ext in (".jpg", ".jpeg")
        else "text/html; charset=utf-8"
        if ext == ".html"
        else "application/octet-stream"
    )
    return FileResponse(target, media_type=media_type)


@router.post("/commercial/render")
def render_client_commercial_reel(req: CommercialRenderRequest, payload: dict = Depends(verify_token_flexible)):
    """Składa gotową rolkę 9:16 z dostarczonych nagrań klienta według researchu niszy."""
    try:
        from ...commercial_montage import render_commercial_multishot
        from ...niche_research_engine import NICHE_RESEARCH_DIR, load_niche_blueprint, slugify_niche

        safe_slug = slugify_niche(req.slug)
        bp = load_niche_blueprint(safe_slug)
        out_stem = slugify_niche(req.output_name or f"{safe_slug}_client_reel")
        out_mp4 = NICHE_RESEARCH_DIR / f"{out_stem}.mp4"
        clips = [Path(p) for p in req.clip_paths]
        music = Path(req.music_path) if req.music_path else None
        res = render_commercial_multishot(clips, bp, out_mp4, music_path=music)
        return {
            "ok": True,
            "slug": safe_slug,
            "output_filename": out_mp4.name,
            "output_url": f"/research/media/{out_mp4.name}",
            "render": res,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd renderowania rolki klienta: {e}")
