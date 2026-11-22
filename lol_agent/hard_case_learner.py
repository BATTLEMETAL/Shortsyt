"""
Shortsyt — Rejestr Pamięci Niewygodnych Klipów (Hard Case Learner)
Zapisuje sygnatury trudnych klipów (np. zatkana kolejka banerów przez Ally slain,
kradzież smoka/barona w trakcie multikilla, rozbieżne okna akcji), aby detektor
oraz przyszły Synapsa Montage Director mogły uczyć się z każdego trudnego przypadku.
"""
import os
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_FILE = Path(__file__).resolve().parent / "hard_cases_memory.json"
_LOCK = threading.Lock()


def load_hard_cases(memory_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    target = Path(memory_path) if memory_path else MEMORY_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_hard_cases(items: List[Dict[str, Any]], memory_path: Optional[Path] = None) -> None:
    target = Path(memory_path) if memory_path else MEMORY_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, target)


def get_hard_case_by_source(video_path: str, memory_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    source_name = Path(video_path).name
    with _LOCK:
        for item in load_hard_cases(memory_path):
            if item.get("source_name") == source_name:
                return item
    return None


def record_hard_case(
    video_path: str,
    detected_frag_type: str,
    kills: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    reason: str,
    objective_secured: bool = False,
    objective_label: str = "",
    ally_banner_blocked: bool = False,
    min_hp_pct: float = 100.0,
    memory_path: Optional[Path] = None,
) -> Dict[str, Any]:
    source_name = Path(video_path).name
    entry = {
        "source_name": source_name,
        "video_path": str(video_path),
        "detected_frag_type": detected_frag_type,
        "kills": list(kills or []),
        "clip_start": round(float(clip_start), 2),
        "clip_end": round(float(clip_end), 2),
        "duration_window": round(max(0.0, float(clip_end) - float(clip_start)), 2),
        "reason": reason,
        "objective_secured": bool(objective_secured),
        "objective_label": objective_label or "",
        "ally_banner_blocked": bool(ally_banner_blocked),
        "min_hp_pct": round(float(min_hp_pct), 1),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        items = load_hard_cases(memory_path)
        replaced = False
        for idx, existing in enumerate(items):
            if existing.get("source_name") == source_name:
                items[idx] = entry
                replaced = True
                break
        if not replaced:
            items.append(entry)
        _save_hard_cases(items, memory_path)
    return entry


def _is_meaningful_hard_case(item: Dict[str, Any]) -> bool:
    kills = item.get("kills") or []
    if len(kills) >= 2:
        return True
    has_obj = bool(item.get("objective_secured") or item.get("objective"))
    return has_obj and len(kills) >= 1


def prune_noisy_hard_cases(memory_path: Optional[Path] = None) -> Dict[str, int]:
    """Usuwa z pamięci hard_cases_memory.json szum z <2 killami (bez potwierdzonego objective z killem)."""
    with _LOCK:
        items = load_hard_cases(memory_path)
        kept = [item for item in items if _is_meaningful_hard_case(item)]
        removed = len(items) - len(kept)
        if removed > 0:
            _save_hard_cases(kept, memory_path)
        return {
            "before": len(items),
            "kept": len(kept),
            "removed": removed,
        }
