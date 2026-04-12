"""
refresh_facts.py — Tygodniowy Odświeżacz Bazy Faktów & Selektor Tematu
=======================================================================
Uruchamiaj raz w tygodniu (poniedziałek rano) LUB przed startem pipeline'u.

Działanie:
  1. Resetuje accounts/used_facts.json  → 120+ faktów znów dostępnych
  2. Analizuje smart_analysis JSONy     → które słowa/tematy mają najwyższe views
  3. Rankinguje TOPIC_ROTATION_POOL     → priorytetyzuje bestseller na przodzie
  4. Zapisuje topic_rotation.json       → pipeline od razu bierze zwycięski temat
  5. Czyści topic_history z sesji       → usuwa wpisy bez video_id (nie wrzucone na YT)

Użycie:
    python refresh_facts.py                    # pełny refresh
    python refresh_facts.py --reset-only       # tylko reset used_facts
    python refresh_facts.py --analyze-only     # tylko analiza + ranking bez resetu
    python refresh_facts.py --days 14          # analizuj ostatnie 14 dni (domyśl: 7)
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Ścieżki ──────────────────────────────────────────────────────────────────
USED_FACTS_FILE      = os.path.join("accounts", "used_facts.json")
TOPIC_ROTATION_FILE  = os.path.join("accounts", "topic_rotation.json")
TOPIC_HISTORY_FILE   = os.path.join("accounts", "topic_history.json")
SMART_ANALYSIS_DIR   = "."
DIRECTIVE_FILE       = "adaptation_directive.json"
PROFILE_NAME         = "dark_mindset"

# ── Kolory konsoli ────────────────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"
C = "\033[96m"; B = "\033[1m";  X = "\033[0m"

# ── Pula tematów (lustro z agent_dark_psychology.py) ─────────────────────────
TOPIC_ROTATION_POOL = [
    "dark psychology body language social dominance",
    "neuropsychology decision making cognitive biases",
    "dark psychology respect social influence power",
    "persuasion techniques negotiation covert influence",
    "narcissist manipulation red flags covert emotional abuse",
    "self mastery self discipline stoic philosophy sigma mindset",
    "social intelligence reading people microexpressions emotions",
    "covert communication nonverbal secrets psychological power",
]

# Mapowanie słów kluczowych → indeks tematu w puli
KEYWORD_TO_TOPIC_IDX = {
    "body": 0, "language": 0, "dominance": 0, "posture": 0,
    "neuroscience": 1, "brain": 1, "decision": 1, "bias": 1, "cognitive": 1,
    "respect": 2, "influence": 2, "power": 2, "status": 2,
    "persuasion": 3, "negotiation": 3, "technique": 3,
    "narcissist": 4, "manipulation": 4, "toxic": 4, "abuse": 4, "red": 4,
    "discipline": 5, "stoic": 5, "sigma": 5, "self": 5, "master": 5,
    "social": 6, "reading": 6, "microexpression": 6, "emotion": 6,
    "communication": 7, "nonverbal": 7, "covert": 7, "secret": 7,
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. RESET used_facts.json
# ─────────────────────────────────────────────────────────────────────────────
def reset_used_facts(profile: str = PROFILE_NAME) -> int:
    """Czyści pulę użytych faktów → wszystkie fakty znów dostępne."""
    data = {}
    if os.path.exists(USED_FACTS_FILE):
        try:
            with open(USED_FACTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    old_count = len(data.get(profile, []))
    data[profile] = []

    os.makedirs(os.path.dirname(USED_FACTS_FILE), exist_ok=True)
    with open(USED_FACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n{G}✅ [RESET] Wyzerowano {old_count} użytych faktów dla profilu '{profile}'.{X}")
    print(f"   Wszystkie 120+ faktów znów dostępne dla pipeline'u.")
    return old_count


# ─────────────────────────────────────────────────────────────────────────────
# 2. ANALIZA SMART_ANALYSIS JSONów
# ─────────────────────────────────────────────────────────────────────────────
def load_videos_from_snapshots(days_back: int = 7) -> list:
    """Ładuje dane wideo z lokalnych smart_analysis_*.json."""
    videos = []
    cutoff = datetime.now() - timedelta(days=days_back)
    seen_ids = set()

    for fname in sorted(os.listdir(SMART_ANALYSIS_DIR), reverse=True):
        if not fname.startswith("smart_analysis_") or not fname.endswith(".json"):
            continue
        try:
            date_str = fname.replace("smart_analysis_", "").replace(".json", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                continue
        except Exception:
            continue

        try:
            with open(os.path.join(SMART_ANALYSIS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            for v in data.get("top_5", []) + data.get("last_2", []):
                vid_id = v.get("id") or v.get("video_id", "")
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    videos.append(v)
        except Exception:
            pass

    return videos


def score_topics_from_videos(videos: list) -> dict:
    """
    Dla każdego tematu w TOPIC_ROTATION_POOL oblicza łączny score:
    score = sum(views * velocity_bonus) dla filmów powiązanych z danym tematem.
    """
    topic_scores = defaultdict(float)
    topic_video_counts = defaultdict(int)

    for v in videos:
        title = (v.get("title") or "").lower()
        views = v.get("views", 0)
        velocity = v.get("velocity", 0)
        bonus = 1 + min(velocity / 10.0, 3.0)  # velocity boost max x4
        score = views * bonus

        # Znajdź pasujący temat
        matched_idx = None
        best_matches = 0
        for word, idx in KEYWORD_TO_TOPIC_IDX.items():
            if word in title:
                matches_for_idx = sum(1 for w, i in KEYWORD_TO_TOPIC_IDX.items()
                                      if i == idx and w in title)
                if matches_for_idx > best_matches:
                    best_matches = matches_for_idx
                    matched_idx = idx

        if matched_idx is not None:
            topic_scores[matched_idx] += score
            topic_video_counts[matched_idx] += 1

    return dict(topic_scores), dict(topic_video_counts)


# ─────────────────────────────────────────────────────────────────────────────
# 3. RANKING TEMATÓW I ZAPIS DO topic_rotation.json
# ─────────────────────────────────────────────────────────────────────────────
def update_topic_rotation(topic_scores: dict, topic_counts: dict,
                          days_back: int = 7) -> str:
    """
    Wybiera najlepiej performujący temat i ustawia go jako startowy w rotacji.
    Zwraca nazwę wybranego tematu.
    """
    # Oblicz ranking
    ranked = []
    for idx, topic in enumerate(TOPIC_ROTATION_POOL):
        score = topic_scores.get(idx, 0)
        count = topic_counts.get(idx, 0)
        avg_score = score / max(count, 1)
        ranked.append((idx, topic, score, count, avg_score))

    ranked.sort(key=lambda x: x[2], reverse=True)  # sort by total score

    print(f"\n{C}── RANKING TEMATÓW (ostatnie {days_back} dni) ────────────────────────{X}\n")
    max_score = max((r[2] for r in ranked), default=1) or 1
    for rank, (idx, topic, score, count, avg) in enumerate(ranked):
        bar_len = int(score / max_score * 25)
        bar = "█" * bar_len + "." * (25 - bar_len)
        medal = ["🥇", "🥈", "🥉"][rank] if rank < 3 else f"#{rank+1}"
        col = G if rank == 0 else (Y if rank < 3 else X)
        print(f"  {medal} {col}{topic[:45]:<45}{X}")
        print(f"      Score: {score:,.0f} | Filmów: {count} | Avg: {avg:,.0f} | {bar}")

    # Zwycięski temat
    if ranked and ranked[0][2] > 0:
        winner_idx = ranked[0][0]
        winner_topic = ranked[0][1]
        print(f"\n{G}{B}🏆 ZWYCIĘSKI TEMAT TYGODNIA: '{winner_topic}'{X}")
    else:
        # Brak danych — użyj domyślnego (body language najlepiej konwertuje)
        winner_idx = 0
        winner_topic = TOPIC_ROTATION_POOL[0]
        print(f"\n{Y}⚠️  Brak danych historycznych — domyślny temat: '{winner_topic}'{X}")

    # Zapisz do topic_rotation.json — ustaw winner_idx jako last_idx-1
    # żeby następny call _get_next_topic() zwrócił właśnie zwycięzcę
    state = {"last_idx": winner_idx - 1}
    with open(TOPIC_ROTATION_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    print(f"   📂 topic_rotation.json zaktualizowany → next topic: #{winner_idx+1}")
    return winner_topic


# ─────────────────────────────────────────────────────────────────────────────
# 4. CZYSZCZENIE topic_history (usuń wpisy z dzisiaj bez wrzucenia na YT)
# ─────────────────────────────────────────────────────────────────────────────
def clean_topic_history_today(profile: str = PROFILE_NAME) -> int:
    """
    Usuwa z topic_history wpisy z DZISIAJ — bo user usunął te shortsy z YT.
    Zachowuje wpisy ze starszych dni.
    """
    if not os.path.exists(TOPIC_HISTORY_FILE):
        return 0

    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = data.get(profile, [])
    before = len(history)

    # Zachowaj tylko wpisy NIE z dzisiaj
    kept = [h for h in history
            if not h.get("timestamp", "").startswith(today_str)]
    removed = before - len(kept)

    if removed > 0:
        data[profile] = kept
        # Backup
        import shutil
        shutil.copy2(TOPIC_HISTORY_FILE, TOPIC_HISTORY_FILE + ".bak")
        with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"\n{Y}🗑️  [HISTORY] Usunięto {removed} wpisów z dziś "
              f"(nieudane/usunięte shortsy). Pozostało: {len(kept)}.{X}")
    else:
        print(f"\n{G}✅ [HISTORY] Brak wpisów z dziś do usunięcia.{X}")

    return removed


# ─────────────────────────────────────────────────────────────────────────────
# 5. WEEKLY SCHEDULER CHECK (czy czas na tygodniowy refresh)
# ─────────────────────────────────────────────────────────────────────────────
def should_do_weekly_refresh() -> bool:
    """Sprawdza czy minął tydzień od ostatniego resetu."""
    refresh_log = os.path.join("accounts", "last_facts_refresh.json")
    if not os.path.exists(refresh_log):
        return True
    try:
        with open(refresh_log, "r", encoding="utf-8") as f:
            d = json.load(f)
        last = datetime.fromisoformat(d.get("last_refresh", "2000-01-01"))
        return (datetime.now() - last).days >= 7
    except Exception:
        return True


def mark_refresh_done():
    """Zapisuje datę ostatniego resetu."""
    refresh_log = os.path.join("accounts", "last_facts_refresh.json")
    os.makedirs("accounts", exist_ok=True)
    with open(refresh_log, "w", encoding="utf-8") as f:
        json.dump({"last_refresh": datetime.now().isoformat()}, f)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Tygodniowy odświeżacz bazy faktów")
    parser.add_argument("--reset-only",    action="store_true",
                        help="Tylko zresetuj used_facts.json — bez analizy")
    parser.add_argument("--analyze-only",  action="store_true",
                        help="Tylko analiza + ranking bez resetu faktów")
    parser.add_argument("--days",          type=int, default=7,
                        help="Ile dni wstecz analizować (domyślnie 7)")
    parser.add_argument("--clean-today",   action="store_true",
                        help="Wyczyść wpisy z dzisiaj z topic_history (usunięte shortsy)")
    parser.add_argument("--force",         action="store_true",
                        help="Wymuś refresh nawet jeśli nie minął tydzień")
    args = parser.parse_args()

    print(f"\n{B}{'='*70}")
    print(f"  🔄 TYGODNIOWY ODŚWIEŻACZ BAZY FAKTÓW & SELEKTOR TEMATU")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Zakres: {args.days} dni")
    print(f"{'='*70}{X}\n")

    # ── Krok 0: Czy czyścić wpisy z dziś ──
    if args.clean_today:
        clean_topic_history_today(PROFILE_NAME)

    # ── Krok 1: Reset użytych faktów ──
    if not args.analyze_only:
        if args.force or should_do_weekly_refresh() or args.reset_only:
            reset_used_facts(PROFILE_NAME)
            if not args.reset_only:
                mark_refresh_done()
        else:
            next_refresh = "za kilka dni"
            print(f"{Y}ℹ️  Tygodniowy reset NOT wymagany jeszcze. "
                  f"Użyj --force aby wymusić. {X}")

    # ── Krok 2: Analiza danych historycznych ──
    if not args.reset_only:
        print(f"\n{C}📊 Ładowanie danych z ostatnich {args.days} dni...{X}")
        videos = load_videos_from_snapshots(days_back=args.days)

        if videos:
            print(f"   Znaleziono {len(videos)} unikalnych filmów w snapshots.")
            topic_scores, topic_counts = score_topics_from_videos(videos)
            best_topic = update_topic_rotation(topic_scores, topic_counts, days_back=args.days)

            # ── Krok 3: Podsumowanie ──
            print(f"\n{C}{'='*70}{X}")
            print(f"{B}📋 PODSUMOWANIE REFRESHU:{X}")
            print(f"  ✅ Facts DB zresetowana — 120+ faktów dostępnych")
            print(f"  🏆 Optymalny temat dla pipeline'u: '{best_topic}'")
            print(f"  📂 topic_rotation.json zaktualizowany")
            print(f"\n  💡 Uruchom teraz: python agent_dark_psychology.py")
        else:
            print(f"{Y}  ⚠️  Brak danych historycznych (nie znaleziono smart_analysis JSONów "
                  f"z ostatnich {args.days} dni). Używam domyślnej kolejności tematów.{X}")
            # Domyślna rotacja — ustaw body language jako start
            state = {"last_idx": -1}
            with open(TOPIC_ROTATION_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            print(f"  📂 topic_rotation.json → reset do domyślnej kolejności")

    print(f"\n{G}{'='*70}")
    print(f"  🎯 REFRESH ZAKOŃCZONY — pipeline gotowy do uruchomienia!")
    print(f"{'='*70}{X}\n")


if __name__ == "__main__":
    main()
