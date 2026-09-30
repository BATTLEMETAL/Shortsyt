"""
LOL Agent - YouTube Metadata Generator (Dwannellenga Channel Proven Templates)
High-converting Titles, Descriptions, Pinned Comments & Tags optimised for YouTube Shorts Algorithm.
"""
import os
import re
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


def generate_channel_title(action_type: str = "outplay", champion: str = "Katarina", rank: str = "", map_zone_label: str = "") -> str:
    """
    Zwraca sprawdzony, wiralowy tytuł YouTube Shorts dopasowany do standardu kanału Dwannellenga
    oraz aktywnego tonu AI (Hype & High Energy / Storytelling & Clutch / Meme & Casual Gaming).
    """
    champ = champion or "Katarina"
    act = action_type.lower()
    loc = f" in {map_zone_label}" if map_zone_label else ""
    loc_prefix = f"{map_zone_label} " if map_zone_label else ""
    
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
            # STATEMENT / SPEED
            f"Entire Team Disappeared in 3 Seconds 💀 {champ} Penta #Shorts",
            f"One Reset. Five Graves. 💀 {champ} Pentakill #Shorts",
            # DISRESPECT / EGO
            f"They Grouped For Free 💀 {champ} Pentakill #Shorts",
            f"Five Enemies. Zero Survivors. 😈 {champ} #Shorts",
            # HUNT / CHASE
            f"No Escape 💀 Hunting Down All Five 🔥 #Shorts",
            f"They Scattered. Didn't Matter. 💨 {champ} Penta #Shorts",
            # MECHANICAL FLEX
            f"Perfect Reset Machine 🔥 {champ} Full Ace 😈 #Shorts",
            f"Zero Hesitation. Pure Execution. 💀 {champ} Penta #Shorts",
            # STORY
            f"They Thought Grouping Was Safe... It Wasn't 😏 #Shorts",
        ]
        if map_zone_label:
            templates.insert(0, f"{map_zone_label} Ace 💀 {champ} Pentakill – Nobody Left Standing #Shorts")
    elif "quadra" in act:
        templates = [
            # DISRESPECT / EGO
            f"They Thought 4v1 Was Safe... It Wasn't 😏 {champ} #Shorts",
            f"All Four Down. Just Like That. 💀 {champ} Quadra #Shorts",
            # HUNT / CHASE
            f"Hunting Down The Entire Squad 💀 {champ} Quadra #Shorts",
            f"No Escape For Any Of Them 😈 {champ} Quadra Kill #Shorts",
            # STATEMENT
            f"Four Enemies Gone in Seconds ⚡ {champ} Quadra #Shorts",
            f"Four Down. One {champ}. Clean. 💥 #Shorts",
            # STORY
            f"They Cornered {champ}... Wrong Decision. 💀 Quadra Kill #Shorts",
        ]
    elif "triple" in act:
        templates = [
            # HUNT / CHASE
            f"No Escape From {champ} 💀 Clean Triple Kill #Shorts",
            f"Hunting Down All Three 🔥 Triple Kill #Shorts",
            # DISRESPECT / EGO
            f"They Thought They Could Run 😈 Triple Kill #Shorts",
            f"Underestimated {champ}? 😈 They Paid The Price 🩸 #Shorts",
            # STATEMENT
            f"Three Down. Zero Chance. 💀 {champ} Triple Kill #Shorts",
            # STORY
            f"Trash Talk Turned Into Silence 😈 {champ} Triple Kill #Shorts",
            f"They Made Their Move... Wrong Choice. 💀 Triple Kill #Shorts",
            # MECHANICAL FLEX
            f"Back-to-Back-to-Back 🩸 {champ} Triple Kill Reset #Shorts",
        ]
        if map_zone_label:
            templates.insert(0, f"{map_zone_label} Triple Kill 💀 {champ} – Nobody Escaped #Shorts")
    elif "clutch" in act or "1hp" in act or "1%" in act:
        templates = [
            # CLUTCH / STAKES
            f"Surviving on 1% HP to Win 🩸 {champ} Clutch #Shorts",
            f"They Were 1 Second Too Late 😏 {champ} Clutch #Shorts",
            f"1 HP. Full Commitment. 💀 {champ} Outplay #Shorts",
            # STORY
            f"They Already Typed 'GG'... {champ} Didn't. 🔥 #Shorts",
            f"Dead or Alive? {champ} Answers With a Kill 🩸 #Shorts",
            # MECHANICAL FLEX
            f"The Cleanest 1% HP Escape You'll See Today 💀 #Shorts",
        ]
    elif "double" in act:
        templates = [
            # DISRESPECT
            f"They Came 2v1... Left 0v1. 💀 {champ} Double Kill #Shorts",
            f"Never Fight {champ} 2v1. 😈 Lesson Learned. #Shorts",
            # HUNT
            f"Two Enemies Down in a Blink ⚡ {champ} Double Kill #Shorts",
            f"No Flash. No Escape. Double Kill. 💀 {champ} #Shorts",
            # STATEMENT
            f"Back-to-Back Execution 🩸 {champ} Double Kill #Shorts",
            # STORY
            f"They Thought Numbers Would Help 💀 {champ} Double Kill #Shorts",
        ]
        if map_zone_label:
            templates.insert(0, f"{map_zone_label} 2v1 Outplay 💀 {champ} Double Kill – No Contest #Shorts")
    elif "solo" in act or "bolo" in act or "1v1" in act:
        templates = [
            # DISRESPECT / EGO (top performer on channel)
            f"They Ego Challenged {champ}... Instant SOLO BOLO 💀 #Shorts",
            f"The Most Disrespectful 1v1 You'll See Today 😈 {champ} #Shorts",
            f"Nobody Survives {champ} in a 1v1 👑 Clean SOLO BOLO #Shorts",
            # MECHANICAL FLEX
            f"SOLO BOLO Masterclass 😈 {champ} Pure 1v1 Mechanics #Shorts",
            f"Pixel-Perfect 1v1 Outplay 💀 {champ} SOLO BOLO #Shorts",
            # STORY
            f"They Called It… {champ} Answered. SOLO BOLO 🩸 #Shorts",
            f"Duel Accepted. Duel Won. 💀 {champ} SOLO BOLO #Shorts",
            # CLUTCH
            f"1v1 at Full Risk 🩸 {champ} SOLO BOLO Clutch #Shorts",
        ]
        if map_zone_label:
            templates.insert(0, f"Clean {map_zone_label} SOLO BOLO! 👑 {champ} 1v1 No Contest #Shorts")
            templates.append(f"They Challenged {champ} in {map_zone_label}... Instant SOLO BOLO 💀 #Shorts")
    else:  # outplay / general
        templates = [
            # DISRESPECT
            f"All-In On {champ}? Instant Regret 💀 #Shorts",
            f"They Thought They Were Safe... Big Mistake 😏 {champ} #Shorts",
            # HUNT
            f"No Escape 💀 Hunting Down The Entire Team 🔥 #Shorts",
            f"They Tried to Run. Nowhere to Go. 💀 {champ} #Shorts",
            # STORY
            f"Underestimated {champ}? 😈 They Paid The Price 🩸 #Shorts",
            f"Enemy Tried an Outplay... They Got Outplayed. 💀 #Shorts",
            # MECHANICAL FLEX
            f"Zero Hesitation. Pure Mechanics. 🔥 {champ} #Shorts",
            # STATEMENT
            f"They Vanished in Seconds 💨 {champ} Outplay #Shorts",
        ]
        if map_zone_label:
            templates.insert(0, f"Clean {map_zone_label} Outplay 💀 {champ} – They Never Stood a Chance #Shorts")

    # Dynamiczne punktowanie wg CTR (junk keywords odfiltrowywane przy ładowaniu dyrektywy)
    _JUNK_SCORE_KW = {"DIVE", "SHORTS", "LEAGUEOFLEGENDS", "LOL", "RIOTGAMES", "GAMING"}
    winning_kw = []
    avoid_kw = []
    try:
        from lol_agent.learning_engine import get_learning_directive
        directive = get_learning_directive()
        winning_kw = [k.upper() for k in directive.get("winning_keywords", []) if k.upper() not in _JUNK_SCORE_KW]
        avoid_kw = [k.upper() for k in directive.get("avoid_keywords", []) if k.upper() not in _JUNK_SCORE_KW]
    except Exception:
        pass

    # Dedup — ładuje odciski (pierwsze 4 słowa) z ostatnich 15 opublikowanych tytułów
    # i mocno obniża wagę szablonów które pasują do już użytej frazy
    _used_fingerprints: set = set()
    try:
        _pub_log = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
        if os.path.exists(_pub_log):
            with open(_pub_log, "r", encoding="utf-8") as _pf:
                _plines = [l.strip() for l in _pf if l.strip()]
            for _pl in _plines[-15:]:
                try:
                    _pt = json.loads(_pl).get("title", "")
                    if _pt:
                        # Usuń hashtagi, emoji i interpunkcję → pierwsze 4 słowa jako odcisk
                        _pt_clean = re.sub(r'#\S+', '', _pt)
                        _pt_clean = re.sub(r'[^\w\s]', '', _pt_clean).strip().upper()
                        _words = _pt_clean.split()
                        if len(_words) >= 3:
                            _used_fingerprints.add(" ".join(_words[:4]))
                            _used_fingerprints.add(" ".join(_words[:3]))
                except Exception:
                    pass
    except Exception:
        pass

    weights = []
    for t in templates:
        t_upper = t.upper()
        t_clean = re.sub(r'#\S+', '', t_upper)
        t_clean = re.sub(r'[^\w\s]', '', t_clean).strip()
        t_words = t_clean.split()
        score = 1.0
        if map_zone_label and map_zone_label.upper() in t_upper:
            score += 6.0
        for kw in winning_kw:
            if kw in t_upper:
                score += 1.8
        for akw in avoid_kw:
            if akw in t_upper:
                score = max(0.05, score - 1.2)
        # Penalizuj szablony których frazy kluczowe były niedawno użyte
        for fp in _used_fingerprints:
            fp_words = fp.split()
            if len(fp_words) >= 3 and all(w in t_clean for w in fp_words[:3]):
                score = max(0.05, score * 0.15)  # -85% wagi przy trafieniu odcisku
                break
        weights.append(score)
    return random.choices(templates, weights=weights, k=1)[0]


def build_channel_description(title: str, champion: str = "Katarina", action_type: str = "outplay", map_zone_label: str = "") -> str:
    """
    Buduje profesjonalny, angażujący opis YouTube z brandingiem kanału Dwannellenga,
    mocnym wezwaniem do subskrypcji i kompletem hashtagów.
    """
    champ = champion or "Katarina"
    act = action_type.lower()
    act_clean = "Solo Bolo" if ("solo" in act or "bolo" in act) else action_type.replace("_", " ").title()
    hashtags = _build_hashtags(champ, action_type)
    loc_str = f" in {map_zone_label}" if map_zone_label else ""
    
    if "solo" in act or "bolo" in act or "1v1" in act:
        return (
            f"Pure 1v1 SOLO BOLO mechanics on {champ}{loc_str}! 🎮👑\n"
            f"They thought they had the duel won... instant ego check and regret.\n\n"
            f"🎮 League of Legends highlights & high-elo plays — Dwannellenga\n"
            f"⚡ New viral shorts and clutch moments every day!\n\n"
            f"👍 Drop a LIKE if this 1v1 was clean!\n"
            f"🔔 SUBSCRIBE to Dwannellenga so you never miss a clip!\n"
            f"💬 Rate this Solo Bolo 1-10 in the comments below! 👇\n\n"
            f"{hashtags}"
        )

    return (
        f"Insane {champ} {act_clean}{loc_str} in League of Legends! 🎮🔥\n"
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

    top_structure = directive.get("top_title_structure", "CLEAN_OUTPLAY")
    _JUNK_KEYWORDS = {"DIVE", "SHORTS", "LEAGUEOFLEGENDS", "LOL", "RIOTGAMES", "GAMING",
                      "KATARINA", "LEAGUE", "HIGHLIGHTS", "GAMES", "CLIP", "THE", "AND"}
    raw_winning = directive.get("winning_keywords", ["RAMPAGE", "NO ESCAPE", "CHASE", "SOLO BOLO", "CLEAN"])
    winning_kw = [k for k in raw_winning if k.upper() not in _JUNK_KEYWORDS]
    avoid_kw = directive.get("avoid_keywords", ["INSANE", "DRAKE", "LATE GAME"])
    raw_viral = directive.get("top_viral_titles", [])
    viral_titles = [t for t in raw_viral if "dive" not in t.lower()]
    title_tone = tuning_params.get("title_tone", "hype")

    # Załaduj ostatnie 20 tytułów — buduj odciski frazowe (pierwsze 4 słowa bez emoji/hashtag)
    _recent_titles = []
    _recent_fingerprints = []
    try:
        _pub_log = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
        if os.path.exists(_pub_log):
            with open(_pub_log, "r", encoding="utf-8") as _f:
                _lines = [l.strip() for l in _f if l.strip()]
            for _line in _lines[-20:]:
                try:
                    _t = json.loads(_line).get("title", "")
                    if _t:
                        _recent_titles.append(_t.split("#")[0].strip())
                        _fp = re.sub(r'#\S+', '', _t)
                        _fp = re.sub(r'[^\w\s]', '', _fp).strip().upper()
                        _fp_words = _fp.split()
                        if len(_fp_words) >= 3:
                            _recent_fingerprints.append(" ".join(_fp_words[:4]))
                except Exception:
                    pass
    except Exception:
        pass
    _recent_titles_block = ""
    if _recent_titles:
        fp_block = "\n".join(f'- "{fp}"' for fp in _recent_fingerprints[-15:]) if _recent_fingerprints else ""
        _recent_titles_block = (
            "\n\nRECENTLY PUBLISHED — STRICT DEDUPLICATION:\n"
            "FORBIDDEN opening phrases (do NOT start title with these first 3+ words):\n"
            + fp_block
            + "\nFull recent titles (do NOT repeat or closely paraphrase):\n"
            + "\n".join(f'- "{t}"' for t in _recent_titles[-15:])
        )

    viral_examples_str = "\n".join([f"- {t}" for t in viral_titles[:4]]) if viral_titles else "- Katarina’s Dragon Pit Rampage – Triple Kill! 💥\n- No Escape From Katarina 💀 Clean Triple Kill!"

    # Przygotuj kontekst lokalizacji z minimapy (jeśli dostępny)
    _ctx = extra_context or {}
    _zone_info = _ctx.get("map_zone", {}) or {}
    _zone = _zone_info.get("zone", "unknown")
    _zone_label = _zone_info.get("zone_label", "")
    _zone_conf = float(_zone_info.get("confidence", 0.0))
    valid_zone = _zone_label if _zone_conf >= 0.60 else ""

    if valid_zone:
        map_location_block = (
            f"\nVERIFIED MAP LOCATION (detected from minimap, confidence {_zone_conf:.0%}):\n"
            f"- Fight happened in: {valid_zone}\n"
            f"- You MAY naturally reference this location in the title if it adds value.\n"
            f"  Examples: 'Mid Lane Duel', 'Top Lane Outplay', 'Baron Pit Fight'.\n"
            f"- Do NOT force it if it sounds awkward for this action type."
        )
    else:
        map_location_block = (
            "\nMAP LOCATION: Unknown (minimap detection confidence too low).\n"
            "DO NOT invent or assume any map location."
        )

    # Dodatkowy kontekst przebiegu akcji (kill count, czas trwania, styl walki, narracja)
    _kill_count = _ctx.get("kill_count")
    _clip_dur = _ctx.get("clip_duration")
    _combat_style = _ctx.get("combat_style", "")
    _combat_narrative = _ctx.get("combat_narrative", "")

    action_context_lines = []
    if _combat_style:
        action_context_lines.append(f"- Combat Style: {_combat_style}")
    if _combat_narrative:
        action_context_lines.append(f"- Combat Narrative: {_combat_narrative}")
    if _kill_count is not None and _kill_count > 0:
        action_context_lines.append(f"- Verified Kill Count: {_kill_count}")
    if _clip_dur:
        action_context_lines.append(f"- Clip Length: {_clip_dur}s")
    action_context_block = ("\n" + "\n".join(action_context_lines)) if action_context_lines else ""

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
- Tone: {title_tone} (high energy, engaging, high-CTR){action_context_block}{map_location_block}

ACTION-SPECIFIC TITLE RULES (follow STRICTLY based on action_type):
- pentakill / quadrakill: Focus on the kill count and ace. Words like "RAMPAGE", "WIPED", "CLEAN WIPE", "NO ESCAPE" fit.
- triple: Focus on the triple kill achievement and relentless pursuit. "TRIPLE KILL", "3 DOWN", "NO ESCAPE", "CHASE & RESET" style.
- solo_bolo / 1v1: Focus on the 1v1 duel mechanics ("SOLO BOLO", "1v1", "EGO CHECK", "DUEL"). If VERIFIED MAP LOCATION is provided above, you MAY mention that zone (e.g. 'Mid Lane 1v1', 'Top Lane SOLO BOLO'). NEVER mention towers, dives or unverified locations.
- outplay: Focus on active skill expression, engage, or hunting down fleeing enemies ("OUTPLAYED", "MECHANICS", "HUNTING THEM DOWN", "DISRESPECT").
- oneshot: Focus on instant burst. "DELETED", "ONE SHOT", "VAPORIZED" style.
- clutch: Focus on survival / comeback. "SURVIVED", "ESCAPED", "OUTRUN" style.
- escape: Focus on the chase / evasion. "ESCAPED", "DODGE", "CHASE FAILED" style.
- double: Focus on quick back-to-back kills or dual pursuit. "2 DOWN", "DOUBLE TAP", "CHASE & EXECUTE" style.
- baron / dragon: You MAY mention the objective (Baron, Dragon) since these are objective fights.

NARRATIVE & COMBAT INITIATIVE MANDATE (CRITICAL — PREVENT HALLUCINATIONS):
- CHAMPION IS THE AGGRESSOR / HUNTER: In high-elo League of Legends, mobile assassins like {champ} engage, flank, chase down, and execute retreating targets.
- STRICTLY FORBIDDEN DEFENSIVE CLAIMS:
  * NEVER claim or hallucinate that the enemy "tried to dive me", "tower dived", "ganked me", or "jumped me" unless the context above explicitly describes a tower dive defense.
  * If the clip is an aggressive chase or hunt, emphasize the relentless pursuit: e.g. "They Thought They Could Run 💀", "No Escape From {champ} 💥", "Chasing Down the Entire Team 😈", "Hunting Them Down 🔥".

LOCATION RULE — CRITICAL:
{"Use the VERIFIED MAP LOCATION above naturally if confidence is high." if valid_zone else "DO NOT invent or assume map locations (tower, river, dragon pit, jungle) — you have no data about where the fight happened."}

CRITICAL VIRAL RULES (DYNAMIC REINFORCEMENT FROM CHANNEL ANALYTICS):
1. WINNING TITLE STRUCTURE: Prioritize '{top_structure}' formula.
   (Examples: Ego Check / Disrespect / Relentless Hunt / Statement / Mechanical Flex)
2. HIGH-CTR POWER KEYWORDS (incorporate 1-2 naturally): {', '.join(winning_kw[:6]) if winning_kw else 'RAMPAGE, NO ESCAPE, CHASE, SOLO BOLO'}
3. STRICTLY FORBIDDEN / LOW-CTR WORDS (DO NOT USE): {', '.join(avoid_kw[:6])}
4. CHANNEL BENCHMARK VIRAL TITLES (Model your style after these top hits):
{viral_examples_str}
5. FORMATTING: Hook phrase first (max 45 visible chars before hashtags), then ONLY #Shorts at end of title. Put #LeagueOfLegends #LoL in DESCRIPTION, NOT in title. 1-2 emojis max.
6. TITLE ARCHETYPE ROTATION — choose ONE archetype that fits this clip best, DO NOT default to questions:
   - DISRESPECT / EGO: "They Grouped For Free 💀", "All-In On Katarina? Instant Regret 💀"
   - STATEMENT / SPEED: "Entire Team Disappeared in 2 Seconds ⚡", "One Reset. Five Graves. 🩸"
   - STORY / RETRIBUTION: "Trash Talk Turned Into Silence 😈", "They Cornered Her. Bad Idea. 💥"
   - MECHANICAL FLEX: "Perfect Reset Machine 🔥 Full Domination 😈", "Zero Hesitation. Pure Execution. 💀"
   - CLUTCH / STAKES: "Surviving on 1 HP to Win 🩸", "They Were 1 Second Too Late 😏"
   - HUNT / CHASE: "No Escape 💀 Hunting Down The Entire Team 🔥", "They Tried to Run. Nowhere to Go."
   QUESTIONS ("Rate 1-10", "Clean or Luck?") are ALLOWED but MUST be used sparingly — max 20% of output. Never two in a row.
7. PINNED COMMENT: Ask one direct question to trigger comments (e.g. "Would you have survived that? Drop 💀 if not!")
{_recent_titles_block}

GENERATE JSON ONLY (no markdown fences, raw json):
{{
  "title": "Strong punchy hook (max 45 chars) + #Shorts ONLY at end. No #LeagueOfLegends in title.",
  "hook_text": "3-4 words punchy overlay in ALL CAPS (e.g. CLEAN OUTPLAY)",
  "description": "Engaging 2-3 sentence description encouraging likes and comments with hashtags #LeagueOfLegends #LoL #{champ.replace(' ', '')} #Shorts",
  "pinned_comment": "Direct question that triggers comments + like trigger",
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
                    # Tytuł: tylko #Shorts na końcu. #LeagueOfLegends #LoL → opis.
                    _raw_title = data.get("title", "").strip()
                    if not _raw_title:
                        _raw_title = f"{action_type.upper()} {champ} #Shorts"
                    if "#shorts" not in _raw_title.lower():
                        _raw_title = f"{_raw_title} #Shorts"
                    # Usuń #LeagueOfLegends i #LoL z tytułu jeśli tam wpadły
                    _raw_title = re.sub(r'\s*#LeagueOfLegends\b', '', _raw_title, flags=re.IGNORECASE).strip()
                    _raw_title = re.sub(r'\s*#LoL\b', '', _raw_title, flags=re.IGNORECASE).strip()
                    gen_title = _raw_title
                    hashtags = _build_hashtags(champ, action_type)
                    raw_desc = (data.get("description") or "").strip()
                    if raw_desc:
                        if "#leagueoflegends" not in raw_desc.lower() or raw_desc.count("#") < 3:
                            gen_desc = f"{raw_desc}\n\n{hashtags}"
                        else:
                            gen_desc = raw_desc
                    else:
                        gen_desc = build_channel_description(gen_title, champ, action_type, map_zone_label=valid_zone)
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
    title = generate_channel_title(action_type, champ, rank, map_zone_label=valid_zone)
    description = build_channel_description(title, champ, action_type, map_zone_label=valid_zone)
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

