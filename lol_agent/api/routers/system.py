"""
Shortsyt API — Router: System Hardware, Benchmarks, Health & Screen Recorder
"""
import os
from pathlib import Path
import threading
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import verify_token_flexible
from ..helpers import DARK_ROOT, _dark_load_json
from ..models import ScreenRecordRequest
from ..config import LOL_TEMP_DIR

router = APIRouter(tags=["System"])

# Globalny stan rejestratora ekranu
_recorder_thread: Optional[threading.Thread] = None
_recorder_stop_event: Optional[threading.Event] = None
_recorder_state = {
    "recording": False,
    "output_path": None,
    "started_at": None,
    "duration": None,
}
_rec_lock = threading.Lock()


@router.get("/system/hardware-info")
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


@router.post("/system/benchmark-scan")
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


@router.post("/system/record-screen/start")
def start_screen_recording(req: ScreenRecordRequest, payload: dict = Depends(verify_token_flexible)):
    """
    Uruchamia nagrywanie ekranu lub okna Shortsyt Studio do pliku MP4 (H.264).
    Działa w oparciu o przełączanie kontekstu wątku na pulpit Default (WinSta0).
    """
    global _recorder_thread, _recorder_stop_event, _recorder_state

    with _rec_lock:
        if _recorder_state["recording"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Nagrywanie ekranu jest już aktywne"
            )

        # Określ ścieżkę wyjściową
        out_filename = req.output_filename or f"shortsyt_demo_{int(datetime.now().timestamp())}.mp4"
        if not out_filename.endswith(".mp4"):
            out_filename += ".mp4"

        # Domyślnie zapisz w Videos/Captures (folder nagrań Windows) lub lol_temp
        captures_dir = Path.home() / "Videos" / "Captures"
        if not captures_dir.exists():
            captures_dir = LOL_TEMP_DIR
        captures_dir.mkdir(parents=True, exist_ok=True)
        out_path = captures_dir / out_filename

        _recorder_stop_event = threading.Event()
        _recorder_state = {
            "recording": True,
            "output_path": str(out_path.resolve()),
            "started_at": datetime.now().isoformat(),
            "duration": req.duration,
        }

        try:
            from scripts.screen_recorder import record_screen
        except ImportError:
            import sys
            root_dir = str(Path(__file__).parent.parent.parent)
            if root_dir not in sys.path:
                sys.path.insert(0, root_dir)
            from scripts.screen_recorder import record_screen

        def _worker():
            global _recorder_state
            try:
                record_screen(
                    output_path=str(out_path.resolve()),
                    duration=req.duration,
                    fps=req.fps,
                    window_title=req.window_title,
                    stop_event=_recorder_stop_event,
                )
            finally:
                with _rec_lock:
                    _recorder_state["recording"] = False

        _recorder_thread = threading.Thread(target=_worker, daemon=True)
        _recorder_thread.start()

        return {
            "status": "recording_started",
            "output_path": str(out_path.resolve()),
            "duration": req.duration,
            "fps": req.fps,
        }


@router.post("/system/record-screen/stop")
def stop_screen_recording(payload: dict = Depends(verify_token_flexible)):
    """Zatrzymuje aktywne nagrywanie ekranu i finalizuje plik MP4."""
    global _recorder_stop_event, _recorder_state

    with _rec_lock:
        if not _recorder_state["recording"] or not _recorder_stop_event:
            return {"status": "not_recording", "output_path": _recorder_state.get("output_path")}

        _recorder_stop_event.set()
        return {
            "status": "stopping",
            "output_path": _recorder_state.get("output_path"),
        }


@router.get("/system/record-screen/status")
def get_screen_recording_status(payload: dict = Depends(verify_token_flexible)):
    """Sprawdza aktualny stan nagrywania ekranu."""
    with _rec_lock:
        return dict(_recorder_state)


@router.get("/health/full")
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


@router.get("/health")
def health():
    """Healthcheck — nie wymaga autoryzacji."""
    return {"status": "ok", "service": "Shortsyt API"}
