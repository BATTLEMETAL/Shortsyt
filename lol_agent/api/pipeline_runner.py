"""
Shortsyt API — async wrapper dla render_short()
Uruchamia pipeline w osobnym wątku, żeby nie blokować FastAPI.
"""
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple

# Dodaj lol_agent do path
sys.path.insert(0, str(Path(__file__).parent.parent))


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class PipelineState:
    status: PipelineStatus = PipelineStatus.IDLE
    progress: int = 0          # 0-100%
    current_step: str = ""
    output_path: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    logs: List[str] = field(default_factory=list)


# Globalny stan pipeline — singleton
_state = PipelineState()
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


def get_state() -> dict:
    """Zwróć aktualny stan pipeline jako dict."""
    with _lock:
        return {
            "status": _state.status.value,
            "progress": _state.progress,
            "current_step": _state.current_step,
            "output_path": _state.output_path,
            "error": _state.error,
            "started_at": _state.started_at,
            "finished_at": _state.finished_at,
            "logs": _state.logs[-50:],  # ostatnie 50 linii
        }


def _update(step: str, progress: int, log: Optional[str] = None):
    """Zaktualizuj stan w wątku pipeline."""
    with _lock:
        _state.current_step = step
        _state.progress = progress
        if log:
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log}")


def _run_pipeline(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str,
    champion_name: str,
    rank: str,
    peak_moment: float,
    hook_text: str,
    output_filename: str,
    use_speed_ramp: bool,
    use_zoom_punch: bool,
    use_smart_camera: bool,
    notify_token: Optional[str],
):
    """Główna funkcja pipeline — uruchamiana w osobnym wątku."""
    global _state

    try:
        with _lock:
            _state.status = PipelineStatus.RUNNING
            _state.progress = 0
            _state.started_at = datetime.now().isoformat()
            _state.output_path = None
            _state.error = None
            _state.logs = []

        _update("Wykrywanie kill eventów", 5, f"Source: {source_path}")

        # Import tutaj żeby uniknąć circular import
        from smart_camera import detect_kill_events
        from lol_editor import render_short

        # Krok 1 — detekcja kill eventów
        try:
            peaks = detect_kill_events(
                source_path, clip_start, clip_end,
                clip_duration=clip_end - clip_start
            )
            _update("Kill detection gotowa", 15, f"Kill peaks: {peaks}")
        except Exception as e:
            _update("Kill detection pominięta", 15, f"Błąd detekcji: {e}")
            peaks = []

        # Krok 2 — render
        _update("Renderowanie klipu", 20, "Uruchamiam render_short...")

        output = render_short(
            source_path=source_path,
            clip_start=clip_start,
            clip_end=clip_end,
            action_type=action_type,
            champion_name=champion_name,
            rank=rank,
            use_speed_ramp=use_speed_ramp,
            use_zoom_punch=use_zoom_punch,
            use_smart_camera=use_smart_camera,
            peak_moment=peak_moment,
            hook_text=hook_text,
            peaks=peaks,
            output_filename=output_filename,
        )

        with _lock:
            _state.status = PipelineStatus.DONE
            _state.progress = 100
            _state.current_step = "Gotowe"
            _state.output_path = str(output)
            _state.finished_at = datetime.now().isoformat()
            _state.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Output: {output}")

        # Wyślij push notyfikację
        if notify_token:
            _send_push(notify_token, "✅ Short gotowy!", f"{output_filename} wyrenderowany")

    except Exception as e:
        err = traceback.format_exc()
        with _lock:
            _state.status = PipelineStatus.ERROR
            _state.error = str(e)
            _state.finished_at = datetime.now().isoformat()
            _state.logs.append(f"[ERROR] {err}")

        if notify_token:
            _send_push(notify_token, "❌ Błąd renderowania", str(e))


def _send_push(expo_token: str, title: str, body: str):
    """Wyślij push notyfikację przez Expo."""
    try:
        import httpx
        httpx.post(
            "https://exp.host/--/api/v2/push/send",
            json={
                "to": expo_token,
                "title": title,
                "body": body,
                "sound": "default",
            },
            timeout=10,
        )
    except Exception:
        pass  # Push jest opcjonalny — nie przerywaj jeśli się nie uda


def start_pipeline(
    source_path: str,
    clip_start: float,
    clip_end: float,
    action_type: str = "pentakill",
    champion_name: str = "Katarina",
    rank: str = "Gold",
    peak_moment: float = 17.0,
    hook_text: str = "PENTAKILL",
    output_filename: str = "short_output.mp4",
    use_speed_ramp: bool = True,
    use_zoom_punch: bool = True,
    use_smart_camera: bool = True,
    notify_token: Optional[str] = None,
) -> bool:
    """Uruchom pipeline w osobnym wątku. Zwraca False jeśli już działa."""
    global _thread

    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            return False

    _thread = threading.Thread(
        target=_run_pipeline,
        kwargs=dict(
            source_path=source_path,
            clip_start=clip_start,
            clip_end=clip_end,
            action_type=action_type,
            champion_name=champion_name,
            rank=rank,
            peak_moment=peak_moment,
            hook_text=hook_text,
            output_filename=output_filename,
            use_speed_ramp=use_speed_ramp,
            use_zoom_punch=use_zoom_punch,
            use_smart_camera=use_smart_camera,
            notify_token=notify_token,
        ),
        daemon=True,
    )
    _thread.start()
    return True


def stop_pipeline():
    """Zatrzymaj pipeline (soft stop — czeka na koniec bieżącego ffmpeg)."""
    with _lock:
        if _state.status == PipelineStatus.RUNNING:
            _state.status = PipelineStatus.ERROR
            _state.error = "Zatrzymano przez użytkownika"
            _state.finished_at = datetime.now().isoformat()
