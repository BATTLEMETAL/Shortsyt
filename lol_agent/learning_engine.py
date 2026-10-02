"""
Shortsyt — Channel Autonomous Learning Engine v2
Analizuje realne wyniki opublikowanych filmów z YouTube, wylicza korelacje efektywności formatów
i generuje dynamiczną dyrektywę adaptacyjną (learning_directive.json) dla montażu, ewaluatora i metadanych.

Implementuje:
  1. Closed Pacing Loop: korelacja czasu trwania i dynamiki filmów z grupy viral_hit → auto-tuning tuning_config.json.
  2. Dynamic Prompt / Title Reinforcement: klasyfikacja struktur tytułów i ekstrakcja wzorców CTR dla Gemini.
  3. Evaluator Weight Auto-Tuning: dynamiczne korygowanie wag akcji w evaluator.py na podstawie MEDIANY, nie średniej.
  4. Statistical Safeguards: min-sample guards, outlier filtering, zero-views exclusion, cadence tracking.
  5. Cadence Detector: wykrywa przerwy w regularności publikacji i ostrzega silnik przed degradacją algorytmu.
  6. Nowe zmienne: publication_cadence, title_fatigue, swiped_away_by_action, best_pub_hour, retention_by_duration.
"""
import os
import sys
import re
import json
import math
import time
import statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

LEARNING_DIR = Path(__file__).resolve().parent
DIRECTIVE_FILE = LEARNING_DIR / "learning_directive.json"
TUNING_FILE = LEARNING_DIR / "tuning_config.json"
PUB_LOG_FILE = LEARNING_DIR / "published_videos.jsonl"

# ── Domyślne wagi akcji (startowe — NIGDY poniżej tych wartości bez wystarczającej próbki) ──────
DEFAULT_ACTION_WEIGHTS = {
    "pentakill": 1.0,
    "solo_bolo": 1.35,
    "clutch": 1.20,
    "triple": 1.10,
    "quadrakill": 1.00,
    "double": 0.90,
    "outplay": 1.30,
    "multikill": 1.00,
}

# ── Minimalna próbka wymagana do wyliczenia wiarygodnej wagi ─────────────────────────────────
MIN_SAMPLE_FOR_WEIGHT = 3      # poniżej tej liczby → waga domyślna, bez modyfikacji
MIN_SAMPLE_FOR_DEMOTION = 4    # poniżej → zakaz democji formatu
MIN_SAMPLE_FOR_BUCKET = 3      # poniżej → bucket duration ignorowany dla rekomendacji

# ── Guard: filmy z ≤ threshold wyświetleń są uważane za błędy dystrybucji/testy ────────────
ZERO_VIEWS_THRESHOLD = 50      # < 50 views = prawdopodobnie błąd tech / draft / prywatny

# ── Okno czasowe „świeżych" danych do nauki ─────────────────────────────────────────────────
RECENT_WINDOW_DAYS = 60        # dane starsze niż 60 dni mają obniżoną wagę (×0.5)

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
            _safe_print(f"[Learning] Warning reading published_videos.jsonl: {e}")
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
            _safe_print(f"[Learning] Błąd odczytu learning_directive.json: {e}")

    # Domyślna dyrektywa startowa
    default_directive = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_videos_analyzed": 0,
        "channel_avg_views": 0,
        "channel_median_views": 0,
        "channel_avg_engagement_rate": 0.0,
        "top_action_type": "solo_bolo",
        "action_weights": DEFAULT_ACTION_WEIGHTS.copy(),
        "action_stats": {},
        "duration_analysis": {
            "best_bucket": "balanced_14_17s",
            "viral_avg_duration_s": 14.0,
            "viral_count": 0,
            "bucket_stats": {},
        },
        "retention_analysis": {
            "total_curves_analyzed": 0,
            "channel_avg_swiped_away_pct": 16.0,
            "channel_avg_hook_retention_pct": 84.0,
            "channel_avg_view_pct": 99.0,
        },
        "publication_cadence": {
            "status": "unknown",
            "avg_gap_days": 0.0,
            "max_gap_days": 0.0,
            "gap_warning": False,
            "recommendation": "Brak danych",
        },
        "title_fatigue": {
            "repeated_phrases": [],
            "fatigue_warning": False,
        },
        "top_title_structure": "EGO_CHECK",
        "title_structure_stats": {},
        "winning_keywords": ["SOLO BOLO", "DISRESPECT", "CLEAN", "1v1", "1% HP", "RAMPAGE"],
        "avoid_keywords": ["LATE GAME", "TRIED TO"],
        "top_viral_titles": [],
        "recommended_pacing": "balanced",
        "evaluator_config": {
            "base_kill_weights": {
                "PENTAKILL": 70.0,
                "QUADRAKILL": 60.0,
                "TRIPLE KILL": 50.0,
                "DOUBLE KILL": 30.0,
                "SOLO BOLO": 90.0,
                "OUTPLAY": 75.0,
                "CLUTCH": 80.0,
                "KILL": 10.0,
            },
            "action_multipliers": DEFAULT_ACTION_WEIGHTS.copy(),
            "demoted_formats": [],
            "demoted_penalty_points": 12.0,
            "s_tier_min": 82.0,
            "a_tier_min": 68.0,
            "b_tier_min": 50.0,
        },
        "insights": ["Inicjalna dyrektywa adaptacyjna (brak wystarczającej historii)."],
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
            "PENTAKILL": 70.0,
            "QUADRAKILL": 60.0,
            "TRIPLE KILL": 50.0,
            "DOUBLE KILL": 30.0,
            "SOLO BOLO": 90.0,
            "OUTPLAY": 75.0,
            "CLUTCH": 80.0,
            "KILL": 10.0,
        },
        "action_multipliers": DEFAULT_ACTION_WEIGHTS.copy(),
        "demoted_formats": [],
        "demoted_penalty_points": 12.0,
        "s_tier_min": 82.0,
        "a_tier_min": 68.0,
        "b_tier_min": 50.0,
    })


def classify_title_structure(title: str) -> str:
    """Klasyfikuje tytuł do jednej z viralowych struktur."""
    t_up = (title or "").upper()
    if any(k in t_up for k in ["SOLO BOLO", "1V1", "DISRESPECT", "SCHOOLED", "DUEL", "EGO CHECK"]):
        return "DISRESPECT_1V1"
    if any(k in t_up for k in ["1% HP", "1 HP", "1% ", "SURVIVING ON", "MIRACLE", "TURNAROUND"]):
        return "CLUTCH_1HP"
    if any(k in t_up for k in ["THEY THOUGHT", "THEY TRIED", "BAD IDEA", "THEY CORNERED",
                                 "GUESS AGAIN", "REGRET", "IT WENT WRONG", "WRONG"]):
        return "EGO_CHECK"
    if any(k in t_up for k in ["PENTAKILL", "FIVE KILLS", "RAMPAGE", "FRENZY",
                                 "ENTIRE TEAM", "IN SECONDS", "CLEAN OR LUCK"]):
        return "RAMPAGE"
    if "?" in title or any(t_up.startswith(k) for k in ["DID YOU", "HOW DID", "WHY", "CAN YOU", "HAVE YOU"]):
        return "QUESTION"
    return "CLEAN_OUTPLAY"


# ─────────────────────────────────────────────────────────────────────────────────────────────
# NOWE ANALIZY
# ─────────────────────────────────────────────────────────────────────────────────────────────

def _extract_video_datetime(v: Dict[str, Any]) -> Optional[datetime]:
    """Ekstrahuje obiekt datetime niezależnie od źródła rekordu (API, cache, jsonl)."""
    pub_raw = (
        v.get("datetime_utc") or
        v.get("published_at") or
        v.get("timestamp") or
        v.get("publish_at") or
        ""
    )
    if not pub_raw and v.get("date") and v.get("time"):
        pub_raw = f"{v.get('date')}T{v.get('time')}:00"
    if pub_raw:
        try:
            clean = str(pub_raw).replace("Z", "+00:00")
            if "+" not in clean and "-" not in clean[10:]:
                clean += "+00:00"
            return datetime.fromisoformat(clean)
        except Exception:
            try:
                return datetime.strptime(str(pub_raw)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _detect_publication_cadence(all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Nowa zmienna: Wykrywa regularność publikacji i ostrzega przed degradacją algorytmu.
    Gap > 3 dni = algorytm YouTube obniża seed shelf (gwarantowaną pulę testową).
    """
    dates = []
    for v in all_videos:
        dt = _extract_video_datetime(v)
        if dt:
            dates.append(dt)

    if len(dates) < 2:
        return {
            "status": "insufficient_data",
            "avg_gap_days": 0.0,
            "max_gap_days": 0.0,
            "gap_warning": False,
            "recommendation": "Za mało danych do analizy rytmu.",
        }

    dates.sort()
    gaps = [(dates[i + 1] - dates[i]).total_seconds() / 86400 for i in range(len(dates) - 1)]

    # Ogranicz do ostatnich 20 przerw (aktualne zachowanie, nie historyczne)
    recent_gaps = gaps[-20:] if len(gaps) >= 20 else gaps
    avg_gap = round(statistics.mean(recent_gaps), 2)
    max_gap = round(max(recent_gaps), 2)
    med_gap = round(statistics.median(recent_gaps), 2)

    # Wzorzec tygodniowy: ile dni tygodnia ma przynajmniej 1 film
    pub_weekdays = [d.weekday() for d in dates[-30:]]  # ostatnie 30 filmów
    unique_weekdays = len(set(pub_weekdays))

    # Ocena regularności
    if avg_gap <= 1.2:
        status = "excellent"
        rec = "Rytm codzienny — optymalny. Algorytm YouTube przyznaje pełną pulę testową (~2500 impr/film)."
    elif avg_gap <= 2.5:
        status = "good"
        rec = f"Rytm co {avg_gap:.1f}d — dobry. Publikuj regularnie, unikaj przerw > 3 dni."
    elif avg_gap <= 4.0:
        status = "degraded"
        rec = f"UWAGA: Rytm co {avg_gap:.1f}d — algorytm zaczyna obniżać seed shelf. Wróć do max. 2-dniowego rytmu."
    else:
        status = "critical"
        rec = f"KRYTYCZNE: Przerwa śr. {avg_gap:.1f}d — algorytm YouTube traktuje kanał jako uśpiony. Pilnie wrócić do regularnych publikacji!"

    gap_warning = avg_gap > 3.0 or max_gap > 7.0

    return {
        "status": status,
        "avg_gap_days": avg_gap,
        "median_gap_days": med_gap,
        "max_gap_days": max_gap,
        "gap_warning": gap_warning,
        "unique_weekdays_active": unique_weekdays,
        "recommendation": rec,
    }


def _detect_title_fatigue(all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Nowa zmienna: Wykrywa zmęczenie materiałowe (tytuły zaczynające się tak samo).
    Algorytm YouTube traktuje powtarzalność tytułów jako niskiej jakości content farm.
    """
    def _sort_ts(v: Dict[str, Any]) -> float:
        dt = _extract_video_datetime(v)
        return dt.timestamp() if dt else 0.0

    recent = sorted(all_videos, key=_sort_ts, reverse=True)[:20]
    fingerprints: Dict[str, List[str]] = defaultdict(list)
    for v in recent:
        title = (v.get("title") or "").strip()
        clean = re.sub(r'[^\w\s]', '', title).strip()
        words = clean.split()
        if len(words) >= 3:
            fp = " ".join(w.lower() for w in words[:3])
            fingerprints[fp].append(title)

    repeated = {fp: titles for fp, titles in fingerprints.items() if len(titles) >= 2}

    fatigue_impact = []
    for fp, titles in repeated.items():
        vids_with_fp = [v for v in recent if v.get("title", "").lower().startswith(fp.split()[0])]
        if vids_with_fp:
            views_fp = [v.get("views", 0) for v in vids_with_fp]
            avg_fp = statistics.mean(views_fp) if views_fp else 0
            fatigue_impact.append({"phrase": fp, "count": len(titles), "avg_views": round(avg_fp)})

    fatigue_warning = len(repeated) >= 2

    return {
        "repeated_phrases": fatigue_impact,
        "unique_repeated_count": len(repeated),
        "fatigue_warning": fatigue_warning,
        "recommendation": (
            "UWAGA: Wykryto powtarzające się frazy w ostatnich tytułach. Algorytm YouTube penalizuje powtarzalność!"
            if fatigue_warning else "Tytuły mają dobrą różnorodność."
        ),
    }


def _analyze_best_pub_hour(all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Nowa zmienna: Wyznacza najlepszą godzinę i dzień tygodnia publikacji na podstawie
    wyświetleń (mediana per godzina/dzień publikacji). Min 2 próbki na slot.
    """
    hour_views: Dict[int, List[int]] = defaultdict(list)
    weekday_views: Dict[int, List[int]] = defaultdict(list)
    weekday_names = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]

    for v in all_videos:
        views = int(v.get("views", 0) or 0)
        if views < ZERO_VIEWS_THRESHOLD:
            continue
        dt = _extract_video_datetime(v)
        if dt:
            hour_views[dt.hour].append(views)
            weekday_views[dt.weekday()].append(views)

    best_hour = None
    best_hour_avg = 0
    hour_stats = {}
    for hour, vws in hour_views.items():
        if len(vws) >= 2:
            avg = statistics.median(vws)
            hour_stats[hour] = {"count": len(vws), "median_views": round(avg)}
            if avg > best_hour_avg:
                best_hour_avg = avg
                best_hour = hour

    best_weekday = None
    best_weekday_avg = 0
    weekday_stats = {}
    for wd, vws in weekday_views.items():
        if len(vws) >= 2:
            avg = statistics.median(vws)
            weekday_stats[weekday_names[wd]] = {"count": len(vws), "median_views": round(avg)}
            if avg > best_weekday_avg:
                best_weekday_avg = avg
                best_weekday = weekday_names[wd]

    return {
        "best_hour_utc": best_hour,
        "best_weekday": best_weekday,
        "hour_stats": hour_stats,
        "weekday_stats": weekday_stats,
        "note": "Mediana wyświetleń per godzina/dzień publikacji. Min 2 próbki na slot.",
    }


def _analyze_retention_by_action(retention_summary: Dict[str, Any], all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Nowa zmienna: Swiped Away rate per typ akcji.
    Pozwala wykryć czy np. double kill jest swipowany szybciej niż solo bolo.
    """
    if not retention_summary.get("videos"):
        return {"status": "no_data", "by_action": {}}

    action_retention: Dict[str, List[float]] = defaultdict(list)
    action_swiped: Dict[str, List[float]] = defaultdict(list)

    for ret_v in retention_summary.get("videos", []):
        vid_id = ret_v.get("video_id")
        swiped = ret_v.get("swiped_away_pct")
        if swiped is None:
            continue

        # Znajdź action_type dla tego video_id
        matched = next((v for v in all_videos if v.get("video_id") == vid_id), None)
        act = (matched.get("action_type") if matched else None) or "unknown"
        action_swiped[act].append(float(swiped))
        hook_ret = ret_v.get("hook_retention_pct")
        if hook_ret is not None:
            action_retention[act].append(float(hook_ret))

    by_action = {}
    for act in set(list(action_swiped.keys()) + list(action_retention.keys())):
        sw = action_swiped.get(act, [])
        hr = action_retention.get(act, [])
        by_action[act] = {
            "count": max(len(sw), len(hr)),
            "avg_swiped_away_pct": round(statistics.mean(sw), 1) if sw else None,
            "avg_hook_retention_pct": round(statistics.mean(hr), 1) if hr else None,
        }

    return {"status": "ok", "by_action": by_action}


def analyze_ab_title_experiments(all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Task C4: A/B Title Testing & CTR Performance Analyzer.
    Analizuje opublikowane filmy pod kątem wariantów tytułów (A vs B) oraz porównuje
    średnie wyświetlenia i retencję między różnymi strukturami tytułów (EGO_CHECK, QUESTION, CLUTCH_1HP itp.).
    """
    experiments = []
    structure_performance: Dict[str, List[int]] = defaultdict(list)

    for v in all_videos:
        views = int(v.get("views", 0) or 0)
        if views < ZERO_VIEWS_THRESHOLD:
            continue
        title = v.get("title", "")
        struct = classify_title_structure(title)
        structure_performance[struct].append(views)

        variant_b = v.get("title_variant_b")
        active_variant = v.get("active_variant", "A")
        if variant_b:
            experiments.append({
                "video_id": v.get("video_id"),
                "active_variant": active_variant,
                "title_a": title if active_variant == "A" else v.get("title_variant_a", title),
                "title_b": variant_b,
                "views": views,
                "structure": struct,
            })

    struct_stats = {}
    for struct, views_list in structure_performance.items():
        if len(views_list) >= 2:
            struct_stats[struct] = {
                "count": len(views_list),
                "median_views": round(statistics.median(views_list)),
                "avg_views": round(statistics.mean(views_list)),
            }

    best_struct = max(struct_stats.items(), key=lambda x: x[1]["median_views"])[0] if struct_stats else "CLEAN_OUTPLAY"

    return {
        "status": "active" if experiments else "structure_benchmark_ready",
        "tracked_ab_experiments": len(experiments),
        "experiments": experiments[-10:],
        "title_structure_benchmark": struct_stats,
        "winning_title_structure": best_struct,
        "recommendation": f"Najwyższy medianowy CTR osiąga struktura '{best_struct}'. Używaj jej jako wariantu A.",
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# POPRAWIONE ALGORYTMY WAG (MEDIANA + OUTLIER FILTER + RECENCY WEIGHTING)
# ─────────────────────────────────────────────────────────────────────────────────────────────

def _compute_robust_metric(views_list: List[int], pub_dates: Optional[List[str]] = None) -> Dict[str, float]:
    """
    Wylicza odporną statystykę z listy wyświetleń:
    - Filtruje zera/niedystrybucje (< ZERO_VIEWS_THRESHOLD)
    - Używa MEDIANY jako miary centralnej (odporna na viral outliers)
    - Opcjonalnie stosuje wagi recency (nowsze filmy ważniejsze)
    - Zwraca: median, mean, trimmed_mean (bez top/bot 10%), count_valid
    """
    now = datetime.now(timezone.utc)
    weighted = []

    for i, v in enumerate(views_list):
        if v < ZERO_VIEWS_THRESHOLD:
            continue  # zero / błąd dystrybucji — odrzucamy
        weight = 1.0
        if pub_dates and i < len(pub_dates):
            try:
                dt = datetime.fromisoformat((pub_dates[i] or "").replace("Z", "+00:00"))
                age_days = (now - dt).days
                # Filmy starsze niż RECENT_WINDOW_DAYS mają wagę 0.5
                weight = 0.5 if age_days > RECENT_WINDOW_DAYS else 1.0
            except Exception:
                pass
        weighted.append((v, weight))

    if not weighted:
        return {"median": 0.0, "mean": 0.0, "trimmed_mean": 0.0, "count_valid": 0}

    vals = [v for v, w in weighted]
    med = statistics.median(vals)

    # Ważona średnia (uwzględnia recency)
    total_w = sum(w for _, w in weighted)
    w_mean = sum(v * w for v, w in weighted) / total_w if total_w > 0 else 0.0

    # Trimmed mean: usuń top 10% i bottom 10%
    n = len(vals)
    trim = max(1, int(n * 0.10))
    trimmed = sorted(vals)[trim: n - trim] if n > 2 else vals
    t_mean = statistics.mean(trimmed) if trimmed else w_mean

    return {
        "median": round(med, 1),
        "mean": round(w_mean, 1),
        "trimmed_mean": round(t_mean, 1),
        "count_valid": len(vals),
    }


def correlate_viral_duration_and_pacing(
    viral_videos: List[Dict[str, Any]],
    all_videos: List[Dict[str, Any]],
    channel_median: float,
) -> Dict[str, Any]:
    """
    KROK 1: Closed Pacing Loop
    Koreluje czas trwania filmów z grupy viral_hit z wynikami.
    POPRAWKA: Używa MEDIANY kanału jako baseline i wymaga MIN_SAMPLE_FOR_BUCKET.
    """
    buckets = {
        "short_10_13s":    {"min": 0.0,  "max": 13.5, "videos": []},
        "balanced_14_17s": {"min": 13.5, "max": 17.5, "videos": []},
        "cinematic_18_25s":{"min": 17.5, "max": 999.0, "videos": []},
    }

    # Odrzuć filmy bez duration_s lub z zerowymi wyświetleniami
    valid_videos = [
        v for v in all_videos
        if int(v.get("views", 0) or 0) >= ZERO_VIEWS_THRESHOLD
    ]

    # Użyj viral_hit lub top 35% jeśli próba viral mała
    sample_videos = viral_videos if len(viral_videos) >= 2 else sorted(
        valid_videos, key=lambda x: x.get("views", 0), reverse=True
    )[:max(3, len(valid_videos) // 3)]

    for v in sample_videos:
        dur = float(v.get("duration_s", 0.0) or 0.0)
        if dur <= 0.0:
            act = str(v.get("action_type") or "").lower()
            dur = 12.0 if act in ("solo_bolo", "clutch") else 15.0
        for b_name, b_data in buckets.items():
            if b_data["min"] <= dur < b_data["max"]:
                b_data["videos"].append(v)
                break

    bucket_stats = {}
    # Domyślny bucket = balanced_14_17s (bezpieczniejszy niż short_10_13s przy małej próbie)
    best_bucket = "balanced_14_17s"
    best_score = -1.0

    for b_name, b_data in buckets.items():
        vids = b_data["videos"]
        count = len(vids)
        if count >= MIN_SAMPLE_FOR_BUCKET:
            vws = [int(v.get("views", 0) or 0) for v in vids]
            b_median_views = statistics.median(vws)
            b_avg_eng = statistics.mean([v.get("engagement_rate", 0.0) or 0.0 for v in vids])
            b_dur_avg = statistics.mean([float(v.get("duration_s", 13.0) or 13.0) for v in vids])
            # Score bazuje na MEDIANIE (odporność na viral outliers)
            score = (b_median_views / (channel_median or 1.0)) * (1.0 + b_avg_eng / 10.0)
        elif count > 0:
            vws = [int(v.get("views", 0) or 0) for v in vids]
            b_median_views = statistics.median(vws)
            b_avg_eng = 0.0
            b_dur_avg = 13.0
            score = 0.0  # Za mała próba — nie daje rekomendacji
        else:
            b_median_views = 0
            b_avg_eng = 0.0
            b_dur_avg = 0.0
            score = 0.0

        bucket_stats[b_name] = {
            "count": count,
            "median_views": round(b_median_views, 1) if count > 0 else 0,
            "avg_engagement_rate": round(b_avg_eng, 2),
            "avg_duration_s": round(b_dur_avg, 1),
            "composite_score": round(score, 2),
            "reliable": count >= MIN_SAMPLE_FOR_BUCKET,  # flaga rzetelności
        }

        if score > best_score and count >= MIN_SAMPLE_FOR_BUCKET:
            best_score = score
            best_bucket = b_name

    # Parametry montażu per bucket
    pacing_params = {
        "short_10_13s": {
            "rec_pacing": "aggressive",
            "zoom_aggression": 1.30,
            "slowmo_duration": 0.9,
            "music_balance": 0.60,
            "game_sound_balance": 0.85,
            "title_tone": "hype",
            "user_notes": "Aggressive (10-13s): natychmiastowy hook 0.8s, zoom 1.30x, zwolnienie 0.9s.",
        },
        "balanced_14_17s": {
            "rec_pacing": "balanced",
            "zoom_aggression": 1.20,
            "slowmo_duration": 1.4,
            "music_balance": 0.55,
            "game_sound_balance": 0.85,
            "title_tone": "narrative",
            "user_notes": "Balanced (14-17s): optymalny buildup 1.8s, zoom 1.20x, zwolnienie 1.4s.",
        },
        "cinematic_18_25s": {
            "rec_pacing": "cinematic",
            "zoom_aggression": 1.10,
            "slowmo_duration": 2.0,
            "music_balance": 0.45,
            "game_sound_balance": 0.90,
            "title_tone": "narrative",
            "user_notes": "Cinematic (18-25s): pełny kontekst walki, buduje watch time.",
        },
    }
    params = pacing_params.get(best_bucket, pacing_params["balanced_14_17s"])

    viral_dur_list = [
        float(v.get("duration_s") or 14.0)
        for v in sample_videos
        if v.get("duration_s") and int(v.get("views", 0) or 0) >= ZERO_VIEWS_THRESHOLD
    ]
    viral_avg_dur = round(statistics.median(viral_dur_list), 1) if viral_dur_list else 14.0

    return {
        "best_bucket": best_bucket,
        "viral_avg_duration_s": viral_avg_dur,
        "viral_count": len(sample_videos),
        "recommended_pacing": params["rec_pacing"],
        "zoom_aggression": params["zoom_aggression"],
        "slowmo_duration": params["slowmo_duration"],
        "music_balance": params["music_balance"],
        "game_sound_balance": params["game_sound_balance"],
        "title_tone": params["title_tone"],
        "user_notes": params["user_notes"],
        "bucket_stats": bucket_stats,
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# GŁÓWNA PĘTLA UCZENIA
# ─────────────────────────────────────────────────────────────────────────────────────────────

def run_channel_learning_cycle(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Główna pętla samouczenia kanału v2:
    1. Pobiera statystyki z YouTube i łączy z lokalną historią.
    2. Filtruje zera/błędy dystrybucji (< ZERO_VIEWS_THRESHOLD).
    3. Wylicza wagi akcji na MEDIANIE i trimmed mean (odporne na outliers).
    4. Wymaga MIN_SAMPLE_FOR_WEIGHT próbek przed modyfikacją wagi.
    5. Detectuje cadence degradację i title fatigue.
    6. Analizuje najlepszą godzinę/dzień publikacji.
    7. Koreluje retencję (Swiped Away) z typem akcji.
    8. Zapisuje zaktualizowaną dyrektywę adaptacyjną.
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

    # Uzupełnij metadane z lokalnej historii (action_type, champion, source_path)
    for loc in local_history:
        vid = loc.get("video_id")
        if vid and vid in videos_by_id:
            if loc.get("action_type"):
                videos_by_id[vid]["action_type"] = loc["action_type"]
            if loc.get("champion"):
                videos_by_id[vid]["champion"] = loc["champion"]
            if loc.get("source_path") and not videos_by_id[vid].get("source_path"):
                videos_by_id[vid]["source_path"] = loc["source_path"]

    all_analyzed = list(videos_by_id.values())
    total_count = len(all_analyzed)

    if total_count == 0:
        return {
            "status": "warning",
            "message": "Brak opublikowanych filmów do analizy na kanale.",
            "directive": get_learning_directive(),
        }

    # ── KROK 0: Filtracja danych wejściowych ────────────────────────────────────
    # Odrzuć filmy z < ZERO_VIEWS_THRESHOLD wyświetleń (błędy dystrybucji / testy / drafty)
    valid_videos = [v for v in all_analyzed if int(v.get("views", 0) or 0) >= ZERO_VIEWS_THRESHOLD]
    zero_views_count = total_count - len(valid_videos)
    if zero_views_count > 0:
        _safe_print(f"[Learning] [GUARD] Odrzucono {zero_views_count} filmów z < {ZERO_VIEWS_THRESHOLD} views (błędy dystrybucji/drafty).")

    # Użyj tylko valid_videos do obliczeń statystycznych
    if not valid_videos:
        return {
            "status": "warning",
            "message": "Wszystkie filmy mają < 50 views — prawdopodobnie błąd API lub tylko drafty.",
            "directive": get_learning_directive(),
        }

    # ── KROK 1: Globalna statystyka kanału ──────────────────────────────────────
    views_list = [int(v.get("views", 0) or 0) for v in valid_videos]
    pub_dates  = [_extract_video_datetime(v) for v in valid_videos]

    global_metrics = _compute_robust_metric(views_list, pub_dates)
    channel_median = global_metrics["median"]
    channel_mean   = global_metrics["mean"]
    trimmed_mean   = global_metrics["trimmed_mean"]

    eng_list = [float(v.get("engagement_rate") or 0.0) for v in valid_videos]
    avg_eng = statistics.mean(eng_list) if eng_list else 0.0

    # ── KROK 2: Agregacja per typ akcji (mediana + min-sample guard) ─────────────
    action_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for v in valid_videos:
        act = (v.get("action_type") or v.get("frag_type") or
               infer_frag_type_from_title(v.get("title", ""))).lower().strip()
        action_groups[act].append(v)

    action_stats: Dict[str, Any] = {}
    action_weights = DEFAULT_ACTION_WEIGHTS.copy()
    base_kill_weights = {
        "PENTAKILL": 70.0,
        "QUADRAKILL": 60.0,
        "TRIPLE KILL": 50.0,
        "DOUBLE KILL": 30.0,
        "SOLO BOLO": 90.0,
        "OUTPLAY": 75.0,
        "CLUTCH": 80.0,
        "KILL": 10.0,
    }
    demoted_formats = []

    # Formaty które NIGDY nie powinny być zdegradowane ze względu na małą próbę
    _NEVER_DEMOTE = {"pentakill", "quadrakill"}

    for act, vids in action_groups.items():
        vws = [int(v.get("views", 0) or 0) for v in vids]
        dates_act = [_extract_video_datetime(v) for v in vids]
        act_metrics = _compute_robust_metric(vws, dates_act)
        n_valid = act_metrics["count_valid"]

        if n_valid == 0:
            # Wszystkie filmy tego formatu to zera — oznacz jako suspect
            action_stats[act] = {
                "count": len(vids),
                "count_valid": 0,
                "avg_views": 0,
                "median_views": 0,
                "trimmed_mean_views": 0,
                "performance_ratio_mean": 0.0,
                "performance_ratio_median": 0.0,
                "avg_engagement_rate": 0.0,
                "weight": DEFAULT_ACTION_WEIGHTS.get(act, 1.0),
                "weight_source": "default_all_zeros",
            }
            continue

        act_median = act_metrics["median"]
        act_trimmed = act_metrics["trimmed_mean"]
        act_mean = act_metrics["mean"]

        # Ratios względem kanału
        ratio_median = (act_median / channel_median) if channel_median > 0 else 1.0
        ratio_trimmed = (act_trimmed / trimmed_mean) if trimmed_mean > 0 else 1.0

        engs = [float(v.get("engagement_rate") or 0.0) for v in vids]
        act_eng = statistics.mean(engs) if engs else 0.0
        eng_factor = 1.0 + min(0.2, max(-0.2, (act_eng - avg_eng) / (avg_eng or 1.0) * 0.15))

        # ── GUARD: Waga bazuje na medianie, nie średniej ──────────────────────────
        # Używamy trimmed_mean jako signal, ale z ograniczeniem zmiany ±30% per cykl
        if n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            raw_weight = ratio_trimmed * eng_factor
            # Clamp: max zmiana od domyślnej wartości ±40%
            default_w = DEFAULT_ACTION_WEIGHTS.get(act, 1.0)
            clamped_w = max(default_w * 0.60, min(default_w * 1.60, raw_weight))
            final_weight = round(max(0.4, min(2.5, clamped_w)), 2)
            weight_source = f"computed_n{n_valid}"
        else:
            # Za mała próba — zostaw domyślną wagę
            final_weight = DEFAULT_ACTION_WEIGHTS.get(act, 1.0)
            weight_source = f"default_small_sample_n{n_valid}"

        action_weights[act] = final_weight

        # ── Democja: wymaga MIN_SAMPLE_FOR_DEMOTION i ratio < 0.75 i nie jest w NEVER_DEMOTE ──
        if (ratio_median < 0.75 and n_valid >= MIN_SAMPLE_FOR_DEMOTION
                and act.lower() not in _NEVER_DEMOTE):
            demoted_formats.append(act)

        action_stats[act] = {
            "count": len(vids),
            "count_valid": n_valid,
            "avg_views": round(act_mean, 1),
            "median_views": round(act_median, 1),
            "trimmed_mean_views": round(act_trimmed, 1),
            "performance_ratio_mean": round(ratio_median, 2),
            "performance_ratio_median": round(ratio_median, 2),
            "avg_engagement_rate": round(act_eng, 2),
            "weight": final_weight,
            "weight_source": weight_source,
        }

        # ── Dostosuj base_kill_weights dla ewaluatora ────────────────────────────
        # Używamy ratio_median (odpornego na viral spike)
        if act == "solo_bolo" and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            base_kill_weights["SOLO BOLO"] = round(min(100.0, max(75.0, 75.0 * ratio_median)), 1)
        elif act == "outplay" and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            base_kill_weights["OUTPLAY"] = round(min(90.0, max(55.0, 65.0 * ratio_median)), 1)
        elif act == "pentakill" and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            # Nie karz Pentakilla za błędy techniczne — guard przez NEVER_DEMOTE
            base_kill_weights["PENTAKILL"] = round(min(100.0, max(55.0, 80.0 * ratio_median)), 1)
        elif act == "quadrakill" and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            base_kill_weights["QUADRAKILL"] = round(min(85.0, max(35.0, 70.0 * ratio_median)), 1)
        elif act in ("triple", "multikill") and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            base_kill_weights["TRIPLE KILL"] = round(min(70.0, max(35.0, 50.0 * ratio_median)), 1)
        elif act == "double" and n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            base_kill_weights["DOUBLE KILL"] = round(min(50.0, max(20.0, 28.0 * ratio_median)), 1)

    # ── KROK 3: Najlepszy format (tylko z MIN_SAMPLE_FOR_WEIGHT próbek) ──────────
    qualified = [
        (act, data["performance_ratio_median"])
        for act, data in action_stats.items()
        if data.get("count_valid", 0) >= MIN_SAMPLE_FOR_WEIGHT
    ]
    if not qualified:
        qualified = [(act, data["performance_ratio_median"])
                     for act, data in action_stats.items() if data.get("count_valid", 0) >= 1]
    top_action = max(qualified, key=lambda x: x[1])[0] if qualified else "solo_bolo"

    # ── KROK 4: Closed Pacing Loop ───────────────────────────────────────────────
    viral_cohort = [
        v for v in valid_videos
        if (int(v.get("views", 0) or 0) >= 1.25 * channel_median)
    ]
    pacing_analysis = correlate_viral_duration_and_pacing(viral_cohort, valid_videos, channel_median)
    rec_pacing = pacing_analysis["recommended_pacing"]

    # ── KROK 5: Analiza struktur tytułów i wzorców CTR ──────────────────────────
    structure_groups: Dict[str, List[float]] = defaultdict(list)
    for v in valid_videos:
        st = classify_title_structure(v.get("title", ""))
        vw = int(v.get("views", 0) or 0)
        ratio = (vw / channel_median) if channel_median > 0 else 1.0
        structure_groups[st].append(ratio)

    title_structure_stats = {}
    for st, ratios in structure_groups.items():
        title_structure_stats[st] = {
            "count": len(ratios),
            "avg_ratio": round(statistics.mean(ratios), 2),
            "median_ratio": round(statistics.median(ratios), 2),
        }

    # Najlepsza struktura bazuje na medianie (nie średniej) i wymaga >= 3 próbek
    qualified_structures = [(st, d["median_ratio"]) for st, d in title_structure_stats.items() if d["count"] >= 3]
    top_structure = max(qualified_structures, key=lambda x: x[1])[0] if qualified_structures else (
        max(title_structure_stats.items(), key=lambda x: x[1]["avg_ratio"])[0]
        if title_structure_stats else "EGO_CHECK"
    )

    # ── KROK 6: Słowa kluczowe CTR (junk filter rozszerzony) ─────────────────────
    _JUNK_KW = {
        "SHORTS", "LEAGUEOFLEGENDS", "LOL", "RIOTGAMES", "GAMING", "LEAGUE",
        "HIGHLIGHTS", "GAMES", "CLIP", "THE", "AND", "FOR", "THIS", "THEY",
        "THAT", "KATARINA", "WITH", "YOU", "HAVE", "ARE", "WAS", "WERE",
        "NOT", "THEIR", "INTO", "BEEN", "FROM", "MORE", "OUT", "ALL",
        "TOP", "HER", "HIM", "HIS", "KILL", "KILLS", "GAME", "LANE",
        "LATE", "WHEN", "TIME", "AFTER", "WHO", "WHAT", "NEVER",
        "MASTER", "TIER", "LEAGUE", "LEGENDS",
    }

    word_perf: Dict[str, List[float]] = defaultdict(list)
    for v in valid_videos:
        title = v.get("title", "")
        vw = int(v.get("views", 0) or 0)
        ratio = (vw / channel_median) if channel_median > 0 else 1.0
        clean_words = re.findall(r"\b[A-Za-z0-9%]{3,}\b", title.upper())
        for w_str in set(clean_words):
            if w_str in _JUNK_KW:
                continue
            word_perf[w_str].append(ratio)

    winning_words = []
    avoid_words = []
    for w_str, ratios in word_perf.items():
        if len(ratios) >= 2:  # min 2 próbki
            med_r = statistics.median(ratios)
            if med_r >= 1.20:
                winning_words.append((w_str, round(med_r, 2)))
            elif med_r <= 0.78:
                avoid_words.append((w_str, round(med_r, 2)))

    winning_words.sort(key=lambda x: x[1], reverse=True)
    avoid_words.sort(key=lambda x: x[1])
    winning_keywords = [w[0] for w in winning_words[:8]] or ["SOLO BOLO", "DISRESPECT", "CLEAN", "1v1"]
    avoid_keywords = [w[0] for w in avoid_words[:8]] or ["LATE GAME"]

    # Korekty z pętli user_feedback_history
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
                avoid_keywords = (avoid_keywords + _extra)[:10]
                _safe_print(f"[Learning] [USER_CORR] Korekty tytułów użytkownika → avoid+{_extra}")
    except Exception as _ue:
        _safe_print(f"[Learning] [WARN] Błąd wczytania korekt tytułów: {_ue}")

    # ── KROK 7: Nowe analizy ────────────────────────────────────────────────────
    cadence_analysis = _detect_publication_cadence(all_analyzed)
    title_fatigue = _detect_title_fatigue(valid_videos)
    pub_hour_analysis = _analyze_best_pub_hour(valid_videos)
    ab_title_analysis = analyze_ab_title_experiments(valid_videos)

    # ── KROK 8: Retencja przez YouTube Analytics API ─────────────────────────────
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

    retention_by_action = _analyze_retention_by_action(retention_summary, valid_videos)

    ret_insight = (
        f"YouTube Analytics API: {retention_summary.get('total_curves_analyzed', 0)} filmów z pełną krzywą retencji. "
        f"Średni Swiped Away: {retention_summary.get('channel_avg_swiped_away_pct', 16.0)}%, AVD: {retention_summary.get('channel_avg_view_pct', 99.0)}%."
        if retention_summary.get("status") == "success"
        else "YouTube Analytics API: Oczekiwanie na agregację krzywych retencji."
    )

    # ── KROK 9: Top viral titles ─────────────────────────────────────────────────
    sorted_by_views = sorted(valid_videos, key=lambda x: int(x.get("views", 0) or 0), reverse=True)
    top_viral_titles = [v.get("title") for v in sorted_by_views[:5] if v.get("title")]

    # ── KROK 10: Evaluator Config ────────────────────────────────────────────────
    evaluator_config = {
        "base_kill_weights": base_kill_weights,
        "action_multipliers": action_weights,
        "demoted_formats": demoted_formats,
        "demoted_penalty_points": 10.0,
        "s_tier_min": 82.0,
        "a_tier_min": 68.0,
        "b_tier_min": 50.0,
        "top_action_type": top_action,
    }

    # ── Insights ─────────────────────────────────────────────────────────────────
    cadence_flag = "⚠️ CADENCE WARNING: " + cadence_analysis["recommendation"] if cadence_analysis.get("gap_warning") else f"Rytm: {cadence_analysis.get('status', 'ok')} (śr. {cadence_analysis.get('avg_gap_days', '?')} dni)."
    fatigue_flag = "⚠️ TITLE FATIGUE: " + title_fatigue["recommendation"] if title_fatigue.get("fatigue_warning") else "Tytuły: różnorodne."

    insights = [
        f"Przeanalizowano {total_count} filmów ({len(valid_videos)} z >= {ZERO_VIEWS_THRESHOLD} views, {zero_views_count} odrzucono jako zera/drafty). Mediana kanału: {int(channel_median)} views, trimmed mean: {int(trimmed_mean)} views (eng: {avg_eng:.1f}%).",
        f"Format o najwyższym performance ratio (mediana): {top_action.upper()} ({action_stats.get(top_action, {}).get('performance_ratio_median', 1.0):.2f}x mediany). Wagi bazują na min {MIN_SAMPLE_FOR_WEIGHT} próbkach — bez tego → waga domyślna.",
        f"Closed Pacing Loop (mediana): Kohorta viral_hit ({pacing_analysis['viral_count']} filmów) → bucket '{pacing_analysis['best_bucket']}' (pewna: {bucket_stats_reliable(pacing_analysis['bucket_stats'])}). Profil: '{rec_pacing}'.",
        f"Title Reinforcement: Najlepsza struktura (mediana ratio): {top_structure}. CTR słowa: {', '.join(winning_keywords[:4])}. Avoid: {', '.join(avoid_keywords[:4])}.",
        f"Evaluator: Solo Bolo={base_kill_weights.get('SOLO BOLO')}pkt, Pentakill={base_kill_weights.get('PENTAKILL')}pkt. Zdegradowane: {', '.join(demoted_formats) or 'brak'} (wymaga N>={MIN_SAMPLE_FOR_DEMOTION}).",
        f"A/B Title Testing: {ab_title_analysis['tracked_ab_experiments']} testów w toku. Winning structure: '{ab_title_analysis['winning_title_structure']}'.",
        cadence_flag,
        fatigue_flag,
        ret_insight,
    ]

    directive = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schema_version": "2.0",
        "total_videos_analyzed": total_count,
        "total_videos_valid": len(valid_videos),
        "zero_views_filtered": zero_views_count,
        "channel_avg_views": round(channel_mean, 1),
        "channel_median_views": round(channel_median, 1),
        "channel_trimmed_mean_views": round(trimmed_mean, 1),
        "channel_avg_engagement_rate": round(avg_eng, 2),
        "top_action_type": top_action,
        "action_weights": action_weights,
        "action_stats": action_stats,
        "duration_analysis": pacing_analysis,
        "retention_analysis": retention_summary,
        "retention_by_action": retention_by_action,
        "publication_cadence": cadence_analysis,
        "title_fatigue": title_fatigue,
        "best_pub_hour_analysis": pub_hour_analysis,
        "ab_title_testing": ab_title_analysis,
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

    # Auto-tuning tuning_config.json (Closed Pacing Loop)
    try:
        if TUNING_FILE.exists():
            with open(TUNING_FILE, "r", encoding="utf-8") as tf:
                tuning_cfg = json.load(tf)
        else:
            tuning_cfg = {}

        tuning_cfg["pacing"] = rec_pacing
        tuning_cfg["zoomAggression"] = pacing_analysis["zoom_aggression"]
        tuning_cfg["slowmoDuration"] = pacing_analysis["slowmo_duration"]
        tuning_cfg["musicBalance"] = pacing_analysis["music_balance"]
        tuning_cfg["gameSoundBalance"] = pacing_analysis["game_sound_balance"]
        tuning_cfg["titleTone"] = pacing_analysis["title_tone"]
        tuning_cfg["userNotes"] = pacing_analysis["user_notes"]

        with open(TUNING_FILE, "w", encoding="utf-8") as tf:
            json.dump(tuning_cfg, tf, indent=2, ensure_ascii=False)
        _safe_print(
            f"[Learning] [TUNING] Auto-tuned {TUNING_FILE.name}: "
            f"pacing={rec_pacing}, zoom={pacing_analysis['zoom_aggression']}x, "
            f"slowmo={pacing_analysis['slowmo_duration']}s"
        )
    except Exception as te:
        _safe_print(f"[Learning] [WARN] Warning tuning_config update: {te}")

    return {
        "status": "success",
        "directive": directive,
        "insights": insights,
    }


def bucket_stats_reliable(bucket_stats: Dict[str, Any]) -> str:
    """Helper: zwraca nazwy bucketów z wystarczającą próbą."""
    reliable = [name for name, d in bucket_stats.items() if d.get("reliable")]
    return ", ".join(reliable) if reliable else "brak rzetelnych (za mała próba)"


if __name__ == "__main__":
    res = run_channel_learning_cycle(force_refresh=True)
    _safe_print("Learning Cycle Result:")
    _safe_print(json.dumps({k: v for k, v in res.items() if k != "directive"}, indent=2, ensure_ascii=False))
    insights = res.get("insights", [])
    _safe_print("\n=== INSIGHTS ===")
    for i, ins in enumerate(insights, 1):
        _safe_print(f"  {i}. {ins}")
