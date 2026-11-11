"""
Shortsyt — Multi-Platform Publisher.
Uruchamia publikację wideo równolegle na wszystkich wybranych platformach
(YouTube Shorts, TikTok, Instagram Reels) w osobnych wątkach, zapewniając pełną izolację błędów.
"""
import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from lol_agent.lol_publisher import upload_lol_short
from lol_agent.tiktok_publisher import upload_tiktok_short, get_tiktok_token_status
from lol_agent.instagram_publisher import upload_instagram_reel, get_instagram_token_status
from lol_agent.facebook_publisher import upload_facebook_reel, get_facebook_token_status



def resolve_video_thumbnail(
    video_path: str,
    thumbnail_path: Optional[str] = None,
    peak_moment: Optional[float] = None
) -> Optional[str]:
    """
    Automatycznie lokalizuje lub generuje miniaturkę dla wideo (9:16).
    1. Sprawdza czy thumbnail_path istnieje.
    2. Sprawdza pliki _thumb.jpg obok wideo oraz w katalogach thumbnails/.
    3. Jeśli brak, wycina klatkę wideo w punkcie szczytowym (peak_moment) za pomocą ffmpeg.
    """
    if thumbnail_path and os.path.exists(thumbnail_path):
        return str(Path(thumbnail_path).resolve())

    vp = Path(video_path).resolve()
    stem = vp.stem

    candidates = [
        vp.parent / f"{stem}_thumb.jpg",
        vp.parent / f"{stem}.jpg",
        ROOT_DIR / "lol_agent" / "lol_temp" / f"{stem}_thumb.jpg",
        ROOT_DIR / "lol_agent" / "thumbnails" / f"{stem}_thumb.jpg",
        ROOT_DIR / "thumbnails" / f"{stem}_thumb.jpg",
    ]

    for c in candidates:
        if c.exists():
            return str(c)

    # Autogeneracja klatki przez ffmpeg jeśli miniatura nie istnieje
    try:
        target = vp.parent / f"{stem}_thumb.jpg"
        seek_s = max(0.5, float(peak_moment)) if (peak_moment and peak_moment > 0) else 2.5
        cmd = f'ffmpeg -y -ss {seek_s} -i "{vp}" -vframes 1 -q:v 2 "{target}"'
        import subprocess
        res = subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if target.exists():
            print(f"🖼️ [AutoThumb] Wygenerowano automatyczną miniaturkę: {target.name}")
            return str(target)
    except Exception as e:
        print(f"⚠️ [AutoThumb] Wyjątek podczas generowania miniatury: {e}")

    return None

def publish_multi_platform(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    hashtags: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    privacy_yt: str = "public",
    privacy_tiktok: str = "PUBLIC_TO_EVERYONE",
    share_to_ig_feed: bool = True,
    thumbnail_path: Optional[str] = None,
    publish_at: Optional[str] = None,
    copy_by_platform: Optional[Dict[str, Dict[str, Any]]] = None,
    pinned_comment: Optional[str] = None,
    champion_name: Optional[str] = None,
    action_type: Optional[str] = None,
    rank: Optional[str] = None,
    peak_moment: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Równoległa publikacja na YouTube Shorts, TikTok, Instagram Reels oraz Facebook Page.
    platforms: lista np. ["youtube", "tiktok", "instagram", "facebook"]. Domyślnie pierwsze trzy.
    Zwraca słownik ze statusem dla każdej platformy.
    """
    if platforms is None:
        platforms = ["youtube", "tiktok", "instagram"]

    resolved_thumb = resolve_video_thumbnail(video_path, thumbnail_path, peak_moment)
    champ_guess = champion_name or "Katarina"
    act_guess = action_type or "outplay"
    if not champion_name:
        for t in (tags or []) + (hashtags or []):
            t_clean = t.strip("#").strip()
            if t_clean.lower() not in ["shorts", "lol", "leagueoflegends", "gaming", "outplay", "highlight"]:
                champ_guess = t_clean
                break

    if not copy_by_platform:
        try:
            from lol_agent.multi_platform_copywriter import generate_all_platform_copy
            copy_by_platform = generate_all_platform_copy(
                champion=champ_guess,
                action_type=act_guess,
                base_metadata={"title": title, "description": description, "tags": tags or []},
                platforms=platforms,
            )
        except Exception as _cp_err:
            print(f"⚠️ [multi_publisher] Auto-copy generation fallback: {_cp_err}")
            copy_by_platform = {}

    copy_by_platform = copy_by_platform or {}
    results = {}

    def _do_youtube():
        try:
            yt_copy = copy_by_platform.get("youtube", {})
            yt_title = yt_copy.get("title") or title
            yt_desc = yt_copy.get("description") or description
            yt_tags = yt_copy.get("tags") or tags or []
            if not yt_tags or len(yt_tags) < 10:
                try:
                    from lol_agent.lol_metadata_generator import build_rich_youtube_tags
                    yt_tags = build_rich_youtube_tags(champ_guess, act_guess, rank or "Challenger")
                except Exception:
                    yt_tags = yt_copy.get("hashtags") or tags or []

            yt_res = upload_lol_short(
                video_path=video_path,
                title=yt_title,
                description=yt_desc,
                tags=yt_tags,
                privacy=privacy_yt,
                thumbnail_path=resolved_thumb,
                publish_at=publish_at,
                pinned_comment=pinned_comment,
            )
            return {
                "success": True,
                "video_id": yt_res.get("video_id"),
                "url": yt_res.get("url"),
                "title": yt_res.get("title"),
                "publish_at": yt_res.get("publish_at") or publish_at,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "youtube"}

    def _do_tiktok():
        try:
            tt_copy = copy_by_platform.get("tiktok", {})
            tt_title = tt_copy.get("title") or title
            tt_tags = tt_copy.get("hashtags") or hashtags or tags or []
            return upload_tiktok_short(
                video_path=video_path,
                title=tt_title,
                hashtags=tt_tags,
                privacy_level=privacy_tiktok,
                publish_at=publish_at,
                thumbnail_path=resolved_thumb
            )
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "tiktok"}

    def _do_instagram():
        try:
            ig_copy = copy_by_platform.get("instagram", {})
            ig_caption = ig_copy.get("caption")
            if not ig_caption:
                ig_tags = hashtags or tags or []
                tag_str = " ".join(f"#{t.strip('#').lower()}" for t in ig_tags if t.strip())
                fb_funnel = "🔗 Więcej akcji i powtórek na FB: facebook.com/Dwannellenga\n🎬 TikTok: @dwannellenga | YouTube: Dwannellenga"
                ig_caption = f"{title}\n\n{fb_funnel}\n\n.\n.\n.\n{tag_str}".strip() if tag_str else f"{title}\n\n{fb_funnel}"
            return upload_instagram_reel(
                video_path=video_path,
                caption=ig_caption,
                share_to_feed=share_to_ig_feed,
                thumbnail_path=resolved_thumb,
                peak_moment=peak_moment,
                publish_at=publish_at
            )
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "instagram"}

    def _do_facebook():
        try:
            fb_copy = copy_by_platform.get("facebook", {})
            fb_caption = fb_copy.get("caption") or title
            return upload_facebook_reel(
                video_path=video_path,
                caption=fb_caption,
                publish_at=publish_at,
                thumbnail_path=resolved_thumb
            )
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "facebook"}

    tasks = {}
    with ThreadPoolExecutor(max_workers=max(1, len(platforms))) as executor:
        if "youtube" in platforms:
            tasks[executor.submit(_do_youtube)] = "youtube"
        if "tiktok" in platforms:
            tasks[executor.submit(_do_tiktok)] = "tiktok"
        if "instagram" in platforms:
            tasks[executor.submit(_do_instagram)] = "instagram"
        if "facebook" in platforms:
            tasks[executor.submit(_do_facebook)] = "facebook"

        for future in as_completed(tasks):
            plat = tasks[future]
            try:
                results[plat] = future.result(timeout=300)
            except Exception as exc:
                results[plat] = {"success": False, "error": f"Timeout lub wyjątek wątku: {exc}", "platform": plat}

    return results
