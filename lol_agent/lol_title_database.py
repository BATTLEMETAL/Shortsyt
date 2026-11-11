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
        "title": "No Escape 💀 Hunting Down the Entire Team 🔥",
        "views": 13022,
        "action_type": "outplay",
        "style": "aggressive_hunt"
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
        "They Grouped Up For Free... Wipe Out 💀🔥",
        "One Reset. Five Graves. {Champion} Pentakill ⚡",
        "Entire Team Disappeared in 3 Seconds 💀💥",
        "Full Squad Wiped Out Clean 💀 {Champion} Pentakill 🔥",
        "They Tried to Contest the Base... Instant ACE ⚡",
        "Disrespectful Base Defense 👑 Full Pentakill 😈",
        "The Health Bars Just Vanished 💀 {Champion} Pentakill ⚡",
        "Vanished Before They Could Even Flash 💨 {Champion} Ace",
        "From Full HP to Ace in Under 4 Seconds 💀🔥",
        "They Thought The Fight Was Won... Full Wipe 😈",
        "Unforgiving Teamfight Execution 💀 {Champion} Penta",
        "Every Reset Timed to the Millisecond ⚡ {Champion} 💥"
    ],
    "quadrakill": [
        "🔥 Quadra Kill Chase – Nobody Escapes! 💀💨",
        "Solo Carry Quadra Kill – 1v4 Defense! 💀🔥",
        "They Thought 4v1 Was Safe... It Wasn't 😏💥",
        "Hunting Down The Whole Squad 💀 {Champion} Quadra",
        "Four Enemies Deleted in Seconds ⚡ {Champion} Quadra 🔥",
        "They Tried to Ambush Her... Counter Wipe 💀",
        "Disrespect Punished Hard 😈 {Champion} Quadra Kill 💥",
        "All Four Down Before The Cooldowns Returned ⚡",
        "Walking Into {Champion} Like That Was Fatal 💀",
        "Zero Hesitation 1v4 Execution 🔥 {Champion}",
        "The Moment The Enemy Realized It Was Over 💀 Quadra"
    ],
    "triple": [
        "ADC Down… Mid Saved? Not Today! 💥 Triple Kill",
        "Three Enemies Gone in 2 Seconds ⚡ {Champion} Triple 🔥",
        "Clean Reset Sequence 🔥 {Champion} Triple Kill 🩸",
        "Three Down in One Single Breath ⚡ {Champion}",
        "They Clustered Together... Total Destruction 💥 {Champion} Triple",
        "Disrespect Turned Into Silence 😈 {Champion} Triple",
        "They Walked Right Into The Daggers 💀 {Champion}",
        "Back-to-Back Resets Under Tower 🩸 {Champion} Triple",
        "They Thought They Had The 3v1 Lock 💀 Clean Turnaround",
        "One By One They Dropped ⚡ {Champion} Triple Kill 🔥",
        "Frame-Perfect Reset Cascade 💀 {Champion} Triple"
    ],
    "double": [
        "From Nowhere to Double Kill – and Gone! 💨",
        "They Came 2v1... Left in Graves 💀 {Champion} Double 🔥",
        "They Ganked The Wrong Lane 😈 Clean Double Kill ⚡",
        "Two Down in a Blink 💥 {Champion} 2v1 Turnaround 💀",
        "Two Resets in 1 Second ⚡ Clean Double Kill 🔥",
        "They Tried to Pinch {Champion}... Instant 2v1 Reversal 💀",
        "Enemy Duo Deleted Before They Could Move ⚡",
        "Walking Into Her Zone Was Their Final Play 💀 Double Kill",
        "Never Double Commit on {Champion} 😈 Clean Double Kill",
        "Both Health Bars Melted Simultaneously 💥 {Champion}"
    ],
    "solo_bolo": [
        "Clean SOLO BOLO 👑 1v1 Masterclass 💀",
        "They Ego Challenged {Champion}... Sent to Base 😈",
        "Nobody Survives {Champion} in a 1v1 👑 Clean SOLO BOLO",
        "Pixel-Perfect 1v1 Outplay 💀 {Champion} SOLO BOLO 🔥",
        "Duel Accepted. Duel Won. 💀 Clean SOLO BOLO ⚡",
        "Walking Up Like That Is Crazy 💀 {Champion} 1v1",
        "They Tested {Champion} and Found Out 💀 SOLO BOLO",
        "Overconfidence Punished in 0.5 Seconds 👑 SOLO BOLO",
        "Dodge Everything, Hit Everything 👑 {Champion} 1v1",
        "They Really Thought They Could 1v1 This 💀 SOLO BOLO",
        "Calculated to the Exact Millisecond 🧠 Clean 1v1"
    ],
    "outplay": [
        "No Escape 💀 Hunting Down the Entire Team 🔥",
        "Frame-Perfect Reaction 🔥 Clean Outplay 💀",
        "Zero Hesitation. Pure Execution. 💀 {Champion} Outplay 🔥",
        "The Health Bars Just Disappeared 💀 {Champion}",
        "They Didn't Even Realize What Happened 💀 {Champion}",
        "The Level of Disrespect in This Play 😈 {Champion}",
        "They Thought They Had The Upper Hand 😏 Reversal ⚡",
        "One Ability Dodge Changed The Whole Fight 🧠 {Champion}",
        "Outplayed at Every Single Step 💀 {Champion} Mechanics",
        "They Flashed Into Their Own Doom 💀 {Champion} Outplay"
    ],
    "clutch": [
        "Rambo {Champion} 💥 Solo Objective Save! 🐉",
        "Surviving on 1 HP to Win 🩸 Impossible Outplay 💀",
        "They Celebrated Too Early 😏 1% HP Turnaround 🔥",
        "They Already Typed 'GG'... {Champion} Didn't. 🔥",
        "1 HP and a Dream 🩸 Miracle Turnaround 💀",
        "Dead or Alive? {Champion} Answers With a Kill 🩸",
        "The Cleanest 1% HP Clutch You'll See Today 💀"
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
