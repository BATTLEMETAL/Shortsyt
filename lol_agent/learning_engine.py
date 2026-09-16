"""
Shortsyt — Channel Autonomous Learning Engine
Analizuje realne wyniki opublikowanych filmów z YouTube, wylicza korelacje efektywności formatów
i generuje dynamiczną dyrektywę adaptacyjną (learning_directive.json) dla montażu, ewaluatora i metadanych.
Implementuje:
  1. Closed Pacing Loop: korelacja czasu trwania i dynamiki filmów z grupy viral_hit -> auto-tuning tuning_config.json.
  2. Dynamic Prompt / Title Reinforcement: klasyfikacja struktur tytułów i ekstrakcja wzorców CTR dla Gemini.
  3. Evaluator Weight Auto-Tuning: dynamiczne korygowanie wag akcji w evaluator.py na podstawie konwersji i engagementu.
"""
import os
import sys
import re
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

LEARNING_DIR = Path(__file__).resolve().parent
DIRECTIVE_FILE = LEARNING_DIR / "learning_directive.json"
TUNING_FILE = LEARNING_DIR / "tuning_config.json"
PUB_LOG_FILE = LEARNING_DIR / "published_videos.jsonl"

DEFAULT_ACTION_WEIGHTS = {
    "pentakill": 1.0,
    "solo_bolo": 1.35,
    "clutch": 1.20,
    "triple": 1.10,
    "quadrakill": 1.00,
    "double": 0.90,
    "outplay": 1.30,
}

_DIRECTIVE_CACHE = {"timestamp": 0.0, "data": None}


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


def _load_published_history() -> List[Dict[str, Any]]:
    """Wczytuje lokalną historię publikacji z published_videos.jsonl (ostatnie 500 wpisów)."""
    history = []
    if PUB_LOG_FILE.exists():
        try:
            with open(PUB_LOG_FILE, "r", encoding="utf-8") as f:
                raw_lines = [l for l in f if l.strip()]
            for line in raw_lines[-500:]:
                try:
                    history.append(json.loads(line.strip()))
                except Exception:
                    pass
        except Exception as e:
            print(f"[Learning] Warning reading published_videos.jsonl: {e}")
    return history


def get_learning_directive(max_age_sec: float = 300.0) -> Dict[str, Any]:
    """Zwraca aktywną dyrektywę adaptacyjną (z cache lub z dysku)."""
    global _DIRECTIVE_CACHE
    now = time.time()
    if _DIRECTIVE_CACHE["data"] and (now - _DIRECTIVE_CACHE["timestamp"] < max_age_sec):
        return _DIRECTIVE_CACHE["data"]

    if DIRECTIVE_FILE.exists():
        try:
            with open(DIRECTIVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _DIRECTIVE_CACHE["timestamp"] = now
                _DIRECTIVE_CACHE["data"] = data
                return data
        except Exception as e:
            print(f"[Learning] Błąd odczytu learning_directive.json: {e}")

    # Domyślna dyrektywa startowa
    default_directive = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_videos_analyzed": 0,
        "channel_avg_views": 0,
        "channel_avg_engagement_rate": 0.0,
        "top_action_type": "solo_bolo",
        "action_weights": DEFAULT_ACTION_WEIGHTS.copy(),
        "action_stats": {},
        "duration_analysis": {
            "best_bucket": "short_10_13s",
            "viral_avg_duration_s": 12.5,
            "viral_count": 0,
            "bucket_stats": {},
        },
        "retention_analysis": {
            "total_curves_analyzed": 0,
            "channel_avg_swiped_away_pct": 12.0,
            "channel_avg_hook_retention_pct": 88.0,
            "channel_avg_view_pct": 102.2,
        },
        "top_title_structure": "EGO_CHECK",
        "title_structure_stats": {},
        "winning_keywords": ["SOLO BOLO", "DISRESPECT", "CLEAN", "1v1", "1% HP", "RAMPAGE"],
        "avoid_keywords": ["LATE GAME", "TRIED TO"],
        "top_viral_titles": [],
        "recommended_pacing": "aggressive",
        "evaluator_config": {
            "base_kill_weights": {
                "PENTAKILL": 60.0,
                "QUADRAKILL": 60.0,
                "TRIPLE KILL": 50.0,
                "DOUBLE KILL": 30.0,
                "SOLO BOLO": 90.0,
                "OUTPLAY": 75.0,
                "CLUTCH": 80.0,
                "KILL": 10.0,
            },
            "action_multipliers": DEFAULT_ACTION_WEIGHTS.copy(),
            "demoted_formats": ["pentakill", "quadrakill"],
            "demoted_penalty_points": 12.0,
            "s_tier_min": 82.0,
            "a_tier_min": 68.0,
            "b_tier_min": 50.0,
        },
        "insights": ["Inicjalna dyrektywa adaptacyjna: faworyzowanie formatów SOLO BOLO i OUTPLAY."],
    }
    return default_directive


def get_action_weight(action_type: str) -> float:
    """Zwraca adaptacyjny mnożnik wagi dla danego typu akcji (domyślnie 1.0)."""
    directive = get_learning_directive()
    weights = directive.get("action_weights", DEFAULT_ACTION_WEIGHTS)
    act = (action_type or "outplay").lower().strip()
    return float(weights.get(act, weights.get("outplay", 1.0)))


def get_evaluator_tuning_config() -> Dict[str, Any]:
    """Zwraca aktywną konfigurację auto-tuningu ewaluatora."""
    directive = get_learning_directive()
    return directive.get("evaluator_config", {
        "base_kill_weights": {
            "PENTAKILL": 60.0,
            "QUADRAKILL": 60.0,
            "TRIPLE KILL": 50.0,
            "DOUBLE KILL": 30.0,
            "SOLO BOLO": 90.0,
            "OUTPLAY": 75.0,
            "CLUTCH": 80.0,
            "KILL": 10.0,
        },
        "action_multipliers": DEFAULT_ACTION_WEIGHTS.copy(),
        "demoted_formats": ["pentakill"],
        "demoted_penalty_points": 12.0,
        "s_tier_min": 82.0,
        "a_tier_min": 68.0,
        "b_tier_min": 50.0,
    })


def classify_title_structure(title: str) -> str:
    """Klasyfikuje tytuł do jednej z viralowych struktur."""
    t_up = (title or "").upper()
    if any(k in t_up for k in ["SOLO BOLO", "1V1", "DISRESPECT", "SCHOOLED", "DUEL"]):
        return "DISRESPECT_1V1"
    if any(k in t_up for k in ["1% HP", "1 HP", "1% ", "SURVIVING ON", "MIRACLE", "TURNAROUND"]):
        return "CLUTCH_1HP"
    if any(k in t_up for k in ["THEY THOUGHT", "THEY TRIED", "BAD IDEA", "THEY CORNERED", "GUESS AGAIN", "REGRET"]):
        return "EGO_CHECK"
    if any(k in t_up for k in ["PENTAKILL", "FIVE KILLS", "RAMPAGE", "FRENZY", "ENTIRE TEAM", "IN SECONDS"]):
        return "RAMPAGE"
    if "?" in title or any(t_up.startswith(k) for k in ["DID YOU", "HOW DID", "WHY", "CAN YOU", "HAVE YOU"]):
        return "QUESTION"
    return "CLEAN_OUTPLAY"


def correlate_viral_duration_and_pacing(
    viral_videos: List[Dict[str, Any]],
    all_videos: List[Dict[str, Any]],
    avg_views: float
) -> Dict[str, Any]:
    """
    KROK 1: Closed Pacing Loop
    Koreluje czas trwania i dynamikę filmów z grupy viral_hit.
    Wylicza optymalny profil pacingu i parametry montażu.
    """
    buckets = {
        "short_10_13s": {"min": 0.0, "max": 13.5, "videos": []},
        "balanced_14_17s": {"min": 13.5, "max": 17.5, "videos": []},
        "cinematic_18_25s": {"min": 17.5, "max": 999.0, "videos": []},
    }

    # Użyj filmów viral_hit (lub top 35% jeśli próba mała)
    sample_videos = viral_videos if len(viral_videos) >= 2 else sorted(all_videos, key=lambda x: x.get("views", 0), reverse=True)[:max(3, len(all_videos)//3)]

    for v in sample_videos:
        dur = float(v.get("duration_s", 0.0) or 0.0)
        if dur <= 0.0:
            # Szacuj na podstawie typu akcji jeśli brak duration_s
            act = str(v.get("action_type") or v.get("frag_type") or "").lower()
            dur = 12.0 if act in ("solo_bolo", "clutch") else 15.0

        for b_name, b_data in buckets.items():
            if b_data["min"] <= dur < b_data["max"]:
                b_data["videos"].append(v)
                break

    bucket_stats = {}
    best_bucket = "short_10_13s"
    best_score = -1.0

    for b_name, b_data in buckets.items():
        vids = b_data["videos"]
        count = len(vids)
        if count > 0:
            b_avg_views = sum(v.get("views", 0) for v in vids) / count
            b_avg_eng = sum(v.get("engagement_rate", 0.0) for v in vids) / count
            b_dur_avg = sum(v.get("duration_s", 13.0) or 13.0 for v in vids) / count
            score = (b_avg_views / (avg_views or 1.0)) * (1.0 + (b_avg_eng / 10.0))
        else:
            b_avg_views = 0
            b_avg_eng = 0.0
            b_dur_avg = 13.0
            score = 0.0

        bucket_stats[b_name] = {
            "count": count,
            "avg_views": round(b_avg_views, 1),
            "avg_engagement_rate": round(b_avg_eng, 2),
            "avg_duration_s": round(b_dur_avg, 1),
            "composite_score": round(score, 2),
        }

        if score > best_score and count >= 1:
            best_score = score
            best_bucket = b_name

    # Wyznacz rekomendowany profil pacingu i parametry montażu
    if best_bucket == "short_10_13s":
        rec_pacing = "aggressive"
        zoom_aggression = 1.30
        slowmo_duration = 0.9
        music_balance = 0.60
        game_sound_balance = 0.85
        title_tone = "hype"
        user_notes = "Auto-AI Closed Pacing Loop: Ekstremalnie Szybkie (10-13s) — najwyższa retencja kanału. Natychmiastowy hook 0.8s, zoom-punch 1.30x i dynamiczne zwolnienie 0.9s."
    elif best_bucket == "balanced_14_17s":
        rec_pacing = "balanced"
        zoom_aggression = 1.20
        slowmo_duration = 1.4
        music_balance = 0.55
        game_sound_balance = 0.85
        title_tone = "narrative"
        user_notes = "Auto-AI Closed Pacing Loop: Zbalansowane (14-17s) — optymalny buildup 1.8s pod teamfighty, zoom 1.20x i zwolnienie 1.4s."
    else:
        rec_pacing = "cinematic"
        zoom_aggression = 1.10
        slowmo_duration = 2.0
        music_balance = 0.45
        game_sound_balance = 0.90
        title_tone = "narrative"
        user_notes = "Auto-AI Closed Pacing Loop: Cinematic Outplay (18-25s) — dłuższy buildup i pełny kontekst pojedynku."

    viral_dur_list = [float(v.get("duration_s", 0.0) or 13.0) for v in sample_videos if v.get("duration_s")]
    viral_avg_dur = round(sum(viral_dur_list) / len(viral_dur_list), 1) if viral_dur_list else 12.5

    return {
        "best_bucket": best_bucket,
        "viral_avg_duration_s": viral_avg_dur,
        "viral_count": len(sample_videos),
        "recommended_pacing": rec_pacing,
        "zoom_aggression": zoom_aggression,
        "slowmo_duration": slowmo_duration,
        "music_balance": music_balance,
        "game_sound_balance": game_sound_balance,
        "title_tone": title_tone,
        "user_notes": user_notes,
        "bucket_stats": bucket_stats,
    }


def run_channel_learning_cycle(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Główna pętla samouczenia kanału:
    1. Pobiera statystyki z YouTube (views, likes, comments, duration_s) i łączy z lokalną historią.
    2. KROK 1: Analizuje kohortę viral_hit i dokonuje auto-tuningu tuning_config.json (Closed Pacing Loop).
    3. KROK 2: Klasyfikuje struktury tytułów i wyciąga wygrywające wzorce CTR do wstrzykiwania do promptu Gemini.
    4. KROK 3: Wylicza adaptacyjne wagi dla evaluator.py premiując najlepiej konwertujące formaty.
    5. Zapisuje zaktualizowaną dyrektywę adaptacyjną (learning_directive.json).
    """
    try:
        from lol_agent.api.youtube_uploader import get_channel_videos_and_performance, infer_frag_type_from_title
    except ImportError:
        try:
            from api.youtube_uploader import get_channel_videos_and_performance, infer_frag_type_from_title
        except ImportError:
            return {"status": "error", "message": "Brak modułu youtube_uploader"}

    yt_data = get_channel_videos_and_performance(max_results=50, force_refresh=force_refresh)
    published_yt = yt_data.get("published", [])
    local_history = _load_published_history()

    # Zbuduj słownik filmów po ID
    videos_by_id: Dict[str, Dict[str, Any]] = {}
    for item in published_yt:
        vid = item.get("video_id")
        if vid:
            videos_by_id[vid] = item

    # Uzupełnij metadane z lokalnej historii
    for loc in local_history:
        vid = loc.get("video_id")
        if vid and vid in videos_by_id:
            if loc.get("action_type"):
                videos_by_id[vid]["action_type"] = loc["action_type"]
            if loc.get("champion"):
                videos_by_id[vid]["champion"] = loc["champion"]

    all_analyzed = list(videos_by_id.values())
    total_count = len(all_analyzed)

    if total_count == 0:
        return {
            "status": "warning",
            "message": "Brak opublikowanych filmów do analizy na kanale.",
            "directive": get_learning_directive(),
        }

    # 1. Średnia wyświetleń i zaangażowania kanału
    views_list = [v.get("views", 0) for v in all_analyzed if v.get("views") is not None]
    avg_views = (sum(views_list) / len(views_list)) if views_list else 1.0

    eng_list = [v.get("engagement_rate", 0.0) for v in all_analyzed if v.get("engagement_rate") is not None]
    avg_eng = (sum(eng_list) / len(eng_list)) if eng_list else 0.0

    # 2. Agregacja per typ akcji (views + engagement)
    action_groups: Dict[str, List[Dict[str, Any]]] = {}
    for v in all_analyzed:
        act = v.get("action_type") or v.get("frag_type") or infer_frag_type_from_title(v.get("title", ""))
        act = act.lower().strip()
        if act not in action_groups:
            action_groups[act] = []
        action_groups[act].append(v)

    action_stats = {}
    action_weights = DEFAULT_ACTION_WEIGHTS.copy()
    base_kill_weights = {
        "PENTAKILL": 60.0,
        "QUADRAKILL": 60.0,
        "TRIPLE KILL": 50.0,
        "DOUBLE KILL": 30.0,
        "SOLO BOLO": 90.0,
        "OUTPLAY": 75.0,
        "CLUTCH": 80.0,
        "KILL": 10.0,
    }

    demoted_formats = []

    for act, vids in action_groups.items():
        vws = [v.get("views", 0) for v in vids]
        act_avg = sum(vws) / len(vws) if vws else 0
        ratio = (act_avg / avg_views) if avg_views > 0 else 1.0

        engs = [v.get("engagement_rate", 0.0) for v in vids]
        act_eng = sum(engs) / len(engs) if engs else 0.0

        # Waga łączona: 75% views ratio + 25% engagement boost
        eng_factor = 1.0 + min(0.3, max(-0.3, (act_eng - avg_eng) / (avg_eng or 1.0) * 0.2)) if avg_eng > 0 else 1.0
        combined_w = round(ratio * eng_factor, 2)
        w = max(0.4, min(2.2, combined_w))
        action_weights[act] = w

        # Democja: wymagana próbka N >= 3, by uniknąć fałszywych wniosków przy małej próbie.
        # Pentakill i Quadrakill są z natury top contentem — democja z powodu słabych tytułów z przeszłości jest zablokowana.
        _NEVER_DEMOTE_ACTIONS = {"pentakill", "quadrakill"}
        if ratio < 0.75 and len(vids) >= 3 and act.lower() not in _NEVER_DEMOTE_ACTIONS:
            demoted_formats.append(act)

        action_stats[act] = {
            "count": len(vids),
            "avg_views": round(act_avg, 1),
            "performance_ratio": round(ratio, 2),
            "avg_engagement_rate": round(act_eng, 2),
            "weight": w,
        }

    # Dostosuj base_kill_weights dla ewaluatora (Krok 3)
    penta_ratio = action_stats.get("pentakill", {}).get("performance_ratio", 0.5)
    solo_ratio = action_stats.get("solo_bolo", {}).get("performance_ratio", 1.3)
    outplay_ratio = action_stats.get("outplay", {}).get("performance_ratio", 1.2)
    quadra_ratio = action_stats.get("quadrakill", {}).get("performance_ratio", 0.6)
    triple_ratio = action_stats.get("triple", {}).get("performance_ratio", 1.0)
    double_ratio = action_stats.get("double", {}).get("performance_ratio", 0.8)

    base_kill_weights["SOLO BOLO"] = round(min(100.0, max(75.0, 75.0 * solo_ratio)), 1)
    base_kill_weights["OUTPLAY"] = round(min(90.0, max(50.0, 65.0 * outplay_ratio)), 1)
    base_kill_weights["PENTAKILL"] = round(min(100.0, max(35.0, 100.0 * penta_ratio)), 1)
    base_kill_weights["QUADRAKILL"] = round(min(85.0, max(30.0, 75.0 * quadra_ratio)), 1)
    base_kill_weights["TRIPLE KILL"] = round(min(70.0, max(30.0, 50.0 * triple_ratio)), 1)
    base_kill_weights["DOUBLE KILL"] = round(min(50.0, max(20.0, 25.0 * double_ratio)), 1)

    # Najlepszy format akcji (wymaga N >= 2 filmów dla stabilności wnioskowania)
    qualified_actions = [
        (act, data["performance_ratio"])
        for act, data in action_stats.items()
        if data["count"] >= 2
    ]
    if not qualified_actions:
        qualified_actions = [
            (act, data["performance_ratio"])
            for act, data in action_stats.items()
            if data["count"] >= 1
        ]
    top_action = max(qualified_actions, key=lambda x: x[1])[0] if qualified_actions else "solo_bolo"

    # 3. KROK 1: Closed Pacing Loop (Korelacja kohorty viral_hit)
    viral_cohort = [
        v for v in all_analyzed
        if v.get("performance_tier") == "viral_hit" or (v.get("views", 0) >= 1.25 * avg_views)
    ]
    pacing_analysis = correlate_viral_duration_and_pacing(viral_cohort, all_analyzed, avg_views)
    rec_pacing = pacing_analysis["recommended_pacing"]

    # 4. KROK 2: Analiza struktur tytułów i wzorców CTR
    structure_groups: Dict[str, List[float]] = {}
    for v in all_analyzed:
        st = classify_title_structure(v.get("title", ""))
        vw = v.get("views", 0)
        ratio = (vw / avg_views) if avg_views > 0 else 1.0
        if st not in structure_groups:
            structure_groups[st] = []
        structure_groups[st].append(ratio)

    title_structure_stats = {}
    for st, ratios in structure_groups.items():
        title_structure_stats[st] = {
            "count": len(ratios),
            "avg_ratio": round(sum(ratios) / len(ratios), 2),
        }

    top_structure = max(
        title_structure_stats.items(),
        key=lambda x: (x[1]["avg_ratio"], x[1]["count"])
    )[0] if title_structure_stats else "EGO_CHECK"

    # Słowa kluczowe
    word_perf: Dict[str, List[float]] = {}
    # Słowa śmieciowe — hashtagi, stopwords i nazwy championów nie są sygnałem CTR
    _JUNK_KW = {
        "SHORTS", "LEAGUEOFLEGENDS", "LOL", "RIOTGAMES", "GAMING", "LEAGUE",
        "HIGHLIGHTS", "GAMES", "CLIP", "THE", "AND", "FOR", "THIS", "THEY",
        "THAT", "KATARINA", "WITH", "YOU", "HAVE", "ARE", "WAS", "WERE",
        "NOT", "THEIR", "INTO", "BEEN", "FROM", "MORE", "OUT", "ALL",
    }

    for v in all_analyzed:
        title = v.get("title", "")
        vw = v.get("views", 0)
        ratio = (vw / avg_views) if avg_views > 0 else 1.0
        clean_words = re.findall(r"\b[A-Za-z0-9%]{3,}\b", title.upper())
        for w_str in set(clean_words):
            if w_str in _JUNK_KW:
                continue
            if w_str not in word_perf:
                word_perf[w_str] = []
            word_perf[w_str].append(ratio)


    winning_words = []
    avoid_words = []
    for w_str, ratios in word_perf.items():
        if len(ratios) >= 2:
            avg_r = sum(ratios) / len(ratios)
            if avg_r >= 1.15:
                winning_words.append((w_str, round(avg_r, 2)))
            elif avg_r <= 0.80:
                avoid_words.append((w_str, round(avg_r, 2)))

    winning_words.sort(key=lambda x: x[1], reverse=True)
    avoid_words.sort(key=lambda x: x[1])

    winning_keywords = [w[0] for w in winning_words[:8]] or ["SOLO BOLO", "DISRESPECT", "CLEAN", "1v1", "1% HP", "RAMPAGE"]
    avoid_keywords = [w[0] for w in avoid_words[:5]] or ["LATE GAME", "TRIED TO"]

    # Wczytaj korekty tytułów z pętli user_feedback_history (POST /learning/correction)
    try:
        _mem_file = LEARNING_DIR / "user_feedback_history.json"
        if _mem_file.exists():
            with open(_mem_file, "r", encoding="utf-8") as _mf:
                _mem = json.load(_mf)
            _user_avoid: set = set()
            for _entry in _mem.get("history", []):
                if _entry.get("param") == "title" and _entry.get("old_value"):
                    _words = re.findall(r"\b[A-Za-z0-9]{4,}\b", str(_entry["old_value"]).upper())
                    _user_avoid.update(w for w in _words if w not in _JUNK_KW)
            _extra = [w for w in sorted(_user_avoid) if w not in avoid_keywords][:3]
            if _extra:
                avoid_keywords = (avoid_keywords + _extra)[:8]
                _safe_print(f"[Learning] [USER_CORR] Korekty tytułów użytkownika → avoid+{_extra}")
    except Exception as _ue:
        _safe_print(f"[Learning] [WARN] Błąd wczytania korekt tytułów: {_ue}")

    # Top 5 realnych viralowych tytułów z kanału
    sorted_by_views = sorted(all_analyzed, key=lambda x: x.get("views", 0), reverse=True)
    top_viral_titles = [v.get("title") for v in sorted_by_views[:5] if v.get("title")]

    # 5. KROK 3: Evaluator Auto-Tuning Configuration
    evaluator_config = {
        "base_kill_weights": base_kill_weights,
        "action_multipliers": action_weights,
        "demoted_formats": demoted_formats,
        "demoted_penalty_points": 12.0,  # formaty o słabym CTR wymagają +12 pkt wyższego score'a
        "s_tier_min": 82.0,
        "a_tier_min": 68.0,
        "b_tier_min": 50.0,
        "top_action_type": top_action,
    }

    # 6. KROK 4: YouTube Analytics API (Retencja i Swiped Away)
    retention_summary = {}
    try:
        from lol_agent.api.youtube_analytics import fetch_channel_retention_overview
        retention_summary = fetch_channel_retention_overview(max_videos=20)
    except Exception:
        try:
            from api.youtube_analytics import fetch_channel_retention_overview
            retention_summary = fetch_channel_retention_overview(max_videos=20)
        except Exception:
            pass

    ret_insight = (
        f"YouTube Analytics API: {retention_summary.get('total_curves_analyzed', 0)} filmów z pełną krzywą retencji. Średni Swiped Away: {retention_summary.get('channel_avg_swiped_away_pct', 12.0)}%, AVD: {retention_summary.get('channel_avg_view_pct', 102.2)}%."
        if retention_summary.get("status") == "success"
        else "YouTube Analytics API: Oczekiwanie na agregację krzywych retencji."
    )

    insights = [
        f"Przeanalizowano {total_count} opublikowanych filmów. Średnia kanału: {int(avg_views)} views (eng: {avg_eng:.1f}%).",
        f"Format o najwyższym współczynniku widowni: {top_action.upper()} ({action_stats.get(top_action, {}).get('performance_ratio', 1.0)}x średniej).",
        f"Closed Pacing Loop: Kohorta viral_hit ({pacing_analysis['viral_count']} filmów) faworyzuje bucket '{pacing_analysis['best_bucket']}' (śr. {pacing_analysis['viral_avg_duration_s']}s). Profil: '{rec_pacing}'.",
        f"Title Reinforcement: Najlepiej konwertująca struktura tytułów: {top_structure}. Słowa CTR: {', '.join(winning_keywords[:4])}.",
        f"Evaluator Auto-Tuning: Solo Bolo wyceniono na {base_kill_weights.get('SOLO BOLO')} pkt, Pentakill na {base_kill_weights.get('PENTAKILL')} pkt. Demoted formats: {', '.join(demoted_formats) or 'brak'}.",
        ret_insight,
    ]

    directive = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_videos_analyzed": total_count,
        "channel_avg_views": round(avg_views, 1),
        "channel_avg_engagement_rate": round(avg_eng, 2),
        "top_action_type": top_action,
        "action_weights": action_weights,
        "action_stats": action_stats,
        "duration_analysis": pacing_analysis,
        "retention_analysis": retention_summary,
        "top_title_structure": top_structure,
        "title_structure_stats": title_structure_stats,
        "winning_keywords": winning_keywords,
        "avoid_keywords": avoid_keywords,
        "top_viral_titles": top_viral_titles,
        "recommended_pacing": rec_pacing,
        "evaluator_config": evaluator_config,
        "insights": insights,
    }

    # Zapisz dyrektywę
    try:
        with open(DIRECTIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(directive, f, indent=2, ensure_ascii=False)
        _safe_print(f"[Learning] [OK] Zaktualizowano dyrektywę adaptacyjną: {DIRECTIVE_FILE.name}")
    except Exception as de:
        _safe_print(f"[Learning] [ERR] Błąd zapisu learning_directive.json: {de}")

    # Aktualizuj cache w pamięci
    global _DIRECTIVE_CACHE
    _DIRECTIVE_CACHE["timestamp"] = time.time()
    _DIRECTIVE_CACHE["data"] = directive

    # KROK 1: Automatyczna modyfikacja tuning_config.json (Closed Pacing Loop)
    try:
        if TUNING_FILE.exists():
            with open(TUNING_FILE, "r", encoding="utf-8") as tf:
                tuning_cfg = json.load(tf)
        else:
            tuning_cfg = {}

        # Aktualizuj parametry z analizy Closed Pacing Loop
        tuning_cfg["pacing"] = rec_pacing
        tuning_cfg["zoomAggression"] = pacing_analysis["zoom_aggression"]
        tuning_cfg["slowmoDuration"] = pacing_analysis["slowmo_duration"]
        tuning_cfg["musicBalance"] = pacing_analysis["music_balance"]
        tuning_cfg["gameSoundBalance"] = pacing_analysis["game_sound_balance"]
        tuning_cfg["titleTone"] = pacing_analysis["title_tone"]
        tuning_cfg["userNotes"] = pacing_analysis["user_notes"]

        with open(TUNING_FILE, "w", encoding="utf-8") as tf:
            json.dump(tuning_cfg, tf, indent=2, ensure_ascii=False)
        _safe_print(f"[Learning] [TUNING] Closed Pacing Loop auto-tuned {TUNING_FILE.name}: pacing={rec_pacing}, zoom={pacing_analysis['zoom_aggression']}x, slowmo={pacing_analysis['slowmo_duration']}s")
    except Exception as te:
        _safe_print(f"[Learning] [WARN] Warning tuning_config update: {te}")

    return {
        "status": "success",
        "directive": directive,
        "insights": insights,
    }


if __name__ == "__main__":
    res = run_channel_learning_cycle(force_refresh=True)
    print("Learning Cycle Result:", json.dumps(res, indent=2, ensure_ascii=False))
