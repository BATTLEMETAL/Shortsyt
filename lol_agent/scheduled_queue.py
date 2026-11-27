"""
Shortsyt — Moduł zarządzania kolejką zaplanowanych publikacji dla platform społecznościowych.
Umożliwia planowanie publikacji m.in. dla Instagram Reels (które nie posiadają natywnego parametru future timestamp w Meta API).
"""
import os
import json
import time
import threading
from contextlib import contextmanager
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
MIN_PLATFORM_FLUSH_GAP_MINUTES = 30


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
        except Exception as exc:
            print(f"[ScheduledQueue] [WARN] Błąd odczytu kolejki ({QUEUE_FILE}): {exc}")
            return []
    return []


def _save_queue(items: List[Dict[str, Any]]):
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = QUEUE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, QUEUE_FILE)
    try:
        try:
            from lol_agent.state_db import get_state_db_path, sync_queue_to_db
        except ImportError:
            from state_db import get_state_db_path, sync_queue_to_db
        sync_queue_to_db(items, db_path=get_state_db_path(QUEUE_FILE))
    except Exception:
        pass


def is_tiktok_inbox_result(platform: Optional[str], res: Any) -> bool:
    """Zwraca True, jeśli wynik publikacji TikTok trafił wyłącznie do INBOX (szkic na telefonie)."""
    if str(platform or "").strip().lower() != "tiktok":
        return False
    if not isinstance(res, dict):
        return False
    if bool(res.get("inbox")):
        return True
    if str(res.get("post_mode") or "").strip().lower() == "inbox":
        return True
    pub_id = str(res.get("publish_id") or "")
    return pub_id.startswith("v_inbox_file")


def summarize_queue_statuses(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """Zlicza wpisy kolejki z rozróżnieniem realnego `published` od `published_to_inbox`."""
    summary = {
        "total": 0,
        "pending": 0,
        "processing": 0,
        "published": 0,
        "published_to_inbox": 0,
        "failed": 0,
    }
    if not isinstance(items, list):
        return summary
    summary["total"] = len(items)
    for it in items:
        if not isinstance(it, dict):
            continue
        st = str(it.get("status") or "pending").strip()
        if st == "published_to_inbox" or (
            st == "published" and is_tiktok_inbox_result(it.get("platform"), it.get("result"))
        ):
            summary["published_to_inbox"] += 1
        elif st in summary:
            summary[st] += 1
    return summary


def count_recent_tiktok_inbox(items: List[Dict[str, Any]], days: int = 14) -> int:
    """Zlicza pozycje TikTok z ostatnich N dni, które trafiły do INBOX zamiast publikacji publicznej."""
    if not isinstance(items, list):
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    cnt = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("platform") or "").strip().lower() != "tiktok":
            continue
        st = str(it.get("status") or "").strip()
        if st != "published_to_inbox" and not (
            st == "published" and is_tiktok_inbox_result("tiktok", it.get("result"))
        ):
            continue
        dt = (
            _parse_iso_utc(it.get("published_at"))
            or _parse_iso_utc(it.get("publish_at"))
            or _parse_iso_utc(it.get("created_at"))
        )
        if dt is None or dt >= cutoff:
            cnt += 1
    return cnt


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
        "status": "pending",  # 'pending' | 'processing' | 'published' | 'published_to_inbox' | 'failed'
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
        if "TIKTOK_USE_WEB_STUDIO" not in os.environ and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from dotenv import load_dotenv
                load_dotenv(ROOT_DIR / ".env", override=False)
            except Exception:
                pass
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
                print(
                    f"⚠️ [ScheduledQueue] TikTok Web nie powiódł się "
                    f"({web_res.get('error') or 'brak powodu'}) -> fallback na TikTok API"
                )
            except Exception as _web_err:
                print(f"⚠️ [ScheduledQueue] TikTok Web fallback na API: {_web_err}")

        return upload_tiktok_short(
            video_path=vp,
            title=caption,
            hashtags=hashtags,
            privacy_level=extra.get("privacy_level", "PUBLIC_TO_EVERYONE"),
            disable_comment=bool(extra.get("disable_comment", False)),
            disable_duet=bool(extra.get("disable_duet", False)),
            disable_stitch=bool(extra.get("disable_stitch", False)),
            brand_organic_toggle=bool(extra.get("brand_organic_toggle", False)),
            brand_content_toggle=bool(extra.get("brand_content_toggle", False)),
            post_mode=str(extra.get("post_mode") or "direct"),
            publish_at=None,
            thumbnail_path=thumb,
            peak_moment=peak,
        )

    return {"success": False, "error": f"Nieobsługiwana platforma w kolejce: {platform}"}


@contextmanager
def _acquire_process_flush_lock(lock_path: Path):
    """Międzyprocesowa nieblokująca blokada plikowa zapobiegająca równoległemu flushowi tej samej kolejki."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = None
    locked = False
    try:
        fh = open(lock_path, "a+b")
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"1")
            fh.flush()
        fh.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
    except OSError:
        locked = False

    try:
        yield locked
    finally:
        if locked and fh is not None:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass


def _norm_video_key(platform: Optional[str], video_path: Optional[str]) -> Optional[tuple]:
    """Zwraca znormalizowany klucz (platforma, ścieżka_wideo) do wykrywania duplikatów."""
    plat = str(platform or "").strip().lower()
    vp = str(video_path or "").strip()
    if not plat or not vp:
        return None
    try:
        resolved = str(Path(vp).resolve()).lower()
    except Exception:
        resolved = vp.lower()
    return (plat, resolved)


def check_and_flush_scheduled_posts() -> int:
    """
    Sprawdza kolejkę zaplanowanych publikacji i wykonuje upload dla pozycji,
    których czas publikacji (publish_at) już nadszedł.
    Zapobiega podwójnej wysyłce (lock międzyprocesowy + deduplikacja (platform, video_path)),
    wymusza odstęp MIN_PLATFORM_FLUSH_GAP_MINUTES po wybudzeniu PC i ponawia błędy sieci (3x co 5 min).
    """
    if not _FLUSH_EXEC_LOCK.acquire(blocking=False):
        return 0

    try:
        with _acquire_process_flush_lock(QUEUE_FILE.with_suffix(".lock")) as proc_locked:
            if not proc_locked:
                return 0

            now_utc = datetime.now(timezone.utc)
            claimed_items: List[Dict[str, Any]] = []

            with _QUEUE_LOCK:
                items = _load_queue()
                if not items:
                    return 0

                queue_dirty = _recover_stale_processing(items, now_utc)

                published_keys = set()
                last_pub_by_platform: Dict[str, datetime] = {}
                for it in items:
                    if it.get("status") not in ("published", "published_to_inbox"):
                        continue
                    k = _norm_video_key(it.get("platform"), it.get("video_path"))
                    if k:
                        published_keys.add(k)
                    p_name = str(it.get("platform") or "").strip().lower()
                    p_dt = _parse_iso_utc(it.get("published_at")) or _parse_iso_utc(it.get("publish_at"))
                    if p_name and p_dt and p_dt <= now_utc:
                        prev_dt = last_pub_by_platform.get(p_name)
                        if prev_dt is None or p_dt > prev_dt:
                            last_pub_by_platform[p_name] = p_dt

                claimed_keys = set()
                gap_delta = timedelta(minutes=MIN_PLATFORM_FLUSH_GAP_MINUTES)

                for item in items:
                    if item.get("status") != "pending":
                        continue

                    pub_dt = _parse_iso_utc(item.get("publish_at"))
                    if pub_dt is None or now_utc < pub_dt:
                        continue

                    next_retry_dt = _parse_iso_utc(item.get("next_retry_at"))
                    if next_retry_dt is not None and now_utc < next_retry_dt:
                        continue

                    v_key = _norm_video_key(item.get("platform"), item.get("video_path"))
                    if v_key and (v_key in published_keys or v_key in claimed_keys):
                        item["status"] = "skipped_duplicate"
                        item["skipped_at"] = now_utc.isoformat()
                        item["error"] = "Duplikat już opublikowany"
                        item.pop("next_retry_at", None)
                        queue_dirty = True
                        print(f"🛑 [ScheduledQueue] Pominięto duplikat {item.get('platform')}: {Path(str(item.get('video_path'))).name}")
                        continue

                    plat_name = str(item.get("platform") or "").strip().lower()
                    last_plat_dt = last_pub_by_platform.get(plat_name)
                    if last_plat_dt is not None and (now_utc - last_plat_dt) < gap_delta:
                        deferred_until = (last_plat_dt + gap_delta).isoformat()
                        if item.get("next_retry_at") != deferred_until:
                            item["next_retry_at"] = deferred_until
                            item["last_error"] = f"Odstęp anty-spamowy {MIN_PLATFORM_FLUSH_GAP_MINUTES} min per platforma"
                            queue_dirty = True
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
                    if v_key:
                        claimed_keys.add(v_key)
                    if plat_name:
                        last_pub_by_platform[plat_name] = now_utc
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
                        is_inbox = is_tiktok_inbox_result(platform, res)
                        _persist_item_state(
                            item_id,
                            {
                                "status": "published_to_inbox" if is_inbox else "published",
                                "delivery_mode": "inbox_draft" if is_inbox else "public",
                                "requires_manual_publish": is_inbox,
                                "result": res,
                                "published_at": datetime.now(timezone.utc).isoformat(),
                            },
                            clear_keys=("processing_started_at", "next_retry_at", "last_error", "error"),
                        )
                        try:
                            from lol_agent.viral_vault import stage_short_original
                            extra_m = item.get("extra") if isinstance(item.get("extra"), dict) else {}
                            src_orig = extra_m.get("source_path")
                            if not src_orig and vp:
                                meta_p = Path(vp).with_suffix(".meta.json")
                                if meta_p.is_file():
                                    src_orig = json.loads(meta_p.read_text(encoding="utf-8", errors="ignore")).get("source_path")
                            if src_orig:
                                stage_short_original(
                                    src_orig,
                                    yt_video_id=str(res.get("video_id") or ""),
                                    metadata={**extra_m, "title": item.get("caption", "")},
                                )
                        except Exception as exc:
                            print(f"[ScheduledQueue] [WARN] Viral vault stage pominięte ({vp}): {exc}")
                        try:
                            from lol_agent.temp_cleaner import cleanup_published_video_if_idle
                            clean_res = cleanup_published_video_if_idle(vp, queue_file=QUEUE_FILE)
                            if clean_res.get("deleted"):
                                print(
                                    f"🧹 [ScheduledQueue] Usunięto opublikowany plik .mp4 po wyczyszczeniu kolejki: "
                                    f"{Path(vp).name} (-{clean_res.get('freed_mb', 0):.1f} MB)"
                                )
                        except Exception as exc:
                            print(f"[ScheduledQueue] [WARN] Auto-czyszczenie .mp4 pominięte ({vp}): {exc}")
                        flushed_count += 1
                        if is_inbox:
                            print(
                                f"⚠️ [ScheduledQueue] TikTok wysłany do INBOX (szkic w aplikacji na telefonie — "
                                f"wymaga ręcznej publikacji), publish_id={res.get('publish_id')}"
                            )
                        else:
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
