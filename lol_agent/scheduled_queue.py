"""
Shortsyt — Moduł zarządzania kolejką zaplanowanych publikacji dla platform społecznościowych.
Umożliwia planowanie publikacji m.in. dla Instagram Reels (które nie posiadają natywnego parametru future timestamp w Meta API).
"""
import os
import json
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT_DIR / "accounts"
QUEUE_FILE = ACCOUNTS_DIR / "scheduled_social_queue.json"
_QUEUE_LOCK = threading.Lock()
_FLUSH_EXEC_LOCK = threading.Lock()

MAX_UPLOAD_RETRIES = 3
RETRY_BACKOFF_MINUTES = 5
STALE_PROCESSING_MINUTES = 15


def _parse_iso_utc(raw: Any) -> Optional[datetime]:
    """Parsuje ciąg ISO-8601 do timezone-aware datetime (UTC)."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _load_queue() -> List[Dict[str, Any]]:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_queue(items: List[Dict[str, Any]]):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = QUEUE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, QUEUE_FILE)


def queue_scheduled_post(
    platform: str,
    video_path: str,
    caption: str,
    publish_at: str,
    thumbnail_path: Optional[str] = None,
    peak_moment: Optional[float] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rejestruje zaplanowaną publikację w kolejce (bezpieczne wątkowo)."""
    entry = {
        "id": f"{platform}_{int(time.time()*1000)}",
        "platform": platform,
        "video_path": str(Path(video_path).resolve()),
        "caption": caption,
        "publish_at": publish_at,
        "thumbnail_path": str(Path(thumbnail_path).resolve()) if thumbnail_path and os.path.exists(thumbnail_path) else None,
        "peak_moment": peak_moment,
        "status": "pending",  # 'pending' | 'processing' | 'published' | 'failed'
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra": extra or {}
    }
    with _QUEUE_LOCK:
        items = _load_queue()
        existing_ids = {x.get("id") for x in items}
        base_id = entry["id"]
        suffix = 1
        while entry["id"] in existing_ids:
            entry["id"] = f"{base_id}_{suffix}"
            suffix += 1
        items.append(entry)
        _save_queue(items)
    return entry


def _recover_stale_processing(items: List[Dict[str, Any]], now_utc: datetime) -> bool:
    """Przywraca zawieszone wpisy 'processing' starsze niż STALE_PROCESSING_MINUTES do 'pending'."""
    changed = False
    stale_cutoff = now_utc - timedelta(minutes=STALE_PROCESSING_MINUTES)
    for item in items:
        if item.get("status") != "processing":
            continue
        started_dt = _parse_iso_utc(item.get("processing_started_at"))
        if started_dt is None or started_dt <= stale_cutoff:
            item["status"] = "pending"
            item.pop("processing_started_at", None)
            changed = True
            print(f"⚠️ [ScheduledQueue] Odzyskano zawieszony wpis processing -> pending: {item.get('id')}")
    return changed


def _persist_item_state(
    item_id: str,
    updates: Dict[str, Any],
    clear_keys: tuple = (),
) -> None:
    """Atomowo zapisuje wynik pojedynczego uploadu bez nadpisywania równolegle dodanych wpisów."""
    with _QUEUE_LOCK:
        current_items = _load_queue()
        for cur in current_items:
            if cur.get("id") == item_id:
                cur.update(updates)
                for key in clear_keys:
                    cur.pop(key, None)
                break
        _save_queue(current_items)


def _record_retry_or_fail(item: Dict[str, Any], err_msg: str) -> None:
    """Planuje ponowną próbę (do 3 razy co 5 min) lub oznacza jako permanent 'failed'."""
    now_utc = datetime.now(timezone.utc)
    retry_count = int(item.get("retry_count") or 0) + 1
    item_id = item.get("id", "")
    if retry_count < MAX_UPLOAD_RETRIES:
        next_retry = (now_utc + timedelta(minutes=RETRY_BACKOFF_MINUTES)).isoformat()
        _persist_item_state(
            item_id,
            {
                "status": "pending",
                "retry_count": retry_count,
                "last_error": err_msg,
                "next_retry_at": next_retry,
            },
            clear_keys=("processing_started_at",),
        )
        print(
            f"⚠️ [ScheduledQueue] Błąd uploadu {item.get('platform')} "
            f"(próba {retry_count}/{MAX_UPLOAD_RETRIES}): {err_msg}. Kolejna próba po {next_retry}"
        )
    else:
        _persist_item_state(
            item_id,
            {
                "status": "failed",
                "retry_count": retry_count,
                "last_error": err_msg,
                "error": err_msg,
                "failed_at": now_utc.isoformat(),
            },
            clear_keys=("processing_started_at", "next_retry_at"),
        )
        print(f"❌ [ScheduledQueue] Trwały błąd publikacji ({item.get('platform')}) po {retry_count} próbach: {err_msg}")


def _execute_single_upload(item: Dict[str, Any]) -> Dict[str, Any]:
    """Wykonuje bezpośredni upload pojedynczej pozycji na docelową platformę."""
    platform = item.get("platform")
    vp = item.get("video_path")
    caption = item.get("caption", "")
    thumb = item.get("thumbnail_path")
    peak = item.get("peak_moment")

    if platform == "instagram":
        from lol_agent.instagram_publisher import upload_instagram_reel
        return upload_instagram_reel(
            video_path=vp,
            caption=caption,
            thumbnail_path=thumb,
            peak_moment=peak,
            publish_at=None,
        )
    if platform == "facebook":
        from lol_agent.facebook_publisher import upload_facebook_reel
        return upload_facebook_reel(
            video_path=vp,
            caption=caption,
            thumbnail_path=thumb,
            publish_at=None,
        )
    if platform == "tiktok":
        from lol_agent.tiktok_publisher import upload_tiktok_short
        extra = item.get("extra", {})
        hashtags = extra.get("hashtags")
        if os.environ.get("TIKTOK_USE_WEB_STUDIO", "").strip() == "1":
            try:
                from lol_agent.tiktok_web_scheduler import schedule_tiktok_via_web_studio
                tag_str = " ".join(f"#{str(t).lstrip('#')}" for t in (hashtags or []) if t)
                web_caption = f"{caption} {tag_str}".strip() if tag_str else caption
                web_res = schedule_tiktok_via_web_studio(
                    video_path=vp,
                    caption=web_caption,
                    publish_at=None,
                    thumbnail_path=thumb,
                    headless=True,
                )
                if web_res.get("success"):
                    return web_res
            except Exception as _web_err:
                print(f"⚠️ [ScheduledQueue] TikTok Web fallback na API: {_web_err}")

        return upload_tiktok_short(
            video_path=vp,
            title=caption,
            hashtags=hashtags,
            privacy_level=extra.get("privacy_level", "PUBLIC_TO_EVERYONE"),
            publish_at=None,
            thumbnail_path=thumb,
            peak_moment=peak,
        )

    return {"success": False, "error": f"Nieobsługiwana platforma w kolejce: {platform}"}


def check_and_flush_scheduled_posts() -> int:
    """
    Sprawdza kolejkę zaplanowanych publikacji i wykonuje upload dla pozycji,
    których czas publikacji (publish_at) już nadszedł.
    Zapobiega podwójnej wysyłce (atomowy claim 'processing') i ponawia błędy sieci (3x co 5 min).
    """
    if not _FLUSH_EXEC_LOCK.acquire(blocking=False):
        return 0

    try:
        now_utc = datetime.now(timezone.utc)
        claimed_items: List[Dict[str, Any]] = []

        with _QUEUE_LOCK:
            items = _load_queue()
            if not items:
                return 0

            queue_dirty = _recover_stale_processing(items, now_utc)
            for item in items:
                if item.get("status") != "pending":
                    continue

                pub_dt = _parse_iso_utc(item.get("publish_at"))
                if pub_dt is None or now_utc < pub_dt:
                    continue

                next_retry_dt = _parse_iso_utc(item.get("next_retry_at"))
                if next_retry_dt is not None and now_utc < next_retry_dt:
                    continue

                vp = item.get("video_path")
                if not vp or not os.path.exists(vp):
                    item["status"] = "failed"
                    item["error"] = f"Plik wideo nie istnieje: {vp}"
                    item["failed_at"] = now_utc.isoformat()
                    queue_dirty = True
                    continue

                item["status"] = "processing"
                item["processing_started_at"] = now_utc.isoformat()
                queue_dirty = True
                claimed_items.append(dict(item))

            if queue_dirty:
                _save_queue(items)

        flushed_count = 0
        for item in claimed_items:
            item_id = item.get("id", "")
            platform = item.get("platform", "")
            vp = item.get("video_path", "")
            print(f"⏰ [ScheduledQueue] Uruchamiam zaplanowaną publikację dla {platform}: {Path(vp).name}")
            try:
                res = _execute_single_upload(item)
                if res.get("success"):
                    _persist_item_state(
                        item_id,
                        {
                            "status": "published",
                            "result": res,
                            "published_at": datetime.now(timezone.utc).isoformat(),
                        },
                        clear_keys=("processing_started_at", "next_retry_at", "last_error", "error"),
                    )
                    flushed_count += 1
                    print(
                        f"✅ [ScheduledQueue] {platform} opublikowany pomyślnie! "
                        f"ID/URL: {res.get('publish_id') or res.get('url')}"
                    )
                else:
                    _record_retry_or_fail(item, str(res.get("error") or "Unknown upload error"))
            except Exception as e:
                _record_retry_or_fail(item, str(e))

        return flushed_count
    finally:
        _FLUSH_EXEC_LOCK.release()
