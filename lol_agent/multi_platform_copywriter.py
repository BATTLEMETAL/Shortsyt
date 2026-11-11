"""
Shortsyt — Multi-Platform Copywriter v1
Generates platform-specific titles, captions and hashtags for each distribution channel.

Wraps existing lol_metadata_generator + lol_smart_titles — does NOT duplicate their logic.
Each platform function returns a dict:
    {
        "title": str,       # the actual title / first line / hook text
        "caption": str,     # full body text (title + hashtags combined where applicable)
        "hashtags": list,   # list of raw tag strings (no # prefix)
        "platform": str,    # "youtube" | "tiktok" | "instagram" | "facebook"
    }

Platform content rules (based on what drives reach per algorithm):
  YouTube Shorts — title is indexed, up to 100 chars; hashtags appended in description
                    emotional + action keywords, emoji OK, avoid "TikTok" / "Instagram"
  TikTok          — no separate title field on API; first caption line = hook (<=100 chars)
                    2–5 focused hashtags in caption, shorter text wins
  Instagram Reels — caption up to 2200 chars; 5-15 hashtags as block at end
                    storytelling hook in first 1-2 lines (visible before "more")
  Facebook        — caption as sentence, NOT a list; 1-3 hashtags max
                    avoid hashtag spam — lowers organic reach on FB
"""

from __future__ import annotations

import os
import re
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from google import genai
    GENAI_OK = True
except ImportError:
    GENAI_OK = False

try:
    from lol_agent.lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS
except ImportError:
    try:
        from lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS
    except ImportError:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        GEMINI_MODEL = "gemini-2.5-flash"
        GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-flash-latest"]


# ─── Hashtag bank per platform ────────────────────────────────────────────────

def _yt_hashtags(champion: str, action_type: str) -> List[str]:
    """YouTube: canonical lowercase tags used in description for proper indexing without autocorrect."""
    clean = re.sub(r"['\s]", "", champion).lower() if champion else "katarina"
    action_map = {
        "pentakill": ["pentakill", "penta"],
        "quadrakill": ["quadrakill", "quadra"],
        "triple": ["triplekill", "triple"],
        "double": ["doublekill", "double"],
        "solo_bolo": ["outplay", "1v1", "solokill"],
        "outplay": ["outplay", "mechanics"],
        "clutch": ["clutch", "outplay"],
    }
    action_tags = action_map.get(action_type.lower(), ["outplay"])
    return [
        "shorts", "shortsfeed", "leagueoflegends", "lol", clean,
        f"{clean}montage",
        *action_tags,
        "lolhighlights", "gaming", "lolgaming",
    ]


def _tiktok_hashtags(champion: str, action_type: str) -> List[str]:
    """TikTok: 3–5 focused tags only — wider tags are algorithmically broader."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    action_map = {
        "pentakill": ["pentakill", "lol"],
        "quadrakill": ["quadrakill", "lol"],
        "triple": ["triplekill", "lol"],
        "solo_bolo": ["outplay", "lol", "1v1"],
        "outplay": ["outplay", "lol"],
        "clutch": ["clutch", "lol"],
    }
    action_tags = action_map.get(action_type.lower(), ["outplay", "lol"])
    return ["leagueoflegends", clean.lower(), *action_tags, "gaming"][:5]


def _instagram_hashtags(champion: str, action_type: str) -> List[str]:
    """Instagram: 10–15 mixed niche + broad tags."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    action_map = {
        "pentakill": ["pentakill", "penta", "lolpentakill"],
        "quadrakill": ["quadrakill", "lolquadra"],
        "triple": ["triplekill", "lol"],
        "solo_bolo": ["outplay", "1v1", "solobolo"],
        "outplay": ["outplay", "loloutplay"],
        "clutch": ["clutch", "outplay"],
    }
    action_tags = action_map.get(action_type.lower(), ["outplay"])
    return [
        "leagueoflegends", "lol", "gaming", clean.lower(),
        *action_tags,
        "lolhighlights", "gamingclips", "reels", "gamingcommunity",
        f"{clean.lower()}gameplay", "esports",
    ][:15]


def _facebook_hashtags(champion: str, action_type: str) -> List[str]:
    """Facebook: 1–3 tags MAXIMUM — FB algorithm penalises hashtag spam."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    return ["LeagueOfLegends", clean, "Gaming"]


# ─── Gemini helper ────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, max_retries: int = 2) -> str:
    """Calls Gemini with retry. Returns empty string on failure."""
    if not GENAI_OK or not GEMINI_API_KEY:
        return ""
    models = [GEMINI_MODEL] + list(GEMINI_FALLBACK_MODELS)
    for attempt in range(max_retries):
        for model in models:
            try:
                client = genai.Client(api_key=GEMINI_API_KEY)
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                return (resp.text or "").strip()
            except Exception as e:
                print(f"   ⚠️  Gemini {model} error: {e}")
                time.sleep(1)
    return ""


# ─── Per-platform generators ──────────────────────────────────────────────────

def generate_youtube_copy(
    champion: str,
    action_type: str,
    yt_history: Optional[List[Dict]] = None,
    base_metadata: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    YouTube copy — wraps existing lol_smart_titles / lol_metadata_generator output.
    If base_metadata already contains a title (from smart_titles), just enriches it.
    """
    title = ""
    description = ""
    tags: List[str] = []
    hashtags: List[str] = []

    # Prefer the already-generated smart title (avoids duplicate Gemini call)
    if base_metadata:
        title = base_metadata.get("title", "")
        description = base_metadata.get("description", "")
        tags = base_metadata.get("tags", [])
        hashtags = base_metadata.get("hashtags", [])

    if not title:
        # Fallback to a deterministic title if Gemini unavailable
        action_label = {
            "pentakill": "PENTAKILL",
            "quadrakill": "QUADRAKILL",
            "triple": "TRIPLE KILL",
            "solo_bolo": "SOLO BOLO 👑",
            "outplay": "OUTPLAY",
            "clutch": "CLUTCH",
        }.get(action_type.lower(), action_type.upper())
        title = f"{champion} {action_label} 🔥 #Shorts"

    if not hashtags:
        hashtags = _yt_hashtags(champion, action_type)

    if not tags or len(tags) < 10:
        try:
            from lol_agent.lol_metadata_generator import build_rich_youtube_tags
            tags = build_rich_youtube_tags(champion, action_type)
        except Exception:
            tags = hashtags

    if not description or "facebook.com/Dwannellenga" not in description:
        try:
            from lol_agent.lol_metadata_generator import build_channel_description
            description = build_channel_description(champion, action_type, description)
        except Exception:
            tag_str = " ".join(f"#{t.lower()}" for t in hashtags)
            description = f"{tag_str}\n\nLeague of Legends Short — {champion}"

    caption = f"{title}\n\n{description}"
    return {
        "platform": "youtube",
        "title": title[:100],
        "caption": caption,
        "hashtags": hashtags,
        "tags": tags,
        "description": description,
    }


def generate_tiktok_copy(
    champion: str,
    action_type: str,
    yt_history: Optional[List[Dict]] = None,
    learning_state: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    TikTok copy — short hook + 3-5 hashtags in one caption field.
    Gemini prompt is tuned to TikTok algorithm patterns (hook speed, informal).
    Falls back to template if Gemini unavailable.
    """
    tags = _tiktok_hashtags(champion, action_type)
    action_label = {
        "pentakill": "PENTAKILL",
        "quadrakill": "QUADRAKILL",
        "triple": "TRIPLE KILL",
        "solo_bolo": "1v1 😤",
        "outplay": "OUTPLAY",
        "clutch": "CLUTCH 😱",
    }.get(action_type.lower(), action_type.upper())

    # Try Gemini for a punchy hook
    gemini_hook = ""
    if GENAI_OK and GEMINI_API_KEY:
        prompt = (
            f"Write a TikTok short caption (1 line, max 90 chars) for a League of Legends clip.\n"
            f"Champion: {champion}. Action: {action_label}.\n"
            f"Rules: casual tone, 1 emoji max, no hashtags, no quotation marks, hook first 3 words.\n"
            f"Output ONLY the caption text, nothing else."
        )
        gemini_hook = _call_gemini(prompt)
        # Sanitise: strip quotes, limit length
        gemini_hook = re.sub(r'^["\']|["\']$', '', gemini_hook).strip()[:90]

    if not gemini_hook:
        # Deterministic fallback templates per action
        templates = {
            "pentakill": f"How does {champion} do a pentakill so fast 😱",
            "triple": f"{champion} triple kill in 3 seconds flat 🔥",
            "solo_bolo": f"{champion} just 1v1'd the whole enemy team 😤",
            "outplay": f"Nobody outplays {champion} and gets away with it",
            "clutch": f"{champion} clutch when it matters most 💀",
        }
        gemini_hook = templates.get(action_type.lower(), f"{champion} {action_label} you won't believe this")

    tag_str = " ".join(f"#{t.lower()}" for t in tags)
    funnel_cta = "👉 Obserwuj nasz FB po więcej: facebook.com/Dwannellenga"
    caption = f"{gemini_hook}\n\n{funnel_cta}\n\n{tag_str}"

    return {
        "platform": "tiktok",
        "title": gemini_hook,          # TikTok API uses caption as title
        "caption": caption,
        "hashtags": tags,
    }


def generate_instagram_copy(
    champion: str,
    action_type: str,
    yt_history: Optional[List[Dict]] = None,
    learning_state: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Instagram Reels copy — storytelling hook in first 2 lines (visible before More),
    then hashtag block below.
    """
    tags = _instagram_hashtags(champion, action_type)
    action_label = {
        "pentakill": "PENTAKILL",
        "quadrakill": "QUADRAKILL",
        "triple": "TRIPLE KILL",
        "solo_bolo": "1v1 carried",
        "outplay": "OUTPLAY",
        "clutch": "clutch play",
    }.get(action_type.lower(), action_type.upper())

    gemini_hook = ""
    if GENAI_OK and GEMINI_API_KEY:
        prompt = (
            f"Write an Instagram Reels caption for a League of Legends highlight.\n"
            f"Champion: {champion}. Action: {action_label}.\n"
            f"Rules: first line is a hook (max 80 chars), second line asks a question to drive comments.\n"
            f"No hashtags in the text. No quotation marks. 2 lines only.\n"
            f"Output ONLY the 2-line caption, nothing else."
        )
        gemini_hook = _call_gemini(prompt).strip()

    if not gemini_hook:
        gemini_hook = (
            f"{champion} just pulled off a {action_label} 🔥\n"
            f"What's your favourite champion to carry with? 👇"
        )

    tag_str = " ".join(f"#{t.lower()}" for t in tags)
    funnel_cta = (
        "🔗 Więcej akcji i powtórek na naszej stronie FB: facebook.com/Dwannellenga\n"
        "🎬 TikTok: @dwannellenga | YouTube: Dwannellenga"
    )
    caption = f"{gemini_hook}\n\n{funnel_cta}\n\n.\n.\n.\n{tag_str}"

    return {
        "platform": "instagram",
        "title": gemini_hook.split("\n")[0][:80],
        "caption": caption,
        "hashtags": tags,
    }


def generate_facebook_copy(
    champion: str,
    action_type: str,
    yt_history: Optional[List[Dict]] = None,
    learning_state: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Facebook Page post copy — sentence-style, minimal hashtags.
    Facebook's algorithm penalises hashtag spam and link-bait language.
    """
    tags = _facebook_hashtags(champion, action_type)
    action_label = {
        "pentakill": "pentakill",
        "quadrakill": "quadrakill",
        "triple": "triple kill",
        "solo_bolo": "solo carry",
        "outplay": "outplay",
        "clutch": "clutch win",
    }.get(action_type.lower(), action_type.lower())

    gemini_text = ""
    if GENAI_OK and GEMINI_API_KEY:
        prompt = (
            f"Write a Facebook post for a League of Legends gaming page.\n"
            f"Champion: {champion}. Action: {action_label}.\n"
            f"Rules: conversational tone, 2-3 sentences max, ask a question at the end.\n"
            f"No hashtag spam (max 1-2 hashtags at the very end). No quotation marks.\n"
            f"Output ONLY the post text, nothing else."
        )
        gemini_text = _call_gemini(prompt).strip()

    clean_champ = re.sub(r'[^a-zA-Z]', '', champion)
    if not gemini_text:
        gemini_text = (
            f"Zobacz jak {champion} dominuje w tej akcji ({action_label})! 🔥\n"
            f"Napisz w komentarzu kim teraz grasz w obecnej mecie! 👇\n"
            f"Więcej skrótów i codziennych akcji znajdziesz też na naszym kanale YT i TikToku @dwannellenga\n\n"
            f"#leagueoflegends #{clean_champ.lower()} #gaming"
        )

    return {
        "platform": "facebook",
        "title": gemini_text.split("\n")[0][:100],
        "caption": gemini_text,
        "hashtags": tags,
    }


# ─── Main entry point ─────────────────────────────────────────────────────────

def generate_all_platform_copy(
    champion: str,
    action_type: str,
    base_metadata: Optional[Dict] = None,
    yt_history: Optional[List[Dict]] = None,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Generates per-platform copy for all requested platforms.

    Args:
        champion:       Champion name, e.g. "Katarina"
        action_type:    Action label, e.g. "pentakill", "outplay"
        base_metadata:  Already-generated YouTube metadata dict (from smart_titles)
                        Used to avoid duplicate Gemini call for YT.
        yt_history:     List of recent YT performance dicts (title, views, likes).
                        Used to bias copy toward proven formats.
        platforms:      List of platform keys to generate for.
                        Defaults to ["youtube", "tiktok", "instagram"].

    Returns:
        {
            "youtube":   {...},
            "tiktok":    {...},
            "instagram": {...},
            "facebook":  {...},   # only if requested
        }
    """
    if platforms is None:
        platforms = ["youtube", "tiktok", "instagram"]

    result: Dict[str, Dict[str, Any]] = {}

    if "youtube" in platforms:
        result["youtube"] = generate_youtube_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
            base_metadata=base_metadata,
        )

    if "tiktok" in platforms:
        result["tiktok"] = generate_tiktok_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
        )

    if "instagram" in platforms:
        result["instagram"] = generate_instagram_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
        )

    if "facebook" in platforms:
        result["facebook"] = generate_facebook_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
        )

    return result
