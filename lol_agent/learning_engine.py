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
MIN_SAMPLE_FOR_BUCKET = 8      # poniżej → bucket długości bez rekomendacji (było 3: sześć filmów nie rozstrzyga długości)
MIN_SAMPLE_FOR_SLOT = 5        # godzina / dzień publikacji: poniżej → slot nie może zostać "najlepszym" (było 2)
MIN_SAMPLE_FOR_KEYWORD = 4     # słowo w tytule: poniżej → ani "winning", ani "avoid" (było 2)
MIN_SAMPLE_FOR_STRUCTURE = 5   # struktura tytułu: poniżej → nie może wygrać (było 3)
MIN_LEAD_TO_WIN = 0.15         # zwycięzca musi wyprzedzać drugiego o 15 %, inaczej "brak wyraźnego zwycięzcy"
SHRINK_K = 10.0                # waga formatu ściągana do 1.0: w = 1 + (ratio - 1) * n / (n + SHRINK_K)
BREAKOUT_VIEWS_RATIO = 1.5     # "świeży hit" = film z ostatnich 5 mający >= 1.5x mediany kanału albo >= 40 wyświetleń/h

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


def _get_cet_tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Warsaw")
    except Exception:
        return timezone(timedelta(hours=1))


def _analyze_best_pub_hour(all_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Nowa zmienna: Wyznacza najlepszą godzinę i dzień tygodnia publikacji (UTC oraz Europe/Warsaw CET)
    na podstawie wyświetleń, AVD% i Engaged View Rate.
    """
    tz_cet = _get_cet_tz()
    hour_views: Dict[int, List[int]] = defaultdict(list)
    hour_cet_items: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    weekday_views: Dict[int, List[int]] = defaultdict(list)
    weekday_names = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]

    window_defs = [
        ("08:00-08:59", lambda h: h == 8),
        ("09:00-11:59", lambda h: 9 <= h < 12),
        ("12:00-14:59", lambda h: 12 <= h < 15),
        ("15:00-17:59", lambda h: 15 <= h < 18),
        ("18:00-18:59", lambda h: h == 18),
        ("19:00-20:59", lambda h: 19 <= h < 21),
        ("21:00-23:59", lambda h: 21 <= h <= 23),
    ]
    window_cet_items: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for v in all_videos:
        views = int(v.get("views", 0) or 0)
        if views < ZERO_VIEWS_THRESHOLD:
            continue
        dt = _extract_video_datetime(v)
        if dt:
            dt_utc = dt.astimezone(timezone.utc)
            dt_cet = dt.astimezone(tz_cet)
            hour_views[dt_utc.hour].append(views)
            hour_cet_items[dt_cet.hour].append(v)
            weekday_views[dt_cet.weekday()].append(views)
            for w_name, pred in window_defs:
                if pred(dt_cet.hour):
                    window_cet_items[w_name].append(v)
                    break

    best_hour = None
    best_hour_avg = 0
    hour_stats = {}
    for hour, vws in hour_views.items():
        if len(vws) >= 2:
            avg = statistics.median(vws)
            hour_stats[hour] = {"count": len(vws), "median_views": round(avg), "reliable": len(vws) >= MIN_SAMPLE_FOR_SLOT}
            if avg > best_hour_avg and len(vws) >= MIN_SAMPLE_FOR_SLOT:
                best_hour_avg = avg
                best_hour = hour

    def _summarize_bucket(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        vws = [int(x.get("views", 0) or 0) for x in items]
        avds = [float(x["avg_view_pct"]) for x in items if x.get("avg_view_pct") is not None and float(x.get("avg_view_pct") or 0) > 0]
        engs = [float(x["engaged_view_rate_pct"]) for x in items if x.get("engaged_view_rate_pct") is not None and float(x.get("engaged_view_rate_pct") or 0) > 0]
        return {
            "count": len(vws),
            "median_views": round(statistics.median(vws)),
            "mean_views": round(statistics.mean(vws)),
            "median_avd_pct": round(statistics.median(avds), 1) if avds else None,
            "median_engaged_rate_pct": round(statistics.median(engs), 1) if engs else None,
            "reliable": len(vws) >= MIN_SAMPLE_FOR_SLOT,
        }

    best_hour_cet = None
    best_hour_cet_med = 0.0
    hour_stats_cet: Dict[int, Dict[str, Any]] = {}
    for hour_c, items in sorted(hour_cet_items.items()):
        if len(items) >= 2:
            st = _summarize_bucket(items)
            hour_stats_cet[hour_c] = st
            if st["median_views"] > best_hour_cet_med and len(items) >= MIN_SAMPLE_FOR_SLOT:
                best_hour_cet_med = float(st["median_views"])
                best_hour_cet = hour_c

    window_stats_cet: Dict[str, Dict[str, Any]] = {}
    for w_name, _ in window_defs:
        items = window_cet_items.get(w_name, [])
        if items:
            window_stats_cet[w_name] = _summarize_bucket(items)

    best_weekday = None
    best_weekday_avg = 0
    weekday_stats = {}
    for wd, vws in weekday_views.items():
        if len(vws) >= 2:
            avg = statistics.median(vws)
            weekday_stats[weekday_names[wd]] = {"count": len(vws), "median_views": round(avg), "reliable": len(vws) >= MIN_SAMPLE_FOR_SLOT}
            if avg > best_weekday_avg and len(vws) >= MIN_SAMPLE_FOR_SLOT:
                best_weekday_avg = avg
                best_weekday = weekday_names[wd]

    def _clear(stats: Dict[Any, Any], best_val: float) -> bool:
        rel = sorted((d["median_views"] for d in stats.values() if d.get("reliable")), reverse=True)
        return len(rel) >= 2 and rel[1] > 0 and best_val >= rel[1] * (1.0 + MIN_LEAD_TO_WIN)

    # Zgodność: reszta systemu (kalendarz) dostaje liczbę jak dawniej. Gdy żaden slot nie ma MIN_SAMPLE_FOR_SLOT
    # filmów, zwracamy najlepszy z tych, które mają >= 2 (stare zachowanie), ale z flagą clear = False.
    hour_clear = best_hour is not None and _clear(hour_stats, best_hour_avg)
    hour_cet_clear = best_hour_cet is not None and _clear(hour_stats_cet, best_hour_cet_med)
    weekday_clear = best_weekday is not None and _clear(weekday_stats, best_weekday_avg)
    if best_hour is None and hour_stats:
        best_hour = max(hour_stats.items(), key=lambda kv: kv[1]["median_views"])[0]
    if best_hour_cet is None and hour_stats_cet:
        best_hour_cet = max(hour_stats_cet.items(), key=lambda kv: kv[1]["median_views"])[0]
    if best_weekday is None and weekday_stats:
        best_weekday = max(weekday_stats.items(), key=lambda kv: kv[1]["median_views"])[0]

    return {
        "best_hour_utc": best_hour,
        "best_hour_cet": best_hour_cet,
        "best_weekday": best_weekday,
        "best_hour_clear": hour_clear,        # False = różnica mieści się w szumie; nie planuj pod tę godzinę
        "best_hour_cet_clear": hour_cet_clear,
        "best_weekday_clear": weekday_clear,
        "hour_stats": hour_stats,
        "hour_stats_cet": hour_stats_cet,
        "window_stats_cet": window_stats_cet,
        "recommended_slots_cet": ["11:00", "21:30"],
        "weekday_stats": weekday_stats,
        "note": (f"Mediana wyświetleń per godzina/okno/dzień (UTC i CET). Slot wygrywa dopiero od {MIN_SAMPLE_FOR_SLOT} filmów "
                 f"i przewagi {int(MIN_LEAD_TO_WIN * 100)} % nad drugim; best_*_clear mówi, czy zwycięzca jest wyraźny."),
    }


def _analyze_learning_progression(valid_videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Mierzy rozwój projektu w czasie i odpowiada na pytanie, czy algorytm i montaż się uczą
    (porównanie miesięczne 2026 oraz kohorty first_half vs second_half vs last_15_videos).
    """
    tz_cet = _get_cet_tz()
    dated: List[Tuple[datetime, Dict[str, Any]]] = []
    for v in valid_videos:
        dt = _extract_video_datetime(v)
        if dt:
            dated.append((dt.astimezone(tz_cet), v))

    if not dated:
        return {
            "total_dated_videos": 0,
            "monthly_2026": {},
            "cohorts": {},
            "is_improving": False,
            "summary": "Brak filmów z datą publikacji.",
        }

    dated.sort(key=lambda pair: pair[0])

    def _cohort_metrics(items: List[Tuple[datetime, Dict[str, Any]]]) -> Dict[str, Any]:
        if not items:
            return {}
        vws = [int(v.get("views", 0) or 0) for _, v in items]
        avds = [float(v["avg_view_pct"]) for _, v in items if v.get("avg_view_pct") is not None and float(v.get("avg_view_pct") or 0) > 0]
        engs = [float(v["engaged_view_rate_pct"]) for _, v in items if v.get("engaged_view_rate_pct") is not None and float(v.get("engaged_view_rate_pct") or 0) > 0]
        subs = sum(int(v.get("subscribers_gained") or 0) for _, v in items)
        return {
            "count": len(items),
            "date_range": [items[0][0].strftime("%Y-%m-%d"), items[-1][0].strftime("%Y-%m-%d")],
            "median_views": round(statistics.median(vws)),
            "mean_views": round(statistics.mean(vws)),
            "median_avd_pct": round(statistics.median(avds), 1) if avds else None,
            "median_engaged_rate_pct": round(statistics.median(engs), 1) if engs else None,
            "subscribers_gained": subs,
        }

    by_month: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = defaultdict(list)
    for dt_c, v in dated:
        if dt_c.year == 2026:
            by_month[dt_c.strftime("%Y-%m")].append((dt_c, v))

    monthly_2026: Dict[str, Any] = {}
    for m_key in sorted(by_month.keys()):
        monthly_2026[m_key] = _cohort_metrics(by_month[m_key])

    mid = len(dated) // 2
    first_half = _cohort_metrics(dated[:mid]) if mid > 0 else {}
    second_half = _cohort_metrics(dated[mid:]) if mid > 0 else {}
    last_15 = _cohort_metrics(dated[-15:])

    avd_improved = False
    summary_parts = []
    if len(monthly_2026) >= 2:
        months_sorted = sorted(monthly_2026.keys())
        m0 = monthly_2026[months_sorted[0]]
        m1 = monthly_2026[months_sorted[-1]]
        if m0.get("median_avd_pct") is not None and m1.get("median_avd_pct") is not None:
            avd_improved = m1["median_avd_pct"] > m0["median_avd_pct"]
            summary_parts.append(
                f"Mediana AVD% (2026): {m0['median_avd_pct']}% ({months_sorted[0]}) -> {m1['median_avd_pct']}% ({months_sorted[-1]})."
            )
    if first_half.get("median_avd_pct") is not None and last_15.get("median_avd_pct") is not None:
        if last_15["median_avd_pct"] > first_half["median_avd_pct"]:
            avd_improved = True
        summary_parts.append(
            f"1. połowa kanału vs ostatnie 15: AVD {first_half['median_avd_pct']}% -> {last_15['median_avd_pct']}%, mediana wyśw. {first_half['median_views']} -> {last_15['median_views']}."
        )

    return {
        "total_dated_videos": len(dated),
        "monthly_2026": monthly_2026,
        "cohorts": {
            "first_half": first_half,
            "second_half": second_half,
            "last_15_videos": last_15,
        },
        "is_improving": avd_improved,
        "summary": " ".join(summary_parts) if summary_parts else "Za mało danych historycznych AVD%.",
    }


def _extract_recipe_director_operation(rec: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(rec, dict):
        return None
    op = rec.get("director_operation") or (((rec.get("director") or {}).get("synapsa_decision") or {}).get("operation"))
    return str(op).strip().upper() if op else None


def _analyze_48h_reality_gate(
    valid_videos: List[Dict[str, Any]],
    channel_median: float,
    shorts_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Agreguje wyniki Bramki 48h (Reality Gate) na filmach starszych niż 48 godzin:
    - Real Watchability Index (RWI 0-100) per format oraz per operacja Synapsy,
    - Odsetek FIT_CONFIRMED vs FALSE_POSITIVE_MONTAGE,
    - Wyuczone korekty parametrów dla Montage Directora (buildup_sec / outro_sec / prefer_style).
    """
    try:
        try:
            from lol_agent.lol_performance_tracker import evaluate_48h_post_publish_gate
        except ImportError:
            from lol_performance_tracker import evaluate_48h_post_publish_gate
    except Exception:
        return {
            "status": "unavailable",
            "total_verified_48h": 0,
            "by_director_operation": {},
            "director_adjustments_by_action": {},
            "high_rwi_video_ids": [],
        }

    now_utc = datetime.now(timezone.utc)
    verified_48h: List[Dict[str, Any]] = []
    pending_under_48h = 0

    for v in valid_videos:
        dt = _extract_video_datetime(v)
        if not dt:
            continue
        age_h = (now_utc - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_h >= 48.0:
            v["is_48h_verified"] = True
            verified_48h.append(v)
        else:
            v["is_48h_verified"] = False
            pending_under_48h += 1

    if not verified_48h:
        return {
            "status": "pending",
            "total_verified_48h": 0,
            "pending_under_48h": pending_under_48h,
            "avg_rwi_score": None,
            "median_rwi_score": None,
            "verdict_counts": {},
            "fit_confirmed_pct": 0.0,
            "false_positive_pct": 0.0,
            "by_action_type": {},
            "by_director_operation": {},
            "director_adjustments_by_action": {},
            "high_rwi_video_ids": [],
        }

    by_id_48 = {str(vv["video_id"]): vv for vv in verified_48h if vv.get("video_id")}
    by_title_48 = {_norm_match_key(vv["title"]): vv for vv in verified_48h if vv.get("title")}
    recipe_for_v: Dict[int, Dict[str, Any]] = {}
    for rec in _collect_recipe_records(shorts_dir):
        mv = _match_recipe_to_video(rec, by_id_48, by_title_48)
        if mv is not None and id(mv) not in recipe_for_v:
            recipe_for_v[id(mv)] = rec

    rwi_all: List[float] = []
    verdict_counts: Dict[str, int] = defaultdict(int)
    by_action_rwi: Dict[str, List[float]] = defaultdict(list)
    by_action_verdicts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_action_issues: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_op_rwi: Dict[str, List[float]] = defaultdict(list)
    by_op_verdicts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    high_rwi_video_ids: List[str] = []

    for v in verified_48h:
        g = evaluate_48h_post_publish_gate(v, v, channel_median_views=channel_median)
        v["_gate_48h_eval"] = g
        rwi = float(g["rwi_score"])
        audit = g.get("definition_audit") or {}
        ov = audit.get("overall_verdict", "FIT_CONFIRMED")
        hv = audit.get("hook_verdict", "HOOK_CONFIRMED")
        pv = audit.get("pacing_verdict", "PACING_CONFIRMED")

        rwi_all.append(rwi)
        verdict_counts[ov] += 1

        act = (v.get("action_type") or v.get("frag_type") or "outplay").lower().strip()
        by_action_rwi[act].append(rwi)
        by_action_verdicts[act][ov] += 1
        by_action_issues[act][hv] += 1
        by_action_issues[act][pv] += 1

        op_name = _extract_recipe_director_operation(recipe_for_v.get(id(v)))
        if not op_name and v.get("director_operation"):
            op_name = str(v["director_operation"]).strip().upper()
        if op_name:
            by_op_rwi[op_name].append(rwi)
            by_op_verdicts[op_name][ov] += 1

        if ov == "FIT_CONFIRMED" and rwi >= 75.0 and v.get("video_id"):
            high_rwi_video_ids.append(str(v["video_id"]))

    n_ver = len(verified_48h)
    fit_cnt = verdict_counts.get("FIT_CONFIRMED", 0)
    fp_cnt = verdict_counts.get("FALSE_POSITIVE_MONTAGE", 0)

    by_action_type: Dict[str, Any] = {}
    director_adjustments_by_action: Dict[str, Dict[str, Any]] = {}
    for act, rwis in by_action_rwi.items():
        cnt = len(rwis)
        v_map = by_action_verdicts[act]
        top_v = max(v_map.items(), key=lambda x: x[1])[0] if v_map else "FIT_CONFIRMED"
        fit_a = round((v_map.get("FIT_CONFIRMED", 0) / max(cnt, 1)) * 100.0, 1)
        by_action_type[act] = {
            "count": cnt,
            "avg_rwi": round(statistics.mean(rwis), 1),
            "median_rwi": round(statistics.median(rwis), 1),
            "fit_confirmed_pct": fit_a,
            "top_verdict": top_v,
        }
        iss = by_action_issues[act]
        adj: Dict[str, Any] = {}
        hook_bad = iss.get("OVERESTIMATED_HOOK", 0) + iss.get("HOOK_WEAK", 0)
        pacing_bad = iss.get("OVERESTIMATED_PACING", 0) + iss.get("PACING_WEAK", 0)
        if cnt >= 2 and hook_bad / cnt >= 0.4:
            adj["buildup_sec_delta"] = -0.3
            adj["prefer_style"] = "IN_MEDIA_RES"
        if cnt >= 2 and pacing_bad / cnt >= 0.4:
            adj["outro_sec_delta"] = -0.4
            adj.setdefault("prefer_style", "SPEED_RAMP_FLOW")
        if adj:
            adj["sample_size"] = cnt
            director_adjustments_by_action[act] = adj

    by_director_operation: Dict[str, Any] = {}
    for op_name, rwis_op in by_op_rwi.items():
        cnt_op = len(rwis_op)
        v_map_op = by_op_verdicts[op_name]
        by_director_operation[op_name] = {
            "count": cnt_op,
            "avg_rwi": round(statistics.mean(rwis_op), 1),
            "median_rwi": round(statistics.median(rwis_op), 1),
            "fit_confirmed_pct": round((v_map_op.get("FIT_CONFIRMED", 0) / max(cnt_op, 1)) * 100.0, 1),
        }

    hard_cases_count = 0
    try:
        from lol_agent.hard_case_learner import load_hard_cases
        hard_cases_count = len(load_hard_cases())
    except Exception:
        try:
            from hard_case_learner import load_hard_cases
            hard_cases_count = len(load_hard_cases())
        except Exception:
            pass

    synapsa_director_insights: List[Dict[str, Any]] = []
    if by_action_type:
        ranked_actions = sorted(by_action_type.items(), key=lambda x: x[1].get("avg_rwi", 0.0), reverse=True)
        best_act, best_st = ranked_actions[0]
        synapsa_director_insights.append({
            "target": best_act,
            "observation": f"Najwyższe średnie RWI {best_st['avg_rwi']} ({best_st['fit_confirmed_pct']}% FIT na {best_st['count']} filmach).",
            "action_taken": "KEEP_FULL_CONTINUOUS (zachowaj naturalny rytm akcji)",
            "expected_impact": "Stabilne utrzymanie widowni i wyższa retencja.",
        })
        worst_act, worst_st = ranked_actions[-1]
        if worst_act != best_act:
            adj_info = director_adjustments_by_action.get(worst_act) or {}
            act_taken = adj_info.get("prefer_style") or "SPEED_RAMP_FLOW / IN_MEDIA_RES"
            synapsa_director_insights.append({
                "target": worst_act,
                "observation": f"Najniższe RWI {worst_st['avg_rwi']} ({worst_st['fit_confirmed_pct']}% FIT na {worst_st['count']} filmach).",
                "action_taken": f"Korekta stylu na {act_taken} + ostrzejszy buildup/outro.",
                "expected_impact": "Skrócenie martwego początku i eliminacja zbyt długiego outro.",
            })
    if hard_cases_count > 0:
        synapsa_director_insights.append({
            "target": "hard_cases_memory",
            "observation": f"Zarejestrowano {hard_cases_count} trudnych klipów (m.in. zatkane banery / kradzież smoka).",
            "action_taken": "Aktywny Rollback Guard przed FFmpeg + wymuszone KEEP_FULL_CONTINUOUS dla teamfightów z obiektem.",
            "expected_impact": "Zero uciętych wielofazowych akcji w kolejnych renderach.",
        })

    return {
        "status": "active",
        "total_verified_48h": n_ver,
        "pending_under_48h": pending_under_48h,
        "avg_rwi_score": round(statistics.mean(rwi_all), 1),
        "median_rwi_score": round(statistics.median(rwi_all), 1),
        "verdict_counts": dict(verdict_counts),
        "fit_confirmed_pct": round((fit_cnt / max(n_ver, 1)) * 100.0, 1),
        "false_positive_pct": round((fp_cnt / max(n_ver, 1)) * 100.0, 1),
        "by_action_type": by_action_type,
        "by_director_operation": by_director_operation,
        "director_adjustments_by_action": director_adjustments_by_action,
        "high_rwi_video_ids": high_rwi_video_ids,
        "hard_cases_count": hard_cases_count,
        "synapsa_director_insights": synapsa_director_insights,
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
                dt = pub_dates[i]
                if not isinstance(dt, datetime):
                    dt = datetime.fromisoformat(str(dt or "").replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
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


def robust_summary(values: List[float]) -> Dict[str, Any]:
    """Mediana, średnia i średnia bez 10 % skrajnych, z listą wartości odstających (reguła 1.5 IQR)."""
    vals = sorted(float(v) for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return {"count": 0, "median": None, "mean": None, "trimmed_mean": None, "outliers": []}
    med = statistics.median(vals)
    trim = int(n * 0.10)
    core = vals[trim: n - trim] if n - 2 * trim >= 1 else vals
    q1 = vals[int((n - 1) * 0.25)]; q3 = vals[int((n - 1) * 0.75)]; iqr = q3 - q1
    out = [v for v in vals if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr] if n >= 5 and iqr > 0 else []
    return {"count": n, "median": round(med, 1), "mean": round(statistics.mean(vals), 1),
            "trimmed_mean": round(statistics.mean(core), 1), "outliers": [round(v, 1) for v in out]}


def bootstrap_median_ratio_ci(values: List[float], baseline: float, rounds: int = 2000, seed: int = 7) -> Tuple[float, float]:
    """Przedział 90 % dla (mediana grupy / mediana kanału). Gdy obejmuje 1.0, różnica może być przypadkiem."""
    import random as _r
    vals = [float(v) for v in values]
    if len(vals) < 2 or baseline <= 0:
        return (0.0, 0.0)
    rng = _r.Random(seed); meds = []
    for _ in range(rounds):
        meds.append(statistics.median([vals[rng.randrange(len(vals))] for _ in vals]) / baseline)
    meds.sort()
    return (round(meds[int(0.05 * rounds)], 2), round(meds[int(0.95 * rounds) - 1], 2))


def shrunk_weight(ratio: float, n: int, k: float = SHRINK_K) -> float:
    """Waga formatu: stosunek do mediany kanału ściągnięty do 1.0 tym mocniej, im mniej filmów."""
    return 1.0 + (float(ratio) - 1.0) * (n / (n + k))


def summarize_retention(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Retencja liczona odpornie. Średnia z 15 filmów daje się przeciągnąć jednemu (474.7 % przy medianie ~100 %),
    a swiped_away równe 0.0 przy klipach 5–8 s to brak danych, nie wynik; filmy poniżej ZERO_VIEWS_THRESHOLD odpadają.
    """
    # film odpada tylko wtedy, gdy ZNAMY jego wyświetlenia i jest ich za mało (rekord bez pola "views" zostaje)
    ok = [v for v in videos if v.get("views") is None or int(v.get("views") or 0) >= ZERO_VIEWS_THRESHOLD]
    avd = robust_summary([v.get("avg_view_pct") for v in ok if v.get("avg_view_pct") is not None])
    sw = robust_summary([v.get("swiped_away_pct") for v in ok
                         if v.get("swiped_away_pct") is not None and float(v.get("swiped_away_pct")) > 0.0])
    return {"videos_used": len(ok), "avg_view_pct": avd, "swiped_away_pct": sw,
            "note": "Podawaj medianę. Średnia jest tu tylko dla porównania ze starymi raportami."}


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

    # Porównujemy WSZYSTKIE ważne filmy z prawdziwą długością. Liczenie mediany tylko wśród hitów (jak dawniej)
    # nie mówi, która długość robi hity; a wpisywanie 12/15 s tam, gdzie długości brak, fałszowało koszyki.
    for v in valid_videos:
        dur = float(v.get("duration_s", 0.0) or 0.0)
        if dur <= 0.0:
            continue
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

    # Zwycięzca musi być wyraźny; inaczej nie ruszamy ustawień montażu
    reliable_scores = sorted((d["composite_score"] for d in bucket_stats.values() if d["reliable"]), reverse=True)
    clear_winner = (len(reliable_scores) >= 2 and reliable_scores[1] > 0
                    and reliable_scores[0] >= reliable_scores[1] * (1.0 + MIN_LEAD_TO_WIN))

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
        "clear_winner": clear_winner,
        "mei_directives": {
            "target_combat_density_pct": 85.0,
            "max_outro_latency_sec": 1.8,
            "target_hook_latency_sec": 1.2,
            "require_smart_camera_lerp": True,
            "require_seamless_loop": True,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────────────────────
# GŁÓWNA PĘTLA UCZENIA
# ─────────────────────────────────────────────────────────────────────────────────────────────

def _norm_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", os.path.splitext(str(value or ""))[0].lower())


def _collect_recipe_records(shorts_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    dirs: List[Path] = []
    if shorts_dir is not None:
        dirs.append(Path(shorts_dir))
    else:
        for d in (
            LEARNING_DIR / "recipes_archive",
            LEARNING_DIR / "lol_temp",
            LEARNING_DIR / "output_shorts",
            LEARNING_DIR.parent / "output_shorts",
            LEARNING_DIR,
        ):
            if d not in dirs:
                dirs.append(d)
    seen = set()
    recipes: List[Dict[str, Any]] = []
    for d in dirs:
        if not d.exists():
            continue
        for rp in sorted(d.glob("*.recipe.json")):
            rp_res = str(rp.resolve())
            if rp_res in seen:
                continue
            seen.add(rp_res)
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                if isinstance(rec, dict):
                    rec = dict(rec)
                    rec.setdefault("_recipe_stem", rp.name[:-len(".recipe.json")])
                    recipes.append(rec)
            except Exception:
                pass
    return recipes


def _match_recipe_to_video(recipe: Dict[str, Any], by_id: Dict[str, Dict[str, Any]], by_title: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    vid = recipe.get("video_id") or (recipe.get("publication") or {}).get("video_id")
    if vid and str(vid) in by_id:
        return by_id[str(vid)]
    for candidate in (recipe.get("title"), recipe.get("_recipe_stem"), os.path.basename(str(recipe.get("video_path") or ""))):
        k = _norm_match_key(candidate or "")
        if k and k in by_title:
            return by_title[k]
    return None


def analyze_recipe_experiments(videos: List[Dict[str, Any]], shorts_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Analizuje eksperymenty montażowe z plików *.recipe.json zestawione z wynikami YouTube.
    Wymaga MIN_SAMPLE_FOR_BUCKET próbek na koszyk oraz >= MIN_LEAD_TO_WIN przewagi do uznania zwycięzcy.
    """
    valid = [v for v in (videos or []) if isinstance(v, dict) and float(v.get("views") or 0) > 0]
    by_id = {str(v["video_id"]): v for v in valid if v.get("video_id")}
    by_title = {_norm_match_key(v["title"]): v for v in valid if v.get("title")}

    recipes = _collect_recipe_records(shorts_dir)
    matched: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for rec in recipes:
        v = _match_recipe_to_video(rec, by_id, by_title)
        if v is not None:
            matched.append((rec, v))

    views_pool = [float(v["views"]) for _, v in matched] or [float(v["views"]) for v in valid]
    channel_median = statistics.median(views_pool) if views_pool else 0.0

    dim_extractors = {
        "montage_style": lambda r: str(r.get("montage_style") or "PRIMARY"),
        "director_operation": lambda r: str(_extract_recipe_director_operation(r) or "KEEP_FULL_CONTINUOUS"),
        "camera_mode": lambda r: str(r.get("camera_mode") or ((r.get("director") or {}).get("camera_mode")) or "tight_player"),
        "hook_style": lambda r: str(r.get("hook_style") or r.get("hook_type") or "default"),
        "outro_cta_id": lambda r: str(r.get("outro_cta_id") or "legacy"),
        "music_track": lambda r: os.path.basename(str((r.get("music") or {}).get("track") or "none")) or "none",
        "crop_mode": lambda r: str(r.get("crop_mode") or "smart"),
        "has_warp_game_audio": lambda r: "yes" if bool(r.get("warp_segments")) else "no",
    }

    dimensions: Dict[str, Any] = {}
    reliable_dims: List[str] = []

    for dim_name, extractor in dim_extractors.items():
        buckets: Dict[str, List[float]] = defaultdict(list)
        buckets_conv: Dict[str, List[float]] = defaultdict(list)
        for rec, vid in matched:
            bkey = extractor(rec)
            v_cnt = float(vid.get("views") or 0)
            buckets[bkey].append(v_cnt)
            c_cnt = float(vid.get("comments") or 0)
            s_cnt = float(vid.get("subscribers_gained") or 0)
            buckets_conv[bkey].append(((c_cnt * 3.0 + s_cnt * 8.0) / max(v_cnt, 1.0)) * 1000.0)

        bucket_stats: Dict[str, Any] = {}
        eligible: List[Tuple[str, float]] = []
        for bname, bviews in sorted(buckets.items()):
            med_v = statistics.median(bviews)
            ratio = round(med_v / channel_median, 2) if channel_median > 0 else 1.0
            rel = len(bviews) >= MIN_SAMPLE_FOR_BUCKET
            convs = buckets_conv.get(bname) or []
            bucket_stats[bname] = {
                "count": len(bviews),
                "median_views": round(med_v, 1),
                "performance_ratio_median": ratio,
                "avg_conversion_per_1k": round(statistics.mean(convs), 2) if convs else 0.0,
                "reliable": rel,
            }
            if rel:
                eligible.append((bname, ratio))

        eligible.sort(key=lambda x: x[1], reverse=True)
        winner = None
        clear_winner = False
        lead_pct = 0.0
        if len(eligible) >= 2:
            top_name, top_r = eligible[0]
            sec_r = eligible[1][1]
            lead = (top_r - sec_r) / max(sec_r, 1e-6)
            lead_pct = round(lead * 100.0, 1)
            if lead >= MIN_LEAD_TO_WIN:
                winner = top_name
                clear_winner = True
                reliable_dims.append(dim_name)

        dimensions[dim_name] = {
            "winner": winner,
            "reliable": clear_winner,
            "lead_pct": lead_pct,
            "buckets": bucket_stats,
        }

    return {
        "total_recipes": len(recipes),
        "matched_videos": len(matched),
        "channel_median_views": round(channel_median, 1),
        "min_sample_per_bucket": MIN_SAMPLE_FOR_BUCKET,
        "min_lead_to_win": MIN_LEAD_TO_WIN,
        "reliable_dimensions": reliable_dims,
        "dimensions": dimensions,
    }


def _pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    try:
        sx = statistics.stdev(xs)
        sy = statistics.stdev(ys)
    except statistics.StatisticsError:
        return None
    if sx <= 0 or sy <= 0:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)
    return round(cov / (sx * sy), 3)


def calibrate_quality_gate(
    videos: List[Dict[str, Any]],
    shorts_dir: Optional[Path] = None,
    current_threshold: float = 70.0,
) -> Dict[str, Any]:
    """
    Kalibruje próg bramki jakości (quality_gate.threshold) na podstawie korelacji quality_score z wynikami (views/retencja).
    Bez próby >= MIN_SAMPLE_FOR_BUCKET utrzymuje current_threshold (reliable=False).
    """
    valid = [v for v in (videos or []) if isinstance(v, dict) and float(v.get("views") or 0) > 0]
    by_id = {str(v["video_id"]): v for v in valid if v.get("video_id")}
    by_title = {_norm_match_key(v["title"]): v for v in valid if v.get("title")}

    recipe_by_vid: Dict[str, Dict[str, Any]] = {}
    for rec in _collect_recipe_records(shorts_dir):
        v = _match_recipe_to_video(rec, by_id, by_title)
        if v is not None:
            key = str(v.get("video_id") or _norm_match_key(v.get("title", "")))
            if key:
                recipe_by_vid[key] = rec

    samples: List[Dict[str, Any]] = []
    for idx, v in enumerate(valid):
        key = str(v.get("video_id") or _norm_match_key(v.get("title", "")) or idx)
        rec = recipe_by_vid.get(key) or {}
        score = v.get("quality_score")
        if score is None:
            score = rec.get("quality_score") or (rec.get("gate_quality") or {}).get("score")
        if score is None:
            continue
        br = v.get("quality_breakdown") or rec.get("quality_breakdown") or (rec.get("gate_quality") or {}).get("breakdown") or {}
        samples.append({
            "score": float(score),
            "views": float(v.get("views") or 0),
            "avg_view_pct": float(v["avg_view_pct"]) if v.get("avg_view_pct") is not None else None,
            "breakdown": br if isinstance(br, dict) else {},
        })

    comp_corrs: Dict[str, float] = {}
    comp_keys = set()
    for s in samples:
        comp_keys.update(s["breakdown"].keys())
    for ck in sorted(comp_keys):
        cxs, cys = [], []
        for s in samples:
            val = s["breakdown"].get(ck)
            if isinstance(val, dict):
                val = val.get("score")
            if val is not None:
                cxs.append(float(val))
                cys.append(s["views"])
        c = _pearson_corr(cxs, cys)
        if c is not None:
            comp_corrs[ck] = c

    xs_all = [s["score"] for s in samples]
    ys_all = [s["views"] for s in samples]
    corr_views = _pearson_corr(xs_all, ys_all)
    avd_pairs = [(s["score"], s["avg_view_pct"]) for s in samples if s["avg_view_pct"] is not None]
    corr_avd = _pearson_corr([p[0] for p in avd_pairs], [p[1] for p in avd_pairs]) if avd_pairs else None

    n = len(samples)
    if n < MIN_SAMPLE_FOR_BUCKET:
        return {
            "sample_size": n,
            "min_sample": MIN_SAMPLE_FOR_BUCKET,
            "reliable": False,
            "current_threshold": float(current_threshold),
            "recommended_threshold": float(current_threshold),
            "correlation_qs_views": corr_views,
            "correlation_qs_avd": corr_avd,
            "component_correlations": comp_corrs,
            "reason": f"Za mała próba ({n} < {MIN_SAMPLE_FOR_BUCKET})",
        }

    med_v = statistics.median(ys_all)
    pos = [s["score"] for s in samples if s["views"] >= med_v]
    neg = [s["score"] for s in samples if s["views"] < med_v]
    best_t = float(current_threshold)
    best_bal_acc = -1.0
    if pos and neg:
        for cand in range(55, 81):
            tpr = sum(1 for sc in pos if sc >= cand) / len(pos)
            tnr = sum(1 for sc in neg if sc < cand) / len(neg)
            bal_acc = (tpr + tnr) / 2.0
            if (bal_acc > best_bal_acc + 1e-9) or (
                abs(bal_acc - best_bal_acc) <= 1e-9 and abs(cand - current_threshold) < abs(best_t - current_threshold)
            ):
                best_bal_acc = bal_acc
                best_t = float(cand)
    best_t = max(55.0, min(80.0, best_t))

    return {
        "sample_size": n,
        "min_sample": MIN_SAMPLE_FOR_BUCKET,
        "reliable": True,
        "current_threshold": float(current_threshold),
        "recommended_threshold": round(best_t, 1),
        "balanced_accuracy": round(best_bal_acc, 3) if best_bal_acc >= 0 else None,
        "correlation_qs_views": corr_views,
        "correlation_qs_avd": corr_avd,
        "component_correlations": comp_corrs,
        "reason": "ok",
    }


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

    # ── Uruchom automatyczną weryfikację oczekujących sprawdzeń z performance trackera
    try:
        try:
            from lol_agent.lol_performance_tracker import reconcile_and_verify_published_videos, run_pending_checks
        except ImportError:
            from lol_performance_tracker import reconcile_and_verify_published_videos, run_pending_checks
        reconcile_and_verify_published_videos()
        run_pending_checks()
    except Exception as e_rec:
        _safe_print(f"[Learning] Reconcile warning: {e_rec}")

    yt_data = get_channel_videos_and_performance(max_results=250, force_refresh=force_refresh)
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

    # Dołącz zweryfikowane dane analityczne z performance_log.jsonl (zamknięcie pętli feedbacku)
    perf_log_file = LEARNING_DIR / "performance_log.jsonl"
    if perf_log_file.exists():
        try:
            with open(perf_log_file, "r", encoding="utf-8") as _plf:
                for _pline in _plf:
                    if not _pline.strip():
                        continue
                    try:
                        p_item = json.loads(_pline.strip())
                        p_vid = p_item.get("video_id")
                        if not p_vid:
                            continue
                        if p_vid in videos_by_id:
                            for k in ("views", "likes", "comments", "hook_retention_pct", "swiped_away_pct", "avg_view_pct", "completion_rate_pct"):
                                if p_item.get(k) is not None:
                                    if k in ("views", "likes", "comments") and videos_by_id[p_vid].get(k) is not None:
                                        if float(p_item[k]) > float(videos_by_id[p_vid][k]):
                                            videos_by_id[p_vid][k] = p_item[k]
                                    else:
                                        videos_by_id[p_vid][k] = p_item[k]
                        else:
                            videos_by_id[p_vid] = p_item
                    except Exception:
                        pass
        except Exception as e_perf:
            _safe_print(f"[Learning] Warning reading performance_log.jsonl: {e_perf}")

    # Wzbogać wszystkie filmy o pełne metryki YouTube Analytics API v2 (198+ filmów naraz)
    bulk_yta: Dict[str, Dict[str, Any]] = {}
    audience_insights: Dict[str, Any] = {}
    try:
        try:
            from lol_agent.api import youtube_analytics as _ya_mod
        except ImportError:
            from api import youtube_analytics as _ya_mod
        if hasattr(_ya_mod, "fetch_bulk_video_analytics"):
            bulk_yta = _ya_mod.fetch_bulk_video_analytics(force_refresh=force_refresh) or {}
        if hasattr(_ya_mod, "fetch_channel_audience_insights"):
            audience_insights = _ya_mod.fetch_channel_audience_insights(force_refresh=force_refresh) or {}
    except Exception as e_yta:
        _safe_print(f"[Learning] Warning fetching YTA v2 bulk/audience metrics: {e_yta}")

    for vid, v_item in videos_by_id.items():
        ya = bulk_yta.get(vid)
        if not ya:
            continue
        for k in ("avg_view_pct", "engaged_views", "engaged_view_rate_pct", "watch_time_hours", "shares", "subscribers_gained"):
            if v_item.get(k) is None and ya.get(k) is not None:
                v_item[k] = ya[k]

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

    # ── KROK 1b: Bramka 48h (Reality Gate) i oddzielenie filmów < 48h ───────────
    gate_48h_summary = _analyze_48h_reality_gate(valid_videos, channel_median)
    verified_48h_pool = [v for v in valid_videos if v.get("is_48h_verified")]
    learning_pool = verified_48h_pool if len(verified_48h_pool) >= 5 else valid_videos

    ch_avd_vals = [float(v["avg_view_pct"]) for v in learning_pool if v.get("avg_view_pct") is not None and 0 < float(v["avg_view_pct"]) < 300]
    ch_med_avd = statistics.median(ch_avd_vals) if ch_avd_vals else 100.0
    ch_eng_vals = [float(v["engaged_view_rate_pct"]) for v in learning_pool if v.get("engaged_view_rate_pct") is not None and float(v["engaged_view_rate_pct"]) > 0]
    ch_med_hook = statistics.median(ch_eng_vals) if ch_eng_vals else None

    # ── KROK 2: Agregacja per typ akcji (mediana + RWI/AVD + min-sample guard) ───
    action_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for v in learning_pool:
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

        # Wielowymiarowe ratio: Views + AVD% + Engaged Hook Rate (gdy dostępne)
        act_avds = [float(v["avg_view_pct"]) for v in vids if v.get("avg_view_pct") is not None and 0 < float(v["avg_view_pct"]) < 300]
        ratio_avd = (statistics.median(act_avds) / ch_med_avd) if (act_avds and ch_med_avd > 0) else ratio_median
        act_hooks = [float(v["engaged_view_rate_pct"]) for v in vids if v.get("engaged_view_rate_pct") is not None and float(v["engaged_view_rate_pct"]) > 0]
        ratio_hook = (statistics.median(act_hooks) / ch_med_hook) if (act_hooks and ch_med_hook) else ratio_median

        if act_avds and act_hooks and ch_med_hook:
            composite_ratio = 0.50 * ratio_median + 0.30 * ratio_avd + 0.20 * ratio_hook
        elif act_avds:
            composite_ratio = 0.70 * ratio_median + 0.30 * ratio_avd
        else:
            composite_ratio = ratio_median

        # Zachowaj zgodność kierunku z performance_ratio_median (wymóg kontraktu testów)
        effective_ratio = composite_ratio
        if (ratio_median >= 1.0 and effective_ratio < 1.0) or (ratio_median < 1.0 and effective_ratio >= 1.0):
            effective_ratio = 0.85 * ratio_median + 0.15 * composite_ratio
            if (ratio_median >= 1.0 and effective_ratio < 1.0) or (ratio_median < 1.0 and effective_ratio >= 1.0):
                effective_ratio = ratio_median

        # ── Waga = stosunek wielowymiarowy ściągnięty do 1.0 przy małej próbie ──
        recent_breakout = any(
            (int(v.get("views", 0) or 0) >= BREAKOUT_VIEWS_RATIO * channel_median or float(v.get("views_per_hour") or 0) >= 40.0)
            for v in vids[-5:]
        )
        ci_low, ci_high = bootstrap_median_ratio_ci([x for x in vws if x >= ZERO_VIEWS_THRESHOLD], channel_median)
        if n_valid >= MIN_SAMPLE_FOR_WEIGHT:
            raw_weight = shrunk_weight(effective_ratio, n_valid) * eng_factor
            if recent_breakout and raw_weight < 1.0:
                raw_weight = 1.0   # świeży hit chroni przed obniżeniem, ale niczego nie zawyża
            final_weight = round(max(0.6, min(1.6, raw_weight)), 2)
            weight_source = f"median_shrunk_n{n_valid}" + ("_breakout_floor" if recent_breakout else "")
        else:
            # Za mała próba — zostaw domyślną wagę
            final_weight = DEFAULT_ACTION_WEIGHTS.get(act, 1.0)
            weight_source = f"default_small_sample_n{n_valid}"

        action_weights[act] = final_weight

        # ── Democja: wymaga MIN_SAMPLE_FOR_DEMOTION i ratio < 0.75 i nie jest w NEVER_DEMOTE i brak świeżego hitu ──
        has_recent_breakout = recent_breakout
        if (ratio_median < 0.75 and n_valid >= MIN_SAMPLE_FOR_DEMOTION
                and act.lower() not in _NEVER_DEMOTE and not has_recent_breakout):
            demoted_formats.append(act)

        rwi_action = (gate_48h_summary.get("by_action_type") or {}).get(act, {})
        conv_vals = [
            ((float(v.get("comments") or 0) * 3.0 + float(v.get("subscribers_gained") or 0) * 8.0) / max(float(v.get("views") or 1), 1.0)) * 1000.0
            for v in vids if float(v.get("views") or 0) > 0
        ]
        action_stats[act] = {
            "count": len(vids),
            "count_valid": n_valid,
            "avg_views": round(act_mean, 1),
            "median_views": round(act_median, 1),
            "trimmed_mean_views": round(act_trimmed, 1),
            "performance_ratio_mean": round((act_mean / channel_mean) if channel_mean > 0 else 1.0, 2),
            "performance_ratio_median": round(ratio_median, 2),
            "composite_watchability_ratio": round(composite_ratio, 2),
            "avg_rwi_48h": rwi_action.get("avg_rwi"),
            "avg_conversion_per_1k": round(statistics.mean(conv_vals), 2) if conv_vals else 0.0,
            "ratio_ci90": [ci_low, ci_high],
            # pewne = cały przedział 90 % po jednej stronie 1.0; inaczej różnica może być przypadkiem
            "reliable": bool(n_valid >= MIN_SAMPLE_FOR_WEIGHT and (ci_low > 1.0 or (ci_high < 1.0 and ci_high > 0))),
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

    # Struktura tytułu jest spleciona z typem akcji (tytuł "1V1" dostają klipy 1v1, które i tak idą najlepiej).
    # Dlatego obok liczymy stosunek do mediany WŁASNEGO typu akcji: to on mówi, co daje sam tytuł.
    _act_median = {a: d.get("median_views", 0) for a, d in action_stats.items()}
    structure_within: Dict[str, List[float]] = defaultdict(list)
    structure_conv: Dict[str, List[float]] = defaultdict(list)
    for v in valid_videos:
        st_name = classify_title_structure(v.get("title", ""))
        vw_num = float(v.get("views", 0) or 0)
        if vw_num > 0:
            conv_score = ((float(v.get("comments") or 0) * 3.0 + float(v.get("subscribers_gained") or 0) * 8.0) / vw_num) * 1000.0
            structure_conv[st_name].append(conv_score)
        a_ = (v.get("action_type") or v.get("frag_type") or infer_frag_type_from_title(v.get("title", ""))).lower().strip()
        base = _act_median.get(a_, 0) or channel_median
        if base > 0:
            structure_within[st_name].append(int(v.get("views", 0) or 0) / base)

    title_structure_stats = {}
    for st, ratios in structure_groups.items():
        convs = structure_conv.get(st) or []
        title_structure_stats[st] = {
            "count": len(ratios),
            "avg_ratio": round(statistics.mean(ratios), 2),
            "median_ratio": round(statistics.median(ratios), 2),
            "median_ratio_within_action": round(statistics.median(structure_within[st]), 2) if structure_within.get(st) else None,
            "avg_conversion_per_1k": round(statistics.mean(convs), 2) if convs else 0.0,
            "reliable": len(ratios) >= MIN_SAMPLE_FOR_STRUCTURE,
        }

    # Najlepsza struktura bazuje na medianie (nie średniej) i wymaga >= 3 próbek
    qualified_structures = [(st, d["median_ratio"]) for st, d in title_structure_stats.items() if d["count"] >= MIN_SAMPLE_FOR_STRUCTURE]
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
        # liczebniki i słowa-wypełniacze: trafiały do avoid/winning przypadkiem ("ONE", "FIVE", "TITLE")
        "ONE", "TWO", "THREE", "FOUR", "FIVE", "TITLE", "JUST", "LIKE", "HOW", "WHY", "CAN", "DID",
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
        if len(ratios) >= MIN_SAMPLE_FOR_KEYWORD:
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

    recipe_experiments = analyze_recipe_experiments(valid_videos)
    gate_calibration = calibrate_quality_gate(valid_videos)
    progression_analysis = _analyze_learning_progression(valid_videos)

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

    # ── KROK 11: Feedback Loop Accuracy (ocena vs realne statystyki) ─────────────
    evaluator_accuracy = {"total_evaluated": 0, "accuracy_pct": 100.0, "correlation": 0.0}
    try:
        try:
            from lol_agent.lol_performance_tracker import _load_performance_log
        except ImportError:
            from lol_performance_tracker import _load_performance_log
        perf_log = _load_performance_log()
        scored_vids = [e for e in perf_log if e.get("quality_score") is not None and e.get("views") is not None]
        if scored_vids:
            # NEUTRAL to brak prognozy, nie trafienie: dawniej podbijał "trafność" do 77 % przy korelacji 0.29
            neutral = sum(1 for e in scored_vids if e.get("prediction_eval") == "NEUTRAL")
            accurate = sum(1 for e in scored_vids if e.get("prediction_eval") in ("ACCURATE_HIGH", "ACCURATE_LOW"))
            decided = len(scored_vids) - neutral
            acc_pct = round((accurate / decided) * 100, 1) if decided else 0.0
            qs_list = [float(e["quality_score"]) for e in scored_vids]
            vw_list = [float(e["views"]) for e in scored_vids]
            if len(scored_vids) >= 3 and statistics.stdev(qs_list) > 0 and statistics.stdev(vw_list) > 0:
                mean_q = statistics.mean(qs_list)
                mean_v = statistics.mean(vw_list)
                cov = sum((q - mean_q) * (v - mean_v) for q, v in zip(qs_list, vw_list)) / (len(scored_vids) - 1)
                corr = round(cov / (statistics.stdev(qs_list) * statistics.stdev(vw_list)), 2)
            else:
                corr = 0.0
            evaluator_accuracy = {
                "total_evaluated": len(scored_vids),
                "accurate_count": accurate,
                "neutral_count": neutral,
                "accuracy_pct": acc_pct,
                "correlation_qs_views": corr,
            }
    except Exception as e_acc:
        _safe_print(f"[Learning] Evaluator accuracy error: {e_acc}")

    # ── Insights ─────────────────────────────────────────────────────────────────
    cadence_flag = "⚠️ CADENCE WARNING: " + cadence_analysis["recommendation"] if cadence_analysis.get("gap_warning") else f"Rytm: {cadence_analysis.get('status', 'ok')} (śr. {cadence_analysis.get('avg_gap_days', '?')} dni)."
    fatigue_flag = "⚠️ TITLE FATIGUE: " + title_fatigue["recommendation"] if title_fatigue.get("fatigue_warning") else "Tytuły: różnorodne."

    geo_top = audience_insights.get("top_countries_30d", []) if isinstance(audience_insights, dict) else []
    geo_str = ", ".join(f"{c['country']}:{c['share_pct']}%" for c in geo_top[:5]) if geo_top else "brak"
    geo_insight = f"Geografia 30d (Top 5): {geo_str}. Zalecane sloty CET: {', '.join(pub_hour_analysis.get('recommended_slots_cet', []))}."
    prog_insight = f"Rozwój algorytmu: {progression_analysis.get('summary', '')}"
    gate48_insight = (
        f"Bramka 48h: {gate_48h_summary.get('total_verified_48h', 0)} zweryfikowanych filmów "
        f"(śr. RWI {gate_48h_summary.get('avg_rwi_score', '?')}/100, FIT_CONFIRMED {gate_48h_summary.get('fit_confirmed_pct', 0.0)}%, "
        f"FALSE_POSITIVE {gate_48h_summary.get('false_positive_pct', 0.0)}%)."
    )

    insights = [
        f"Przeanalizowano {total_count} filmów ({len(valid_videos)} z >= {ZERO_VIEWS_THRESHOLD} views, {zero_views_count} odrzucono jako zera/drafty). Mediana kanału: {int(channel_median)} views, trimmed mean: {int(trimmed_mean)} views (eng: {avg_eng:.1f}%).",
        f"Format o najwyższym performance ratio (mediana): {top_action.upper()} ({action_stats.get(top_action, {}).get('performance_ratio_median', 1.0):.2f}x mediany). Wagi bazują na min {MIN_SAMPLE_FOR_WEIGHT} próbkach — bez tego → waga domyślna.",
        f"Closed Pacing Loop (mediana): Kohorta viral_hit ({pacing_analysis['viral_count']} filmów) → bucket '{pacing_analysis['best_bucket']}' (pewna: {bucket_stats_reliable(pacing_analysis['bucket_stats'])}). Profil: '{rec_pacing}'.",
        f"Title Reinforcement: Najlepsza struktura (mediana ratio): {top_structure}. CTR słowa: {', '.join(winning_keywords[:4])}. Avoid: {', '.join(avoid_keywords[:4])}.",
        f"Evaluator: Solo Bolo={base_kill_weights.get('SOLO BOLO')}pkt, Pentakill={base_kill_weights.get('PENTAKILL')}pkt. Zdegradowane: {', '.join(demoted_formats) or 'brak'} (wymaga N>={MIN_SAMPLE_FOR_DEMOTION}).",
        f"Feedback Loop: Przetestowano {evaluator_accuracy.get('total_evaluated', 0)} filmów pod kątem jakości. Trafność predykcji: {evaluator_accuracy.get('accuracy_pct', 100.0)}% (korelacja QS vs Views: {evaluator_accuracy.get('correlation_qs_views', 0.0):+.2f}).",
        f"A/B Title Testing: {ab_title_analysis['tracked_ab_experiments']} testów w toku. Winning structure: '{ab_title_analysis['winning_title_structure']}'.",
        cadence_flag,
        fatigue_flag,
        ret_insight,
        prog_insight,
        geo_insight,
        gate48_insight,
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
        "retention_robust": summarize_retention(retention_summary.get("videos", []) if isinstance(retention_summary, dict) else []),
        "retention_by_action": retention_by_action,
        "youtube_analytics_v2": audience_insights,
        "learning_progression": progression_analysis,
        "post_48h_gate_summary": gate_48h_summary,
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
        "evaluator_accuracy": evaluator_accuracy,
        "recipe_experiments": recipe_experiments,
        "gate_calibration": gate_calibration,
        "insights": insights,
    }

    # Automatyczna synchronizacja zbioru QLoRA z nowymi danymi 48h i hard_cases
    try:
        try:
            from lol_agent.synapsa_title_trainer import sync_incremental_training_dataset
        except ImportError:
            from synapsa_title_trainer import sync_incremental_training_dataset
        directive["synapsa_retrain_status"] = sync_incremental_training_dataset(
            directive=directive,
            write_dataset=("PYTEST_CURRENT_TEST" not in os.environ),
        )
    except Exception as _syn_sync_err:
        directive["synapsa_retrain_status"] = {"error": str(_syn_sync_err), "retrain_ready": False}

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
    # Dawniej KAŻDY cykl nadpisywał pacing, zoom, slow-mo i głośności wynikiem z koszyka długości (często 6 filmów),
    # kasując to, co użytkownik ustawił w panelu Styl & Feedback. Teraz:
    #   1) klucze ustawione ręcznie ("userLocked": [...] w tuning_config.json albo wpisy w user_feedback_history.json) są nietykalne,
    #   2) cykl pisze tylko przy wyraźnym zwycięzcy (clear_winner) i tylko wtedy, gdy coś się zmienia,
    #   3) każda zmiana zostawia ślad: "autoTuned": {kiedy, z czego, co zmieniono}.
    try:
        if TUNING_FILE.exists():
            with open(TUNING_FILE, "r", encoding="utf-8") as tf:
                tuning_cfg = json.load(tf)
        else:
            tuning_cfg = {}

        proposed = {
            "pacing": rec_pacing,
            "zoomAggression": pacing_analysis["zoom_aggression"],
            "slowmoDuration": pacing_analysis["slowmo_duration"],
            "musicBalance": pacing_analysis["music_balance"],
            "gameSoundBalance": pacing_analysis["game_sound_balance"],
            "titleTone": pacing_analysis["title_tone"],
            "userNotes": pacing_analysis["user_notes"],
        }
        changes = plan_tuning_update(tuning_cfg, proposed, bool(pacing_analysis.get("clear_winner")), _user_locked_keys(tuning_cfg))
        if changes:
            tuning_cfg.update(changes)
            tuning_cfg["autoTuned"] = {"at": datetime.now(timezone.utc).isoformat(), "from": pacing_analysis["best_bucket"],
                                       "changed": sorted(changes.keys())}
            with open(TUNING_FILE, "w", encoding="utf-8") as tf:
                json.dump(tuning_cfg, tf, indent=2, ensure_ascii=False)
            _safe_print(f"[Learning] [TUNING] Auto-tuned {TUNING_FILE.name}: {changes}")
        else:
            _safe_print("[Learning] [TUNING] Bez zmian w tuning_config.json (brak wyraźnego zwycięzcy albo ustawienia użytkownika).")
    except Exception as te:
        _safe_print(f"[Learning] [WARN] Warning tuning_config update: {te}")

    return {
        "status": "success",
        "directive": directive,
        "insights": insights,
    }


_PARAM_TO_KEY = {"pacing": "pacing", "zoom": "zoomAggression", "zoom_aggression": "zoomAggression", "zoomaggression": "zoomAggression",
                 "slowmo": "slowmoDuration", "slowmo_duration": "slowmoDuration", "slowmoduration": "slowmoDuration",
                 "music": "musicBalance", "music_balance": "musicBalance", "musicbalance": "musicBalance",
                 "game_sound": "gameSoundBalance", "game_sound_balance": "gameSoundBalance", "gamesoundbalance": "gameSoundBalance",
                 "title_tone": "titleTone", "titletone": "titleTone"}


def _user_locked_keys(tuning_cfg: Dict[str, Any]) -> set:
    """Klucze tuningu, których cykl uczenia nie może ruszyć: lista "userLocked" + wszystko, co użytkownik zmieniał ręcznie."""
    locked = set(tuning_cfg.get("userLocked") or [])
    try:
        mem = LEARNING_DIR / "user_feedback_history.json"
        if mem.exists():
            with open(mem, "r", encoding="utf-8") as f:
                for entry in json.load(f).get("history", []):
                    key = _PARAM_TO_KEY.get(str(entry.get("param", "")).lower().replace(" ", "_"))
                    if key:
                        locked.add(key)
    except Exception:
        pass
    return locked


def plan_tuning_update(current: Dict[str, Any], proposed: Dict[str, Any], clear_winner: bool, locked: set) -> Dict[str, Any]:
    """Czysta funkcja: co cykl uczenia WOLNO zmienić w tuning_config. Pusty słownik = nie zapisuj nic."""
    if not clear_winner:
        return {}
    return {k: v for k, v in proposed.items() if k not in locked and current.get(k) != v}


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
