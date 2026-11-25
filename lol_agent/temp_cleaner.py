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


def _is_meta_published(meta_path: Path) -> bool:
    """Zwraca True, jeśli plik .meta.json oznacza film już opublikowany na co najmniej jednej platformie."""
    if not meta_path.is_file():
        return False
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        return bool(data.get("published_at") or data.get("published_platforms"))
    except Exception:
        return False


def _add_with_siblings(protected: Set[str], raw_path: Any, include_video: bool = True) -> None:
    if not raw_path:
        return
    p = Path(str(raw_path))
    if include_video:
        protected.add(_norm_path(p))
    if p.suffix.lower() == ".mp4":
        protected.add(_norm_path(p.with_suffix(".meta.json")))
        protected.add(_norm_path(p.with_suffix(".recipe.json")))
        protected.add(_norm_path(p.with_name(f"{p.stem}_thumb.jpg")))


def is_video_referenced_in_active_queue(
    video_path: str,
    queue_file: Optional[Path] = None,
) -> bool:
    """Sprawdza, czy podany plik wideo nadal czeka w aktywnej kolejce publikacji ('pending'/'processing')."""
    q_file = Path(queue_file) if queue_file is not None else Path(DEFAULT_QUEUE_FILE)
    if not video_path or not q_file.exists():
        return False
    target_norm = _norm_path(video_path)
    try:
        items = json.loads(q_file.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return False
        for item in items:
            if item.get("status") not in ("pending", "processing"):
                continue
            vp = item.get("video_path")
            if vp and _norm_path(vp) == target_norm:
                return True
    except Exception:
        return True  # Ostrożność przy uszkodzonym odczycie — nie kasuj
    return False


def cleanup_published_video_if_idle(
    video_path: str,
    queue_file: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Bezpiecznie usuwa ciężki wyrenderowany plik .mp4 po publikacji, jeśli żadna platforma
    nie czeka z tym plikiem w aktywnej kolejce. Zostawia .meta.json, .recipe.json i _thumb.jpg.
    """
    q_file = Path(queue_file) if queue_file is not None else Path(DEFAULT_QUEUE_FILE)
    if not video_path:
        return {"deleted": False, "reason": "empty_path", "freed_mb": 0.0}
    vp = Path(str(video_path))
    if not vp.is_file():
        return {"deleted": False, "reason": "missing", "freed_mb": 0.0}
    if is_video_referenced_in_active_queue(str(vp), queue_file=q_file):
        return {"deleted": False, "reason": "pending_in_queue", "freed_mb": 0.0}

    freed_bytes = 0
    for cand in (vp, vp.with_name(f"{vp.stem}_tkcover.mp4")):
        if cand.is_file():
            try:
                sz = cand.stat().st_size
                cand.unlink()
                freed_bytes += sz
            except OSError as err:
                return {"deleted": False, "reason": f"unlink_error:{err}", "freed_mb": 0.0}

    meta_p = vp.with_suffix(".meta.json")
    if meta_p.is_file():
        try:
            meta_obj = json.loads(meta_p.read_text(encoding="utf-8"))
            if isinstance(meta_obj, dict):
                meta_obj["video_cleaned"] = True
                meta_obj["video_cleaned_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                tmp_meta = meta_p.with_suffix(".meta.tmp")
                tmp_meta.write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp_meta, meta_p)
        except Exception:
            pass

    return {
        "deleted": True,
        "reason": "published_idle",
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
    }


def collect_protected_paths(
    queue_file: Optional[Path] = None,
    batches_dir: Optional[Path] = None,
) -> Set[str]:
    """Zbiera zbiór znormalizowanych ścieżek chronionych przed rotacją (opublikowane .mp4 nie są chronione)."""
    q_file = Path(queue_file) if queue_file is not None else Path(DEFAULT_QUEUE_FILE)
    b_dir = Path(batches_dir) if batches_dir is not None else Path(DEFAULT_BATCHES_DIR)
    protected: Set[str] = set()

    if q_file.exists():
        try:
            items = json.loads(q_file.read_text(encoding="utf-8"))
            if isinstance(items, list):
                for item in items:
                    if item.get("status") in ("pending", "processing"):
                        _add_with_siblings(protected, item.get("video_path"), include_video=True)
                        _add_with_siblings(protected, item.get("thumbnail_path"), include_video=True)
        except Exception:
            pass

    if b_dir.exists():
        try:
            batches = sorted(
                b_dir.glob("batch_*.json"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if batches:
                latest = json.loads(batches[0].read_text(encoding="utf-8"))
                for it in (latest.get("items") or []):
                    out_p = it.get("output_path")
                    is_pub = bool(out_p and _is_meta_published(Path(str(out_p)).with_suffix(".meta.json")))
                    _add_with_siblings(protected, out_p, include_video=not is_pub)
                    _add_with_siblings(protected, it.get("thumbnail_path"), include_video=True)
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
    removed_pub = 0
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
        elif entry.suffix.lower() == ".mp4" and _is_meta_published(entry.with_suffix(".meta.json")):
            reason = "published"
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
        elif reason == "published":
            removed_pub += 1
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
            "files": max(0, before_stats["files"] - (removed_inter + removed_stale + removed_pub)),
            "size_mb": round(max(0.0, before_stats["size_mb"] - freed_bytes / (1024 * 1024)), 2),
        }
        if dry_run
        else get_temp_dir_stats(target_dir)
    )

    return {
        "before_files": before_stats["files"],
        "before_size_mb": before_stats["size_mb"],
        "removed_intermediate": removed_inter,
        "removed_published": removed_pub,
        "removed_stale": removed_stale,
        "removed_total": removed_inter + removed_stale + removed_pub,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "after_files": after_stats["files"],
        "after_size_mb": after_stats["size_mb"],
        "protected_count": len(protected),
        "dry_run": dry_run,
    }
