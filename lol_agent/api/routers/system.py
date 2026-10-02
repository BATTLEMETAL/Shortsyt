"""
Shortsyt API — Router: System Hardware, Benchmarks & Health
"""
from fastapi import APIRouter, Depends, HTTPException

from ..auth import verify_token_flexible
from ..helpers import DARK_ROOT, _dark_load_json

router = APIRouter(tags=["System"])


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
