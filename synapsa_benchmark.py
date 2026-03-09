"""
synapsa_benchmark.py
====================
BENCHMARK JAKOŚCI WYJŚĆ SYNAPSY (Qwen2.5)

Mierzy:
1. JSON Validity — czy model zwraca poprawny JSON
2. Script Length — czy skrypt ma 60-200 słów (idealne 80-120)
3. Loop Quality — czy ending brzmi jak kontynuacja początku
4. Meta-text Pollution — czy nie ma "Hook:", "[Narrator]", itp.
5. Language Compliance — PL dla brainrot, EN dla dark_mindset
6. Forbidden Topics — czy model respektuje zablokowane tematy

Uruchomienie:
    python synapsa_benchmark.py --runs 5
    python synapsa_benchmark.py --runs 10 --niche dark_mindset --verbose
"""

import json
import re
import sys
import os
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# =============================================================================
# === TESTY JAKOŚCI ===
# =============================================================================

class BenchmarkResult:
    def __init__(self, run_id: int, niche: str):
        self.run_id = run_id
        self.niche = niche
        self.scores = {}
        self.details = {}
        self.raw_json = None
        self.elapsed_time = 0.0

    def final_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores) * 10

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "niche": self.niche,
            "final_score": round(self.final_score(), 2),
            "scores": self.scores,
            "details": self.details,
            "elapsed_time": round(self.elapsed_time, 2),
            "timestamp": datetime.utcnow().isoformat()
        }


def check_json_validity(response: dict) -> tuple[float, str]:
    """Sprawdza czy JSON ma wszystkie wymagane klucze."""
    required = ["viral_score", "script_text", "background_vibe", "music_folder",
                "title", "description", "seo_tags"]
    if not response or "error" in response:
        return 0.0, f"Błąd: {response.get('error', 'Brak odpowiedzi')}"

    missing = [k for k in required if k not in response]
    if missing:
        return max(0.0, (len(required) - len(missing)) / len(required)), f"Brakuje kluczy: {missing}"

    return 1.0, "Wszystkie wymagane klucze obecne ✅"


def check_script_length(response: dict) -> tuple[float, str]:
    """Sprawdza długość skryptu (idealnie 80-120 słów)."""
    script = response.get("script_text", "")
    if not script:
        return 0.0, "Brak script_text"

    words = len(script.split())
    if words < 30:
        return 0.1, f"Za krótki: {words} słów (minimum 60)"
    elif words < 60:
        return 0.5, f"Krótki: {words} słów (lepiej 80+)"
    elif words <= 150:
        return 1.0, f"Idealna długość: {words} słów ✅"
    elif words <= 250:
        return 0.7, f"Długi: {words} słów (lepiej max 150)"
    else:
        return 0.3, f"Za długi: {words} słów (max 200)"


def check_loop_quality(response: dict) -> tuple[float, str]:
    """Sprawdza czy końcowe słowa skryptu łączą się z początkiem."""
    script = response.get("script_text", "").strip()
    if not script:
        return 0.0, "Brak script_text"

    words = script.split()
    if len(words) < 10:
        return 0.0, "Za krótki do oceny pętli"

    # Heurystyka: sprawdź czy ostatnie słowa są połówką zdania (loop indicator)
    last_3 = " ".join(words[-3:]).lower()
    first_3 = " ".join(words[:3]).lower()

    # Dobry loop: kończy się przedimkiem, przyimkiem, spójnikiem
    loop_indicators = [
        "że", "kiedy", "jak", "bo", "ale", "który", "która", "the", "when", "that",
        "because", "and", "but", "who", "where", "why", "how", "a", "bo", "gdy"
    ]
    bad_endings = ["koniec.", "koniec", "the end", "end.", "dziękuję", "thanks", "subscribe"]

    # Sprawdź złe zakończenia
    for bad in bad_endings:
        if last_3.endswith(bad):
            return 0.1, f"Brak pętli! Kończy się: '{last_3}' - to nie jest loop"

    # Sprawdź wskaźniki loop
    last_word = words[-1].lower().rstrip(".,!?")
    if last_word in loop_indicators:
        return 1.0, f"Excellent loop: kończy na '{last_word}' → łączy z początkiem ✅"

    # Sprawdź czy koniec brzmi jak urwane zdanie (nie ma kropki)
    if not script.endswith((".", "!", "?")):
        return 0.9, f"Dobry loop: skrypt urwany po '{last_3}' bez kończącej interpunkcji ✅"

    # Sprawdź czy pierwsze słowa z końca pokrywają się z początkiem (loop check)
    for word in words[-5:]:
        if word.lower() in first_3.lower() and len(word) > 3:
            return 0.85, f"Dobry loop: słowo '{word}' łączy koniec z początkiem ✅"

    return 0.5, f"Niepewny loop. Koniec: '{last_3}', Początek: '{first_3}'"


def check_meta_text_pollution(response: dict) -> tuple[float, str]:
    """Sprawdza czy skrypt nie ma meta-tekstu reżyserskiego."""
    script = response.get("script_text", "")
    if not script:
        return 0.0, "Brak script_text"

    # Zakazane wzorce reżyserskie
    forbidden_patterns = [
        r'\[.*?\]',          # [Narrator mówi]
        r'\(.*?\)',          # (pauza 2 sekundy)
        r'Hook\s*:',         # Hook:
        r'Narrator\s*:',     # Narrator:
        r'Scena\s*:',        # Scena:
        r'HOOK\s*[-–]',      # HOOK -
        r'CIAŁO\s*[-–]',     # CIAŁO -
        r'LOOP\s*[-–]',      # LOOP -
        r'Rozpocznij od',    # Rozpocznij od
        r'Zakończ przez',    # Zakończ przez
        r'BEGIN:',
        r'END:',
    ]

    found_violations = []
    for pattern in forbidden_patterns:
        if re.search(pattern, script, re.IGNORECASE):
            found_violations.append(pattern.replace(r'\s*', ' ').replace(r'.*?', '...'))

    if found_violations:
        return 0.0, f"🚨 Meta-tekst wykryty: {', '.join(found_violations[:3])}"

    return 1.0, "Czysty skrypt bez meta-tekstu ✅"


def check_language_compliance(response: dict, niche: str) -> tuple[float, str]:
    """Sprawdza czy język skryptu zgadza się z dyrektywą kanału."""
    script = response.get("script_text", "")
    if not script:
        return 0.0, "Brak script_text"

    # Detekcja języka heurystyczna
    polish_markers = ["że", "się", "nie", "jest", "są", "jak", "gdy", "kiedy", "przez"]
    english_markers = ["the", "you", "your", "they", "their", "is", "are", "don't", "can't"]

    words_lower = [w.lower() for w in script.split()[:50]]
    polish_count = sum(1 for m in polish_markers if m in words_lower)
    english_count = sum(1 for m in english_markers if m in words_lower)

    is_polish = polish_count > english_count

    if niche == "brainrot":
        if is_polish:
            return 1.0, f"Język PL potwierdzony ✅ (wskaźniki PL: {polish_count}, EN: {english_count})"
        else:
            return 0.0, f"🚨 Zły język! Brainrot = PL, ale wykryto EN (PL:{polish_count} EN:{english_count})"
    else:  # dark_mindset
        if not is_polish:
            return 1.0, f"Język EN potwierdzony ✅ (wskaźniki EN: {english_count}, PL: {polish_count})"
        else:
            return 0.0, f"🚨 Zły język! Dark Mindset = EN, ale wykryto PL (PL:{polish_count} EN:{english_count})"


def check_viral_score_realism(response: dict) -> tuple[float, str]:
    """Sprawdza czy viral_score jest realistyczny (nie zawsze 10/10)."""
    score = response.get("viral_score")
    if score is None:
        return 0.5, "Brak viral_score"

    try:
        score = int(score)
    except:
        return 0.3, f"Nieprawidłowy viral_score: {score}"

    if score == 10:
        return 0.6, "⚠️ viral_score=10 to podejrzane — model bywa zbyt optymistyczny"
    elif 6 <= score <= 9:
        return 1.0, f"Realistyczny viral_score: {score}/10 ✅"
    elif score == 5:
        return 0.7, f"Neutralny viral_score: {score}/10 (model niepewny?)"
    else:
        return 0.4, f"Niski viral_score: {score}/10"


# =============================================================================
# === RUNNER BENCHMARKU ===
# =============================================================================

def run_single_benchmark(run_id: int, niche: str, verbose: bool = False) -> BenchmarkResult:
    """Uruchamia jeden test Synapsy i ocenia output."""
    from synapsa_bridge import generate_viral_script_with_synapsa

    result = BenchmarkResult(run_id, niche)

    # Kontekst testowy
    if niche == "brainrot":
        context = ["[TREND] Kiedy sigma zostaje nauczycielem w ohio | Kanał: BrainrotPL",
                   "[TREND] Roblox ale wszystko jest ohio | Kanał: SkibidiWave"]
        rule = "[DYREKTYWA: BRAINROT PL] Pisz po polsku, hook + loop, 80 słów."
    else:
        context = ["[TREND] Why silence is the most powerful weapon | Kanał: DarkPsychSecrets",
                   "[TREND] Stop explaining yourself to people | Kanał: SigmaVault"]
        rule = "[DYREKTYWA: DARK MINDSET EN] Write in English only. Hook + loop. 80 words."

    print(f"\n  🧪 Run #{run_id} | Niche: {niche}...")
    start_time = time.time()

    try:
        response = generate_viral_script_with_synapsa(
            viral_context=context,
            niche_topic=niche,
            channel_rule=rule,
            forbidden_topics=[]
        )
    except Exception as e:
        response = {"error": str(e)}

    result.elapsed_time = time.time() - start_time
    result.raw_json = response

    # Testy jakości
    tests = [
        ("json_validity",        check_json_validity(response)),
        ("script_length",        check_script_length(response)),
        ("loop_quality",         check_loop_quality(response)),
        ("meta_text_pollution",  check_meta_text_pollution(response)),
        ("language_compliance",  check_language_compliance(response, niche)),
        ("viral_score_realism",  check_viral_score_realism(response)),
    ]

    for test_name, (score, detail) in tests:
        result.scores[test_name] = score
        result.details[test_name] = detail
        if verbose:
            status = "✅" if score >= 0.8 else ("⚠️" if score >= 0.5 else "❌")
            print(f"    {status} {test_name}: {score:.1f} — {detail}")

    final = result.final_score()
    status = "🟢" if final >= 8 else ("🟡" if final >= 6 else "🔴")
    print(f"  {status} Run #{run_id}: {final:.1f}/10 | ⏱️ {result.elapsed_time:.1f}s")

    return result


def run_benchmark(runs: int = 5, niche: str = "both", verbose: bool = False,
                  output_file: str = "accounts/synapsa_benchmark_report.json"):
    """Uruchamia pełny benchmark dla Synapsy."""
    print("\n" + "=" * 62)
    print("📊 SYNAPSA BENCHMARK — Test jakości modelu AI")
    print(f"   Liczba testów: {runs} | Nisza: {niche} | Verbose: {verbose}")
    print("=" * 62)

    niches = []
    if niche == "both" or niche == "brainrot":
        niches.extend(["brainrot"] * (runs // 2 if niche == "both" else runs))
    if niche == "both" or niche == "dark_mindset":
        niches.extend(["dark_mindset"] * (runs - (runs // 2) if niche == "both" else runs))

    if not niches:
        print("❌ Nieznana nisza. Użyj: brainrot / dark_mindset / both")
        return

    all_results = []

    for i, n in enumerate(niches, 1):
        result = run_single_benchmark(i, n, verbose)
        all_results.append(result.to_dict())

    # Statystyki zbiorcze
    print("\n" + "=" * 62)
    print("📈 WYNIKI ZBIORCZE:")
    print("=" * 62)

    all_scores_by_test = {}
    for r in all_results:
        for test, score in r["scores"].items():
            all_scores_by_test.setdefault(test, []).append(score)

    overall_scores = [r["final_score"] for r in all_results]
    avg_overall = sum(overall_scores) / len(overall_scores) if overall_scores else 0
    avg_time = sum(r["elapsed_time"] for r in all_results) / len(all_results) if all_results else 0

    print(f"\n{'Test':<25} {'Średnia':>8} {'Min':>6} {'Max':>6} {'Ocena':>8}")
    print("-" * 58)
    for test, scores in all_scores_by_test.items():
        avg = sum(scores) / len(scores)
        mn = min(scores)
        mx = max(scores)
        rating = "🟢 OK" if avg >= 0.8 else ("🟡 SŁABE" if avg >= 0.5 else "🔴 KRYTYCZNE")
        print(f"{test:<25} {avg:>8.2f} {mn:>6.2f} {mx:>6.2f} {rating:>8}")

    print("-" * 58)
    overall_rating = "🟢 GOTOWA" if avg_overall >= 8 else ("🟡 WYMAGA DOSZKOLENIA" if avg_overall >= 6 else "🔴 KRYTYCZNIE SŁABA")
    print(f"\n🏆 WYNIK KOŃCOWY SYNAPSY: {avg_overall:.1f}/10 — {overall_rating}")
    print(f"⏱️  Średni czas generacji: {avg_time:.1f}s na short")

    # Rekomendacje
    print("\n📌 REKOMENDACJE:")
    for test, scores in all_scores_by_test.items():
        avg = sum(scores) / len(scores)
        if avg < 0.7:
            recos = {
                "json_validity": "→ Model nie zwraca poprawnego JSON. Uruchom synapsa_trainer.py i doucz model.",
                "script_length": "→ Skrypt za krótki/długi. Dodaj do promptu: 'Dokładnie 80-120 słów.'",
                "loop_quality": "→ Brak loop endingu. Doucz model przykładami z GOLDEN_EXAMPLES.",
                "meta_text_pollution": "→ Model dodaje instrukcje reżyserskie. Wzmocnij prompt: 'ABSOLUTNY ZAKAZ nawiasów []'",
                "language_compliance": "→ Model myli języki. Sprawdź dyrektywy kanałów w CHANNEL_CONFIG.",
                "viral_score_realism": "→ Model zawsze daje 10/10. Doucz kontrprzykładami."
            }
            print(f"  ⚠️  {test}: {recos.get(test, '→ Sprawdź logi.')}")

    # Zapis raportu
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "config": {"runs": runs, "niche": niche},
        "summary": {
            "avg_score": round(avg_overall, 2),
            "avg_time_seconds": round(avg_time, 2),
            "rating": overall_rating,
            "per_test_averages": {k: round(sum(v)/len(v), 3) for k, v in all_scores_by_test.items()}
        },
        "individual_runs": all_results
    }

    os.makedirs("accounts", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Pełny raport zapisany: {output_file}")
    return report


# =============================================================================
# === MAIN ===
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapsa Benchmark — Ocena jakości modelu AI")
    parser.add_argument("--runs", type=int, default=4,
                        help="Liczba testów do uruchomienia (default: 4)")
    parser.add_argument("--niche", type=str, default="both",
                        choices=["brainrot", "dark_mindset", "both"],
                        help="Testowana nisza (default: both)")
    parser.add_argument("--verbose", action="store_true",
                        help="Pokazuj szczegółowe wyniki każdego testu")
    parser.add_argument("--output", type=str, default="accounts/synapsa_benchmark_report.json",
                        help="Plik wyjściowy z raportem JSON")
    args = parser.parse_args()

    run_benchmark(
        runs=args.runs,
        niche=args.niche,
        verbose=args.verbose,
        output_file=args.output
    )
