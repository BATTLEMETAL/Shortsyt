"""
LOL Agent — Channel Title Database & Proven Top Patterns
Zawiera autentyczne, najlepiej konwertujące tytuły z kanału Dwannellenga.
"""
from typing import List, Dict

CHANNEL_TOP_TITLES: List[Dict] = [
    {
        "videoId": "Wy6mvAprWS0",
        "title": "Katarina’s Dragon Pit Rampage – Triple Kill! 💥",
        "views": 24428,
        "action_type": "triple",
        "style": "location_action"
    },
    {
        "videoId": "6EwdZgvFdcQ",
        "title": "Enemy Tried to Dive Me 💀 It Went Wrong 😏",
        "views": 13022,
        "action_type": "outplay",
        "style": "enemy_mistake"
    },
    {
        "videoId": "IMSSS_6quI8",
        "title": "Rambo Katarina 💥 Solo Baron Save! 🐉",
        "views": 11905,
        "action_type": "clutch",
        "style": "persona_moment"
    },
    {
        "videoId": "zJYaFuQdie8",
        "title": "Trash Talk Turned Into Silence 😈 Katarina Triple Kill 💥",
        "views": 8517,
        "action_type": "triple",
        "style": "story_retribution"
    },
    {
        "videoId": "BlJ3HHmX-C0",
        "title": "From Nowhere to Double Kill – and Gone! 💨",
        "views": 7143,
        "action_type": "double",
        "style": "speed_stealth"
    },
    {
        "videoId": "pNwW8kfSfTc",
        "title": "No Escape 💀 Katarina the Jumping Queen 👑",
        "views": 5640,
        "action_type": "quadrakill",
        "style": "persona_statement"
    },
    {
        "videoId": "HTaDSMenx6E",
        "title": "Tower Dive Contest – Katarina Edition 🔥",
        "views": 5616,
        "action_type": "outplay",
        "style": "event_edition"
    },
    {
        "videoId": "9wWHeNd1zRw",
        "title": "Herald Came to Save the Day! 🐲🔥",
        "views": 5184,
        "action_type": "clutch",
        "style": "third_party_save"
    },
    {
        "videoId": "sx3x38o_RUk",
        "title": "Perfect Reset Machine 🔥 Katarina Full Domination 😈",
        "views": 5049,
        "action_type": "pentakill",
        "style": "machine_execution"
    },
    {
        "videoId": "3hgiyFnnsVI",
        "title": "Baron Pit Carnage – Triple Kill & Assist! 🐉💥",
        "views": 2847,
        "action_type": "triple",
        "style": "location_action"
    },
    {
        "videoId": "FM0oZ1RKx14",
        "title": "🔥 Quadra Kill Chase – Nobody Escapes! 💀💨",
        "views": 2505,
        "action_type": "quadrakill",
        "style": "chase_punishment"
    },
    {
        "videoId": "3a0EnhCSJus",
        "title": "Katarina Pentakill – They Never Stood A Chance! 💥",
        "views": 1293,
        "action_type": "pentakill",
        "style": "action_enemy_view"
    },
    {
        "videoId": "Pgn0M8RXRIA",
        "title": "Five Kills. One Katarina. 🔥",
        "views": 1046,
        "action_type": "pentakill",
        "style": "punchy_count"
    }
]

PROVEN_STYLE_TEMPLATES = {
    "pentakill": [
        "Five Kills. One {Champion}. 🔥",
        "{Champion} Pentakill – They Never Stood A Chance! 💥",
        "They Grouped Up For Free... Big Mistake 💀🔥",
        "One Reset. Five Graves. {Champion} Pentakill ⚡",
        "Entire Team Disappeared in 3 Seconds 💀💥"
    ],
    "quadrakill": [
        "🔥 Quadra Kill Chase – Nobody Escapes! 💀💨",
        "Solo Carry Quadra Kill – 1v4 Defense! 💀🔥",
        "They Thought 4v1 Was Safe... It Wasn't 😏💥",
        "Hunting Down The Whole Squad 💀 {Champion} Quadra"
    ],
    "triple": [
        "{Champion}’s Dragon Pit Rampage – Triple Kill! 💥",
        "Trash Talk Turned Into Silence 😈 {Champion} Triple Kill 💥",
        "Baron Pit Carnage – Triple Kill & Assist! 🐉💥",
        "ADC Down… Mid Saved? Not Today! 💥 Triple Kill"
    ],
    "outplay": [
        "Enemy Tried to Dive Me 💀 It Went Wrong 😏",
        "Tower Dive Contest – {Champion} Edition 🔥",
        "Ambush at Drake 🐉 Gone Wrong (for Them 😏)",
        "They Flashed For The Kill... And Regretted It 💀"
    ],
    "clutch": [
        "Rambo {Champion} 💥 Solo Baron Save! 🐉",
        "Herald Came to Save the Day! 🐲🔥",
        "1% HP Dream – Stealing Drake and Winning 💀🔥"
    ]
}

def get_few_shot_examples(action_type: str = "pentakill", limit: int = 5) -> str:
    """Zwraca sformatowane realne przykłady top filmów pod konkretną akcję."""
    act = action_type.lower()
    matched = [v for v in CHANNEL_TOP_TITLES if v["action_type"] == act]
    if len(matched) < limit:
        for v in CHANNEL_TOP_TITLES:
            if v not in matched:
                matched.append(v)
            if len(matched) >= limit:
                break
    
    lines = []
    for item in matched[:limit]:
        clean_title = item["title"].split("#")[0].strip()
        lines.append(f'- "{clean_title}" ({item["views"]:,} views, {item["action_type"].upper()})')
    return "\n".join(lines)
