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


try:
    from lol_agent.synapsa_engine import strip_rank_prefix
except ImportError:
    try:
        from synapsa_engine import strip_rank_prefix
    except ImportError:
        def strip_rank_prefix(title: str) -> str:
            return re.sub(r'^(?:(?:master|diamond|challenger|grandmaster|emerald|platinum|gold|silver|bronze)\s*(?:tier|elo)?|tier)\s+', '', str(title or ''), flags=re.IGNORECASE).strip()


def _build_hashtags(champion: str = "Katarina", action_type: str = "outplay") -> str:
    """Buduje bogaty zestaw viralowych hashtagów pod algorytm YouTube Shorts (kanoniczne małe litery)."""
    clean = re.sub(r"[^a-zA-Z0-9]", "", champion).lower() if champion else "katarina"
    act = (action_type or "outplay").lower().replace("_", "")

    action_map = {
        "pentakill": "#pentakill #lolpentakill",
        "quadrakill": "#quadrakill #lolquadra",
        "triple": "#triplekill #loltriple",
        "double": "#doublekill #loldouble",
        "solobolo": "#solobolo #solokill #1v1 #outplay",
        "solo": "#solobolo #1v1",
        "outplay": "#outplay #loloutplay",
        "clutch": "#clutch #outplay",
        "oneshot": "#oneshot",
    }
    action_tag = action_map.get(act, "#outplay")
    tags = [
        "#shorts", "#shortsfeed", "#leagueoflegends", "#lol",
        f"#{clean}", f"#{clean}montage", action_tag,
        "#lolhighlights", "#gaming", "#gamingclips"
    ]
    seen = set()
    unique_tags = []
    for t in " ".join(tags).split():
        t_clean = t.strip().lower()
        if t_clean not in seen:
            seen.add(t_clean)
            unique_tags.append(t_clean)
    return " ".join(unique_tags)


def build_rich_youtube_tags(champion: str = "Katarina", action_type: str = "outplay", rank: str = "Master") -> list:
    """
    Generuje bogaty zestaw słów kluczowych do pola 'Tagi' (max 500 znaków) na YouTube.
    Zawiera frazy championa, akcji, elo oraz wyszukiwań broad bez przedrostka '#'.
    """
    champ = (champion or "Katarina").strip()
    c_lower = champ.lower()
    act = (action_type or "outplay").lower().replace("_", " ").strip()

    candidate_tags = [
        c_lower,
        f"{c_lower} montage",
        f"{c_lower} outplay",
        f"{c_lower} gameplay",
        f"lol {c_lower}",
        f"{c_lower} lol",
        f"{c_lower} best plays",
        f"{c_lower} mechanics",
        f"{c_lower} 1v1",
        f"{c_lower} mid",
        f"{c_lower} guide",
        act,
        f"{c_lower} {act}",
        f"{act} lol",
        f"{act} league of legends",
        "triple kill",
        "penta kill",
        "pentakill",
        "solo bolo",
        "1v1 outplay",
        "mechanical outplay",
        "clutch",
        "league of legends",
        "lol",
        "lol shorts",
        "league shorts",
        "lol highlights",
        "league of legends highlights",
        "lol montage",
        "best lol plays",
        "gaming",
        "gaming shorts",
        "pc gaming",
        "riot games",
        "challenger",
        "master tier",
        "high elo lol",
        "dwannellenga",
        "shorts feed",
        "trending gaming",
    ]

    seen = set()
    result = []
    char_count = 0
    for t in candidate_tags:
        clean = re.sub(r"[#,\n,]", "", t).strip().lower()
        if not clean or clean in seen:
            continue
        if char_count + len(clean) + 1 > 480:
            continue
        seen.add(clean)
        result.append(clean)
        char_count += len(clean) + 1

    return result


def _ensure_shorts_tag(text: str, champion: str = "Katarina", action_type: str = "outplay") -> str:
    """Zapewnia obecność tagu #shorts w opisie (do użytku w opisach i komentarzach)."""
    if not text:
        return "#shorts"

    t = text.strip()
    t = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", t)
    if "#shorts" not in t.lower():
        if len(t) + len(" #shorts") <= 96:
            t = f"{t} #shorts"
        else:
            t = t[:96 - len(" #shorts")].rstrip() + " #shorts"

    return t


def _format_final_title(raw_title: str) -> str:
    """
    Wymusza końcowy format viralowego tytułu YouTube Shorts:
    <hook> #shorts #leagueoflegends #lol
    
    Usuwa duplikaty tagów, normalizuje wszystkie tagi do kanonicznych małych liter i pilnuje limitu 96 znaków.
    Zawsze gwarantuje obecność WSZYSTKICH trzech tagów kanonicznych.
    """
    if not raw_title:
        return "#shorts #leagueoflegends #lol"

    t = raw_title.strip()
    # Usuń wszystkie hashtagi z końca i środka w dowolnej wielkości liter
    t = re.sub(r'\s*#Shorts\b', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*#LeagueOfLegends\b', '', t, flags=re.IGNORECASE).strip()
    t = re.sub(r'\s*#LoL\b', '', t, flags=re.IGNORECASE).strip()
    # Konwertuj ewentualne inne hasztagi w tytule na małe litery
    t = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", t)
    t = t.rstrip(" ,.")

    suffix = " #shorts #leagueoflegends #lol"
    max_hook = 96 - len(suffix)
    if len(t) > max_hook:
        t = t[:max_hook].rstrip()

    return f"{t}{suffix}"


def generate_channel_title(
    action_type: str = "outplay",
    champion: str = "Katarina",
    rank: str = "",
    map_zone_label: str = "",
    variant: str = "A",
    exclude_title: str = "",
) -> str:
    """
    Zwraca sprawdzony, wiralowy tytuł YouTube Shorts dopasowany do standardu kanału Dwannellenga
    oraz aktywnego tonu AI (Hype & High Energy / Storytelling & Clutch / Meme & Casual Gaming).
    Obsługuje A/B testing tytułów (variant='A' vs variant='B').
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
            f"Entire Team Disappeared in 3 Seconds 💀 {champ} Penta #Shorts",
            f"Enemy Team Wiped Clean 💀 {champ} Pentakill #Shorts",
            f"They Grouped For Free 💀 {champ} Pentakill #Shorts",
            f"They Tried to Contest... Complete Wipe 😈 {champ} #Shorts",
            f"Enemy Made the Wrong Call 💀 {champ} Pentakill #Shorts",
            f"They Scattered. Didn't Matter. 💨 {champ} Penta #Shorts",
            f"Full Squad Execution 💀 {champ} Pentakill #Shorts",
            f"Zero Hesitation. Pure Execution. 💀 {champ} Penta #Shorts",
            f"They Challenged the Reset Queen 👑 Full Pentakill #Shorts",
            f"Enemy Team Deleted in Seconds ⚡ {champ} Pentakill #Shorts",
            f"From Full HP to Ace in Under 4 Seconds 💀🔥 #Shorts",
            f"Vanished Before They Could Even Flash 💨 {champ} Ace #Shorts",
            f"The Health Bars Just Vanished 💀 {champ} Pentakill #Shorts",
            f"Every Reset Timed to the Millisecond ⚡ {champ} 💥 #Shorts",
            f"Absolute Teamfight Domination 💥 {champ} Pentakill #Shorts",
        ]
        if map_zone_label:
            templates.append(f"{map_zone_label} Ace 💀 {champ} Pentakill – Clean Wipe #Shorts")
    elif "quadra" in act:
        templates = [
            f"They Thought 4v1 Was Safe... It Wasn't 😏 {champ} #Shorts",
            f"All Four Down. Just Like That. 💀 {champ} Quadra #Shorts",
            f"Enemy Squad Disassembled 💀 {champ} Quadra Kill #Shorts",
            f"They Tried to Collapse... Counter Wipe 😈 {champ} #Shorts",
            f"They Thought Numbers Would Win 😏 {champ} Quadra #Shorts",
            f"Four Enemies Gone in Seconds ⚡ {champ} Quadra #Shorts",
            f"Four Down. Clean Execution. 💥 {champ} Quadra #Shorts",
            f"Clean Cleanup ⚡ {champ} Quadra Kill #Shorts",
            f"All Four Down Before Cooldowns Returned ⚡ {champ} #Shorts",
            f"Zero Hesitation 1v4 Execution 🔥 {champ} #Shorts",
            f"Walking Into {champ} Like That Was Fatal 💀 #Shorts",
            f"The Moment The Enemy Realized It Was Over 💀 Quadra #Shorts",
        ]
        if map_zone_label:
            templates.append(f"{map_zone_label} Quadra Kill 💀 {champ} Clean 1v4 #Shorts")
    elif "triple" in act:
        templates = [
            f"ADC Down… Mid Saved? Not Today! 💥 Triple Kill #Shorts",
            f"Three Enemies Gone in 2 Seconds ⚡ {champ} Triple 🔥 #Shorts",
            f"Clean Reset Sequence 🔥 {champ} Triple Kill 🩸 #Shorts",
            f"Three Down in One Single Breath ⚡ {champ} #Shorts",
            f"They Clustered Together... Total Destruction 💥 {champ} Triple #Shorts",
            f"Disrespect Turned Into Silence 😈 {champ} Triple #Shorts",
            f"They Walked Right Into The Daggers 💀 {champ} #Shorts",
            f"Back-to-Back Resets Under Pressure 🩸 {champ} Triple #Shorts",
            f"They Thought They Had The 3v1 Lock 💀 {champ} Triple Turnaround #Shorts",
            f"One By One They Dropped ⚡ {champ} Triple Kill 🔥 #Shorts",
            f"Frame-Perfect Reset Cascade 💀 {champ} Triple #Shorts",
            f"Three Down. Clean Outplay. 💀 {champ} Triple Kill #Shorts",
            f"Zero Hesitation. Three Down. 💥 {champ} Triple ⚡ #Shorts",
        ]
        if map_zone_label:
            templates.append(f"{map_zone_label} Triple Kill 💀 {champ} – Clean Execution #Shorts")
    elif "clutch" in act or "1hp" in act or "1%" in act:
        templates = [
            f"Surviving on 1% HP to Win 🩸 {champ} Clutch #Shorts",
            f"They Were 1 Second Too Late 😏 {champ} Clutch #Shorts",
            f"1 HP. Full Commitment. 💀 {champ} Outplay #Shorts",
            f"The Cleanest 1% HP Outplay You'll See Today 💀 #Shorts",
            f"They Already Typed 'GG'... {champ} Didn't. 🔥 #Shorts",
            f"Dead or Alive? {champ} Answers With a Kill 🩸 #Shorts",
            f"They Tried to Finish Me... Impossible Outplay 🩸 #Shorts",
            f"Enemy Got Greedy 😏 1% HP Turnaround #Shorts",
            f"They Thought It Was Over 💀 {champ} Clutch Outplay #Shorts",
            f"Enemy Celebrated Too Early 😈 1 HP Clutch #Shorts",
            f"Pure Calculation on 1 HP 🧠 {champ} Clutch #Shorts",
            f"Survived the Full Burst ⚡ {champ} Miracle Outplay #Shorts",
        ]
    elif "double" in act:
        templates = [
            f"From Nowhere to Double Kill – and Gone! 💨 #Shorts",
            f"They Came 2v1... Left in Graves 💀 {champ} Double 🔥 #Shorts",
            f"Greedy Chase Turned Around 😈 Clean Double Kill ⚡ #Shorts",
            f"Two Down in a Blink 💥 {champ} 2v1 Turnaround 💀 #Shorts",
            f"Two Resets in 1 Second ⚡ Clean Double Kill 🔥 #Shorts",
            f"They Tried to Pinch {champ}... Instant 2v1 Reversal 💀 #Shorts",
            f"Enemy Duo Deleted Before They Could Move ⚡ #Shorts",
            f"Walking Into Her Zone Was Their Final Play 💀 Double Kill #Shorts",
            f"Never Double Commit on {champ} 😈 Clean Double Kill #Shorts",
            f"Both Health Bars Melted Simultaneously 💥 {champ} #Shorts",
            f"Back-to-Back Execution 🩸 {champ} Double Kill #Shorts",
            f"Two Down. Zero Hesitation. 🩸 {champ} Double Kill #Shorts",
        ]
        if map_zone_label:
            templates.append(f"{map_zone_label} 2v1 Outplay 💀 {champ} Double Kill #Shorts")
    elif "solo" in act or "bolo" in act or "1v1" in act:
        templates = [
            f"Clean SOLO BOLO 👑 1v1 Masterclass 💀 #Shorts",
            f"They Ego Challenged {champ}... Sent to Base 😈 #Shorts",
            f"Nobody Survives {champ} in a 1v1 👑 Clean SOLO BOLO #Shorts",
            f"Walking Up Like That Is Crazy 💀 {champ} 1v1 #Shorts",
            f"They Tested {champ} and Found Out 💀 SOLO BOLO #Shorts",
            f"Overconfidence Punished in 0.5 Seconds 👑 SOLO BOLO #Shorts",
            f"Dodge Everything, Hit Everything 👑 {champ} 1v1 #Shorts",
            f"They Really Thought They Could 1v1 This 💀 SOLO BOLO #Shorts",
            f"Calculated to the Exact Millisecond 🧠 Clean 1v1 #Shorts",
            f"Pixel-Perfect 1v1 Outplay 💀 {champ} SOLO BOLO 🔥 #Shorts",
            f"Duel Accepted. Duel Won. 💀 Clean SOLO BOLO ⚡ #Shorts",
            f"They Stepped Up... Instant Gray Screen 💀 SOLO BOLO #Shorts",
            f"The Level of Disrespect in This 1v1 😈 {champ} #Shorts",
        ]
        if map_zone_label:
            templates.append(f"Clean {map_zone_label} SOLO BOLO! 👑 {champ} 1v1 #Shorts")
            templates.append(f"They Challenged {champ} in {map_zone_label}... Clean Duel 💀 #Shorts")
    else:  # outplay / general
        templates = [
            f"No Escape 💀 Hunting Down The Entire Team 🔥 #Shorts",
            f"Frame-Perfect Reaction 🔥 Clean Outplay 💀 #Shorts",
            f"Zero Hesitation. Pure Execution. 💀 {champ} Outplay 🔥 #Shorts",
            f"The Health Bars Just Disappeared 💀 {champ} #Shorts",
            f"They Didn't Even Realize What Happened 💀 {champ} #Shorts",
            f"The Level of Disrespect in This Play 😈 {champ} #Shorts",
            f"They Thought They Had The Upper Hand 😏 Reversal ⚡ #Shorts",
            f"One Ability Dodge Changed The Whole Fight 🧠 {champ} #Shorts",
            f"Outplayed at Every Single Step 💀 {champ} Mechanics #Shorts",
            f"They Flashed Into Their Own Doom 💀 {champ} Outplay #Shorts",
            f"Zero Hesitation. Pure Mechanics. 🔥 {champ} #Shorts",
            f"They Vanished in Seconds 💨 {champ} Outplay #Shorts",
            f"Enemy Team Miscalculated 💀 {champ} Clean Outplay #Shorts",
        ]
        if map_zone_label:
            templates.append(f"Clean {map_zone_label} Outplay 💀 {champ} #Shorts")

    # Dynamiczne punktowanie wg CTR (junk keywords odfiltrowywane przy ładowaniu dyrektywy)
    _JUNK_SCORE_KW = {"DIVE", "SHORTS", "LEAGUEOFLEGENDS", "LOL", "RIOTGAMES", "GAMING"}
    winning_kw = []
    avoid_kw = []
    fatigued_fps = []
    try:
        from lol_agent.learning_engine import get_learning_directive
        directive = get_learning_directive()
        winning_kw = [k.upper() for k in directive.get("winning_keywords", []) if k.upper() not in _JUNK_SCORE_KW]
        avoid_kw = [k.upper() for k in directive.get("avoid_keywords", []) if k.upper() not in _JUNK_SCORE_KW]
        fatigue_items = directive.get("title_fatigue", {}).get("repeated_phrases", [])
        fatigued_fps = [it["phrase"].upper() for it in fatigue_items if it.get("count", 0) >= 2]
    except Exception:
        pass

    # Załaduj odciski (2-word, 3-word i 4-word) z ostatnich 30 opublikowanych tytułów
    _used_fingerprints: set = set()
    _banned_recent_tropes: set = {
        "BAD IDEA", "HUNTING GROUNDS", "MASSACRE", "RESET MACHINE",
        "CHAOS", "BIG MISTAKE", "REGRET", "MISTAKE"
    }
    try:
        _pub_log = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
        if os.path.exists(_pub_log):
            with open(_pub_log, "r", encoding="utf-8") as _pf:
                _plines = [l.strip() for l in _pf if l.strip()]
            for _pl in _plines[-30:]:
                try:
                    _pt = json.loads(_pl).get("title", "")
                    if _pt:
                        _pt_clean = re.sub(r'#\S+', '', _pt)
                        _pt_clean = re.sub(r'[^\w\s]', '', _pt_clean).strip().upper()
                        _words = _pt_clean.split()
                        if len(_words) >= 2:
                            _used_fingerprints.add(" ".join(_words[:2]))
                        if len(_words) >= 3:
                            _used_fingerprints.add(" ".join(_words[:3]))
                        if len(_words) >= 4:
                            _used_fingerprints.add(" ".join(_words[:4]))
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

        # Subtelny bonus za lokalizację (+0.3 zamiast agresywnego +6.0)
        if map_zone_label and map_zone_label.upper() in t_upper:
            score += 0.3

        # Bezwzględny zakaz overused cliches
        for trope in _banned_recent_tropes:
            if trope in t_upper:
                score = 0.0001
                break

        if score > 0.001:
            for kw in winning_kw:
                if re.search(rf"\b{re.escape(kw)}\b", t_clean):
                    score += 0.8  # Umiarkowany bonus, by nie faworyzować stale tych samych słów
            for akw in avoid_kw:
                if re.search(rf"\b{re.escape(akw)}\b", t_clean):
                    score = max(0.05, score - 1.2)

            # Penalizuj szablony dotknięte zmęczeniem materiałowym (title fatigue)
            for ffp in fatigued_fps:
                ffp_words = ffp.split()
                if len(ffp_words) >= 2 and all(w in t_clean for w in ffp_words[:2]):
                    score = 0.0001
                    break

            # Głęboka deduplikacja: jeśli szablon zaczyna się od tych samych 2 słów co niedawny film
            if len(t_words) >= 2 and " ".join(t_words[:2]) in _used_fingerprints:
                score = 0.0001
            elif len(t_words) >= 3 and " ".join(t_words[:3]) in _used_fingerprints:
                score = 0.0001

        # A/B Testing: wyklucz identyczny tytuł jeśli podano exclude_title
        if exclude_title:
            clean_excl = exclude_title.split("#")[0].strip().upper()
            if t.split("#")[0].strip().upper() == clean_excl:
                score = 0.0001

        # A/B Testing: Wariant B promuje alternatywne kąty
        if str(variant).upper() == "B":
            if any(q in t for q in ["?", "They Thought", "Tried", "Safe", "Wrong", "Surviving", "Calculation", "Miracle", "Cleanest"]):
                score *= 3.0

        weights.append(score)

    return _format_final_title(random.choices(templates, weights=weights, k=1)[0])


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
            f"💬 Clean mechanics or greedy enemy mistake? Drop your take below! 👇\n\n"
            f"🌐 Connect with us across platforms:\n"
            f"📘 Facebook: https://www.facebook.com/Dwannellenga\n"
            f"📸 Instagram: https://www.instagram.com/dwannellenga\n"
            f"🎵 TikTok: https://www.tiktok.com/@dwannellenga\n\n"
            f"{hashtags}"
        )

    return (
        f"Insane {champ} {act_clean}{loc_str} in League of Legends! 🎮🔥\n"
        f"They thought they had the fight won, but {champ} turned everything around in seconds.\n\n"
        f"🎮 League of Legends highlights & high-elo plays — Dwannellenga\n"
        f"⚡ New viral shorts and clutch moments every day!\n\n"
        f"👍 Drop a LIKE if you enjoyed the outplay!\n"
        f"🔔 SUBSCRIBE to Dwannellenga so you never miss a clip!\n"
        f"💬 Would you have chased here or backed off? Drop your take below! 👇\n\n"
        f"🌐 Connect with us across platforms:\n"
        f"📘 Facebook: https://www.facebook.com/Dwannellenga\n"
        f"📸 Instagram: https://www.instagram.com/dwannellenga\n"
        f"🎵 TikTok: https://www.tiktok.com/@dwannellenga\n\n"
        f"{hashtags}"
    )


_FORBIDDEN_COMMENT_TERMS = (
    "flash", "flashed", "ignite", "exhaust", "tp", "teleport",
    "zhonya", "baron", "dragon", "rate this play 1-10", "rate 1-10",
    "1 to 10", "facebook.com", "part #", "road to",
)


def sanitize_pinned_comment(text: str, extra_context: Optional[dict] = None) -> str:
    """
    Usuwa linki zewnętrzne (facebook.com), szablony 'Rate 1-10', zmyślone spelle oraz
    prefiksy rangowe, jeśli nie wynikają wprost ze zweryfikowanej telemetrii HUD.
    """
    if not text:
        return ""
    cleaned = str(text).strip()
    # Usuń stopkę facebook / social promo doklejaną dawniej do komentarza
    cleaned = re.sub(r"\n+👉\s*Catch daily.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
    cleaned = re.sub(r"https?://\S+", "", cleaned).strip()

    ctx = extra_context or {}
    hud_spells = ctx.get("hud_spells_used") or {}
    spells_verified = bool(hud_spells.get("verified")) and any(
        hud_spells.get(k) for k in ("d_used", "f_used", "r_used")
    )
    _mz = ctx.get("map_zone")
    z_label = (
        (_mz.get("zone_label") or _mz.get("zone") or "")
        if isinstance(_mz, dict)
        else str(_mz or "")
    ).lower()

    low = cleaned.lower()
    if len(cleaned) > 140:
        return ""
    bot_phrases = (
        "rate 1-10", "rate this", "1 to 10", "part #", "road to",
        "tell us what you think", "let us know", "in the comments below",
        "what do you guys think", "drop a like and subscribe",
    )
    if any(b in low for b in bot_phrases):
        return ""
    if not spells_verified and any(sp in low for sp in ("flash", "flashed", "ignite", "exhaust", "zhonya", "tp ", "teleport")):
        return ""
    if "tower dive" in low or "dived" in low:
        return ""
    if "baron" in low and "baron" not in z_label:
        return ""
    if "dragon" in low and "dragon" not in z_label:
        return ""
    return cleaned


def _get_comment_history_path(explicit_path: Optional[str] = None) -> Optional[str]:
    if explicit_path:
        return explicit_path
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "accounts", "comment_history.json")


def _load_recent_comments(history_path: Optional[str]) -> List[str]:
    if not history_path or not os.path.isfile(history_path):
        return []
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data[-10:]] if isinstance(data, list) else []
    except Exception:
        return []


def _record_comment_history(comment_text: str, history_path: Optional[str]) -> None:
    if not history_path or not comment_text:
        return
    try:
        recent = _load_recent_comments(history_path)
        recent.append(comment_text)
        os.makedirs(os.path.dirname(history_path), exist_ok=True)
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(recent[-10:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def build_pinned_comment(
    champion: str = "Katarina",
    action_type: str = "outplay",
    extra_context: Optional[dict] = None,
    comment_history_path: Optional[str] = None,
) -> str:
    """
    Generuje wiarygodny przypięty komentarz oparty wyłącznie o zweryfikowaną telemetrię klipu
    (bez linku facebook.com, bez szablonu 'Rate 1-10', bez zmyślonych spelli i powtórek).
    """
    champ = champion or "Katarina"
    act = (action_type or "outplay").lower()
    ctx = extra_context or {}

    kill_span = float(ctx.get("kill_span_s") or 0.0)
    k_count = int(ctx.get("kill_count") or 0)
    min_hp = ctx.get("min_hp_pct")
    low_hp = bool(ctx.get("low_hp_survival")) or (min_hp is not None and float(min_hp) <= 22.0)
    clean_stomp = bool(ctx.get("clean_stomp")) or (min_hp is not None and float(min_hp) >= 75.0)
    enemies = int(ctx.get("enemies_in_fight") or 0)

    candidates: List[str] = []

    # 1) Warianty oparte ściśle o zmierzone fakty z montażu / screenów HUD
    if low_hp and min_hp is not None:
        hp_int = max(1, min(22, int(round(float(min_hp)))))
        candidates.extend([
            f"Dropped down to ~{hp_int}% HP and still turned the fight — greedy overchase by them or clean {champ} limit test? 💀",
            f"Honest check: when you hit ~{hp_int}% HP here, are you backing out or resetting back in? 👇",
        ])
    elif low_hp:
        candidates.extend([
            f"One hit away from dying and still got the reset — calculated {champ} damage or pure enemy panic? 💀",
            "Would you have turned back in on that sliver of HP or backed off? 👇",
        ])

    if kill_span >= 0.4 and k_count >= 2:
        candidates.extend([
            f"{k_count} eliminations in {kill_span:.1f}s — did the enemy clump up for free or was that reset too fast? 👇",
            f"Blinked for {kill_span:.1f} seconds and the fight was over. Who messed up first on the enemy team? 💀",
        ])

    if enemies >= 3 and k_count >= 1:
        candidates.extend([
            f"Outnumbered {enemies} targets in frame — did they tunnel vision too hard or play the spacing wrong? 👇",
        ])

    if clean_stomp:
        candidates.extend([
            f"Barely lost any HP in that sequence — massive spacing gap or huge item advantage? 👀",
        ])

    # 2) Bezpieczne uniwersalne dylematy gracza dopasowane do kategorii (zero spelli!)
    if "solo" in act or "bolo" in act or "1v1" in act:
        candidates.extend([
            f"Did enemy mid disrespect the {champ} damage window or did they actually have an outplay angle here? 👇",
            f"Honest question for {champ} mains: clean 1v1 spacing or did the opponent hand this over? 🧠",
            f"Watch the spacing right before the final blow — calculated bait or coinflip ego duel? 👇",
        ])
    elif "penta" in act:
        candidates.extend([
            "At which elimination did the enemy team realize they could not stop the resets? Watch the first 3 seconds 💀",
            f"Was this {champ} pentakill enabled by clean target priority or enemy mispositioning? 👇",
            "Which enemy player threw this fight the hardest? Comment the moment 👇",
        ])
    elif "triple" in act or "quadra" in act:
        candidates.extend([
            f"Clean reset chain or did they group right on top of {champ} daggers? 👇",
            "Which target needed to hold crowd control instead of walking up here? 💀",
            f"Be honest — did you expect the last kill to connect on {champ} or did you think they walked out? 👇",
        ])
    else:
        candidates.extend([
            f"Greedy play that paid off or completely calculated {champ} angle? Drop your take below 👇",
            "Which mistake cost the enemy team this fight the most? 💀",
            f"What was the turning point in this sequence — engage timing or target selection? 👇",
            "Would you have committed for that final chase or taken the safe reset? 👀",
        ])

    hist_path = _get_comment_history_path(comment_history_path)
    recent = _load_recent_comments(hist_path)
    recent_low = {r.strip().lower() for r in recent}
    fresh = [c for c in candidates if c.strip().lower() not in recent_low]
    pool = fresh if fresh else candidates
    chosen = random.choice(pool)
    _record_comment_history(chosen, hist_path)
    return chosen


_GENERIC_HOOKS = {
    "INSANE OUTPLAY", "INSANE OUTPLAY!", "CLEAN OUTPLAY", "NICE PLAY",
    "CLEAN MECHANICAL OUTPLAY", "MECHANICAL OUTPLAY", "INSANE MECHANICAL OUTPLAY",
    "PIXEL PERFECT OUTPLAY", "CLEAN PLAY", "MECHANICAL PLAY",
    "OUTPLAY", "OUTPLAY!", "PENTAKILL", "PENTAKILL!", "TRIPLE KILL",
    "DOUBLE KILL", "SOLO BOLO", "CLUTCH", "QUADRAKILL",
}


def sanitize_hook_text(
    raw_hook: str,
    action_type: str = "outplay",
    champion: str = "Katarina",
    kill_span_s: float = 0.0,
    low_hp_survival: bool = False,
    min_hp_pct: Optional[float] = None,
    objective_secured: bool = False,
    map_zone: str = "",
) -> str:
    """Czyści lub generuje z telemetrii zwięzły ALL CAPS hook (<=34 zn., zero generyków typu INSANE OUTPLAY!)."""
    cleaned = re.sub(r"[^\x00-\x7F]+", "", str(raw_hook or "")).replace("'", "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).upper()
    act = (action_type or "outplay").lower().strip()
    champ_u = (champion or "KATARINA").upper().strip()

    is_generic = (
        (not cleaned)
        or (cleaned.rstrip("!.") in _GENERIC_HOOKS)
        or ("INSANE OUTPLAY" in cleaned)
        or ("NICE PLAY" in cleaned)
        or cleaned.rstrip("!.").endswith((" CLIP", " HIGHLIGHT", " VIDEO", " PLAY"))
        or (objective_secured and ("quadra" in act or "triple" in act or "penta" in act)
            and not any(k in cleaned for k in ("DRAGON", "DRAKE", "BARON", "STEAL", "OBJECTIVE")))
    )
    if is_generic or len(cleaned) < 6:
        if objective_secured and ("quadra" in act or "triple" in act or "penta" in act):
            cleaned = f"DRAGON STEAL + {act.replace('kill', '').upper()}".strip()
        elif objective_secured:
            cleaned = "OBJECTIVE STEAL OUTPLAY"
        elif low_hp_survival or (min_hp_pct is not None and float(min_hp_pct) <= 12.0):
            hp_n = max(1, int(round(float(min_hp_pct)))) if min_hp_pct is not None else 1
            cleaned = f"{hp_n}% HP TURNAROUND"
        elif "triple" in act and 0.0 < float(kill_span_s or 0.0) <= 7.0:
            cleaned = f"3 KILLS IN {float(kill_span_s):.1f}S"
        elif "double" in act and 0.0 < float(kill_span_s or 0.0) <= 5.0:
            cleaned = f"2 KILLS IN {float(kill_span_s):.1f}S"
        elif "triple" in act:
            cleaned = "TRIPLE RESET WIPE"
        elif "quadra" in act:
            cleaned = "QUADRA RESET CHAIN"
        elif "penta" in act:
            cleaned = "UNSTOPPABLE 5V5 WIPE"
        elif "solo" in act or "1v1" in act:
            cleaned = "1V1 EGO CHECK"
        elif map_zone:
            cleaned = f"{map_zone.upper()} CLEAN RESET"
        else:
            cleaned = f"{champ_u} RESET WIPE"

    words = cleaned.split()[:5]
    out = " ".join(words)
    if len(out) > 34:
        out = out[:34].rsplit(" ", 1)[0] if " " in out[:34] else out[:34]
    return out.strip()


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

    # Załaduj ostatnie 30 tytułów — buduj odciski frazowe (2, 3 i 4 słowa bez emoji/hashtag)
    _recent_titles = []
    _recent_fingerprints = []
    try:
        _pub_log = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
        if os.path.exists(_pub_log):
            with open(_pub_log, "r", encoding="utf-8") as _f:
                _lines = [l.strip() for l in _f if l.strip()]
            for _line in _lines[-30:]:
                try:
                    _t = json.loads(_line).get("title", "")
                    if _t:
                        _recent_titles.append(_t.split("#")[0].strip())
                        _fp = re.sub(r'#\S+', '', _t)
                        _fp = re.sub(r'[^\w\s]', '', _fp).strip().upper()
                        _fp_words = _fp.split()
                        if len(_fp_words) >= 2:
                            _recent_fingerprints.append(" ".join(_fp_words[:2]))
                        if len(_fp_words) >= 3:
                            _recent_fingerprints.append(" ".join(_fp_words[:3]))
                        if len(_fp_words) >= 4:
                            _recent_fingerprints.append(" ".join(_fp_words[:4]))
                except Exception:
                    pass
    except Exception:
        pass
    fatigue_info = directive.get("title_fatigue", {})
    repeated_items = fatigue_info.get("repeated_phrases", [])
    fatigued_phrases = [item["phrase"].upper() for item in repeated_items if item.get("count", 0) >= 2]

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
    if fatigued_phrases:
        fatigue_lines = "\n".join(f'- "{p}"' for p in fatigued_phrases)
        _fatigue_block = f"\n\nTITLE FATIGUE WARNING (STRICTLY FORBIDDEN OPENING PHRASES — OVERUSED ON CHANNEL):\n{fatigue_lines}"
        _recent_titles_block = (_recent_titles_block + _fatigue_block) if _recent_titles_block else _fatigue_block

    viral_examples_str = "\n".join([f"- {t}" for t in viral_titles[:4]]) if viral_titles else "- Katarina’s Dragon Pit Rampage – Triple Kill! 💥\n- No Escape From Katarina 💀 Clean Triple Kill!"

    # Przygotuj kontekst lokalizacji z minimapy (jeśli dostępny)
    _ctx = extra_context or {}
    _raw_zone = _ctx.get("map_zone")
    if isinstance(_raw_zone, dict):
        _zone_info = _raw_zone
        _zone = _zone_info.get("zone", "unknown")
        _zone_label = _zone_info.get("zone_label", "")
        _zone_conf = float(_zone_info.get("confidence", 0.0))
        valid_zone = _zone_label if _zone_conf >= 0.60 else ""
    else:
        _zone = str(_raw_zone or "unknown")
        _zone_label = str(_raw_zone or "")
        _zone_conf = 1.0 if _zone_label else 0.0
        valid_zone = _zone_label

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
    _kill_span_s = _ctx.get("kill_span_s")
    _min_hp_pct = _ctx.get("min_hp_pct")
    _low_hp = bool(_ctx.get("low_hp_survival"))
    _clean_stomp = bool(_ctx.get("clean_stomp"))
    _enemies = _ctx.get("enemies_in_fight")
    _combo_tempo = _ctx.get("combo_tempo", "")
    _montage_style = _ctx.get("montage_style", "")
    _objective_secured = bool(_ctx.get("objective_secured"))
    _objective_label = str(_ctx.get("objective_label") or "")
    _hud_spells = _ctx.get("hud_spells_used") or {}

    action_context_lines = []
    if _combat_style:
        action_context_lines.append(f"- Combat Style: {_combat_style}")
    if _combat_narrative:
        action_context_lines.append(f"- Combat Narrative: {_combat_narrative}")
    if _objective_secured:
        action_context_lines.append(f"- Epic Objective Secured/Stolen During Fight: YES ({_objective_label or 'Drake/Baron'})")
    if _kill_count is not None and _kill_count > 0:
        action_context_lines.append(f"- Verified Kill Count: {_kill_count}")
    if _kill_span_s is not None and float(_kill_span_s) > 0:
        action_context_lines.append(f"- Verified Kill Window Span: {_kill_span_s}s ({_combo_tempo})")
    if _min_hp_pct is not None:
        action_context_lines.append(f"- Verified Player Minimum HP: ~{_min_hp_pct}% (low_hp_survival={_low_hp}, clean_stomp={_clean_stomp})")
    if _enemies is not None and int(_enemies) > 0:
        action_context_lines.append(f"- Enemy Healthbars Detected: {_enemies}")
    if _montage_style:
        action_context_lines.append(f"- Montage Style: {_montage_style}")
    if _hud_spells.get("verified"):
        used_list = [k.replace("_used", "").upper() for k in ("d_used", "f_used", "r_used") if _hud_spells.get(k)]
        action_context_lines.append(f"- Verified HUD Cooldowns Triggered: {', '.join(used_list) if used_list else 'none observed'}")
    else:
        action_context_lines.append("- Summoner Spells (Flash/Ignite/Exhaust): NOT VERIFIED — DO NOT MENTION ANY SPELL NAMES.")
    if _clip_dur:
        action_context_lines.append(f"- Clip Length: {_clip_dur}s")
    action_context_block = ("\n" + "\n".join(action_context_lines)) if action_context_lines else ""

    # ── PRIORYTET #1: Lokalna Synapsa (Qwen2.5-7B-4bit + LoRA, 0 tokenów API) ──
    try:
        try:
            from lol_agent.synapsa_engine import generate_with_synapsa, score_and_select_best_titles
        except ImportError:
            from synapsa_engine import generate_with_synapsa, score_and_select_best_titles

        syn_payload = {
            "champion": champ,
            "action_type": action_type,
            "kill_count": _kill_count or 1,
            "kill_span_s": round(float(_kill_span_s or 0.0), 2),
            "min_hp_pct": _min_hp_pct,
            "low_hp_survival": _low_hp,
            "enemies_in_fight": _enemies or 1,
            "map_zone": valid_zone,
            "montage_style": _montage_style,
            "hud_spells_verified": bool(_hud_spells.get("verified")),
            "objective_secured": _objective_secured,
        }
        syn_res = generate_with_synapsa("lol_metadata", syn_payload, timeout=140)
        if syn_res and isinstance(syn_res.get("title_candidates"), list) and syn_res["title_candidates"]:
            best_a, best_b = score_and_select_best_titles(
                [str(c) for c in syn_res["title_candidates"]],
                action_type=action_type,
                extra_context=_ctx,
                directive=directive,
                recent_titles=_recent_titles,
            )
            if best_a:
                gen_title = _format_final_title(strip_rank_prefix(best_a))
                gen_title_b = _format_final_title(strip_rank_prefix(best_b)) if best_b and best_b != best_a else generate_channel_title(action_type, champ, rank, map_zone_label=valid_zone, variant="B", exclude_title=gen_title)
                hashtags = _build_hashtags(champ, action_type)
                raw_desc = (syn_res.get("description") or "").strip()
                social_block = (
                    "\n\n🌐 Connect with us across platforms:\n"
                    "📘 Facebook: https://www.facebook.com/Dwannellenga\n"
                    "📸 Instagram: https://www.instagram.com/dwannellenga\n"
                    "🎵 TikTok: https://www.tiktok.com/@dwannellenga"
                )
                gen_desc = f"{re.sub(r'#\\S+', '', raw_desc).strip()}\n\n{hashtags}{social_block}" if raw_desc else build_channel_description(gen_title, champ, action_type, map_zone_label=valid_zone)
                syn_pin = sanitize_pinned_comment(syn_res.get("pinned_comment") or "", extra_context=_ctx)
                gen_pin = syn_pin or build_pinned_comment(champ, action_type, extra_context=_ctx)
                rich_base = build_rich_youtube_tags(champ, action_type, rank)
                raw_tags = [str(t).lstrip("#").strip().lower() for t in (syn_res.get("tags") or []) if str(t).strip()]
                all_tags = list(dict.fromkeys(rich_base + raw_tags))[:20]
                return {
                    "title": gen_title,
                    "title_variant_b": gen_title_b,
                    "title_variants": [gen_title, gen_title_b],
                    "description": gen_desc,
                    "pinned_comment": gen_pin,
                    "tags": all_tags,
                    "hook_text": sanitize_hook_text(
                        syn_res.get("hook_text") or "",
                        action_type=action_type,
                        champion=champ,
                        kill_span_s=float(_kill_span_s or 0.0),
                        low_hp_survival=_low_hp,
                        min_hp_pct=_min_hp_pct,
                        objective_secured=_objective_secured,
                        map_zone=valid_zone,
                    ),
                    "champion": champ,
                    "rank": rank,
                    "action_type": action_type,
                    "source": "synapsa_local_lora",
                }
    except Exception as _syn_err:
        print(f"   [Synapsa AI] Fallback na Gemini/Szablon ({_syn_err})")

    # Spróbuj wygenerować z Gemini AI (opcjonalny fallback)
    allow_live_gemini = not (
        os.environ.get("PYTEST_CURRENT_TEST")
        and os.environ.get("ALLOW_LIVE_GEMINI_IN_TEST") != "1"
    )
    if GEMINI_API_KEY and allow_live_gemini:
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
- STRICTLY FORBIDDEN RANK PREFIX:
  * NEVER prepend the rank to champion name as a title prefix (e.g. DO NOT write "Master Katarina", "Diamond Katarina"). Rank is purely context for play quality, NOT a title hook!
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
5. FORMATTING: Hook phrase first (max 45 visible chars before hashtags), then MUST end with viral hashtags: #shorts #leagueoflegends #lol. 1-2 emojis max.
6. TITLE ARCHETYPE ROTATION — choose ONE archetype that fits this clip best, DO NOT default to questions:
   - DISRESPECT / EGO: "They Grouped For Free 💀", "They Thought 1v1 Was Safe 😏", "Walking Up Like That Is Crazy 💀"
   - STATEMENT / SPEED: "Entire Team Disappeared in 2 Seconds ⚡", "No Escape From the Reset Chain 💨"
   - STORY / TURNAROUND: "Duel Accepted. Duel Won. 💀", "They Already Typed 'GG' 🔥", "One Misstep Cost the Fight 💀"
   - MECHANICAL FLEX: "Pixel-Perfect Reaction 🔥", "Calculated to the Exact Millisecond 🧠", "Dodge Everything, Hit Everything 👑"
   - CLUTCH / STAKES: "Surviving on 1 HP to Win 🩸", "The Cleanest 1% HP Clutch 💀"
   - HUNT / CHASE: "No Escape 💀 Hunting Down The Squad 🔥", "Chasing Down Every Single Reset ⚡"
   DO NOT USE "Rate 1-10", "Part #", "Road to", OR UNVERIFIED SPELL NAMES (Flash/Ignite/Exhaust/Zhonya).
7. STRICTLY FORBIDDEN CLICHES & TROPE WORDS (DO NOT USE UNDER ANY CIRCUMSTANCES):
   - "Bad Idea", "Hunting Grounds", "Massacre", "Reset Machine", "Mistake", "Regret"
   - Never prepend rank or champion as prefix like "Master Katarina", "Master Reset".
8. PINNED COMMENT: Ask one sharp debate/dilemma question strictly grounded in verified combat facts above (NO external links like facebook.com, NO 'Rate 1-10', NO invented Flash/Ignite claims).
{_recent_titles_block}

GENERATE JSON ONLY (no markdown fences, raw json):
{{
  "title": "Strong punchy hook (max 45 chars) + #shorts #leagueoflegends #lol at end.",
  "hook_text": "3-4 words punchy overlay in ALL CAPS (e.g. CLEAN OUTPLAY)",
  "description": "Engaging 2-3 sentence description encouraging likes and comments. ENGLISH ONLY.",
  "pinned_comment": "Direct question that triggers comments + like trigger",
  "tags": ["{champ.lower()}", "lol {champ.lower()}", "league of legends", "shorts", "gaming", "outplay"]
}}"""


            gen_config = None
            try:
                from google.genai import types as _genai_types
                gen_config = _genai_types.GenerateContentConfig(temperature=0.85)
            except Exception:
                pass

            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(model=model_name, contents=prompt, config=gen_config) if gen_config else client.models.generate_content(model=model_name, contents=prompt)
                    raw_text = resp.text.strip()
                    if "```json" in raw_text:
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in raw_text:
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()

                    data = json.loads(raw_text)
                    _raw_title = data.get("title", "").strip()
                    # Polish language detection — odrzuć ewentualne polskie słowa w angielskich Shortsach
                    POLISH_MARKERS = [
                        "roku", "nie ma", "szans", "który", "która", "przez",
                        "tego", " jest ", " tak ", "ale ", "czyli", "żeby", "można",
                        "kiedy", "każdy", "bardzo", "zawsze", "nigdy", "tylko",
                        "więc", "jednak", "dlatego", "potem", "teraz", "właśnie",
                        "przed", "zaraz", "nawet", "gdzie", "tutaj", " dlaczego ",
                    ]
                    _combined_check = f"{_raw_title.lower()} {(data.get('description') or '').lower()}"
                    _detected_pl = [p for p in POLISH_MARKERS if p in _combined_check]
                    if _detected_pl:
                        print(f"   [Gemini AI] ⚠️ Wykryto polskie słowa w tytule/opisie ({_detected_pl}) — ponawiam...")
                        continue

                    # Usuń niechciane prefixy rangowe (np. "Master Katarina ...", "Tier ...")
                    _raw_title = strip_rank_prefix(_raw_title)

                    # Wymuś pełny zestaw viralowych tagów: #Shorts #LeagueOfLegends #LoL
                    gen_title = _format_final_title(_raw_title)

                    # Sprawdź bezwzględnie zakazane klisze
                    BANNED_TROPES = ["bad idea", "hunting grounds", "massacre", "reset machine", "mistake", "regret"]
                    if any(bt in gen_title.lower() for bt in BANNED_TROPES):
                        print(f"   [Gemini AI] ⚠️ Tytuł '{gen_title}' zawiera zakazaną kliszę — odrzucam i ponawiam...")
                        continue

                    # Sprawdź czy wygenerowany tytuł nie wpada w wykryte zmęczenie materiałowe (title fatigue) i duplikaty
                    _t_clean = re.sub(r'#\S+', '', gen_title.upper())
                    _t_clean = re.sub(r'[^\w\s]', '', _t_clean).strip()
                    _t_words = _t_clean.split()
                    if len(_t_words) >= 2:
                        _gen_fp2 = " ".join(_t_words[:2])
                        _gen_fp3 = " ".join(_t_words[:3]) if len(_t_words) >= 3 else _gen_fp2
                        _gen_fp4 = " ".join(_t_words[:4]) if len(_t_words) >= 4 else _gen_fp3

                        # Sprawdź powtórzenie otwierających słów z ostatnich filmów
                        if any(_gen_fp2 == fp for fp in _recent_fingerprints if len(fp.split()) == 2):
                            print(f"   [Gemini AI] ⚠️ Tytuł '{gen_title}' powtarza pierwsze 2 słowa niedawnego filmu ('{_gen_fp2}') — odrzucam i ponawiam...")
                            continue

                        # Sprawdź zmęczenie materiałowe (title fatigue)
                        if fatigued_phrases and any(_gen_fp3 == fp or _gen_fp3.startswith(fp) for fp in fatigued_phrases):
                            print(f"   [Gemini AI] ⚠️ Tytuł '{gen_title}' narusza title fatigue (fraza '{_gen_fp3}') — odrzucam i ponawiam...")
                            continue
                        # Sprawdź duplikację z ostatnimi opublikowanymi filmami
                        if _recent_fingerprints and any(_gen_fp3 == fp or _gen_fp4 == fp or fp.startswith(_gen_fp3) for fp in _recent_fingerprints):
                            print(f"   [Gemini AI] ⚠️ Tytuł '{gen_title}' powtarza niedawny motyw kanału ('{_gen_fp3}') — odrzucam i ponawiam...")
                            continue

                    hashtags = _build_hashtags(champ, action_type)
                    raw_desc = (data.get("description") or "").strip()
                    social_block = (
                        "\n\n🌐 Connect with us across platforms:\n"
                        "📘 Facebook: https://www.facebook.com/Dwannellenga\n"
                        "📸 Instagram: https://www.instagram.com/dwannellenga\n"
                        "🎵 TikTok: https://www.tiktok.com/@dwannellenga"
                    )
                    if raw_desc:
                        # Usuń wszelkie wplecione hashtagi z surowego tekstu — wstawiamy czysty blok kanoniczny na końcu
                        clean_desc_body = re.sub(r'#\S+', '', raw_desc).strip()
                        clean_desc_body = re.sub(r'\n\s*\n+', '\n\n', clean_desc_body).strip()
                        if valid_zone and valid_zone.lower() not in clean_desc_body.lower():
                            clean_desc_body = f"{clean_desc_body}\n\n📍 Location: {valid_zone}"
                        gen_desc = f"{clean_desc_body}\n\n{hashtags}{social_block}"
                    else:
                        gen_desc = build_channel_description(gen_title, champ, action_type, map_zone_label=valid_zone)

                    raw_pin = sanitize_pinned_comment(data.get("pinned_comment") or "", extra_context=_ctx)
                    gen_pin = raw_pin or build_pinned_comment(champ, action_type, extra_context=_ctx)
                    gen_hook = data.get("hook_text") or f"{action_type.upper()}! 💥"
                    rich_base = build_rich_youtube_tags(champ, action_type, rank)
                    raw_tags = [t.lstrip("#").strip().lower() for t in data.get("tags", []) if t.strip()]
                    all_tags = list(dict.fromkeys(rich_base + raw_tags))
                    pruned_tags = []
                    t_len = 0
                    for tag in all_tags:
                        if t_len + len(tag) + 1 <= 480:
                            pruned_tags.append(tag)
                            t_len += len(tag) + 1
                    all_tags = pruned_tags

                    gen_title_b = generate_channel_title(action_type, champ, rank, map_zone_label=valid_zone, variant="B", exclude_title=gen_title)
                    print(f"   [Gemini AI] Wygenerowano wzmocniony tytuł ({model_name}): {gen_title}")
                    print(f"   [A/B Testing] Wariant B: {gen_title_b}")
                    return {
                        "title": gen_title,
                        "title_variant_b": gen_title_b,
                        "title_variants": [gen_title, gen_title_b],
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
    title = generate_channel_title(action_type, champ, rank, map_zone_label=valid_zone, variant="A")
    title_b = generate_channel_title(action_type, champ, rank, map_zone_label=valid_zone, variant="B", exclude_title=title)
    description = build_channel_description(title, champ, action_type, map_zone_label=valid_zone)
    pinned_comment = build_pinned_comment(champ, action_type, extra_context=_ctx)
    
    all_tags = build_rich_youtube_tags(champ, action_type, rank)

    return {
        "title": title,
        "title_variant_b": title_b,
        "title_variants": [title, title_b],
        "description": description,
        "pinned_comment": pinned_comment,
        "tags": all_tags,
        "hook_text": sanitize_hook_text(
            "",
            action_type=action_type,
            champion=champ,
            kill_span_s=float(_kill_span_s or 0.0),
            low_hp_survival=_low_hp,
            min_hp_pct=_min_hp_pct,
            objective_secured=_objective_secured,
            map_zone=valid_zone,
        ),
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
    Universal metadata generator — uwzględnia tryb i wytyczne kontentu aktywnego konta.
    Konto GAMING_HIGHLIGHTS (lub domyślny profil LoL) korzysta z generate_metadata().
    Konta reklamowe / salon / marka osobista kierowane są do account_manager.generate_account_aware_metadata().
    """
    try:
        try:
            from lol_agent.account_manager import get_active_account, generate_account_aware_metadata
        except ImportError:
            from account_manager import get_active_account, generate_account_aware_metadata
        active_acc = get_active_account()
        if active_acc and active_acc.get("content_mode") != "GAMING_HIGHLIGHTS":
            return generate_account_aware_metadata(
                action_type=action_type,
                subject_name=subject_name or active_acc.get("display_name") or "Produkt",
                extra_context=extra_context,
                account=active_acc,
            )
    except Exception:
        active_acc = None

    if not game_type or game_type == "lol":
        return generate_metadata(action_type, subject_name or "Katarina", rank,
                                 extra_context=extra_context)
    try:
        try:
            from lol_agent.account_manager import generate_account_aware_metadata
        except ImportError:
            from account_manager import generate_account_aware_metadata
        return generate_account_aware_metadata(
            action_type=action_type,
            subject_name=subject_name or "Produkt",
            extra_context=extra_context,
            account=active_acc,
        )
    except Exception:
        return generate_metadata(action_type, subject_name or "Katarina", rank)


def _fmt_mmss(sec: float) -> str:
    s = max(0, int(round(float(sec or 0.0))))
    return f"{s // 60}:{s % 60:02d}"


def generate_longform_metadata(
    champion: str = "Katarina",
    clips_meta: Optional[List[Dict[str, Any]]] = None,
    duration_s: float = 240.0,
    chapters: Optional[List[Dict[str, Any]]] = None,
    tracks_used: Optional[List[str]] = None,
    week_label: str = "",
    use_local_ai: bool = True,
) -> Dict[str, Any]:
    """
    Generuje metadane Long-Form 16:9 (`Etap 31.3`):
      - narracyjny tytuł <=65 zn. (ZERO `#shorts`, ZERO AI-żargonu),
      - auto-rozdziały WYŁĄCZNIE dla filmów >= 6 min (360s),
      - dokładnie 3 hasztagi SEO + lista utworów NCS.
    """
    champ = (champion or "Katarina").strip() or "Katarina"
    clean_champ = re.sub(r"[^a-zA-Z0-9]", "", champ) or "Katarina"
    n_clips = len(clips_meta or []) or 5
    actions = [str(c.get("action_type") or "outplay").replace("_", " ") for c in (clips_meta or [])]
    top_act = actions[-1] if actions else "outplay"

    ai_res: Optional[Dict[str, Any]] = None
    in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST")) and os.environ.get("ALLOW_LIVE_SYNAPSA_IN_TEST") != "1"
    if use_local_ai and not in_pytest:
        try:
            try:
                from lol_agent.synapsa_engine import generate_with_synapsa
            except ImportError:
                from synapsa_engine import generate_with_synapsa
            ai_res = generate_with_synapsa(
                "lol_longform_metadata",
                {
                    "champion": champ,
                    "clips_count": n_clips,
                    "duration_s": round(float(duration_s), 1),
                    "top_action": top_act,
                    "week_label": week_label,
                },
                timeout=90,
            )
        except Exception:
            ai_res = None

    raw_title = str((ai_res or {}).get("title") or "").strip()
    raw_title = re.sub(r"#\S+", "", raw_title).strip()
    raw_title = strip_rank_prefix(raw_title)
    _bad_lf = ("execution", "relentless", "reset chain", "pixel-perfect", "takedown", "rampage", "shorts")
    if len(raw_title) < 12 or any(b in raw_title.lower() for b in _bad_lf):
        title_pool = [
            f"Why Nobody Steps Up To {champ} | Best Plays",
            f"Top {n_clips} {champ} Outplays You Missed This Week",
            f"They Grouped Straight Into {champ} | Weekly Highlights",
        ]
        raw_title = title_pool[n_clips % len(title_pool)]
    title = raw_title[:65].strip()

    thumb_headline = str((ai_res or {}).get("thumbnail_headline") or "").strip()
    thumb_headline = re.sub(r"[^A-Za-z0-9!?%+\s-]", "", thumb_headline).upper().strip()
    if not thumb_headline or any(b in thumb_headline.lower() for b in _bad_lf):
        thumb_headline = "1 HP 1V4?!" if "clutch" in top_act or "quadra" in top_act else f"TOP {n_clips} PLAYS"
    thumb_headline = " ".join(thumb_headline.split()[:3])

    thumb_subline = str((ai_res or {}).get("thumbnail_subline") or "").strip().upper()
    if not thumb_subline:
        thumb_subline = f"{clean_champ.upper()} WEEKLY #1"

    intro = str((ai_res or {}).get("description_intro") or "").strip()
    intro = re.sub(r"(?<!\w)#shorts(?:feed)?\b", "", intro, flags=re.IGNORECASE).strip()
    if len(intro) < 20 or any(b in intro.lower() for b in _bad_lf):
        intro = (
            f"The cleanest {champ} highlights from this week in League of Legends, "
            f"counted down to the #1 play. Watch until the end to see which outplay took the top spot!"
        )

    lines: List[str] = [intro]
    if float(duration_s) >= 360.0 and chapters:
        lines.append("")
        lines.append("Chapters:")
        for ch in chapters:
            t_str = _fmt_mmss(float(ch.get("time_s") or 0.0))
            lbl = re.sub(r"#\S+", "", str(ch.get("label") or "Highlight")).strip()
            lines.append(f"{t_str} - {lbl}")

    if tracks_used:
        pretty_tracks = ", ".join(str(t).replace("ncs_", "").replace("_", " ").title() for t in tracks_used)
        lines.append("")
        lines.append(f"Music Credits (NCS): {pretty_tracks}")

    lines.extend([
        "",
        "Connect across platforms:",
        "Facebook: https://www.facebook.com/Dwannellenga",
        "Instagram: https://www.instagram.com/dwannellenga",
        "TikTok: https://www.tiktok.com/@dwannellenga",
        "",
        f"#LeagueOfLegends #{clean_champ} #LoLMontage",
    ])
    description = "\n".join(lines).strip()

    raw_tags = list((ai_res or {}).get("tags") or []) + [
        champ.lower(),
        "league of legends",
        f"{champ.lower()} montage",
        "league of legends montage",
        "lol highlights",
        "lol best plays",
        f"{champ.lower()} highlights",
        "outplays",
    ]
    clean_tags: List[str] = []
    seen_t: set[str] = set()
    for t in raw_tags:
        s = re.sub(r"^#", "", str(t or "")).strip().lower()
        if not s or s in ("shorts", "shortsfeed", "ytshots", "short") or s in seen_t:
            continue
        seen_t.add(s)
        clean_tags.append(s)
        if len(clean_tags) >= 15:
            break

    return {
        "title": title,
        "thumbnail_headline": thumb_headline,
        "thumbnail_subline": thumb_subline[:28],
        "description": description[:5000],
        "tags": clean_tags,
        "hashtags": ["#LeagueOfLegends", f"#{clean_champ}", "#LoLMontage"],
        "chapters_included": bool(float(duration_s) >= 360.0 and chapters),
        "video_format": "longform",
    }


if __name__ == "__main__":
    res = generate_metadata("triple", "Katarina", "Master")
    print("TITLE:", res["title"])
    print("\nDESCRIPTION:\n", res["description"])
    print("\nPINNED COMMENT:", res["pinned_comment"])

