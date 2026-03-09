"""
synapsa_trainer.py
==================
GENERATOR DANYCH SZKOLENIOWYCH DLA SYNAPSY (Qwen2.5 LoRA Fine-tuning)

Zadanie:
1. Wczytuje viral_patterns.json (wyniki faktycznych wideo z kanałów)
2. Wczytuje topic_history.json (co było już opublikowane)
3. Generuje pary (prompt → idealny JSON) dla doszkolenienia modelu
4. Zapisuje zestaw do JSONL (format Unsloth/HuggingFace fine-tuning)

Uruchomienie:
    python synapsa_trainer.py --output training_data.jsonl
    python synapsa_trainer.py --output training_data.jsonl --augment 50
"""

import json
import os
import random
import argparse
from datetime import datetime


# =============================================================================
# === WZORCOWE PRZYKŁADY SZKOLENIOWE (Hardcoded golden examples) ===
# =============================================================================

GOLDEN_EXAMPLES_BRAINROT = [
    {
        "niche": "brainrot polska",
        "rule": "[DYREKTYWA KANAŁU: BRAINROT - JĘZYK POLSKI]",
        "context": ["[TREND] Kiedy sigma gracz trafił do ohio school | Kanał: BrainrotPL"],
        "ideal_output": {
            "viral_score": 9,
            "vs_top_shorts": "Lepszy: mocniejszy hook z absurdem. Gorszy: brak prawdziwej twarzy.",
            "viral_reasoning": "Ohio + szkoła = idealna kombinacja dla 13-17 lat. Hook zaskakuje.",
            "script_text": "Wyobraź sobie, że przychodzisz do szkoły i widzisz, że każdy uczeń mówi tylko sigma i ohio. Nauczycielka krzyczy W rizz, dyrektor wchodzi w subway surfers mode. Ty jeden jesteś normalny, ale po dwóch minutach już nie. Bo to jest właśnie ohio, wyobraź sobie,",
            "background_vibe": "subway surfers gameplay no copyright 4k vertical",
            "music_folder": "brainrot",
            "title": "💀 Kiedy Cała Szkoła Staje się OHIO #brainrot",
            "description": "Normalni lekcji tu nie ma 😂 zostaw lajka jeśli twoja szkoła też jest ohio! #brainrot #ohio #sigma #shorts #viral",
            "seo_tags": ["brainrot", "ohio", "sigma", "szkoła", "polska", "shorts", "viral", "gen-z", "tiktok"]
        }
    },
    {
        "niche": "brainrot polska",
        "rule": "[DYREKTYWA KANAŁU: BRAINROT - JĘZYK POLSKI]",
        "context": ["[TREND] Roblox obby ale ona jest 100% niemożliwa | Kanał: SkibidiPL"],
        "ideal_output": {
            "viral_score": 8,
            "vs_top_shorts": "Lepszy: loop ending niewidoczny dla widza. Gorszy: brak gameplay w tle.",
            "viral_reasoning": "Impossible Roblox obby to hit 2025-2026 wśród 10-15 lat. Krótka frustracja = loop.",
            "script_text": "Próbowałem przejść tę obby przez trzy godziny i za każdym razem wypadałem w tym samym miejscu. Serio, jakiś deweloper musi nienawidzić ludzi. Ale w chwili kiedy prawie rzuciłem kompem coś kliknęło, nacisnąłem skok i stałem na końcu. Stałem trzy sekundy, a potem wypadłem, bo za długo próbowałem przejść tę obby przez",
            "background_vibe": "roblox obby impossible gameplay no copyright funny",
            "music_folder": "brainrot",
            "title": "😤 Ta Obby Roblox ZNISZCZYŁA MOJE ŻYCIE 💀 #roblox",
            "description": "Spróbuj sam i napisz jak długo wytrzymałeś 😂 #roblox #obby #shorts #viral #gaming #brainrot",
            "seo_tags": ["roblox", "obby", "impossible", "brainrot", "gaming", "shorts", "viral", "polska", "gameplay"]
        }
    }
]

GOLDEN_EXAMPLES_DARK_MINDSET = [
    {
        "niche": "dark mindset psychology",
        "rule": "[DYREKTYWA KANAŁU: DARK MINDSET - JĘZYK ANGIELSKI]",
        "context": ["[TREND] Silent Manipulation tactics nobody talks about | Kanał: DarkPsychSecrets"],
        "ideal_output": {
            "viral_score": 9,
            "vs_top_shorts": "Better: specific behavior pattern people recognize instantly. Worse: no face on camera.",
            "viral_reasoning": "Recognition hook - viewer thinks 'wait, someone did this to me'. High rewatch rate.",
            "script_text": "You already know someone who does this. They never argue with you directly. Instead they go quiet, they pull back just enough to make you anxious, and they wait. They wait for you to come back and apologize for something they caused. That silence is a weapon, and you already know someone who does",
            "background_vibe": "dark rainy city night walk noir cinematic no copyright 4k",
            "music_folder": "dark_mindset",
            "title": "😶‍🌫️ This Silence Is A Weapon — You Know Someone Like This",
            "description": "They never argue. They just go quiet and wait. Recognize this before it's too late. 💀\n#darkpsychology #manipulation #mindset #psychology #shorts #viral",
            "seo_tags": ["dark psychology", "manipulation", "silent treatment", "psychology", "mindset", "sigma", "shorts", "viral", "power dynamics"]
        }
    },
    {
        "niche": "dark mindset psychology",
        "rule": "[DYREKTYWA KANAŁU: DARK MINDSET - JĘZYK ANGIELSKI]",
        "context": ["[TREND] why they respect you when you stop caring | Kanał: SigmaVault"],
        "ideal_output": {
            "viral_score": 10,
            "vs_top_shorts": "Better: actionable insight + personal relevance. Equal: same alpha-male aesthetic.",
            "viral_reasoning": "Aspirational identity content. People share what they want others to think about them.",
            "script_text": "The moment you stop needing their approval they start chasing yours. People can feel desperation. They can smell when you need them and they will use it. But the second you don't, the second you genuinely stop caring what they think, something shifts. They start wondering what changed. They start watching you more carefully. Because the only people who get respect are the ones who don't beg for the moment you stop needing their",
            "background_vibe": "sigma male aesthetic dark moody office no copyright cinematic",
            "music_folder": "dark_mindset",
            "title": "🧠 Stop Caring And Watch Them Start Chasing You 💀",
            "description": "They respect you when you stop needing them. This is how social dynamics actually work. 🔥\n#sigma #psychology #darkpsychology #mindset #shorts #viral",
            "seo_tags": ["sigma", "dark psychology", "respect", "mindset", "alpha", "psychology", "self improvement", "shorts", "viral"]
        }
    }
]

# =============================================================================
# === GENERATOR KONTRPRZYKŁADÓW (Bad output → nauczaj co NIE robić) ===
# =============================================================================

BAD_EXAMPLES = [
    {
        "niche": "brainrot polska",
        "description": "Błąd: Meta-tekst reżyserski w script_text",
        "bad_output": {
            "script_text": "Hook: Wyobraź sobie... [Narrator mówi energicznie] Ciało: Tutaj opowiedz historię. [Zakończ]",
            "viral_score": 3,
        },
        "correction": "ZABRONIONE: Nawiasy [], instrukcje reżyserskie, słowa 'Hook:', 'Narrator'. Pisz TYLKO czysty tekst do lektora."
    },
    {
        "niche": "brainrot polska",
        "description": "Błąd: Brak loop ending",
        "bad_output": {
            "script_text": "Dzisiaj opowiem wam o najdziwniejszym dniu w szkole. Był to piątek, gdy wszystko poszło nie tak. Na końcu wszyscy się śmialiśmy. Koniec.",
            "viral_score": 4,
        },
        "correction": "LOOP ENDING: Ostatnie słowo/zdanie musi składniowo łączyć się z pierwszym. 'Koniec.' niszczy pętlę YT Shorts."
    },
    {
        "niche": "dark mindset psychology",
        "description": "Błąd: Odpowiedź po polsku dla kanału EN",
        "bad_output": {
            "script_text": "Wiesz że manipulacja to coś złego. Uważaj na takie osoby.",
            "viral_score": 2,
        },
        "correction": "KANAŁ dark_mindset = TYLKO ANGIELSKI. 'English ONLY.' Jest tak zapisane w dyrektywie kanału."
    }
]


# =============================================================================
# === AUGMENTACJA NA PODSTAWIE viral_patterns.json ===
# =============================================================================

def load_viral_patterns() -> dict:
    patterns_file = "accounts/viral_patterns.json"
    if not os.path.exists(patterns_file):
        print("⚠️  Brak viral_patterns.json - brak danych z rzeczywistych wyświetleń.")
        return {}
    with open(patterns_file, "r", encoding="utf-8") as f:
        return json.load(f)


def patterns_to_training_examples(patterns: dict) -> list:
    """Konwertuje dane z viral_patterns.json na pary treningowe."""
    examples = []
    for channel, data in patterns.items():
        top_videos = data.get("top_videos", [])
        avg_views = data.get("avg_views", 0)

        for vid in top_videos:
            title = vid.get("title", "")
            views = vid.get("views", 0)
            likes = vid.get("likes", 0)

            if not title or views < 1000:
                continue

            # Ocena viral score na podstawie realnych danych
            viral_score = min(10, int(views / max(avg_views, 1) * 5) + 5) if avg_views > 0 else 6

            niche = "brainrot polska" if channel == "brainrot" else "dark mindset psychology"
            lang_note = "JĘZYK POLSKI" if channel == "brainrot" else "JĘZYK ANGIELSKI"

            example = {
                "source": "viral_patterns",
                "channel": channel,
                "title_reference": title,
                "views": views,
                "viral_score_real": viral_score,
                "training_note": (
                    f"Ten tytuł osiągnął {views:,} wyświetleń ({likes:,} likes). "
                    f"Naucz się jego wzorca: hook, emocja, długość."
                ),
                "niche": niche,
                "prompt_for_similar": (
                    f"Kanał {channel} ({lang_note}). "
                    f"Wzorzec tytułu który zadziałał: '{title}'. "
                    f"Wygeneruj INNY, ale podobnie angażujący skrypt."
                )
            }
            examples.append(example)

    return examples


# =============================================================================
# === GENERATOR JSONL (Format HuggingFace/Unsloth) ===
# =============================================================================

def build_prompt(example: dict) -> str:
    """Buduje prompt w formacie szkoleniowym (Alpaca style)."""
    niche = example.get("niche", "brainrot polska")
    rule = example.get("rule", "Bądź kreatywny.")
    context = "\n".join(example.get("context", ["Brak kontekstu - improwizuj."]))

    return f"""### Instruction:
Jesteś Master Director AI generującym skrypty YouTube Shorts.

Nisza: {niche}
Dyrektywa kanału: {rule}

Kontekst trendów (TOP wideo z ostatnich 7 dni):
{context}

Wygeneruj TYLKO poprawny JSON wg schematu. Zero słów poza JSON.

### Response:"""


def example_to_jsonl(example: dict) -> dict:
    """Konwertuje example do formatu JSONL (instruction + output)."""
    prompt = build_prompt(example)
    output = json.dumps(example["ideal_output"], ensure_ascii=False)

    return {
        "text": f"{prompt}\n{output}",
        "instruction": prompt,
        "output": output,
        "metadata": {
            "niche": example.get("niche"),
            "viral_score": example["ideal_output"].get("viral_score"),
            "source": "golden_example",
        }
    }


def generate_training_file(output_path: str, augment_count: int = 0):
    """Główna funkcja generująca plik JSONL do fine-tuningu."""
    print(f"\n🧬 SYNAPSA TRAINER — Generowanie danych szkoleniowych")
    print(f"   Output: {output_path}")
    print(f"   Augmentacja z viral_patterns: {augment_count} przykładów")
    print("=" * 60)

    all_examples = []

    # 1. Złote przykłady (hardcoded, sprawdzone)
    for ex in GOLDEN_EXAMPLES_BRAINROT + GOLDEN_EXAMPLES_DARK_MINDSET:
        all_examples.append(example_to_jsonl(ex))
    print(f"✅ Dodano {len(GOLDEN_EXAMPLES_BRAINROT + GOLDEN_EXAMPLES_DARK_MINDSET)} złotych przykładów")

    # 2. Przykłady z rzeczywistych wyników (viral_patterns.json)
    patterns = load_viral_patterns()
    if patterns:
        pattern_examples = patterns_to_training_examples(patterns)
        print(f"✅ Załadowano {len(pattern_examples)} wzorców z viral_patterns.json")
        # Zapisz wzorce do osobnego pliku referencyjnego
        with open("accounts/training_references.json", "w", encoding="utf-8") as f:
            json.dump(pattern_examples, f, indent=2, ensure_ascii=False)
        print(f"   📄 Wzorce zapisane w accounts/training_references.json")

    # 3. Raport kontrprzykładów (co jest złe)
    corrections_path = "accounts/synapsa_corrections.json"
    with open(corrections_path, "w", encoding="utf-8") as f:
        json.dump(BAD_EXAMPLES, f, indent=2, ensure_ascii=False)
    print(f"✅ Zapisano {len(BAD_EXAMPLES)} kontrprzykładów (co robić ŹLE) → {corrections_path}")

    # 4. Augmentacja (losowe warianty tematów)
    if augment_count > 0:
        augmented = augment_training_data(augment_count)
        all_examples.extend(augmented)
        print(f"✅ Wygenerowano {len(augmented)} augmentowanych przykładów")

    # 5. Zapis JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n🎉 GOTOWE! Zestaw treningowy: {len(all_examples)} przykładów → {output_path}")
    print(f"\n📌 Następny krok — fine-tuning Unsloth:")
    print(f"   python -m unsloth.finetune \\")
    print(f"       --model unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit \\")
    print(f"       --dataset {output_path} \\")
    print(f"       --output_dir moje_ai_adaptery \\")
    print(f"       --max_steps 200 \\")
    print(f"       --learning_rate 2e-4")
    print(f"\n⚠️  Pamiętaj: im więcej realnych wideo w viral_patterns.json, tym lepszy model!")

    return output_path


def augment_training_data(count: int) -> list:
    """Generuje dodatkowe warianty tematów przez losowe kombinacje."""
    augmented = []

    brainrot_hooks = [
        "Wyobraź sobie że", "Nikt mi nie uwierzy ale", "To nie mogło się przydarzyć ale",
        "Serio nikt nie mówi o tym że", "Gdybyś wiedział co się stało kiedy"
    ]
    dark_hooks = [
        "The person you trust most", "You already know someone who does this",
        "They never tell you this but", "Most people don't realize", "Watch what happens when"
    ]
    brainrot_topics = ["szkoła", "roblox", "minecraft", "nauczyciel", "rodzice", "telefon", "egzamin"]
    dark_topics = ["silence", "manipulation", "respect", "loneliness", "ambition", "power", "control"]

    for _ in range(count // 2):
        # Brainrot
        hook = random.choice(brainrot_hooks)
        topic = random.choice(brainrot_topics)
        augmented.append({
            "text": f"### Instruction:\nNisza: brainrot polska\n### Response:\n{{\"viral_score\": 7, \"script_text\": \"{hook} {topic} działa inaczej niż myślisz...\", \"title\": \"😂 {topic.capitalize()} #brainrot #shorts\", \"music_folder\": \"brainrot\"}}",
            "instruction": f"brainrot | hook: {hook} | topic: {topic}",
            "output": f"viral_score=7 | {hook} {topic}...",
            "metadata": {"niche": "brainrot", "source": "augmented"}
        })

        # Dark mindset
        hook2 = random.choice(dark_hooks)
        topic2 = random.choice(dark_topics)
        augmented.append({
            "text": f"### Instruction:\nNiche: dark mindset\n### Response:\n{{\"viral_score\": 8, \"script_text\": \"{hook2} about {topic2}...\", \"title\": \"🧠 {topic2.capitalize()} Truth #psychology\", \"music_folder\": \"dark_mindset\"}}",
            "instruction": f"dark_mindset | hook: {hook2} | topic: {topic2}",
            "output": f"viral_score=8 | {hook2} {topic2}...",
            "metadata": {"niche": "dark_mindset", "source": "augmented"}
        })

    return augmented


# =============================================================================
# === MAIN ===
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapsa Trainer — Generator danych szkoleniowych")
    parser.add_argument("--output", type=str, default="accounts/training_data.jsonl",
                        help="Ścieżka wyjściowa do pliku JSONL")
    parser.add_argument("--augment", type=int, default=20,
                        help="Liczba augmentowanych przykładów (default: 20)")
    args = parser.parse_args()

    os.makedirs("accounts", exist_ok=True)
    generate_training_file(args.output, args.augment)
