"""
LOL Agent - YouTube Metadata Generator (Dwannellenga Channel Proven Templates)
High-converting Titles, Descriptions, Pinned Comments & Tags optimised for YouTube Shorts Algorithm.
"""
import os
import json
import time
import random
from typing import Optional, Dict, Any, List

try:
    from lol_agent.lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, YT_BASE_TAGS, ACTION_LABELS
except ImportError:
    try:
        from lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, YT_BASE_TAGS, ACTION_LABELS
    except ImportError:
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        GEMINI_MODEL = "gemini-2.5-flash"
        GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-flash-latest"]
        YT_BASE_TAGS = ["shorts", "leagueoflegends", "lol", "gaming", "highlights", "outplay"]
        ACTION_LABELS = {
            "pentakill": "PENTAKILL",
            "quadrakill": "QUADRAKILL",
            "triple": "TRIPLE KILL",
            "double": "DOUBLE KILL",
            "outplay": "OUTPLAY",
            "clutch": "CLUTCH",
        }


def _build_hashtags(champion: str = "Katarina", action_type: str = "outplay") -> str:
    """Buduje zestaw viralowych hashtagów pod algorytm YouTube Shorts."""
    clean = champion.replace(' ', '').replace("'", '') if champion else 'Katarina'
    champion_tag = f"#{clean}"
    
    action_map = {
        "pentakill": "#Pentakill #Penta",
        "quadrakill": "#Quadrakill #QuadraKill",
        "triple": "#TripleKill",
        "double": "#DoubleKill",
        "outplay": "#Outplay #LoLOutplay",
        "clutch": "#Clutch #1PercentHP",
        "oneshot": "#OneShot",
    }
    action_tag = action_map.get(action_type.lower(), "#Outplay")
    tags = [
        "#Shorts", "#LeagueOfLegends", "#LoL",
        champion_tag, action_tag,
        "#Gaming", "#LoLHighlights", "#lolgaming",
        "#epicmoments", "#lolclips"
    ]
    return " ".join(tags)


def generate_channel_title(action_type: str = "outplay", champion: str = "Katarina", rank: str = "") -> str:
    """
    Zwraca sprawdzony, wiralowy tytuł YouTube Shorts dopasowany do standardu kanału Dwannellenga
    oraz aktywnego tonu AI (Hype & High Energy / Storytelling & Clutch / Meme & Casual Gaming).
    """
    champ = champion or "Katarina"
    act = action_type.lower()
    
    try:
        from lol_agent.tuning_manager import get_pacing_parameters
    except ImportError:
        try:
            from tuning_manager import get_pacing_parameters
        except ImportError:
            get_pacing_parameters = lambda: {"title_tone": "hype"}

    tone = get_pacing_parameters().get("title_tone", "hype")

    if "penta" in act:
        templates = [
            f"One {champ}. Five Kills. PENTAKILL RAMPAGE! 💥 #Shorts #LeagueOfLegends #LoL",
            f"{champ}'s Unstoppable Pentakill! 💥 No Escape 💀 #Shorts #LeagueOfLegends #LoL",
            f"Five Enemies. One {champ}. Instant Regret. 😈 #Shorts #LeagueOfLegends #LoL",
            f"Entire Team Disappeared In Seconds 💀💥 {champ} Penta #Shorts #LeagueOfLegends #LoL",
            f"{champ} Pentakill – They Never Stood A Chance! 💥 #Shorts #LeagueOfLegends #LoL",
            f"This {champ} PENTAKILL is INSANE! 🔥 #Shorts #LeagueOfLegends #LoL",
            f"Five Kills. One {champ}. PENTA! 💥 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "quadra" in act:
        templates = [
            f"They Thought They Had Me 😈 {champ} Quadra Kill 💥 #Shorts #LeagueOfLegends #LoL",
            f"{champ}'s Four-Kill Frenzy! ⚡ Quadra Domination #Shorts #LeagueOfLegends #LoL",
            f"Four Enemies Down in Seconds! Insane {champ} Quadra 🔥 #Shorts #LeagueOfLegends #LoL",
            f"They cornered {champ}... Bad idea. Quadra Kill! 💥 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "triple" in act:
        templates = [
            f"Triple Kill! They Never Saw {champ} Coming 😈 #Shorts #LeagueOfLegends #LoL",
            f"They cornered her. Bad idea. Triple Kill! 💥 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Chaos – {champ} Triple Kill 💥 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Teamfight Masterclass – Triple Kill! 🔥 #Shorts #LeagueOfLegends #LoL",
            f"Their Dive on {champ}? Not Today! 💥 Triple Kill #Shorts #LeagueOfLegends #LoL",
            f"Underestimated {champ}? 😈 Triple Kill Outplay 🩸 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Nightmare 💀 Triple Kill Clutch! #Shorts #LeagueOfLegends #LoL",
            f"Late Game Triple Kill – Nowhere to Run 💨 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "clutch" in act or "1hp" in act or "1%" in act:
        templates = [
            f"Surviving on 1% HP to Win The Fight! 💀🔥 {champ} Clutch #Shorts #LeagueOfLegends #LoL",
            f"They Thought He Was 100% Dead... 1% HP {champ} Miracle Outplay 🩸 #Shorts #LeagueOfLegends #LoL",
            f"1 HP and a Dream! 💀 {champ} Turnaround Clutch 🔥 #Shorts #LeagueOfLegends #LoL",
            f"The Most Stressful 1% HP Clutch You'll See Today 😱 {champ} #Shorts #LeagueOfLegends #LoL",
            f"How Did {champ} Survive That?! 💀 1% HP Impossible Outplay #Shorts #LeagueOfLegends #LoL",
            f"Calculated or Pure Luck? 🧠 1% HP {champ} Clutch Survival #Shorts #LeagueOfLegends #LoL",
        ]
    elif "double" in act:
        templates = [
            f"Clean Double Kill Turnaround! 💥 {champ} Outplay #Shorts #LeagueOfLegends #LoL",
            f"They Tried a 2v1 Dive on {champ}... Instant Double Kill 💀 #Shorts #LeagueOfLegends #LoL",
            f"Two Enemies Down In A Blink ⚡ {champ} Double Kill #Shorts #LeagueOfLegends #LoL",
            f"Never Dive A Fed {champ}! 💀 Fast Double Kill #Shorts #LeagueOfLegends #LoL",
        ]
    else:  # outplay / solo kill
        templates = [
            f"They Flashed In for the Kill... Bad Idea 😏 #Shorts #LeagueOfLegends #LoL",
            f"They Tried to Catch {champ} 💀 It Went Wrong 😏 #Shorts #LeagueOfLegends #LoL",
            f"All-In On {champ}? Instant Regret 💀 #Shorts #LeagueOfLegends #LoL",
            f"Underestimated {champ}? 😈 They Paid The Price 🩸 #Shorts #LeagueOfLegends #LoL",
            f"Thought They Had Me 💀 Guess Again 😏 #Shorts #LeagueOfLegends #LoL",
            f"Enemy Tried an Outplay... They Got Outplayed. 💀 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Instant Burst 💀 They Vanished 💨 #Shorts #LeagueOfLegends #LoL",
            f"They Made Their Move... {champ} Burst Back! 💥 #Shorts #LeagueOfLegends #LoL",
        ]
    return random.choice(templates)


def build_channel_description(title: str, champion: str = "Katarina", action_type: str = "outplay") -> str:
    """
    Buduje profesjonalny, angażujący opis YouTube z brandingiem kanału Dwannellenga,
    mocnym wezwaniem do subskrypcji i kompletem hashtagów.
    """
    champ = champion or "Katarina"
    act_clean = action_type.replace("_", " ").title()
    hashtags = _build_hashtags(champ, action_type)
    
    return (
        f"Insane {champ} {act_clean} in League of Legends! 🎮🔥\n"
        f"They thought they had the fight won, but {champ} turned everything around in seconds.\n\n"
        f"🎮 League of Legends highlights & high-elo plays — Dwannellenga\n"
        f"⚡ New viral shorts and clutch moments every day!\n\n"
        f"👍 Drop a LIKE if you enjoyed the outplay!\n"
        f"🔔 SUBSCRIBE to Dwannellenga so you never miss a clip!\n"
        f"💬 Rate this play 1-10 in the comments below! 👇\n\n"
        f"{hashtags}"
    )


def build_pinned_comment(champion: str = "Katarina", action_type: str = "outplay") -> str:
    """
    Generuje angażujący przypięty komentarz (Pinned Comment) z pytaniem zachęcającym do dyskusji.
    """
    champ = champion or "Katarina"
    comments = [
        f"What would you have done in this situation? 👇 Rate this {champ} play 1-10! 🔥",
        f"Did the enemy team misplay or was this {champ} outplay 100% calculated? Let me know! 🧠👇",
        f"Cleanest {champ} play today? Drop your thoughts in the comments! 👇🔥",
        f"Who is your main champion in League of Legends? Let's discuss below! ⚔️👇",
    ]
    return random.choice(comments)


def generate_metadata(
    action_type: str,
    champion_name: str = "Katarina",
    rank: str = "Master",
    language: str = "en"
) -> dict:
    """
    Główny generator metadanych — łączy szablony kanału z generowaniem tagów i przypiętego komentarza.
    """
    champ = champion_name or "Katarina"
    title = generate_channel_title(action_type, champ, rank)
    description = build_channel_description(title, champ, action_type)
    pinned_comment = build_pinned_comment(champ, action_type)
    
    all_tags = [
        champ, champ.lower(), f"lol {champ.lower()}",
        f"{champ.lower()} outplay", f"{champ.lower()} montage",
        action_type.lower(), f"{action_type.lower()} lol",
        "league of legends", "lol", "lol shorts", "shorts", "gaming",
        "lol gameplay", "lol highlights", "best lol plays"
    ] + YT_BASE_TAGS
    all_tags = list(dict.fromkeys(all_tags))[:30]

    return {
        "title": title,
        "description": description,
        "pinned_comment": pinned_comment,
        "tags": all_tags,
        "hook_text": f"{action_type.upper()}! 💥",
        "champion": champ,
        "rank": rank,
        "action_type": action_type,
    }


def generate_fallback_title(action_label: str, champion: str, rank: str) -> str:
    return generate_channel_title(action_label, champion, rank)


def generate_fallback_description(action_label: str, champion: str) -> str:
    return build_channel_description("", champion, action_label)


def generate_fallback_metadata(
    action_label: str, champion: str, rank: str, action_type: str
) -> dict:
    return generate_metadata(action_type, champion, rank)


if __name__ == "__main__":
    res = generate_metadata("triple", "Katarina", "Master")
    print("TITLE:", res["title"])
    print("\nDESCRIPTION:\n", res["description"])
    print("\nPINNED COMMENT:", res["pinned_comment"])
