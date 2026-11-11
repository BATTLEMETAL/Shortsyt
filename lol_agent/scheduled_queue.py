"""
Shortsyt — Moduł zarządzania kolejką zaplanowanych publikacji dla platform społecznościowych.
Umożliwia planowanie publikacji m.in. dla Instagram Reels (które nie posiadają natywnego parametru future timestamp w Meta API).
"""
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT_DIR / "accounts"
QUEUE_FILE = ACCOUNTS_DIR / "scheduled_social_queue.json"


def _load_queue() -> List[Dict[str, Any]]:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_queue(items: List[Dict[str, Any]]):
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
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
    """Rejestruje zaplanowaną publikację w kolejce."""
    items = _load_queue()
    entry = {
        "id": f"{platform}_{int(time.time()*1000)}",
        "platform": platform,
        "video_path": str(Path(video_path).resolve()),
        "caption": caption,
        "publish_at": publish_at,
        "thumbnail_path": str(Path(thumbnail_path).resolve()) if thumbnail_path and os.path.exists(thumbnail_path) else None,
        "peak_moment": peak_moment,
        "status": "pending",  # 'pending' | 'published' | 'failed'
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extra": extra or {}
    }
    items.append(entry)
    _save_queue(items)
    return entry


def check_and_flush_scheduled_posts() -> int:
    """
    Sprawdza kolejkę zaplanowanych publikacji i wykonuje upload dla pozycji,
    których czas publikacji (publish_at) już nadszedł.
    Zwraca liczbę zrealizowanych publikacji.
    """
    items = _load_queue()
    if not items:
        return 0

    now_utc = datetime.now(timezone.utc)
    flushed_count = 0
    modified = False

    for item in items:
        if item.get("status") != "pending":
            continue

        pub_at_str = item.get("publish_at")
        if not pub_at_str:
            continue

        try:
            pub_dt = datetime.fromisoformat(pub_at_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # Czy nadszedł czas publikacji?
        if now_utc >= pub_dt:
            platform = item.get("platform")
            vp = item.get("video_path")
            caption = item.get("caption", "")
            thumb = item.get("thumbnail_path")
            peak = item.get("peak_moment")

            if not vp or not os.path.exists(vp):
                item["status"] = "failed"
                item["error"] = f"Plik wideo nie istnieje: {vp}"
                modified = True
                continue

            print(f"⏰ [ScheduledQueue] Uruchamiam zaplanowaną publikację dla {platform}: {Path(vp).name}")
            try:
                if platform == "instagram":
                    from lol_agent.instagram_publisher import upload_instagram_reel
                    res = upload_instagram_reel(
                        video_path=vp,
                        caption=caption,
                        thumbnail_path=thumb,
                        peak_moment=peak,
                        publish_at=None  # bezpośrednia publikacja teraz
                    )
                    if res.get("success"):
                        item["status"] = "published"
                        item["result"] = res
                        item["published_at"] = datetime.now(timezone.utc).isoformat()
                        flushed_count += 1
                        print(f"✅ [ScheduledQueue] Instagram Reel opublikowany pomyślnie! URL: {res.get('url')}")
                    else:
                        item["status"] = "failed"
                        item["error"] = res.get("error")
                elif platform == "facebook":
                    from lol_agent.facebook_publisher import upload_facebook_reel
                    res = upload_facebook_reel(
                        video_path=vp,
                        caption=caption,
                        thumbnail_path=thumb,
                        publish_at=None
                    )
                    if res.get("success"):
                        item["status"] = "published"
                        item["result"] = res
                        item["published_at"] = datetime.now(timezone.utc).isoformat()
                        flushed_count += 1
                        print(f"✅ [ScheduledQueue] Facebook Reel opublikowany pomyślnie! URL: {res.get('url')}")
                    else:
                        item["status"] = "failed"
                        item["error"] = res.get("error")
                elif platform == "tiktok":
                    from lol_agent.tiktok_publisher import upload_tiktok_short
                    extra = item.get("extra", {})
                    hashtags = extra.get("hashtags")
                    res = upload_tiktok_short(
                        video_path=vp,
                        title=caption,
                        hashtags=hashtags,
                        privacy_level=extra.get("privacy_level", "PUBLIC_TO_EVERYONE"),
                        publish_at=None
                    )
                    if res.get("success"):
                        item["status"] = "published"
                        item["result"] = res
                        item["published_at"] = datetime.now(timezone.utc).isoformat()
                        flushed_count += 1
                        print(f"✅ [ScheduledQueue] TikTok Short opublikowany pomyślnie! Publish ID: {res.get('publish_id')}")
                    else:
                        item["status"] = "failed"
                        item["error"] = res.get("error")
                modified = True
            except Exception as e:
                item["status"] = "failed"
                item["error"] = str(e)
                modified = True
                print(f"❌ [ScheduledQueue] Błąd wykonania zaplanowanej publikacji ({platform}): {e}")

    if modified:
        _save_queue(items)

    return flushed_count
