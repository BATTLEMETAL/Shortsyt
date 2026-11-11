"""
Shortsyt — Multi-Platform Analytics Engine
Zbiera i unifikuje metryki analityczne na żywo z:
  1. YouTube Data API & Analytics API
  2. Instagram Graph API (Reels Insights: views, reach, likes, comments, saved, shares)
  3. Facebook Graph API (Page Videos: views, reactions, comments)
  4. TikTok Content Posting API v2 (User info, token status, publication stats)
  5. Omnichannel Aggregator (Cross-platform overview, unified reach & engagement)
"""
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT_DIR / "accounts"
FB_TOKEN_FILE = ACCOUNTS_DIR / "facebook_token.json"
IG_TOKEN_FILE = ACCOUNTS_DIR / "instagram_token.json"
TT_TOKEN_FILE = ACCOUNTS_DIR / "tiktok_token.json"

IG_CACHE_FILE = ACCOUNTS_DIR / "instagram_analytics_cache.json"
FB_CACHE_FILE = ACCOUNTS_DIR / "facebook_analytics_cache.json"
TT_CACHE_FILE = ACCOUNTS_DIR / "tiktok_analytics_cache.json"
TT_POST_CACHE_FILE = ACCOUNTS_DIR / "tiktok_post_cache.json"
OMNI_CACHE_FILE = ACCOUNTS_DIR / "omnichannel_analytics_cache.json"

CACHE_TTL_SECONDS = 300  # 5 minut


def _read_cache(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_at = data.get("_cached_at", 0)
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return data
    except Exception:
        return None
    return None


def _write_cache(cache_path: Path, data: Dict[str, Any]) -> None:
    try:
        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        data["_cached_at"] = time.time()
        data["synced_at"] = datetime.now(timezone.utc).isoformat()
        cache_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Nie udało się zapisać cache {cache_path.name}: {e}")


def get_instagram_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera rzeczywiste statystyki profilu i Rolek z Instagram Graph API."""
    if not force_refresh:
        cached = _read_cache(IG_CACHE_FILE)
        if cached:
            return cached

    if not IG_TOKEN_FILE.exists():
        return {
            "connected": False,
            "message": "Brak połączonego konta Instagram. Wklej token w Ustawieniach.",
            "profile": None,
            "total_views": 0,
            "total_reach": 0,
            "total_likes": 0,
            "total_comments": 0,
            "total_interactions": 0,
            "reels": []
        }

    try:
        token_info = json.loads(IG_TOKEN_FILE.read_text(encoding="utf-8"))
        access_token = token_info.get("access_token")
        ig_id = token_info.get("instagram_business_account_id") or "17841473819182842"

        # 1. Pobierz profil Instagram Business
        prof_res = requests.get(
            f"https://graph.facebook.com/v21.0/{ig_id}",
            params={
                "fields": "username,name,followers_count,follows_count,media_count,profile_picture_url,media{id,caption,like_count,comments_count,permalink,timestamp,media_type}",
                "access_token": access_token
            },
            timeout=12
        ).json()

        if "error" in prof_res:
            err_msg = prof_res["error"].get("message", "Błąd Instagram API")
            # fallback do cache jeśli istnieje
            if IG_CACHE_FILE.exists():
                try:
                    return json.loads(IG_CACHE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return {"connected": False, "error": err_msg, "reels": [], "total_views": 0}

        username = prof_res.get("username", "dwannellenga")
        name = prof_res.get("name", "Dwannellenga")
        followers = prof_res.get("followers_count", 0)
        follows = prof_res.get("follows_count", 0)
        media_count = prof_res.get("media_count", 0)
        profile_pic = prof_res.get("profile_picture_url", "")

        raw_media = prof_res.get("media", {}).get("data", [])
        reels: List[Dict[str, Any]] = []

        total_views = 0
        total_reach = 0
        total_likes = 0
        total_comments = 0
        total_interactions = 0

        for m in raw_media:
            m_id = m.get("id")
            caption = m.get("caption", "")
            likes = int(m.get("like_count", 0))
            comments = int(m.get("comments_count", 0))
            permalink = m.get("permalink", f"https://www.instagram.com/reel/{m_id}/")
            ts = m.get("timestamp", "")

            views = 0
            reach = 0
            saved = 0
            shares = 0
            interactions = likes + comments

            # Pobierz szczegółowe statystyki z /insights
            try:
                ins_resp = requests.get(
                    f"https://graph.facebook.com/v21.0/{m_id}/insights",
                    params={
                        "metric": "views,reach,saved,shares,total_interactions",
                        "access_token": access_token
                    },
                    timeout=8
                ).json()

                for row in ins_resp.get("data", []):
                    metric_name = row.get("name")
                    val = 0
                    if row.get("values"):
                        val = int(row["values"][0].get("value", 0))
                    elif row.get("total_value"):
                        val = int(row["total_value"].get("value", 0))

                    if metric_name == "views":
                        views = val
                    elif metric_name == "reach":
                        reach = val
                    elif metric_name == "saved":
                        saved = val
                    elif metric_name == "shares":
                        shares = val
                    elif metric_name == "total_interactions" and val > 0:
                        interactions = val
            except Exception:
                pass

            total_views += views
            total_reach += reach
            total_likes += likes
            total_comments += comments
            total_interactions += interactions

            reels.append({
                "id": m_id,
                "title": caption.split("\n")[0][:80] if caption else f"Instagram Reel #{m_id}",
                "caption": caption,
                "url": permalink,
                "timestamp": ts,
                "views": views,
                "reach": reach,
                "likes": likes,
                "comments": comments,
                "saved": saved,
                "shares": shares,
                "interactions": interactions,
                "engagement_rate": round((interactions / max(views, 1)) * 100, 2)
            })

        avg_views = int(total_views / max(len(reels), 1))

        result = {
            "connected": True,
            "platform": "instagram",
            "profile": {
                "username": username,
                "name": name,
                "followers_count": followers,
                "follows_count": follows,
                "media_count": media_count,
                "profile_picture_url": profile_pic
            },
            "count": len(reels),
            "total_views": total_views,
            "total_reach": total_reach,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_interactions": total_interactions,
            "avg_views": avg_views,
            "top_reels": sorted(reels, key=lambda x: x["views"], reverse=True)[:5],
            "reels": reels
        }

        _write_cache(IG_CACHE_FILE, result)
        return result

    except Exception as e:
        print(f"❌ Wyjątek get_instagram_analytics: {e}")
        if IG_CACHE_FILE.exists():
            try:
                return json.loads(IG_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"connected": False, "error": str(e), "reels": [], "total_views": 0}


def get_facebook_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera rzeczywiste statystyki fanpage'a i wideo z Facebook Graph API."""
    if not force_refresh:
        cached = _read_cache(FB_CACHE_FILE)
        if cached:
            return cached

    if not FB_TOKEN_FILE.exists():
        return {
            "connected": False,
            "message": "Brak połączonego konta Facebook. Wklej token w Ustawieniach.",
            "page": None,
            "total_views": 0,
            "total_reactions": 0,
            "total_comments": 0,
            "videos": []
        }

    try:
        token_info = json.loads(FB_TOKEN_FILE.read_text(encoding="utf-8"))
        access_token = token_info.get("access_token")
        page_id = token_info.get("page_id") or "1398423656686108"

        # 1. Pobierz dane Fanpage'a i listę wideo
        page_res = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}",
            params={
                "fields": "name,followers_count,fan_count,picture,videos{id,description,permalink_url,created_time,views}",
                "access_token": access_token
            },
            timeout=12
        ).json()

        if "error" in page_res:
            err_msg = page_res["error"].get("message", "Błąd Facebook API")
            if FB_CACHE_FILE.exists():
                try:
                    return json.loads(FB_CACHE_FILE.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return {"connected": False, "error": err_msg, "videos": [], "total_views": 0}

        page_name = page_res.get("name", "Dwannellenga")
        followers = page_res.get("followers_count", 0)
        fan_count = page_res.get("fan_count", 0)
        picture_url = page_res.get("picture", {}).get("data", {}).get("url", "")

        raw_videos = page_res.get("videos", {}).get("data", [])
        videos: List[Dict[str, Any]] = []

        total_views = 0
        total_reactions = 0
        total_comments = 0

        for v in raw_videos:
            v_id = v.get("id")
            desc = v.get("description", "")
            views = int(v.get("views", 0))
            perm = v.get("permalink_url", f"/reel/{v_id}/")
            if perm.startswith("/"):
                perm = f"https://www.facebook.com{perm}"
            created_time = v.get("created_time", "")

            # Zapytaj o reakcje i komentarze dla wideo
            reactions = 0
            comments = 0
            try:
                stat_res = requests.get(
                    f"https://graph.facebook.com/v21.0/{v_id}",
                    params={
                        "fields": "reactions.summary(true),comments.summary(true)",
                        "access_token": access_token
                    },
                    timeout=6
                ).json()
                reactions = stat_res.get("reactions", {}).get("summary", {}).get("total_count", 0)
                comments = stat_res.get("comments", {}).get("summary", {}).get("total_count", 0)
            except Exception:
                pass

            total_views += views
            total_reactions += reactions
            total_comments += comments

            videos.append({
                "id": v_id,
                "title": desc.split("\n")[0][:80] if desc else f"Facebook Reel #{v_id}",
                "description": desc,
                "url": perm,
                "timestamp": created_time,
                "views": views,
                "reactions": reactions,
                "comments": comments,
                "engagement": reactions + comments
            })

        avg_views = int(total_views / max(len(videos), 1))

        result = {
            "connected": True,
            "platform": "facebook",
            "page": {
                "id": page_id,
                "name": page_name,
                "followers_count": followers,
                "fan_count": fan_count,
                "picture_url": picture_url
            },
            "count": len(videos),
            "total_views": total_views,
            "total_reactions": total_reactions,
            "total_comments": total_comments,
            "avg_views": avg_views,
            "top_videos": sorted(videos, key=lambda x: x["views"], reverse=True)[:5],
            "videos": videos
        }

        _write_cache(FB_CACHE_FILE, result)
        return result

    except Exception as e:
        print(f"❌ Wyjątek get_facebook_analytics: {e}")
        if FB_CACHE_FILE.exists():
            try:
                return json.loads(FB_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"connected": False, "error": str(e), "videos": [], "total_views": 0}


def get_tiktok_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera profil i metryki publikacji z TikTok Content Posting API oraz live video insights."""
    if not force_refresh:
        cached = _read_cache(TT_CACHE_FILE)
        if cached:
            return cached

    if not TT_TOKEN_FILE.exists():
        return {
            "connected": False,
            "message": "Brak połączonego konta TikTok.",
            "profile": None,
            "videos": [],
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "avg_views": 0
        }

    try:
        import re
        token_info = json.loads(TT_TOKEN_FILE.read_text(encoding="utf-8"))
        access_token = token_info.get("access_token")
        now = int(time.time())
        refresh_expires_at = token_info.get("refresh_expires_at", 0)
        days_left = max(0, int((refresh_expires_at - now) / 86400))

        # 1. Zapytanie o profil użytkownika przez oficjalny endpoint
        user_res = requests.get(
            "https://open.tiktokapis.com/v2/user/info/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "open_id,union_id,avatar_url,display_name"},
            timeout=10
        ).json()

        user_data = user_res.get("data", {}).get("user", {})
        display_name = user_data.get("display_name", "Dwannellenga")
        avatar_url = user_data.get("avatar_url", "")
        open_id = user_data.get("open_id", "")

        # 2. Pobranie danych profilu z live web hydration
        followers_count = 6
        following_count = 3
        heart_count = 193
        video_count = 28
        unique_id = "dwannellenga"

        headers_web = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            prof_web = requests.get(f"https://www.tiktok.com/@{unique_id}", headers=headers_web, timeout=6)
            match_prof = re.search(r'<script id=.__UNIVERSAL_DATA_FOR_REHYDRATION__.[^>]*>(.*?)</script>', prof_web.text)
            if match_prof:
                p_data = json.loads(match_prof.group(1))
                uinfo = p_data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {}).get("userInfo", {})
                p_stats = uinfo.get("stats", {})
                followers_count = p_stats.get("followerCount", followers_count)
                following_count = p_stats.get("followingCount", following_count)
                heart_count = p_stats.get("heartCount", heart_count)
                video_count = p_stats.get("videoCount", video_count)
                p_user = uinfo.get("user", {})
                if p_user.get("nickname"):
                    display_name = p_user.get("nickname")
                if p_user.get("avatarLarger") or p_user.get("avatarThumb"):
                    avatar_url = p_user.get("avatarLarger") or p_user.get("avatarThumb")
        except Exception as _p_err:
            print(f"ℹ️ [TikTok Web Profile Fetch]: {_p_err}")

        # 3. Odczyt cache'owanych postów TikTok
        post_cache: Dict[str, Any] = {}
        if TT_POST_CACHE_FILE.exists():
            try:
                post_cache = json.loads(TT_POST_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                post_cache = {}

        # 4. Skanowanie lokalnych filmów opublikowanych na TikTok
        headers_api = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        temp_dir = ROOT_DIR / "lol_agent" / "lol_temp"
        meta_files = sorted(list(temp_dir.glob("*.meta.json")), key=lambda p: p.stat().st_mtime, reverse=True)

        videos: List[Dict[str, Any]] = []
        cache_modified = False

        for mf in meta_files:
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                tt_res = m.get("multi_results", {}).get("tiktok", {})
                pid = tt_res.get("publish_id")
                if not pid:
                    continue

                p_entry = post_cache.get(pid, {})
                post_id = p_entry.get("post_id")

                # Jeśli brak post_id, sprawdź w status API
                if not post_id and access_token:
                    try:
                        st_res = requests.post(
                            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                            headers=headers_api,
                            json={"publish_id": pid},
                            timeout=6
                        ).json()
                        st_data = st_res.get("data", {})
                        p_ids = st_data.get("publicaly_available_post_id", [])
                        if p_ids:
                            post_id = str(p_ids[0])
                            p_entry["post_id"] = post_id
                            cache_modified = True
                    except Exception:
                        pass

                # Jeśli mamy post_id, a brakuje views lub wymuszone odświeżenie
                if post_id and (force_refresh or "views" not in p_entry or p_entry.get("views", 0) == 0):
                    try:
                        v_res = requests.get(f"https://www.tiktok.com/@{unique_id}/video/{post_id}", headers=headers_web, timeout=6)
                        v_match = re.search(r'<script id=.__UNIVERSAL_DATA_FOR_REHYDRATION__.[^>]*>(.*?)</script>', v_res.text)
                        if v_match:
                            v_raw = json.loads(v_match.group(1))
                            item = v_raw.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {}).get("itemInfo", {}).get("itemStruct", {})
                            v_stats = item.get("stats", {})
                            p_entry["views"] = int(v_stats.get("playCount", 0))
                            p_entry["likes"] = int(v_stats.get("diggCount", 0))
                            p_entry["comments"] = int(v_stats.get("commentCount", 0))
                            p_entry["shares"] = int(v_stats.get("shareCount", 0))
                            p_entry["desc"] = item.get("desc", "")
                            p_entry["url"] = f"https://www.tiktok.com/@{unique_id}/video/{post_id}"
                            cache_modified = True
                    except Exception:
                        pass

                clean_title = p_entry.get("desc") or m.get("hook_text") or m.get("source_path", "TikTok Short")
                if "#" in clean_title:
                    clean_title = clean_title.split("#")[0].strip() or clean_title

                p_entry["id"] = post_id or pid
                p_entry["title"] = clean_title
                p_entry["publish_id"] = pid
                p_entry["url"] = p_entry.get("url") or f"https://www.tiktok.com/@{unique_id}"
                p_entry["timestamp"] = m.get("rendered_at") or m.get("published_at") or ""
                p_entry["views"] = p_entry.get("views", 0)
                p_entry["likes"] = p_entry.get("likes", 0)
                p_entry["comments"] = p_entry.get("comments", 0)
                p_entry["shares"] = p_entry.get("shares", 0)

                post_cache[pid] = p_entry
                videos.append(p_entry)
            except Exception:
                pass

        if cache_modified:
            try:
                TT_POST_CACHE_FILE.write_text(json.dumps(post_cache, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        total_views = sum(v.get("views", 0) for v in videos)
        total_likes = sum(v.get("likes", 0) for v in videos)
        total_comments = sum(v.get("comments", 0) for v in videos)
        avg_views = int(total_views / max(len(videos), 1))

        result = {
            "connected": True,
            "platform": "tiktok",
            "profile": {
                "display_name": display_name,
                "unique_id": unique_id,
                "avatar_url": avatar_url,
                "open_id": open_id,
                "mode": "Live Production",
                "refresh_expires_in_days": days_left,
                "followers_count": followers_count,
                "following_count": following_count,
                "heart_count": heart_count,
                "video_count": video_count
            },
            "count": len(videos),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "avg_views": avg_views,
            "top_videos": sorted(videos, key=lambda x: x.get("views", 0), reverse=True)[:5],
            "videos": videos
        }

        _write_cache(TT_CACHE_FILE, result)
        return result

    except Exception as e:
        print(f"❌ Wyjątek get_tiktok_analytics: {e}")
        return {"connected": False, "error": str(e), "videos": [], "total_views": 0}


def get_omnichannel_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Łączy statystyki ze wszystkich 4 platform w jeden ekosystemowy panel (Omnichannel)."""
    if not force_refresh:
        cached = _read_cache(OMNI_CACHE_FILE)
        if cached:
            return cached

    # 1. YouTube
    from lol_agent.api.routers.learning import _sync_youtube_analytics
    yt_sync = _sync_youtube_analytics(force=force_refresh)
    yt_videos = yt_sync.get("videos", [])
    yt_total_views = sum(v.get("views", 0) for v in yt_videos)
    yt_total_likes = sum(v.get("likes", 0) for v in yt_videos)
    yt_total_comments = sum(v.get("comments", 0) for v in yt_videos)

    # 2. Instagram
    ig_data = get_instagram_analytics(force_refresh=force_refresh)
    ig_views = ig_data.get("total_views", 0)
    ig_likes = ig_data.get("total_likes", 0)
    ig_comments = ig_data.get("total_comments", 0)
    ig_interactions = ig_data.get("total_interactions", 0)

    # 3. Facebook
    fb_data = get_facebook_analytics(force_refresh=force_refresh)
    fb_views = fb_data.get("total_views", 0)
    fb_reactions = fb_data.get("total_reactions", 0)
    fb_comments = fb_data.get("total_comments", 0)

    # 4. TikTok
    tt_data = get_tiktok_analytics(force_refresh=force_refresh)
    tt_views = tt_data.get("total_views", 0)
    tt_likes = tt_data.get("total_likes", 0)
    tt_comments = tt_data.get("total_comments", 0)
    tt_engagement = tt_likes + tt_comments

    grand_total_views = yt_total_views + ig_views + fb_views + tt_views
    grand_total_engagement = (
        yt_total_likes + yt_total_comments +
        ig_interactions +
        fb_reactions + fb_comments +
        tt_engagement
    )

    platform_breakdown = {
        "youtube": {
            "name": "YouTube Shorts",
            "icon": "youtube",
            "views": yt_total_views,
            "videos_count": len(yt_videos),
            "share_pct": round((yt_total_views / max(grand_total_views, 1)) * 100, 1),
            "engagement": yt_total_likes + yt_total_comments
        },
        "instagram": {
            "name": "Instagram Reels",
            "icon": "instagram",
            "views": ig_views,
            "videos_count": ig_data.get("count", 0),
            "share_pct": round((ig_views / max(grand_total_views, 1)) * 100, 1),
            "engagement": ig_interactions
        },
        "facebook": {
            "name": "Facebook Reels",
            "icon": "facebook",
            "views": fb_views,
            "videos_count": fb_data.get("count", 0),
            "share_pct": round((fb_views / max(grand_total_views, 1)) * 100, 1),
            "engagement": fb_reactions + fb_comments
        },
        "tiktok": {
            "name": "TikTok",
            "icon": "tiktok",
            "views": tt_views,
            "videos_count": tt_data.get("count", 0),
            "share_pct": round((tt_views / max(grand_total_views, 1)) * 100, 1),
            "engagement": tt_engagement
        }
    }

    # Zunifikowana lista najlepszych wideo z całego ekosystemu
    all_top: List[Dict[str, Any]] = []
    for yv in yt_videos[:10]:
        all_top.append({
            "platform": "youtube",
            "title": yv.get("title", ""),
            "views": yv.get("views", 0),
            "likes": yv.get("likes", 0),
            "comments": yv.get("comments", 0),
            "url": yv.get("url", ""),
            "timestamp": yv.get("published_at") or yv.get("timestamp", "")
        })
    for iv in ig_data.get("reels", []):
        all_top.append({
            "platform": "instagram",
            "title": iv.get("title", ""),
            "views": iv.get("views", 0),
            "likes": iv.get("likes", 0),
            "comments": iv.get("comments", 0),
            "url": iv.get("url", ""),
            "timestamp": iv.get("timestamp", "")
        })
    for fv in fb_data.get("videos", []):
        all_top.append({
            "platform": "facebook",
            "title": fv.get("title", ""),
            "views": fv.get("views", 0),
            "likes": fv.get("reactions", 0),
            "comments": fv.get("comments", 0),
            "url": fv.get("url", ""),
            "timestamp": fv.get("timestamp", "")
        })
    for tv in tt_data.get("videos", []):
        all_top.append({
            "platform": "tiktok",
            "title": tv.get("title", ""),
            "views": tv.get("views", 0),
            "likes": tv.get("likes", 0),
            "comments": tv.get("comments", 0),
            "url": tv.get("url", ""),
            "timestamp": tv.get("timestamp", "")
        })

    all_top.sort(key=lambda x: x["views"], reverse=True)

    result = {
        "platform": "omnichannel",
        "grand_total_views": grand_total_views,
        "grand_total_engagement": grand_total_engagement,
        "total_published_videos": len(yt_videos) + ig_data.get("count", 0) + fb_data.get("count", 0) + tt_data.get("count", 0),
        "platforms": platform_breakdown,
        "top_videos": all_top[:15]
    }

    _write_cache(OMNI_CACHE_FILE, result)
    return result
