"""
Shortsyt API — Router: Publication Calendar & Scheduling
"""
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from ..auth import verify_token_flexible
from ..models import ReserveSlotRequest, AutoFillCalendarRequest
from ..youtube_uploader import upload_video
from .clips import scan_available_clips

router = APIRouter(tags=["Calendar"])


@router.get("/calendar/slots")
def get_calendar(
    start_date: Optional[str] = None,
    days: int = 14,
    force_refresh: bool = False,
    payload: dict = Depends(verify_token_flexible)
):
    """Pobiera listę slotów publikacji na zadany okres (z uwzględnieniem Peak Hours CET)."""
    try:
        from .. import calendar_manager
        slots = calendar_manager.get_calendar_slots(start_date=start_date, days=days, force_refresh=force_refresh)
        return {"slots": slots, "days": days, "total": len(slots)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd kalendarza: {e}")


@router.post("/calendar/reserve")
def reserve_calendar_slot(req: ReserveSlotRequest, payload: dict = Depends(verify_token_flexible)):
    """Rezerwuje slot w kalendarzu dla konkretnego klipu lub wyrenderowanego filmu."""
    try:
        from .. import calendar_manager
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


@router.delete("/calendar/slot/{slot_id}")
def delete_calendar_slot(slot_id: str, payload: dict = Depends(verify_token_flexible)):
    """Zwalnia zarezerwowany slot."""
    try:
        from .. import calendar_manager
        success = calendar_manager.release_slot(slot_id)
        return {"status": "released" if success else "not_found", "slot_id": slot_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd zwalniania slotu: {e}")


@router.post("/calendar/slot/{slot_id}/publish")
def publish_calendar_slot(slot_id: str, payload: dict = Depends(verify_token_flexible)):
    """Publikuje / planuje wideo ze slotu bezpośrednio na YouTube na przypisaną godzinę."""
    try:
        from .. import calendar_manager
        db = calendar_manager._load_calendar_db()
        slot = db.get(slot_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Slot nie znaleziony w bazie rezerwacji")

        video_path = slot.get("output_video")
        if not video_path or not Path(video_path).exists():
            raise HTTPException(status_code=400, detail="Brak wyrenderowanego pliku wideo dla tego slotu")

        title = slot.get("title") or "League of Legends Highlight #Shorts"
        publish_at = slot.get("datetime_utc")

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


@router.post("/calendar/auto-fill")
def auto_fill_calendar(req: AutoFillCalendarRequest, payload: dict = Depends(verify_token_flexible)):
    """Automatycznie zapełnia najbliższe wolne sloty najlepszymi nieprzetworzonymi klipami."""
    try:
        from .. import calendar_manager
        clips = scan_available_clips(folder=None)
        assigned = calendar_manager.auto_fill_upcoming_slots(clips, max_slots=req.max_slots)
        return {"status": "ok", "assigned_count": len(assigned), "assigned": assigned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd auto-przypisywania: {e}")
