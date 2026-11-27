"""
Shortsyt API — Router: System Hardware, Benchmarks, Health & Screen Recorder
"""
import atexit
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
import threading
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import verify_token_flexible
from ..helpers import DARK_ROOT, _dark_load_json
from ..models import ScreenRecordRequest
from ..config import LOL_TEMP_DIR, ACCOUNTS_DIR, API_PORT

router = APIRouter(tags=["System"])
LOL_AGENT_DIR = Path(__file__).resolve().parent.parent.parent

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


def _safe_token_probe(fn, valid_key: str = "valid") -> dict:
    try:
        res = fn() or {}
        return {**res, "valid": bool(res.get(valid_key))}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


@router.get("/system/reliability")
def get_system_reliability(payload: dict = Depends(verify_token_flexible)):
    """Kompleksowy watchdog zdrowia systemu 24/7 (tokeny, kolejka, dysk, lol_temp, VRAM)."""
    from datetime import datetime, timezone

    from ..youtube_uploader import get_token_status as get_yt_token_status
    from ..youtube_analytics import get_bulk_analytics_health
    try:
        from lol_agent.tiktok_publisher import get_tiktok_token_status
        from lol_agent.instagram_publisher import get_instagram_token_status
        from lol_agent.facebook_publisher import get_facebook_token_status
        from lol_agent.temp_cleaner import get_temp_dir_stats
        from lol_agent.scheduled_queue import summarize_queue_statuses, count_recent_tiktok_inbox
    except ImportError:
        from tiktok_publisher import get_tiktok_token_status  # type: ignore
        from instagram_publisher import get_instagram_token_status  # type: ignore
        from facebook_publisher import get_facebook_token_status  # type: ignore
        from temp_cleaner import get_temp_dir_stats  # type: ignore
        from scheduled_queue import summarize_queue_statuses, count_recent_tiktok_inbox  # type: ignore

    from concurrent.futures import ThreadPoolExecutor

    probe_specs = {
        "youtube": (get_yt_token_status, "is_valid"),
        "tiktok": (get_tiktok_token_status, "valid"),
        "instagram": (get_instagram_token_status, "valid"),
        "facebook": (get_facebook_token_status, "valid"),
    }
    tokens = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            name: pool.submit(_safe_token_probe, fn, valid_key)
            for name, (fn, valid_key) in probe_specs.items()
        }
        for name, fut in futures.items():
            tokens[name] = fut.result()

    queue_summary = {
        "total": 0,
        "pending": 0,
        "processing": 0,
        "published": 0,
        "published_to_inbox": 0,
        "failed": 0,
        "due_now": 0,
    }
    tiktok_inbox_recent_14d = 0
    queue_file = ACCOUNTS_DIR / "scheduled_social_queue.json"
    if queue_file.exists():
        try:
            items = json.loads(queue_file.read_text(encoding="utf-8"))
            if isinstance(items, list):
                now_utc = datetime.now(timezone.utc)
                queue_summary.update(summarize_queue_statuses(items))
                tiktok_inbox_recent_14d = count_recent_tiktok_inbox(items, days=14)
                for it in items:
                    st = str(it.get("status") or "pending")
                    if st == "pending" and it.get("publish_at"):
                        try:
                            pub_dt = datetime.fromisoformat(str(it["publish_at"]).replace("Z", "+00:00"))
                            if pub_dt.tzinfo is None:
                                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                            if now_utc >= pub_dt:
                                queue_summary["due_now"] += 1
                        except Exception:
                            pass
        except Exception as exc:
            print(f"[System] [WARN] Błąd odczytu kolejki ({queue_file}): {exc}")

    usage = shutil.disk_usage(DARK_ROOT if DARK_ROOT.exists() else Path("."))
    free_gb = round(usage.free / (1024 ** 3), 2)
    total_gb = round(usage.total / (1024 ** 3), 2)
    temp_stats = get_temp_dir_stats(LOL_TEMP_DIR)

    gpu_info = {"cuda_available": False, "free_vram_mb": None, "total_vram_mb": None}
    try:
        import torch
        if torch.cuda.is_available():
            free_b, total_b = torch.cuda.mem_get_info()
            gpu_info = {
                "cuda_available": True,
                "device_name": torch.cuda.get_device_name(0),
                "free_vram_mb": round(free_b / (1024 * 1024), 1),
                "total_vram_mb": round(total_b / (1024 * 1024), 1),
            }
    except Exception:
        pass
    if not gpu_info["cuda_available"]:
        try:
            smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.free,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if smi.returncode == 0 and smi.stdout.strip():
                parts = [p.strip() for p in smi.stdout.strip().splitlines()[0].split(",")]
                if len(parts) >= 3:
                    gpu_info = {
                        "cuda_available": True,
                        "device_name": parts[0],
                        "free_vram_mb": float(parts[1]),
                        "total_vram_mb": float(parts[2]),
                    }
        except Exception as exc:
            print(f"[System] [WARN] Błąd sondowania nvidia-smi: {exc}")

    try:
        bulk_health = get_bulk_analytics_health()
    except Exception as exc:
        bulk_health = {"last_error": str(exc)}

    yt_cache_path = LOL_AGENT_DIR / "yt_perf_cache.json"
    yt_integrity: Dict[str, Any] = {
        "exists": yt_cache_path.is_file(),
        "total_videos": 0,
        "videos_with_avp": 0,
        "videos_with_evr": 0,
        "avp_coverage_pct": 0.0,
        "evr_coverage_pct": 0.0,
        "synced_at": None,
        "ok": True,
    }
    if yt_cache_path.is_file():
        try:
            yc = json.loads(yt_cache_path.read_text(encoding="utf-8"))
            yvids = yc.get("videos") if isinstance(yc, dict) else []
            if isinstance(yvids, list):
                tot_v = len(yvids)
                with_avp = sum(1 for v in yvids if isinstance(v, dict) and v.get("avg_view_pct") is not None)
                with_evr = sum(1 for v in yvids if isinstance(v, dict) and v.get("engaged_view_rate_pct") is not None)
                avp_cov = round((with_avp / tot_v) * 100.0, 1) if tot_v > 0 else 0.0
                evr_cov = round((with_evr / tot_v) * 100.0, 1) if tot_v > 0 else 0.0
                yt_ok = not (tot_v >= 20 and (with_avp == 0 or with_evr == 0 or avp_cov < 30.0))
                yt_integrity.update({
                    "total_videos": tot_v,
                    "videos_with_avp": with_avp,
                    "videos_with_evr": with_evr,
                    "avp_coverage_pct": avp_cov,
                    "evr_coverage_pct": evr_cov,
                    "synced_at": yc.get("synced_at") if isinstance(yc, dict) else None,
                    "ok": yt_ok,
                })
        except Exception as exc:
            yt_integrity["ok"] = False
            yt_integrity["error"] = str(exc)

    ld_path = LOL_AGENT_DIR / "learning_directive.json"
    ld_integrity: Dict[str, Any] = {
        "exists": ld_path.is_file(),
        "timestamp": None,
        "monthly_2026_with_evr": 0,
        "monthly_2026_total": 0,
        "retrain_ready": False,
        "new_examples_since_train": 0,
        "ok": True,
    }
    if ld_path.is_file():
        try:
            ld_obj = json.loads(ld_path.read_text(encoding="utf-8"))
            if isinstance(ld_obj, dict):
                m26 = ((ld_obj.get("learning_progression") or {}).get("monthly_2026") or {})
                m_tot = len(m26) if isinstance(m26, dict) else 0
                m_evr = sum(
                    1 for row in (m26.values() if isinstance(m26, dict) else [])
                    if isinstance(row, dict) and row.get("median_engaged_rate_pct") is not None
                )
                ret_st = ld_obj.get("synapsa_retrain_status") or {}
                ld_ok = not (m_tot > 0 and m_evr == 0)
                ld_integrity.update({
                    "timestamp": ld_obj.get("timestamp"),
                    "monthly_2026_with_evr": m_evr,
                    "monthly_2026_total": m_tot,
                    "retrain_ready": bool(ret_st.get("retrain_ready")),
                    "new_examples_since_train": int(ret_st.get("new_examples_since_train") or 0),
                    "ok": ld_ok,
                })
        except Exception as exc:
            ld_integrity["ok"] = False
            ld_integrity["error"] = str(exc)

    warnings = []
    data_integrity_degraded = False
    for plat, tinfo in tokens.items():
        if not tinfo.get("valid"):
            warnings.append(f"Token {plat} nieważny lub brak połączenia")
    if free_gb < 15.0:
        warnings.append(f"Mało miejsca na dysku: {free_gb} GB (< 15 GB)")
    if temp_stats.get("size_mb", 0.0) > 4096.0:
        warnings.append(f"lol_temp przekracza 4 GB ({temp_stats['size_mb']} MB)")
    if queue_summary["due_now"] > 0:
        warnings.append(f"{queue_summary['due_now']} zaległych pozycji oczekuje na publikację")

    if not yt_integrity["ok"]:
        data_integrity_degraded = True
        warnings.append(
            f"yt_perf_cache.json ma puste metryki YouTube Analytics "
            f"(AVP: {yt_integrity['videos_with_avp']}/{yt_integrity['total_videos']}, "
            f"EVR: {yt_integrity['videos_with_evr']}/{yt_integrity['total_videos']}) — silnik uczenia nie ma danych retencji!"
        )
    if bulk_health.get("last_error"):
        data_integrity_degraded = True
        warnings.append(f"Ostatnie zapytanie YouTube Analytics API zgłosiło błąd: {bulk_health['last_error']}")
    if not ld_integrity["ok"]:
        data_integrity_degraded = True
        warnings.append("learning_directive.json nie zawiera żadnych wartości EVR dla miesięcy 2026")
    if tiktok_inbox_recent_14d > 0:
        warnings.append(
            f"TikTok: {tiktok_inbox_recent_14d} filmów z ostatnich 14 dni trafiło do INBOX "
            "(szkice na telefonie — wymagają ręcznej publikacji lub App Review video.publish)"
        )

    all_tokens_ok = all(bool(t.get("valid")) for t in tokens.values())
    overall_status = "healthy" if (all_tokens_ok and free_gb >= 15.0 and not data_integrity_degraded) else "degraded"

    return {
        "status": overall_status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tokens": tokens,
        "queue": queue_summary,
        "disk": {
            "free_gb": free_gb,
            "total_gb": total_gb,
            "temp_files": temp_stats["files"],
            "temp_size_mb": temp_stats["size_mb"],
            "low_space_warning": free_gb < 15.0,
        },
        "gpu": gpu_info,
        "data_integrity": {
            "yt_perf_cache": yt_integrity,
            "bulk_analytics": bulk_health,
            "learning_directive": ld_integrity,
            "tiktok_inbox_recent_14d": tiktok_inbox_recent_14d,
        },
        "warnings": warnings,
    }


@router.post("/system/cleanup-temp")
def run_temp_cleanup(
    max_age_days: int = 14,
    dry_run: bool = False,
    payload: dict = Depends(verify_token_flexible),
):
    """Uruchamia bezpieczną rotację katalogu tymczasowego lol_agent/lol_temp/."""
    try:
        from lol_agent.temp_cleaner import cleanup_temp_directory
    except ImportError:
        from temp_cleaner import cleanup_temp_directory  # type: ignore

    return cleanup_temp_directory(
        max_age_days=max(1, min(365, int(max_age_days))),
        dry_run=bool(dry_run),
        temp_dir=LOL_TEMP_DIR,
        queue_file=ACCOUNTS_DIR / "scheduled_social_queue.json",
    )


# ── Zdalne Sterowanie z Telefonu (LAN + Cloudflare Quick Tunnel) ─────────────

_CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
_TUNNEL_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
_tunnel_lock = threading.Lock()
_tunnel_state: dict = {
    "process": None,
    "url": None,
    "started_at": None,
    "error": None,
    "logs": [],
}


def _discover_lan_ipv4() -> list[str]:
    """Zwraca listę lokalnych adresów IPv4 (np. Wi-Fi LAN) z priorytetem sieci prywatnych."""
    candidates: list[str] = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            primary_ip = s.getsockname()[0]
            if primary_ip:
                candidates.append(primary_ip)
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip:
                candidates.append(ip)
    except Exception:
        pass

    try:
        import psutil
        for addrs in psutil.net_if_addrs().values():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address:
                    candidates.append(addr.address)
    except Exception:
        pass

    seen: set[str] = set()
    private_ips: list[str] = []
    other_ips: list[str] = []
    for raw in candidates:
        if raw in seen:
            continue
        seen.add(raw)
        try:
            ip_obj = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_unspecified:
            continue
        if ip_obj.is_private:
            private_ips.append(raw)
        else:
            other_ips.append(raw)
    return private_ips + other_ips


def _get_cloudflared_path() -> Optional[Path]:
    which = shutil.which("cloudflared")
    if which:
        return Path(which)
    local_bin = ACCOUNTS_DIR / "bin" / "cloudflared.exe"
    if local_bin.exists():
        return local_bin
    return None


def _ensure_cloudflared_binary() -> Path:
    existing = _get_cloudflared_path()
    if existing:
        return existing
    bin_dir = ACCOUNTS_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "cloudflared.exe"
    tmp_path = bin_dir / "cloudflared.exe.tmp"
    req = urllib.request.Request(
        _CLOUDFLARED_URL,
        headers={"User-Agent": "Shortsyt-RemoteControl/1.0"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp, open(tmp_path, "wb") as f:
        shutil.copyfileobj(resp, f)
    tmp_path.replace(target)
    return target


def _update_live_stats_remote_url(url: Optional[str]) -> None:
    targets = [
        DARK_ROOT / "docs" / "live_stats.json",
        Path.home() / "OneDrive" / "Pulpit" / "odpal" / "Shortsyt" / "live_stats.json",
    ]
    now_iso = datetime.now().isoformat()
    for path in targets:
        try:
            if not path.parent.exists():
                continue
            data = {}
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            if url:
                data["remote_control_url"] = url
            else:
                data.pop("remote_control_url", None)
            data["remote_tunnel_updated_at"] = now_iso
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:
            print(f"[System] [WARN] Błąd aktualizacji remote_control_url w {path}: {exc}")


def _stop_tunnel_locked() -> None:
    proc = _tunnel_state.get("process")
    if proc is not None:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as exc:
            print(f"[System] [WARN] Błąd zatrzymywania procesu tunelu: {exc}")
    _tunnel_state["process"] = None
    _tunnel_state["url"] = None
    _tunnel_state["started_at"] = None
    _update_live_stats_remote_url(None)


def _cleanup_tunnel_on_exit() -> None:
    with _tunnel_lock:
        _stop_tunnel_locked()


atexit.register(_cleanup_tunnel_on_exit)


def _build_remote_access_status() -> dict:
    lan_ips = _discover_lan_ipv4()
    lan_urls = [f"http://{ip}:{API_PORT}" for ip in lan_ips]
    with _tunnel_lock:
        proc = _tunnel_state.get("process")
        alive = proc is not None and proc.poll() is None
        if not alive and proc is not None:
            _tunnel_state["process"] = None
            _tunnel_state["url"] = None
        tunnel_url = _tunnel_state.get("url") if alive else None
        tunnel_started = _tunnel_state.get("started_at") if alive else None
        tunnel_error = _tunnel_state.get("error")
    return {
        "port": API_PORT,
        "lan_ips": lan_ips,
        "lan_urls": lan_urls,
        "primary_lan_url": lan_urls[0] if lan_urls else f"http://localhost:{API_PORT}",
        "tunnel_active": bool(alive and tunnel_url),
        "tunnel_url": tunnel_url,
        "tunnel_started_at": tunnel_started,
        "tunnel_error": tunnel_error,
        "cloudflared_available": _get_cloudflared_path() is not None,
    }


def _read_cloudflared_output(proc: subprocess.Popen) -> None:
    try:
        if proc.stdout is None:
            return
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            with _tunnel_lock:
                logs: list[str] = _tunnel_state.setdefault("logs", [])
                logs.append(line)
                if len(logs) > 40:
                    del logs[:-40]
                if _tunnel_state.get("process") is proc and not _tunnel_state.get("url"):
                    m = _TUNNEL_URL_RE.search(line)
                    if m:
                        url = m.group(0)
                        _tunnel_state["url"] = url
                        _tunnel_state["error"] = None
                        _update_live_stats_remote_url(url)
    except Exception:
        pass


@router.get("/system/remote-access")
def get_remote_access_status(user: dict = Depends(verify_token_flexible)):
    """Zwraca adresy LAN oraz status tunelu HTTPS do zdalnej obsługi z telefonu."""
    return _build_remote_access_status()


@router.post("/system/remote-access/tunnel/start")
def start_remote_access_tunnel(user: dict = Depends(verify_token_flexible)):
    """Uruchamia Cloudflare Quick Tunnel (trycloudflare.com) do obsługi poza domem (LTE/5G)."""
    with _tunnel_lock:
        proc = _tunnel_state.get("process")
        if proc is not None and proc.poll() is None and _tunnel_state.get("url"):
            return {"ok": True, **_build_remote_access_status()}
        _stop_tunnel_locked()
        _tunnel_state["error"] = None
        _tunnel_state["logs"] = []

    try:
        bin_path = _ensure_cloudflared_binary()
    except Exception as exc:
        with _tunnel_lock:
            _tunnel_state["error"] = f"Nie udało się pobrać cloudflared: {exc}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nie udało się pobrać cloudflared: {exc}",
        )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [
        str(bin_path),
        "tunnel",
        "--url",
        f"http://127.0.0.1:{API_PORT}",
        "--no-autoupdate",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except Exception as exc:
        with _tunnel_lock:
            _tunnel_state["error"] = f"Nie udało się uruchomić cloudflared: {exc}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nie udało się uruchomić cloudflared: {exc}",
        )

    with _tunnel_lock:
        _tunnel_state["process"] = proc
        _tunnel_state["started_at"] = datetime.now().isoformat()

    reader = threading.Thread(target=_read_cloudflared_output, args=(proc,), daemon=True)
    reader.start()

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        with _tunnel_lock:
            if _tunnel_state.get("url"):
                break
            if proc.poll() is not None:
                break
        time.sleep(0.25)

    with _tunnel_lock:
        url = _tunnel_state.get("url")
        if not url:
            tail = " | ".join(_tunnel_state.get("logs", [])[-5:])
            _stop_tunnel_locked()
            _tunnel_state["error"] = f"Tunel nie zwrócił adresu URL w ciągu 20s. {tail}".strip()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_tunnel_state["error"],
            )

    return {"ok": True, **_build_remote_access_status()}


@router.post("/system/remote-access/tunnel/stop")
def stop_remote_access_tunnel(user: dict = Depends(verify_token_flexible)):
    """Zatrzymuje aktywny tunel Cloudflare Quick Tunnel."""
    with _tunnel_lock:
        _stop_tunnel_locked()
        _tunnel_state["error"] = None
    return {"ok": True, **_build_remote_access_status()}

