"""
Shortsyt — Automatyczny rotator dysku dla lol_agent/lol_temp/.
Usuwa przeterminowane pliki pośrednie FFmpeg oraz nieopublikowane rendery >14 dni,
chroniąc aktywne pozycje w kolejce publikacji i najnowszy batch nocny.
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMP_DIR = Path(__file__).resolve().parent / "lol_temp"
DEFAULT_QUEUE_FILE = ROOT_DIR / "accounts" / "scheduled_social_queue.json"
DEFAULT_BATCHES_DIR = Path(__file__).resolve().parent / "overnight_batches"

INTERMEDIATE_EXACT_NAMES = {
    "01_cut.mp4",
    "04_processed.mp4",
    "05_music.mp4",
    "concat_list.txt",
}
INTERMEDIATE_SUFFIXES = ("_filter.txt", "_raw_frame.jpg", "_tkcover.mp4")


def _norm_path(p: Any) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def _add_with_siblings(protected: Set[str], raw_path: Any) -> None:
    if not raw_path:
        return
    p = Path(str(raw_path))
    protected.add(_norm_path(p))
    if p.suffix.lower() == ".mp4":
        protected.add(_norm_path(p.with_suffix(".meta.json")))
        protected.add(_norm_path(p.with_suffix(".recipe.json")))
        protected.add(_norm_path(p.with_name(f"{p.stem}_thumb.jpg")))


def collect_protected_paths(
    queue_file: Path = DEFAULT_QUEUE_FILE,
    batches_dir: Path = DEFAULT_BATCHES_DIR,
) -> Set[str]:
    """Zbiera zbiór znormalizowanych ścieżek chronionych przed rotacją."""
    protected: Set[str] = set()

    if queue_file.exists():
        try:
            items = json.loads(queue_file.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for item in items:
                    if item.get("status") in ("pending", "processing"):
                        _add_with_siblings(protected, item.get("video_path"))
                        _add_with_siblings(protected, item.get("thumbnail_path"))
        except Exception:
            pass

    if batches_dir.exists():
        try:
            batches = sorted(
                batches_dir.glob("batch_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if batches:
                latest = json.loads(batches[0].read_text(encoding="utf-8"))
                for it in (latest.get("items") or []):
                    _add_with_siblings(protected, it.get("output_path"))
                    _add_with_siblings(protected, it.get("thumbnail_path"))
        except Exception:
            pass

    return protected


def is_intermediate_artifact(path: Path) -> bool:
    name = path.name.lower()
    if name in INTERMEDIATE_EXACT_NAMES:
        return True
    if any(name.endswith(sfx) for sfx in INTERMEDIATE_SUFFIXES):
        return True
    if name.startswith("seg_") and name.endswith(".mp4"):
        return True
    return False


def get_temp_dir_stats(temp_dir: Path = DEFAULT_TEMP_DIR) -> Dict[str, Any]:
    """Zwraca liczbę plików i zajęty rozmiar MB w katalogu tymczasowym."""
    if not temp_dir.exists():
        return {"files": 0, "size_mb": 0.0}
    total_files = 0
    total_bytes = 0
    for f in temp_dir.rglob("*"):
        if f.is_file():
            total_files += 1
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
    return {
        "files": total_files,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
    }


def cleanup_temp_directory(
    max_age_days: int = 14,
    intermediate_min_age_minutes: int = 30,
    dry_run: bool = False,
    temp_dir: Optional[Path] = None,
    queue_file: Optional[Path] = None,
    batches_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Czyści zbędne pliki tymczasowe w lol_agent/lol_temp/:
    - natychmiastowo (>30 min) usuwa surowe półprodukty FFmpeg (01_cut/04_processed/05_music/*_raw_frame/*_filter)
    - usuwa stare nieopublikowane rendery i foldery debugowe > max_age_days
    - bezwzględnie chroni wpisy 'pending'/'processing' z kolejki oraz najnowszy batch nocny.
    """
    target_dir = Path(temp_dir) if temp_dir else DEFAULT_TEMP_DIR
    q_file = Path(queue_file) if queue_file else DEFAULT_QUEUE_FILE
    b_dir = Path(batches_dir) if batches_dir else DEFAULT_BATCHES_DIR

    before_stats = get_temp_dir_stats(target_dir)
    if not target_dir.exists():
        return {
            "before_files": 0,
            "before_size_mb": 0.0,
            "removed_intermediate": 0,
            "removed_stale": 0,
            "removed_total": 0,
            "freed_mb": 0.0,
            "after_files": 0,
            "after_size_mb": 0.0,
            "protected_count": 0,
            "dry_run": dry_run,
        }

    protected = collect_protected_paths(queue_file=q_file, batches_dir=b_dir)
    now_ts = time.time()
    inter_cutoff = now_ts - max(1, intermediate_min_age_minutes) * 60
    stale_cutoff = now_ts - max(1, max_age_days) * 86400

    removed_inter = 0
    removed_stale = 0
    freed_bytes = 0

    for entry in list(target_dir.rglob("*")):
        if not entry.is_file():
            continue
        if entry.name in (".gitkeep", ".keep"):
            continue
        if _norm_path(entry) in protected:
            continue

        try:
            st = entry.stat()
        except OSError:
            continue

        reason: Optional[str] = None
        if is_intermediate_artifact(entry) and st.st_mtime < inter_cutoff:
            reason = "intermediate"
        elif st.st_mtime < stale_cutoff:
            reason = "stale"

        if not reason:
            continue

        size_b = st.st_size
        if not dry_run:
            try:
                entry.unlink()
            except OSError:
                continue

        freed_bytes += size_b
        if reason == "intermediate":
            removed_inter += 1
        else:
            removed_stale += 1

    if not dry_run:
        # Usuń puste podkatalogi debugowe po usunięciu starych plików
        for d in sorted((p for p in target_dir.rglob("*") if p.is_dir()), reverse=True):
            try:
                if not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass

    after_stats = (
        {
            "files": max(0, before_stats["files"] - (removed_inter + removed_stale)),
            "size_mb": round(max(0.0, before_stats["size_mb"] - freed_bytes / (1024 * 1024)), 2),
        }
        if dry_run
        else get_temp_dir_stats(target_dir)
    )

    return {
        "before_files": before_stats["files"],
        "before_size_mb": before_stats["size_mb"],
        "removed_intermediate": removed_inter,
        "removed_stale": removed_stale,
        "removed_total": removed_inter + removed_stale,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "after_files": after_stats["files"],
        "after_size_mb": after_stats["size_mb"],
        "protected_count": len(protected),
        "dry_run": dry_run,
    }
