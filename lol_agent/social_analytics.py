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
from typing import Dict, Any, List, Optional, Tuple

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
TT_LEARNING_FILE = ACCOUNTS_DIR / "tiktok_learning_directive.json"
OMNI_CACHE_FILE = ACCOUNTS_DIR / "omnichannel_analytics_cache.json"

_YT_ONLY_TAG_BLOCKLIST = {"shorts", "shortsfeed", "ytshorts", "youtubeshorts", "short"}

CACHE_TTL_SECONDS = 300  # 5 minut


def _read_cache(cache_path: Path) -> Optional[Dict[str, Any]]:
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        cached_at = data.get("_cached_at", 0)
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            return data
    except Exception as exc:
        print(f"[SocialAnalytics] [WARN] Błąd odczytu cache {cache_path.name}: {exc}")
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


def _paginate_graph_edges(
    url: str,
    params: Dict[str, Any],
    max_items: int = 200,
    timeout: int = 12,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Iteruje po stronach Meta Graph API (paging.next) do limitu max_items."""
    items: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    next_params: Optional[Dict[str, Any]] = params

    while next_url and len(items) < max_items:
        try:
            resp = requests.get(next_url, params=next_params, timeout=timeout).json()
        except Exception as exc:
            err_msg = f"Wyjątek paginacji Graph API: {exc}"
            print(f"[SocialAnalytics] [WARN] {err_msg}")
            return items, err_msg

        if "error" in resp:
            err_obj = resp.get("error") or {}
            err_msg = err_obj.get("message") or str(err_obj)
            print(f"[SocialAnalytics] [WARN] Błąd paginacji Graph API: {err_msg}")
            return items, err_msg

        batch = resp.get("data") or []
        if not batch:
            break
        remaining = max_items - len(items)
        items.extend(batch[:remaining])
        next_url = (resp.get("paging") or {}).get("next")
        next_params = None

    return items, None


def _parse_ig_insights_rows(ins_resp: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Wyciąga metryki /insights z odpowiedzi Graph API v21.0 dla Instagram Reel/Media."""
    parsed: Dict[str, Optional[float]] = {
        "views": 0,
        "reach": 0,
        "saved": 0,
        "shares": 0,
        "interactions": None,
        "avg_watch_time_ms": None,
        "total_watch_time_ms": None,
        "skip_rate_pct": None,
    }
    for row in ins_resp.get("data", []):
        metric_name = row.get("name")
        val = None
        if row.get("values"):
            val = row["values"][0].get("value")
        elif row.get("total_value"):
            val = row["total_value"].get("value")
        if val is None:
            continue

        if metric_name == "views":
            parsed["views"] = int(val)
        elif metric_name == "reach":
            parsed["reach"] = int(val)
        elif metric_name == "saved":
            parsed["saved"] = int(val)
        elif metric_name == "shares":
            parsed["shares"] = int(val)
        elif metric_name == "total_interactions":
            parsed["interactions"] = int(val)
        elif metric_name == "ig_reels_avg_watch_time":
            parsed["avg_watch_time_ms"] = int(val)
        elif metric_name == "ig_reels_video_view_total_time":
            parsed["total_watch_time_ms"] = int(val)
        elif metric_name == "reels_skip_rate":
            parsed["skip_rate_pct"] = round(float(val), 2)
    return parsed


def get_instagram_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera rzeczywiste statystyki profilu i wszystkich Rolek z Instagram Graph API v21.0 (z paginacją)."""
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
            "total_saved": 0,
            "total_shares": 0,
            "avg_watch_time_s": None,
            "avg_skip_rate_pct": None,
            "insights_errors": 0,
            "media_count_mismatch": False,
            "reels": []
        }

    try:
        token_info = json.loads(IG_TOKEN_FILE.read_text(encoding="utf-8"))
        access_token = token_info.get("access_token")
        ig_id = (
            token_info.get("instagram_business_account_id")
            or token_info.get("instagram_account_id")
            or "17841473819182842"
        )

        # 1. Pobierz profil Instagram Business
        prof_res = requests.get(
            f"https://graph.facebook.com/v21.0/{ig_id}",
            params={
                "fields": "username,name,followers_count,follows_count,media_count,profile_picture_url",
                "access_token": access_token
            },
            timeout=12
        ).json()

        if "error" in prof_res:
            err_msg = prof_res["error"].get("message", "Błąd Instagram API")
            if IG_CACHE_FILE.exists():
                try:
                    return json.loads(IG_CACHE_FILE.read_text(encoding="utf-8"))
                except Exception as exc:
                    print(f"[SocialAnalytics] [WARN] Błąd odczytu fallback cache IG: {exc}")
            return {"connected": False, "error": err_msg, "reels": [], "total_views": 0}

        username = prof_res.get("username", "dwannellenga")
        name = prof_res.get("name", "Dwannellenga")
        followers = prof_res.get("followers_count", 0)
        follows = prof_res.get("follows_count", 0)
        media_count = int(prof_res.get("media_count", 0) or 0)
        profile_pic = prof_res.get("profile_picture_url", "")

        # 2. Pobierz wszystkie media z pełną paginacją
        raw_media, ig_page_err = _paginate_graph_edges(
            f"https://graph.facebook.com/v21.0/{ig_id}/media",
            params={
                "fields": "id,caption,like_count,comments_count,permalink,timestamp,media_type,media_product_type",
                "limit": 50,
                "access_token": access_token,
            },
            max_items=200,
            timeout=12,
        )

        reels: List[Dict[str, Any]] = []
        total_views = 0
        total_reach = 0
        total_likes = 0
        total_comments = 0
        total_interactions = 0
        total_saved = 0
        total_shares = 0
        insights_errors = 0
        watch_times_s: List[float] = []
        skip_rates: List[float] = []

        for m in raw_media:
            m_id = m.get("id")
            caption = m.get("caption", "")
            likes = int(m.get("like_count", 0) or 0)
            comments = int(m.get("comments_count", 0) or 0)
            permalink = m.get("permalink", f"https://www.instagram.com/reel/{m_id}/")
            ts = m.get("timestamp", "")
            m_type = str(m.get("media_type") or "").upper()
            m_prod = str(m.get("media_product_type") or "").upper()
            is_reel = m_type in ("VIDEO", "REELS") or m_prod == "REELS" or not m_type

            views = 0
            reach = 0
            saved = 0
            shares = 0
            interactions = likes + comments
            avg_watch_time_ms: Optional[int] = None
            avg_watch_time_s: Optional[float] = None
            total_watch_time_ms: Optional[int] = None
            skip_rate_pct: Optional[float] = None

            base_metrics = "views,reach,saved,shares,total_interactions"
            ext_metrics = (
                "views,reach,saved,shares,total_interactions,"
                "ig_reels_avg_watch_time,ig_reels_video_view_total_time,reels_skip_rate"
            )
            try:
                req_metric = ext_metrics if is_reel else base_metrics
                ins_resp = requests.get(
                    f"https://graph.facebook.com/v21.0/{m_id}/insights",
                    params={"metric": req_metric, "access_token": access_token},
                    timeout=8,
                ).json()
                if "error" in ins_resp and req_metric != base_metrics:
                    err_ext = (ins_resp.get("error") or {}).get("message", "Błąd rozszerzonych metryk IG")
                    print(f"[SocialAnalytics] [WARN] Rozszerzone insights IG ({m_id}): {err_ext} — fallback bazowy")
                    ins_resp = requests.get(
                        f"https://graph.facebook.com/v21.0/{m_id}/insights",
                        params={"metric": base_metrics, "access_token": access_token},
                        timeout=8,
                    ).json()

                if "error" in ins_resp:
                    insights_errors += 1
                    err_ins = (ins_resp.get("error") or {}).get("message", "Błąd insights IG")
                    print(f"[SocialAnalytics] [WARN] Błąd insights IG ({m_id}): {err_ins}")
                else:
                    parsed = _parse_ig_insights_rows(ins_resp)
                    views = int(parsed["views"] or 0)
                    reach = int(parsed["reach"] or 0)
                    saved = int(parsed["saved"] or 0)
                    shares = int(parsed["shares"] or 0)
                    if parsed["interactions"] is not None:
                        interactions = max(int(parsed["interactions"]), likes + comments) if int(parsed["interactions"]) > 0 else (likes + comments)
                    if parsed["avg_watch_time_ms"] is not None:
                        avg_watch_time_ms = int(parsed["avg_watch_time_ms"])
                        if avg_watch_time_ms > 0:
                            avg_watch_time_s = round(avg_watch_time_ms / 1000.0, 2)
                            watch_times_s.append(avg_watch_time_s)
                    if parsed["total_watch_time_ms"] is not None:
                        total_watch_time_ms = int(parsed["total_watch_time_ms"])
                    if parsed["skip_rate_pct"] is not None:
                        skip_rate_pct = float(parsed["skip_rate_pct"])
                        skip_rates.append(skip_rate_pct)
            except Exception as exc:
                insights_errors += 1
                print(f"[SocialAnalytics] [WARN] Błąd insights IG ({m_id}): {exc}")

            total_views += views
            total_reach += reach
            total_likes += likes
            total_comments += comments
            total_interactions += interactions
            total_saved += saved
            total_shares += shares

            reels.append({
                "id": m_id,
                "title": caption.split("\n")[0][:80] if caption else f"Instagram Reel #{m_id}",
                "caption": caption,
                "url": permalink,
                "timestamp": ts,
                "media_type": m_type or None,
                "media_product_type": m_prod or None,
                "views": views,
                "reach": reach,
                "likes": likes,
                "comments": comments,
                "saved": saved,
                "shares": shares,
                "interactions": interactions,
                "engagement_rate": round((interactions / max(views, 1)) * 100, 2),
                "avg_watch_time_ms": avg_watch_time_ms,
                "avg_watch_time_s": avg_watch_time_s,
                "total_watch_time_ms": total_watch_time_ms,
                "skip_rate_pct": skip_rate_pct,
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
            "total_saved": total_saved,
            "total_shares": total_shares,
            "avg_views": avg_views,
            "avg_watch_time_s": round(sum(watch_times_s) / len(watch_times_s), 2) if watch_times_s else None,
            "avg_skip_rate_pct": round(sum(skip_rates) / len(skip_rates), 2) if skip_rates else None,
            "insights_errors": insights_errors,
            "media_count_mismatch": bool(media_count and len(reels) != media_count),
            "pagination_error": ig_page_err,
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
            except Exception as cache_err:
                print(f"[SocialAnalytics] [WARN] Błąd odczytu fallback cache IG: {cache_err}")
        return {"connected": False, "error": str(e), "reels": [], "total_views": 0}


def get_facebook_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera rzeczywiste statystyki fanpage'a i wszystkich wideo z Facebook Graph API v21.0 (z paginacją)."""
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
            "total_likes": 0,
            "total_reactions": 0,
            "total_comments": 0,
            "has_read_insights_permission": False,
            "videos": []
        }

    try:
        token_info = json.loads(FB_TOKEN_FILE.read_text(encoding="utf-8"))
        access_token = token_info.get("access_token")
        page_id = token_info.get("page_id") or "1398423656686108"
        scopes = token_info.get("scopes") or token_info.get("permissions") or []
        has_read_insights = "read_insights" in scopes
        metrics_limitation = (
            None
            if has_read_insights
            else (
                "Brak uprawnienia read_insights w tokenie Facebook Page — Graph API zwraca wyłącznie "
                "podstawowe pola wideo (views, likes.summary, comments.summary) bez video_insights."
            )
        )

        # 1. Pobierz dane Fanpage'a
        page_res = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}",
            params={
                "fields": "name,followers_count,fan_count,picture",
                "access_token": access_token
            },
            timeout=12
        ).json()

        if "error" in page_res:
            err_msg = page_res["error"].get("message", "Błąd Facebook API")
            if FB_CACHE_FILE.exists():
                try:
                    return json.loads(FB_CACHE_FILE.read_text(encoding="utf-8"))
                except Exception as cache_err:
                    print(f"[SocialAnalytics] [WARN] Błąd odczytu fallback cache FB: {cache_err}")
            return {"connected": False, "error": err_msg, "videos": [], "total_views": 0}

        page_name = page_res.get("name", "Dwannellenga")
        followers = page_res.get("followers_count", 0)
        fan_count = page_res.get("fan_count", 0)
        picture_url = page_res.get("picture", {}).get("data", {}).get("url", "")

        # 2. Pobierz wszystkie wideo z paginacją i działającymi polami v21.0 (bez nieistniejącego 'reactions')
        raw_videos, fb_page_err = _paginate_graph_edges(
            f"https://graph.facebook.com/v21.0/{page_id}/videos",
            params={
                "fields": "id,description,permalink_url,created_time,length,views,likes.summary(true),comments.summary(true)",
                "limit": 50,
                "access_token": access_token,
            },
            max_items=200,
            timeout=12,
        )

        videos: List[Dict[str, Any]] = []
        total_views = 0
        total_likes = 0
        total_comments = 0

        for v in raw_videos:
            v_id = v.get("id")
            desc = v.get("description", "")
            views = int(v.get("views", 0) or 0)
            perm = v.get("permalink_url") or f"/reel/{v_id}/"
            if perm.startswith("/"):
                perm = f"https://www.facebook.com{perm}"
            created_time = v.get("created_time", "")
            length_raw = v.get("length")
            length_s = round(float(length_raw), 2) if length_raw is not None else None
            likes = int((v.get("likes") or {}).get("summary", {}).get("total_count", 0) or 0)
            comments = int((v.get("comments") or {}).get("summary", {}).get("total_count", 0) or 0)

            total_views += views
            total_likes += likes
            total_comments += comments

            videos.append({
                "id": v_id,
                "title": desc.split("\n")[0][:80] if desc else f"Facebook Reel #{v_id}",
                "description": desc,
                "url": perm,
                "timestamp": created_time,
                "length_s": length_s,
                "views": views,
                "likes": likes,
                "reactions": likes,
                "comments": comments,
                "engagement": likes + comments
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
            "total_likes": total_likes,
            "total_reactions": total_likes,
            "total_comments": total_comments,
            "avg_views": avg_views,
            "has_read_insights_permission": has_read_insights,
            "metrics_limitation": metrics_limitation,
            "pagination_error": fb_page_err,
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
            except Exception as cache_err:
                print(f"[SocialAnalytics] [WARN] Błąd odczytu fallback cache FB: {cache_err}")
        return {"connected": False, "error": str(e), "videos": [], "total_views": 0}


def _build_tiktok_learning(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analizuje wszystkie filmy na TikToku (@dwannellenga) pod kątem tagów i hooków."""
    import re
    tag_stats: Dict[str, Dict[str, float]] = {}
    for v in videos:
        raw_text = f"{v.get('desc') or ''} {v.get('title') or ''}"
        found_tags = {t.lower() for t in re.findall(r"#([a-zA-Z0-9_]+)", raw_text)}
        views = int(v.get("views") or 0)
        likes = int(v.get("likes") or 0)
        for tag in found_tags:
            if not tag or tag in _YT_ONLY_TAG_BLOCKLIST:
                continue
            bucket = tag_stats.setdefault(tag, {"count": 0, "total_views": 0, "total_likes": 0})
            bucket["count"] += 1
            bucket["total_views"] += views
            bucket["total_likes"] += likes

    top_hashtags: List[Dict[str, Any]] = []
    for tag, st in tag_stats.items():
        cnt = int(st["count"])
        tv = int(st["total_views"])
        tl = int(st["total_likes"])
        top_hashtags.append({
            "tag": tag,
            "count": cnt,
            "total_views": tv,
            "avg_views": round(tv / max(cnt, 1), 1),
            "avg_likes": round(tl / max(cnt, 1), 1),
        })

    min_reliable = 5 if len(videos) >= 15 else 2
    top_hashtags.sort(
        key=lambda x: (1 if x["count"] >= min_reliable else 0, x["avg_views"], x["total_views"]),
        reverse=True,
    )

    recommended = [h["tag"] for h in top_hashtags[:5]]
    for fallback_tag in ("outplayed", "pcgaming", "leagueoflegends", "lolhighlights", "katarina"):
        if len(recommended) >= 5:
            break
        if fallback_tag not in recommended:
            recommended.append(fallback_tag)

    sorted_by_views = sorted(videos, key=lambda x: int(x.get("views") or 0), reverse=True)
    top_hooks: List[Dict[str, Any]] = []
    for v in sorted_by_views[:5]:
        raw_hook = str(v.get("title") or v.get("desc") or "").split("#")[0].strip()
        if not raw_hook:
            raw_hook = str(v.get("title") or "TikTok Short")
        top_hooks.append({
            "title": raw_hook[:120],
            "views": int(v.get("views") or 0),
            "likes": int(v.get("likes") or 0),
            "comments": int(v.get("comments") or 0),
            "url": v.get("url") or "",
            "post_id": v.get("post_id") or v.get("id") or "",
        })

    return {
        "analyzed_videos": len(videos),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "top_hashtags": top_hashtags[:12],
        "recommended_hashtags": recommended[:5],
        "top_hooks": top_hooks,
    }


def get_tiktok_analytics(force_refresh: bool = False) -> Dict[str, Any]:
    """Pobiera profil, wszystkie zsynchronizowane filmy TikTok oraz analizę Synapsy (tagi i hooki)."""
    if not force_refresh:
        cached = _read_cache(TT_CACHE_FILE)
        if cached and cached.get("tiktok_learning"):
            return cached

    if not TT_TOKEN_FILE.exists() and not TT_POST_CACHE_FILE.exists():
        return {
            "connected": False,
            "message": "Brak połączonego konta TikTok.",
            "profile": None,
            "videos": [],
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "avg_views": 0,
            "tiktok_learning": _build_tiktok_learning([]),
        }

    try:
        import re
        access_token = ""
        days_left = 0
        display_name = "Dwannellenga"
        avatar_url = ""
        open_id = ""
        unique_id = "dwannellenga"

        if TT_TOKEN_FILE.exists():
            token_info = json.loads(TT_TOKEN_FILE.read_text(encoding="utf-8"))
            access_token = token_info.get("access_token") or ""
            now = int(time.time())
            refresh_expires_at = token_info.get("refresh_expires_at", 0)
            days_left = max(0, int((refresh_expires_at - now) / 86400))

            if access_token:
                try:
                    user_res = requests.get(
                        "https://open.tiktokapis.com/v2/user/info/",
                        headers={"Authorization": f"Bearer {access_token}"},
                        params={"fields": "open_id,union_id,avatar_url,display_name"},
                        timeout=10,
                    ).json()
                    user_data = user_res.get("data", {}).get("user", {})
                    display_name = user_data.get("display_name") or display_name
                    avatar_url = user_data.get("avatar_url") or avatar_url
                    open_id = user_data.get("open_id") or open_id
                except Exception as exc:
                    print(f"[SocialAnalytics] [WARN] Błąd user/info TikTok: {exc}")

        # 2. Pobranie danych profilu z live web hydration
        followers_count = 10
        following_count = 3
        heart_count = 312
        video_count = 35

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

        # 3. Odczyt wszystkich filmów z tiktok_post_cache.json
        post_cache: Dict[str, Any] = {}
        if TT_POST_CACHE_FILE.exists():
            try:
                post_cache = json.loads(TT_POST_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[SocialAnalytics] [WARN] Błąd odczytu tiktok_post_cache.json: {exc}")
                post_cache = {}

        # Zindeksuj istniejące posty po post_id, żeby uzupełnić brakujące wpisy z .meta.json bez duplikatów
        headers_api = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        temp_dir = ROOT_DIR / "lol_agent" / "lol_temp"
        meta_files = sorted(list(temp_dir.glob("*.meta.json")), key=lambda p: p.stat().st_mtime, reverse=True) if temp_dir.exists() else []
        cache_modified = False

        for mf in meta_files:
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
                tt_res = (m.get("multi_results") or {}).get("tiktok") or {}
                pid = tt_res.get("publish_id")
                if not pid:
                    continue

                p_entry = dict(post_cache.get(pid) or {})
                post_id = p_entry.get("post_id")

                if not post_id and access_token:
                    try:
                        st_res = requests.post(
                            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                            headers=headers_api,
                            json={"publish_id": pid},
                            timeout=6,
                        ).json()
                        st_data = st_res.get("data", {})
                        p_ids = st_data.get("publicaly_available_post_id", [])
                        if p_ids:
                            post_id = str(p_ids[0])
                            p_entry["post_id"] = post_id
                            cache_modified = True
                    except Exception as exc:
                        print(f"[SocialAnalytics] [WARN] Błąd status/fetch TikTok ({pid}): {exc}")

                if post_id and not p_entry.get("synced_from_profile") and (force_refresh or "views" not in p_entry or p_entry.get("views", 0) == 0):
                    try:
                        v_res = requests.get(f"https://www.tiktok.com/@{unique_id}/video/{post_id}", headers=headers_web, timeout=6)
                        v_match = re.search(r'<script id=.__UNIVERSAL_DATA_FOR_REHYDRATION__.[^>]*>(.*?)</script>', v_res.text)
                        if v_match:
                            v_raw = json.loads(v_match.group(1))
                            item = v_raw.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {}).get("itemInfo", {}).get("itemStruct", {})
                            v_stats = item.get("stats", {})
                            if v_stats:
                                p_entry["views"] = int(v_stats.get("playCount", 0))
                                p_entry["likes"] = int(v_stats.get("diggCount", 0))
                                p_entry["comments"] = int(v_stats.get("commentCount", 0))
                                p_entry["shares"] = int(v_stats.get("shareCount", 0))
                                p_entry["desc"] = item.get("desc", p_entry.get("desc", ""))
                                p_entry["url"] = f"https://www.tiktok.com/@{unique_id}/video/{post_id}"
                                cache_modified = True
                    except Exception as exc:
                        print(f"[SocialAnalytics] [WARN] Błąd web scrape TikTok ({post_id}): {exc}")

                clean_title = p_entry.get("desc") or m.get("hook_text") or m.get("title") or "TikTok Short"
                if "#" in clean_title:
                    clean_title = clean_title.split("#")[0].strip() or clean_title

                p_entry["id"] = post_id or pid
                p_entry["title"] = p_entry.get("title") or clean_title
                p_entry["publish_id"] = pid
                p_entry["url"] = p_entry.get("url") or f"https://www.tiktok.com/@{unique_id}"
                p_entry["timestamp"] = p_entry.get("timestamp") or m.get("rendered_at") or m.get("published_at") or ""
                p_entry["views"] = int(p_entry.get("views") or 0)
                p_entry["likes"] = int(p_entry.get("likes") or 0)
                p_entry["comments"] = int(p_entry.get("comments") or 0)
                p_entry["shares"] = int(p_entry.get("shares") or 0)

                post_cache[pid] = p_entry
            except Exception as exc:
                print(f"[SocialAnalytics] [WARN] Błąd meta TikTok ({mf.name}): {exc}")

        # Scal wszystkie wpisy z post_cache po unikalnym kluczu post_id (preferując bogatszy wpis)
        dedup_videos: Dict[str, Dict[str, Any]] = {}
        for cache_key, raw_entry in post_cache.items():
            if not isinstance(raw_entry, dict):
                continue
            canonical_id = str(raw_entry.get("post_id") or raw_entry.get("id") or cache_key).strip()
            if not canonical_id:
                continue
            desc = str(raw_entry.get("desc") or "").strip()
            raw_title = str(raw_entry.get("title") or desc or f"TikTok Short #{canonical_id[-6:]}")
            clean_title = raw_title.split("#")[0].strip() if "#" in raw_title else raw_title
            if not clean_title:
                clean_title = f"TikTok Short #{canonical_id[-6:]}"

            normalized = {
                **raw_entry,
                "id": canonical_id,
                "post_id": raw_entry.get("post_id") or (canonical_id if canonical_id.isdigit() else None),
                "title": clean_title,
                "desc": desc,
                "url": raw_entry.get("url") or (
                    f"https://www.tiktok.com/@{unique_id}/video/{canonical_id}"
                    if canonical_id.isdigit()
                    else f"https://www.tiktok.com/@{unique_id}"
                ),
                "timestamp": raw_entry.get("timestamp") or "",
                "views": int(raw_entry.get("views") or 0),
                "likes": int(raw_entry.get("likes") or 0),
                "comments": int(raw_entry.get("comments") or 0),
                "shares": int(raw_entry.get("shares") or 0),
            }

            existing = dedup_videos.get(canonical_id)
            if not existing or normalized["views"] > existing.get("views", 0) or (len(normalized["desc"]) > len(existing.get("desc") or "")):
                dedup_videos[canonical_id] = normalized

        videos = sorted(
            dedup_videos.values(),
            key=lambda x: (str(x.get("timestamp") or ""), str(x.get("post_id") or x.get("id") or "")),
            reverse=True,
        )

        if cache_modified:
            try:
                TT_POST_CACHE_FILE.write_text(json.dumps(post_cache, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                print(f"[SocialAnalytics] [WARN] Błąd zapisu tiktok_post_cache.json: {exc}")

        tiktok_learning = _build_tiktok_learning(videos)
        try:
            ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
            TT_LEARNING_FILE.write_text(
                json.dumps(tiktok_learning, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            print(f"[SocialAnalytics] [WARN] Błąd zapisu tiktok_learning.json: {exc}")

        total_views = sum(int(v.get("views") or 0) for v in videos)
        total_likes = sum(int(v.get("likes") or 0) for v in videos)
        total_comments = sum(int(v.get("comments") or 0) for v in videos)
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
                "heart_count": max(heart_count, total_likes),
                "video_count": max(video_count, len(videos)),
            },
            "count": len(videos),
            "api_videos_only": False,
            "profile_total_videos": max(video_count, len(videos)),
            "profile_total_hearts": max(heart_count, total_likes),
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "avg_views": avg_views,
            "top_videos": sorted(videos, key=lambda x: int(x.get("views") or 0), reverse=True)[:5],
            "videos": videos,
            "tiktok_learning": tiktok_learning,
        }

        _write_cache(TT_CACHE_FILE, result)
        return result

    except Exception as e:
        print(f"❌ Wyjątek get_tiktok_analytics: {e}")
        return {
            "connected": False,
            "error": str(e),
            "videos": [],
            "total_views": 0,
            "tiktok_learning": _build_tiktok_learning([]),
        }


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
    yt_total_views_sampled = sum(v.get("views", 0) for v in yt_videos)
    yt_total_likes = sum(v.get("likes", 0) for v in yt_videos)
    yt_total_comments = sum(v.get("comments", 0) for v in yt_videos)

    # FIX: Use channel-level statistics for accurate all-time total views.
    # _sync_youtube_analytics fetches only the last ~50 videos, missing older ones.
    # channels.list(statistics).viewCount returns the real channel lifetime total.
    yt_total_views = yt_total_views_sampled  # safe fallback
    try:
        import pickle
        from lol_agent.api.config import YT_TOKEN_PATH
        from googleapiclient.discovery import build as _yt_build
        if YT_TOKEN_PATH.exists():
            with open(YT_TOKEN_PATH, "rb") as _f:
                _creds = pickle.load(_f)
            if _creds and _creds.valid:
                _yt_svc = _yt_build("youtube", "v3", credentials=_creds)
                _ch = _yt_svc.channels().list(part="statistics", mine=True).execute()
                _items = _ch.get("items", [])
                if _items:
                    _ch_views = int(_items[0].get("statistics", {}).get("viewCount", 0))
                    if _ch_views > yt_total_views_sampled:
                        yt_total_views = _ch_views  # use real channel total
    except Exception as _yt_views_err:
        print(f"[SocialAnalytics] [WARN] Błąd pobrania lifetime views YT: {_yt_views_err}")  # keep sampled fallback if API fails

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
