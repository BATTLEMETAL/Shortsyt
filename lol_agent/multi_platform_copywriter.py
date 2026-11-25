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


def _dedup_preserve(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        low = str(item).strip().lstrip("#").lower()
        if low and low not in seen:
            seen.add(low)
            out.append(low)
    return out


_YT_TAG_BLOCKLIST = {"shorts", "shortsfeed", "ytshorts", "youtubeshorts", "short"}
_TT_LEARNING_PATH = Path(__file__).resolve().parent.parent / "accounts" / "tiktok_learning_directive.json"


def _load_tiktok_recommended_tags() -> List[str]:
    try:
        if _TT_LEARNING_PATH.is_file():
            data = json.loads(_TT_LEARNING_PATH.read_text(encoding="utf-8"))
            tags = data.get("recommended_hashtags") or []
            return [t.strip().lstrip("#").lower() for t in tags if t and t.strip().lstrip("#").lower() not in _YT_TAG_BLOCKLIST]
    except Exception:
        pass
    return []


def _tiktok_hashtags(champion: str, action_type: str) -> List[str]:
    """TikTok: 5 najlepszych tagów wyuczonych z @dwannellenga (bez tagów YouTube typu #shorts)."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    clean_low = clean.lower()
    action_map = {
        "pentakill": ["pentakill", "lolpenta"],
        "quadrakill": ["quadrakill", "lolquadra"],
        "triple": ["triplekill", "loltriple"],
        "double": ["doublekill", "loldouble"],
        "solo_bolo": ["outplayed", "1v1"],
        "outplay": ["outplayed", "lolhighlights"],
        "clutch": ["outplayed", "lolhighlights"],
        "steal": ["dragonsteal", "smite"],
    }
    action_tags = action_map.get(action_type.lower(), ["outplayed", "lolhighlights"])
    learned = _load_tiktok_recommended_tags()
    if learned:
        combined: List[str] = []
        if action_type and action_type.lower() in action_map:
            combined.append(action_tags[0])
        if clean_low:
            combined.append(clean_low)
        combined.extend(learned[:2])
        combined.append("fyp")
        combined.extend(learned[2:])
        return _dedup_preserve([t for t in combined if t not in _YT_TAG_BLOCKLIST])[:5]

    raw = [
        action_tags[0],
        "pcgaming",
        "leagueoflegends",
        "lolhighlights",
        clean_low or "katarina",
    ]
    return _dedup_preserve([t for t in raw if t not in _YT_TAG_BLOCKLIST])[:5]


def _instagram_hashtags(champion: str, action_type: str) -> List[str]:
    """Instagram: 10–15 mieszanych tagów niszowych i viralowych (bez duplikatów)."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    clean_low = clean.lower()
    action_map = {
        "pentakill": ["pentakill", "penta", "lolpentakill"],
        "quadrakill": ["quadrakill", "lolquadra"],
        "triple": ["triplekill", "loltriple"],
        "double": ["doublekill", "loldouble"],
        "solo_bolo": ["outplay", "1v1", "solobolo"],
        "outplay": ["outplay", "loloutplay"],
        "clutch": ["clutch", "outplay"],
        "steal": ["baronsteal", "dragonsteal", "smite"],
    }
    action_tags = action_map.get(action_type.lower(), ["outplay"])
    raw = [
        "leagueoflegends", "lol", "gaming", clean_low, f"{clean_low}mains",
        *action_tags,
        "lolhighlights", "lolclips", "gamingclips", "reels", "gamingcommunity",
        f"{clean_low}gameplay", "esports",
    ]
    return _dedup_preserve(raw)[:6]


def _extract_clean_base_hook(base_metadata: Optional[Dict[str, Any]]) -> str:
    """Czyści zatwierdzony tytuł z tagów YouTube (#shorts, #ytshorts, #shortsfeed itp.) pod TikTok/IG."""
    if not isinstance(base_metadata, dict):
        return ""
    raw_title = str(base_metadata.get("title") or "").strip()
    if not raw_title:
        return ""
    cleaned = re.sub(r"#\S+", "", raw_title)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -—|")
    return cleaned


def _facebook_hashtags(champion: str, action_type: str) -> List[str]:
    """Facebook: 1–3 tags MAXIMUM — FB algorithm penalises hashtag spam."""
    clean = re.sub(r"['\s]", "", champion) if champion else "Katarina"
    return ["LeagueOfLegends", clean, "Gaming"]


# ─── Gemini helper ────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, max_retries: int = 2) -> str:
    """
    Priorytet #1: Lokalna Synapsa (0 tokenów API).
    Fallback: Gemini API jeśli skonfigurowano GEMINI_API_KEY i Synapsa niedostępna.
    """
    in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not in_pytest or os.environ.get("ALLOW_LIVE_SYNAPSA_IN_TEST") == "1":
        try:
            try:
                from lol_agent.synapsa_engine import generate_with_synapsa
            except ImportError:
                from synapsa_engine import generate_with_synapsa
            syn = generate_with_synapsa("social_caption", {"prompt": prompt}, timeout=60)
            if syn and isinstance(syn.get("caption"), str) and syn["caption"].strip():
                return syn["caption"].strip()
        except Exception:
            pass

    if not GENAI_OK or not GEMINI_API_KEY:
        return ""
    if in_pytest and os.environ.get("ALLOW_LIVE_GEMINI_IN_TEST") != "1":
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
    base_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    TikTok copy — używa czystego zatwierdzonego tytułu (bez #shorts/#ytshorts),
    a gdy go brak, pyta Synapsę / szablony przypisane do konkretnej akcji (koniec halucynacji).
    """
    tags = _tiktok_hashtags(champion, action_type)
    action_label = {
        "pentakill": "PENTAKILL",
        "quadrakill": "QUADRAKILL",
        "triple": "TRIPLE KILL",
        "double": "DOUBLE KILL",
        "solo_bolo": "1v1 😤",
        "outplay": "OUTPLAY",
        "clutch": "CLUTCH 😱",
        "steal": "OBJECTIVE STEAL 💀",
    }.get(action_type.lower(), action_type.upper())

    clean_base = _extract_clean_base_hook(base_metadata)
    if len(clean_base) >= 8:
        gemini_hook = clean_base[:90]
    else:
        prompt = (
            f"Write a TikTok short caption (1 line, max 90 chars) for a League of Legends clip.\n"
            f"Champion: {champion}. Action: {action_label}.\n"
            f"Rules: casual tone, 1 emoji max, no hashtags, no quotation marks, hook first 3 words.\n"
            f"Do NOT invent steals or pentakills if action is {action_label}.\n"
            f"Output ONLY the caption text, nothing else."
        )
        gemini_hook = _call_gemini(prompt)
        gemini_hook = re.sub(r'^["\']|["\']$', '', gemini_hook).strip()[:90]

    if not gemini_hook:
        templates = {
            "pentakill": f"How does {champion} wipe 5 players so fast 😱",
            "quadrakill": f"Wait until you see the last reset on {champion} 💀",
            "triple": f"3 down before they even reacted on {champion} ⚡",
            "double": f"Greedy chase into {champion} gets punished in 2s 🔥",
            "solo_bolo": f"{champion} 1v1 spacing check — would you fight this? 😤",
            "outplay": f"Nobody outplays {champion} and walks away alive ⚡",
            "clutch": f"{champion} surviving on 1 HP like nothing happened 💀",
            "steal": f"Enemy jungler missed smite vs {champion} 💀",
        }
        gemini_hook = templates.get(action_type.lower(), f"{champion} {action_label} — clean or pure luck? 💀")[:90]

    tag_str = " ".join(f"#{t.lower()}" for t in tags if t.lower() not in _YT_TAG_BLOCKLIST)
    caption = f"{gemini_hook}\n{tag_str}".strip()

    return {
        "platform": "tiktok",
        "title": gemini_hook[:90],
        "caption": caption,
        "hashtags": tags,
    }


def generate_instagram_copy(
    champion: str,
    action_type: str,
    yt_history: Optional[List[Dict]] = None,
    learning_state: Optional[Dict] = None,
    base_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Instagram Reels copy — używa czystego zatwierdzonego tytułu jako pierwszej linii,
    a następnie pytania pod komentarze oraz bloku hasztagów poniżej fałdu.
    """
    tags = _instagram_hashtags(champion, action_type)
    action_label = {
        "pentakill": "PENTAKILL",
        "quadrakill": "QUADRAKILL",
        "triple": "TRIPLE KILL",
        "double": "DOUBLE KILL",
        "solo_bolo": "1v1 carried",
        "outplay": "OUTPLAY",
        "clutch": "clutch play",
        "steal": "objective steal",
    }.get(action_type.lower(), action_type.upper())

    clean_base = _extract_clean_base_hook(base_metadata)
    if len(clean_base) >= 8:
        q_map = {
            "pentakill": f"Did the enemy team have any counterplay to that {champion} pentakill? 👇",
            "quadrakill": "Could enemy team actually stop that reset chain? 👇",
            "triple": "Did enemy squad clump up for free or was that unreactable? 👇",
            "double": "Greedy chase or clean bait? Drop your take below 👇",
            "solo_bolo": f"Would you take this 1v1 against {champion}? 👇",
            "clutch": "1 HP dream — who wins that fight in your games? 👇",
        }
        q_line = q_map.get(action_type.lower(), f"What's your favourite {champion} combo this patch? 👇")
        gemini_hook = f"{clean_base[:80]}\n{q_line}"
    else:
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
    caption = f"{gemini_hook}\n\n.\n.\n.\n{tag_str}".strip()

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
    base_metadata: Optional[Dict[str, Any]] = None,
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

    clean_champ = re.sub(r'[^a-zA-Z]', '', champion) or "lol"
    clean_base = _extract_clean_base_hook(base_metadata)
    if len(clean_base) >= 8:
        fb_questions = {
            "pentakill": "Who could actually stop that cleanup?",
            "quadrakill": "Was the last reset fair or pure chaos?",
            "triple": "Did enemy team walk into those daggers for free?",
            "double": "Greedy chase by the enemy or clean spacing?",
            "solo_bolo": f"Would you ever step up 1v1 against {champion} here?",
            "clutch": "1 HP survival — lucky tick or calculated limit test?",
        }
        q_line = fb_questions.get(action_type.lower(), f"Was that enemy throw or pure {champion} mechanics?")
        gemini_text = (
            f"{clean_base[:90]}\n"
            f"{q_line}\n\n"
            f"#leagueoflegends #{clean_champ.lower()} #reels"
        )
    else:
        prompt = (
            f"Write a Facebook post for a League of Legends gaming page.\n"
            f"Champion: {champion}. Action: {action_label}.\n"
            f"Rules: conversational tone, 2-3 sentences max, ask a question at the end.\n"
            f"No hashtag spam (max 1-2 hashtags at the very end). No quotation marks.\n"
            f"Output ONLY the post text, nothing else."
        )
        gemini_text = _call_gemini(prompt).strip()

    if not gemini_text:
        gemini_text = (
            f"Clean {champion} {action_label} before they could even react! 💀\n"
            f"Did the enemy overextend here or was this pure mechanical diff?\n\n"
            f"#leagueoflegends #{clean_champ.lower()} #reels"
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
            base_metadata=base_metadata,
        )

    if "instagram" in platforms:
        result["instagram"] = generate_instagram_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
            base_metadata=base_metadata,
        )

    if "facebook" in platforms:
        result["facebook"] = generate_facebook_copy(
            champion=champion,
            action_type=action_type,
            yt_history=yt_history,
            base_metadata=base_metadata,
        )

    return result
