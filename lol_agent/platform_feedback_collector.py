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
SCHEDULED_QUEUE_FILE = ACCOUNTS_DIR / "scheduled_social_queue.json"
_DEFAULT_PUB_LOG_FILE = PUB_LOG_FILE
_DEFAULT_SCHEDULED_QUEUE_FILE = SCHEDULED_QUEUE_FILE
TOKEN_PICKLE = ACCOUNTS_DIR / "lol_token.pickle"
IG_TOKEN_FILE = ACCOUNTS_DIR / "instagram_token.json"
FB_TOKEN_FILE = ACCOUNTS_DIR / "facebook_token.json"
TT_TOKEN_FILE = ACCOUNTS_DIR / "tiktok_token.json"

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

try:
    from lol_agent.social_analytics import _parse_ig_insights_rows as _shared_parse_ig_insights
except ImportError:
    from social_analytics import _parse_ig_insights_rows as _shared_parse_ig_insights  # type: ignore


# ─── YouTube Metrics Fetcher ──────────────────────────────────────────────────

def _extract_yta_video_metrics_row(an_resp: Dict[str, Any]) -> Tuple[float, float]:
    """Wyciąga (estimatedMinutesWatched, averageViewDuration) po columnHeaders z bezpiecznym fallbackiem 3-kolumnowym."""
    rows = an_resp.get("rows") or []
    if not rows or not isinstance(rows[0], (list, tuple)):
        return 0.0, 0.0
    row = rows[0]
    headers = [str(h.get("name") or "") for h in (an_resp.get("columnHeaders") or []) if isinstance(h, dict)]
    if headers:
        col_map = {name: idx for idx, name in enumerate(headers) if idx < len(row)}
        if "estimatedMinutesWatched" in col_map or "averageViewDuration" in col_map:
            est = float(row[col_map["estimatedMinutesWatched"]]) if "estimatedMinutesWatched" in col_map else 0.0
            avd = float(row[col_map["averageViewDuration"]]) if "averageViewDuration" in col_map else 0.0
            return est, avd
    # Zapytanie YTA bez dimensions=video zwraca dokładnie 3 kolumny: [views, estimatedMinutesWatched, averageViewDuration]
    if len(row) >= 4:
        return float(row[2]), float(row[3])
    if len(row) >= 3:
        return float(row[1]), float(row[2])
    return 0.0, 0.0


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
        avg_view_duration = 0.0
        est_minutes = 0.0
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

            est_minutes, avg_view_duration = _extract_yta_video_metrics_row(an_resp)
        except Exception as an_err:
            print(f"⚠️ [Feedback Loop] Ostrzeżenie YTA v2 dla {video_id}: {an_err}")

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

def _extract_ig_insights(media_id: str, token: str, timeout: int = 10) -> Dict[str, Any]:
    """Pobiera metryki IG Insights v21.0 z bezpiecznym fallbackiem z metryk rozszerzonych do bazowych."""
    base_metric = "views,reach,saved,shares,total_interactions"
    ext_metric = (
        "views,reach,saved,shares,total_interactions,"
        "ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"
    )
    ins_url = f"{GRAPH_API_BASE}/{media_id}/insights"
    empty_res: Dict[str, Any] = {
        "views": 0,
        "reach": 0,
        "saved": 0,
        "shares": 0,
        "total_interactions": 0,
        "avg_watch_time_ms": None,
        "avg_watch_time_s": None,
        "total_watch_time_ms": None,
        "skip_rate_pct": None,
        "insights_ok": False,
    }
    try:
        ins_resp = requests.get(
            ins_url,
            params={"metric": ext_metric, "access_token": token},
            timeout=timeout,
        ).json()
        if "error" in ins_resp:
            err_ext = (ins_resp.get("error") or {}).get("message", "Błąd rozszerzonych insights IG")
            print(f"⚠️ [Feedback Loop] Rozszerzone insights IG ({media_id}) odrzucone: {err_ext} — fallback bazowy.")
            ins_resp = requests.get(
                ins_url,
                params={"metric": base_metric, "access_token": token},
                timeout=timeout,
            ).json()

        if "error" in ins_resp:
            err_base = (ins_resp.get("error") or {}).get("message", "Błąd insights IG")
            print(f"⚠️ [Feedback Loop] Błąd insights IG ({media_id}): {err_base}")
            return empty_res

        parsed = _shared_parse_ig_insights(ins_resp)
        avg_wt_ms = int(parsed["avg_watch_time_ms"]) if parsed["avg_watch_time_ms"] is not None else None
        avg_wt_s = round(avg_wt_ms / 1000.0, 2) if avg_wt_ms and avg_wt_ms > 0 else None
        return {
            "views": int(parsed["views"] or 0),
            "reach": int(parsed["reach"] or 0),
            "saved": int(parsed["saved"] or 0),
            "shares": int(parsed["shares"] or 0),
            "total_interactions": int(parsed["interactions"] or 0),
            "avg_watch_time_ms": avg_wt_ms,
            "avg_watch_time_s": avg_wt_s,
            "total_watch_time_ms": int(parsed["total_watch_time_ms"]) if parsed["total_watch_time_ms"] is not None else None,
            "skip_rate_pct": float(parsed["skip_rate_pct"]) if parsed["skip_rate_pct"] is not None else None,
            "insights_ok": True,
        }
    except Exception as exc:
        print(f"⚠️ [Feedback Loop] Wyjątek insights IG ({media_id}): {exc}")
        return empty_res


def fetch_instagram_reel_metrics(media_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera zasięg, wyświetlenia, retencję i interakcje dla Reels z Instagram Graph API v21.0."""
    if not IG_TOKEN_FILE.exists():
        return None

    try:
        data = json.loads(IG_TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        if not token:
            return None

        # 1. Podstawowe liczniki i opis (likes, comments, caption)
        media_url = f"{GRAPH_API_BASE}/{media_id}"
        m_resp = requests.get(
            media_url,
            params={
                "fields": "like_count,comments_count,permalink,caption,timestamp,media_type,media_product_type",
                "access_token": token,
            },
            timeout=10,
        ).json()
        if "error" in m_resp:
            err_msg = (m_resp.get("error") or {}).get("message", str(m_resp["error"]))
            print(f"⚠️ [Feedback Loop] Błąd API IG dla {media_id}: {err_msg}")
            return None

        likes = int(m_resp.get("like_count", 0) or 0)
        comments = int(m_resp.get("comments_count", 0) or 0)

        # 2. Insights v21.0 (views, reach, saved, shares, watch time, skip rate)
        ins = _extract_ig_insights(media_id, token, timeout=10)
        views = int(ins["views"])
        total_interactions = int(ins["total_interactions"]) if ins["insights_ok"] else (likes + comments)
        if ins["insights_ok"] and total_interactions == 0 and (likes + comments) > 0:
            total_interactions = likes + comments

        return {
            "platform": "instagram",
            "media_id": media_id,
            "permalink": m_resp.get("permalink", ""),
            "caption": m_resp.get("caption", ""),
            "likes": likes,
            "comments": comments,
            "views": views,
            "plays": views,
            "reach": int(ins["reach"]),
            "saved": int(ins["saved"]),
            "shares": int(ins["shares"]),
            "total_interactions": total_interactions,
            "avg_watch_time_s": ins["avg_watch_time_s"],
            "total_watch_time_ms": ins["total_watch_time_ms"],
            "skip_rate_pct": ins["skip_rate_pct"],
            "insights_ok": bool(ins["insights_ok"]),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"⚠️ Błąd pobierania metryk IG dla {media_id}: {e}")
        return None


# ─── Facebook Metrics Fetcher ─────────────────────────────────────────────────

def fetch_facebook_reel_metrics(video_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera wyświetlenia, polubienia i komentarze posta/rolki z Facebook Graph API v21.0."""
    if not FB_TOKEN_FILE.exists():
        return None

    try:
        data = json.loads(FB_TOKEN_FILE.read_text(encoding="utf-8"))
        token = data.get("access_token")
        if not token:
            return None

        scopes = data.get("scopes") or data.get("permissions") or []
        has_read_insights = "read_insights" in scopes

        url = f"{GRAPH_API_BASE}/{video_id}"
        resp = requests.get(
            url,
            params={
                "fields": "views,description,permalink_url,created_time,length,likes.summary(true),comments.summary(true)",
                "access_token": token,
            },
            timeout=10,
        ).json()

        if "error" in resp:
            err_msg = (resp.get("error") or {}).get("message", str(resp["error"]))
            print(f"⚠️ [Feedback Loop] Błąd API FB dla {video_id}: {err_msg}")
            return None

        likes = int((resp.get("likes") or {}).get("summary", {}).get("total_count", 0) or 0)
        comments = int((resp.get("comments") or {}).get("summary", {}).get("total_count", 0) or 0)
        views = int(resp.get("views", 0) or 0)
        length_raw = resp.get("length")
        length_s = round(float(length_raw), 2) if length_raw is not None else None
        perm = str(resp.get("permalink_url") or f"/reel/{video_id}/")
        if perm.startswith("/"):
            perm = f"https://www.facebook.com{perm}"

        return {
            "platform": "facebook",
            "video_id": video_id,
            "permalink_url": perm,
            "description": resp.get("description", ""),
            "length_s": length_s,
            "views": views,
            "likes": likes,
            "reactions": likes,
            "comments": comments,
            "shares": 0,
            "has_read_insights_permission": has_read_insights,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
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
    """Aktualizuje learning_youtube.json o nowe wyniki z YouTube (z deduplikacją po video_id)."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        vid = str(metric.get("video_id") or "").strip()
        views = int(metric.get("views", 0) or 0)
        title = metric.get("title", "")
        ret_sec = float(metric.get("avg_view_duration", 0) or 0.0)

        seen_videos = data.setdefault("seen_videos", {})
        prev_seen = seen_videos.get(vid) if vid else None
        is_repeat = bool(vid and isinstance(prev_seen, dict))
        delta_views = max(0, views - int(prev_seen.get("views", 0))) if is_repeat else views

        if not is_repeat:
            data["videos_analysed"] = data.get("videos_analysed", 0) + 1

        # Top / worst performers (aktualizacja po video_id/title bez duplikowania listy)
        top = data.setdefault("title_patterns", {}).setdefault("top_performers", [])
        if views > 100:
            updated_entry = False
            for item in top:
                if (vid and item.get("video_id") == vid) or (not item.get("video_id") and item.get("title") == title):
                    item["views"] = max(int(item.get("views", 0)), views)
                    item["retention_sec"] = ret_sec
                    if vid:
                        item["video_id"] = vid
                    updated_entry = True
                    break
            if not updated_entry:
                entry = {"title": title, "views": views, "retention_sec": ret_sec}
                if vid:
                    entry["video_id"] = vid
                top.append(entry)
            top.sort(key=lambda x: x.get("views", 0), reverse=True)
            data["title_patterns"]["top_performers"] = top[:10]

        # Wagi akcji (nalicz raz dla nowego filmu)
        if action_type and not is_repeat:
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
                h_entry["views_total"] += delta_views
                if not is_repeat:
                    h_entry["count"] += 1
                h_entry["avg_views"] = round(h_entry["views_total"] / max(1, h_entry["count"]), 1)

                reliable_hours = [(h, st) for h, st in hour_stats.items() if st.get("count", 0) >= 3]
                pool = reliable_hours if reliable_hours else list(hour_stats.items())
                best_h = max(pool, key=lambda x: x[1].get("avg_views", 0.0))[0]
                data["publish_time"]["best_hour"] = int(best_h)
            except Exception as exc:
                print(f"⚠️ [Feedback Loop] Błąd analizy godziny YT: {exc}")

        if vid:
            seen_videos[vid] = {
                "views": views,
                "retention_sec": ret_sec,
                "action_type": action_type,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        return data

    _update_learning_file("learning_youtube.json", _updater)


def _aggregate_hashtag_stats(entries: List[Dict[str, Any]], text_field: str) -> Dict[str, Dict[str, Any]]:
    """Wyciąga statystyki skuteczności #tagów z wpisów metryk IG lub FB."""
    acc: Dict[str, Dict[str, float]] = {}
    for entry in entries:
        txt = str((entry or {}).get(text_field) or "")
        tags = {m.lower() for m in re.findall(r"#([A-Za-z0-9_]+)", txt)}
        if not tags:
            continue
        views_v = int(entry.get("views") or entry.get("plays") or 0)
        reach_v = int(entry.get("reach") or 0)
        for tag in tags:
            bucket = acc.setdefault(tag, {"count": 0.0, "views_sum": 0.0, "reach_sum": 0.0})
            bucket["count"] += 1.0
            bucket["views_sum"] += views_v
            bucket["reach_sum"] += reach_v

    out: Dict[str, Dict[str, Any]] = {}
    for tag, st in sorted(acc.items(), key=lambda kv: (kv[1]["views_sum"] / max(1.0, kv[1]["count"]), kv[1]["count"]), reverse=True)[:30]:
        cnt = int(st["count"])
        out[tag] = {
            "count": cnt,
            "avg_views": round(st["views_sum"] / max(1, cnt), 1),
            "avg_reach": round(st["reach_sum"] / max(1, cnt), 1),
        }
    return out


def _first_caption_line(text: Any) -> str:
    line = str(text or "").strip().splitlines()[0].strip() if str(text or "").strip() else ""
    return line[:100]


def ingest_instagram_metric(metric: Dict[str, Any], action_type: str, pub_ts: Optional[str] = None) -> None:
    """Aktualizuje learning_instagram.json o zasięgi, retencję, hooki i tagi Reels (z deduplikacją po media_id)."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        mid = str(metric.get("media_id") or "").strip()
        views_now = int(metric.get("views") or metric.get("plays") or 0)
        reach_now = int(metric.get("reach") or 0)
        seen_media = data.setdefault("seen_media", {})
        is_repeat = bool(mid and mid in seen_media)
        if not is_repeat:
            data["videos_analysed"] = data.get("videos_analysed", 0) + 1

        if metric.get("insights_ok") or reach_now > 0 or views_now > 0:
            data.pop("_warning", None)
            data["_description"] = "Instagram Reels learning state (Graph API v21.0 + instagram_manage_insights aktywne)."

        entries = data.setdefault("metrics_collected", {}).setdefault("entries", [])
        if mid:
            entries = [e for e in entries if str((e or {}).get("media_id") or "").strip() != mid]
            seen_media[mid] = datetime.now(timezone.utc).isoformat()
        entries.append(metric)
        entries = entries[-30:]
        data["metrics_collected"]["entries"] = entries

        # Agregacja retencji i oglądalności
        wt_vals = [float(e["avg_watch_time_s"]) for e in entries if isinstance(e, dict) and e.get("avg_watch_time_s") is not None]
        skip_vals = [float(e["skip_rate_pct"]) for e in entries if isinstance(e, dict) and e.get("skip_rate_pct") is not None]
        views_vals = [int(e.get("views") or e.get("plays") or 0) for e in entries if isinstance(e, dict)]
        reach_vals = [int(e.get("reach") or 0) for e in entries if isinstance(e, dict)]
        samples_with_ins = sum(1 for e in entries if isinstance(e, dict) and (e.get("insights_ok") or int(e.get("reach") or 0) > 0 or int(e.get("views") or 0) > 0))
        data["retention_summary"] = {
            "avg_watch_time_s": round(sum(wt_vals) / len(wt_vals), 2) if wt_vals else None,
            "avg_skip_rate_pct": round(sum(skip_vals) / len(skip_vals), 2) if skip_vals else None,
            "avg_views": round(sum(views_vals) / max(1, len(views_vals)), 1),
            "avg_reach": round(sum(reach_vals) / max(1, len(reach_vals)), 1),
            "samples_with_insights": samples_with_ins,
        }

        # Hooki z pierwszej linii caption
        hook_rows = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            hook = _first_caption_line(e.get("caption"))
            if not hook:
                continue
            hook_rows.append({
                "media_id": e.get("media_id"),
                "hook": hook,
                "views": int(e.get("views") or e.get("plays") or 0),
                "reach": int(e.get("reach") or 0),
                "avg_watch_time_s": e.get("avg_watch_time_s"),
                "skip_rate_pct": e.get("skip_rate_pct"),
            })
        hook_rows.sort(key=lambda r: (r["views"], r["reach"]), reverse=True)
        hook_lens = [len(r["hook"]) for r in hook_rows]
        cp = data.setdefault("caption_patterns", {})
        cp["top_hooks"] = hook_rows[:5]
        cp["worst_hooks"] = list(reversed(hook_rows[-5:])) if len(hook_rows) >= 2 else []
        cp["avg_hook_length"] = round(sum(hook_lens) / len(hook_lens), 1) if hook_lens else None

        # Hasztagi
        data.setdefault("hashtag_performance", {})["by_tag"] = _aggregate_hashtag_stats(entries, "caption")

        # Wagi akcji (raz na nowy media_id)
        if action_type and not is_repeat:
            weights = data.setdefault("action_type_weights", {})
            cur = float(weights.get(action_type.lower(), 1.0))
            if views_now >= 400:
                weights[action_type.lower()] = round(min(2.0, cur + 0.05), 3)

        return data

    _update_learning_file("learning_instagram.json", _updater)


def ingest_facebook_metric(metric: Dict[str, Any], action_type: str, pub_ts: Optional[str] = None) -> None:
    """Aktualizuje learning_facebook.json o wyświetlenia, polubienia, wzorce postów i godziny (z deduplikacją)."""
    def _updater(data: Dict[str, Any]) -> Dict[str, Any]:
        fbid = str(metric.get("video_id") or "").strip()
        views = int(metric.get("views", 0) or 0)
        seen_videos = data.setdefault("seen_videos", {})
        prev_seen = seen_videos.get(fbid) if fbid else None
        is_repeat = bool(fbid and isinstance(prev_seen, dict))
        delta_views = max(0, views - int(prev_seen.get("views", 0))) if is_repeat else views

        if metric.get("has_read_insights_permission"):
            data.pop("_warning", None)
            data["_description"] = "Facebook Page Reels learning state (Graph API v21.0 + read_insights aktywne)."
        else:
            data["_description"] = "Facebook Page Reels learning state (Graph API v21.0: views, likes, comments aktywne)."
            data["_warning"] = (
                "Token Facebook Page nie zawiera read_insights — zbierane są podstawowe metryki "
                "wideo (views, likes, comments) bez video_insights."
            )

        if not is_repeat:
            data["videos_analysed"] = data.get("videos_analysed", 0) + 1
        entries = data.setdefault("metrics_collected", {}).setdefault("entries", [])
        if fbid:
            entries = [e for e in entries if str((e or {}).get("video_id") or "").strip() != fbid]
        entries.append(metric)
        entries = entries[-30:]
        data["metrics_collected"]["entries"] = entries

        post_rows = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            title_line = _first_caption_line(e.get("description"))
            post_rows.append({
                "video_id": e.get("video_id"),
                "title": title_line or f"Facebook Reel #{e.get('video_id')}",
                "views": int(e.get("views") or 0),
                "reactions": int(e.get("reactions") or e.get("likes") or 0),
                "comments": int(e.get("comments") or 0),
            })
        post_rows.sort(key=lambda r: (r["views"], r["reactions"]), reverse=True)
        data.setdefault("post_patterns", {})["top_posts"] = post_rows[:5]
        data.setdefault("hashtag_performance", {})["by_tag"] = _aggregate_hashtag_stats(entries, "description")

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
                e["views_total"] += delta_views
                if not is_repeat:
                    e["count"] += 1
                e["avg_views"] = round(e["views_total"] / max(1, e["count"]), 1)

                reliable_keys = [(k, st) for k, st in stats.items() if st.get("count", 0) >= 3]
                pool = reliable_keys if reliable_keys else list(stats.items())
                best_k = max(pool, key=lambda x: x[1].get("avg_views", 0.0))[0]
                best_day_part, best_hour_part = best_k.rsplit("_", 1)
                data["best_post_time"]["best_hour"] = int(best_hour_part.split(":")[0])
                data["best_post_time"]["best_day"] = best_day_part
            except Exception as exc:
                print(f"⚠️ [Feedback Loop] Błąd analizy godziny FB: {exc}")

        if fbid:
            seen_videos[fbid] = {"views": views, "updated_at": datetime.now(timezone.utc).isoformat()}

        return data

    _update_learning_file("learning_facebook.json", _updater)


def _infer_action_type_from_queue_item(item: Dict[str, Any]) -> str:
    """Wyznacza action_type dla wpisu kolejki z extra, pliku .meta.json lub nazwy wideo."""
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    act = str(extra.get("action_type") or "").strip()
    if act:
        return act

    vp_raw = str(item.get("video_path") or "").strip()
    if vp_raw:
        vp = Path(vp_raw)
        meta_p = vp.with_suffix(".meta.json")
        if meta_p.is_file():
            try:
                meta = json.loads(meta_p.read_text(encoding="utf-8"))
                meta_act = str(meta.get("action_type") or "").strip()
                if meta_act:
                    return meta_act
            except Exception as exc:
                print(f"⚠️ [Feedback Loop] Błąd odczytu {meta_p.name}: {exc}")
        stem_low = vp.stem.lower()
        for token, mapped in (
            ("pentakill", "pentakill"),
            ("penta", "pentakill"),
            ("quadrakill", "quadrakill"),
            ("quadra", "quadrakill"),
            ("triple", "triple"),
            ("double", "double"),
            ("solo_bolo", "solo_bolo"),
            ("clutch", "clutch"),
        ):
            if token in stem_low:
                return mapped

    return "outplay"


def _load_queue_social_entries(
    queue_file: Optional[Path],
    seen_ig_ids: set,
    seen_fb_ids: set,
    max_videos: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Zbiera opublikowane ID Instagrama i Facebooka z kolejki 24/7 pomijając ID już pobrane z logu."""
    if not queue_file or not queue_file.exists():
        return [], []
    try:
        items = json.loads(queue_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ [Feedback Loop] Błąd odczytu kolejki {queue_file}: {exc}")
        return [], []
    if not isinstance(items, list):
        return [], []

    ig_entries: List[Dict[str, Any]] = []
    fb_entries: List[Dict[str, Any]] = []
    published = [it for it in items if isinstance(it, dict) and str(it.get("status") or "") == "published"]
    published.sort(key=lambda x: str(x.get("published_at") or x.get("publish_at") or ""), reverse=True)

    for it in published:
        plat = str(it.get("platform") or "").lower()
        res = it.get("result") if isinstance(it.get("result"), dict) else {}
        action_type = _infer_action_type_from_queue_item(it)
        pub_ts = it.get("published_at") or it.get("publish_at")

        if plat == "instagram" and len(ig_entries) < max_videos:
            mid = str(res.get("media_id") or "").strip()
            if mid and mid not in seen_ig_ids:
                seen_ig_ids.add(mid)
                ig_entries.append({"id": mid, "action_type": action_type, "timestamp": pub_ts})
        elif plat == "facebook" and len(fb_entries) < max_videos:
            fid = str(res.get("video_id") or "").strip()
            if fid and fid not in seen_fb_ids:
                seen_fb_ids.add(fid)
                fb_entries.append({"id": fid, "action_type": action_type, "timestamp": pub_ts})

    return ig_entries, fb_entries


# ─── Główna Pętla Zwrotna (Automated Loop) ─────────────────────────────────────

def collect_all_platform_metrics(max_videos: int = 15) -> Dict[str, Any]:
    """
    Skanuje published_videos.jsonl oraz opublikowane wpisy scheduled_social_queue.json
    i zbiera metryki dla wszystkich platform. Zwraca raport podsumowujący.
    """
    resolved_queue_file: Optional[Path] = SCHEDULED_QUEUE_FILE
    if (
        PUB_LOG_FILE != _DEFAULT_PUB_LOG_FILE
        and SCHEDULED_QUEUE_FILE == _DEFAULT_SCHEDULED_QUEUE_FILE
        and ACCOUNTS_DIR == ROOT_DIR / "accounts"
    ):
        resolved_queue_file = None

    has_queue = bool(resolved_queue_file and resolved_queue_file.exists())
    if not PUB_LOG_FILE.exists() and not has_queue:
        return {"status": "no_pub_log", "analysed": 0}

    print("\n📊 [Feedback Loop] Rozpoczynam zbieranie metryk ze wszystkich platform...")

    entries: List[Dict[str, Any]] = []
    if PUB_LOG_FILE.exists():
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

    recent_entries = entries[-max_videos:]
    seen_ig_ids = {str(it.get("instagram_media_id") or "").strip() for it in recent_entries if it.get("instagram_media_id")}
    seen_fb_ids = {str(it.get("facebook_video_id") or "").strip() for it in recent_entries if it.get("facebook_video_id")}
    queue_ig, queue_fb = _load_queue_social_entries(resolved_queue_file, seen_ig_ids, seen_fb_ids, max_videos)

    if not recent_entries and not queue_ig and not queue_fb:
        print("ℹ️ Brak opublikowanych filmów w logu i kolejce.")
        return {"status": "empty_log", "analysed": 0}

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_checked": len(recent_entries) + len(queue_ig) + len(queue_fb),
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

        # 2. Instagram (z logu)
        ig_id = item.get("instagram_media_id")
        if ig_id:
            ig_metric = fetch_instagram_reel_metrics(ig_id)
            if ig_metric:
                ingest_instagram_metric(ig_metric, action_type, pub_ts=pub_ts)
                report["instagram_updated"] += 1
                print(f"   📸 IG [{ig_id}]: views={ig_metric.get('views', 0)}, reach={ig_metric.get('reach', 0)}, likes={ig_metric.get('likes', 0)}")

        # 3. Facebook (z logu)
        fb_id = item.get("facebook_video_id")
        if fb_id:
            fb_metric = fetch_facebook_reel_metrics(fb_id)
            if fb_metric:
                ingest_facebook_metric(fb_metric, action_type, pub_ts=pub_ts)
                report["facebook_updated"] += 1
                print(f"   📘 FB [{fb_id}]: views={fb_metric.get('views', 0)}, reactions={fb_metric.get('reactions', 0)}")

        # 4. TikTok
        tt_id = item.get("tiktok_publish_id")
        if tt_id:
            tt_metric = fetch_tiktok_metrics(tt_id)
            if tt_metric:
                report["tiktok_queried"] += 1
                print(f"   🚀 TikTok [{tt_id}]: status={tt_metric.get('status')}")

    for q_ig in queue_ig:
        ig_metric = fetch_instagram_reel_metrics(q_ig["id"])
        if ig_metric:
            ingest_instagram_metric(ig_metric, q_ig["action_type"], pub_ts=q_ig["timestamp"])
            report["instagram_updated"] += 1
            print(f"   📸 IG [queue {q_ig['id']}]: views={ig_metric.get('views', 0)}, reach={ig_metric.get('reach', 0)}, likes={ig_metric.get('likes', 0)}")

    for q_fb in queue_fb:
        fb_metric = fetch_facebook_reel_metrics(q_fb["id"])
        if fb_metric:
            ingest_facebook_metric(fb_metric, q_fb["action_type"], pub_ts=q_fb["timestamp"])
            report["facebook_updated"] += 1
            print(f"   📘 FB [queue {q_fb['id']}]: views={fb_metric.get('views', 0)}, reactions={fb_metric.get('reactions', 0)}")

    print(f"✅ [Feedback Loop] Zakończono! Zaktualizowano bazy learning_states:")
    print(f"   YT: {report['youtube_updated']} | IG: {report['instagram_updated']} | FB: {report['facebook_updated']} | TT: {report['tiktok_queried']}")

    return report


if __name__ == "__main__":
    collect_all_platform_metrics()
