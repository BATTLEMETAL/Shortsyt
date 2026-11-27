"""
LOL Agent / Synapsa — Tryb Nocny („Opcja Nocna”: Skan -> Top 5 Montaży -> Rekomendacja)
========================================================================================
Skanuje wszystkie nieopublikowane klipy w folderze nagrań (Outplayed / Medal / custom),
bezwzględnie odrzuca przeciętne i puste klipy, wybiera 5 najbardziej hypowanych akcji,
montuje wszystkie 5 lokalnie pełnym pipeline'em (ZERO auto-uploadu), bada oglądalność
każdego gotowego shorta (`inspect_rendered_short` + `ffprobe`) i wyłania finalną
rekomendację Synapsy `#1` (`PICK_WINNER`) w trybie `Sykofankcja 0`.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

LOL_AGENT_DIR = Path(__file__).resolve().parent
OVERNIGHT_DIR = LOL_AGENT_DIR / "overnight_batches"
LATEST_BATCH_FILE = OVERNIGHT_DIR / "latest_batch.json"
DISMISSED_CLIPS_FILE = OVERNIGHT_DIR / "dismissed_clips.json"
PUBLISHED_VIDEOS_FILE = LOL_AGENT_DIR / "published_videos.jsonl"
SCAN_CACHE_FILE = LOL_AGENT_DIR / "overnight_scan_cache.json"
SCAN_CACHE_SCHEMA_VERSION = 7
MAX_UNACCEPTED_OVERNIGHT_RENDERS = 2

_DEFAULT_PROD_OVERNIGHT_DIR = LOL_AGENT_DIR / "overnight_batches"
_DEFAULT_PROD_DISMISSED_CLIPS = _DEFAULT_PROD_OVERNIGHT_DIR / "dismissed_clips.json"
_DEFAULT_PROD_PUBLISHED_FILE = LOL_AGENT_DIR / "published_videos.jsonl"

MONTAGE_PRESETS = ("compare_all_3", "auto_fallback", "arena_wide", "beat_velocity", "story_raw_pov")
VIRAL_STYLE_ORDER = ("ARENA_WIDE", "BEAT_VELOCITY", "STORY_RAW_POV")

TIER_FILTER_MIN_RANK: Dict[str, int] = {
    "auto": -1,
    "all": -1,
    "any_kill": 1,
    "double_plus": 2,
    "triple_plus": 3,
    "quadra_plus": 4,
}
_TIER_BY_RANK: Dict[int, str] = {
    0: "assist_only",
    1: "single_kill",
    2: "double",
    3: "triple",
    4: "quadrakill",
    5: "pentakill",
}
_BANNER_BY_RANK: Dict[int, str] = {
    1: "KILL",
    2: "DOUBLE KILL",
    3: "TRIPLE KILL",
    4: "QUADRA KILL",
    5: "PENTA KILL",
}

_OVERNIGHT_LOCK = threading.Lock()
_MANIFEST_LOCK = threading.Lock()
_OVERNIGHT_CANCEL = threading.Event()
_OVERNIGHT_THREAD: Optional[threading.Thread] = None

_OVERNIGHT_STATE: Dict[str, Any] = {
    "status": "idle",  # idle | scanning | rendering | evaluating | done | error | stopped
    "batch_id": None,
    "phase": "Oczekuje",
    "progress": 0,
    "total_clips": 0,
    "scanned_clips": 0,
    "skipped_published": 0,
    "qualified_count": 0,
    "rejected_count": 0,
    "selected_count": 0,
    "rendered_count": 0,
    "current_clip": "",
    "recommended_filename": None,
    "summary_pl": "",
    "error": None,
    "started_at": None,
    "finished_at": None,
    "logs": [],
}

_ACTION_BASE_HYPE: Dict[str, float] = {
    "pentakill": 86.0,
    "quadrakill": 78.0,
    "triple": 68.0,
    "double": 54.0,
    "clutch": 52.0,
    "solo_bolo": 38.0,
    "outplay": 34.0,
}

_VERDICT_CRITICAL_REASONS = (
    "black_end_frame",
    "frame0_hook_illegible",
    "audio_clipping_gt_10",
    "av_desync_gt_025s",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomowo zapisuje tekst UTF-8 przez plik tymczasowy w tym samym katalogu i os.replace."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _update_overnight_state(**kwargs: Any) -> None:
    log_line = kwargs.pop("log", None)
    with _OVERNIGHT_LOCK:
        _OVERNIGHT_STATE.update(kwargs)
        if log_line:
            ts = datetime.now().strftime("%H:%M:%S")
            _OVERNIGHT_STATE["logs"].append(f"[{ts}] {log_line}")
            _OVERNIGHT_STATE["logs"] = _OVERNIGHT_STATE["logs"][-60:]


def get_overnight_status() -> Dict[str, Any]:
    """Zwraca wątkowo-bezpieczną kopię aktualnego statusu trybu nocnego."""
    with _OVERNIGHT_LOCK:
        return {**_OVERNIGHT_STATE, "logs": list(_OVERNIGHT_STATE["logs"])}


def stop_overnight_batch() -> bool:
    """Przerywa trwającą sesję trybu nocnego (gdy aktywna) i zatrzymuje aktywny render FFmpeg."""
    with _OVERNIGHT_LOCK:
        if _OVERNIGHT_STATE.get("status") not in ("scanning", "rendering", "evaluating"):
            return False
        _OVERNIGHT_CANCEL.set()
        _OVERNIGHT_STATE["phase"] = "Zatrzymywanie..."
        ts = datetime.now().strftime("%H:%M:%S")
        _OVERNIGHT_STATE["logs"].append(f"[{ts}] Zażądano zatrzymania trybu nocnego.")
        _OVERNIGHT_STATE["logs"] = _OVERNIGHT_STATE["logs"][-60:]

    try:
        from lol_agent.api import pipeline_runner
    except ImportError:
        from api import pipeline_runner  # type: ignore
    try:
        pipeline_runner.stop_pipeline(clear_queue=True)
    except Exception:
        pass
    return True


_DEFAULT_PROD_SCAN_CACHE = LOL_AGENT_DIR / "overnight_scan_cache.json"


def _is_blocked_test_cache_write() -> bool:
    try:
        return bool(os.environ.get("PYTEST_CURRENT_TEST")) and SCAN_CACHE_FILE.resolve() == _DEFAULT_PROD_SCAN_CACHE.resolve()
    except Exception:
        return False


def _load_scan_cache() -> Dict[str, Any]:
    if _is_blocked_test_cache_write() or not SCAN_CACHE_FILE.is_file():
        return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}
    try:
        data = json.loads(SCAN_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema") == SCAN_CACHE_SCHEMA_VERSION:
            entries = data.get("entries")
            if isinstance(entries, dict):
                return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": entries}
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd odczytu SCAN_CACHE_FILE ({SCAN_CACHE_FILE}): {exc}")
    return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}


def _save_scan_cache(cache_data: Dict[str, Any]) -> None:
    if _is_blocked_test_cache_write():
        return
    try:
        entries = cache_data.get("entries") or {}
        if len(entries) > 600:
            # Zachowaj ostatnie 600 wpisów bez rozrastania JSON-a w nieskończoność
            trimmed = dict(list(entries.items())[-600:])
            cache_data = {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": trimmed}
        _atomic_write_text(SCAN_CACHE_FILE, json.dumps(cache_data, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd zapisu SCAN_CACHE_FILE ({SCAN_CACHE_FILE}): {exc}")


def _cache_key_for(path: str, size_bytes: int, mtime_sec: float) -> str:
    return f"{Path(path).resolve()}|{int(size_bytes)}|{int(mtime_sec)}|{SCAN_CACHE_SCHEMA_VERSION}"


def _is_blocked_test_path(path: Path, default_path: Path) -> bool:
    """Blokuje operacje na plikach produkcyjnych w trakcie pytest, dopóki test nie podmieniał ścieżki."""
    try:
        return bool(os.environ.get("PYTEST_CURRENT_TEST")) and Path(path).resolve() == Path(default_path).resolve()
    except Exception:
        return False


def _load_dismissed_clips_from(path: Path) -> Dict[str, Dict[str, Any]]:
    if _is_blocked_test_path(path, _DEFAULT_PROD_DISMISSED_CLIPS) or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            clips = raw.get("clips") if isinstance(raw.get("clips"), dict) else raw
            return {
                str(k).strip().lower(): dict(v)
                for k, v in clips.items()
                if str(k).strip() and isinstance(v, dict)
            }
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd odczytu DISMISSED_CLIPS_FILE ({path}): {exc}")
    return {}


def load_dismissed_clips() -> Dict[str, Dict[str, Any]]:
    """Zwraca mapę odrzuconych/wykluczonych powtórzeń nocnych indeksowaną po nazwie pliku (lower)."""
    return _load_dismissed_clips_from(Path(DISMISSED_CLIPS_FILE))


def load_dismissed_clip_keys() -> Set[str]:
    """Zwraca zbiór nazw plików (lower) trwale wykluczonych po niezaakceptowanych powtórzeniach."""
    return set(load_dismissed_clips().keys())


def _save_dismissed_clips(data: Dict[str, Dict[str, Any]], path: Optional[Path] = None) -> None:
    target = Path(path) if path is not None else Path(DISMISSED_CLIPS_FILE)
    if _is_blocked_test_path(target, _DEFAULT_PROD_DISMISSED_CLIPS):
        return
    try:
        payload = {
            "schema_version": 1,
            "updated_at": _now_iso(),
            "clips": {str(k).strip().lower(): v for k, v in sorted(data.items())},
        }
        _atomic_write_text(target, json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd zapisu DISMISSED_CLIPS_FILE ({target}): {exc}")


def _move_file_to_recycle_bin(path: Path) -> Tuple[bool, str]:
    """Przenosi plik do Kosza Windows (SHFileOperationW + FOF_ALLOWUNDO), bez trwałego kasowania fallbackiem."""
    p = Path(path)
    if not p.exists():
        return False, "missing"
    if sys.platform != "win32":
        return False, "non_windows"
    try:
        import ctypes
        from ctypes import wintypes

        class _SHFILEOPSTRUCTW(ctypes.Structure):
            if ctypes.sizeof(ctypes.c_void_p) == 4:
                _pack_ = 1
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", ctypes.POINTER(ctypes.c_wchar)),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        abs_path = str(p.resolve())
        pfrom_buf = ctypes.create_unicode_buffer(abs_path + "\0")
        op = _SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = 3  # FO_DELETE
        op.pFrom = pfrom_buf
        op.pTo = None
        op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None

        shell32 = ctypes.windll.shell32
        shell32.SHFileOperationW.argtypes = [ctypes.POINTER(_SHFILEOPSTRUCTW)]
        shell32.SHFileOperationW.restype = ctypes.c_int
        rc = int(shell32.SHFileOperationW(ctypes.byref(op)))
        if rc == 0 and not op.fAnyOperationsAborted and not p.exists():
            return True, "recycled"
        return False, f"shfileop_rc_{rc}_aborted_{bool(op.fAnyOperationsAborted)}"
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd przenoszenia do Kosza Windows ({p}): {exc}")
        return False, str(exc)


def _collect_overnight_render_history(overnight_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """
    Agreguje historię udanych (`render_ok=True`) montaży nocnych per plik źródłowy.
    Zlicza unikalne `batch_id`, więc 3 warianty `compare_all_3` w jednej paczce liczą się jako 1.
    """
    target_dir = Path(overnight_dir) if overnight_dir is not None else Path(OVERNIGHT_DIR)
    if _is_blocked_test_path(target_dir, _DEFAULT_PROD_OVERNIGHT_DIR) or not target_dir.is_dir():
        return {}

    history: Dict[str, Dict[str, Any]] = {}
    for batch_file in sorted(target_dir.glob("batch_*.json")):
        try:
            data = json.loads(batch_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[Overnight] [WARN] Błąd odczytu historii batcha ({batch_file}): {exc}")
            continue
        if not isinstance(data, dict):
            continue
        batch_id = str(data.get("batch_id") or batch_file.stem).strip()
        for it in (data.get("items") or []):
            if not isinstance(it, dict) or not it.get("render_ok"):
                continue
            src_name = str(it.get("source_filename") or "").strip()
            src_path = str(it.get("source_path") or "").strip()
            src_key = (src_name or (Path(src_path).name if src_path else "")).strip().lower()
            if not src_key:
                continue

            entry = history.setdefault(
                src_key,
                {
                    "source_filename": src_name or Path(src_path).name,
                    "batch_ids": set(),
                    "output_filenames": set(),
                    "output_paths": [],
                    "thumbnail_filenames": set(),
                    "thumbnail_paths": [],
                },
            )
            entry["batch_ids"].add(batch_id)

            def _record_art(obj: Dict[str, Any]) -> None:
                ofn = str(obj.get("output_filename") or "").strip()
                opth = str(obj.get("output_path") or "").strip()
                if ofn:
                    entry["output_filenames"].add(ofn.lower())
                elif opth:
                    entry["output_filenames"].add(Path(opth).name.lower())
                if opth and opth not in entry["output_paths"]:
                    entry["output_paths"].append(opth)

                tfn = str(obj.get("thumbnail_filename") or "").strip()
                tpth = str(obj.get("thumbnail_path") or "").strip()
                if tfn:
                    entry["thumbnail_filenames"].add(tfn.lower())
                elif tpth:
                    entry["thumbnail_filenames"].add(Path(tpth).name.lower())
                if tpth and tpth not in entry["thumbnail_paths"]:
                    entry["thumbnail_paths"].append(tpth)

            _record_art(it)
            for alt in (it.get("alternate_renders") or []):
                if isinstance(alt, dict):
                    _record_art(alt)
    return history


def _resolve_output_artifact_dirs() -> List[Path]:
    dirs: List[Path] = []
    try:
        try:
            from lol_agent.api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
        except ImportError:
            from api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR  # type: ignore
        dirs.extend([Path(LOL_TEMP_DIR), Path(LOL_OUTPUT_DIR)])
    except Exception as exc:
        print(f"[Overnight] [WARN] Brak ścieżek LOL_TEMP_DIR/LOL_OUTPUT_DIR: {exc}")
    dirs.append(LOL_AGENT_DIR / "lol_temp")
    unique: List[Path] = []
    seen: Set[str] = set()
    for d in dirs:
        k = str(d)
        if k not in seen:
            seen.add(k)
            unique.append(d)
    return unique


def _collect_accepted_clip_keys(
    published_file: Optional[Path] = None,
    queue_items: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Set[str], Set[str]]:
    """Zwraca `(accepted_sources_lower, accepted_outputs_lower)` z `published_videos.jsonl` oraz aktywnej kolejki."""
    accepted_sources: Set[str] = set()
    accepted_outputs: Set[str] = set()

    pub_path = Path(published_file) if published_file is not None else Path(PUBLISHED_VIDEOS_FILE)
    if not _is_blocked_test_path(pub_path, _DEFAULT_PROD_PUBLISHED_FILE) and pub_path.is_file():
        for line in pub_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception as exc:
                print(f"[Overnight] [WARN] Uszkodzony wiersz published_videos.jsonl: {exc}")
                continue
            if not isinstance(rec, dict):
                continue
            for key in ("source_path", "source_filename"):
                val = str(rec.get(key) or "").strip()
                if val:
                    accepted_sources.add(Path(val).name.lower())
            for key in ("video_path", "output_filename"):
                val = str(rec.get(key) or "").strip()
                if val:
                    accepted_outputs.add(Path(val).name.lower())

    q_list = queue_items
    if q_list is None:
        try:
            try:
                from lol_agent import scheduled_queue as _sq
            except ImportError:
                import scheduled_queue as _sq  # type: ignore
            default_q = LOL_AGENT_DIR.parent / "accounts" / "scheduled_social_queue.json"
            if not _is_blocked_test_path(Path(_sq.QUEUE_FILE), default_q):
                q_list = _sq._load_queue()
            else:
                q_list = []
        except Exception as exc:
            print(f"[Overnight] [WARN] Błąd odczytu kolejki przy ochronie zaakceptowanych klipów: {exc}")
            q_list = []

    out_dirs = _resolve_output_artifact_dirs()
    active_statuses = {"pending", "processing", "published", "published_to_inbox"}
    for q_it in (q_list or []):
        if not isinstance(q_it, dict) or str(q_it.get("status") or "") not in active_statuses:
            continue
        sp = str(q_it.get("source_path") or "").strip()
        if sp:
            accepted_sources.add(Path(sp).name.lower())
        vp = str(q_it.get("video_path") or "").strip()
        if vp:
            vp_path = Path(vp)
            accepted_outputs.add(vp_path.name.lower())
            meta_candidates = [
                vp_path.with_suffix(".meta.json"),
                Path(str(vp_path) + ".meta.json"),
            ]
            for d in out_dirs:
                meta_candidates.append(d / f"{vp_path.stem}.meta.json")
            for mp in meta_candidates:
                if mp.is_file():
                    try:
                        m = json.loads(mp.read_text(encoding="utf-8"))
                        if isinstance(m, dict):
                            for key in ("source_path", "source_filename"):
                                sval = str(m.get(key) or "").strip()
                                if sval:
                                    accepted_sources.add(Path(sval).name.lower())
                    except Exception as exc:
                        print(f"[Overnight] [WARN] Błąd odczytu meta dla kolejki ({mp}): {exc}")

    return accepted_sources, accepted_outputs


def _remove_unaccepted_rendered_artifacts(
    history_entry: Dict[str, Any],
    accepted_outputs: Set[str],
) -> List[str]:
    """Usuwa stare niezaakceptowane rendery `short_overnight_*.mp4`, ich `.meta.json` i nieużywane miniaturki."""
    removed: List[str] = []
    removed_set: Set[str] = set()
    accepted_stems = {Path(o).stem.lower() for o in accepted_outputs if o}
    search_dirs = _resolve_output_artifact_dirs()

    candidate_mp4s: List[Path] = []
    for op in (history_entry.get("output_paths") or []):
        if op:
            p = Path(op)
            candidate_mp4s.append(p)
            if p.parent not in search_dirs:
                search_dirs.append(p.parent)
    for ofn in (history_entry.get("output_filenames") or []):
        for d in search_dirs:
            candidate_mp4s.append(d / ofn)

    seen_files: Set[str] = set()
    for mp4_path in candidate_mp4s:
        try:
            key = str(mp4_path.resolve()).lower()
        except Exception:
            key = str(mp4_path).lower()
        if key in seen_files:
            continue
        seen_files.add(key)

        name_l = mp4_path.name.lower()
        if not name_l.startswith("short_overnight_") or name_l in accepted_outputs:
            continue
        if "viral_vault" in {part.lower() for part in mp4_path.parts}:
            continue
        for target in (
            mp4_path,
            mp4_path.with_suffix(".meta.json"),
            Path(str(mp4_path) + ".meta.json"),
        ):
            if target.is_file():
                try:
                    target.unlink()
                    label = target.name
                    if label not in removed_set:
                        removed_set.add(label)
                        removed.append(label)
                except Exception as exc:
                    print(f"[Overnight] [WARN] Nie udało się usunąć starego artefaktu ({target}): {exc}")

    thumb_dirs = _thumb_search_dirs() + search_dirs
    candidate_thumbs: List[Path] = [Path(tp) for tp in (history_entry.get("thumbnail_paths") or []) if tp]
    for tfn in (history_entry.get("thumbnail_filenames") or []):
        for td in thumb_dirs:
            candidate_thumbs.append(td / tfn)

    for tp in candidate_thumbs:
        stem_l = tp.stem.lower()
        if any(st and st in stem_l for st in accepted_stems):
            continue
        if "viral_vault" in {part.lower() for part in tp.parts}:
            continue
        if tp.is_file():
            try:
                tp.unlink()
                if tp.name not in removed_set:
                    removed_set.add(tp.name)
                    removed.append(tp.name)
            except Exception as exc:
                print(f"[Overnight] [WARN] Nie udało się usunąć miniaturki ({tp}): {exc}")

    return removed


def prune_unaccepted_repeat_clip(
    cl: Dict[str, Any],
    history_entry: Dict[str, Any],
    dismissed_map: Dict[str, Dict[str, Any]],
    accepted_outputs: Set[str],
) -> Dict[str, Any]:
    """
    Usuwa stare niezaakceptowane rendery klipu, przenosi plik źródłowy z Outplayed do Kosza Windows,
    dopisuje wpis do `dismissed_map` oraz rejestruje odrzucenie w `user_learning_memory`.
    """
    src_path_str = str(cl.get("path") or "").strip()
    src_name = str(cl.get("filename") or (Path(src_path_str).name if src_path_str else "")).strip()
    src_key = src_name.lower()

    removed_outputs = _remove_unaccepted_rendered_artifacts(history_entry, accepted_outputs)
    recycled, recycle_status = (
        _move_file_to_recycle_bin(Path(src_path_str)) if src_path_str else (False, "missing")
    )

    batch_ids_sorted = sorted(str(b) for b in (history_entry.get("batch_ids") or set()))
    entry = {
        "source_filename": src_name,
        "source_path": src_path_str,
        "batch_ids": batch_ids_sorted,
        "render_count": len(batch_ids_sorted),
        "dismissed_at": _now_iso(),
        "source_recycled": recycled,
        "recycle_status": recycle_status,
        "removed_outputs": removed_outputs,
        "is_favorite": bool(cl.get("is_favorite", False)),
        "reason": "unaccepted_repeat_2x",
    }
    if src_key:
        dismissed_map[src_key] = entry

    try:
        try:
            from lol_agent.user_learning_memory import record_render_rejected
        except ImportError:
            from user_learning_memory import record_render_rejected  # type: ignore
        record_render_rejected(
            src_name or src_key,
            reason=f"Auto-wykluczenie po {len(batch_ids_sorted)} niezaakceptowanych montażach nocnych ({', '.join(batch_ids_sorted)})",
            qa_details=["unaccepted_repeat_2x"],
        )
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd zapisu odrzucenia w user_learning_memory ({src_name}): {exc}")

    return entry


def find_unaccepted_repeat_candidates(
    folder: Optional[str] = None,
    max_unaccepted_renders: int = MAX_UNACCEPTED_OVERNIGHT_RENDERS,
    overnight_dir: Optional[Path] = None,
    published_file: Optional[Path] = None,
    dismissed_file: Optional[Path] = None,
    queue_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Funkcja read-only zwracająca klipy obecnie kwalifikujące się do auto-pruningu
    (>= `max_unaccepted_renders` udanych montaży w osobnych paczkach bez publikacji ani kolejki).
    """
    try:
        from lol_agent.api.routers.clips import scan_available_clips
    except ImportError:
        from api.routers.clips import scan_available_clips  # type: ignore

    all_clips = scan_available_clips(folder)
    history = _collect_overnight_render_history(overnight_dir)
    accepted_sources, accepted_outputs = _collect_accepted_clip_keys(published_file, queue_items)
    dismissed_map = _load_dismissed_clips_from(
        Path(dismissed_file) if dismissed_file is not None else Path(DISMISSED_CLIPS_FILE)
    )
    threshold = max(1, int(max_unaccepted_renders))
    candidates: List[Dict[str, Any]] = []
    for cl in all_clips:
        src_name = str(cl.get("filename") or Path(str(cl.get("path") or "")).name).strip()
        src_key = src_name.lower()
        hist = history.get(src_key)
        if not hist:
            continue
        is_accepted = (
            bool(cl.get("already_published"))
            or src_key in accepted_sources
            or any(o in accepted_outputs for o in hist.get("output_filenames", set()))
        )
        if is_accepted or src_key in dismissed_map:
            continue
        batch_ids = sorted(str(b) for b in hist.get("batch_ids", set()))
        if len(batch_ids) >= threshold:
            candidates.append({
                "source_filename": src_name,
                "source_path": str(cl.get("path") or ""),
                "is_favorite": bool(cl.get("is_favorite", False)),
                "batch_count": len(batch_ids),
                "batch_ids": batch_ids,
                "output_filenames": sorted(hist.get("output_filenames", set())),
            })
    return candidates


def _check_trailing_survival(video_path: str, clip_end: float, fps: float) -> bool:
    """
    Sprawdza w ostatnich 2.2s okna klipu czy gracz przeżył.
    Wspiera zarówno Standard Mode (zielony pasek HP), jak i Colorblind (złoty) + dolny HUD.
    """
    cap = None
    try:
        try:
            from lol_agent.autonomous.evaluator import _player_hp_mask
            from lol_agent.lol_frag_detector import _measure_player_hp
        except ImportError:
            from autonomous.evaluator import _player_hp_mask  # type: ignore
            from lol_frag_detector import _measure_player_hp  # type: ignore

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        v_fps = fps if fps > 0 else (cap.get(cv2.CAP_PROP_FPS) or 30.0)
        end_t = max(1.5, float(clip_end))
        start_t = max(0.0, end_t - 2.2)

        hp_px_counts: List[int] = []
        hud_hp_vals: List[float] = []
        saturations: List[float] = []

        for t in np.linspace(start_t, max(start_t + 0.1, end_t - 0.15), 5):
            f_idx = min(max(0, total_frames - 1), int(float(t) * v_fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            hp_px_counts.append(int(np.count_nonzero(_player_hp_mask(frame))))
            hud_hp = _measure_player_hp(frame)
            if hud_hp is not None:
                hud_hp_vals.append(float(hud_hp))
            h_f, w_f = frame.shape[:2]
            roi = frame[int(h_f * 0.2):int(h_f * 0.8), int(w_f * 0.2):int(w_f * 0.8)]
            if roi.size > 0:
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                saturations.append(float(np.mean(hsv[:, :, 1])))

        has_world_hp = bool(hp_px_counts) and max(hp_px_counts) >= 6
        has_hud_hp = bool(hud_hp_vals) and max(hud_hp_vals) >= 4.0
        tail_gray = len(saturations) >= 2 and all(s < 38.0 for s in saturations[-2:])
        if tail_gray:
            return True
        return not (has_world_hp or has_hud_hp)
    except Exception:
        return False
    finally:
        if cap is not None:
            cap.release()


def _normalize_action_type_in_window(
    raw_detected_frag_type: str,
    kills_in_win: List[Dict[str, Any]],
    is_clutch: bool,
) -> str:
    """Klasyfikuje akcję wyłącznie po banerach/zabójstwach mieszczących się w oknie shorta."""
    det = str(raw_detected_frag_type or "outplay").lower().strip()
    n_k = len(kills_in_win)
    max_tier = max([int(k.get("tier", 0) or 0) for k in kills_in_win], default=0)
    if max_tier >= 5:
        return "pentakill"
    if max_tier == 4:
        return "quadrakill"
    if max_tier == 3:
        return "triple"
    if max_tier == 2:
        return "double"
    if is_clutch and n_k >= 1:
        return "clutch"
    if det == "solo_bolo" or any(str(k.get("label") or "").upper() == "FIRST BLOOD" for k in kills_in_win):
        return "solo_bolo"
    return "outplay"


def _load_learning_directive_safe() -> Dict[str, Any]:
    """Bezpiecznie ładuje learning_directive.json z learning_engine."""
    try:
        try:
            from lol_agent.learning_engine import get_learning_directive
        except ImportError:
            from learning_engine import get_learning_directive
        data = get_learning_directive()
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"⚠️ [Overnight] Ostrzeżenie odczytu learning_directive.json: {exc}")
        return {}


def _get_recent_evr_safe(directive: Dict[str, Any]) -> Optional[float]:
    try:
        try:
            from lol_agent.lol_montage_director import _extract_recent_evr_pct
        except ImportError:
            from lol_montage_director import _extract_recent_evr_pct
        return _extract_recent_evr_pct(directive or {})
    except Exception:
        return None


def _score_and_classify_candidate(
    raw_entry: Dict[str, Any],
    directive: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Przelicza klasyfikację okienkową, filtrację i hype_score na surowym lub zcache'owanym wpisie."""
    entry = dict(raw_entry)
    if entry.get("rejection_code") in (
        "REJECT_UNREADABLE",
        "REJECT_LOW_TECH",
        "REJECT_ASSIST_ONLY",
        "REJECT_WRONG_CHAMPION",
        "REJECT_TIER_FILTER",
        "REJECT_SINGLE_KILL_MULTIKILLS_AVAILABLE",
    ):
        return entry

    clip_start = float(entry.get("clip_start") or 0.0)
    clip_end = float(entry.get("clip_end") or 0.0)
    window_dur = max(1.0, round(clip_end - clip_start, 2))
    raw_kills = list(entry.get("kills") or [])

    kills_in_win = [
        k for k in raw_kills
        if (clip_start - 0.6) <= float(k.get("timestamp", 0.0)) <= (clip_end + 0.6)
    ]
    kill_count_in_win = len(kills_in_win)
    ts_in_win = sorted(float(k.get("timestamp", 0.0)) for k in kills_in_win)
    kill_span_s = round(max(0.0, ts_in_win[-1] - ts_in_win[0]), 2) if len(ts_in_win) >= 2 else 0.0
    first_kill_offset_s = round(max(0.0, ts_in_win[0] - clip_start), 2) if ts_in_win else round(window_dur, 2)

    is_clutch = bool(entry.get("is_clutch_1hp"))
    raw_det = str(entry.get("raw_detected_frag_type") or entry.get("action_type") or "outplay").lower().strip()
    action_type = _normalize_action_type_in_window(raw_det, kills_in_win, is_clutch)

    event_source = str(entry.get("event_source") or "")
    outplayed_rank_raw = entry.get("event_tier_rank")
    outplayed_rank = int(outplayed_rank_raw) if isinstance(outplayed_rank_raw, (int, float)) else None
    is_outplayed = event_source.startswith("outplayed_")
    if is_outplayed and outplayed_rank is not None:
        if outplayed_rank >= 2:
            action_type = _TIER_BY_RANK.get(min(5, outplayed_rank), action_type)
            kill_count_in_win = max(kill_count_in_win, outplayed_rank)
        elif outplayed_rank == 1 and action_type in ("double", "triple", "quadrakill", "pentakill"):
            # Riot API widzi pojedynczego killa -> zapobiegaj halucynacji OCR multikilla
            action_type = "clutch" if is_clutch else "solo_bolo"
            kill_count_in_win = max(1, min(kill_count_in_win, 1))

    objective_secured = bool(entry.get("objective_secured"))
    min_hp = float(entry.get("min_hp_percentage") if entry.get("min_hp_percentage") is not None else 100.0)
    conf = float(entry.get("confidence") or 0.0)
    ally_blocked = bool(entry.get("ally_banner_blocked"))
    player_died = bool(entry.get("player_died"))
    raw_ok = bool(entry.get("raw_viable", True))
    raw_reason = str(entry.get("raw_reason") or "")
    raw_code = entry.get("raw_code")
    is_favorite = bool(entry.get("is_favorite"))
    total_kills_in_clip = int(entry.get("total_kills_in_clip") or 0)

    base_key = action_type if kill_count_in_win > 0 else "outplay"
    hype = _ACTION_BASE_HYPE.get(base_key, 34.0) if kill_count_in_win > 0 else 10.0
    if objective_secured:
        hype += 6.0 if kill_count_in_win >= 2 else 10.0
    if is_outplayed and (outplayed_rank or 0) >= 2:
        hype += 3.0
    if is_clutch or min_hp <= 20.0:
        hype += 9.0
    elif min_hp <= 35.0 and kill_count_in_win >= 1:
        hype += 4.0
    if is_favorite:
        hype += 14.0
    if total_kills_in_clip >= 4:
        hype += 4.0
    if kill_count_in_win >= 3 and kill_span_s <= 6.5:
        hype += 6.0
    elif kill_count_in_win == 2 and kill_span_s <= 3.0:
        hype += 5.0
    if conf >= 0.85 and not ally_blocked and kill_count_in_win >= 1:
        hype += 4.0
    if 10.0 <= window_dur <= 24.0 and kill_count_in_win >= 1:
        hype += 3.0

    if kill_count_in_win == 2 and kill_span_s > 6.5:
        hype -= min(12.0, round((kill_span_s - 6.5) * 1.5, 1))
    elif kill_count_in_win >= 3 and kill_span_s > 11.0:
        hype -= min(10.0, round((kill_span_s - 11.0) * 1.5, 1))
    if player_died:
        hype -= 18.0
    if ally_blocked:
        hype -= 3.0
    if window_dur > 32.0:
        hype -= 10.0
    elif window_dur < 6.0:
        hype -= 6.0
    if first_kill_offset_s > 4.5 and not objective_secured:
        hype -= min(10.0, round((first_kill_offset_s - 4.5) * 2.0, 1))

    if directive is None and not os.environ.get("PYTEST_CURRENT_TEST"):
        directive_data = _load_learning_directive_safe()
    else:
        directive_data = directive if isinstance(directive, dict) else {}

    mult = 1.0
    learning_signals: List[str] = []
    if directive_data:
        action_weights = directive_data.get("action_weights") or {}
        eval_mults = ((directive_data.get("evaluator_config") or {}).get("action_multipliers") or {})
        raw_mult = action_weights.get(action_type) if action_weights.get(action_type) is not None else eval_mults.get(action_type)
        if raw_mult is not None:
            try:
                mult = max(0.88, min(1.15, float(raw_mult)))
            except (TypeError, ValueError):
                mult = 1.0
        if abs(mult - 1.0) >= 0.01 and kill_count_in_win >= 1:
            hype = round(hype * mult, 1)
            learning_signals.append(f"action_mult:{action_type}={mult:.2f}")

        recent_evr = _get_recent_evr_safe(directive_data)
        if recent_evr is not None and recent_evr < 48.0 and first_kill_offset_s > 3.5 and kill_count_in_win >= 1 and not objective_secured:
            evr_pen = min(8.0, round((first_kill_offset_s - 3.5) * 2.5, 1))
            hype -= evr_pen
            learning_signals.append(f"low_evr_slow_hook:-{evr_pen:.1f}(evr={recent_evr:.1f}%,fk={first_kill_offset_s:.1f}s)")

    rejection_code: Optional[str] = None
    rejection_reason = ""
    fallback_eligible = False

    if kill_count_in_win == 0 and not objective_secured:
        rejection_code = "REJECT_NO_KILLS"
        rejection_reason = "Brak potwierdzonych zabójstw OCR w oknie klipu i brak zabezpieczonego obiektu"
        hype = min(hype, 15.0)
    elif player_died and kill_count_in_win <= 2 and not objective_secured:
        rejection_code = "REJECT_DIED_LOW_IMPACT"
        rejection_reason = f"Gracz zginął na końcu akcji przy zaledwie {kill_count_in_win} kill(ach) w oknie"
        hype = min(hype, 24.0)
    elif window_dur > 28.0 and kill_count_in_win <= 1 and not objective_secured:
        rejection_code = "REJECT_WALKING_SIM"
        rejection_reason = f"Rozwleczony klip ({window_dur:.1f}s) z {kill_count_in_win} killem — symulator chodzenia"
        hype = min(hype, 28.0)
    elif (not is_outplayed) and kill_count_in_win >= 3 and conf < 0.45 and ally_blocked:
        rejection_code = "REJECT_LOW_CONFIDENCE"
        rejection_reason = f"Podejrzany OCR multikilla przy zablokowanym banerze sojusznika (conf={conf:.2f})"
        hype = min(hype, 35.0)
    elif kill_count_in_win == 1 and not is_clutch and min_hp > 25.0 and not objective_secured:
        rejection_code = "REJECT_MEDIOCRE_1KILL"
        rejection_reason = f"Przeciętny pojedynczy kill bez clutcha (min_HP={min_hp:.0f}%, brak obiektu)"
        hype = min(hype, 42.0)
        fallback_eligible = raw_ok
    elif (not is_outplayed or (outplayed_rank or 0) < 2) and (not raw_ok and kill_count_in_win <= 1 and not objective_secured):
        rejection_code = str(raw_code or "REJECT_RAW_GATE")
        rejection_reason = str(raw_reason or "Odrzucono przez bramkę jakości surowca")
        hype = min(hype, 38.0)

    hype_score = round(max(0.0, min(100.0, hype)), 1)
    qualified = rejection_code is None

    hook_text = str(entry.get("hook_text") or "").strip()
    hk_up = hook_text.upper()
    if action_type not in ("pentakill",) and "PENTA" in hk_up:
        hook_text = ""
    if action_type not in ("pentakill", "quadrakill") and "QUADRA" in hk_up:
        hook_text = ""
    if action_type in ("triple", "quadrakill", "pentakill") and "DOUBLE" in hk_up:
        hook_text = ""
    if action_type in ("double", "quadrakill", "pentakill") and "TRIPLE" in hk_up:
        hook_text = ""

    entry.update({
        "raw_detected_frag_type": raw_det,
        "action_type": action_type,
        "kill_count": kill_count_in_win,
        "kill_count_total_file": len(raw_kills),
        "kills_in_window": kills_in_win,
        "kill_span_s": kill_span_s,
        "first_kill_offset_s": first_kill_offset_s,
        "window_dur": window_dur,
        "hook_text": hook_text,
        "hype_score": hype_score,
        "learning_action_multiplier": round(mult, 3),
        "learning_signals_applied": learning_signals,
        "qualified": qualified,
        "fallback_eligible": fallback_eligible,
        "fallback_mediocre": False,
        "rejection_code": rejection_code,
        "rejection_reason": rejection_reason,
    })
    return entry


def _apply_outplayed_anchor(
    clip_info: Dict[str, Any],
    raw_kills: List[Dict[str, Any]],
    raw_det: str,
    clip_start: float,
    clip_end: float,
    peak_moment: float,
    combat_segs: Optional[List[Tuple[float, float]]],
    duration: float,
) -> Tuple[List[Dict[str, Any]], str, float, float, float, Optional[List[Tuple[float, float]]]]:
    """Kotwiczy okno montażowe do znacznika Riot API z Outplayed przy multikillu lub długim klipie."""
    event_source = str(clip_info.get("event_source") or "")
    best_t = clip_info.get("best_event_time_s")
    tier_rank = clip_info.get("event_tier_rank")
    if (
        not event_source.startswith("outplayed_")
        or best_t is None
        or not isinstance(tier_rank, (int, float))
        or int(tier_rank) < 2
    ):
        return raw_kills, raw_det, clip_start, clip_end, peak_moment, combat_segs

    t_ev = max(0.0, min(duration, float(best_t)))
    t_rank = int(tier_rank)
    event_tier = str(clip_info.get("event_tier") or _TIER_BY_RANK.get(t_rank, raw_det))
    try:
        try:
            from lol_agent.account_manager import get_target_duration_bounds
        except ImportError:
            from account_manager import get_target_duration_bounds  # type: ignore
        min_dur, max_dur = get_target_duration_bounds(t_rank)
    except Exception:
        min_dur, max_dur = 11.0, (17.5 if t_rank >= 4 else 15.2)

    cur_span = float(clip_end) - float(clip_start)
    ocr_in_win = [
        k for k in raw_kills
        if (clip_start - 0.6) <= float(k.get("timestamp", 0.0)) <= (clip_end + 0.6)
    ]
    ocr_max_tier = max([int(k.get("tier") or 0) for k in ocr_in_win], default=0)
    window_covers_peak = (
        (clip_start + 1.5 <= t_ev <= clip_end - 1.0)
        and ((min_dur - 1.0) <= cur_span <= max(16.0, max_dur + 0.8))
        and ocr_max_tier >= t_rank
    )
    if window_covers_peak:
        return raw_kills, event_tier, clip_start, clip_end, peak_moment, combat_segs

    events_summary = clip_info.get("events_summary")
    best_past_s = clip_info.get("best_event_past_s")
    best_future_s = clip_info.get("best_event_future_s")
    est_first_kill_s = clip_info.get("est_first_kill_s")
    est_last_kill_s = clip_info.get("est_last_kill_s")
    if (events_summary is None or est_last_kill_s is None) and clip_info.get("path"):
        try:
            try:
                from lol_agent.outplayed_db import get_outplayed_clip_info
            except ImportError:
                from outplayed_db import get_outplayed_clip_info  # type: ignore
            full_op = get_outplayed_clip_info(str(clip_info["path"]))
            if full_op:
                events_summary = events_summary if events_summary is not None else full_op.get("events_summary")
                best_past_s = best_past_s if best_past_s is not None else full_op.get("best_event_past_s")
                best_future_s = best_future_s if best_future_s is not None else full_op.get("best_event_future_s")
                est_first_kill_s = est_first_kill_s if est_first_kill_s is not None else full_op.get("est_first_kill_s")
                est_last_kill_s = est_last_kill_s if est_last_kill_s is not None else full_op.get("est_last_kill_s")
        except Exception as exc:
            print(f"[Overnight] [WARN] Błąd odczytu outplayed_db dla klatki {clip_info.get('path')}: {exc}")

    kill_times = sorted(
        float(ev["time_s"])
        for ev in (events_summary or [])
        if isinstance(ev, dict)
        and ev.get("type") == "kill"
        and isinstance(ev.get("time_s"), (int, float))
        and float(ev["time_s"]) <= t_ev + 0.5
    )
    burst: List[float] = [t_ev]
    for kt in reversed(kill_times):
        if kt >= burst[0] - 0.25:
            continue
        if (burst[0] - kt) <= 10.5 and (t_ev - kt) <= 18.0:
            burst.insert(0, kt)
        else:
            break

    later_ev_kills = [
        float(ev["time_s"])
        for ev in (events_summary or [])
        if isinstance(ev, dict)
        and ev.get("type") == "kill"
        and isinstance(ev.get("time_s"), (int, float))
        and float(ev["time_s"]) > t_ev + 1.5
    ]
    ocr_target_hits = [
        k for k in ocr_in_win
        if int(k.get("tier") or 0) >= t_rank
        and abs(float(k.get("timestamp", -99.0)) - t_ev) <= 3.5
    ]
    if ocr_target_hits and not later_ev_kills:
        ocr_real_end = max(float(k.get("timestamp", t_ev)) for k in ocr_target_hits)
        anchor_end_k = max(min(t_ev, ocr_real_end), ocr_real_end)
    else:
        anchor_end_k = max(t_ev, float(est_last_kill_s)) if isinstance(est_last_kill_s, (int, float)) else t_ev
    anchor_end_k = min(duration, anchor_end_k)

    burst_first = burst[0]
    anchor_start_k = (
        min(burst_first, float(est_first_kill_s))
        if isinstance(est_first_kill_s, (int, float))
        else burst_first
    )
    has_distinct_first_kill = (
        (anchor_start_k < anchor_end_k - 1.0 and burst_first < t_ev - 1.0)
        or (isinstance(est_first_kill_s, (int, float)) and float(est_first_kill_s) < anchor_end_k - 1.5)
    )
    max_pre_first_kill = 3.2 if t_rank >= 4 else 3.0
    default_pre_first_kill = 2.8 if t_rank >= 4 else 2.4

    if anchor_start_k < anchor_end_k - 1.0 and burst_first < t_ev - 1.0:
        new_start = max(0.0, anchor_start_k - default_pre_first_kill)
    elif isinstance(est_first_kill_s, (int, float)) and float(est_first_kill_s) < anchor_end_k - 1.5:
        new_start = max(0.0, float(est_first_kill_s) - default_pre_first_kill)
    else:
        default_lead = min(9.5, max_dur - 3.5) if t_rank >= 4 else (3.8 if t_rank <= 2 else min(7.2, max_dur - 3.5))
        lead = float(best_past_s) if isinstance(best_past_s, (int, float)) and float(best_past_s) > 0 else default_lead
        max_lead = min(11.5, max_dur - 3.0) if t_rank >= 4 else (3.95 if t_rank <= 2 else min(7.8, max_dur - 3.2))
        min_lead = 3.0 if t_rank <= 2 else 6.0
        lead = max(min_lead, min(max_lead, lead))
        new_start = max(0.0, t_ev - lead)

    is_merged_est = isinstance(est_last_kill_s, (int, float)) and float(est_last_kill_s) > t_ev + 0.5
    tail_s = 2.0 if is_merged_est else max(2.8, min(3.6, float(best_future_s) if isinstance(best_future_s, (int, float)) and float(best_future_s) > 0 else 3.2))
    new_end = min(duration, anchor_end_k + tail_s)
    eff_min_dur = min(min_dur, 8.2) if (not has_distinct_first_kill and t_rank <= 2) else min_dur
    # P0.2: Najpierw delikatny tail po ostatnim killu; wstecz cofamy wyłącznie do granicy max_pre_first_kill (bez 5-9s biegu)
    if (new_end - new_start) < eff_min_dur:
        extra_tail_end = min(duration, anchor_end_k + 3.5)
        if extra_tail_end > new_end:
            new_end = min(extra_tail_end, new_start + eff_min_dur)
        if (new_end - new_start) < eff_min_dur:
            desired_start = max(0.0, new_end - eff_min_dur)
            if has_distinct_first_kill:
                min_allowed_start = max(0.0, anchor_start_k - max_pre_first_kill)
                new_start = max(desired_start, min_allowed_start)
            elif t_rank <= 2:
                min_allowed_single = max(0.0, t_ev - 4.0)
                new_start = max(desired_start, min_allowed_single)
            else:
                new_start = desired_start
        if (new_end - new_start) < eff_min_dur and not has_distinct_first_kill and duration > new_end:
            max_single_end = min(duration, anchor_end_k + 4.1)
            new_end = min(max_single_end, new_start + eff_min_dur)
    # Zbyt długie okna lub martwe intro przed 1. wykrytym OCR killem tniemy od początku
    ocr_in_new = [
        float(k.get("timestamp", 0.0))
        for k in raw_kills
        if (new_start - 0.3) <= float(k.get("timestamp", 0.0)) <= (new_end + 0.3)
    ]
    if ocr_in_new:
        first_ocr_in = min(ocr_in_new)
        if (first_ocr_in - new_start) > 3.6 and first_ocr_in <= anchor_end_k + 0.5:
            want_trim_start = round(max(new_start, first_ocr_in - 2.6), 2)
            if (new_end - want_trim_start) < eff_min_dur and duration > new_end:
                new_end = min(duration, anchor_end_k + 3.4, want_trim_start + eff_min_dur)
            if (new_end - want_trim_start) >= max(8.0, eff_min_dur - 0.2):
                new_start = want_trim_start

    if (new_end - new_start) > max_dur:
        safe_earliest_kill = max(0.0, anchor_start_k - 1.2)
        trimmed_start = min(safe_earliest_kill, new_end - max_dur)
        if trimmed_start > new_start:
            new_start = trimmed_start

    anchored_peak_t = min(max(new_start + 0.5, anchor_end_k), new_end - 0.8)

    filtered_segs: Optional[List[Tuple[float, float]]] = None
    if combat_segs:
        segs = [
            (max(new_start, float(s[0])), min(new_end, float(s[1])))
            for s in combat_segs
            if float(s[1]) > new_start + 0.5 and float(s[0]) < new_end - 0.5
        ]
        if segs:
            filtered_segs = [(round(a, 2), round(b, 2)) for a, b in segs if b - a >= 1.5] or None

    # Uzupełnij listę zabójstw w zakotwiczonym oknie znacznikami Riot API, jeśli OCR nie trafił klatek
    anchored_ocr = [
        k for k in raw_kills
        if (new_start - 0.5) <= float(k.get("timestamp", 0.0)) <= (new_end + 0.5)
    ]
    ocr_anch_max = max([int(k.get("tier") or 0) for k in anchored_ocr], default=0)
    merged_kills = list(raw_kills)
    if ocr_anch_max < t_rank:
        # Dodaj brakujące punkty Riot w nowym oknie, unikając duplikatów <1.0s
        op_points: List[Tuple[float, int]] = []
        in_win_kt = [kt for kt in kill_times if new_start - 0.3 <= kt <= new_end + 0.3]
        for idx_kt, kt in enumerate(in_win_kt):
            is_peak = abs(kt - t_ev) <= 0.4
            op_points.append((round(kt, 2), t_rank if is_peak else min(t_rank, idx_kt + 1)))
        if not any(abs(pt[0] - anchored_peak_t) <= 0.5 for pt in op_points):
            op_points.append((round(anchored_peak_t, 2), t_rank))
        for pt_t, pt_tier in op_points:
            near_idx = next(
                (i for i, k in enumerate(merged_kills) if abs(float(k.get("timestamp", -99.0)) - pt_t) <= 1.0),
                None,
            )
            banner_lbl = _BANNER_BY_RANK.get(pt_tier, "KILL")
            if near_idx is not None:
                if int(merged_kills[near_idx].get("tier") or 0) < pt_tier:
                    merged_kills[near_idx] = {
                        **merged_kills[near_idx],
                        "tier": pt_tier,
                        "label": banner_lbl,
                        "source": event_source,
                    }
            else:
                merged_kills.append({
                    "timestamp": pt_t,
                    "tier": pt_tier,
                    "label": banner_lbl,
                    "confidence": 0.96,
                    "source": event_source,
                })
        merged_kills.sort(key=lambda k: float(k.get("timestamp", 0.0)))
    elif (
        len(anchored_ocr) < min(t_rank, 2)
        and isinstance(est_first_kill_s, (int, float))
        and anchored_ocr
        and float(est_first_kill_s) < min(float(k.get("timestamp", 0.0)) for k in anchored_ocr) - 0.6
        and (new_start - 0.3) <= float(est_first_kill_s) <= (new_end + 0.2)
    ):
        merged_kills.append({
            "timestamp": round(float(est_first_kill_s), 2),
            "tier": 1,
            "label": "KILL",
            "confidence": 0.92,
            "source": event_source,
        })
        merged_kills.sort(key=lambda k: float(k.get("timestamp", 0.0)))

    return merged_kills, event_tier, new_start, new_end, anchored_peak_t, filtered_segs


def _analyze_single_clip_for_overnight(clip_info: Dict[str, Any]) -> Dict[str, Any]:
    """Analizuje pojedynczy plik wideo pod kątem jakości surowca, hype i przydatności pod montaż."""
    path = str(clip_info.get("path") or "")
    filename = str(clip_info.get("filename") or Path(path).name)
    modified = float(clip_info.get("modified") or 0.0)
    size_mb = float(clip_info.get("size_mb") or 0.0)

    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return {
                "filename": filename,
                "path": path,
                "modified": modified,
                "size_mb": size_mb,
                "qualified": False,
                "fallback_eligible": False,
                "rejection_code": "REJECT_UNREADABLE",
                "rejection_reason": "Nie można otworzyć pliku wideo",
                "hype_score": 0.0,
            }
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        frame_cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()

    duration = (frame_cnt / fps) if fps > 0 else 0.0
    if height < 720 or fps < 24.0 or duration < 5.0 or duration > 180.0:
        return {
            "filename": filename,
            "path": path,
            "modified": modified,
            "size_mb": size_mb,
            "duration": round(duration, 2),
            "width": width,
            "height": height,
            "fps": round(fps, 1),
            "qualified": False,
            "fallback_eligible": False,
            "rejection_code": "REJECT_LOW_TECH",
            "rejection_reason": f"Parametry poza zakresem ({width}x{height}@{fps:.0f}fps, {duration:.1f}s)",
            "hype_score": 0.0,
        }

    try:
        from lol_agent.lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window
        from lol_agent.lol_quality_validator import is_raw_material_viable
    except ImportError:
        from lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window  # type: ignore
        from lol_quality_validator import is_raw_material_viable  # type: ignore

    frag_res = analyze_clip_frags(path, sample_fps=1.0)
    raw_kills = list(frag_res.kills or [])
    raw_det = str(frag_res.detected_frag_type or "outplay").lower().strip()
    pre_act = _normalize_action_type_in_window(raw_det, raw_kills, bool(frag_res.is_clutch_1hp))

    clip_start, clip_end, peak_moment, combat_segs = compute_optimal_clip_window(
        frag_res,
        duration,
        action_type=pre_act,
    )
    raw_kills, raw_det, clip_start, clip_end, peak_moment, combat_segs = _apply_outplayed_anchor(
        clip_info=clip_info,
        raw_kills=raw_kills,
        raw_det=raw_det,
        clip_start=clip_start,
        clip_end=clip_end,
        peak_moment=peak_moment,
        combat_segs=combat_segs,
        duration=duration,
    )
    window_dur = max(1.0, round(float(clip_end) - float(clip_start), 2))
    player_died = _check_trailing_survival(path, clip_end, fps)

    peaks_tuples = [(float(k["timestamp"]), str(k.get("label", "KILL"))) for k in raw_kills]
    raw_ok, raw_code, raw_reason = is_raw_material_viable(
        peaks=peaks_tuples,
        clip_start=clip_start,
        clip_end=clip_end,
        source_size=(width, height),
        source_fps=fps,
    )

    raw_entry = {
        "filename": filename,
        "path": path,
        "modified": modified,
        "size_mb": size_mb,
        "duration": round(duration, 2),
        "width": width,
        "height": height,
        "fps": round(fps, 1),
        "raw_detected_frag_type": raw_det,
        "kills": raw_kills,
        "clip_start": round(float(clip_start), 2),
        "clip_end": round(float(clip_end), 2),
        "peak_moment": round(float(peak_moment), 2),
        "window_dur": window_dur,
        "combat_segments": [list(s) for s in combat_segs] if combat_segs else None,
        "hook_text": str(frag_res.suggested_title_hook or "").strip(),
        "confidence": round(float(frag_res.confidence or 0.0), 3),
        "min_hp_percentage": round(float(frag_res.min_hp_percentage if frag_res.min_hp_percentage is not None else 100.0), 1),
        "is_clutch_1hp": bool(frag_res.is_clutch_1hp),
        "objective_secured": bool(frag_res.objective_secured),
        "objective_label": str(frag_res.objective_label or ""),
        "ally_banner_blocked": bool(frag_res.ally_banner_blocked),
        "player_died": player_died,
        "raw_viable": bool(raw_ok),
        "raw_code": raw_code,
        "raw_reason": raw_reason,
        "champion": clip_info.get("champion") or "",
        "is_favorite": bool(clip_info.get("is_favorite", False)),
        "event_tier": clip_info.get("event_tier") or "",
        "event_tier_rank": clip_info.get("event_tier_rank"),
        "event_source": clip_info.get("event_source") or "none",
        "best_event_time_s": clip_info.get("best_event_time_s"),
        "est_first_kill_s": clip_info.get("est_first_kill_s"),
        "est_last_kill_s": clip_info.get("est_last_kill_s"),
        "total_kills_in_clip": clip_info.get("total_kills_in_clip"),
        "match_folder": clip_info.get("match_folder") or "",
        "match_date": clip_info.get("match_date") or "",
        "clip_base_key": clip_info.get("clip_base_key") or "",
        "match_kda": clip_info.get("match_kda") or "",
    }
    return _score_and_classify_candidate(raw_entry)


def _select_top_diverse_candidates(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    top_n: int,
) -> List[Dict[str, Any]]:
    """Wybiera Top N najlepszych kandydatów z deduplikacją par (_0/_1) i dywersyfikacją między meczami."""
    sort_key = lambda c: (
        float(c.get("hype_score", 0.0)),
        int(c.get("kill_count", 0)),
        bool(c.get("is_favorite", False)),
        bool(c.get("objective_secured", False)),
        float(c.get("confidence", 0.0)),
        float(c.get("modified", 0.0)),
    )
    q_sorted = sorted(qualified, key=sort_key, reverse=True)
    selected: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    seen_base_keys: set[str] = set()
    match_counts: Dict[str, int] = {}

    def _base_key(cand: Dict[str, Any]) -> str:
        bk = str(cand.get("clip_base_key") or "").strip().lower()
        if bk:
            return bk
        p = Path(str(cand.get("path") or ""))
        return re.sub(r"_\d+$", "", p.stem).lower()

    def _is_near_duplicate(cand: Dict[str, Any], chosen: List[Dict[str, Any]]) -> bool:
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            return True
        c_dir = str(Path(str(cand.get("path") or "")).parent)
        c_m = float(cand.get("modified") or 0.0)
        for prev in chosen:
            if str(Path(str(prev.get("path") or "")).parent) == c_dir and abs(c_m - float(prev.get("modified") or 0.0)) < 20.0:
                return True
        return False

    for cand in q_sorted:
        if len(selected) >= top_n:
            break
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            continue
        mf = str(cand.get("match_folder") or "").strip()
        if _is_near_duplicate(cand, selected) or (mf and match_counts.get(mf, 0) >= 2):
            deferred.append(cand)
        else:
            selected.append(cand)
            if c_bk:
                seen_base_keys.add(c_bk)
            if mf:
                match_counts[mf] = match_counts.get(mf, 0) + 1

    # Jeśli po dywersyfikacji brakło różnych meczów do top_n, dobierz z odłożonych (zawsze pomijając duplikaty _0/_1)
    for cand in deferred:
        if len(selected) >= top_n:
            break
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            continue
        selected.append(cand)
        if c_bk:
            seen_base_keys.add(c_bk)

    # Jeśli zakwalifikowanych jest mniej niż top_n, dopuszczamy WYŁĄCZNIE fallback_eligible (1-kill raw_ok),
    # NIGDY 0-kill śmieci ani zgonów o niskim wpływie
    if len(selected) < top_n:
        fb_pool = sorted(
            [c for c in rejected if c.get("fallback_eligible")],
            key=sort_key,
            reverse=True,
        )
        for cand in fb_pool:
            if len(selected) >= top_n:
                break
            c_bk = _base_key(cand)
            if c_bk and c_bk in seen_base_keys:
                continue
            copy_c = dict(cand)
            copy_c["fallback_mediocre"] = True
            selected.append(copy_c)
            if c_bk:
                seen_base_keys.add(c_bk)

    return selected


def _make_prerejected_entry(cl: Dict[str, Any], code: str, reason: str) -> Dict[str, Any]:
    return {
        "filename": cl.get("filename", "?"),
        "path": str(cl.get("path") or ""),
        "modified": float(cl.get("modified") or 0.0),
        "size_mb": float(cl.get("size_mb") or 0.0),
        "action_type": str(cl.get("event_tier") or "outplay"),
        "champion": cl.get("champion") or "",
        "is_favorite": bool(cl.get("is_favorite", False)),
        "event_tier": cl.get("event_tier") or "",
        "event_tier_rank": cl.get("event_tier_rank"),
        "event_source": cl.get("event_source") or "none",
        "best_event_time_s": cl.get("best_event_time_s"),
        "total_kills_in_clip": cl.get("total_kills_in_clip"),
        "match_folder": cl.get("match_folder") or "",
        "match_date": cl.get("match_date") or "",
        "clip_base_key": cl.get("clip_base_key") or "",
        "match_kda": cl.get("match_kda") or "",
        "qualified": False,
        "fallback_eligible": False,
        "rejection_code": code,
        "rejection_reason": reason,
        "hype_score": 0.0,
    }


def _merge_fresh_metadata_into_cached(cached_item: Dict[str, Any], cl: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(cached_item)
    for k in (
        "champion",
        "is_favorite",
        "event_tier",
        "event_tier_rank",
        "event_source",
        "best_event_time_s",
        "est_first_kill_s",
        "est_last_kill_s",
        "total_kills_in_clip",
        "match_folder",
        "match_date",
        "clip_base_key",
        "match_kda",
    ):
        if k in cl and cl.get(k) not in (None, ""):
            merged[k] = cl.get(k)
        elif k == "is_favorite" and "is_favorite" in cl:
            merged[k] = bool(cl["is_favorite"])
    return merged


def scan_and_rank_all_clips(
    folder: Optional[str] = None,
    top_n: int = 5,
    skip_published: bool = True,
    use_cache: bool = True,
    max_workers: int = 3,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    champion_name: Optional[str] = "Katarina",
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
    skip_dismissed_repeats: bool = True,
    auto_prune_unaccepted_repeats: bool = False,
    max_unaccepted_renders: int = MAX_UNACCEPTED_OVERNIGHT_RENDERS,
) -> Dict[str, Any]:
    """
    Skanuje wszystkie nagrania w folderze, filtruje wstępnie wg telemetrii Riot Outplayed,
    odfiltrowuje opublikowane, powtórzone niezaakceptowane oraz przeciętne klipy i zwraca Top N kandydatów o najwyższym `hype_score`.
    """
    try:
        from lol_agent.api.routers.clips import invalidate_clips_cache, scan_available_clips
    except ImportError:
        from api.routers.clips import invalidate_clips_cache, scan_available_clips  # type: ignore

    all_clips = scan_available_clips(folder)
    total_found = len(all_clips)
    skipped_published = 0
    skipped_dismissed = 0
    pruned_unaccepted_repeats = 0
    pruned_clip_filenames: List[str] = []
    champ_ok_pool: List[Dict[str, Any]] = []
    pre_rejected: List[Dict[str, Any]] = []
    req_champ = str(champion_name or "").strip().lower()
    tf_key = str(tier_filter or "auto").strip().lower()
    min_rank = TIER_FILTER_MIN_RANK.get(tf_key, -1)

    render_history = _collect_overnight_render_history() if skip_dismissed_repeats else {}
    accepted_sources, accepted_outputs = (
        _collect_accepted_clip_keys() if (skip_dismissed_repeats or render_history) else (set(), set())
    )
    dismissed_map = load_dismissed_clips() if skip_dismissed_repeats else {}
    dismissed_dirty = False
    repeat_threshold = max(1, int(max_unaccepted_renders))

    for cl in all_clips:
        src_name = str(cl.get("filename") or Path(str(cl.get("path") or "")).name).strip()
        src_key = src_name.lower()
        hist = render_history.get(src_key)
        is_accepted = (
            bool(cl.get("already_published"))
            or src_key in accepted_sources
            or bool(hist and any(o in accepted_outputs for o in hist.get("output_filenames", set())))
        )
        if is_accepted:
            if skip_published:
                skipped_published += 1
                continue
        elif skip_dismissed_repeats and src_key in dismissed_map:
            skipped_dismissed += 1
            pre_rejected.append(
                _make_prerejected_entry(
                    cl,
                    "REJECT_DISMISSED_REPEAT",
                    "Wykluczony automatycznie po wcześniejszych niezaakceptowanych montażach nocnych",
                )
            )
            continue
        elif skip_dismissed_repeats and hist and len(hist.get("batch_ids") or set()) >= repeat_threshold:
            b_cnt = len(hist.get("batch_ids") or set())
            if auto_prune_unaccepted_repeats:
                prune_unaccepted_repeat_clip(cl, hist, dismissed_map, accepted_outputs)
                dismissed_dirty = True
                pruned_unaccepted_repeats += 1
                pruned_clip_filenames.append(src_name)
            skipped_dismissed += 1
            pre_rejected.append(
                _make_prerejected_entry(
                    cl,
                    "REJECT_UNACCEPTED_REPEAT_2X",
                    f"Powtórzony {b_cnt}x w paczkach nocnych bez publikacji (wykluczony)",
                )
            )
            continue

        cl_champ = str(cl.get("champion") or "").strip()
        if only_channel_champion and req_champ and cl_champ and cl_champ.lower() != req_champ:
            pre_rejected.append(
                _make_prerejected_entry(
                    cl,
                    "REJECT_WRONG_CHAMPION",
                    f"Inny bohater w telemetry ({cl_champ} != {champion_name})",
                )
            )
            continue
        champ_ok_pool.append(cl)

    if dismissed_dirty:
        _save_dismissed_clips(dismissed_map)
        try:
            invalidate_clips_cache()
        except Exception as exc:
            print(f"[Overnight] [WARN] Błąd inwalidacji cache klipów po pruningu: {exc}")

    # Policz ile unikalnych klipów (bez duplikatów _0/_1) to potwierdzone multikille (>= Double)
    multikill_base_keys: set[str] = set()
    for cl in champ_ok_pool:
        src = str(cl.get("event_source") or "")
        rk = cl.get("event_tier_rank")
        if (src.startswith("outplayed_") or src == "medal_db") and isinstance(rk, (int, float)) and int(rk) >= 2:
            bk = str(cl.get("clip_base_key") or "").strip().lower() or str(cl.get("path") or "")
            multikill_base_keys.add(bk)
    multikills_available = len(multikill_base_keys)

    pool: List[Dict[str, Any]] = []
    for cl in champ_ok_pool:
        src = str(cl.get("event_source") or "")
        rk_raw = cl.get("event_tier_rank")
        has_db_tier = (src.startswith("outplayed_") or src == "medal_db") and isinstance(rk_raw, (int, float))
        if has_db_tier:
            t_rank = int(rk_raw)
            if t_rank == 0 and tf_key != "all":
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_ASSIST_ONLY",
                        "Tylko asysta w telemetrii Riot Outplayed (pominięto przed OCR)",
                    )
                )
                continue
            if min_rank >= 1 and t_rank < min_rank:
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_TIER_FILTER",
                        f"Tier '{cl.get('event_tier')}' poniżej filtra '{tf_key}'",
                    )
                )
                continue
            if tf_key == "auto" and t_rank == 1 and multikills_available >= max(1, int(top_n)):
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_SINGLE_KILL_MULTIKILLS_AVAILABLE",
                        f"Single kill w bazie Outplayed pominięty przed OCR (dostępne {multikills_available} multikilli)",
                    )
                )
                continue
        pool.append(cl)

    cache_data = _load_scan_cache() if use_cache else {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}
    entries = cache_data["entries"]
    results: List[Dict[str, Any]] = list(pre_rejected)
    analyzed_cached: List[Dict[str, Any]] = []
    to_analyze: List[Tuple[Dict[str, Any], str]] = []

    for cl in pool:
        p = str(cl.get("path") or "")
        try:
            st = Path(p).stat()
            ckey = _cache_key_for(p, st.st_size, st.st_mtime)
        except Exception:
            ckey = _cache_key_for(p, int(cl.get("size_mb", 0) * 1024 * 1024), float(cl.get("modified", 0)))

        cached_item = entries.get(ckey) if use_cache else None
        if isinstance(cached_item, dict) and Path(p).exists():
            merged_cached = _merge_fresh_metadata_into_cached(cached_item, cl)
            analyzed_cached.append(_score_and_classify_candidate(merged_cached))
        else:
            to_analyze.append((cl, ckey))

    results.extend(analyzed_cached)
    done_count = len(analyzed_cached)
    total_to_scan = len(pool)
    if progress_cb and (analyzed_cached or pre_rejected):
        progress_cb(
            done_count,
            total_to_scan,
            f"Pre-filtr: odrzucono {len(pre_rejected)}, cache {done_count}/{total_to_scan}",
        )

    if to_analyze:
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        workers = max(1, min(int(max_workers or 1), len(to_analyze)))
        cache_lock = threading.Lock()

        def _worker(item: Tuple[Dict[str, Any], str]) -> Tuple[str, Dict[str, Any]]:
            cl_item, ckey = item
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Skan przerwany przez użytkownika")
            res = _analyze_single_clip_for_overnight(cl_item)
            return ckey, res

        ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        cancelled = False
        try:
            future_map = {ex.submit(_worker, item): item[0] for item in to_analyze}
            newly_scanned = 0
            for fut in concurrent.futures.as_completed(future_map):
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    for pending in future_map:
                        pending.cancel()
                    break
                cl_meta = future_map[fut]
                done_count += 1
                try:
                    ckey, res = fut.result()
                    results.append(res)
                    newly_scanned += 1
                    if use_cache:
                        with cache_lock:
                            entries[ckey] = res
                            if newly_scanned % 5 == 0:
                                _save_scan_cache(cache_data)
                except InterruptedError:
                    cancelled = True
                    for pending in future_map:
                        pending.cancel()
                    break
                except Exception as exc:
                    results.append({
                        "filename": cl_meta.get("filename", "?"),
                        "path": cl_meta.get("path", ""),
                        "modified": float(cl_meta.get("modified") or 0.0),
                        "qualified": False,
                        "fallback_eligible": False,
                        "rejection_code": "REJECT_SCAN_ERROR",
                        "rejection_reason": str(exc),
                        "hype_score": 0.0,
                    })
                if progress_cb:
                    progress_cb(done_count, total_to_scan, str(cl_meta.get("filename", "")))
        finally:
            ex.shutdown(wait=not cancelled, cancel_futures=cancelled)

    if use_cache and to_analyze:
        _save_scan_cache(cache_data)

    qualified = [r for r in results if r.get("qualified")]
    rejected = [r for r in results if not r.get("qualified")]
    selected = _select_top_diverse_candidates(qualified, rejected, max(1, int(top_n)))

    rejection_breakdown: Dict[str, int] = {}
    for r in rejected:
        code = str(r.get("rejection_code") or "REJECT_OTHER")
        rejection_breakdown[code] = rejection_breakdown.get(code, 0) + 1

    return {
        "folder": folder or "Outplayed + Medal",
        "total_clips_found": total_found,
        "skipped_published": skipped_published,
        "skipped_dismissed": skipped_dismissed,
        "pruned_unaccepted_repeats": pruned_unaccepted_repeats,
        "pruned_clip_filenames": pruned_clip_filenames,
        "scanned_unpublished": len(results),
        "qualified_count": len(qualified),
        "rejected_count": len(rejected),
        "rejection_breakdown": rejection_breakdown,
        "selected": selected,
        "all_qualified": sorted(qualified, key=lambda c: float(c.get("hype_score", 0.0)), reverse=True),
        "rejected_sample": sorted(rejected, key=lambda c: float(c.get("hype_score", 0.0)), reverse=True)[:15],
    }


def _extract_defects(insp: Dict[str, Any], ig_ready: bool, item: Optional[Dict[str, Any]] = None) -> Tuple[List[str], bool]:
    defects: List[str] = []
    critical = False
    if insp.get("black_end_frame"):
        defects.append("black_end_frame")
        critical = True
    if not insp.get("frame0_hook_legible", True):
        defects.append("frame0_hook_illegible")
        critical = True
    if int(insp.get("audio_clip_gt_096") or 0) > 10:
        defects.append("audio_clipping_gt_10")
        critical = True
    if float(insp.get("av_delta_s") or 0.0) > 0.25:
        defects.append("av_desync_gt_025s")
        critical = True
    if insp.get("kill_overlay_zone") == "center_blocking":
        defects.append("center_blocking_overlay")
    vis_r = float(insp.get("player_visible_ratio") if insp.get("player_visible_ratio") is not None else 1.0)
    if 0.0 < vis_r < 0.55:
        defects.append("low_player_visibility")
    elif 0.0 < vis_r < 0.72:
        defects.append("player_offscreen_frames")
    edge_r = float(
        insp.get("player_edge_clip_ratio")
        if insp.get("player_edge_clip_ratio") is not None
        else ((item or {}).get("player_edge_clip_ratio") or 0.0)
    )
    if edge_r > 0.35:
        defects.append("high_edge_clipping")
    elif edge_r > 0.12:
        defects.append("moderate_edge_clipping")
    cam_step = float(insp.get("camera_peak_step_px") or (item or {}).get("camera_peak_step_px") or 0.0)
    if cam_step >= 220.0:
        defects.append("camera_jump_gt_220px")
    gap_s = float(insp.get("longest_gap_out_sec") or (item or {}).get("longest_gap_out_sec") or 0.0)
    if gap_s >= 3.8:
        defects.append("dead_gap_gt_3.8s")
    if insp.get("first_kill_out_sec") is not None:
        fk_sec = float(insp.get("first_kill_out_sec") or 0.0)
        if fk_sec > 4.8:
            defects.append("slow_intro_gt_4.8s")
        elif fk_sec > 3.5:
            defects.append("slow_intro_gt_3.5s")
    dur_s = float(insp.get("video_dur_s") or insp.get("duration_s") or 0.0)
    if 0.0 < dur_s < 9.0:
        defects.append("duration_too_short_lt_9s")
    elif dur_s > 16.5:
        defects.append("duration_too_long_gt_16.5s")
    if insp.get("hook_is_generic"):
        defects.append("generic_hook")
    if item and item.get("champion_mismatch"):
        defects.append(f"wrong_champion:{item.get('champion_name')}!={item.get('requested_champion')}")
    if not ig_ready:
        defects.append("ig_needs_transcode_on_upload")
    return defects, critical


_DISALLOWED_TEXT_RE = re.compile(r"[^\x20-\x7E\nąćęłńóśźżĄĆĘŁŃÓŚŹŻ–—’„”•]")
_BROKEN_PL_RE = re.compile(r"\b(?:triunf\w*|katarinsk\w*|obserwator\w*|dwuekranow\w*|z\s+obiektywem)\b", re.IGNORECASE)
_SCORE_MENTION_RE = re.compile(
    r"(?:final(?:_score)?\s*[=:]\s*|wynik\s*[=:]\s*|ocena\s*[=:]\s*|(?<!\d))(\d{2}(?:\.\d+)?)\s*(?=/100|\b)",
    re.IGNORECASE,
)


def _is_clean_consistent_polish_note(note: str, item: Dict[str, Any]) -> bool:
    """Weryfikuje poprawność językową, brak halucynacji tieru/wad/czasów i spójność liczb w notkach LoRA."""
    txt = str(note or "").strip()
    if len(txt) < 38:
        return False
    if _DISALLOWED_TEXT_RE.search(txt) or _BROKEN_PL_RE.search(txt):
        return False
    if not re.search(r"[a-ząćęłńóśźż]{4,}", txt.lower()):
        return False

    low = txt.lower()
    crit = bool(item.get("has_critical_defect"))
    real_defects = [d for d in (item.get("defects") or []) if d != "ig_needs_transcode_on_upload"]
    praise_tokens = (
        "świetn", "idealn", "niesamow", "perfekc", "najlepsz", "bez wątpliwości",
        "bez wad", "brak wad", "zero wad", "bez defekt", "bez zarzut", "mistrzostw",
    )
    if (crit or real_defects) and any(tok in low for tok in praise_tokens):
        return False
    if int(item.get("overnight_rank") or 1) >= 2 and any(tok in low for tok in ("najlepsz", "zwycięzc", "#1")):
        return False
    if (not real_defects) and "regresj" in low:
        return False
    if item.get("champion_mismatch"):
        req_ch = str(item.get("requested_champion") or "").strip().lower()
        act_ch = str(item.get("champion_name") or "").strip().lower()
        req_stem = req_ch[:5] if len(req_ch) >= 5 else req_ch
        act_stem = act_ch[:5] if len(act_ch) >= 5 else act_ch
        if req_stem and req_stem in low and (not act_stem or act_stem not in low):
            return False

    act = str(item.get("action_type") or "").lower()
    if act == "triple" and re.search(r"\b(?:dwufrag\w*|double)\b", low):
        return False
    if act == "double" and re.search(r"\b(?:tr[oó]jk\w*|trzy\s+frag\w*|triple|quadr\w*|pent\w*)\b", low):
        return False
    if act == "quadrakill" and re.search(r"\b(?:dwufrag\w*|tr[oó]jk\w*)\b", low):
        return False

    # Ochrona przed halucynowanymi timestampami w sekundach (np. zapamiętany szablon "3.0s, 4.5s i 8.2s")
    kill_ts_list = [
        float(v) for v in (item.get("kill_timestamps_out") or [])
        if isinstance(v, (int, float))
    ]
    if "3.0s, 4.5s" in low or "4.5s i 8.2s" in low:
        has_all_template_ts = kill_ts_list and all(
            any(abs(kt - target_t) <= 0.7 for kt in kill_ts_list)
            for target_t in (3.0, 4.5, 8.2)
        )
        if not has_all_template_ts:
            return False

    ts_matches = re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*s\b", txt, re.IGNORECASE)
    if ts_matches:
        has_kill_time_phrase = bool(
            re.search(r"(?:w|czas(?:ie)?|zabójstw\w*\s+w)\s+\d+(?:\.\d+)?\s*s\b", low)
        )
        if len(ts_matches) >= 2 and not kill_ts_list:
            return False
        real_times = list(kill_ts_list)
        for key in ("duration_s", "first_kill_out_sec", "kill_span_s", "longest_gap_out_sec"):
            val = item.get(key)
            if isinstance(val, (int, float)):
                real_times.append(float(val))
        if (len(ts_matches) >= 2 or has_kill_time_phrase) and real_times:
            for ts_str in ts_matches:
                try:
                    mentioned_s = float(ts_str)
                except ValueError:
                    continue
                if not any(abs(mentioned_s - rt) <= 0.7 for rt in real_times):
                    return False

    fs = item.get("final_score")
    known_metrics = [
        float(item[k])
        for k in ("final_score", "hype_score", "watchability_score", "qa_score")
        if isinstance(item.get(k), (int, float))
    ]
    if known_metrics:
        # Każda nieoznaczona liczba >= 30 (niebędąca sekundami/godzinami ani mianownikiem /100) musi odpowiadać realnej metryce tego shorta
        for m in re.finditer(r"(?<![\d./])(\d{2,3}(?:\.\d+)?)(?!\s*(?:s\b|ms\b|h\b|px\b|fps\b|k\b|%\b))", txt, re.IGNORECASE):
            end_pos = m.end()
            if txt[end_pos : end_pos + 1] == "/" and txt[end_pos + 1 : end_pos + 4] != "100":
                continue
            try:
                num_v = float(m.group(1))
            except Exception:
                continue
            if 30.0 <= num_v <= 100.0 and not any(abs(num_v - km) <= 1.8 for km in known_metrics):
                return False

    if isinstance(fs, (int, float)):
        fs_val = float(fs)
        for m in re.finditer(
            r"(?:final(?:_score)?\s*[=:]\s*|wynik\s*[=:]\s*|ocena\s*[=:]\s*)(\d{2}(?:\.\d+)?)|(\d{2}(?:\.\d+)?)\s*/\s*100|\((\d{2}(?:\.\d+)?)\)",
            txt,
            re.IGNORECASE,
        ):
            val_s = m.group(1) or m.group(2) or m.group(3)
            try:
                val = float(val_s)
            except Exception:
                continue
            if abs(val - fs_val) > 2.5:
                return False
        for labeled_re, key_name in (
            (r"hype\s*[=:]\s*(\d{2}(?:\.\d+)?)", "hype_score"),
            (r"watch(?:ability)?\s*[=:]\s*(\d{2}(?:\.\d+)?)", "watchability_score"),
            (r"qa\s*[=:]\s*(\d{2}(?:\.\d+)?)", "qa_score"),
        ):
            ref = item.get(key_name)
            if isinstance(ref, (int, float)):
                for m in re.finditer(labeled_re, txt, re.IGNORECASE):
                    try:
                        if abs(float(m.group(1)) - float(ref)) > 2.5:
                            return False
                    except Exception:
                        pass
    return True


def _build_honest_short_comment_pl(item: Dict[str, Any]) -> str:
    act = str(item.get("action_type", "outplay")).upper()
    champ = str(item.get("champion_name") or "?")
    hype = item.get("hype_score", 0)
    watch = item.get("watchability_score", 0)
    qa = item.get("qa_score", 0)
    extra_parts: List[str] = []
    if isinstance(item.get("duration_s"), (int, float)) and float(item["duration_s"]) > 0:
        extra_parts.append(f"dur={float(item['duration_s']):.1f}s")
    if isinstance(item.get("player_visible_ratio"), (int, float)):
        extra_parts.append(f"vis={float(item['player_visible_ratio']):.2f}")
    if isinstance(item.get("player_edge_clip_ratio"), (int, float)) and float(item["player_edge_clip_ratio"]) > 0:
        extra_parts.append(f"edge_clip={float(item['player_edge_clip_ratio']):.2f}")
    if isinstance(item.get("longest_gap_out_sec"), (int, float)) and float(item["longest_gap_out_sec"]) > 0:
        extra_parts.append(f"gap={float(item['longest_gap_out_sec']):.1f}s")
    extra_txt = f", {', '.join(extra_parts)}" if extra_parts else ""
    defects = [d for d in (item.get("defects") or []) if d != "ig_needs_transcode_on_upload"]
    defect_txt = f" | UWAGA wady: {', '.join(defects)}" if defects else " | brak defektów krytycznych"
    fb_txt = " [fallback słabszy 1-kill]" if item.get("fallback_mediocre") else ""
    return (
        f"{champ} {act}{fb_txt}: hype={hype}, watch={watch}, qa={qa}{extra_txt}, "
        f"klatka0={'OK' if item.get('frame0_hook_legible', True) else 'NIE'} "
        f"({item.get('kill_overlay_zone', '?')}){defect_txt}."
    )


def _compute_item_final_score(item: Dict[str, Any]) -> float:
    """Oblicza finalną punktację shorta (0..100) z karami za defekty oglądalności."""
    hype = float(item.get("hype_score") or 0.0)
    watch = float(item.get("watchability_score") or 0.0)
    qa = float(item.get("qa_score") or 0.0)
    defects = list(item.get("defects") or [])
    has_crit = bool(item.get("has_critical_defect"))

    raw_final = round(0.35 * hype + 0.50 * watch + 0.15 * qa, 1)
    if item.get("champion_mismatch"):
        raw_final -= 6.0
    if "dead_gap_gt_3.8s" in defects:
        raw_final -= 4.5
    if "moderate_edge_clipping" in defects:
        raw_final -= 3.5
    if "camera_jump_gt_220px" in defects:
        cam_step = float(item.get("camera_peak_step_px") or 0.0)
        raw_final -= 4.5 if cam_step >= 450.0 else 3.0
    if "slow_intro_gt_4.8s" in defects:
        raw_final -= 4.0
    elif "slow_intro_gt_3.5s" in defects:
        raw_final -= 2.0
    if "duration_too_long_gt_16.5s" in defects:
        raw_final -= 2.0
    if "center_blocking_overlay" in defects:
        raw_final -= 3.0

    vis_r = float(item.get("player_visible_ratio") if item.get("player_visible_ratio") is not None else 1.0)
    if 0.72 <= vis_r < 0.76:
        raw_final -= 2.0

    if has_crit:
        raw_final = min(raw_final, 65.0)
    if (0.0 < vis_r < 0.55) or float(item.get("player_edge_clip_ratio") or 0.0) > 0.35:
        raw_final = min(raw_final, 68.0)
    elif 0.0 < vis_r < 0.72:
        raw_final = min(raw_final, 74.0)
    if item.get("fallback_mediocre"):
        raw_final = min(raw_final, 64.0)
    return round(max(0.0, min(100.0, raw_final)), 1)


def _compute_publish_block_reasons(item: Dict[str, Any]) -> List[str]:
    """Wyznacza twardą listę powodów blokady publikacji na podstawie metryk wideo i final_score."""
    block_reasons: List[str] = []
    if bool(item.get("has_critical_defect")):
        block_reasons.append("has_critical_defect")
    gap_v = item.get("longest_gap_out_sec")
    if isinstance(gap_v, (int, float)) and float(gap_v) >= 5.5:
        block_reasons.append(f"dead_gap_{float(gap_v):.1f}s>=5.5s")
    fk_v = item.get("first_kill_out_sec")
    if isinstance(fk_v, (int, float)) and float(fk_v) > 4.0:
        block_reasons.append(f"slow_intro_{float(fk_v):.1f}s>4.0s")
    vr_v = item.get("player_visible_ratio")
    if isinstance(vr_v, (int, float)) and 0.0 < float(vr_v) < 0.72:
        block_reasons.append(f"low_visibility_{float(vr_v):.2f}<0.72")
    dur_v = item.get("duration_s")
    act_low = str(item.get("action_type") or "").lower().strip()
    min_pub_dur = 8.9 if act_low in ("double", "solo_bolo", "solo", "1v1", "clutch", "oneshot", "outplay") else 10.0
    if isinstance(dur_v, (int, float)) and float(dur_v) > 0.0:
        if float(dur_v) < min_pub_dur:
            block_reasons.append(f"too_short_{float(dur_v):.1f}s<{min_pub_dur:.1f}s")
        elif float(dur_v) > 17.0:
            block_reasons.append(f"too_long_{float(dur_v):.1f}s>17.0s")
    fs = float(item.get("final_score") or 0.0)
    if fs < 76.0:
        block_reasons.append(f"low_final_{fs:.1f}<76.0")
    if item.get("fallback_mediocre"):
        block_reasons.append("fallback_mediocre")
    return block_reasons


def rank_rendered_overnight_shorts(
    rendered_items: List[Dict[str, Any]],
    scan_stats: Dict[str, Any],
    use_local_ai: bool = True,
) -> Dict[str, Any]:
    """
    Szereguje wyrenderowane shorty (#1..#5) z twardym strażnikiem anty-sykofankcji (Sykofankcja 0).
    """
    valid_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []

    for it in rendered_items:
        item = dict(it)
        if not item.get("render_ok") or not item.get("output_path") or not Path(str(item["output_path"])).is_file():
            item["final_score"] = 0.0
            item["verdict"] = "RENDER_ERROR"
            item["has_critical_defect"] = True
            item["synapsa_comment_pl"] = f"Błąd renderowania: {item.get('error') or 'brak pliku .mp4'}."
            failed_items.append(item)
            continue

        item["defects"] = list(item.get("defects") or [])
        item["final_score"] = _compute_item_final_score(item)
        valid_items.append(item)

    valid_items.sort(
        key=lambda x: (
            not bool(x.get("has_critical_defect")),
            float(x.get("final_score", 0.0)),
            float(x.get("watchability_score", 0.0)),
            float(x.get("hype_score", 0.0)),
        ),
        reverse=True,
    )

    ai_resp: Optional[Dict[str, Any]] = None
    id_to_item: Dict[str, Dict[str, Any]] = {str(i): x for i, x in enumerate(valid_items, start=1)}
    item_to_id: Dict[int, str] = {id(x): str(i) for i, x in enumerate(valid_items, start=1)}
    if valid_items and use_local_ai:
        try:
            try:
                from lol_agent.synapsa_engine import generate_with_synapsa, is_synapsa_available
            except ImportError:
                from synapsa_engine import generate_with_synapsa, is_synapsa_available  # type: ignore

            if is_synapsa_available():
                compact_cands = [
                    {
                        "id": str(i),
                        "filename": x.get("output_filename"),
                        "champion_name": x.get("champion_name"),
                        "champion_mismatch": bool(x.get("champion_mismatch")),
                        "action_type": x.get("action_type"),
                        "event_tier": x.get("event_tier") or "",
                        "kill_count": x.get("kill_count"),
                        "duration_s": x.get("duration_s"),
                        "hype_score": x.get("hype_score"),
                        "watchability_score": x.get("watchability_score"),
                        "qa_score": x.get("qa_score"),
                        "final_score": x.get("final_score"),
                        "player_visible_ratio": x.get("player_visible_ratio"),
                        "player_edge_clip_ratio": x.get("player_edge_clip_ratio"),
                        "camera_peak_step_px": x.get("camera_peak_step_px"),
                        "longest_gap_out_sec": x.get("longest_gap_out_sec"),
                        "first_kill_out_sec": x.get("first_kill_out_sec"),
                        "black_end_frame": bool(x.get("black_end_frame")),
                        "frame0_hook_legible": bool(x.get("frame0_hook_legible", True)),
                        "audio_clip_gt_096": int(x.get("audio_clip_gt_096") or 0),
                        "defects": [d for d in (x.get("defects") or []) if d != "ig_needs_transcode_on_upload"],
                    }
                    for i, x in enumerate(valid_items, start=1)
                ]
                ai_resp = generate_with_synapsa(
                    "overnight_rank",
                    {"candidates": compact_cands, "scan_stats": {"qualified": scan_stats.get("qualified_count"), "rejected": scan_stats.get("rejected_count")}},
                    timeout=180,
                )
        except Exception:
            ai_resp = None

    objective_leader = valid_items[0] if valid_items else None
    chosen_leader = objective_leader
    guard_override = False
    rec_source = "synapsa_deterministic_judge"

    if ai_resp and valid_items:
        winner_id_raw = str(ai_resp.get("winner_id") or "").strip().lstrip("#")
        ai_fn = str(ai_resp.get("recommended_filename") or "").strip()
        by_fn = {str(x.get("output_filename")): x for x in valid_items}
        ai_pick = id_to_item.get(winner_id_raw) or by_fn.get(ai_fn)
        if ai_pick is not None and objective_leader is not None:
            gap = float(objective_leader["final_score"]) - float(ai_pick["final_score"])
            if ai_pick.get("has_critical_defect") or gap >= 8.0:
                guard_override = True
                chosen_leader = objective_leader
                rec_source = "synapsa_guard_override"
            else:
                chosen_leader = ai_pick
                rec_source = "synapsa_local_lora_judge"
                if chosen_leader is not objective_leader:
                    valid_items.remove(chosen_leader)
                    valid_items.insert(0, chosen_leader)

    ai_notes = ai_resp.get("notes_pl") if (ai_resp and isinstance(ai_resp.get("notes_pl"), dict)) else {}
    ai_per_short = ai_resp.get("per_short_pl") if (ai_resp and isinstance(ai_resp.get("per_short_pl"), dict)) else {}

    ranked_all: List[Dict[str, Any]] = []
    seen_ai_comments: set[str] = set()
    for idx, item in enumerate(valid_items, start=1):
        item["overnight_rank"] = idx
        fs = float(item.get("final_score") or 0.0)
        ws = float(item.get("watchability_score") or 0.0)
        crit = bool(item.get("has_critical_defect"))
        if idx == 1:
            item["verdict"] = "PICK_WINNER" if (fs >= 70.0 and ws >= 68.0 and not crit and not item.get("fallback_mediocre")) else "NEEDS_TWEAK"
        elif idx <= 3:
            item["verdict"] = "STRONG_ALT" if (fs >= 65.0 and ws >= 65.0 and not crit) else ("NEEDS_TWEAK" if fs >= 50.0 else "SKIP")
        elif fs >= 75.0 and ws >= 80.0 and not crit and not item.get("fallback_mediocre"):
            item["verdict"] = "STRONG_ALT"
        else:
            item["verdict"] = "NEEDS_TWEAK" if fs >= 50.0 else "SKIP"

        block_reasons = _compute_publish_block_reasons(item)
        item["publish_block_reasons"] = block_reasons
        item["publish_recommended"] = len(block_reasons) == 0

        orig_id = item_to_id.get(id(item), str(idx))
        raw_ai_comment = str(ai_notes.get(orig_id) or ai_per_short.get(str(item.get("output_filename") or ""), "") or "").strip()
        metrics_comment = _build_honest_short_comment_pl(item)
        has_digits = any(ch.isdigit() for ch in raw_ai_comment)
        norm_ai = raw_ai_comment.lower()
        is_dup_ai = bool(norm_ai and norm_ai in seen_ai_comments)
        note_clean = (not is_dup_ai) and _is_clean_consistent_polish_note(raw_ai_comment, item)
        if not guard_override and note_clean and len(raw_ai_comment) >= 38 and has_digits:
            item["synapsa_comment_pl"] = raw_ai_comment
            seen_ai_comments.add(norm_ai)
        elif not guard_override and note_clean and len(raw_ai_comment) >= 38:
            item["synapsa_comment_pl"] = f"{raw_ai_comment.rstrip('.')} — {metrics_comment}"
            seen_ai_comments.add(norm_ai)
        else:
            item["synapsa_comment_pl"] = metrics_comment
        ranked_all.append(item)

    for fail_it in failed_items:
        fail_it["overnight_rank"] = len(ranked_all) + 1
        fail_it["publish_recommended"] = False
        fail_it["publish_block_reasons"] = ["render_error"]
        ranked_all.append(fail_it)

    ai_summary = str((ai_resp or {}).get("summary_pl") or "").strip()
    if chosen_leader is not None:
        summary_ok = _is_clean_consistent_polish_note(ai_summary, chosen_leader) and len(ai_summary) >= 30
        if guard_override or not summary_ok:
            leader_fn = chosen_leader.get("output_filename")
            leader_ch = chosen_leader.get("champion_name") or "?"
            other_note = (
                f" Drugi: {valid_items[1].get('output_filename')} ({valid_items[1].get('champion_name', '?')}, final={valid_items[1].get('final_score')})."
                if len(valid_items) >= 2
                else ""
            )
            weak_note = ""
            if int(scan_stats.get("qualified_count") or 0) < int(len(valid_items)):
                weak_note = f" UWAGA: tylko {scan_stats.get('qualified_count')} klipy spełniły ostry próg hype (reszta to fallback)."
            mismatch_note = (
                f" Uwaga: klip #{1} ma bohatera {leader_ch} (poza {chosen_leader.get('requested_champion')})."
                if chosen_leader.get("champion_mismatch")
                else ""
            )
            summary_pl = (
                f"Rekomendacja #1: {leader_fn} ({leader_ch} {str(chosen_leader.get('action_type', '')).upper()}, "
                f"final={chosen_leader.get('final_score')}/100, hype={chosen_leader.get('hype_score')}, "
                f"watch={chosen_leader.get('watchability_score')}, qa={chosen_leader.get('qa_score')})."
                f"{mismatch_note}{other_note}{weak_note}"
            )
        else:
            summary_pl = ai_summary
    else:
        summary_pl = "Żaden short z tej paczki nie wyrenderował się poprawnie."

    return {
        "recommended_filename": chosen_leader.get("output_filename") if chosen_leader else None,
        "recommended_verdict": chosen_leader.get("verdict") if chosen_leader else None,
        "recommendation_source": rec_source,
        "guard_override": guard_override,
        "summary_pl": summary_pl,
        "items": ranked_all,
    }


def _build_batch_manifest(
    *,
    batch_id: str,
    status: str,
    champion_name: Optional[str],
    tier_filter: str,
    only_channel_champion: bool,
    preset: str,
    rank: str,
    scan_res: Dict[str, Any],
    started_at: str,
    finished_at: str,
    ranked_res: Dict[str, Any],
    summary_pl: str,
) -> Dict[str, Any]:
    """Buduje ujednolicony manifest paczki nocnej dla stanu `done` oraz `stopped`."""
    return {
        "batch_id": batch_id,
        "status": status,
        "auto_publish": False,
        "champion_name": champion_name,
        "tier_filter": tier_filter,
        "only_channel_champion": only_channel_champion,
        "montage_preset": preset,
        "rank": rank,
        "folder": scan_res.get("folder"),
        "started_at": started_at,
        "finished_at": finished_at,
        "scan_stats": {
            "total_clips_found": scan_res.get("total_clips_found", 0),
            "skipped_published": scan_res.get("skipped_published", 0),
            "skipped_dismissed": scan_res.get("skipped_dismissed", 0),
            "pruned_unaccepted_repeats": scan_res.get("pruned_unaccepted_repeats", 0),
            "pruned_clip_filenames": scan_res.get("pruned_clip_filenames") or [],
            "scanned_unpublished": scan_res.get("scanned_unpublished", 0),
            "qualified_count": scan_res.get("qualified_count", 0),
            "rejected_count": scan_res.get("rejected_count", 0),
            "rejection_breakdown": scan_res.get("rejection_breakdown") or {},
        },
        "recommended_filename": ranked_res.get("recommended_filename"),
        "recommended_verdict": ranked_res.get("recommended_verdict"),
        "recommendation_source": ranked_res.get("recommendation_source"),
        "guard_override": ranked_res.get("guard_override"),
        "summary_pl": summary_pl,
        "items": ranked_res.get("items") or [],
    }


def _persist_batch_manifest(manifest: Dict[str, Any]) -> str:
    OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
    bid = str(manifest.get("batch_id") or datetime.now().strftime("%Y%m%d_%H%M%S"))
    batch_file = OVERNIGHT_DIR / f"batch_{bid}.json"
    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    _atomic_write_text(batch_file, text)
    _atomic_write_text(LATEST_BATCH_FILE, text)
    return str(batch_file)


def _thumb_search_dirs(output_path: Optional[str] = None) -> List[Path]:
    """Zwraca listę katalogów, w których mogą znajdować się miniaturki 9:16."""
    dirs: List[Path] = []
    if output_path:
        try:
            dirs.append(Path(str(output_path)).parent)
        except Exception as exc:
            print(f"[Overnight] [WARN] Niepoprawna ścieżka output_path ({output_path}): {exc}")
    try:
        try:
            from lol_agent.api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
        except ImportError:
            from api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR  # type: ignore
        dirs.extend([Path(LOL_TEMP_DIR), Path(LOL_OUTPUT_DIR)])
    except Exception:
        pass
    dirs.extend([LOL_AGENT_DIR / "lol_temp", LOL_AGENT_DIR / "thumbnails"])
    unique: List[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _resolve_thumbnail_for_output(
    output_filename: str,
    existing_thumb_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Zwraca (pełna ścieżka, nazwa pliku) istniejącej miniaturki dla danego shorta lub (None, None)."""
    if existing_thumb_path:
        p = Path(str(existing_thumb_path))
        if p.is_file():
            return str(p), p.name
    safe_name = Path(str(output_filename or "")).name
    if not safe_name:
        return None, None
    stem = Path(safe_name).stem
    thumb_name = f"{stem}_thumb.jpg"
    for d in _thumb_search_dirs(output_path):
        cand = d / thumb_name
        if cand.is_file():
            return str(cand), cand.name
    return None, None


def update_overnight_item_thumbnail(output_filename: str, thumb_path: str) -> bool:
    """Aktualizuje ścieżkę i nazwę miniaturki w manifeście paczki nocnej (`latest_batch.json` + `batch_*.json`)."""
    safe_video = Path(str(output_filename or "")).name
    tp = Path(str(thumb_path or ""))
    if not safe_video or not tp.name:
        return False
    tp_str = str(tp)
    tp_name = tp.name

    def _patch_manifest(mf_path: Path) -> Tuple[bool, Optional[str]]:
        if not mf_path.is_file():
            return False, None
        try:
            data = json.loads(mf_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[Overnight] [WARN] Błąd odczytu manifestu {mf_path}: {exc}")
            return False, None
        if not isinstance(data, dict):
            return False, None
        changed = False
        for it in (data.get("items") or []):
            if not isinstance(it, dict):
                continue
            if Path(str(it.get("output_filename") or "")).name == safe_video:
                it["thumbnail_path"] = tp_str
                it["thumbnail_filename"] = tp_name
                changed = True
        if changed:
            _atomic_write_text(mf_path, json.dumps(data, indent=2, ensure_ascii=False))
        return changed, data.get("batch_id")

    with _MANIFEST_LOCK:
        updated, batch_id = _patch_manifest(LATEST_BATCH_FILE)
        if batch_id:
            _patch_manifest(OVERNIGHT_DIR / f"batch_{batch_id}.json")
        return updated


def load_latest_overnight_batch() -> Optional[Dict[str, Any]]:
    """Odczytuje ostatni zapisany manifest paczki nocnej lub None (z uzupełnieniem miniaturek)."""
    if not LATEST_BATCH_FILE.is_file():
        return None
    try:
        data = json.loads(LATEST_BATCH_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        for it in (data.get("items") or []):
            if not isinstance(it, dict):
                continue
            t_path, t_name = _resolve_thumbnail_for_output(
                str(it.get("output_filename") or ""),
                it.get("thumbnail_path"),
                output_path=it.get("output_path"),
            )
            it["thumbnail_path"] = t_path
            it["thumbnail_filename"] = t_name
        return data
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd ładowania LATEST_BATCH_FILE ({LATEST_BATCH_FILE}): {exc}")
        return None


def list_overnight_batches(limit: int = 10) -> List[Dict[str, Any]]:
    """Zwraca listę ostatnich paczek nocnych z katalogu `overnight_batches/`."""
    if not OVERNIGHT_DIR.exists():
        return []
    files = sorted(OVERNIGHT_DIR.glob("batch_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for p in files[:max(1, int(limit))]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                out.append(d)
        except Exception as exc:
            print(f"[Overnight] [WARN] Pominięto uszkodzony plik batch {p.name}: {exc}")
            continue
    return out


def _save_single_output_meta(item: Dict[str, Any], batch_id: str, out_fn: Optional[str] = None, style_override: Optional[str] = None) -> None:
    try:
        from lol_agent.api.helpers import _save_meta
    except ImportError:
        from api.helpers import _save_meta  # type: ignore

    target_fn = out_fn or item.get("output_filename")
    if not target_fn:
        return
    try:
        _save_meta(str(target_fn), {
            "source_path": item.get("source_path") or "",
            "champion_name": item.get("champion_name") or "Katarina",
            "action_type": item.get("action_type") or "outplay",
            "rank": item.get("rank") or "Master",
            "clip_start": item.get("clip_start"),
            "clip_end": item.get("clip_end"),
            "peak_moment": item.get("peak_moment"),
            "thumbnail_path": item.get("thumbnail_path") or "",
            "thumbnail_filename": item.get("thumbnail_filename") or "",
            "title": item.get("title") or "",
            "title_variant_b": item.get("title_variant_b") or "",
            "description": item.get("description") or "",
            "pinned_comment": item.get("pinned_comment") or "",
            "overnight_batch_id": batch_id,
            "overnight_rank": item.get("overnight_rank"),
            "overnight_verdict": item.get("verdict"),
            "montage_style": style_override or item.get("montage_style") or "",
            "fallback_triggered": bool(item.get("fallback_triggered", False)),
            "fallback_from_style": item.get("fallback_from_style"),
            "hype_score": item.get("hype_score"),
            "watchability_score": item.get("watchability_score"),
            "final_score": item.get("final_score"),
            "synapsa_comment_pl": item.get("synapsa_comment_pl"),
        })
    except Exception as exc:
        print(f"[Overnight] [WARN] Błąd zapisu meta ({target_fn}): {exc}")


def _annotate_output_metas(ranked_items: List[Dict[str, Any]], batch_id: str) -> None:
    for it in ranked_items:
        if it.get("output_filename") and it.get("render_ok"):
            _save_single_output_meta(it, batch_id=batch_id)
        for alt in (it.get("alternate_renders") or []):
            alt_fn = alt.get("output_filename")
            if alt_fn and alt.get("render_ok", True) and alt_fn != it.get("output_filename"):
                alt_payload = dict(it)
                alt_payload.update({
                    "output_filename": alt_fn,
                    "thumbnail_path": alt.get("thumbnail_path") or it.get("thumbnail_path"),
                    "thumbnail_filename": alt.get("thumbnail_filename") or it.get("thumbnail_filename"),
                    "title": alt.get("title") or it.get("title"),
                    "watchability_score": alt.get("watchability_score", it.get("watchability_score")),
                    "final_score": alt.get("final_score", it.get("final_score")),
                    "synapsa_comment_pl": alt.get("synapsa_comment_pl") or it.get("synapsa_comment_pl"),
                })
                _save_single_output_meta(
                    alt_payload,
                    batch_id=batch_id,
                    out_fn=str(alt_fn),
                    style_override=str(alt.get("montage_style") or ""),
                )


def _probe_ig_compliance(mp4_path: str) -> Dict[str, Any]:
    try:
        try:
            from lol_agent.instagram_publisher import _probe_video_for_ig, _needs_ig_transcode
        except ImportError:
            from instagram_publisher import _probe_video_for_ig, _needs_ig_transcode  # type: ignore
        vp = Path(mp4_path)
        size_bytes = vp.stat().st_size
        probe = _probe_video_for_ig(vp)
        need_tx, reasons = _needs_ig_transcode(probe, size_bytes)
        return {
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "bitrate_mbps": round(float(probe.get("video_bitrate") or 0) / 1_000_000.0, 2),
            "audio_kbps": round(float(probe.get("audio_bitrate") or 0) / 1000.0, 1),
            "audio_sr": int(probe.get("audio_sample_rate") or 0),
            "r_fps": round(float(probe.get("r_fps") or 0.0), 2),
            "avg_fps": round(float(probe.get("avg_fps") or 0.0), 2),
            "ig_ready": not need_tx,
            "ig_issues": reasons,
        }
    except Exception:
        return {"ig_ready": True, "ig_issues": []}


def _normalize_montage_preset(montage_preset: Optional[str]) -> str:
    val = str(montage_preset or "compare_all_3").strip().lower()
    return val if val in MONTAGE_PRESETS else "compare_all_3"


def _choose_primary_and_fallback_styles(
    cand: Dict[str, Any],
    montage_preset: str = "compare_all_3",
    directive: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Dobiera główny i kontrastowy styl montażu dla klipu wg presetu z Opcji Nocnej."""
    preset = _normalize_montage_preset(montage_preset)
    if preset == "arena_wide":
        return "ARENA_WIDE", None
    if preset == "beat_velocity":
        return "BEAT_VELOCITY", None
    if preset == "story_raw_pov":
        return "STORY_RAW_POV", None
    if preset == "compare_all_3":
        return "ARENA_WIDE", None

    act = str(cand.get("action_type") or "").strip().lower()
    kill_span = float(cand.get("kill_span_s") or 0.0)
    est_k0 = cand.get("est_first_kill_s")
    est_k1 = cand.get("est_last_kill_s")
    if kill_span <= 0.0 and est_k0 is not None and est_k1 is not None:
        try:
            kill_span = max(0.0, float(est_k1) - float(est_k0))
        except (TypeError, ValueError):
            kill_span = 0.0
    total_kills = int(cand.get("total_kills_in_clip") or cand.get("kill_count") or 0)

    if (
        act in ("triple", "quadrakill", "pentakill", "objective_steal")
        or bool(cand.get("objective_secured"))
        or total_kills >= 3
        or kill_span > 5.2
    ):
        fb = "STORY_RAW_POV" if kill_span > 6.0 else "BEAT_VELOCITY"
        return "ARENA_WIDE", fb

    if directive is None and not os.environ.get("PYTEST_CURRENT_TEST"):
        directive_data = _load_learning_directive_safe()
    else:
        directive_data = directive if isinstance(directive, dict) else {}

    m_dim = (((directive_data.get("recipe_experiments") or {}).get("dimensions") or {}).get("montage_style") or {})
    if bool(m_dim.get("reliable")):
        winner = str(m_dim.get("winner") or "").upper().strip()
        if winner in VIRAL_STYLE_ORDER:
            fb = "ARENA_WIDE" if winner != "ARENA_WIDE" else "BEAT_VELOCITY"
            return winner, fb

    return "BEAT_VELOCITY", "ARENA_WIDE"


def _pick_dynamic_fallback_style(
    primary_style: str,
    default_fallback: Optional[str],
    item: Dict[str, Any],
) -> str:
    defects = {str(d) for d in (item.get("defects") or [])}
    blocks = " ".join(str(b) for b in (item.get("publish_block_reasons") or []))
    if (
        "dead_gap_gt_3.8s" in defects
        or "dead_gap_" in blocks
        or "slow_intro_gt_4.8s" in defects
        or "duration_too_long_gt_16.5s" in defects
        or "too_long_" in blocks
    ) and primary_style != "STORY_RAW_POV":
        return "STORY_RAW_POV"
    if (
        "camera_jump_gt_220px" in defects
        or "low_visibility_" in blocks
        or "moderate_edge_clipping" in defects
    ) and primary_style != "ARENA_WIDE":
        return "ARENA_WIDE"
    if default_fallback and default_fallback != primary_style:
        return default_fallback
    return "ARENA_WIDE" if primary_style != "ARENA_WIDE" else "BEAT_VELOCITY"


def _needs_style_fallback(item: Dict[str, Any]) -> bool:
    if not item.get("render_ok"):
        return True
    if bool(item.get("has_critical_defect")):
        return True
    if not bool(item.get("publish_recommended", False)):
        return True
    defects = {str(d) for d in (item.get("defects") or [])}
    if defects & {"camera_jump_gt_220px", "dead_gap_gt_3.8s", "slow_intro_gt_4.8s", "moderate_edge_clipping"}:
        return True
    blocks = " ".join(str(b) for b in (item.get("publish_block_reasons") or []))
    if any(k in blocks for k in ("low_visibility_", "too_short_", "too_long_", "slow_intro_", "dead_gap_")):
        return True
    if float(item.get("watchability_score") or 0.0) < 76.0:
        return True
    if float(item.get("final_score") or 0.0) < 76.0:
        return True
    return False


def _variant_quality_key(item: Dict[str, Any]) -> Tuple[int, int, int, float, float]:
    return (
        1 if item.get("render_ok") else 0,
        1 if item.get("publish_recommended") else 0,
        0 if item.get("has_critical_defect") else 1,
        float(item.get("final_score") or 0.0),
        float(item.get("watchability_score") or 0.0),
    )


def _summarize_variant(item: Dict[str, Any], is_selected: bool = False) -> Dict[str, Any]:
    out_p = item.get("output_path")
    file_exists = bool(out_p and Path(str(out_p)).is_file())
    return {
        "montage_style": str(item.get("montage_style") or ""),
        "output_filename": str(item.get("output_filename") or ""),
        "output_path": out_p,
        "thumbnail_path": item.get("thumbnail_path"),
        "thumbnail_filename": item.get("thumbnail_filename"),
        "title": item.get("title") or "",
        "hook_text": item.get("hook_text") or "",
        "duration_s": item.get("duration_s"),
        "final_score": item.get("final_score"),
        "watchability_score": item.get("watchability_score"),
        "qa_score": item.get("qa_score"),
        "camera_peak_step_px": item.get("camera_peak_step_px"),
        "first_kill_out_sec": item.get("first_kill_out_sec"),
        "longest_gap_out_sec": item.get("longest_gap_out_sec"),
        "player_visible_ratio": item.get("player_visible_ratio"),
        "player_edge_clip_ratio": item.get("player_edge_clip_ratio"),
        "has_critical_defect": bool(item.get("has_critical_defect")),
        "publish_recommended": bool(item.get("publish_recommended", False)),
        "publish_block_reasons": list(item.get("publish_block_reasons") or []),
        "defects": list(item.get("defects") or []),
        "synapsa_comment_pl": item.get("synapsa_comment_pl") or _build_honest_short_comment_pl(item),
        "render_ok": bool(item.get("render_ok")),
        "file_exists": file_exists,
        "is_selected": bool(is_selected),
    }


def _normalize_title_key(title: str) -> str:
    txt = re.sub(r"#\S+", "", str(title or ""))
    txt = re.sub(r"[^\w\s]", "", txt, flags=re.UNICODE)
    return re.sub(r"\s+", " ", txt).strip().lower()


def _pick_unique_batch_hook(cand: Dict[str, Any], used_hooks: set[str]) -> str:
    champ = str(cand.get("champion") or "KATARINA").upper().strip() or "KATARINA"
    act = str(cand.get("action_type") or "outplay").lower().strip()
    raw_hk = str(cand.get("hook_text") or "").strip()
    up_hk = " ".join(raw_hk.upper().split())
    is_spoiler = up_hk.startswith(("DOUBLE KILL - ", "TRIPLE KILL - ", "QUADRAKILL - ", "PENTAKILL - "))
    if up_hk and not is_spoiler and up_hk not in used_hooks:
        used_hooks.add(up_hk)
        return raw_hk

    pools: Dict[str, List[str]] = {
        "pentakill": ["WAIT FOR THE FIFTH RESET", "NEVER GROUP VS KATARINA", "5V1 AND NO SURVIVORS", "HOW FAST CAN HP DROP?", "THEY THOUGHT 5V1 WAS FREE"],
        "quadrakill": ["WAIT FOR THE FOURTH RESET", "NEVER STACK VS KATARINA", "4V1 INSTANT TURNAROUND", "WATCH THE RESET CHAIN", "THEY THOUGHT 4V1 WAS SAFE"],
        "triple": ["WAIT FOR THE THIRD RESET", "THEY WALKED INTO DAGGERS", "NEVER CHASE KATARINA", "WATCH THIS COUNTER-ENGAGE", "3V1 GREED PUNISHED"],
        "double": ["WAIT FOR THE SECOND RESET", f"NEVER CHASE {champ}", "THEY THOUGHT 2V1 WAS FREE", "WATCH THE DAGGER ANGLE", "GREEDY DIVE INSTANT REGRET", "BLINK AND BOTH VANISH"],
        "clutch": ["HOW DID SHE SURVIVE?!", "THEY CELEBRATED TOO EARLY", "1 SECOND FROM DEATH", "NO WAY SHE FLIPS THIS"],
        "solo_bolo": ["WHO WINS THIS 1V1?", "EGO CHALLENGE ACCEPTED", "WATCH THE DODGE TIMING", "PURE SKILL CHECK"],
    }
    cands = list(pools.get(act, ["WATCH THE LAST 3 SECONDS", "THEY THOUGHT THEY HAD ME", "ONE MISTAKE COST EVERYTHING", "ZERO HESITATION FLIP"]))
    for h in cands:
        nh = " ".join(h.upper().split())
        if nh not in used_hooks:
            used_hooks.add(nh)
            return h
    fallback_h = cands[len(used_hooks) % len(cands)]
    used_hooks.add(" ".join(fallback_h.upper().split()))
    return fallback_h


def _ensure_unique_batch_title(
    items: List[Dict[str, Any]],
    used_titles: set[str],
    champion: str,
    action_type: str,
    rank: str,
) -> None:
    if not items:
        return
    base_title = str(items[0].get("title") or "").strip()
    base_key = _normalize_title_key(base_title)
    chosen = base_title

    if not base_key or base_key in used_titles:
        alt_b = str(items[0].get("title_variant_b") or "").strip()
        if alt_b and _normalize_title_key(alt_b) not in used_titles:
            chosen = alt_b
        else:
            try:
                try:
                    from lol_agent.lol_metadata_generator import generate_channel_title, _format_final_title
                except ImportError:
                    from lol_metadata_generator import generate_channel_title, _format_final_title  # type: ignore
                found = None
                for _attempt in range(12):
                    cand_t = generate_channel_title(
                        action_type=action_type,
                        champion=champion,
                        rank=rank,
                        variant="A" if _attempt % 2 == 0 else "B",
                        exclude_title=chosen,
                    )
                    if _normalize_title_key(cand_t) not in used_titles:
                        found = cand_t
                        break
                if found:
                    chosen = found
                else:
                    # Gwarancja braku duplikatu nawet gdy wyczerpano pulę szablonów
                    extra_pool = [
                        f"Every Dagger Timed To Perfection ⚡ {champion} #shorts #leagueoflegends #lol",
                        f"Blink Once And The Fight Is Over 💀 {champion} #shorts #leagueoflegends #lol",
                        f"They Punished Themselves Stepping Up 🔥 {champion} #shorts #leagueoflegends #lol",
                        f"Instant Turnaround On {champion} ⚡ Unreactable #shorts #leagueoflegends #lol",
                        f"Zero Room To Breathe Against {champion} 💀 #shorts #leagueoflegends #lol",
                    ]
                    for ep in extra_pool:
                        if _normalize_title_key(ep) not in used_titles:
                            chosen = _format_final_title(ep)
                            break
            except Exception:
                pass

    chosen_key = _normalize_title_key(chosen)
    if chosen_key:
        used_titles.add(chosen_key)
    for it in items:
        it["title"] = chosen


def _render_and_inspect_candidate(
    pipeline_runner: Any,
    inspect_rendered_short: Callable[[str], Dict[str, Any]],
    cand: Dict[str, Any],
    out_filename: str,
    candidate_rank: int,
    requested_champion: str,
    rank: str,
    montage_style: str,
    emit_log: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Renderuje jeden wariant stylu dla kandydata i od razu wykonuje pełną inspekcję oglądalności + IG."""
    safe_act = re.sub(r"[^a-z0-9_]+", "", str(cand.get("action_type") or "outplay").lower()) or "outplay"

    with pipeline_runner._lock:
        pipeline_runner._cancel_event.clear()
        pipeline_runner._job_queue.clear()

    combat_segs = None
    if safe_act != "solo_bolo" and cand.get("combat_segments"):
        combat_segs = [(float(s[0]), float(s[1])) for s in cand["combat_segments"]]

    cand_champ = str(cand.get("champion") or "").strip()
    if cand_champ and str(cand.get("event_source") or "").startswith("outplayed_"):
        detected_champ = cand_champ
    else:
        detected_champ = requested_champion
        try:
            try:
                from lol_agent.lol_screen_inspector import detect_champion_local
            except ImportError:
                from lol_screen_inspector import detect_champion_local  # type: ignore
            if cand.get("path") and Path(str(cand["path"])).is_file():
                detected_champ = detect_champion_local(str(cand["path"]), default_champion=requested_champion) or requested_champion
        except Exception:
            detected_champ = requested_champion
    champ_mismatch = bool(requested_champion and detected_champ and detected_champ.lower() != requested_champion.lower())

    safe_hook = str(cand.get("hook_text") or "").strip()
    if not safe_hook or (safe_act in ("triple", "quadrakill", "pentakill") and "DOUBLE" in safe_hook.upper()):
        if safe_act == "triple":
            safe_hook = "TRIPLE KILL - 3 DOWN"
        elif safe_act == "quadrakill":
            safe_hook = "QUADRAKILL - ONE MORE"
        elif safe_act == "pentakill":
            safe_hook = "PENTAKILL WIPE"

    run_exc_msg: Optional[str] = None
    try:
        pipeline_runner._run_pipeline(
            source_path=str(cand["path"]),
            clip_start=float(cand.get("clip_start") or 0.0),
            clip_end=float(cand.get("clip_end") or 15.0),
            action_type=str(cand.get("action_type") or "outplay"),
            champion_name=detected_champ,
            rank=rank,
            peak_moment=float(cand.get("peak_moment") or 8.0),
            hook_text=safe_hook,
            output_filename=out_filename,
            use_speed_ramp=True,
            use_zoom_punch=True,
            use_smart_camera=True,
            notify_token=None,
            combat_segments=combat_segs,
            game_type="lol",
            montage_style_override=montage_style,
        )
    except Exception as run_err:
        run_exc_msg = str(run_err)
        if emit_log:
            emit_log(f"Błąd renderu #{candidate_rank} [{montage_style}] ({cand.get('filename')}): {run_exc_msg}")

    p_state = pipeline_runner.get_state()
    out_path = p_state.get("output_path")
    render_ok = (not run_exc_msg) and (p_state.get("status") == "done") and bool(out_path) and Path(str(out_path)).is_file()
    resolved_out_name = Path(str(out_path)).name if render_ok else out_filename

    thumb_path, thumb_filename = _resolve_thumbnail_for_output(
        resolved_out_name,
        p_state.get("thumbnail_path") if not run_exc_msg else None,
        output_path=str(out_path) if out_path else None,
    )
    if render_ok and out_path and not thumb_path:
        try:
            try:
                from lol_agent.lol_thumbnail import generate_thumbnail as _gen_thumb
            except ImportError:
                from lol_thumbnail import generate_thumbnail as _gen_thumb  # type: ignore
            eff_start = float(p_state.get("clip_start") if p_state.get("clip_start") is not None else (cand.get("clip_start") or 0.0))
            eff_end = float(p_state.get("clip_end") if p_state.get("clip_end") is not None else (cand.get("clip_end") or 15.0))
            eff_peak = float(cand.get("peak_moment") or eff_end)
            eff_dur = max(1.0, eff_end - eff_start)
            safe_peak_rel = min(max(0.2, eff_peak - eff_start), max(0.3, eff_dur - 1.0))
            fallback_thumb_out = str(Path(str(out_path)).with_name(f"{Path(str(out_path)).stem}_thumb.jpg"))
            act_lbl = str(p_state.get("action_type") or cand.get("action_type") or "outplay").upper().replace("_", " ")
            _gen_thumb(
                video_path=str(out_path),
                peak_moment=safe_peak_rel,
                action_label=act_lbl,
                champion_name=detected_champ,
                output_path=fallback_thumb_out,
                source_clip_path=str(cand.get("path")) if cand.get("path") and os.path.isfile(str(cand.get("path"))) else None,
                source_peak_moment=float(eff_peak),
            )
            thumb_path, thumb_filename = _resolve_thumbnail_for_output(
                resolved_out_name,
                fallback_thumb_out,
                output_path=str(out_path),
            )
        except Exception as thumb_err:
            if emit_log:
                emit_log(f"Miniaturka fallback warning (#{candidate_rank}): {thumb_err}")

    item_record: Dict[str, Any] = {
        "candidate_rank": candidate_rank,
        "source_filename": cand.get("filename"),
        "source_path": cand.get("path"),
        "output_filename": resolved_out_name,
        "output_path": out_path if not run_exc_msg else None,
        "thumbnail_path": thumb_path,
        "thumbnail_filename": thumb_filename,
        "champion_name": detected_champ,
        "requested_champion": requested_champion,
        "champion_mismatch": champ_mismatch,
        "rank": rank,
        "action_type": p_state.get("action_type") or cand.get("action_type"),
        "montage_style": montage_style,
        "kill_count": cand.get("kill_count"),
        "kill_span_s": cand.get("kill_span_s"),
        "objective_secured": cand.get("objective_secured"),
        "is_clutch_1hp": cand.get("is_clutch_1hp"),
        "min_hp_percentage": cand.get("min_hp_percentage"),
        "is_favorite": bool(cand.get("is_favorite", False)),
        "event_tier": cand.get("event_tier") or "",
        "event_source": cand.get("event_source") or "none",
        "best_event_time_s": cand.get("best_event_time_s"),
        "est_first_kill_s": cand.get("est_first_kill_s"),
        "est_last_kill_s": cand.get("est_last_kill_s"),
        "total_kills_in_clip": cand.get("total_kills_in_clip"),
        "match_folder": cand.get("match_folder") or "",
        "match_date": cand.get("match_date") or "",
        "clip_base_key": cand.get("clip_base_key") or "",
        "match_kda": cand.get("match_kda") or "",
        "clip_start": p_state.get("clip_start") if p_state.get("clip_start") is not None else cand.get("clip_start"),
        "clip_end": p_state.get("clip_end") if p_state.get("clip_end") is not None else cand.get("clip_end"),
        "peak_moment": cand.get("peak_moment"),
        "title": p_state.get("title") or "",
        "title_variant_b": p_state.get("title_variant_b") or "",
        "description": p_state.get("description") or "",
        "pinned_comment": p_state.get("pinned_comment") or "",
        "hype_score": cand.get("hype_score"),
        "fallback_mediocre": bool(cand.get("fallback_mediocre")),
        "qa_status": p_state.get("qa_status"),
        "qa_score": p_state.get("qa_score") or 0,
        "render_ok": render_ok,
        "error": run_exc_msg or p_state.get("error"),
        "fallback_triggered": False,
        "fallback_from_style": None,
        "alternate_renders": [],
    }

    if render_ok and out_path:
        try:
            insp = dict(inspect_rendered_short(str(out_path)) or {})
            out_meta: Dict[str, Any] = {}
            meta_fp = Path(str(out_path)).with_suffix(".meta.json")
            if meta_fp.is_file():
                try:
                    out_meta = json.loads(meta_fp.read_text(encoding="utf-8"))
                except Exception:
                    out_meta = {}
            recipe_fp = Path(str(out_path)).with_suffix(".recipe.json")
            recipe_style = ""
            if recipe_fp.is_file():
                try:
                    recipe_style = str((json.loads(recipe_fp.read_text(encoding="utf-8")) or {}).get("montage_style") or "").strip()
                except Exception:
                    recipe_style = ""
            resolved_style = str(out_meta.get("montage_style") or recipe_style or montage_style or "").strip()
            if resolved_style:
                item_record["montage_style"] = resolved_style

            qa_det = out_meta.get("qa_details") if isinstance(out_meta.get("qa_details"), dict) else {}
            rg_meas = ((qa_det.get("recipe_gate") or {}).get("measured") or {}) if isinstance(qa_det, dict) else {}
            qar_checks = ((qa_det.get("qa_after_render") or {}).get("checks") or {}) if isinstance(qa_det, dict) else {}

            if insp.get("longest_gap_out_sec") is None and rg_meas.get("longest_gap_out_sec") is not None:
                insp["longest_gap_out_sec"] = rg_meas.get("longest_gap_out_sec")
            if insp.get("camera_peak_step_px") is None:
                cam_vel = (qar_checks.get("camera_velocity") or {}).get("peak_velocity_px")
                insp["camera_peak_step_px"] = (
                    cam_vel if cam_vel is not None else rg_meas.get("camera_peak_step_px")
                )

            raw_kills_out = (qar_checks.get("kill_timing") or {}).get("kills") or []
            kill_timestamps_out: List[float] = []
            for kr in raw_kills_out:
                if isinstance(kr, (list, tuple)) and len(kr) >= 1:
                    try:
                        kill_timestamps_out.append(round(float(kr[0]), 2))
                    except (TypeError, ValueError):
                        pass

            if insp.get("longest_gap_out_sec") is not None:
                item_record["longest_gap_out_sec"] = float(insp["longest_gap_out_sec"])
            if insp.get("camera_peak_step_px") is not None:
                item_record["camera_peak_step_px"] = float(insp["camera_peak_step_px"])
            item_record["kill_timestamps_out"] = kill_timestamps_out

            ig_info = _probe_ig_compliance(str(out_path))
            defects, has_crit = _extract_defects(insp, bool(ig_info.get("ig_ready", True)), item=item_record)
            item_record.update({
                "watchability_score": float(insp.get("watchability_score") or 0.0),
                "frame0_hook_legible": bool(insp.get("frame0_hook_legible", True)),
                "kill_overlay_zone": insp.get("kill_overlay_zone"),
                "player_visible_ratio": insp.get("player_visible_ratio"),
                "player_edge_clip_ratio": insp.get("player_edge_clip_ratio"),
                "audio_clip_gt_096": int(insp.get("audio_clip_gt_096") or 0),
                "av_delta_s": float(insp.get("av_delta_s") or 0.0),
                "black_end_frame": bool(insp.get("black_end_frame")),
                "hook_is_generic": bool(insp.get("hook_is_generic")),
                "hook_text": insp.get("hook_text") or "",
                "duration_s": float(insp.get("video_dur_s") or 0.0),
                "camera_peak_step_px": insp.get("camera_peak_step_px"),
                "first_kill_out_sec": insp.get("first_kill_out_sec"),
                "longest_gap_out_sec": insp.get("longest_gap_out_sec"),
                "kill_timestamps_out": kill_timestamps_out,
                "ig_compliance": ig_info,
                "defects": defects,
                "has_critical_defect": has_crit,
            })
        except Exception as insp_err:
            print(f"[Overnight] [WARN] inspect_rendered_short nie powiodło się ({out_path}): {insp_err}")
            item_record["watchability_score"] = float(p_state.get("qa_score") or 0.0)
            item_record["defects"] = [f"inspect_error:{insp_err}"]
            item_record["has_critical_defect"] = False

    item_record["final_score"] = _compute_item_final_score(item_record)
    block_reasons = _compute_publish_block_reasons(item_record)
    item_record["publish_block_reasons"] = block_reasons
    item_record["publish_recommended"] = bool(render_ok and len(block_reasons) == 0)
    return item_record


def run_overnight_batch(
    folder: Optional[str] = None,
    top_n: int = 5,
    champion_name: str = "Katarina",
    rank: str = "Master",
    skip_published: bool = True,
    use_cache: bool = True,
    use_local_ai: bool = True,
    output_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    clear_cancel: bool = True,
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
    montage_preset: str = "compare_all_3",
) -> Dict[str, Any]:
    """
    Uruchamia pełny tryb nocny (synchronicznie):
      1. Skanuje cały folder i wybiera Top N najbardziej hypowanych klipów.
      2. Renderuje każdy lokalnie (ZERO auto-uploadu) w wybranym stylu lub z Auto-Fallback #2 / Compare 3.
      3. Inspekcjonuje każdy wyrenderowany short i zwraca rekomendację Synapsy #1..#N.
    """
    try:
        from lol_agent.api import pipeline_runner
        from lol_agent.synapsa_watchability_judge import inspect_rendered_short
    except ImportError:
        from api import pipeline_runner  # type: ignore
        from synapsa_watchability_judge import inspect_rendered_short  # type: ignore

    preset = _normalize_montage_preset(montage_preset)
    cur_pipe = pipeline_runner.get_state()
    if cur_pipe.get("status") == "running":
        raise RuntimeError("Inny render pipeline już trwa — poczekaj lub zatrzymaj przed uruchomieniem trybu nocnego.")

    if clear_cancel:
        _OVERNIGHT_CANCEL.clear()
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:5]
    started_at = _now_iso()

    def _emit_status(**fields: Any) -> None:
        _update_overnight_state(**fields)
        if progress_cb:
            progress_cb(get_overnight_status())

    _emit_status(
        status="scanning",
        batch_id=batch_id,
        phase="Skanowanie całego folderu nagrań...",
        progress=2,
        total_clips=0,
        scanned_clips=0,
        skipped_published=0,
        qualified_count=0,
        rejected_count=0,
        selected_count=0,
        rendered_count=0,
        current_clip="",
        recommended_filename=None,
        summary_pl="",
        error=None,
        started_at=started_at,
        finished_at=None,
        log=f"Start trybu nocnego (top_n={top_n}, preset={preset}, skip_published={skip_published}, folder={folder or 'Outplayed + Medal'})",
    )

    def _on_scan_prog(done: int, total: int, name: str) -> None:
        pct = 5 + int((done / max(1, total)) * 25)
        _emit_status(
            phase=f"Skanowanie {done}/{total}",
            progress=pct,
            scanned_clips=done,
            total_clips=total,
            current_clip=name,
        )

    scan_res = scan_and_rank_all_clips(
        folder=folder,
        top_n=top_n,
        skip_published=skip_published,
        use_cache=use_cache,
        max_workers=3,
        progress_cb=_on_scan_prog,
        cancel_event=_OVERNIGHT_CANCEL,
        champion_name=champion_name,
        tier_filter=tier_filter,
        only_channel_champion=only_channel_champion,
        skip_dismissed_repeats=True,
        auto_prune_unaccepted_repeats=bool(skip_published),
        max_unaccepted_renders=MAX_UNACCEPTED_OVERNIGHT_RENDERS,
    )
    if _OVERNIGHT_CANCEL.is_set():
        _emit_status(status="stopped", phase="Anulowano podczas skanu", finished_at=_now_iso())
        return {"batch_id": batch_id, "status": "stopped", "scan_stats": scan_res, "items": []}

    selected = list(scan_res.get("selected") or [])
    pruned_n = int(scan_res.get("pruned_unaccepted_repeats") or 0)
    pruned_note = f", usunięto {pruned_n} niezaakceptowanych powtórzeń 2x" if pruned_n > 0 else ""
    _emit_status(
        status="rendering",
        phase=f"Wybrano {len(selected)} kandydatów ({preset})",
        progress=32,
        total_clips=scan_res.get("total_clips_found", 0),
        skipped_published=scan_res.get("skipped_published", 0),
        qualified_count=scan_res.get("qualified_count", 0),
        rejected_count=scan_res.get("rejected_count", 0),
        selected_count=len(selected),
        log=(
            f"Skan gotowy: {scan_res['scanned_unpublished']} nieopublikowanych -> "
            f"{scan_res['qualified_count']} mocnych, {scan_res['rejected_count']} odrzuconych przeciętnych"
            f"{pruned_note}, wybrano {len(selected)} (preset={preset})."
        ),
    )

    def _log_render(msg: str) -> None:
        _emit_status(log=msg)

    rendered_items: List[Dict[str, Any]] = []
    used_batch_hooks: set[str] = set()
    used_batch_titles: set[str] = set()
    for idx, orig_cand in enumerate(selected, start=1):
        if _OVERNIGHT_CANCEL.is_set():
            _emit_status(status="stopped", phase=f"Przerwano przed renderem {idx}/{len(selected)}", finished_at=_now_iso())
            break

        cand = dict(orig_cand)
        cand["hook_text"] = _pick_unique_batch_hook(cand, used_batch_hooks)
        safe_act = re.sub(r"[^a-z0-9_]+", "", str(cand.get("action_type") or "outplay").lower()) or "outplay"
        # Nazwa MUSI zawierać "short", bo endpoint GET /outputs filtruje po "short" / "test".
        base_out = f"short_overnight_{batch_id}_r{idx}_{safe_act}"
        pct = 32 + int(((idx - 1) / max(1, len(selected))) * 58)

        if preset == "compare_all_3":
            variants: List[Dict[str, Any]] = []
            for s_idx, style_name in enumerate(VIRAL_STYLE_ORDER):
                if _OVERNIGHT_CANCEL.is_set():
                    break
                var_fn = f"{base_out}.mp4" if s_idx == 0 else f"{base_out}_alt_{style_name.lower()}.mp4"
                _emit_status(
                    status="rendering",
                    phase=f"Montaż {idx}/{len(selected)} [{style_name}]: {cand.get('filename')}",
                    progress=min(89, pct + s_idx * 3),
                    current_clip=str(cand.get("filename") or ""),
                    log=f"Compare A/B/C #{idx}/{len(selected)} [{style_name}]: {cand.get('filename')} -> {var_fn}",
                )
                v_item = _render_and_inspect_candidate(
                    pipeline_runner=pipeline_runner,
                    inspect_rendered_short=inspect_rendered_short,
                    cand=cand,
                    out_filename=var_fn,
                    candidate_rank=idx,
                    requested_champion=champion_name,
                    rank=rank,
                    montage_style=style_name,
                    emit_log=_log_render,
                )
                v_item["synapsa_comment_pl"] = _build_honest_short_comment_pl(v_item)
                variants.append(v_item)
                if _OVERNIGHT_CANCEL.is_set():
                    break
            if not variants:
                break
            _ensure_unique_batch_title(
                variants,
                used_batch_titles,
                champion=str(variants[0].get("champion_name") or champion_name or "Katarina"),
                action_type=str(variants[0].get("action_type") or cand.get("action_type") or "outplay"),
                rank=rank,
            )
            best_item = max(variants, key=_variant_quality_key)
            chosen_item = dict(best_item)
            chosen_item["alternate_renders"] = [
                _summarize_variant(v, is_selected=(v.get("output_filename") == chosen_item.get("output_filename")))
                for v in variants
            ]
            rendered_items.append(chosen_item)
            _emit_status(
                rendered_count=len(rendered_items),
                log=(
                    f"Ukończono #{idx} (Compare 3): winner={chosen_item.get('montage_style')}, "
                    f"final={chosen_item.get('final_score')}, watch={chosen_item.get('watchability_score')}"
                ),
            )
            continue

        primary_style, default_fb = _choose_primary_and_fallback_styles(cand, montage_preset=preset)
        primary_fn = f"{base_out}.mp4"
        _emit_status(
            status="rendering",
            phase=f"Montaż {idx}/{len(selected)} [{primary_style}]: {cand.get('filename')}",
            progress=pct,
            current_clip=str(cand.get("filename") or ""),
            log=f"Render #{idx}/{len(selected)} [{primary_style}]: {cand.get('filename')} -> {primary_fn} (hype={cand.get('hype_score')})",
        )
        item1 = _render_and_inspect_candidate(
            pipeline_runner=pipeline_runner,
            inspect_rendered_short=inspect_rendered_short,
            cand=cand,
            out_filename=primary_fn,
            candidate_rank=idx,
            requested_champion=champion_name,
            rank=rank,
            montage_style=primary_style,
            emit_log=_log_render,
        )
        item1["synapsa_comment_pl"] = _build_honest_short_comment_pl(item1)
        cand_items = [item1]
        chosen_item = dict(item1)

        if preset == "auto_fallback" and (not _OVERNIGHT_CANCEL.is_set()) and _needs_style_fallback(item1):
            fb_style = _pick_dynamic_fallback_style(primary_style, default_fb, item1)
            fb_fn = f"{base_out}_alt_{fb_style.lower()}.mp4"
            _emit_status(
                status="rendering",
                phase=f"Auto-Fallback {idx}/{len(selected)} [{primary_style} -> {fb_style}]: {cand.get('filename')}",
                progress=min(89, pct + 5),
                current_clip=str(cand.get("filename") or ""),
                log=(
                    f"Auto-Fallback #{idx}: {primary_style} (final={item1.get('final_score')}, "
                    f"watch={item1.get('watchability_score')}, pub={item1.get('publish_recommended')}) -> próba #{2}: {fb_style}"
                ),
            )
            item2 = _render_and_inspect_candidate(
                pipeline_runner=pipeline_runner,
                inspect_rendered_short=inspect_rendered_short,
                cand=cand,
                out_filename=fb_fn,
                candidate_rank=idx,
                requested_champion=champion_name,
                rank=rank,
                montage_style=fb_style,
                emit_log=_log_render,
            )
            item2["synapsa_comment_pl"] = _build_honest_short_comment_pl(item2)
            cand_items.append(item2)
            _ensure_unique_batch_title(
                cand_items,
                used_batch_titles,
                champion=str(item1.get("champion_name") or champion_name or "Katarina"),
                action_type=str(item1.get("action_type") or cand.get("action_type") or "outplay"),
                rank=rank,
            )
            if _variant_quality_key(item2) > _variant_quality_key(item1):
                chosen_item = dict(item2)
                chosen_item["fallback_triggered"] = True
                chosen_item["fallback_from_style"] = primary_style
                chosen_item["alternate_renders"] = [
                    _summarize_variant(item1, is_selected=False),
                    _summarize_variant(item2, is_selected=True),
                ]
            else:
                chosen_item = dict(item1)
                chosen_item["alternate_renders"] = [
                    _summarize_variant(item1, is_selected=True),
                    _summarize_variant(item2, is_selected=False),
                ]
        else:
            _ensure_unique_batch_title(
                cand_items,
                used_batch_titles,
                champion=str(item1.get("champion_name") or champion_name or "Katarina"),
                action_type=str(item1.get("action_type") or cand.get("action_type") or "outplay"),
                rank=rank,
            )
            chosen_item = dict(item1)

        rendered_items.append(chosen_item)
        _emit_status(
            rendered_count=len(rendered_items),
            log=(
                f"Ukończono #{idx} [{chosen_item.get('montage_style')}]: ok={chosen_item.get('render_ok')}, "
                f"qa={chosen_item.get('qa_score')}, watch={chosen_item.get('watchability_score')}, "
                f"fb={chosen_item.get('fallback_triggered')}"
            ),
        )

    if _OVERNIGHT_CANCEL.is_set():
        finished_at = _now_iso()
        if not any(x.get("render_ok") for x in rendered_items):
            _emit_status(status="stopped", phase="Przerwano przez użytkownika", finished_at=finished_at)
            return {"batch_id": batch_id, "status": "stopped", "scan_stats": scan_res, "items": rendered_items}

        ranked_res = rank_rendered_overnight_shorts(rendered_items, scan_res, use_local_ai=False)
        _annotate_output_metas(ranked_res["items"], batch_id=batch_id)
        stopped_summary = f"[Przerwano po {len(ranked_res['items'])} klipach] {ranked_res['summary_pl']}"
        manifest = _build_batch_manifest(
            batch_id=batch_id,
            status="stopped",
            champion_name=champion_name,
            tier_filter=tier_filter,
            only_channel_champion=only_channel_champion,
            preset=preset,
            rank=rank,
            scan_res=scan_res,
            started_at=started_at,
            finished_at=finished_at,
            ranked_res=ranked_res,
            summary_pl=stopped_summary,
        )
        if output_dir:
            _atomic_write_text(
                Path(output_dir) / f"overnight_manifest_{batch_id}.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
        _persist_batch_manifest(manifest)
        _emit_status(
            status="stopped",
            phase=f"Przerwano przez użytkownika (zapisano {len(ranked_res['items'])} gotowych)",
            rendered_count=sum(1 for x in ranked_res["items"] if x.get("render_ok")),
            recommended_filename=ranked_res["recommended_filename"],
            summary_pl=stopped_summary,
            finished_at=finished_at,
            log=stopped_summary,
        )
        return manifest

    _emit_status(
        status="evaluating",
        phase="Synapsa ocenia shorty i wybiera #1...",
        progress=94,
        log="Uruchamiam ocenę Synapsy (Sykofankcja 0) wszystkich wyrenderowanych shortów...",
    )

    ranked_res = rank_rendered_overnight_shorts(rendered_items, scan_res, use_local_ai=use_local_ai)
    _annotate_output_metas(ranked_res["items"], batch_id=batch_id)

    finished_at = _now_iso()
    manifest = _build_batch_manifest(
        batch_id=batch_id,
        status="done",
        champion_name=champion_name,
        tier_filter=tier_filter,
        only_channel_champion=only_channel_champion,
        preset=preset,
        rank=rank,
        scan_res=scan_res,
        started_at=started_at,
        finished_at=finished_at,
        ranked_res=ranked_res,
        summary_pl=ranked_res["summary_pl"],
    )
    if output_dir:
        out_p = Path(output_dir)
        _atomic_write_text(
            out_p / f"overnight_manifest_{batch_id}.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
    _persist_batch_manifest(manifest)

    _emit_status(
        status="done",
        phase="Gotowe — sprawdź rekomendację Synapsy",
        progress=100,
        rendered_count=sum(1 for x in ranked_res["items"] if x.get("render_ok")),
        recommended_filename=ranked_res["recommended_filename"],
        summary_pl=ranked_res["summary_pl"],
        finished_at=finished_at,
        log=ranked_res["summary_pl"],
    )
    return manifest


def restyle_overnight_short(output_filename: str, target_style: str) -> Dict[str, Any]:
    """Przerenderowuje wybrany short z ostatniej paczki nocnej w jednym z 3 stylów (1-klik z Outputs.tsx)."""
    style_norm = str(target_style or "").strip().upper()
    if style_norm not in VIRAL_STYLE_ORDER:
        raise ValueError(f"Nieznany styl montażu: {target_style}. Dozwolone: {', '.join(VIRAL_STYLE_ORDER)}")

    target_name = Path(str(output_filename or "").strip()).name
    if not target_name:
        raise ValueError("Brak nazwy pliku wyjściowego (output_filename).")

    try:
        from lol_agent.api import pipeline_runner
        from lol_agent.api.helpers import _load_meta
        from lol_agent.synapsa_watchability_judge import inspect_rendered_short
    except ImportError:
        from api import pipeline_runner  # type: ignore
        from api.helpers import _load_meta  # type: ignore
        from synapsa_watchability_judge import inspect_rendered_short  # type: ignore

    with _OVERNIGHT_LOCK:
        if _OVERNIGHT_STATE.get("status") in ("scanning", "rendering", "evaluating"):
            raise RuntimeError("Tryb nocny aktualnie pracuje — poczekaj na zakończenie przed restylem.")
    if pipeline_runner.get_state().get("status") == "running":
        raise RuntimeError("Inny render pipeline już trwa — poczekaj przed restylem.")

    batch = load_latest_overnight_batch()
    matched_item: Optional[Dict[str, Any]] = None
    if isinstance(batch, dict):
        for it in (batch.get("items") or []):
            if not isinstance(it, dict):
                continue
            if str(it.get("output_filename") or "") == target_name:
                matched_item = it
                break
            for alt in (it.get("alternate_renders") or []):
                if str(alt.get("output_filename") or "") == target_name:
                    matched_item = it
                    break
            if matched_item is not None:
                break

    meta = _load_meta(target_name) or {}
    if matched_item is None and not meta:
        out_fp = LOL_AGENT_DIR / "outputs" / target_name
        if not out_fp.is_file():
            raise FileNotFoundError(f"Nie znaleziono shorta '{target_name}' w paczce nocnej ani metadanych.")

    src_path = str((matched_item or {}).get("source_path") or meta.get("source_path") or "").strip()
    if not src_path or not Path(src_path).is_file():
        raise FileNotFoundError(f"Brak pliku źródłowego dla '{target_name}': {src_path or '?'}")

    cand: Dict[str, Any] = {
        "filename": Path(src_path).name,
        "path": src_path,
        "clip_start": (matched_item or {}).get("clip_start") if (matched_item or {}).get("clip_start") is not None else (meta.get("clip_start") or 0.0),
        "clip_end": (matched_item or {}).get("clip_end") if (matched_item or {}).get("clip_end") is not None else (meta.get("clip_end") or 15.0),
        "action_type": (matched_item or {}).get("action_type") or meta.get("action_type") or "outplay",
        "peak_moment": (matched_item or {}).get("peak_moment") if (matched_item or {}).get("peak_moment") is not None else (meta.get("peak_moment") or 8.0),
        "champion": (matched_item or {}).get("champion_name") or meta.get("champion_name") or "Katarina",
        "event_source": (matched_item or {}).get("event_source") or "outplayed_restyle",
        "hook_text": (matched_item or {}).get("hook_text") or "",
        "hype_score": (matched_item or {}).get("hype_score") or meta.get("hype_score") or 75.0,
        "kill_count": (matched_item or {}).get("kill_count"),
        "kill_span_s": (matched_item or {}).get("kill_span_s"),
        "objective_secured": (matched_item or {}).get("objective_secured"),
        "is_clutch_1hp": (matched_item or {}).get("is_clutch_1hp"),
        "min_hp_percentage": (matched_item or {}).get("min_hp_percentage"),
        "is_favorite": bool((matched_item or {}).get("is_favorite", False)),
        "event_tier": (matched_item or {}).get("event_tier") or "",
        "best_event_time_s": (matched_item or {}).get("best_event_time_s"),
        "est_first_kill_s": (matched_item or {}).get("est_first_kill_s"),
        "est_last_kill_s": (matched_item or {}).get("est_last_kill_s"),
        "total_kills_in_clip": (matched_item or {}).get("total_kills_in_clip"),
        "match_folder": (matched_item or {}).get("match_folder") or "",
        "match_date": (matched_item or {}).get("match_date") or "",
        "clip_base_key": (matched_item or {}).get("clip_base_key") or "",
        "match_kda": (matched_item or {}).get("match_kda") or "",
        "fallback_mediocre": bool((matched_item or {}).get("fallback_mediocre", False)),
    }

    base_stem = re.sub(r"_(alt|style)_[a-z0-9_]+$", "", Path(target_name).stem)
    if "short" not in base_stem.lower():
        base_stem = f"short_{base_stem}"
    new_out_fn = f"{base_stem}_style_{style_norm.lower()}.mp4"

    req_champ = str((matched_item or {}).get("requested_champion") or (matched_item or {}).get("champion_name") or meta.get("champion_name") or "Katarina")
    rank_val = str((matched_item or {}).get("rank") or meta.get("rank") or "Master")
    cand_rank = int((matched_item or {}).get("candidate_rank") or (matched_item or {}).get("overnight_rank") or 1)

    new_item = _render_and_inspect_candidate(
        pipeline_runner=pipeline_runner,
        inspect_rendered_short=inspect_rendered_short,
        cand=cand,
        out_filename=new_out_fn,
        candidate_rank=cand_rank,
        requested_champion=req_champ,
        rank=rank_val,
        montage_style=style_norm,
    )
    new_item["synapsa_comment_pl"] = _build_honest_short_comment_pl(new_item)
    batch_id = str((batch or {}).get("batch_id") or meta.get("overnight_batch_id") or "restyle")
    if matched_item is not None and matched_item.get("overnight_rank") is not None:
        new_item["overnight_rank"] = matched_item["overnight_rank"]
        fs = float(new_item.get("final_score") or 0.0)
        ws = float(new_item.get("watchability_score") or 0.0)
        crit = bool(new_item.get("has_critical_defect"))
        r_idx = int(matched_item["overnight_rank"])
        if r_idx == 1:
            new_item["verdict"] = "PICK_WINNER" if (fs >= 70.0 and ws >= 68.0 and not crit and not new_item.get("fallback_mediocre")) else "NEEDS_TWEAK"
        else:
            new_item["verdict"] = "STRONG_ALT" if (fs >= 65.0 and ws >= 65.0 and not crit) else ("NEEDS_TWEAK" if fs >= 50.0 else "SKIP")

    new_variant = _summarize_variant(new_item, is_selected=bool(new_item.get("render_ok")))
    batch_updated = False
    if isinstance(batch, dict) and matched_item is not None and new_item.get("render_ok"):
        existing_alts = list(matched_item.get("alternate_renders") or [])
        by_fn: Dict[str, Dict[str, Any]] = {}
        prev_fn = str(matched_item.get("output_filename") or "")
        if prev_fn:
            by_fn[prev_fn] = _summarize_variant(matched_item, is_selected=False)
        for a in existing_alts:
            afn = str(a.get("output_filename") or "")
            if afn:
                alt_copy = dict(a)
                alt_copy["is_selected"] = False
                by_fn[afn] = alt_copy
        by_fn[str(new_item.get("output_filename") or new_out_fn)] = dict(new_variant)
        new_alts = list(by_fn.values())

        for k in (
            "output_filename", "output_path", "thumbnail_path", "thumbnail_filename",
            "montage_style", "title", "title_variant_b", "description", "pinned_comment",
            "clip_start", "clip_end", "qa_status", "qa_score", "render_ok", "error",
            "watchability_score", "final_score", "duration_s", "defects", "has_critical_defect",
            "publish_block_reasons", "publish_recommended", "ig_compliance",
            "player_visible_ratio", "player_edge_clip_ratio", "camera_peak_step_px",
            "first_kill_out_sec", "longest_gap_out_sec", "kill_timestamps_out",
            "verdict", "synapsa_comment_pl", "hook_text", "frame0_hook_legible",
            "kill_overlay_zone", "audio_clip_gt_096", "av_delta_s", "black_end_frame",
        ):
            if k in new_item:
                matched_item[k] = new_item[k]
        matched_item["alternate_renders"] = new_alts
        new_item["alternate_renders"] = new_alts

        if batch.get("recommended_filename") == prev_fn or matched_item.get("overnight_rank") == 1:
            batch["recommended_filename"] = matched_item.get("output_filename")
            batch["recommended_verdict"] = matched_item.get("verdict")
        _persist_batch_manifest(batch)
        batch_updated = True

    _annotate_output_metas([new_item], batch_id=batch_id)
    return {
        "status": "done" if new_item.get("render_ok") else "error",
        "target_style": style_norm,
        "item": new_item,
        "variant": new_variant,
        "batch_updated": batch_updated,
    }


def start_overnight_batch_async(
    folder: Optional[str] = None,
    top_n: int = 5,
    champion_name: str = "Katarina",
    rank: str = "Master",
    skip_published: bool = True,
    use_cache: bool = True,
    use_local_ai: bool = True,
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
    montage_preset: str = "compare_all_3",
) -> bool:
    """Uruchamia tryb nocny w wątku w tle. Zwraca False jeśli sesja lub pipeline już trwa."""
    global _OVERNIGHT_THREAD
    try:
        from lol_agent.api import pipeline_runner
    except ImportError:
        from api import pipeline_runner  # type: ignore

    preset = _normalize_montage_preset(montage_preset)
    with _OVERNIGHT_LOCK:
        if _OVERNIGHT_STATE.get("status") in ("scanning", "rendering", "evaluating"):
            return False
        if pipeline_runner.get_state().get("status") == "running":
            return False
        _OVERNIGHT_CANCEL.clear()
        _OVERNIGHT_STATE["status"] = "scanning"
        _OVERNIGHT_STATE["phase"] = "Inicjalizacja trybu nocnego..."
        _OVERNIGHT_STATE["progress"] = 1
        _OVERNIGHT_STATE["error"] = None

    def _runner() -> None:
        try:
            run_overnight_batch(
                folder=folder,
                top_n=top_n,
                champion_name=champion_name,
                rank=rank,
                skip_published=skip_published,
                use_cache=use_cache,
                use_local_ai=use_local_ai,
                clear_cancel=False,
                tier_filter=tier_filter,
                only_channel_champion=only_channel_champion,
                montage_preset=preset,
            )
        except Exception as exc:
            _update_overnight_state(
                status="error",
                phase="Błąd trybu nocnego",
                error=str(exc),
                finished_at=_now_iso(),
                log=f"ERROR: {exc}",
            )
        finally:
            with _OVERNIGHT_LOCK:
                if _OVERNIGHT_STATE.get("status") in ("scanning", "rendering", "evaluating"):
                    _OVERNIGHT_STATE["status"] = "stopped" if _OVERNIGHT_CANCEL.is_set() else "error"
                    if not _OVERNIGHT_STATE.get("finished_at"):
                        _OVERNIGHT_STATE["finished_at"] = _now_iso()

    _OVERNIGHT_THREAD = threading.Thread(target=_runner, daemon=True)
    _OVERNIGHT_THREAD.start()
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapsa Tryb Nocny (Skan -> Top 5 -> Rekomendacja)")
    parser.add_argument("--folder", default=None, help="Opcjonalny folder klipów")
    parser.add_argument("--top", type=int, default=5, help="Liczba najlepszych klipów do montażu")
    parser.add_argument("--champion", default="Katarina")
    parser.add_argument("--tier-filter", default="auto", choices=sorted(TIER_FILTER_MIN_RANK.keys()))
    parser.add_argument("--montage-preset", default="compare_all_3", choices=list(MONTAGE_PRESETS))
    parser.add_argument("--all-champions", action="store_true")
    parser.add_argument("--rank", default="Master")
    parser.add_argument("--include-published", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-local-ai", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    ns = parser.parse_args()

    def _cli_scan_prog(done: int, total: int, label: str) -> None:
        print(f"[SCAN {done}/{total}] {label}", flush=True)

    def _cli_batch_prog(st: Dict[str, Any]) -> None:
        print(f"[OVERNIGHT {st.get('progress', 0)}%] {st.get('phase')} | {st.get('current_clip')}", flush=True)

    if ns.scan_only:
        res = scan_and_rank_all_clips(
            folder=ns.folder,
            top_n=ns.top,
            skip_published=not ns.include_published,
            use_cache=not ns.no_cache,
            progress_cb=_cli_scan_prog,
            champion_name=ns.champion,
            tier_filter=ns.tier_filter,
            only_channel_champion=not ns.all_champions,
        )
        print(json.dumps({k: v for k, v in res.items() if k not in ("all_qualified",)}, indent=2, ensure_ascii=False))
    else:
        manifest = run_overnight_batch(
            folder=ns.folder,
            top_n=ns.top,
            champion_name=ns.champion,
            rank=ns.rank,
            skip_published=not ns.include_published,
            use_cache=not ns.no_cache,
            use_local_ai=not ns.no_local_ai,
            progress_cb=_cli_batch_prog,
            tier_filter=ns.tier_filter,
            only_channel_champion=not ns.all_champions,
            montage_preset=ns.montage_preset,
        )
        print(json.dumps({
            "batch_id": manifest.get("batch_id"),
            "montage_preset": manifest.get("montage_preset"),
            "scan_stats": manifest.get("scan_stats"),
            "recommended_filename": manifest.get("recommended_filename"),
            "summary_pl": manifest.get("summary_pl"),
            "items": [
                {
                    "rank": it.get("overnight_rank"),
                    "output_filename": it.get("output_filename"),
                    "source_filename": it.get("source_filename"),
                    "action_type": it.get("action_type"),
                    "montage_style": it.get("montage_style"),
                    "fallback_triggered": it.get("fallback_triggered"),
                    "hype_score": it.get("hype_score"),
                    "watchability_score": it.get("watchability_score"),
                    "qa_score": it.get("qa_score"),
                    "final_score": it.get("final_score"),
                    "verdict": it.get("verdict"),
                    "publish_recommended": it.get("publish_recommended"),
                    "defects": it.get("defects"),
                    "synapsa_comment_pl": it.get("synapsa_comment_pl"),
                }
                for it in (manifest.get("items") or [])
            ],
        }, indent=2, ensure_ascii=False))
