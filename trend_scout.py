"""
trend_scout.py  — Codzienny zwiad trendów  
==========================================
Uruchamiany automatycznie PRZED generacją treści przez agent_dark_psychology.py.

Co robi:
  1. Pobiera z YouTube Search API ~30 najnowszych Shorts (ostatnie 24-48h)
     z niszowych zapytań: dark psychology, body language, manipulation, mindset
  2. Analizuje tytuły: format (QUESTION/STATEMENT), słowa kluczowe, tematy
  3. Wyciąga TOP trendy dnia (formaty + słowa + motyw)
  4. Wstrzykuje wyniki do adaptation_directive.json jako "today_trends"
  5. Zwraca krótki string do os.environ["SYNAPSA_TREND_TODAY"] dla promptu AI

Użycie samodzielne:
  python trend_scout.py
"""

import os
import sys
import json
import re
import pickle
from datetime import datetime, timezone, timedelta
from collections import Counter

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# ─── Config ──────────────────────────────────────────────────────────────────
PROFILE_NAME   = "dark_mindset"
TOKEN_FILE     = os.path.join("accounts", f"{PROFILE_NAME}_token.pickle")
DIRECTIVE_FILE = "adaptation_directive.json"
REPORT_PREFIX  = "trend_report"

# Zapytania do YouTube Search — nisze + pokrewne
SEARCH_QUERIES = [
    "dark psychology body language shorts",
    "manipulation tactics psychology shorts",
    "mindset respect body language shorts",
    "silent power techniques shorts",
    "dark psychology facts secrets",
    "human behavior psychology tricks shorts",
]

G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"


# ─── Auth ─────────────────────────────────────────────────────────────────────
def _get_yt_client():
    if not os.path.exists(TOKEN_FILE):
        print(f"{R}❌ Brak tokenu: {TOKEN_FILE}{X}")
        return None
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)


# ─── 1. Pobieranie trendów ────────────────────────────────────────────────────
def fetch_trending_dark_psychology(yt, hours_back=48):
    """Pobiera najnowsze Shorts z niszy dark psychology z ostatnich X godzin."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_videos = []

    for query in SEARCH_QUERIES:
        try:
            resp = yt.search().list(
                part         = "snippet",
                q            = query,
                type         = "video",
                videoDuration= "short",
                order        = "date",
                publishedAfter=since,
                maxResults   = 10,
                regionCode   = "PL",
            ).execute()
            for item in resp.get("items", []):
                vid_id = item["id"].get("videoId")
                if not vid_id:
                    continue
                snippet = item["snippet"]
                title   = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")
                pub     = snippet.get("publishedAt", "")
                if not title:
                    continue
                all_videos.append({
                    "id":       vid_id,
                    "title":    title,
                    "channel":  channel,
                    "published":pub,
                    "query":    query,
                    "link":     f"https://youtube.com/shorts/{vid_id}",
                })
        except Exception as e:
            print(f"  {Y}⚠️  Błąd zapytania '{query}': {e}{X}")

    # Deduplikacja po ID
    seen = set()
    unique = []
    for v in all_videos:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique.append(v)

    print(f"  {G}✅ Znaleziono {len(unique)} unikalnych Shorts z ostatnich {hours_back}h{X}")
    return unique


# ─── 2. Analiza wzorców ───────────────────────────────────────────────────────
def detect_title_format(title: str) -> str:
    stripped = title.strip()
    if re.match(r"^\[.+?\]", stripped):
        return "PREFIX_BRACKET"
    q_words = r"^(have|can|are|do|does|is|why|how|what|when|who|which|would|could|did|will|stop)\b"
    if stripped.endswith("?") or re.match(q_words, stripped.lower()):
        return "QUESTION"
    if re.search(r"\b(stop|watch out|warning|secret)\b", stripped.lower()):
        return "IMPERATIVE_SHOCK"
    return "STATEMENT"


def analyze_trend_patterns(videos: list) -> dict:
    """Analizuje tytuły: format, słowa kluczowe, motyw, hooking patterns."""
    STOPWORDS = {"the","and","is","in","to","a","of","this","you","they","your","for",
                 "with","not","at","are","or","but","their","will","that","when","it",
                 "its","from","by","an","be","was","were","has","had","have","do","does",
                 "if","just","so","has","all","one","can","about","who","what","how"}

    format_counter = Counter()
    word_counter   = Counter()
    topic_counter  = Counter()
    hook_patterns  = []

    TOPIC_MAP = {
        "body language": ["body", "language", "posture", "gesture", "eye", "contact", "stance", "gaze"],
        "manipulation":  ["manipulat", "control", "trick", "deceiv", "gaslightin", "narcissist"],
        "silence/power": ["silence", "silent", "quiet", "power", "dominant", "dominance", "alpha"],
        "respect":       ["respect", "command", "authority", "effortless", "dignit"],
        "psychology":    ["psychology", "psycholog", "brain", "mind", "behavior", "cognitive"],
        "dark secrets":  ["secret", "dark", "hidden", "forbidden", "truth", "exposed"],
    }

    for v in videos:
        title = v["title"]
        fmt   = detect_title_format(title)
        format_counter[fmt] += 1

        # Słowa kluczowe
        words = re.findall(r"\b[a-zA-Z]{3,}\b", title.lower())
        for w in words:
            if w not in STOPWORDS:
                word_counter[w] += 1

        # Tematy
        title_lower = title.lower()
        for topic, keywords in TOPIC_MAP.items():
            if any(kw in title_lower for kw in keywords):
                topic_counter[topic] += 1

        # Hook patterns: pierwsze 5 słów tytułu
        first_5 = " ".join(title.split()[:5])
        if first_5:
            hook_patterns.append(first_5)

    total = len(videos) if videos else 1
    return {
        "total_videos_analyzed": len(videos),
        "format_distribution": dict(format_counter),
        "dominant_format": format_counter.most_common(1)[0][0] if format_counter else "QUESTION",
        "top_keywords_today": [kw for kw, _ in word_counter.most_common(15)],
        "hot_topics_today": [t for t, _ in topic_counter.most_common(5)],
        "hook_patterns_sample": list(set(hook_patterns))[:8],
    }


# ─── 3. Generowanie podsumowania dla promptu AI ───────────────────────────────
def summarize_for_prompt(patterns: dict, videos: list) -> str:
    fmt        = patterns["dominant_format"]
    kw_str     = ", ".join(f"'{w}'" for w in patterns["top_keywords_today"][:10])
    topics_str = " / ".join(patterns["hot_topics_today"][:4]) or "dark psychology"
    sample_titles = [v["title"][:60] for v in videos[:4]]
    titles_str = "\n   ".join(f"• {t}" for t in sample_titles)

    fmt_advice = {
        "QUESTION":       "Używaj formatu PYTANIA — to dominuje w trendach dziś.",
        "STATEMENT":      "Twierdzenia dominują dziś — zacznij od mocnego faktu.",
        "IMPERATIVE_SHOCK": "Dziś działa szok/imperatyw — zacznij od 'Stop scrolling.' lub 'Watch this.'",
        "PREFIX_BRACKET": "UWAGA: PREFIX_BRACKET w trendach — NIE stosuj (historycznie słabe).",
    }.get(fmt, "Używaj pytań.")

    summary = (
        f"TODAY'S TREND INTELLIGENCE ({datetime.now().strftime('%Y-%m-%d')}):\n"
        f"Dominant format: {fmt} — {fmt_advice}\n"
        f"Hot topics RIGHT NOW: {topics_str}\n"
        f"Trending keywords today: {kw_str}\n"
        f"Top hook patterns seen today:\n   {titles_str}\n"
        f"INSTRUCTION: Align your script with these trends. Create a FRESH angle on: {topics_str.split('/')[0].strip()}."
    )
    return summary


# ─── 4. Wstrzykiwanie do dyrektywy ───────────────────────────────────────────
def inject_into_directive(patterns: dict, trend_summary: str):
    directive = {}
    if os.path.exists(DIRECTIVE_FILE):
        try:
            with open(DIRECTIVE_FILE, "r", encoding="utf-8") as f:
                directive = json.load(f)
        except Exception:
            pass

    directive["today_trends"] = {
        "fetched_at":        datetime.now(timezone.utc).isoformat(),
        "patterns":          patterns,
        "prompt_injection":  trend_summary,
    }

    with open(DIRECTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(directive, f, indent=4, ensure_ascii=False)
    print(f"  {G}✅ Trendy wstrzyknięte do {DIRECTIVE_FILE}{X}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def run_trend_scout() -> str:
    """Główna funkcja — zwraca trend_summary string do wstrzyknięcia w prompt."""
    print(f"\n{C}{'═'*60}{X}")
    print(f"{C}  📡 TREND SCOUT — Co dziś jest na topie YouTube?{X}")
    print(f"{C}  Czas: {datetime.now().strftime('%Y-%m-%d %H:%M')}{X}")
    print(f"{C}{'═'*60}{X}\n")

    yt = _get_yt_client()
    if not yt:
        fallback = "TODAY'S TRENDS: API unavailable. Use proven QUESTION format with keywords: respect, body language, command."
        print(f"{Y}⚠️  YouTube API niedostępne. Używam fallbacku.{X}")
        return fallback

    print(f"{C}🔍 Szukam najnowszych Shorts z niszy dark psychology...{X}")
    videos = fetch_trending_dark_psychology(yt, hours_back=48)

    if not videos:
        fallback = "TODAY'S TRENDS: No fresh data. Use QUESTION format: 'Have you noticed how...' + respect/body language."
        print(f"{Y}⚠️  Brak wyników z ostatnich 48h. Fallback.{X}")
        return fallback

    print(f"\n{C}📊 Analiza wzorców...{X}")
    patterns = analyze_trend_patterns(videos)

    # Raport CLI
    print(f"\n  Format dominujący:  {B}{patterns['dominant_format']}{X}")
    print(f"  Gorące tematy:      {', '.join(patterns['hot_topics_today'][:4])}")
    print(f"  Top słowa dziś:     {', '.join(patterns['top_keywords_today'][:8])}")
    print(f"  Hook patterns próbka:")
    for hp in patterns['hook_patterns_sample'][:4]:
        print(f"    ➤ \"{hp}...\"")

    trend_summary = summarize_for_prompt(patterns, videos)

    # Zapisz raport JSON
    report_file = f"{REPORT_PREFIX}_{datetime.now().strftime('%Y-%m-%d')}.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "videos_found": len(videos),
        "patterns":     patterns,
        "top_videos":   videos[:10],
        "trend_summary":trend_summary,
    }
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    print(f"\n  {G}📄 Raport trendów: {report_file}{X}")

    # Wstrzyknij do directive
    inject_into_directive(patterns, trend_summary)

    print(f"\n{B}📋 TREND SUMMARY (wstrzykiwany do AI):{X}")
    for line in trend_summary.split("\n"):
        print(f"  {line}")
    print()

    return trend_summary


if __name__ == "__main__":
    result = run_trend_scout()
    print(f"\n{G}{'═'*60}{X}")
    print(f"{G}✅ Trend Scout zakończony.{X}")
