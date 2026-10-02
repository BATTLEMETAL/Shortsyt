"""
Shortsyt API — Router: Pipeline Control & Status
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import verify_token
from ..models import PipelineStartRequest
from ..helpers import _save_meta, get_push_token
from .. import pipeline_runner

router = APIRouter(tags=["Pipeline"])


@router.get("/status")
@router.get("/pipeline/status")
def pipeline_status(payload: dict = Depends(verify_token)):
    """Aktualny status pipeline (idle / running / done / error)."""
    return pipeline_runner.get_state()


@router.post("/pipeline/start")
def start_pipeline(req: PipelineStartRequest, payload: dict = Depends(verify_token)):
    """Uruchom renderowanie klipu."""
    try:
        try:
            from lol_agent.run_lol_agent import check_duplicate_clip
        except ImportError:
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
        notify_token=req.expo_push_token or get_push_token(),
        game_type=req.game_type or "lol",
    )

    if not started:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline już działa — poczekaj na koniec lub zatrzymaj",
        )

    try:
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
        pass

    return {"status": "started", "output_filename": req.output_filename}


@router.post("/pipeline/stop")
def stop_pipeline(payload: dict = Depends(verify_token)):
    """Zatrzymaj pipeline."""
    pipeline_runner.stop_pipeline()
    return {"status": "stopped"}
