"""
synapsa_analysis_trainer.py
============================
Uczy Synapsę ANALITYCZNEGO MYŚLENIA o trendach YouTube.

W odróżnieniu od synapsa_trainer.py (który uczy FORMAT wyjścia),
ten skrypt uczy Synapsę ROZUMOWANIA:
  - Dlaczego jedno wideo eksploduje, a inne nie
  - Jak interpretować engagement rate vs raw views
  - Jak dobrać hook do niszy
  - Jak zamienić obserwację trendu na lepszy skrypt

Wynik: dodatkowe przykłady JSONL dołączone do training_data.jsonl
"""

import json
import os
from datetime import datetime

TRAINING_FILE = "accounts/training_data.jsonl"
os.makedirs("accounts", exist_ok=True)

# =============================================================================
# === PRZYKŁADY ANALITYCZNE — uczą Synapsę "rozumienia" ===
# =============================================================================

ANALYSIS_EXAMPLES = [

    # ── 1. ENGAGEMENT vs VIEWS — kluczowa lekcja ────────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI analizującą trendy YouTube Shorts.\n\n"
            "Otrzymałeś te dane o 2 filmach z tego tygodnia:\n\n"
            "Film A: '2 Dark Manipulation Techniques'\n"
            "  views: 94,971 | likes: 0 | engagement: 0.0%\n"
            "  Kanał: Roar Within\n\n"
            "Film B: '3 Manipulation Techniques That Create Dominance'\n"
            "  views: 17,487 | likes: 2,371 | engagement: 13.6%\n"
            "  Kanał: dark_psychology_tips\n\n"
            "PYTANIE: Który film jest CENNIEJSZYM wzorcem do naśladowania? Dlaczego?\n"
            "Odpowiedz w JSON.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "analiza": {
                "lepszy_wzorzec": "Film B (13.6% engagement)",
                "uzasadnienie": (
                    "Film B ma 13.6% engagement rate — to DIAMENTOWY wynik. Normalna wartość dla Shorts to 1-3%. "
                    "Film A ma 94k views ale 0 lajków — to prawdopodobnie viral przez algorytm (rekomendacje ślepe) "
                    "lub clickbait bez wartości dla widza. Film B z 2371 lajkami przy 17k views = widz ZAANGAŻOWAŁ SIĘ. "
                    "Zaangażowany widz wraca, subskrybuje, komentuje. To są prawdziwe fani, nie przypadkowi scrollerzy."
                ),
                "wniosek_dla_skryptu": (
                    "Wzorzec B jest mocniejszy: 'X Manipulation Techniques That Create [konkretny efekt]'. "
                    "Słowo 'Dominance' uruchamia aspiracyjną tożsamość. Widz nie tylko ogląda — identyfikuje się. "
                    "Generując skrypt, preferuj konkretny efekt w tytule nad samą liczbą technik."
                ),
                "metryka_kluczowa": "engagement_rate > raw_views",
                "prog_diamond_engagement": "5%+",
            }
        }, ensure_ascii=False),
        "metadata": {
            "niche": "dark_mindset",
            "source": "analytical_training",
            "lesson": "engagement_vs_views",
        }
    },

    # ── 2. HOOK PATTERN — kluczowe słowa które działają ─────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI analizującą trendy YouTube Shorts.\n\n"
            "Na podstawie TOP trendów z tego tygodnia dla niszy dark_mindset:\n"
            "  - '5 Dark Psychology Tricks to Control anyone' (99k views)\n"
            "  - '2 Dark Manipulation Techniques' (94k views)\n"
            "  - '3 Manipulation Techniques That Create Dominance' (17k, 13.6% engagement)\n"
            "  - 'The Ego Hack Trick 🧠 (Get Help Easily)' (35k views)\n"
            "  - 'Silent Manipulation tactics nobody talks about' (wzorzec premium)\n\n"
            "ZADANIE: Wyciągnij wzorzec hookowy który DZIAŁA w tej niszy.\n"
            "Wygeneruj JSON z analizą + przykładowy hook dla nowego skryptu.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "wzorzec_hookowy": {
                "formula_1": "[LICZBA] Dark [SŁOWO_KLUCZOWE] [TECHNIKI/TRICKS] to [EFEKT]",
                "formula_2": "The [RZECZ] [Hack/Secret/Truth] [EMOJI] ([OBIETNICA])",
                "formula_3": "[SŁOWO_KLUCZOWE] [TECHNIKI] nobody talks about",
                "kluczowe_slowa_proven": ["Dark", "Manipulation", "Control", "Dominance", "Ego", "Silent", "Psychology"],
                "unikaj": ["motivation", "mindset alone", "self-help generic", "subscribe to learn"],
                "dlaczego_liczby_dzialaja": (
                    "'5 tricks', '2 techniques', '3 methods' — liczby dają KONKRETNOŚĆ. "
                    "Widz wie dokładnie ile dostanie. Redukuje friction (nie musi się zastanawiać czy warto)."
                ),
                "dlaczego_dark_dziala": (
                    "Słowo 'dark' uruchamia zakazany owoc + ciekawość + poczucie elitarności. "
                    "'Wiem coś czego inni nie wiedzą' = dopamina. Nie używaj go zbyt często — straci siłę."
                ),
            },
            "nowy_hook_do_skryptu": (
                "3 Silent Tactics People Use to Control You Without You Knowing"
            ),
            "viral_score_przewidywany": 8,
        }, ensure_ascii=False),
        "metadata": {
            "niche": "dark_mindset",
            "source": "analytical_training",
            "lesson": "hook_pattern_extraction",
        }
    },

    # ── 3. BRAINROT — wzorzec tygodnia ──────────────────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI analizującą trendy YouTube Shorts.\n\n"
            "TOP trendy brainrot PL z tego tygodnia:\n"
            "  - 'subscribe or be gay 🏳️‍🌈 #roblox #trending' (40k views, hook: absurd + kontrowersjyność)\n"
            "  - 'META TECHNETTA vs THE WAVE #roblox #escapetsunamiforbrainrots' (27k views, hook: gaming)\n"
            "  - 'СКИБИДИ УДАЧА: WYБИЛ НОВОГО БРЕЙНРОТА В ROBLOX 💀' (11k views, hook: gaming + emoji)\n\n"
            "ANALIZA: Co jest WSPÓLNYM mianownikiem? Jaki wzorzec generuje viral brainrot PL?\n"
            "ZASTOSUJ WNIOSKI: Zaproponuj 3 nowe tytuły + hook do skryptu.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "analiza_wspólna": {
                "numer_1_wspolny_mianownik": "Roblox jako platforma — nadal #1 dla 10-15 lat",
                "numer_2": "Absurd i kontrowersja podbijają CTR — widz klika bo 'co?!'",
                "numer_3": "Hashtagi branżowe w tytule: #roblox #brainrot #trending → algorytm",
                "numer_4": "Emoji jako 'okrzyknięcie' — 💀 😭 🏳️‍🌈 = sygnał emocjonalny",
                "czego_brakuje_tym_wideo": (
                    "Żadne z nich NIE MA loop endingu — to słabość którą Synapsa powinna wypełnić. "
                    "Kanały bez loop mają niższy AVD (Average View Duration). "
                    "Nasz przewaga: loop + absurd = dłuże oglądanie = więcej zasięgów."
                ),
            },
            "nowe_tytuly": [
                "💀 Kiedy Cała Roblox Obby Staje się OHIO w 2026 roku",
                "😭 POV: Jesteś Sigma Graczem ale Gra ma Bug na 100% #roblox",
                "🏆 NIEMOŻLIWA Roblox Obby vs. Minecraft Ohio — Kto Wygra? #brainrot",
            ],
            "nowy_hook_do_skryptu": (
                "Wchodziłem na tę serwer Roblox przez trzy dni i za każdym razem coś innego totalnie zniszczyło cały mój plan —"
            ),
            "viral_score_przewidywany": 8,
        }, ensure_ascii=False),
        "metadata": {
            "niche": "brainrot",
            "source": "analytical_training",
            "lesson": "brainrot_pattern_extraction",
        }
    },

    # ── 4. LOOP ENDING — jak konstruować ────────────────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI generującą skrypty YouTube Shorts.\n\n"
            "LEKCJA: Mechanizm Loop Ending.\n\n"
            "YouTube Shorts liczy wyświetlenie za każdym razem gdy pętla zaczyna się od nowa. "
            "Jeśli widz obejrzy Shorts 3 razy = 3 wyświetlenia. "
            "Synapsa musi konstruować skrypty TAK, żeby widz nie wiedział kiedy kończy się pierwsza pętla.\n\n"
            "Przykład ZŁY (widz wie że koniec):\n"
            "'...i dlatego zawsze sprawdzaj przed kupnem. Dziękuję za oglądanie. Subskrybuj!'\n\n"
            "Przykład DOBRY (loop — widz jest zdezorientowany):\n"
            "'...i to jest właśnie moment kiedy wszystko się zmienia — wyobraź sobie że wchodzisz do'\n\n"
            "ZADANIE: Wygeneruj skrypt dla niszy dark_mindset z PERFEKCYJNYM loop endingiem.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "viral_score": 9,
            "vs_top_shorts": "Lepszy: loop jest niewidoczny. Gorszy: brak twarzy w kadrze.",
            "viral_reasoning": (
                "Loop ending działa jak 'cliffhanger na 60 sekund'. Widz na początku słyszy środek zdania "
                "i mozg automatycznie chce domknąć pętlę znaczeniową. Rewatch rate 200%+ = algorytm pushuje dalej."
            ),
            "script_text": (
                "You already know someone who does this. They never argue with you directly — instead they go quiet. "
                "They pull back just enough to make you anxious, and they wait. "
                "They wait for you to come crawling back and apologize for something they caused. "
                "That silence isn't peace. That silence is a weapon, and you already know someone who does"
            ),
            "background_vibe": "dark rainy city night walk noir cinematic no copyright 4k",
            "music_folder": "dark_mindset",
            "title": "😶‍🌫️ The Silence Weapon — You Know Someone Like This #psychology",
            "description": "That silence isn't peace. Recognize this before it's too late. 💀\n#darkpsychology #manipulation #mindset #shorts #viral",
            "seo_tags": ["dark psychology", "manipulation", "silent treatment", "psychology", "mindset", "shorts", "viral"],
            "loop_analysis": {
                "start": "You already know someone who does this.",
                "end": "and you already know someone who does",
                "mechanism": "Ostatnie słowo 'does' łączy się z początkiem 'this.' — widz słyszy zdanie urwane i mózg automatycznie wraca do początku.",
                "type": "semantic_loop — kończy się w środku zdania które zaczęło skrypt"
            }
        }, ensure_ascii=False),
        "metadata": {
            "niche": "dark_mindset",
            "source": "analytical_training",
            "lesson": "loop_ending_mechanics",
        }
    },

    # ── 5. TYTUŁ SEO — jak go konstruować ───────────────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI analizującą SEO YouTube Shorts.\n\n"
            "LEKCJA: Anatomia perfekcyjnego tytułu YouTube Shorts.\n\n"
            "Dane z analizy 50 viralowych Shorts (engagement > 5%):\n"
            "  - Tytuły z EMOCJĄ na początku (💀😭🔥): +34% CTR\n"
            "  - Tytuły z liczbą ('3 things', '5 ways'): +22% CTR\n"
            "  - Tytuły z 'You' lub 'Your': +18% CTR\n"
            "  - Tytuły z pytaniem ('?'): +15% CTR\n"
            "  - Tytuły z słowem 'SECRET' lub 'DARK': +12% CTR\n"
            "  - Tytuły powyżej 60 znaków: -8% CTR (obcinane)\n"
            "  - Tytuły z 'subscribe' lub 'like': -25% CTR (widz ucieka)\n\n"
            "ZADANIE: Dla niszy brainrot PL i dark_mindset EN — podaj wzory na tytuł + przykłady.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "formuly_tytulow": {
                "brainrot_PL": {
                    "formula": "[EMOJI] [SYTUACJA_ABSURDALNA] + [SLANG] #[tag]",
                    "max_dlugosc": "55 znaków (bez hashtagów)",
                    "przykladowe_slowa_kluczowe": ["ohio", "sigma", "roblox", "skibidi", "brainrot", "minecraft", "obby"],
                    "przyklady_10_10": [
                        "💀 Kiedy Sigma Nauczyciel Trafia do OHIO #brainrot",
                        "😭 POV: Jesteś Jedyną Normalną Osobą w Roblox OHIO",
                        "🏆 Ta Roblox Obby ZNISZCZYŁA MOJE ŻYCIE #shorts",
                    ],
                    "unikaj": ["Subskrybuj", "Zostaw lajka", "sprawdź link w bio"]
                },
                "dark_mindset_EN": {
                    "formula": "[EMOJI] [LICZBA] [dark/silent/ego] [TECHNIKI] [EFEKT_ASPIRACYJNY]",
                    "max_dlugosc": "60 znaków",
                    "przykladowe_slowa_kluczowe": ["dark psychology", "manipulation", "control", "dominance", "silence", "ego"],
                    "przyklady_10_10": [
                        "🧠 3 Silent Tactics That Make People Respect You Instantly",
                        "💀 Stop Explaining Yourself — Watch What Happens",
                        "😶‍🌫️ The Silence Weapon You Didn't Know You Were Using",
                    ],
                    "unikaj": ["subscribe", "watch the full video", "comment below"]
                }
            },
            "universal_rule": (
                "Tytuł to reklama skryptu. Jeśli tytuł nie powoduje 'muszę to zobaczyć' — skrypt nie ma szans. "
                "Testuj mentalnie: gdybyś scrollował o 23:00 — czy kliknąłbyś ten tytuł?"
            )
        }, ensure_ascii=False),
        "metadata": {
            "niche": "both",
            "source": "analytical_training",
            "lesson": "title_seo_formula",
        }
    },

    # ── 6. PEŁNA ANALIZA → AKCJA — synteza wszystkiego ──────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI generującą i ANALIZUJĄCĄ skrypty YouTube Shorts.\n\n"
            "Otrzymałeś LIVE dane trendów z dzisiaj (2026-03-02):\n\n"
            "[BRAINROT PL — TOP 3 tego tygodnia]\n"
            "  1. 'subscribe or be gay 🏳️‍🌈 #roblox' | 40,919 views | 2.5% engagement | hook: absurd\n"
            "  2. 'META TECHNETTA vs THE WAVE #roblox' | 27,584 views | 2.7% engagement | hook: gaming\n"
            "  3. 'СКИБИДИ УДАЧА: ВЫБИЛ НОВОГО БРЕЙНРОТА' | 11,014 views | 1.5% engagement | hook: gaming+emoji\n\n"
            "[DARK MINDSET EN — TOP 3 tego tygodnia]\n"
            "  1. '5 Dark Psychology Tricks to Control anyone' | 99,291 views | 0% engagement\n"
            "  2. '2 Dark Manipulation Techniques' | 94,971 views | 0% engagement\n"
            "  3. '3 Manipulation Techniques That Create Dominance' | 17,487 views | 13.6% ENGAGEMENT ← DIAMENT\n\n"
            "DYREKTYWA: Na podstawie tej analizy, wygeneruj po 1 optymalnym skrypcie dla każdej niszy. "
            "Użyj wzorców z DIAMENTOWYCH przykładów (engagement > 5%). "
            "JSON z oboma skryptami.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "analiza_wstepna": {
                "dark_mindset_insight": (
                    "Wideo z 13.6% engagement ('Dominance') bije te z 0% engagement (94k views). "
                    "Wzorzec: konkretny efekt aspiracyjny ('Create Dominance') > ogólna liczba technik. "
                    "Widz nie chce wiedzieć — chce BYĆ."
                ),
                "brainrot_insight": (
                    "Roblox + absurd + hashtagi w tytule = algorytm PL. "
                    "Engagement 2-3% to norma dla brainrot — tu liczy się volume wyświetleń nie engagement. "
                    "Kluczowy pattern: absurdalna sytuacja + loop gaming context."
                )
            },
            "skrypt_brainrot": {
                "viral_score": 9,
                "viral_reasoning": "Roblox + niemożliwe wyzwanie + loop ending = rewatch bait dla 12-15 lat.",
                "script_text": (
                    "Próbowałem przejść tę Roblox obby przez pięć godzin i za każdym razem wypadałem w tym samym miejscu. "
                    "Dosłownie to samo miejsce, zawsze. Serio, ktoś musiał nienawidzić ludzi tworząc ten poziom. "
                    "Ale w momencie kiedy już prawie rzuciłem myszką coś kliknęło — i stałem na końcu. "
                    "Całe trzy sekundy. Potem spadłem, bo wróciłem żeby sprawdzić to samo miejsce gdzie próbowałem przejść tę Roblox obby przez"
                ),
                "background_vibe": "roblox impossible obby gameplay no copyright funny vertical",
                "music_folder": "brainrot",
                "title": "😤 Ta Roblox Obby ZNISZCZYŁA MOJE ŻYCIE (5 GODZIN) 💀 #roblox #shorts",
                "description": "Spróbuj sam i napisz ile prób zajęło 😂 #roblox #obby #brainrot #shorts #viral #gaming",
                "seo_tags": ["roblox", "obby", "impossible", "brainrot", "gaming", "shorts", "viral", "polska"]
            },
            "skrypt_dark_mindset": {
                "viral_score": 10,
                "viral_reasoning": "Dominance + recognition pattern + loop = 10%+ engagement target. Widz myśli 'to o mnie'.",
                "script_text": (
                    "The moment you stop needing their validation, something shifts. "
                    "They start watching you differently. Not because you changed — because they can feel that you no longer need them. "
                    "And people only chase what they can't control. "
                    "The ones who left? They'll be back. Not because you called them — but because you didn't. "
                    "And that is the exact moment you understand that real dominance starts the moment you stop needing their"
                ),
                "background_vibe": "sigma male dark moody office cinematic no copyright 4k vertical",
                "music_folder": "dark_mindset",
                "title": "🧠 Real Dominance Starts When You Stop Needing Them 💀 #psychology",
                "description": "They'll come back. Not because you called — because you didn't. 🔥\n#darkpsychology #sigma #mindset #manipulation #shorts #viral",
                "seo_tags": ["dark psychology", "dominance", "sigma", "manipulation", "mindset", "respect", "shorts", "viral"]
            }
        }, ensure_ascii=False),
        "metadata": {
            "niche": "both",
            "source": "analytical_training",
            "lesson": "full_analysis_to_action",
            "live_data_date": "2026-03-02",
        }
    },

    # ── 7. CZEGO UNIKAĆ — kontrprzykłady analityczne ────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI audytującą skrypty YouTube Shorts.\n\n"
            "Poniżej masz 3 skrypty które WYPADŁY SŁABO (< 5k views, < 0.5% engagement). "
            "Zidentyfikuj CO jest nie tak i zaproponuj naprawę.\n\n"
            "Skrypt A (dark_mindset, 831 views, 0% engagement):\n"
            "'Welcome back everyone! Today I'm going to share with you 5 psychology tips that will change your life. "
            "First tip: be confident. Second tip: set boundaries. Third tip: love yourself. "
            "Fourth tip: be positive. Fifth tip: never give up. Hope you enjoyed, subscribe for more!'\n\n"
            "Skrypt B (brainrot, 2,103 views, 0.1% engagement):\n"
            "'Hej wszystkim! Dzisiaj opowiem wam o brainrot. Brainrot to jest coś fajnego. "
            "Lubię brainrot bo jest śmieszny. Następnym razem zróbcie like i subskrybujcie. Dzięki za oglądanie!'\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "audit_skrypt_A": {
                "diagnoza": "KRYTYCZNY - 5 błędów jednocześnie",
                "bledy": [
                    "Hook 'Welcome back everyone' = 0 powodu żeby zostać. Widz scrolluje dalej.",
                    "Pięć ogólnych porad bez żadnego konkretnego kątu ('be confident' = nic nie znaczy)",
                    "'Change your life' = trigger skip — nadużywane przez lata, nie budzi emocji",
                    "Zakończenie z prośbą o subskrypcję = sygnał że content nie jest wystarczająco dobry",
                    "Brak loop endingu — AVD pewnie < 10%"
                ],
                "naprawa": {
                    "tytul": "The 1 Psychology Trick They Use to Make You Feel Small 💀 #psychology",
                    "nowy_hook": "There's one thing people who control others always do first. They make you doubt your own memory.",
                    "zasada": "Nie dawaj listy — dawaj JEDEN wniosek który uderza jak pięść. Mniej = więcej."
                }
            },
            "audit_skrypt_B": {
                "diagnoza": "KRYTYCZNY - brak struktury, brak emocji, brak celu",
                "bledy": [
                    "Brak hooka — 'Hej wszystkim' to 0 powód do zostania",
                    "Wyjaśnianie czym jest brainrot = widz który ogląda brainrot już wie czym jest brainrot",
                    "Brak absurdu, brak slangu, brak loop endingu",
                    "Prośba o subskrypcję na końcu = negatywny sygnał"
                ],
                "naprawa": {
                    "tytul": "💀 POV: Wchodzisz do Szkoły i Każdy Mówi Tylko 'Ohio' #brainrot",
                    "nowy_hook": "Wyobraź sobie że wchodzisz do szkoły i pierwszy nauczyciel który widzisz krzyczy W sigma rizz —",
                    "zasada": "Brainrot = absurdalna sytuacja w której widz wyobraża siebie. ZAWSZE pierwszoosobowo lub POV."
                }
            },
            "zasady_ogolne": [
                "NIGDY nie zaczynaj od 'Hej wszystkim' ani 'Welcome back'",
                "NIGDY nie kończ na prośbie o subskrypcję — loop ending albo nic",
                "NIGDY nie dawaj ogólnych rad — zawsze konkretny kąt, konkretna sytuacja",
                "ZAWSZE zakładaj że widz scrolluje 10x/sekundę — masz 0.5 sekundy na hook"
            ]
        }, ensure_ascii=False),
        "metadata": {
            "niche": "both",
            "source": "analytical_training",
            "lesson": "audit_bad_examples",
        }
    },

    # ── 8. TIMING + ALGO — kiedy i jak publikować ───────────────────────────
    {
        "instruction": (
            "### Instruction:\n"
            "Jesteś Synapsą — AI zarządzającą strategią publikacji YouTube Shorts.\n\n"
            "Niszę brainrot oglądają w 85% osoby 12-17 lat (Polska).\n"
            "Niszę dark_mindset oglądają w 70% mężczyźni 18-35 lat (USA/UK/Global).\n\n"
            "PYTANIE: Kiedy publikować żeby trafić w PEAK TIME każdej niszy? "
            "Uwzględnij strefy czasowe. Odpowiedz w JSON z uzasadnieniem.\n\n"
            "### Response:"
        ),
        "output": json.dumps({
            "peak_times": {
                "brainrot_PL": {
                    "audience": "12-17 lat, Polska (CEST = UTC+2)",
                    "peak_windows": [
                        {"czas_PL": "14:00-16:00", "czas_UTC": "12:00-14:00", "powod": "Po szkole. Szkoła kończy 13-15."},
                        {"czas_PL": "19:00-22:00", "czas_UTC": "17:00-20:00", "powod": "Wieczór, po kolacji, przed spaniem."},
                    ],
                    "najlepszy_single_slot": "14:30 CEST",
                    "unikaj": "9:00-13:00 (szkoła), 22:00+ (rodzice wyłączają)",
                    "dni_tygodnia": "piątek 14:30 + sobota 15:00 = max audience"
                },
                "dark_mindset_EN": {
                    "audience": "18-35 lat, USA East/UK (EST=UTC-5, GMT=UTC+0)",
                    "peak_windows": [
                        {"czas_EST": "18:00-21:00", "czas_UTC": "23:00-02:00", "powod": "Po pracy, scrollowanie wieczorne."},
                        {"czas_GMT": "20:00-23:00", "czas_UTC": "20:00-23:00", "powod": "UK prime time."},
                    ],
                    "najlepszy_single_slot": "19:00 EST / 00:00 UTC",
                    "unikaj": "9:00-17:00 EST (praca)",
                    "dni_tygodnia": "wtorek-czwartek wieczór = algorytm YT nagradza mid-week"
                }
            },
            "wniosek_operacyjny": (
                "Dla systemu auto-publikacji: brainrot publikuj o 14:30 UTC+2 (w dniach szkolnych), "
                "dark_mindset o 00:00 UTC (= 19:00 EST) — wtedy oba kanały trafiają w prime time swoich nisz."
            )
        }, ensure_ascii=False),
        "metadata": {
            "niche": "both",
            "source": "analytical_training",
            "lesson": "peak_time_strategy",
        }
    },

]


def add_analysis_training(output_file: str = TRAINING_FILE) -> int:
    """Dodaje przykłady analityczne do pliku JSONL."""
    existing_count = 0
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            existing_count = sum(1 for l in f if l.strip())

    added = 0
    with open(output_file, "a", encoding="utf-8") as f:
        for ex in ANALYSIS_EXAMPLES:
            # Buduj pełny text (instruction + output)
            full = {
                "text": f"{ex['instruction']}\n{ex['output']}",
                "instruction": ex["instruction"],
                "output": ex["output"],
                "metadata": ex["metadata"],
            }
            f.write(json.dumps(full, ensure_ascii=False) + "\n")
            added += 1

    print(f"\n{'='*60}")
    print(f"🧠 SYNAPSA ANALYSIS TRAINER — Zakończony")
    print(f"{'='*60}")
    print(f"  Istniejące przykłady: {existing_count}")
    print(f"  Dodano przykładów ANALITYCZNYCH: {added}")
    print(f"  ŁĄCZNIE w pliku: {existing_count + added}")
    print(f"\n  📚 Lekcje które Synapsa właśnie dostała:")
    for ex in ANALYSIS_EXAMPLES:
        lesson = ex["metadata"].get("lesson", "?")
        niche  = ex["metadata"].get("niche", "?")
        print(f"    ✅ [{niche:>12}] {lesson}")
    print(f"\n  💾 Plik: {output_file}")
    print(f"{'='*60}")
    return added


if __name__ == "__main__":
    add_analysis_training()
