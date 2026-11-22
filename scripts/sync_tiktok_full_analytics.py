"""
Shortsyt — Pełny skan i synchronizacja kanału TikTok (@dwannellenga)
Łączy się przez zalogowaną sesję Chrome w accounts/tiktok_web_profile, pobiera wszystkie
opublikowane filmy z profilu @dwannellenga (wyświetlenia, polubienia, komentarze, opisy i tagi),
zapisuje je do accounts/tiktok_post_cache.json, a następnie odświeża analitykę i model Synapsy dla TikToka.
"""
import os
import sys
import re
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

ACCOUNTS_DIR = PROJECT_ROOT / "accounts"
WEB_PROFILE_DIR = ACCOUNTS_DIR / "tiktok_web_profile"
TT_POST_CACHE_FILE = ACCOUNTS_DIR / "tiktok_post_cache.json"


def sync_tiktok_profile_videos(unique_id: str = "dwannellenga") -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    WEB_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    captured_items: Dict[str, Dict[str, Any]] = {}
    profile_stats: Dict[str, Any] = {}

    with sync_playwright() as pw:
        launch_args = {
            "user_data_dir": str(WEB_PROFILE_DIR),
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--window-position=-2200,0",
                "--window-size=1280,900",
            ],
        }
        try:
            ctx = pw.chromium.launch_persistent_context(channel="chrome", **launch_args)
        except Exception:
            ctx = pw.chromium.launch_persistent_context(**launch_args)

        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            def _on_response(resp):
                u = resp.url
                if "api/post/item_list" in u or "creator/item_list" in u:
                    try:
                        payload = resp.json()
                    except Exception:
                        return
                    lst = (
                        payload.get("itemList")
                        or payload.get("items")
                        or (payload.get("data") or {}).get("itemList")
                        or []
                    )
                    for it in lst:
                        author_uid = str((it.get("author") or {}).get("uniqueId") or "").strip().lower()
                        if author_uid and author_uid != unique_id.lower():
                            continue
                        vid_id = str(it.get("id") or "").strip()
                        if vid_id:
                            captured_items[vid_id] = it

            page.on("response", _on_response)
            page.goto(f"https://www.tiktok.com/@{unique_id}", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4500)

            for _ in range(5):
                prev_cnt = len(captured_items)
                page.mouse.wheel(0, 3200)
                page.wait_for_timeout(1800)
                if len(captured_items) == prev_cnt and prev_cnt >= 30:
                    break

            # Pobierz też aktualne statystyki profilu z DOM/hydration JSON
            try:
                html_text = page.content()
                m = re.search(
                    r'<script id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>',
                    html_text,
                    re.S,
                )
                if m:
                    uinfo = (
                        json.loads(m.group(1))
                        .get("__DEFAULT_SCOPE__", {})
                        .get("webapp.user-detail", {})
                        .get("userInfo", {})
                    )
                    st = uinfo.get("stats", {})
                    if st:
                        profile_stats["followers_count"] = int(st.get("followerCount", 0))
                        profile_stats["following_count"] = int(st.get("followingCount", 0))
                        profile_stats["heart_count"] = int(st.get("heartCount", 0))
                        profile_stats["video_count"] = int(st.get("videoCount", 0))
            except Exception:
                pass
        finally:
            ctx.close()

    existing_cache: Dict[str, Any] = {}
    if TT_POST_CACHE_FILE.exists():
        try:
            raw_prev = json.loads(TT_POST_CACHE_FILE.read_text(encoding="utf-8"))
            for k, v in raw_prev.items():
                if not isinstance(v, dict):
                    continue
                # Zachowaj tylko wpisy publish_id lub filmy przechwycone jako własne autora
                if k.startswith("v_inbox_file~") or k in captured_items:
                    existing_cache[k] = v
        except Exception:
            existing_cache = {}

    # Mapuj istniejące post_id na klucze cache, żeby uniknąć duplikatów z v_inbox_file~...
    pid_to_cache_key: Dict[str, str] = {}
    for k, entry in existing_cache.items():
        if isinstance(entry, dict):
            pid_val = str(entry.get("post_id") or entry.get("id") or "").strip()
            if pid_val:
                pid_to_cache_key[pid_val] = k

    updated_count = 0
    for vid_id, it in captured_items.items():
        stats = it.get("stats") or {}
        desc = str(it.get("desc") or "").strip()
        create_ts = int(it.get("createTime") or 0)
        ts_iso = (
            datetime.fromtimestamp(create_ts, tz=timezone.utc).isoformat()
            if create_ts > 0
            else ""
        )
        target_key = pid_to_cache_key.get(vid_id, vid_id)
        prev = existing_cache.get(target_key) if isinstance(existing_cache.get(target_key), dict) else {}
        clean_title = desc.split("#")[0].strip() if "#" in desc else desc
        if not clean_title:
            prev_title = str(prev.get("title") or "").strip()
            if prev_title and not prev_title.startswith("TikTok Short"):
                clean_title = prev_title
            elif vid_id == "7704512367207484694":
                clean_title = "SOLO BOLO - EGO CHECKED"
            else:
                clean_title = f"TikTok Short #{vid_id[-6:]}"
        merged = {
            **prev,
            "id": vid_id,
            "post_id": vid_id,
            "views": int(stats.get("playCount", prev.get("views", 0))),
            "likes": int(stats.get("diggCount", prev.get("likes", 0))),
            "comments": int(stats.get("commentCount", prev.get("comments", 0))),
            "shares": int(stats.get("shareCount", prev.get("shares", 0))),
            "desc": desc or prev.get("desc", ""),
            "title": clean_title,
            "url": f"https://www.tiktok.com/@{unique_id}/video/{vid_id}",
            "timestamp": ts_iso or prev.get("timestamp", ""),
            "synced_from_profile": True,
        }
        existing_cache[target_key] = merged
        updated_count += 1

    TT_POST_CACHE_FILE.write_text(
        json.dumps(existing_cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "captured": len(captured_items),
        "updated": updated_count,
        "total_cached": len(existing_cache),
        "profile_stats": profile_stats,
    }


if __name__ == "__main__":
    summary = sync_tiktok_profile_videos("dwannellenga")
    print("SYNC SUMMARY:", json.dumps(summary, ensure_ascii=False))

    from lol_agent.social_analytics import get_tiktok_analytics, get_omnichannel_analytics, OMNI_CACHE_FILE

    tt_res = get_tiktok_analytics(force_refresh=True)
    OMNI_CACHE_FILE.unlink(missing_ok=True)
    omni_res = get_omnichannel_analytics(force_refresh=False)
    tl = tt_res.get("tiktok_learning") or {}
    print(
        f"TIKTOK ANALYTICS: videos={tt_res.get('count')} total_views={tt_res.get('total_views')} "
        f"rec_tags={tl.get('recommended_hashtags')}"
    )
    print(
        f"OMNICHANNEL ANALYTICS: grand_total_views={omni_res.get('grand_total_views')} "
        f"tt_count={(omni_res.get('platforms') or {}).get('tiktok', {}).get('videos_count')}"
    )
