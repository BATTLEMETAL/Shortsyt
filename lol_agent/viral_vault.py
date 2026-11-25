"""
Flikcut / Shortsyt — Viral Vault (`Etap 31.1`)
==============================================
Archiwizuje surowe nagrania 16:9 powiązane z opublikowanymi Shortsami za pomocą
twardych linków NTFS (`os.link`, 0 B dodatkowego miejsca) poza OneDrive,
promuje hity na podstawie wyników 24h+ (`views >= max(2000, 1.25x mediany)` /
`AVP >= 95%` / `Quadra+` / `Favorite`) oraz zasila tygodniowe/miesięczne
kompilacje poziome `16:9`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOL_AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_VAULT_DIR = Path(
    os.environ.get("FLIKCUT_VIRAL_VAULT_DIR", str(Path.home() / "Videos" / "Flikcut_Viral_Vault"))
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_vault_dir(vault_dir: Optional[Path | str] = None) -> Optional[Path]:
    if vault_dir is not None:
        return Path(vault_dir)
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("FLIKCUT_VAULT_ALLOW_IN_TEST") != "1":
        return None
    return DEFAULT_VAULT_DIR


def _db_path_for_vault(vdir: Path, custom_vault_dir: Optional[Path | str]) -> Path:
    if custom_vault_dir is not None:
        return vdir / "vault_state.db"
    try:
        from lol_agent.state_db import get_state_db_path
        return get_state_db_path()
    except Exception:
        return vdir / "vault_state.db"


def _ensure_vault_dirs(vdir: Path) -> Dict[str, Path]:
    dirs = {
        "root": vdir,
        "staging": vdir / "staging",
        "approved": vdir / "approved",
        "rendered": vdir / "rendered",
    }
    for p in dirs.values():
        p.mkdir(parents=True, exist_ok=True)
    return dirs


def _index_path(vdir: Path) -> Path:
    return vdir / "vault_index.json"


def _load_vault_index(vdir: Path) -> Dict[str, Dict[str, Any]]:
    idx_file = _index_path(vdir)
    if idx_file.is_file():
        try:
            data = json.loads(idx_file.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_vault_index(vdir: Path, index: Dict[str, Dict[str, Any]]) -> None:
    _ensure_vault_dirs(vdir)
    idx_file = _index_path(vdir)
    tmp = idx_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, idx_file)


def _sync_item_db(item: Dict[str, Any], vdir: Path, custom_vault_dir: Optional[Path | str]) -> None:
    try:
        from lol_agent.state_db import upsert_vault_item_db
        upsert_vault_item_db(item, db_path=_db_path_for_vault(vdir, custom_vault_dir))
    except Exception:
        pass


def _link_or_copy(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return "existing"
    try:
        os.link(src, dst)
        return "ntfs_hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def _safe_clip_id(source_path: Path, yt_video_id: str = "") -> str:
    digest = hashlib.sha1(str(source_path).lower().encode("utf-8", errors="ignore")).hexdigest()[:8]
    if yt_video_id:
        clean_yt = re.sub(r"[^a-zA-Z0-9_-]", "", str(yt_video_id))[:20]
        return f"{clean_yt}_{digest}"
    stem = re.sub(r"[^a-zA-Z0-9_-]", "_", source_path.stem).strip("_")[:36] or "clip"
    return f"{stem}_{digest}"


def _parse_iso(raw: Any) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def stage_short_original(
    source_path: str | Path,
    yt_video_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    vault_dir: Optional[Path | str] = None,
    force_approved: bool = False,
) -> Dict[str, Any]:
    """
    Zapisuje oryginał 16:9 powiązany z Shortem w Viral Vault (hardlink NTFS 0 B).
    Klip trafia do `staging/`, a przy Quadra+/Favorite lub `force_approved=True` od razu do `approved/`.
    """
    vdir = _resolve_vault_dir(vault_dir)
    if vdir is None:
        return {"ok": False, "skipped": True, "reason": "pytest_guard"}

    src = Path(source_path) if source_path else Path()
    if not source_path or not src.is_file():
        return {"ok": False, "error": f"Brak pliku źródłowego: {source_path}"}

    dirs = _ensure_vault_dirs(vdir)
    meta = dict(metadata or {})
    clip_id = _safe_clip_id(src, yt_video_id=yt_video_id)
    action_type = str(meta.get("action_type") or "outplay").lower().strip()
    is_fav = bool(meta.get("is_favorite"))
    immediate_approve = bool(
        force_approved
        or is_fav
        or any(t in action_type for t in ("quadra", "penta"))
    )
    target_state = "approved" if immediate_approve else "staging"
    target_bucket = dirs[target_state]

    ext = src.suffix.lower() or ".mp4"
    dst_video = target_bucket / f"{clip_id}{ext}"
    link_mode = _link_or_copy(src, dst_video)

    now_iso = _now_utc().isoformat()
    record: Dict[str, Any] = {
        "clip_id": clip_id,
        "state": target_state,
        "link_mode": link_mode,
        "vault_path": str(dst_video),
        "source_path": str(src),
        "yt_video_id": str(yt_video_id or meta.get("youtube_id") or "").strip(),
        "title": str(meta.get("title") or meta.get("yt_title") or ""),
        "champion": str(meta.get("champion_name") or meta.get("champion") or "Katarina"),
        "action_type": action_type,
        "match_kda": str(meta.get("match_kda") or ""),
        "clip_start": float(meta.get("clip_start") or 0.0),
        "clip_end": float(meta.get("clip_end") or 0.0),
        "peaks": list(meta.get("peaks") or []),
        "views": int(meta.get("views") or 0),
        "avg_view_percentage": float(meta.get("avg_view_percentage") or 0.0),
        "engagement_rate": float(meta.get("engagement_rate") or 0.0),
        "is_favorite": is_fav,
        "staged_at": now_iso,
        "approved_at": now_iso if immediate_approve else "",
        "promotion_reason": "immediate_tier_or_favorite" if immediate_approve else "",
        "used_in_compilations": list(meta.get("used_in_compilations") or []),
    }

    sidecar = dst_video.with_suffix(".json")
    sidecar.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

    index = _load_vault_index(vdir)
    if clip_id in index and index[clip_id].get("state") == "approved" and target_state == "staging":
        # Zachowaj status approved jeśli klip już został wcześniej wypromowany
        return {"ok": True, "item": index[clip_id], "preserved_approved": True}

    index[clip_id] = record
    _save_vault_index(vdir, index)
    _sync_item_db(record, vdir, vault_dir)
    return {"ok": True, "item": record}


def _extract_metric(row: Dict[str, Any], keys: tuple, default: float = 0.0) -> float:
    for k in keys:
        val = row.get(k)
        if val is not None and val != "":
            try:
                return float(val)
            except Exception:
                pass
    return default


def evaluate_and_promote_vault(
    analytics_rows: List[Dict[str, Any]],
    channel_median_views: float = 1593.5,
    min_views_floor: int = 2000,
    stale_days: int = 14,
    now_utc: Optional[datetime] = None,
    vault_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Promuje nagrania z `staging/` do `approved/`, gdy odpowiadający im Short
    osiągnął próg popularności (`views >= max(2000, 1.25x mediana)` lub `AVP >= 95%`
    lub `engagement >= 2%` przy >=1200 wyśw. lub `Quadra/Penta/Favorite`).
    Słabe hardlinki po `stale_days` są usuwane ze `staging/` (bez ruszania oryginału).
    """
    vdir = _resolve_vault_dir(vault_dir)
    if vdir is None:
        return {"skipped": True, "promoted": 0, "expired": 0}

    dirs = _ensure_vault_dirs(vdir)
    index = _load_vault_index(vdir)
    if not index:
        return {"promoted": 0, "expired": 0, "checked": 0, "view_threshold": int(min_views_floor)}

    now = now_utc or _now_utc()
    view_threshold = max(int(min_views_floor), int(round(1.25 * float(channel_median_views or 0.0))))

    by_vid: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    for row in analytics_rows or []:
        if not isinstance(row, dict):
            continue
        vid = str(row.get("video_id") or row.get("id") or "").strip()
        if vid:
            by_vid[vid] = row
        title = re.sub(r"#\S+", "", str(row.get("title") or "")).strip().lower()
        if title:
            by_title[title] = row

    promoted = 0
    expired = 0
    checked = 0

    for clip_id, rec in list(index.items()):
        if not isinstance(rec, dict) or rec.get("state") != "staging":
            continue
        checked += 1
        vid = str(rec.get("yt_video_id") or "").strip()
        t_clean = re.sub(r"#\S+", "", str(rec.get("title") or "")).strip().lower()
        row = by_vid.get(vid) or (by_title.get(t_clean) if t_clean else None)

        if row:
            views = int(_extract_metric(row, ("views", "view_count"), rec.get("views", 0)))
            avp = _extract_metric(row, ("avg_view_percentage", "avp", "averageViewPercentage"), rec.get("avg_view_percentage", 0.0))
            likes = _extract_metric(row, ("likes", "like_count"), 0.0)
            eng = _extract_metric(
                row,
                ("engagement_rate",),
                (likes / max(1.0, float(views)) * 100.0) if views > 0 and likes > 0 else rec.get("engagement_rate", 0.0),
            )
            rec["views"] = views
            rec["avg_view_percentage"] = round(avp, 2)
            rec["engagement_rate"] = round(eng, 2)
        else:
            views = int(rec.get("views") or 0)
            avp = float(rec.get("avg_view_percentage") or 0.0)
            eng = float(rec.get("engagement_rate") or 0.0)

        act = str(rec.get("action_type") or "").lower()
        is_fav = bool(rec.get("is_favorite"))
        reason = ""
        if views >= view_threshold:
            reason = f"views>={view_threshold} ({views})"
        elif avp >= 95.0 and views >= 1200:
            reason = f"avp>={avp:.1f}% ({views} views)"
        elif eng >= 2.0 and views >= 1200:
            reason = f"engagement>={eng:.1f}% ({views} views)"
        elif any(t in act for t in ("quadra", "penta")):
            reason = f"high_tier:{act}"
        elif is_fav:
            reason = "outplayed_favorite"

        staged_dt = _parse_iso(rec.get("staged_at")) or now
        age_hours = (now - staged_dt).total_seconds() / 3600.0

        src_vault_path = Path(str(rec.get("vault_path") or ""))
        if reason and (age_hours >= 24.0 or views >= view_threshold or is_fav or any(t in act for t in ("quadra", "penta"))):
            dst_approved = dirs["approved"] / (src_vault_path.name if src_vault_path.name else f"{clip_id}.mp4")
            if src_vault_path.is_file():
                dst_approved.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_vault_path), str(dst_approved))
                old_sidecar = src_vault_path.with_suffix(".json")
                if old_sidecar.is_file():
                    try:
                        old_sidecar.unlink()
                    except OSError:
                        pass
            rec["state"] = "approved"
            rec["vault_path"] = str(dst_approved)
            rec["approved_at"] = now.isoformat()
            rec["promotion_reason"] = reason
            dst_approved.with_suffix(".json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
            _sync_item_db(rec, vdir, vault_dir)
            promoted += 1
        elif age_hours >= float(stale_days) * 24.0:
            if src_vault_path.is_file():
                try:
                    src_vault_path.unlink()
                except OSError:
                    pass
            old_sidecar = src_vault_path.with_suffix(".json")
            if old_sidecar.is_file():
                try:
                    old_sidecar.unlink()
                except OSError:
                    pass
            rec["state"] = "expired"
            rec["promotion_reason"] = f"expired_after_{stale_days}d"
            _sync_item_db(rec, vdir, vault_dir)
            expired += 1
        else:
            _sync_item_db(rec, vdir, vault_dir)

    _save_vault_index(vdir, index)
    return {
        "promoted": promoted,
        "expired": expired,
        "checked": checked,
        "view_threshold": view_threshold,
    }


def _estimate_window_from_outplayed(entry: Dict[str, Any]) -> Dict[str, Any]:
    best_t = entry.get("best_event_time_s")
    clip_start = 0.0
    clip_end = 0.0
    peaks: List[List[Any]] = []
    evs = [
        float(ev["time_s"])
        for ev in (entry.get("events_summary") or [])
        if isinstance(ev, dict) and ev.get("type") == "kill" and isinstance(ev.get("time_s"), (int, float))
    ]
    if isinstance(best_t, (int, float)):
        t_ev = float(best_t)
        rel_kills = [kt for kt in sorted(evs) if abs(t_ev - kt) <= 14.0]
        first_k = min(rel_kills) if rel_kills else t_ev
        last_k = max(rel_kills + [t_ev])
        clip_start = max(0.0, round(first_k - 2.8, 2))
        clip_end = round(last_k + 3.0, 2)
        if clip_end - clip_start < 9.5:
            clip_start = max(0.0, round(clip_end - 9.5, 2))
        tier = str(entry.get("event_tier") or "outplay").upper()
        peaks = [[round(kt - clip_start, 2), "KILL"] for kt in rel_kills[:-1]]
        peaks.append([round(last_k - clip_start, 2), tier.replace("_", " ")])
    return {"clip_start": clip_start, "clip_end": clip_end, "peaks": peaks}


def bootstrap_vault_from_outplayed(
    champion: str = "Katarina",
    limit: int = 12,
    vault_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """
    Zasila `approved/` z ocalałych oryginałów w `published_videos.jsonl` oraz
    najlepszych nieusuniętych nagrań w Outplayed (priorytet: Penta > Quadra > Triple > Favorite > Double).
    """
    vdir = _resolve_vault_dir(vault_dir)
    if vdir is None:
        return {"skipped": True, "added": 0}

    candidates: List[Dict[str, Any]] = []
    seen_paths: set[str] = set()
    champ_low = str(champion or "").strip().lower()

    # 1. Ocalałe źródła opublikowanych hitów + ich wyświetlenia z performance_log.jsonl
    perf_views: Dict[str, int] = {}
    perf_path = LOL_AGENT_DIR / "performance_log.jsonl"
    if perf_path.is_file():
        for line in perf_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                p = json.loads(line)
                if p.get("video_id"):
                    perf_views[str(p["video_id"])] = int(p.get("views") or 0)
            except Exception:
                continue

    pub_path = LOL_AGENT_DIR / "published_videos.jsonl"
    if pub_path.is_file():
        for line in pub_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            sp = str(row.get("source_path") or "").strip()
            rc = str(row.get("champion") or "").strip()
            if not sp or not Path(sp).is_file():
                continue
            if "\\recently deleted\\" in sp.lower():
                continue
            if champ_low and rc and champ_low not in rc.lower():
                continue
            norm = os.path.normcase(os.path.normpath(sp))
            if norm in seen_paths:
                continue
            seen_paths.add(norm)
            vid = str(row.get("video_id") or "")
            act = str(row.get("action_type") or "outplay").lower()
            tier_bonus = {"pentakill": 5000, "quadrakill": 4000, "triple": 3000, "double": 2000, "clutch": 2200, "solo_bolo": 2100}.get(act, 1500)
            views = perf_views.get(vid, int(row.get("views") or 0))
            candidates.append({
                "source_path": sp,
                "yt_video_id": vid,
                "title": row.get("title") or "",
                "champion_name": rc or champion,
                "action_type": act,
                "views": views,
                "score": tier_bonus + views,
                "mtime": Path(sp).stat().st_mtime,
            })

    # 2. Indeks Outplayed (w tym Live V8 IDB)
    try:
        from lol_agent.outplayed_db import load_outplayed_index
        idx = load_outplayed_index()
        for k, entry in idx.items():
            if str(k).startswith("name::"):
                continue
            sp = str(entry.get("raw_path") or "").strip()
            if not sp or not Path(sp).is_file():
                continue
            if "\\recently deleted\\" in sp.lower() or "\\.trash\\" in sp.lower():
                continue
            ec = str(entry.get("champion") or "").strip()
            if champ_low and ec and champ_low not in ec.lower():
                continue
            tier_rank = int(entry.get("event_tier_rank") or 0)
            is_fav = bool(entry.get("is_favorite"))
            if tier_rank < 2 and not is_fav:
                continue
            norm = os.path.normcase(os.path.normpath(sp))
            if norm in seen_paths:
                continue
            seen_paths.add(norm)
            win = _estimate_window_from_outplayed(entry)
            act = str(entry.get("event_tier") or "double").lower()
            tier_bonus = tier_rank * 1000 + (900 if is_fav else 0)
            candidates.append({
                "source_path": sp,
                "yt_video_id": "",
                "title": "",
                "champion_name": ec or champion,
                "action_type": act,
                "match_kda": entry.get("match_kda") or "",
                "is_favorite": is_fav,
                "clip_start": win["clip_start"],
                "clip_end": win["clip_end"],
                "peaks": win["peaks"],
                "views": 0,
                "score": tier_bonus + Path(sp).stat().st_mtime / 1e7,
                "mtime": Path(sp).stat().st_mtime,
            })
    except Exception:
        pass

    candidates.sort(key=lambda c: (float(c.get("score") or 0.0), float(c.get("mtime") or 0.0)), reverse=True)
    added = 0
    items_added: List[Dict[str, Any]] = []
    for cand in candidates[: max(1, int(limit))]:
        res = stage_short_original(
            cand["source_path"],
            yt_video_id=cand.get("yt_video_id", ""),
            metadata=cand,
            vault_dir=vault_dir,
            force_approved=True,
        )
        if res.get("ok"):
            added += 1
            items_added.append(res["item"])
    return {"ok": True, "added": added, "candidates_found": len(candidates), "items": items_added}


def select_clips_for_compilation(
    mode: str = "weekly",
    champion: str = "Katarina",
    max_clips: Optional[int] = None,
    vault_dir: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    """Wybiera zatwierdzone klipy ze skarbca pod kompilację tygodniową (8-12) lub miesięczną (22-32)."""
    vdir = _resolve_vault_dir(vault_dir)
    if vdir is None:
        return []
    index = _load_vault_index(vdir)
    champ_low = str(champion or "").strip().lower()
    target_n = int(max_clips) if max_clips else (24 if mode == "monthly" else 10)

    tier_weight = {"pentakill": 5000, "quadrakill": 4000, "triple": 3000, "clutch": 2400, "solo_bolo": 2200, "double": 2000}
    approved: List[tuple[float, Dict[str, Any]]] = []
    for rec in index.values():
        if not isinstance(rec, dict) or rec.get("state") != "approved":
            continue
        vp = Path(str(rec.get("vault_path") or ""))
        sp = Path(str(rec.get("source_path") or ""))
        media = vp if vp.is_file() else (sp if sp.is_file() else None)
        if media is None:
            continue
        rc = str(rec.get("champion") or "").lower()
        if champ_low and rc and champ_low not in rc:
            continue
        act = str(rec.get("action_type") or "").lower()
        score = tier_weight.get(act, 1500) + int(rec.get("views") or 0) * 1.2 + (600 if rec.get("is_favorite") else 0)
        enriched = dict(rec)
        enriched["resolved_media_path"] = str(media)
        enriched["selection_score"] = round(float(score), 2)
        approved.append((score, enriched))

    approved.sort(key=lambda pair: pair[0], reverse=True)
    return [pair[1] for pair in approved[:target_n]]


def get_vault_summary(vault_dir: Optional[Path | str] = None) -> Dict[str, Any]:
    vdir = _resolve_vault_dir(vault_dir)
    if vdir is None:
        return {"vault_dir": "", "counts": {"staging": 0, "approved": 0, "expired": 0, "rendered": 0}, "items": []}
    dirs = _ensure_vault_dirs(vdir)
    index = _load_vault_index(vdir)
    counts = {"staging": 0, "approved": 0, "expired": 0, "rendered": 0}
    items: List[Dict[str, Any]] = []
    for rec in index.values():
        if not isinstance(rec, dict):
            continue
        st = str(rec.get("state") or "staging")
        counts[st] = counts.get(st, 0) + 1
        items.append(rec)
    counts["rendered"] = len(list(dirs["rendered"].glob("*.mp4")))
    items.sort(key=lambda x: (0 if x.get("state") == "approved" else 1, -int(x.get("views") or 0), str(x.get("staged_at") or "")))
    return {"vault_dir": str(vdir), "counts": counts, "items": items}
