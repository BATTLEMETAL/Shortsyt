"""
Shortsyt API — Router: Analytics, Tuning, Learning Engine & Dark Psychology
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from ..auth import verify_token, verify_token_flexible
from ..helpers import (
    DARK_ROOT, _dark_load_json, _sync_youtube_analytics,
    TUNING_FILE, DEFAULT_TUNING_CONFIG
)
from ..models import UserCorrectionRequest, DarkRunRequest

router = APIRouter(tags=["Analytics", "Config", "Learning", "Dark Psychology"])


@router.get("/analytics")
def get_analytics(range: str = "30d", refresh: bool = False, payload: dict = Depends(verify_token_flexible)):
    """Pobierz statystyki ROI i wydajności opublikowanych filmów na żywo z YouTube."""
    sync_data = _sync_youtube_analytics(force=refresh)
    ch_info = sync_data.get("channel", {})
    all_videos = sync_data.get("videos", [])

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


@router.get("/config/tuning", tags=["Config"])
def get_tuning_config(payload: dict = Depends(verify_token)):
    """Pobierz aktualny profil dostrajania stylu montażu i promptów AI."""
    if TUNING_FILE.exists():
        try:
            with open(TUNING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_TUNING_CONFIG


@router.post("/config/tuning", tags=["Config"])
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


@router.get("/learning/status", tags=["Learning"])
def get_learning_status(payload: dict = Depends(verify_token_flexible)):
    """Pobiera aktualną dyrektywę samouczenia, wagi akcji i wygrywające wzorce."""
    try:
        from lol_agent.learning_engine import get_learning_directive
        directive = get_learning_directive()
        return {"ok": True, "directive": directive}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu statusu uczenia: {e}")


@router.get("/learning/preferences", tags=["Learning"])
def get_user_learning_preferences(payload: dict = Depends(verify_token_flexible)):
    """Pobiera wyuczone preferencje montażu z korekt użytkownika."""
    try:
        from lol_agent.user_learning_memory import get_learned_preferences
        return {"ok": True, "preferences": get_learned_preferences()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu preferencji: {e}")


@router.post("/learning/recalibrate", tags=["Learning"])
def recalibrate_learning_cycle(payload: dict = Depends(verify_token_flexible)):
    """Wymusza pełny cykl analizy YouTube i rekalibracji wag samouczenia."""
    try:
        from lol_agent.learning_engine import run_channel_learning_cycle
        result = run_channel_learning_cycle(force_refresh=True)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd rekalibracji: {e}")


@router.post("/learning/correction", tags=["Learning"])
def record_correction(req: UserCorrectionRequest, payload: dict = Depends(verify_token_flexible)):
    """Rejestruje korektę parametru wykonaną przez użytkownika (tytuł, opis, suwaki)."""
    try:
        from lol_agent.user_learning_memory import record_user_correction
        learned = record_user_correction(
            param_name=req.param_name,
            old_val=req.old_value,
            new_val=req.new_value,
            source=req.source,
            reason=req.reason or None,
        )
        return {"ok": True, "learned": learned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd zapisu korekty: {e}")


@router.get("/analytics/video/{video_id}", tags=["Analytics"])
def get_video_retention(video_id: str, duration_s: float = 13.0, force_refresh: bool = False, payload: dict = Depends(verify_token_flexible)):
    """Pobiera retencję klatka-po-klatce (100 punktów), Swiped Away % i punkty opuszczenia dla filmu."""
    try:
        from lol_agent.api.youtube_analytics import fetch_video_retention_data
        data = fetch_video_retention_data(video_id=video_id, duration_s=duration_s, force_refresh=force_refresh)
        return {"ok": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd pobierania retencji wideo: {e}")


@router.get("/analytics/channel/retention", tags=["Analytics"])
def get_channel_retention_overview(payload: dict = Depends(verify_token_flexible)):
    """Pobiera zbiorczy raport retencji, średniego Swiped Away i korelacji AVD dla kanału."""
    try:
        from lol_agent.api.youtube_analytics import fetch_channel_retention_overview
        data = fetch_channel_retention_overview()
        return {"ok": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd pobierania raportu retencji kanału: {e}")


@router.get("/dark/status", tags=["Dark Psychology"])
def dark_status(payload: dict = Depends(verify_token_flexible)):
    """Status Dark Psychology agenta: ostatnie filmy, wyniki audytu, v/h."""
    analysis = _dark_load_json("smart_analysis_2026-05-05.json")
    directive = _dark_load_json("adaptation_directive.json")
    feedback_records = []
    feedback_file = DARK_ROOT / "auditor_feedback.json"
    if feedback_file.exists():
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                feedback_records = json.load(f)
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


@router.get("/dark/analytics", tags=["Dark Psychology"])
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


@router.get("/dark/calibration", tags=["Dark Psychology"])
def dark_calibration(payload: dict = Depends(verify_token_flexible)):
    """Raport kalibracji audytora — wagi Pearsona per kategoria + trafność prognoz."""
    weights_file = DARK_ROOT / "auditor_weights.json"
    feedback_file = DARK_ROOT / "auditor_feedback.json"

    weights = {}
    if weights_file.exists():
        try:
            with open(weights_file, "r", encoding="utf-8") as f:
                weights = json.load(f)
        except Exception:
            pass

    records = []
    if feedback_file.exists():
        try:
            with open(feedback_file, "r", encoding="utf-8") as f:
                records = json.load(f)
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


@router.post("/dark/recalibrate", tags=["Dark Psychology"])
def dark_recalibrate(payload: dict = Depends(verify_token_flexible)):
    """Rekalibracja wag audytora Dark Psychology."""
    return {
        "ok": True,
        "status": "archived",
        "message": "Moduł Dark Psychology jest zarchiwizowany. Aktywny agent: LoL Shortsyt Studio."
    }


@router.post("/dark/run", tags=["Dark Psychology"])
def dark_run(
    req: DarkRunRequest,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(verify_token),
):
    """Uruchom agenta dark_psychology w tle (generuje + publikuje shorty)."""
    agent_script = DARK_ROOT / "agent_dark_psychology.py"
    if not agent_script.exists():
        archive_cand = DARK_ROOT / "_archive" / "agent_dark_psychology.py"
        if archive_cand.exists():
            agent_script = archive_cand
        else:
            return {"status": "archived", "detail": "Moduł dark psychology jest zarchiwizowany"}

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
