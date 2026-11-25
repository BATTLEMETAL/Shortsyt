"""
Shortsyt — Platform Feedback Collector (Multi-Platform Closed Feedback Loop).
Zbiera realne wyniki (wyświetlenia, retencja, polubienia, udostępnienia) z:
  1. YouTube Data API + YouTube Analytics API (views, retention, avgViewDuration)
  2. Instagram Graph API (reach, interactions, likes, comments, saves)
  3. Facebook Graph API (views, reactions, comments, shares)
  4. TikTok API (status publikacji, zapytanie o stan)

Aktualizuje bazy wiedzy w accounts/learning_states/ (learning_youtube.json,
learning_instagram.json, learning_facebook.json, learning_tiktok.json)
oraz sprzęga się z learning_directive.json dla generatora metadanych i montażu.
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import pickle
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
LEARNING_STATES_DIR = ACCOUNTS_DIR / "learning_states"
PUB_LOG_FILE = ROOT_DIR / "lol_agent" / "published_videos.jsonl"
TOKEN_PICKLE = ACCOUNTS_DIR / "lol_token.pickle"
IG_TOKEN_FILE = ACCOUNTS_DIR / "instagram_token.json"
FB_TOKEN_FILE = ACCOUNTS_DIR / "facebook_token.json"
TT_TOKEN_FILE = ACCOUNTS_DIR / "tiktok_token.json"

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


# ─── YouTube Metrics Fetcher ──────────────────────────────────────────────────

def fetch_youtube_video_metrics(video_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera wyświetlenia, polubienia i retencję dla filmu z YouTube API."""
    if not TOKEN_PICKLE.exists():
        return None

    try:
        from googleapiclient.discovery import build
        with open(TOKEN_PICKLE, "rb") as f:
            creds = pickle.load(f)

        yt = build("youtube", "v3", credentials=creds)

        # 1. Statystyki podstawowe (Data API)
        resp = yt.videos().list(part="snippet,statistics,contentDetails", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return None

        stat = items[0].get("statistics", {})
        snippet = items[0].get("snippet", {})
        views = int(stat.get("viewCount", 0))
        likes = int(stat.get("likeCount", 0))
        comments = int(stat.get("commentCount", 0))

        # 2. Retencja i czas oglądania (YouTube Analytics API)
        avg_view_duration = 0
        est_minutes = 0
        try:
            ch_resp = yt.channels().list(part="id", mine=True).execute()
            ch_id = ch_resp["items"][0]["id"]

            yta = build("youtubeAnalytics", "v2", credentials=creds)
            # Okno zapytania: od daty publikacji do dziś
            published_at = snippet.get("publishedAt", "")[:10] or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            today = datetime.now().strftime("%Y-%m-%d")

            an_resp = yta.reports().query(
                ids=f"channel=={ch_id}",
                startDate=published_at,
                endDate=today,
                metrics="views,estimatedMinutesWatched,averageViewDuration",
                filters=f"video=={video_id}"
            ).execute()

            rows = an_resp.get("rows", [])
            if rows and len(rows[0]) >= 4:
                est_minutes = float(rows[0][2])
                avg_view_duration = float(rows[0][3])
        except Exception as an_err:
            pass  # Analytics API może jeszcze nie mieć zagregowanych danych (<24h)

        return {
            "platform": "youtube",
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "views": views,
            "likes": likes,
            "comments": comments,
            "avg_view_duration": avg_view_duration,
            "estimated_minutes_watched": est_minutes,
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"⚠️ Błąd pobierania metryk YT dla {video_id}: {e}")
        return None


# ─── Instagram Metrics Fetcher ────────────────────────────────────────────────

def fetch_instagram_reel_metrics(media_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera zasięg, wyświetlenia i interakcje dla Reels z Instagram Graph API."""
    if not IG_TOKEN_FILE.exists():
        return None

    try:
        data = json.loads(IG_TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        if not token:
            return None

        # 1. Podstawowe liczniki (likes, comments)
        media_url = f"{GRAPH_API_BASE}/{media_id}"
        m_resp = requests.get(
            media_url,
            params={"fields": "like_count,comments_count,permalink,caption", "access_token": token},
            timeout=10
        ).json()

        likes = int(m_resp.get("like_count", 0))
        comments = int(m_resp.get("comments_count", 0))

        # 2. Insights (reach, interactions, plays)
        reach = 0
        total_interactions = 0
        plays = 0
        try:
            ins_url = f"{GRAPH_API_BASE}/{media_id}/insights"
            ins_resp = requests.get(
                ins_url,
                params={"metric": "reach,total_interactions,plays,likes,shares,saved", "access_token": token},
                timeout=10
            ).json()

            for item in ins_resp.get("data", []):
                val = item.get("values", [{}])[0].get("value", 0) if item.get("values") else item.get("total_value", {}).get("value", 0)
                name = item.get("name")
                if name == "reach":
                    reach = int(val)
                elif name == "total_interactions":
                    total_interactions = int(val)
                elif name == "plays":
                    plays = int(val)
        except Exception:
            pass

        return {
            "platform": "instagram",
            "media_id": media_id,
            "permalink": m_resp.get("permalink", ""),
            "likes": likes,
            "comments": comments,
            "reach": reach,
            "total_interactions": total_interactions,
            "plays": plays,
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"⚠️ Błąd pobierania metryk IG dla {media_id}: {e}")
        return None


# ─── Facebook Metrics Fetcher ─────────────────────────────────────────────────

def fetch_facebook_reel_metrics(video_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera wyświetlenia, reakcje i udostępnienia dla posta na Facebook Page."""
    if not FB_TOKEN_FILE.exists():
        return None

    try:
        data = json.loads(FB_TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        if not token:
            return None

        url = f"{GRAPH_API_BASE}/{video_id}"
        resp = requests.get(
            url,
            params={
                "fields": "views,description,permalink_url,reactions.summary(true),comments.summary(true),shares",
                "access_token": token
            },
            timeout=10
        ).json()

        if "error" in resp:
            return None

        reactions = resp.get("reactions", {}).get("summary", {}).get("total_count", 0)
        comments = resp.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = resp.get("shares", {}).get("count", 0)
        views = int(resp.get("views", 0))

        return {
            "platform": "facebook",
            "video_id": video_id,
            "permalink_url": resp.get("permalink_url", ""),
            "views": views,
            "reactions": reactions,
            "comments": comments,
            "shares": shares,
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"⚠️ Błąd pobierania metryk FB dla {video_id}: {e}")
        return None


# ─── TikTok Status Query ──────────────────────────────────────────────────────

def fetch_tiktok_metrics(publish_id: str) -> Optional[Dict[str, Any]]:
    """Sprawdza status publikacji filmu na TikTok."""
    if not TT_TOKEN_FILE.exists() or not publish_id:
        return None

    try:
        data = json.loads(TT_TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        if not token:
            return None

        url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, json={"publish_id": publish_id}, timeout=10).json()

        st = resp.get("data", {}).get("status", "UNKNOWN")
        return {
            "platform": "tiktok",
            "publish_id": publish_id,
            "status": st,
            "fail_reason": resp.get("data", {}).get("fail_reason"),
            "fetched_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        print(f"⚠️ Błąd odpytania statusu TikTok dla {publish_id}: {e}")
        return None


# ─── Learning States Ingestion ────────────────────────────────────────────────

def _update_learning_file(filename: str, updater_fn) -> None:
    """Bezpiecznie wczytuje, modyfikuje i zapisuje plik learning_*.json."""
    LEARNING_STATES_DIR.mkdir(parents=True, exist_ok=True)
    target = LEARNING_STATES_DIR / filename
    if not target.exists():
        data = {"_schema_version": 1, "videos_analysed": 0, "updated_at": None}
    else:
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            data = {"_schema_version": 1, "videos_analysed": 0, "updated_at": None}

    data = updater_fn(data)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ingest_youtube_metric(metric: Dict[str, Any], action_type: str, pub_ts: Optional[str] = None) -> None:
    """Aktualizuje learning_youtube.json o nowe wyniki z YouTube (w tym Peak Hours)."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        data["videos_analysed"] = data.get("videos_analysed", 0) + 1
        views = metric.get("views", 0)
        title = metric.get("title", "")

        # Top / worst performers
        top = data.setdefault("title_patterns", {}).setdefault("top_performers", [])
        if views > 100:
            top.append({"title": title, "views": views, "retention_sec": metric.get("avg_view_duration", 0)})
            top.sort(key=lambda x: x.get("views", 0), reverse=True)
            data["title_patterns"]["top_performers"] = top[:10]

        # Wagi akcji
        if action_type:
            weights = data.setdefault("action_type_weights", {})
            cur = weights.get(action_type.lower(), 1.0)
            if views > 1000:
                weights[action_type.lower()] = round(min(2.0, cur + 0.05), 3)
            elif views < 50 and views > 0:
                weights[action_type.lower()] = round(max(0.7, cur - 0.02), 3)

        # ── Peak Hours Correlation (Uczenie najlepszej godziny publikacji w Europe/Warsaw) ──
        if pub_ts:
            try:
                from zoneinfo import ZoneInfo
                tz_pl = ZoneInfo("Europe/Warsaw")
            except Exception:
                tz_pl = timezone(timedelta(hours=1))
            try:
                clean_ts = str(pub_ts).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_pl = dt.astimezone(tz_pl)
                hour = str(dt_pl.hour)
                hour_stats = data.setdefault("publish_time", {}).setdefault("hour_stats", {})
                h_entry = hour_stats.setdefault(hour, {"views_total": 0, "count": 0, "avg_views": 0.0})
                h_entry["views_total"] += views
                h_entry["count"] += 1
                h_entry["avg_views"] = round(h_entry["views_total"] / h_entry["count"], 1)

                reliable_hours = [(h, st) for h, st in hour_stats.items() if st.get("count", 0) >= 3]
                pool = reliable_hours if reliable_hours else list(hour_stats.items())
                best_h = max(pool, key=lambda x: x[1].get("avg_views", 0.0))[0]
                data["publish_time"]["best_hour"] = int(best_h)
            except Exception:
                pass

        return data

    _update_learning_file("learning_youtube.json", _updater)


def ingest_instagram_metric(metric: Dict[str, Any], action_type: str, pub_ts: Optional[str] = None) -> None:
    """Aktualizuje learning_instagram.json o zasięgi i interakcje Reels."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        data["videos_analysed"] = data.get("videos_analysed", 0) + 1
        entries = data.setdefault("metrics_collected", {}).setdefault("entries", [])
        entries.append(metric)
        data["metrics_collected"]["entries"] = entries[-20:]  # Ostatnie 20
        return data

    _update_learning_file("learning_instagram.json", _updater)


def ingest_facebook_metric(metric: Dict[str, Any], action_type: str, pub_ts: Optional[str] = None) -> None:
    """Aktualizuje learning_facebook.json o reakcje, komentarze i godziny (Europe/Warsaw)."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        data["videos_analysed"] = data.get("videos_analysed", 0) + 1
        entries = data.setdefault("metrics_collected", {}).setdefault("entries", [])
        entries.append(metric)
        data["metrics_collected"]["entries"] = entries[-20:]

        if pub_ts:
            try:
                from zoneinfo import ZoneInfo
                tz_pl = ZoneInfo("Europe/Warsaw")
            except Exception:
                tz_pl = timezone(timedelta(hours=1))
            try:
                clean_ts = str(pub_ts).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_pl = dt.astimezone(tz_pl)
                hour = str(dt_pl.hour)
                day_name = dt_pl.strftime("%A")
                stats = data.setdefault("best_post_time", {}).setdefault("day_hour_stats", {})
                key = f"{day_name}_{hour}:00"
                e = stats.setdefault(key, {"views_total": 0, "count": 0, "avg_views": 0.0})
                e["views_total"] += metric.get("views", 0)
                e["count"] += 1
                e["avg_views"] = round(e["views_total"] / e["count"], 1)

                reliable_keys = [(k, st) for k, st in stats.items() if st.get("count", 0) >= 3]
                pool = reliable_keys if reliable_keys else list(stats.items())
                best_k = max(pool, key=lambda x: x[1].get("avg_views", 0.0))[0]
                best_day_part, best_hour_part = best_k.rsplit("_", 1)
                data["best_post_time"]["best_hour"] = int(best_hour_part.split(":")[0])
                data["best_post_time"]["best_day"] = best_day_part
            except Exception:
                pass

        return data

    _update_learning_file("learning_facebook.json", _updater)


# ─── Główna Pętla Zwrotna (Automated Loop) ─────────────────────────────────────

def collect_all_platform_metrics(max_videos: int = 15) -> Dict[str, Any]:
    """
    Skanuje published_videos.jsonl i zbiera metryki dla wszystkich platform.
    Zwraca raport podsumowujący.
    """
    if not PUB_LOG_FILE.exists():
        return {"status": "no_pub_log", "analysed": 0}

    print("\n📊 [Feedback Loop] Rozpoczynam zbieranie metryk ze wszystkich platform...")

    entries: List[Dict[str, Any]] = []
    try:
        with open(PUB_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    except Exception as e:
        print(f"⚠️ Błąd odczytu {PUB_LOG_FILE}: {e}")
        return {"status": "error", "error": str(e)}

    if not entries:
        print("ℹ️ Brak opublikowanych filmów w logu.")
        return {"status": "empty_log", "analysed": 0}

    # Bierzemy ostatnie max_videos filmów
    recent_entries = entries[-max_videos:]
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checked": len(recent_entries),
        "youtube_updated": 0,
        "instagram_updated": 0,
        "facebook_updated": 0,
        "tiktok_queried": 0,
    }

    for item in recent_entries:
        action_type = item.get("action_type", "outplay")
        pub_ts = item.get("timestamp")

        # 1. YouTube
        yt_id = item.get("video_id")
        if yt_id:
            yt_metric = fetch_youtube_video_metrics(yt_id)
            if yt_metric:
                ingest_youtube_metric(yt_metric, action_type, pub_ts=pub_ts)
                report["youtube_updated"] += 1
                print(f"   📺 YT [{yt_id}]: {yt_metric['views']} views, {yt_metric['likes']} likes")

        # 2. Instagram
        ig_id = item.get("instagram_media_id")
        if ig_id:
            ig_metric = fetch_instagram_reel_metrics(ig_id)
            if ig_metric:
                ingest_instagram_metric(ig_metric, action_type, pub_ts=pub_ts)
                report["instagram_updated"] += 1
                print(f"   📸 IG [{ig_id}]: reach={ig_metric['reach']}, likes={ig_metric['likes']}")

        # 3. Facebook
        fb_id = item.get("facebook_video_id")
        if fb_id:
            fb_metric = fetch_facebook_reel_metrics(fb_id)
            if fb_metric:
                ingest_facebook_metric(fb_metric, action_type, pub_ts=pub_ts)
                report["facebook_updated"] += 1
                print(f"   📘 FB [{fb_id}]: views={fb_metric['views']}, reactions={fb_metric['reactions']}")

        # 4. TikTok
        tt_id = item.get("tiktok_publish_id")
        if tt_id:
            tt_metric = fetch_tiktok_metrics(tt_id)
            if tt_metric:
                report["tiktok_queried"] += 1
                print(f"   🚀 TikTok [{tt_id}]: status={tt_metric.get('status')}")

    print(f"✅ [Feedback Loop] Zakończono! Zaktualizowano bazy learning_states:")
    print(f"   YT: {report['youtube_updated']} | IG: {report['instagram_updated']} | FB: {report['facebook_updated']} | TT: {report['tiktok_queried']}")

    return report


if __name__ == "__main__":
    collect_all_platform_metrics()
