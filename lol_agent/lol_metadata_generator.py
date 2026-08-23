"""
LOL Agent - YouTube Metadata Generator (English-only)
Title, description and tags optimised for the YT Gaming algorithm.
Channel: Dwannellenga (English-language LoL Shorts)
"""
import os
import json
import time
import random
try:
    from lol_agent.lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, YT_BASE_TAGS, ACTION_LABELS
except ImportError:
    from lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, YT_BASE_TAGS, ACTION_LABELS


def _build_hashtags(champion: str = "", action_type: str = "") -> str:
    """Buduje zestaw hashtagów dla opisu — widoczne w YT jako clickable."""
    clean = champion.replace(' ', '').replace("'", '') if champion else ''
    champion_tag = f"#{clean}" if clean else ""
    action_map = {
        "pentakill": "#Pentakill #Penta",
        "quadrakill": "#Quadrakill #Quadra",
        "triple": "#TripleKill",
        "double": "#DoubleKill",
        "outplay": "#Outplay",
        "oneshot": "#OneShot",
        "clutch": "#Clutch",
        "baron": "#BaronSteal",
        "dragon": "#DragonSteal",
    }
    action_tag = action_map.get(action_type, "#Outplay")
    tags = [
        "#Shorts", "#LeagueOfLegends", "#LoL",
        champion_tag, action_tag,
        "#Gaming", "#LoLHighlights", "#lolgaming",
        "#epicmoments", "#lolclips",
    ]
    return " ".join(t for t in tags if t)


def _ensure_shorts_tag(description: str, champion: str = "", action_type: str = "") -> str:
    """Garantuje #Shorts i pełen zestaw hashtagów w opisie."""
    # Usuń stare hashtagi jeśli są na końcu, żeby nie duplikować
    lines = description.rstrip().split("\n")
    # Zbierz linie bez hashtagowych linii na samym końcu
    content_lines = lines
    while content_lines and content_lines[-1].strip().startswith("#"):
        content_lines = content_lines[:-1]
    clean_desc = "\n".join(content_lines).rstrip()
    hashtags = _build_hashtags(champion, action_type)
    return f"{clean_desc}\n\n{hashtags}"


GEMINI_RETRIES = 3
GEMINI_RETRY_DELAYS = [0, 15, 45]  # seconds between attempts


POPULAR_CHAMPIONS = [
    "Jinx", "Yasuo", "Zed", "Ahri", "Lee Sin", "Thresh", "Vayne",
    "Master Yi", "Katarina", "Lux", "Yone", "Viego", "Akali",
    "Ezreal", "Caitlyn", "Sylas", "Fizz", "Rengar", "Kha'Zix", "Irelia"
]

RANKS = ["Iron", "Bronze", "Silver", "Gold", "Platinum", "Emerald", "Diamond", "Master", "Challenger"]


def generate_metadata(
    action_type: str,
    champion_name: str = "",
    rank: str = "",
    language: str = "en"
) -> dict:
    """
    Generates title, description and tags for a LoL Short via Gemini AI.
    Falls back to English templates if the API is unavailable.
    """
    action_label = (
        ACTION_LABELS.get(action_type, "OUTPLAY")
        .replace("🔥", "").replace("⚡", "")
        .replace("💥", "").replace("🎯", "").replace("👑", "").strip()
    )

    if not champion_name:
        champion_name = random.choice(POPULAR_CHAMPIONS)
    if not rank:
        rank = random.choice(["Gold", "Platinum", "Diamond"])

    prompt = f"""You are a YouTube Shorts expert for League of Legends gaming content.
Generate metadata for a short gaming clip in ENGLISH ONLY.

CONTEXT:
- Action type: {action_label}
- Champion: {champion_name}
- Rank: {rank}
- Format: YouTube Short (9:16, under 60 seconds)
- Channel: Dwannellenga (English LoL Shorts channel)

GENERATE (JSON format):
{{
  "title": "Catchy English title, max 70 chars, 1-2 emoji, SEO friendly, NO Polish words",
  "description": "English description 100-150 words. Describe the play, encourage subscribe. MUST end with hashtags including #Shorts.",
  "tags": ["list", "of", "15-20", "tags", "in", "english"],
  "hook_text": "Short hook 3-5 words for video overlay (e.g. IMPOSSIBLE OUTPLAY) -- CAPS, English only"
}}

RULES:
- Title MUST be in English -- clickbait but honest
- Include: {champion_name}, {action_label}, rank {rank}
- Description MUST contain #Shorts (REQUIRED for YouTube classification)
- Hashtags at end: #LeagueOfLegends #LoL #Shorts #gaming
- NO Polish words anywhere
- Hook: max 4 words, ALL CAPS, English"""

    client = genai.Client(api_key=GEMINI_API_KEY)
    models_to_try = GEMINI_FALLBACK_MODELS if "GEMINI_FALLBACK_MODELS" in globals() else [GEMINI_MODEL]

    for model_name in models_to_try:
        for attempt in range(GEMINI_RETRIES):
            delay = GEMINI_RETRY_DELAYS[attempt]
            if delay > 0:
                print(f"   Gemini retry {attempt + 1}/{GEMINI_RETRIES} for {model_name} (waiting {delay}s)...")
                time.sleep(delay)
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                text = response.text.strip()

                # Extract JSON from response
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()

                data = json.loads(text)

                # Merge with base tags, strip # prefix from all tags
                raw_tags = [t.lstrip("#").strip() for t in data.get("tags", []) if t.strip()]
                all_tags = raw_tags + YT_BASE_TAGS
                all_tags = list(dict.fromkeys(all_tags))[:30]

                result = {
                    "title":       data.get("title",       generate_fallback_title(action_label, champion_name, rank)),
                    "description": _ensure_shorts_tag(data.get("description", generate_fallback_description(action_label, champion_name)), champion_name, action_type),
                    "tags":        all_tags,
                    "hook_text":   data.get("hook_text",   action_label.upper()),
                    "champion":    champion_name,
                    "rank":        rank,
                    "action_type": action_type,
                }

                print(f"OK Metadata generated by Gemini AI ({model_name})")
                print(f"   Title: {result['title']}")
                print(f"   Tags:  {len(result['tags'])}")
                return result

            except Exception as e:
                print(f"   Gemini ({model_name}) attempt {attempt + 1} failed: {e}")
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e) or "404" in str(e):
                    # Immediately switch model on quota/not found instead of waiting retries
                    break

    print("Warning: All Gemini models failed — using static fallback")
    return generate_fallback_metadata(action_label, champion_name, rank, action_type)



def generate_fallback_title(action_label: str, champion: str, rank: str) -> str:
    templates = [
        f"{champion} {action_label}! They Never Stood a Chance! 😈",
        f"This {champion} {action_label} is INSANE! 🔥 #{rank}",
        f"{action_label} in {rank}... Nobody Escaped! 💀",
        f"You Can't Stop This {champion} {action_label} 😏",
        f"{champion} {action_label} – Too Fast, Too Clean! ⚡",
    ]
    return random.choice(templates)


def generate_fallback_description(action_label: str, champion: str) -> str:
    return (
        f"Insane {action_label} on {champion}! 🎮\n\n"
        f"One of the cleanest plays you'll ever see in League of Legends. "
        f"Subscribe to Dwannellenga for more epic LoL highlights!\n\n"
        f"👍 Drop a like if you enjoyed this clip!\n"
        f"🔔 Subscribe so you never miss another moment like this!\n"
        f"💬 Comment your best play below!\n\n"
        f"#LeagueOfLegends #LoL #{champion.replace(' ', '')} "
        f"#{action_label.replace(' ', '')} #Shorts #Gaming #LoLHighlights #BestPlays"
    )


def generate_fallback_metadata(
    action_label: str, champion: str, rank: str, action_type: str
) -> dict:
    all_tags = [
        champion, champion.lower(), f"lol {champion.lower()}",
        action_label.lower(), action_type, rank.lower(),
        f"{rank.lower()} gameplay",
    ] + YT_BASE_TAGS
    # Strip # from any tags that might have slipped in
    all_tags = [t.lstrip("#").strip() for t in all_tags if t.strip()]
    all_tags = list(dict.fromkeys(all_tags))[:30]

    return {
        "title":       generate_fallback_title(action_label, champion, rank),
        "description": _ensure_shorts_tag(generate_fallback_description(action_label, champion), champion, action_type),
        "tags":        all_tags,
        "hook_text":   action_label.upper(),
        "champion":    champion,
        "rank":        rank,
        "action_type": action_type,
    }


if __name__ == "__main__":
    result = generate_metadata(
        action_type="pentakill",
        champion_name="Katarina",
        rank="Diamond"
    )
    print(f"\nRESULT:")
    print(f"Title: {result['title']}")
    print(f"Hook:  {result['hook_text']}")
    print(f"Tags:  {', '.join(result['tags'][:10])}...")
