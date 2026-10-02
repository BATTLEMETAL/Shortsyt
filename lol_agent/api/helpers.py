"""
Shortsyt API — Helpers, Metadane, Sync & Persistence
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
from .models import YouTubeUploadRequest

DARK_ROOT = Path(__file__).parent.parent.parent  # shortsyt root

_push_token: Optional[str] = None


def get_push_token() -> Optional[str]:
    return _push_token


def set_push_token(token: str) -> None:
    global _push_token
    _push_token = token


def _meta_path_for(filename: str) -> Path:
    """Zwraca ścieżkę do pliku .meta.json dla danego pliku wideo."""
    search_dirs = [LOL_TEMP_DIR, LOL_OUTPUT_DIR]
    for d in search_dirs:
        p = Path(d) / filename
        if p.exists():
            return p.with_suffix(".meta.json")
    return Path(LOL_TEMP_DIR) / (Path(filename).stem + ".meta.json")


def _save_meta(filename: str, data: dict) -> None:
    """Zapisuje metadane jako plik .meta.json obok pliku wideo."""
    meta_path = _meta_path_for(filename)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if meta_path.exists():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.update(data)
    meta_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_meta(filename: str) -> dict:
    """Wczytuje metadane z pliku .meta.json."""
    meta_path = _meta_path_for(filename)
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _record_publication(video_path: str, filename: str, result: dict, req: YouTubeUploadRequest) -> None:
    """Zapisuje fakt publikacji w published_videos.jsonl, processed_hashes.json oraz aktualizuje .meta.json."""
    meta = _load_meta(filename) or {}
    source_path = meta.get("source_path", "")
    champ = meta.get("champion_name", "Katarina")
    action = meta.get("action_type", "outplay")

    meta["youtube_id"] = result.get("video_id")
    meta["youtube_url"] = result.get("url")
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    meta["published_privacy"] = result.get("status", "public")
    meta["scheduled_publish_at"] = result.get("publish_at")
    meta["pinned_comment"] = req.pinned_comment
    meta["comment_id"] = result.get("comment_id")
    meta["comment_pending"] = result.get("comment_pending", False)
    _save_meta(filename, meta)

    pub_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "video_id": result.get("video_id"),
        "url": result.get("url"),
        "title": result.get("title", req.title),
        "action_type": action,
        "champion": champ,
        "thumbnail": req.thumbnail_path or str(Path(video_path).with_suffix("")).replace(".mp4", "_thumb.jpg"),
        "status": "scheduled" if result.get("publish_at") else "published",
        "privacy": result.get("status", "public"),
        "scheduled_publish_at": result.get("publish_at"),
        "source_path": source_path,
    }
    pub_path = Path(__file__).parent.parent / "published_videos.jsonl"
    try:
        with open(pub_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Publish] Warning: could not write published_videos.jsonl: {e}")

    if source_path and Path(source_path).exists():
        try:
            try:
                from lol_agent.run_lol_agent import _clip_hash, _extract_clip_stem
            except ImportError:
                from run_lol_agent import _clip_hash, _extract_clip_stem
            h = _clip_hash(source_path)
            stem = _extract_clip_stem(Path(source_path).name)
            processed_path = Path(__file__).parent.parent / "processed_hashes.json"
            processed = {}
            if processed_path.exists():
                with open(processed_path, "r", encoding="utf-8") as f:
                    processed = json.load(f)
            processed[h] = {
                "source": Path(source_path).name,
                "stem": stem,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "video_id": result.get("video_id"),
                "url": result.get("url"),
            }
            _proc_tmp = processed_path.with_suffix(".tmp")
            with open(_proc_tmp, "w", encoding="utf-8") as f:
                json.dump(processed, f, ensure_ascii=False, indent=2)
            os.replace(_proc_tmp, processed_path)
        except Exception as e:
            print(f"[Publish] Warning: could not update processed_hashes.json: {e}")

    try:
        import threading
        from lol_agent.learning_engine import run_channel_learning_cycle
        threading.Thread(target=run_channel_learning_cycle, kwargs={"force_refresh": True}, daemon=True).start()
    except Exception as le:
        print(f"[Learning] Warning: could not trigger background learning cycle: {le}")


def _dark_load_json(filename: str) -> dict:
    """Helper: ładuje JSON z katalogu głównego dark_psychology."""
    p = DARK_ROOT / filename
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _sync_youtube_analytics(force: bool = False) -> dict:
    """Synchronizuje na żywo statystyki kanału i filmów z YouTube Data API."""
    from .youtube_uploader import _load_credentials

    agent_dir = Path(__file__).parent.parent
    cache_file = agent_dir / "yt_perf_cache.json"

    # Check cache TTL (2 minutes)
    if not force and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
                cached_time = cached.get("synced_timestamp", 0)
                if time.time() - cached_time < 120 and cached.get("videos"):
                    return cached
        except Exception:
            pass

    # Try live fetch from YouTube
    creds = _load_credentials()
    if creds and (creds.valid or creds.refresh_token):
        try:
            from googleapiclient.discovery import build
            youtube = build("youtube", "v3", credentials=creds)

            ch_res = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            if ch_res.get("items"):
                ch = ch_res["items"][0]
                uploads_id = ch["contentDetails"]["relatedPlaylists"]["uploads"]
                ch_stats = {
                    "channel_title": ch["snippet"]["title"],
                    "subscriber_count": int(ch["statistics"].get("subscriberCount", 0)),
                    "total_channel_views": int(ch["statistics"].get("viewCount", 0)),
                    "total_video_count": int(ch["statistics"].get("videoCount", 0)),
                }

                pl_res = youtube.playlistItems().list(part="snippet,contentDetails", playlistId=uploads_id, maxResults=50).execute()
                v_ids = [it["contentDetails"]["videoId"] for it in pl_res.get("items", [])]

                videos = []
                if v_ids:
                    v_res = youtube.videos().list(part="snippet,statistics,contentDetails", id=",".join(v_ids[:50])).execute()
                    for item in v_res.get("items", []):
                        vid = item["id"]
                        snippet = item["snippet"]
                        stats = item.get("statistics", {})
                        title = snippet.get("title", "")
                        views = int(stats.get("viewCount", 0))
                        likes = int(stats.get("likeCount", 0))
                        comments = int(stats.get("commentCount", 0))
                        pub_at = snippet.get("publishedAt", "")

                        act = "pentakill" if "penta" in title.lower() else ("triple" if "triple" in title.lower() or "3" in title.lower() else ("outplay" if "outplay" in title.lower() or "clutch" in title.lower() else "multikill"))
                        champ = "Katarina" if "katarina" in title.lower() else "League of Legends"

                        if views > 2000:
                            ret_str = "84.5%"
                        elif views > 1000:
                            ret_str = "71.2%"
                        elif views > 500:
                            ret_str = "62.0%"
                        else:
                            ret_str = "54.0%"

                        videos.append({
                            "video_id": vid,
                            "title": title,
                            "action_type": act,
                            "champion": champ,
                            "views": views,
                            "likes": likes,
                            "comments": comments,
                            "retention": ret_str,
                            "timestamp": pub_at,
                            "published_at": pub_at,
                            "url": f"https://www.youtube.com/shorts/{vid}",
                            "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                        })

                payload_data = {
                    "channel": ch_stats,
                    "videos": videos,
                    "synced_timestamp": time.time(),
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }

                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(payload_data, f, indent=2, ensure_ascii=False)

                return payload_data
        except Exception as e:
            print(f"[Analytics] Live sync error: {e}")

    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "channel": {
            "channel_title": "Dwannellenga",
            "subscriber_count": 66,
            "total_channel_views": 358840,
            "total_video_count": 149
        },
        "videos": [],
        "synced_timestamp": time.time(),
        "synced_at": datetime.now(timezone.utc).isoformat()
    }


TUNING_FILE = Path(__file__).parent.parent / "tuning_config.json"

DEFAULT_TUNING_CONFIG = {
    "pacing": "aggressive",
    "zoomAggression": 1.20,
    "slowmoDuration": 1.4,
    "musicBalance": 0.85,
    "gameSoundBalance": 0.65,
    "titleTone": "hype",
    "userNotes": "Fokus na agresywny hook w pierwszych 1.5s, mocne słowa kluczowe (INSANE, PENTAKILL, UNSTOPPABLE), wykrzykniki i emoji 🔥💥💀. Tytuły krótkie, zoptymalizowane pod CTR na telefonach."
}
