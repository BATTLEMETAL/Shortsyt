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
            "solo_bolo": "SOLO BOLO 👑",
            "outplay": "OUTPLAY",
            "clutch": "CLUTCH",
        }


def _build_hashtags(champion: str = "Katarina", action_type: str = "outplay") -> str:
    """Buduje bogaty zestaw viralowych hashtagów pod algorytm YouTube Shorts."""
    clean = champion.replace(' ', '').replace("'", '') if champion else 'Katarina'
    champion_tag = f"#{clean}"
    
    action_map = {
        "pentakill": "#Pentakill #Penta #PentaKill #LoLPentakill",
        "quadrakill": "#Quadrakill #QuadraKill #LoLQuadra",
        "triple": "#TripleKill #Triple #LoLTriple",
        "double": "#DoubleKill #Double #LoLDouble",
        "solo_bolo": "#SoloBolo #SoloKill #1v1 #Outplay #League1v1",
        "solo": "#SoloBolo #1v1 #SoloKill",
        "outplay": "#Outplay #LoLOutplay #MechanicalOutplay",
        "clutch": "#Clutch #1PercentHP #Outplay",
        "oneshot": "#OneShot",
    }
    action_tag = action_map.get(action_type.lower(), "#Outplay")
    tags = [
        "#Shorts", "#LeagueOfLegends", "#LoL",
        champion_tag, action_tag,
        "#Gaming", "#LoLHighlights", "#lolgaming",
        "#epicmoments", "#lolclips", f"#{clean}Plays",
        "#LoLShorts", "#LeagueOfLegendsShorts", "#GamingShorts"
    ]
    seen = set()
    unique_tags = []
    for t in " ".join(tags).split():
        t_clean = t.strip()
        if t_clean.lower() not in seen:
            seen.add(t_clean.lower())
            unique_tags.append(t_clean)
    return " ".join(unique_tags)


def _ensure_shorts_tag(text: str, champion: str = "Katarina", action_type: str = "outplay") -> str:
    """Zapewnia obecność viralowych hashtagów (#Shorts #LeagueOfLegends #LoL) w tytule."""
    if not text:
        return "#Shorts #LeagueOfLegends #LoL"

    t = text.strip()
    target_tags = ["#Shorts", "#LeagueOfLegends", "#LoL"]
    for tag in target_tags:
        if tag.lower() not in t.lower():
            if len(t) + len(tag) + 1 <= 96:
                t = f"{t} {tag}"

    return t


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
            f"Clean 1v5 or Enemy Trolling? 💀 {champ} Pentakill #Shorts #LeagueOfLegends #LoL",
            f"Rate this {champ} PENTAKILL 1-10! 🔥 #Shorts #LeagueOfLegends #LoL",
            f"One {champ}. Five Kills. PENTAKILL RAMPAGE! 💥 #Shorts #LeagueOfLegends #LoL",
            f"{champ}'s Unstoppable Pentakill! 💥 No Escape 💀 #Shorts #LeagueOfLegends #LoL",
            f"Five Enemies. One {champ}. Instant Regret. 😈 #Shorts #LeagueOfLegends #LoL",
            f"Entire Team Disappeared In Seconds 💀💥 {champ} Penta #Shorts #LeagueOfLegends #LoL",
            f"{champ} Pentakill – They Never Stood A Chance! 💥 #Shorts #LeagueOfLegends #LoL",
            f"Pure Mechanics or Enemy Throw? 😱 {champ} Penta #Shorts #LeagueOfLegends #LoL",
            f"This {champ} PENTAKILL is INSANE! 🔥 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "quadra" in act:
        templates = [
            f"Clean Quadra or Pure Luck? 🤔 {champ} 1v4 #Shorts #LeagueOfLegends #LoL",
            f"Rate this {champ} Quadra Kill 1-10! ⚡ #Shorts #LeagueOfLegends #LoL",
            f"They Thought They Had Me 😈 {champ} Quadra Kill 💥 #Shorts #LeagueOfLegends #LoL",
            f"{champ}'s Four-Kill Frenzy! ⚡ Quadra Domination #Shorts #LeagueOfLegends #LoL",
            f"Four Enemies Down in Seconds! Insane {champ} Quadra 🔥 #Shorts #LeagueOfLegends #LoL",
            f"They cornered {champ}... Bad idea. Quadra Kill! 💥 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "triple" in act:
        templates = [
            f"Clean Outplay or Enemy Griefing? 💀 {champ} Triple #Shorts #LeagueOfLegends #LoL",
            f"Rate this Triple Kill 1-10! 🔥 {champ} #Shorts #LeagueOfLegends #LoL",
            f"Triple Kill! They Never Saw {champ} Coming 😈 #Shorts #LeagueOfLegends #LoL",
            f"They cornered her. Bad idea. Triple Kill! 💥 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Chaos – {champ} Triple Kill 💥 #Shorts #LeagueOfLegends #LoL",
            f"Late Game Teamfight Masterclass – Triple Kill! 🔥 #Shorts #LeagueOfLegends #LoL",
            f"Their Dive on {champ}? Not Today! 💥 Triple Kill #Shorts #LeagueOfLegends #LoL",
            f"Underestimated {champ}? 😈 Triple Kill Outplay 🩸 #Shorts #LeagueOfLegends #LoL",
        ]
    elif "clutch" in act or "1hp" in act or "1%" in act:
        templates = [
            f"Calculated or 100% Luck? 🧠 1% HP {champ} Clutch #Shorts #LeagueOfLegends #LoL",
            f"How Did {champ} Survive That?! 💀 Rate 1-10 #Shorts #LeagueOfLegends #LoL",
            f"Surviving on 1% HP to Win The Fight! 💀🔥 {champ} Clutch #Shorts #LeagueOfLegends #LoL",
            f"They Thought He Was 100% Dead... 1% HP {champ} Miracle Outplay 🩸 #Shorts #LeagueOfLegends #LoL",
            f"1 HP and a Dream! 💀 Skill or Luck? 🔥 {champ} #Shorts #LeagueOfLegends #LoL",
            f"The Most Stressful 1% HP Clutch You'll See Today 😱 {champ} #Shorts #LeagueOfLegends #LoL",
        ]
    elif "double" in act:
        templates = [
            f"Clean Outplay or Enemy Misplay? 🤔 {champ} 2v1 #Shorts #LeagueOfLegends #LoL",
            f"Rate this 2v1 Double Kill 1-10! 💥 {champ} #Shorts #LeagueOfLegends #LoL",
            f"Clean Double Kill Turnaround! 💥 {champ} Outplay #Shorts #LeagueOfLegends #LoL",
            f"They Tried a 2v1 Dive on {champ}... Instant Double Kill 💀 #Shorts #LeagueOfLegends #LoL",
            f"Two Enemies Down In A Blink ⚡ {champ} Double Kill #Shorts #LeagueOfLegends #LoL",
            f"Never Dive A Fed {champ}! 💀 Fast Double Kill #Shorts #LeagueOfLegends #LoL",
        ]
    elif "solo" in act or "bolo" in act or "1v1" in act:
        templates = [
            f"Clean Outplay or 100% Luck? 🤔 {champ} SOLO BOLO #Shorts #LeagueOfLegends #LoL",
            f"SOLO BOLO! 👑 Was This Disrespectful? Rate 1-10 👇 #Shorts #LeagueOfLegends #LoL",
            f"Pure 1v1 Mechanics or Pure Luck? 😈 {champ} #Shorts #LeagueOfLegends #LoL",
            f"They Ego Challenged {champ} 1v1... Instant SOLO BOLO! 💀 #Shorts #LeagueOfLegends #LoL",
            f"Clean SOLO BOLO! 😈 They Really Thought They Won This 1v1? #Shorts #LeagueOfLegends #LoL",
            f"The Most Disrespectful 1v1 SOLO BOLO in High Elo 💀 #Shorts #LeagueOfLegends #LoL",
            f"Did the Enemy Misplay or Was This Clean? 💀 {champ} 1v1 #Shorts #LeagueOfLegends #LoL",
            f"Nobody Survives {champ} in a 1v1! Clean SOLO BOLO ⚡ #Shorts #LeagueOfLegends #LoL",
            f"SOLO BOLO Turnaround! 🩸 {champ} Duel Masterclass #Shorts #LeagueOfLegends #LoL",
        ]
    else:  # outplay / general
        templates = [
            f"Clean Outplay or Complete Luck? 🤔 {champ} #Shorts #LeagueOfLegends #LoL",
            f"Rate This {champ} Play 1-10! 🔥 #Shorts #LeagueOfLegends #LoL",
            f"Did They Misplay or Was This Clean? 💀 {champ} Outplay #Shorts #LeagueOfLegends #LoL",
            f"They Flashed In for the Kill... Bad Idea 😏 #Shorts #LeagueOfLegends #LoL",
            f"They Tried to Catch {champ} 💀 It Went Wrong 😏 #Shorts #LeagueOfLegends #LoL",
            f"All-In On {champ}? Instant Regret 💀 #Shorts #LeagueOfLegends #LoL",
            f"Underestimated {champ}? 😈 They Paid The Price 🩸 #Shorts #LeagueOfLegends #LoL",
            f"Enemy Tried an Outplay... They Got Outplayed. 💀 #Shorts #LeagueOfLegends #LoL",
        ]

    # Załaduj dynamiczną dyrektywę samouczenia
    winning_kw = []
    avoid_kw = []
    try:
        from lol_agent.learning_engine import get_learning_directive
        directive = get_learning_directive()
        winning_kw = [k.upper() for k in directive.get("winning_keywords", [])]
        avoid_kw = [k.upper() for k in directive.get("avoid_keywords", [])]
    except Exception:
        pass

    # Dynamiczne punktowanie szablonów wg historycznego CTR z kanału
    if winning_kw or avoid_kw:
        weights = []
        for t in templates:
            t_upper = t.upper()
            score = 1.0
            for kw in winning_kw:
                if kw in t_upper:
                    score += 1.8
            for akw in avoid_kw:
                if akw in t_upper:
                    score = max(0.1, score - 1.2)
            weights.append(score)
        return random.choices(templates, weights=weights, k=1)[0]

    return random.choice(templates)


def build_channel_description(title: str, champion: str = "Katarina", action_type: str = "outplay") -> str:
    """
    Buduje profesjonalny, angażujący opis YouTube z brandingiem kanału Dwannellenga,
    mocnym wezwaniem do subskrypcji i kompletem hashtagów.
    """
    champ = champion or "Katarina"
    act = action_type.lower()
    act_clean = "Solo Bolo" if ("solo" in act or "bolo" in act) else action_type.replace("_", " ").title()
    hashtags = _build_hashtags(champ, action_type)
    
    if "solo" in act or "bolo" in act or "1v1" in act:
        return (
            f"Pure 1v1 SOLO BOLO mechanics on {champ}! 🎮👑\n"
            f"They thought they had the duel won... instant ego check and regret.\n\n"
            f"🎮 League of Legends highlights & high-elo plays — Dwannellenga\n"
            f"⚡ New viral shorts and clutch moments every day!\n\n"
            f"👍 Drop a LIKE if this 1v1 was clean!\n"
            f"🔔 SUBSCRIBE to Dwannellenga so you never miss a clip!\n"
            f"💬 Rate this Solo Bolo 1-10 in the comments below! 👇\n\n"
            f"{hashtags}"
        )

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
    Generuje angażujący przypięty komentarz (Pinned Comment) z pytaniem zachęcającym do dyskusji
    oraz bezpośrednim micro-triggerem do polubienia filmu (zwiększa Like-to-View ratio 5-10x).
    """
    champ = champion or "Katarina"
    act = action_type.lower()

    if "solo" in act or "bolo" in act or "1v1" in act:
        comments = [
            f"1 to 10: How clean was this {champ} 1v1? 👇 (Drop a LIKE if you would have died here 💀)",
            f"Was this SOLO BOLO pure mechanics or pure luck? 😈 Comment below! 👇 (Leave a LIKE if this was clean! 🔥)",
            f"Did the enemy misplay or was this {champ} 100% calculated? 🧠👇 (Drop a LIKE for more {champ} duels!)",
            f"Rate this outplay 1-10! Would you ever take this 1v1? 👑👇 (Like to bless your ranked games 🍀)",
        ]
        return random.choice(comments)

    if "penta" in act:
        comments = [
            f"Rate this {champ} PENTAKILL 1-10! 🔥 (Drop a LIKE if you love {champ} teamfights 💥)",
            f"Was this clean mechanics or was the enemy team inting? 💀 Let me know below! 👇",
            f"1 to 10: How clean was this Penta? 👇 (Leave a LIKE to bless your next ranked game! 🍀)",
        ]
        return random.choice(comments)

    comments = [
        f"Rate this {champ} play 1-10 in the comments! 👇 (Drop a LIKE if you would have panicked 💀)",
        f"Did the enemy team misplay or was this {champ} outplay 100% calculated? 🧠👇 (Leave a LIKE if this was clean!)",
        f"What would you have done in this situation? 👇 Rate 1-10! 🔥 (Drop a LIKE for more {champ} clips!)",
        f"Cleanest {champ} play today? Drop a rating 1-10 below! 👇🔥 (Drop a LIKE if you main {champ}!)",
    ]
    return random.choice(comments)


def generate_metadata(
    action_type: str,
    champion_name: str = "Katarina",
    rank: str = "Master",
    language: str = "en",
    extra_context: dict = None,
) -> dict:
    """
    Główny generator metadanych z dynamicznym wzmocnieniem promptu Gemini (KROK 2).
    Wstrzykuje wygrywające struktury tytułów, słowa kluczowe CTR oraz referencje viralowe
    z learning_directive.json bezpośrednio do promptu AI.
    W przypadku braku API / błędu sieci bezpiecznie przełącza na szablony kanału.

    extra_context: opcjonalny dict z dodatkowym kontekstem, np.:
        {"map_zone": {"zone": "mid_lane", "zone_label": "Mid Lane", "confidence": 0.82}}
    """
    champ = champion_name or "Katarina"
    act_clean = ACTION_LABELS.get(action_type.lower(), action_type.replace("_", " ").title())

    # Pobierz dyrektywę samouczenia i parametry stylu
    try:
        from lol_agent.learning_engine import get_learning_directive
        directive = get_learning_directive()
    except Exception:
        directive = {}

    try:
        from lol_agent.tuning_manager import get_pacing_parameters
        tuning_params = get_pacing_parameters()
    except Exception:
        tuning_params = {"title_tone": "hype"}

    top_structure = directive.get("top_title_structure", "EGO_CHECK")
    winning_kw = directive.get("winning_keywords", ["RAMPAGE", "PIT", "DIVE", "SOLO BOLO", "CLEAN"])
    avoid_kw = directive.get("avoid_keywords", ["FIVE", "ONE", "INSANE", "DRAKE"])
    viral_titles = directive.get("top_viral_titles", [])
    title_tone = tuning_params.get("title_tone", "hype")

    viral_examples_str = "\n".join([f"- {t}" for t in viral_titles[:4]]) if viral_titles else "- Katarina’s Dragon Pit Rampage – Triple Kill! 💥\n- Enemy Tried to Dive Me 💀 It Went Wrong 😏"

    # Przygotuj kontekst lokalizacji z minimapy (jeśli dostępny)
    _ctx = extra_context or {}
    _zone_info = _ctx.get("map_zone", {}) or {}
    _zone = _zone_info.get("zone", "unknown")
    _zone_label = _zone_info.get("zone_label", "")
    _zone_conf = float(_zone_info.get("confidence", 0.0))
    if _zone_label and _zone_conf >= 0.60:
        map_location_block = (
            f"\nVERIFIED MAP LOCATION (detected from minimap, confidence {_zone_conf:.0%}):\n"
            f"- Fight happened in: {_zone_label}\n"
            f"- You MAY naturally reference this location in the title if it adds value.\n"
            f"  Examples: 'Mid Lane Duel', 'Top Lane Outplay', 'Baron Pit Fight'.\n"
            f"- Do NOT force it if it sounds awkward for this action type."
        )
    else:
        map_location_block = (
            "\nMAP LOCATION: Unknown (minimap detection confidence too low).\n"
            "DO NOT invent or assume any map location."
        )

    # Spróbuj wygenerować z Gemini AI
    if GEMINI_API_KEY:
        try:
            import google.genai as genai

            client = genai.Client(api_key=GEMINI_API_KEY)
            models_to_try = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]

            prompt = f"""You are a YouTube Shorts algorithm specialist for League of Legends gaming content.
Channel: Dwannellenga (English League of Legends Shorts).
Language: ENGLISH ONLY.

CONTEXT:
- Action Type: {act_clean} ({action_type})
- Champion: {champ}
- Rank: {rank}
- Tone: {title_tone} (high energy, engaging, high-CTR){map_location_block}

ACTION-SPECIFIC TITLE RULES (follow STRICTLY based on action_type):
- pentakill / quadrakill: Focus on the kill count. Words like "RAMPAGE", "WIPED", "CLEAN WIPE" fit.
- triple: Focus on the triple kill achievement. "TRIPLE KILL", "3 DOWN" style.
- solo_bolo / 1v1: Focus ONLY on the duel mechanics. Use "SOLO BOLO", "1v1", "EGO CHECK", "DUEL". DO NOT mention dragon, baron, tower, river, jungle.
- outplay: Focus on the skill expression. "OUTPLAYED", "MECHANICS", "CLUTCH" style.
- oneshot: Focus on instant burst. "DELETED", "ONE SHOT", "VAPORIZED" style.
- clutch: Focus on survival / comeback. "SURVIVED", "ESCAPED", "OUTRUN" style.
- escape: Focus on the chase / evasion. "ESCAPED", "DODGE", "CHASE FAILED" style.
- double: Focus on quick back-to-back kills. "2 DOWN", "DOUBLE TAP" style.
- baron / dragon: You MAY mention the objective (Baron, Dragon) since these are objective fights.

LOCATION RULE — CRITICAL:
{"Use the VERIFIED MAP LOCATION above naturally if confidence is high." if _zone_label and _zone_conf >= 0.60 else "DO NOT invent or assume map locations (tower, river, dragon pit, jungle) — you have no data about where the fight happened."}

CRITICAL VIRAL RULES (DYNAMIC REINFORCEMENT FROM CHANNEL ANALYTICS):
1. WINNING TITLE STRUCTURE: Prioritize '{top_structure}' formula.
   (Examples: Ego Check / Disrespect / 1v1 Skill Check / Rampage).
2. HIGH-CTR POWER KEYWORDS (incorporate 1-2 naturally): {', '.join(winning_kw[:6])}
3. STRICTLY FORBIDDEN / LOW-CTR WORDS (DO NOT USE): {', '.join(avoid_kw[:6])}
4. CHANNEL BENCHMARK VIRAL TITLES (Model your style after these top hits):
{viral_examples_str}
5. FORMATTING: Title under 65 chars + hashtags, 1-2 emojis, MUST include #Shorts #LeagueOfLegends #LoL.
6. ENGAGEMENT TRIGGER MANDATE (VITAL TO BREAK PAST 1.5K VIEWS):
   - Title MUST pose a provocative question or challenge (e.g. 'Clean or Luck?', 'Rate 1-10', 'Ego Challenged').
   - Pinned comment MUST ask a fast question requiring a rating (1-10) or short reaction AND end with a like trigger in parentheses (e.g. 'Rate 1-10 👇 (Drop a LIKE if you would have died here 💀)').

GENERATE JSON ONLY (no markdown fences, raw json):
{{
  "title": "Provocative/High-CTR Short title with 1-2 emojis ending with #Shorts #LeagueOfLegends #LoL",
  "hook_text": "3-4 words punchy overlay in ALL CAPS (e.g. CLEAN OUTPLAY)",
  "description": "Engaging 2-3 sentence description encouraging likes and comments with hashtags #LeagueOfLegends #LoL #{champ.replace(' ', '')} #Shorts",
  "pinned_comment": "Specific rating question 1-10 with an engaging like trigger in parentheses",
  "tags": ["{champ.lower()}", "lol {champ.lower()}", "league of legends", "shorts", "gaming", "outplay"]
}}"""


            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = resp.text.strip()
                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()

                    data = json.loads(raw_text)
                    gen_title = _ensure_shorts_tag(data.get("title", ""), champ, action_type)
                    hashtags = _build_hashtags(champ, action_type)
                    raw_desc = (data.get("description") or "").strip()
                    if raw_desc:
                        if "#leagueoflegends" not in raw_desc.lower() or raw_desc.count("#") < 3:
                            gen_desc = f"{raw_desc}\n\n{hashtags}"
                        else:
                            gen_desc = raw_desc
                    else:
                        gen_desc = build_channel_description(gen_title, champ, action_type)
                    gen_pin = data.get("pinned_comment") or build_pinned_comment(champ, action_type)
                    gen_hook = data.get("hook_text") or f"{action_type.upper()}! 💥"
                    raw_tags = [t.lstrip("#").strip() for t in data.get("tags", []) if t.strip()]
                    all_tags = list(dict.fromkeys(raw_tags + YT_BASE_TAGS))[:30]

                    print(f"   [Gemini AI] Wygenerowano wzmocniony tytuł ({model_name}): {gen_title}")
                    return {
                        "title": gen_title,
                        "description": gen_desc,
                        "pinned_comment": gen_pin,
                        "tags": all_tags,
                        "hook_text": gen_hook,
                        "champion": champ,
                        "rank": rank,
                        "action_type": action_type,
                        "source": f"gemini_{model_name}_reinforced",
                    }
                except Exception as me:
                    print(f"   [Gemini AI] Model {model_name} warning: {me}")
                    continue
        except Exception as ge:
            print(f"   [Gemini AI] General failure: {ge}")

    # Fallback na szablony z wagami CTR kanału
    print(f"   [Fallback] Użyto szablonu kanału z wagami słów kluczowych CTR")
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
        "source": "template_ctr_weighted",
    }


def generate_fallback_title(action_label: str, champion: str, rank: str) -> str:
    return generate_channel_title(action_label, champion, rank)


def generate_fallback_description(action_label: str, champion: str) -> str:
    return build_channel_description("", champion, action_label)


def generate_fallback_metadata(
    action_label: str, champion: str, rank: str, action_type: str
) -> dict:
    return generate_metadata(action_type, champion, rank)


def generate_metadata_universal(
    game_type: str = "lol",
    action_type: str = "outplay",
    subject_name: str = "Katarina",
    rank: str = "Master",
    extra_context: dict = None
) -> dict:
    """
    Universal metadata generator — routes to appropriate profile based on game_type.
    Backward compatible: game_type='lol' → existing generate_metadata() behavior.
    extra_context: optional dict with additional data, e.g. {"map_zone": {...}}
    """
    if not game_type or game_type == "lol":
        return generate_metadata(action_type, subject_name or "Katarina", rank,
                                 extra_context=extra_context)
    try:
        from lol_agent.metadata_profiles import generate_metadata_for_game
    except ImportError:
        try:
            from metadata_profiles import generate_metadata_for_game
        except ImportError:
            return generate_metadata(action_type, subject_name or "Katarina", rank)
    return generate_metadata_for_game(
        game_type=game_type,
        action_type=action_type,
        subject_name=subject_name,
        rank=rank,
        extra_context=extra_context
    )


if __name__ == "__main__":
    res = generate_metadata("triple", "Katarina", "Master")
    print("TITLE:", res["title"])
    print("\nDESCRIPTION:\n", res["description"])
    print("\nPINNED COMMENT:", res["pinned_comment"])

