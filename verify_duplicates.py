"""
verify_duplicates.py — Weryfikator Duplikatów Shortsów
======================================================
Skanuje topic_history.json i detect duplikaty/bardzo podobne shortsy.
Używa NLP (SequenceMatcher + tokenizacji) do wykrycia parafraz.

Użycie:
    python verify_duplicates.py                    # Raport ze wszystkich kanałów
    python verify_duplicates.py --fix              # Usuwa duplikaty z historii (zachowuje pierwsze)
    python verify_duplicates.py --profile dark_mindset  # Tylko jeden kanał
    python verify_duplicates.py --threshold 0.35   # Próg podobieństwa (domyślnie 0.40)
"""

import os
import sys
import json
import difflib
import re
import argparse
from datetime import datetime
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

TOPIC_HISTORY_FILE = "accounts/topic_history.json"

G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"


def normalize_text(text: str) -> str:
    """Normalizuje tekst do porównania: małe litery, bez interpunkcji, bez emoji."""
    text = text.lower().strip()
    # Usuń emoji i znaki specjalne
    text = re.sub(r'[^\w\s]', ' ', text)
    # Kompresuj spacje
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_unique_words(text: str) -> set:
    """Zwraca zbiór unikalnych słów dłuższych niż 3 znaki (content words)."""
    stopwords = {
        "most", "people", "this", "that", "they", "your", "with", "have", "here",
        "when", "some", "what", "into", "you're", "their", "from", "ever", "once",
        "never", "after", "before", "about", "which", "there", "these", "those",
        "follow", "more", "dark", "psychology", "using", "someone"
    }
    words = re.findall(r'\b[a-z]{4,}\b', text.lower())
    return {w for w in words if w not in stopwords}


def calculate_similarity(text_a: str, text_b: str) -> dict:
    """
    Oblicza podobieństwo na 3 poziomach:
    - sequence: klasyczny SequenceMatcher ratio
    - jaccard: współczynnik Jaccarda na content words
    - combined: ważona średnia
    """
    norm_a = normalize_text(text_a)
    norm_b = normalize_text(text_b)

    # 1. Sequence matcher
    seq_ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    # 2. Jaccard na content words
    words_a = get_unique_words(norm_a)
    words_b = get_unique_words(norm_b)
    if words_a or words_b:
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        jaccard = intersection / union if union > 0 else 0.0
    else:
        jaccard = 0.0

    # 3. Ważona: sequence bardziej miarodajny dla krótkich tekstów
    combined = (seq_ratio * 0.6) + (jaccard * 0.4)

    return {
        "sequence": round(seq_ratio, 3),
        "jaccard": round(jaccard, 3),
        "combined": round(combined, 3),
    }


def find_duplicates(history: list, threshold: float = 0.40) -> list:
    """
    Szuka par duplikatów w historii shortsów.
    Zwraca listę dicts: {idx_a, idx_b, title_a, title_b, similarity, type}
    """
    duplicates = []
    n = len(history)

    for i in range(n):
        for j in range(i + 1, n):
            item_a = history[i]
            item_b = history[j]

            title_a = item_a.get("title", "")
            title_b = item_b.get("title", "")
            script_a = item_a.get("script", "")
            script_b = item_b.get("script", "")

            # Sprawdź podobieństwo tytułu
            title_sim = calculate_similarity(title_a, title_b)

            # Sprawdź podobieństwo skryptu (bardziej krytyczne)
            script_sim = {"sequence": 0, "jaccard": 0, "combined": 0}
            if script_a and script_b:
                script_sim = calculate_similarity(script_a, script_b)

            # Klasyfikuj typ duplikatu
            dup_type = None
            if script_sim["combined"] >= threshold:
                if script_sim["sequence"] >= 0.85:
                    dup_type = "IDENTYCZNY_SKRYPT"
                elif script_sim["combined"] >= 0.60:
                    dup_type = "PRAWIE_KOPIA"
                else:
                    dup_type = "PARAFRAZA"
            elif title_sim["combined"] >= 0.70:
                dup_type = "PODOBNY_TYTUŁ"

            if dup_type:
                duplicates.append({
                    "idx_a": i,
                    "idx_b": j,
                    "title_a": title_a,
                    "title_b": title_b,
                    "script_preview_a": script_a[:100] if script_a else "",
                    "script_preview_b": script_b[:100] if script_b else "",
                    "timestamp_a": item_a.get("timestamp", "?"),
                    "timestamp_b": item_b.get("timestamp", "?"),
                    "title_similarity": title_sim,
                    "script_similarity": script_sim,
                    "type": dup_type,
                })

    return duplicates


def print_duplicate_report(profile: str, history: list, duplicates: list, threshold: float):
    """Wyświetla sformatowany raport duplikatów dla jednego profilu."""
    print(f"\n{C}{'='*70}{X}")
    print(f"{B}📋 PROFIL: {profile.upper()} | Filmów w historii: {len(history)}{X}")
    print(f"{C}{'='*70}{X}")

    if not duplicates:
        print(f"{G}✅ Brak duplikatów! Wszystkie {len(history)} shortsów ma unikalną treść.{X}")
        return

    # Grupuj wg typu
    by_type = defaultdict(list)
    for d in duplicates:
        by_type[d["type"]].append(d)

    type_colors = {
        "IDENTYCZNY_SKRYPT": R,
        "PRAWIE_KOPIA": R,
        "PARAFRAZA": Y,
        "PODOBNY_TYTUŁ": Y,
    }
    type_icons = {
        "IDENTYCZNY_SKRYPT": "🚨",
        "PRAWIE_KOPIA": "⚠️",
        "PARAFRAZA": "📝",
        "PODOBNY_TYTUŁ": "🏷️",
    }

    print(f"\n{R}{B}❌ Znaleziono {len(duplicates)} par duplikatów (próg: {threshold:.0%}):{X}\n")

    for dup_type, dups in sorted(by_type.items(), key=lambda x: -len(x[1])):
        col = type_colors.get(dup_type, Y)
        icon = type_icons.get(dup_type, "⚠️")
        print(f"{col}{icon} {dup_type} ({len(dups)} par):{X}")
        print(f"{'─'*65}")

        for d in dups:
            sim_script = d["script_similarity"]["combined"]
            sim_title = d["title_similarity"]["combined"]

            # Format czasu
            ts_a = d["timestamp_a"][:16].replace("T", " ") if d["timestamp_a"] != "?" else "?"
            ts_b = d["timestamp_b"][:16].replace("T", " ") if d["timestamp_b"] != "?" else "?"

            print(f"\n  Film #{d['idx_a']+1} [{ts_a}]:")
            print(f"    Tytuł:  {d['title_a'][:70]}")
            if d["script_preview_a"]:
                print(f"    Skrypt: {d['script_preview_a'][:80]}...")

            print(f"\n  Film #{d['idx_b']+1} [{ts_b}]:")
            print(f"    Tytuł:  {d['title_b'][:70]}")
            if d["script_preview_b"]:
                print(f"    Skrypt: {d['script_preview_b'][:80]}...")

            print(f"\n  {col}📊 Podobieństwo skryptu: {sim_script:.0%} | Tytuł: {sim_title:.0%}{X}")
            print(f"  {'─'*60}")

    print(f"\n{R}{B}PODSUMOWANIE: {len(duplicates)} duplikatów wykrytych w profilu '{profile}'!{X}")
    print(f"  Użyj --fix aby usunąć duplikaty z historii (zachowa pierwsze).")


def remove_duplicates(history: list, threshold: float = 0.40) -> tuple:
    """
    Usuwa duplikaty z historii, zachowując pierwszy unikatowy wpis.
    Zwraca (cleaned_history, removed_count).
    """
    if not history:
        return history, 0

    unique = [history[0]]
    removed = []

    for i in range(1, len(history)):
        item = history[i]
        is_dup = False

        for existing in unique:
            script_new = item.get("script", "")
            script_old = existing.get("script", "")
            title_new = item.get("title", "")
            title_old = existing.get("title", "")

            if script_new and script_old:
                sim = calculate_similarity(script_new, script_old)
                if sim["combined"] >= threshold:
                    is_dup = True
                    break
            else:
                # Bez skryptu porównaj tylko tytuły
                t_sim = calculate_similarity(title_new, title_old)
                if t_sim["combined"] >= 0.75:
                    is_dup = True
                    break

        if is_dup:
            removed.append(item)
        else:
            unique.append(item)

    return unique, len(removed)


def main():
    parser = argparse.ArgumentParser(description="Weryfikator Duplikatów Shortsów")
    parser.add_argument("--profile", default=None, help="Tylko jeden profil (np. dark_mindset)")
    parser.add_argument("--threshold", type=float, default=0.40,
                        help="Próg podobieństwa 0.0-1.0 (domyślnie 0.40)")
    parser.add_argument("--fix", action="store_true",
                        help="Usuń duplikaty z historii (zachowuje pierwsze, backup w .bak)")
    parser.add_argument("--json", action="store_true",
                        help="Wyjście w formacie JSON (do integracji z pipeline'm)")
    args = parser.parse_args()

    print(f"\n{B}{'='*70}")
    print(f"  🔍 WERYFIKATOR DUPLIKATÓW SHORTSÓW")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Próg: {args.threshold:.0%}")
    print(f"{'='*70}{X}\n")

    if not os.path.exists(TOPIC_HISTORY_FILE):
        print(f"{R}❌ Brak pliku historii: {TOPIC_HISTORY_FILE}{X}")
        print(f"   Uruchom agenta przynajmniej raz, by zbudować historię.")
        sys.exit(1)

    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"{R}❌ Błąd odczytu historii: {e}{X}")
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"{R}❌ Nieprawidłowy format historii (oczekiwano dict z profilami).{X}")
        sys.exit(1)

    # Filtruj profil jeśli podano
    profiles = [args.profile] if args.profile else list(data.keys())
    profiles = [p for p in profiles if p in data]

    if not profiles:
        print(f"{Y}⚠️  Brak profilu '{args.profile}' w historii. Dostępne: {list(data.keys())}{X}")
        sys.exit(1)

    all_results = {}
    total_dups = 0

    for profile in profiles:
        history = data.get(profile, [])
        duplicates = find_duplicates(history, threshold=args.threshold)
        total_dups += len(duplicates)

        all_results[profile] = {
            "videos_count": len(history),
            "duplicates_count": len(duplicates),
            "duplicates": duplicates,
        }

        if not args.json:
            print_duplicate_report(profile, history, duplicates, args.threshold)

    # Tryb JSON
    if args.json:
        output = {
            "generated_at": datetime.now().isoformat(),
            "threshold": args.threshold,
            "total_duplicates": total_dups,
            "profiles": all_results,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        sys.exit(0 if total_dups == 0 else 1)

    # Podsumowanie globalne
    print(f"\n{C}{'='*70}{X}")
    print(f"{B}📊 PODSUMOWANIE GLOBALNE:{X}")
    for profile, res in all_results.items():
        dup_col = R if res["duplicates_count"] > 0 else G
        dup_icon = "❌" if res["duplicates_count"] > 0 else "✅"
        print(f"  {dup_icon} {profile}: {res['videos_count']} filmów, "
              f"{dup_col}{res['duplicates_count']} duplikatów{X}")
    print(f"\n  {R if total_dups > 0 else G}Łącznie: {total_dups} duplikatów{X}")

    # Tryb FIX
    if args.fix and total_dups > 0:
        print(f"\n{Y}🔧 TRYB FIX: Usuwanie duplikatów z historii...{X}")

        # Backup
        backup_file = TOPIC_HISTORY_FILE + ".bak"
        import shutil
        shutil.copy2(TOPIC_HISTORY_FILE, backup_file)
        print(f"  💾 Backup: {backup_file}")

        fixed_data = {}
        for profile in profiles:
            history = data.get(profile, [])
            cleaned, removed_count = remove_duplicates(history, threshold=args.threshold)
            fixed_data[profile] = cleaned
            print(f"  {G}✅ {profile}: usunięto {removed_count} duplikatów, \
pozostało {len(cleaned)} unikalnych.{X}")

        # Zachowaj pozostałe profile bez zmian
        for p in data:
            if p not in fixed_data:
                fixed_data[p] = data[p]

        with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(fixed_data, f, indent=4, ensure_ascii=False)

        print(f"\n{G}✅ Historia zaktualizowana: {TOPIC_HISTORY_FILE}{X}")
    elif args.fix and total_dups == 0:
        print(f"\n{G}✅ Brak duplikatów do usunięcia.{X}")

    sys.exit(0 if total_dups == 0 else 1)


if __name__ == "__main__":
    main()
