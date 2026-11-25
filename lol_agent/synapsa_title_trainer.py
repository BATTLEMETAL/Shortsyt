"""
LOL Agent — Synapsa LoRA Trainer (Shortsyt / Flikcut)
====================================================
Buduje zbiór szkoleniowy JSONL z:
  1) 202 zweryfikowanych filmów kanału (learning_directive.json + performance_log.jsonl)
  2) Zewnętrznych viralowych schematów YouTube Shorts (lol_yt_pattern_miner.py)
  3) Zestawu Multi-Account (e-commerce, salon beauty, ekspert) + social + comment replies
i trenuje adapter LoRA `adapters_shortsyt_titles` na RTX 3060 12 GB.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from lol_agent.synapsa_engine import (
    BASE_MODEL_NAME,
    PARAM_EFFECT_CONTRACT,
    SYNAPSA_ROOT,
    TITLE_ADAPTER_DIR,
    _AI_JARGON_PHRASES,
    _BANNED_TITLE_PHRASES,
    _SPELL_TERMS,
    _extract_first_json_object,
    _install_lazy_safetensors_loader,
    _setup_windows_triton_mock,
    build_synapsa_instruction,
    strip_rank_prefix,
)

DATASET_PATH = Path(SYNAPSA_ROOT) / "dataset_shortsyt_titles.jsonl"


def _strip_title_tags(title: str) -> str:
    return re.sub(r"#\S+", "", str(title or "")).strip()


def _infer_action_from_row(row: Dict[str, Any]) -> str:
    act = str(row.get("action_type") or row.get("frag_type") or "").lower().strip()
    if act:
        return act
    t_up = str(row.get("title") or "").upper()
    if "PENTA" in t_up:
        return "pentakill"
    if "QUADRA" in t_up:
        return "quadrakill"
    if "TRIPLE" in t_up:
        return "triple"
    if "DOUBLE" in t_up:
        return "double"
    if "1V1" in t_up or "SOLO" in t_up:
        return "solo_bolo"
    if "1% HP" in t_up or "1 HP" in t_up or "SURVIV" in t_up:
        return "clutch"
    return "outplay"


def _telemetry_comment_for_training(action_type: str, k_count: int, kill_span_s: float, low_hp: bool) -> str:
    if low_hp:
        return "Dropped into critical HP and still turned the fight — greedy overchase by them or clean limit test? 💀"
    if kill_span_s > 0.0 and k_count >= 2:
        return f"{k_count} eliminations in {kill_span_s:.1f}s — did the enemy clump up for free or was that reset unreactable? 👇"
    if action_type in ("solo_bolo", "1v1"):
        return "Did enemy mid disrespect the damage window or was there actually an outplay angle here? 👇"
    if action_type in ("pentakill", "quadrakill"):
        return "Which enemy player threw this fight the hardest? Watch the first 3 seconds 💀"
    return "Calculated angle or pure enemy panic? Drop your take below 👇"


def build_training_dataset(
    output_path: Path = DATASET_PATH,
    mine_youtube: bool = True,
    directive_override: Optional[Dict[str, Any]] = None,
    write_file: bool = True,
) -> Dict[str, Any]:
    """Generuje dataset JSONL dla fine-tuningu QLoRA w dokładnie tym formacie co synapsa_engine."""
    lol_dir = ROOT_DIR / "lol_agent"
    directive_path = lol_dir / "learning_directive.json"
    perf_log_path = lol_dir / "performance_log.jsonl"

    directive: Dict[str, Any] = dict(directive_override) if isinstance(directive_override, dict) else {}
    if not directive and directive_path.exists():
        directive = json.loads(directive_path.read_text(encoding="utf-8"))

    # 1. Zbierz realne topowe filmy z performance_log + top_viral_titles + yt_perf_cache
    source_rows: List[Dict[str, Any]] = []
    seen_titles = set()

    if perf_log_path.exists():
        for line in perf_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                t = _strip_title_tags(row.get("title", ""))
                views = int(row.get("views") or 0)
                if len(t) >= 12 and views >= 1100 and t.lower() not in seen_titles:
                    seen_titles.add(t.lower())
                    source_rows.append(row)
            except Exception:
                continue

    yt_cache_path = lol_dir / "yt_perf_cache.json"
    if yt_cache_path.exists():
        try:
            cache_data = json.loads(yt_cache_path.read_text(encoding="utf-8"))
            for row in cache_data.get("videos", []):
                t = _strip_title_tags(row.get("title", ""))
                views = int(row.get("views") or 0)
                if len(t) >= 12 and views >= 1500 and t.lower() not in seen_titles:
                    seen_titles.add(t.lower())
                    source_rows.append(row)
        except Exception:
            pass

    for vt in directive.get("top_viral_titles", []):
        t = _strip_title_tags(vt)
        if len(t) >= 12 and t.lower() not in seen_titles:
            seen_titles.add(t.lower())
            source_rows.append({"title": vt, "views": 3500, "action_type": _infer_action_from_row({"title": vt})})

    # 2. Zewnętrzne topowe wzorce YouTube Shorts
    ext_patterns: List[Dict[str, Any]] = []
    if mine_youtube:
        try:
            from lol_agent.lol_yt_pattern_miner import mine_top_youtube_patterns
            ext_patterns = mine_top_youtube_patterns(max_results=20, force_refresh=False)
        except Exception:
            ext_patterns = []

    for pat in ext_patterns:
        t = _strip_title_tags(pat.get("title", ""))
        if len(t) >= 12 and t.lower() not in seen_titles:
            seen_titles.add(t.lower())
            source_rows.append({
                "title": pat["title"],
                "views": pat.get("views", 10000),
                "action_type": _infer_action_from_row({"title": t}),
            })

    # Pula viralowych tytułów alternatywnych (POV / Curiosity-Gap / Ego-Check / Time-Math, zero AI-żargonu)
    alt_pools: Dict[str, List[str]] = {
        "solo_bolo": [
            "POV: They Challenged The Wrong 1v1 😏",
            "How Did They Lose This 1v1? 💀",
            "Duel Accepted. Duel Won. 👑",
            "Walking Up Like That Is Crazy ⚡",
        ],
        "clutch": [
            "Surviving on 1 HP to Turn Everything 🩸",
            "How Is She Still Alive Here?! 💀",
            "Wait Until The 1% HP Flip 🔥",
            "Miracle Turnaround on Sliver HP ⚡",
        ],
        "pentakill": [
            "POV: Five Enemies. Zero Escape. 💀",
            "Entire Squad Vanished in Seconds ⚡",
            "When They Group Straight Into Daggers 🔥",
            "Wait For The Fifth Reset Kill 👑",
        ],
        "quadrakill": [
            "POV: When Enemy Thinks 4v1 Is Free 💀",
            "Four Down Before They Even Reacted ⚡",
            "They Grouped Straight Into a Quadra 🔥",
            "Wait Until The Fourth Reset Hits 👑",
        ],
        "triple": [
            "POV: When Enemy Thinks 3v1 Is Free ⚡",
            "3 Eliminations Before They Reacted 💀",
            "How Is This Legal In Ranked? 🔥",
            "Wait Until The Third Reset Hits 👑",
        ],
        "double": [
            "Greedy 2v1 Punished In 2 Seconds 💀",
            "When Bot/Mid Overchases Too Far ⚡",
            "Cleanest 2v1 Spacing Trap 🔥",
            "Cleanest 2-for-0 Turnaround 👑",
        ],
        "outplay": [
            "POV: They Walked Straight Into Every Dagger ⚡",
            "How Did That Actually Work? 🧠",
            "They Overextended Straight Into This 💀",
            "Wait Until You See The Flip 🔥",
        ],
    }

    _bad_train_terms = (*_BANNED_TITLE_PHRASES, *_AI_JARGON_PHRASES, *_SPELL_TERMS, "bad idea")
    _desc_variants = [
        "Sharp {champ} {act} built on dagger positioning and timing windows. Would you have stepped up or backed off?",
        "They tried to force a fight straight into {champ} daggers and paid for it immediately. Could enemy squad play this any differently?",
        "Clean {champ} {act} from a fight that looked over before the first reset. Who misplayed hardest on the enemy side?",
        "Wait for the dagger angle that turns this whole fight around on {champ}. Worth pushing forward or too greedy?",
        "Zero hesitation from {champ} on the counter-engage to close out the {act}. Would you take that fight in ranked?",
    ]

    examples: List[Dict[str, str]] = []
    for idx, row in enumerate(source_rows):
        clean_title = _strip_title_tags(row.get("title", ""))
        # Usuń stare prefiksy/spelle oraz AI-żargon z historycznych przykładów przy treningu
        clean_title = strip_rank_prefix(clean_title)
        if len(clean_title) < 8 or any(bad in clean_title.lower() for bad in _bad_train_terms):
            continue

        act = _infer_action_from_row(row)
        k_cnt = 5 if "penta" in act else (4 if "quadra" in act else (3 if "triple" in act else (2 if "double" in act else 1)))
        low_hp = act == "clutch" or ("1% hp" in clean_title.lower()) or ("1 hp" in clean_title.lower())
        kill_span = round(2.1 + (idx % 4) * 0.6, 1) if k_cnt >= 2 else 0.0
        payload = {
            "champion": "Katarina",
            "action_type": act,
            "kill_count": k_cnt,
            "kill_span_s": kill_span,
            "min_hp_pct": 12.0 if low_hp else 68.0,
            "low_hp_survival": low_hp,
            "enemies_in_fight": max(1, min(5, k_cnt)),
            "map_zone": "Mid Lane" if idx % 2 == 0 else "",
            "hud_spells_verified": False,
        }

        pool = list(alt_pools.get(act if act in alt_pools else "outplay"))
        cands = [clean_title] + [c for c in pool if c.lower() != clean_title.lower()]
        cands = cands[:5]
        hook_map = {
            "solo_bolo": "1V1 EGO CHECK",
            "clutch": "1% HP SURVIVAL",
            "pentakill": "5 MAN RESET WIPE",
            "quadrakill": "4 MAN RESET WIPE",
            "triple": "3 DOWN IN SECONDS",
            "double": "INSTANT DOUBLE DOWN",
        }
        desc_tpl = _desc_variants[idx % len(_desc_variants)]
        out_json = {
            "title_candidates": cands,
            "hook_text": hook_map.get(act, "CLEAN ANGLE FLIP"),
            "description": desc_tpl.format(champ="Katarina", act=act.replace("_", " ")),
            "pinned_comment": _telemetry_comment_for_training(act, k_cnt, kill_span, low_hp),
            "tags": ["katarina", "league of legends", "lol shorts", act.replace("_", " "), "gaming", "outplay"],
        }
        examples.append({
            "instruction": build_synapsa_instruction("lol_metadata", payload),
            "output": json.dumps(out_json, ensure_ascii=False),
        })

    # 3. Dodaj pary Multi-Account (Beauty Salon, E-commerce, Ekspert) + Social + Comment Reply
    multi_acc_samples = [
        (
            "account_metadata",
            {
                "account_name": "Salon Pretty Woman Świdnica",
                "content_mode": "BEAUTY_SALON_SERVICE",
                "language": "PL",
                "subject_name": "Afroloki Blond Metamorfoza",
                "action_type": "metamorfoza",
                "value_proposition": "Naturalny efekt i objętość utrzymująca się tygodniami",
                "cta_text": "Zapisz się lub zamów w sklepie 👇",
                "location": "ul. Ofiar Oświęcimskich 28, Świdnica",
                "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
            },
            {
                "title_candidates": [
                    "Metamorfoza Afroloki Blond w 3h ✨ #shorts",
                    "Zobacz efekt Afroloków przed i po 😍 #shorts",
                    "Objętość bez niszczenia włosów 💁‍♀️ #shorts",
                ],
                "title_variant_b": "Afroloki Świdnica — szybka metamorfoza ✨ #shorts",
                "hook_text": "EFEKT PRZED I PO",
                "description": "Naturalna objętość i wygoda noszenia na co dzień. Zapraszamy do rezerwacji terminu w Świdnicy przy ul. Ofiar Oświęcimskich 28.",
                "pinned_comment": "Który odcień blondu pasowałby Ci bardziej — ciepły miód czy chłodny beż? Napisz poniżej 👇",
                "tags": ["afroloki", "salonbeauty", "fryzjerświdnica", "metamorfoza", "shorts"],
            },
        ),
        (
            "account_metadata",
            {
                "account_name": "Sklep E-Commerce Demo",
                "content_mode": "PRODUCT_ECOMMERCE_AD",
                "language": "PL",
                "subject_name": "Mini Blender USB-C",
                "action_type": "unboxing",
                "value_proposition": "Koktajl gotowy w 20 sekund w pracy i na siłowni",
                "cta_text": "Sprawdź link w opisie 👇",
                "forbidden_words": ["Katarina", "League of Legends"],
            },
            {
                "title_candidates": [
                    "Koktajl w 20s w pracy i na siłowni ⚡ #shorts",
                    "Ten blender USB-C mieści się w plecaku 🥤 #shorts",
                    "Koniec z myciem wielkiego miksera ✨ #shorts",
                ],
                "title_variant_b": "Test mini blendera USB-C — hit czy kit? #shorts",
                "hook_text": "KOKTAJL W 20 SEKUND",
                "description": "Zero kabli i szybkie czyszczenie po treningu lub w biurze. Sprawdź szczegóły produktu w linku poniżej.",
                "pinned_comment": "Co wrzuciłbyś jako pierwsze — shake białkowy czy mrożone owoce? 👇",
                "tags": ["gadżety", "zakupy", "recenzja", "fit", "shorts"],
            },
        ),
        (
            "account_metadata",
            {
                "account_name": "Kebab u Ali Wrocław",
                "content_mode": "FOOD_GASTRO",
                "language": "PL",
                "subject_name": "Kraftowy Rollo z Baraniny i Świeżej Surówki",
                "action_type": "kuchnia_na_zywo",
                "value_proposition": "Wypiekana na miejscu pita i autorski sos czosnkowy w 3 minuty",
                "cta_text": "Wpadnij spróbować na ul. Świdnickiej 14 👇",
                "location": "Wrocław, ul. Świdnicka 14",
                "forbidden_words": ["Katarina", "League of Legends", "Pentakill", "Ranked"],
            },
            {
                "title_candidates": [
                    "Tak kręci się prawdziwy kraftowy kebab 🌯",
                    "Chrupiąca pita prosto z pieca w 60 sekund 🔥",
                    "Sekret naszego sosu czosnkowego bez ulepszaczy 🧄",
                ],
                "title_variant_b": "Kebab rzemieślniczy Wrocław — co ląduje w środku?",
                "hook_text": "PROSTO Z RUSZTU",
                "description": "Świeżo wypiekana pita, chrupiące warzywa i soczysta baranina krojona na oczach gości. Odwiedź nas dziś we Wrocławiu przy ul. Świdnickiej 14!",
                "pinned_comment": "Który sos wygrywa u Ciebie — łagodny czosnkowy czy ostry harissa? 👇",
                "tags": ["kebab", "wroclawjedzenie", "streetfood", "gastro", "kuchnia"],
            },
        ),
        (
            "account_metadata",
            {
                "account_name": "Piekarnia i Burger Stacja Poznań",
                "content_mode": "FOOD_GASTRO",
                "language": "PL",
                "subject_name": "Podwójny Smash Burger na Brioche",
                "action_type": "smazenie_na_grilu",
                "value_proposition": "Sezonowana wołowina smażona na maślanej bułce brioche",
                "cta_text": "Zamów ciepłego smash burgera z odbiorem 👇",
                "location": "Poznań, Jeżyce",
                "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
            },
            {
                "title_candidates": [
                    "Chrupkość tego smash burgera słychać z daleka 🍔",
                    "Dlaczego smażymy dwie cienkie porcje zamiast jednej? 🔥",
                    "Maślana bułka brioche i topiony cheddar z rana 🧀",
                ],
                "title_variant_b": "Smash burger na Jeżycach — zobacz środek po przekrojeniu",
                "hook_text": "CHRUPIĄCA SKÓRKA",
                "description": "Dwie soczyste porcje wołowiny dociśnięte na rozgrzanej płycie aż do karmelizacji. Czekamy na Ciebie codziennie na poznańskich Jeżycach!",
                "pinned_comment": "Klasyczny podwójny cheddar czy wersja z bekonem i jalapeno? 👇",
                "tags": ["smashburger", "poznanjedzenie", "burgery", "streetfoodpolska", "jezyce"],
            },
        ),
        (
            "account_metadata",
            {
                "account_name": "Atelier Paznokci Kamila Kraków",
                "content_mode": "NAILS_BEAUTY",
                "language": "PL",
                "subject_name": "Manicure Hybrydowy French Milky",
                "action_type": "stylizacja_paznokci",
                "value_proposition": "Trwały french bez odprysków nawet do 4 tygodni",
                "cta_text": "Wolne terminy na ten tydzień w opisie 👇",
                "location": "Kraków, Kazimierz",
                "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
            },
            {
                "title_candidates": [
                    "Milky French, który wydłuża każdą dłoń ✨",
                    "Równy uśmiech na paznokciach w jednym ruchu 💅",
                    "Efekt po 3 tygodniach noszenia bez zapowietrzeń 😍",
                ],
                "title_variant_b": "Klasyczny french czy babyboomer na co dzień?",
                "hook_text": "CZYSTA LINIA FRENCH",
                "description": "Delikatny mleczny odcień i cienka warstwa żelu wzmacniającego przy skórkach. Zarezerwuj wizytę na krakowskim Kazimierzu zanim znikną poranne terminy!",
                "pinned_comment": "Wolisz cienką białą kreskę czy klasyczny babyboomer? 👇",
                "tags": ["paznokciehybrydowe", "manicurekrakow", "stylizacjapaznokci", "milkyfrench", "beauty"],
            },
        ),
        (
            "account_metadata",
            {
                "account_name": "Studio Paznokci Velvet Gdańsk",
                "content_mode": "NAILS_BEAUTY",
                "language": "PL",
                "subject_name": "Przedłużanie Żelem Kształt Migdał",
                "action_type": "metamorfoza_dloni",
                "value_proposition": "Cienka budowa paznokcia odporna na pęknięcia",
                "cta_text": "Sprawdź cennik i zapisy online 👇",
                "location": "Gdańsk, Wrzeszcz",
                "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
            },
            {
                "title_candidates": [
                    "Od ogryzionych paznokci do smukłego migdała ✨",
                    "Zobacz grubość wolnego brzegu po opiłowaniu 💅",
                    "Krótka rekonstrukcja bez efektu grubej łopaty 😍",
                ],
                "title_variant_b": "Metamorfoza dłoni żelem — efekt przed i po",
                "hook_text": "SMUKŁY MIGDAŁ",
                "description": "Naturalna krzywizna i czyste wykończenie pod same skórki w 90 minut. Umów konsultację w Gdańsku Wrzeszczu przez link w opisie.",
                "pinned_comment": "Jaki kształt nosisz częściej — migdał czy miękki kwadrat? 👇",
                "tags": ["paznokciezelowe", "manicuregdansk", "migdalki", "paznokcieprzedipo", "salonbeauty"],
            },
        ),
        (
            "social_caption",
            {"platform": "tiktok", "champion": "Katarina", "action_type": "solo_bolo", "kill_span_s": 0.0, "min_hp_pct": 15.0},
            {"caption": "15% HP 1v1 turnaround with zero room for error 💀 Would you stay in?"},
        ),
        (
            "social_caption",
            {"platform": "instagram", "champion": "Katarina", "action_type": "triple", "kill_span_s": 2.4},
            {"caption": "3 eliminations in 2.4 seconds flat ⚡\nWho threw the fight harder on the enemy squad? 👇"},
        ),
        (
            "social_caption",
            {"prompt": "Write a TikTok short caption (1 line, max 90 chars) for a League of Legends clip. Champion: Katarina. Action: quadrakill. Wait 2.8s spin."},
            {"caption": "Four down before they even pinged missing 💀"},
        ),
        (
            "social_caption",
            {"prompt": "Write an Instagram Reels caption (2 short lines, debate question, NO facebook links, NO Rate 1-10) for Katarina double kill."},
            {"caption": "They walked straight onto two passive daggers.\nGreedy chase or clean bait? 👇"},
        ),
        (
            "social_caption",
            {"prompt": "Write a Facebook post for a League of Legends gaming page. Champion: Katarina. Action: triple kill. Rules: conversational tone, 2-3 sentences max, ask a question at the end. No hashtag spam (max 1-2 hashtags at the very end)."},
            {"caption": "Enemy squad stacked three deep right over two waiting daggers and lost the whole fight in seconds. Would you have respected the reset range or forced the dive?\n\n#leagueoflegends #reels"},
        ),
        (
            "social_caption",
            {"prompt": "Write a Facebook post for a League of Legends gaming page. Champion: Katarina. Action: clutch win. Rules: conversational tone, 2-3 sentences max, ask a question at the end."},
            {"caption": "Left on sliver HP after taking full engage, one dagger reset turned the entire skirmish around. Lucky Triumph tick or calculated limit test?\n\n#leagueoflegends #katarina"},
        ),
        (
            "comment_reply",
            {
                "video_title": "They Thought 1v1 Was Safe #shorts",
                "action_type": "solo bolo",
                "viewer_comment": "Enemy mid completely greeded that wave lol",
            },
            {"replies": [
                "100% — once they walked up for that cannon the spacing window opened wide open 😅",
                "Classic cannon minion tax 💀 Would you have greeded for it too?",
            ]},
        ),
        (
            "comment_reply",
            {
                "video_title": "Surviving on 1% HP to Win #shorts",
                "action_type": "clutch",
                "viewer_comment": "Clean resets, thought you were dead there",
            },
            {"replies": [
                "Appreciate it! Literally one auto attack away from grey screen 😅",
                "Triumph and reset timing saved my life by half a pixel 💀",
            ]},
        ),
        (
            "comment_reply",
            {
                "video_title": "POV: When Enemy Thinks 4v1 Is Free #shorts",
                "action_type": "quadrakill",
                "viewer_comment": "Why did they all walk over the same dagger?",
            },
            {"replies": [
                "Magnet daggers strikes again — nobody expects the second bounce 😅",
                "Group hug over passive dagger never ends well in solo queue 💀",
            ]},
        ),
        (
            "comment_reply",
            {
                "video_title": "Greedy 2v1 Punished In 2 Seconds #shorts",
                "action_type": "double",
                "viewer_comment": "Enemy jungler ganking a fed Katarina mid haha",
            },
            {"replies": [
                "Free double buff delivery straight to mid lane 😅",
                "Best kind of gank — brings extra gold right to the wave 💀",
            ]},
        ),
    ]

    for task, pload, out_obj in multi_acc_samples:
        examples.append({
            "instruction": build_synapsa_instruction(task, pload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    # 4. Przykłady Montage Director z hard_cases_memory.json + kontrastowych scenariuszy 48h
    director_examples = _build_director_training_examples(directive, lol_dir)
    examples.extend(director_examples)

    # 4b. Przykłady overnight_rank (Sykofankcja 0 — odrzucanie wad krytycznych i mismatchy)
    overnight_rank_examples = _build_overnight_rank_training_examples()
    examples.extend(overnight_rank_examples)

    # 5. Lekcje inżynierskie i delty atrybutów Before -> After (`engineering_cause_effect`) + historia zmian wartości
    cause_effect_examples: List[Dict[str, str]] = []
    watchability_examples: List[Dict[str, str]] = []
    historical_examples: List[Dict[str, str]] = []
    try:
        from lol_agent.synapsa_conversation_learner import (
            build_cause_effect_training_examples,
            build_historical_evolution_training_examples,
            build_watchability_training_examples,
            sync_engineering_memory,
        )
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            sync_engineering_memory(include_transcripts=False, write_files=True)
        cause_effect_examples = build_cause_effect_training_examples(max_examples=40)
        examples.extend(cause_effect_examples)
        watchability_examples = build_watchability_training_examples(max_examples=18)
        examples.extend(watchability_examples)
        historical_examples = build_historical_evolution_training_examples(max_examples=14)
        examples.extend(historical_examples)
    except Exception:
        cause_effect_examples = []
        watchability_examples = []
        historical_examples = []

    # Wyrównaj wagi próbek tak, by dataset miał stabilną objętość
    if write_file:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return {
        "dataset_path": str(output_path),
        "written": bool(write_file),
        "total_examples": len(examples),
        "channel_and_yt_examples": (
            len(examples)
            - len(multi_acc_samples)
            - len(director_examples)
            - len(overnight_rank_examples)
            - len(cause_effect_examples)
            - len(watchability_examples)
            - len(historical_examples)
        ),
        "multi_account_and_reply_examples": len(multi_acc_samples),
        "director_examples": len(director_examples),
        "overnight_rank_examples": len(overnight_rank_examples),
        "engineering_cause_effect_examples": len(cause_effect_examples),
        "watchability_examples": len(watchability_examples),
        "historical_evolution_examples": len(historical_examples),
        "external_yt_patterns": len(ext_patterns),
    }


def _build_director_training_examples(directive: Dict[str, Any], lol_dir: Path) -> List[Dict[str, str]]:
    """Generuje min. 35 przykładów QLoRA dla `montage_director` (hard_cases + recipes_archive + warianty 48h z pełnymi suwakami)."""
    from lol_agent.synapsa_engine import PARAM_EFFECT_CONTRACT, decide_montage_with_synapsa

    out: List[Dict[str, str]] = []

    def _add_case(pload: Dict[str, Any], custom_ans: Dict[str, Any] = None) -> None:
        pload_full = dict(pload)
        pload_full["param_ranges"] = {k: (v.get("range") or v.get("allowed")) for k, v in PARAM_EFFECT_CONTRACT.items()}
        ch_low = str(pload_full.get("champion") or "").lower().strip()
        pload_full["camera_policy"] = (
            "smooth_pan<=80px_or_instant_shunpo_E_snap_to_dagger_or_enemy_then_center_katarina"
            if ch_low == "katarina" or not ch_low
            else "smooth_pan<=80px_or_confirmed_dash_snap"
        )
        ans = custom_ans or decide_montage_with_synapsa(
            {
                "action_type": pload_full.get("action_type", "outplay"),
                "champion": pload_full.get("champion", "Katarina"),
                "duration": pload_full.get("duration", 16.0),
                "kills": [{"timestamp": t} for t in (pload_full.get("kill_timestamps") or [])],
                "gaps": pload_full.get("gaps"),
                "gap_has_combat": pload_full.get("gap_has_combat", False),
                "objective_secured": pload_full.get("objective_secured", False),
                "ally_banner_blocked": pload_full.get("ally_banner_blocked", False),
                "min_hp_pct": pload_full.get("min_hp_pct"),
            },
            directive=directive,
            use_local_ai=False,
        )
        clean_out = {
            "operation": ans["operation"],
            "style": ans["style"],
            "buildup_sec": ans["buildup_sec"],
            "outro_sec": ans["outro_sec"],
            "zoom_aggression": ans["zoom_aggression"],
            "slowmo_duration": ans["slowmo_duration"],
            "camera_mode": ans["camera_mode"],
            "drop_anchor": ans.get("drop_anchor", "climax_final_kill"),
            "rationale": ans["rationale"],
        }
        out.append({
            "instruction": build_synapsa_instruction("montage_director", pload_full),
            "output": json.dumps(clean_out, ensure_ascii=False),
        })

    # 1. Trudne klipy z hard_cases_memory.json (wyłącznie zweryfikowane multikille >=2, limit 24 przykładów)
    hc_path = lol_dir / "hard_cases_memory.json"
    if hc_path.exists():
        try:
            items = json.loads(hc_path.read_text(encoding="utf-8"))
            hc_examples_added = 0
            for hc in (items if isinstance(items, list) else []):
                if hc_examples_added >= 24:
                    break
                kills = hc.get("kills") or []
                if len(kills) < 2:
                    continue
                ts = sorted(float(k.get("timestamp", 0.0)) for k in kills)
                gaps = [round(b - a, 2) for a, b in zip(ts, ts[1:])]
                act = str(hc.get("detected_frag_type") or "quadrakill").lower().strip()
                pload = {
                    "action_type": act,
                    "champion": hc.get("champion") or "Katarina",
                    "duration": hc.get("duration_window", 24.0),
                    "kill_timestamps": ts,
                    "gaps": gaps,
                    "gap_has_combat": bool(hc.get("objective_secured") or hc.get("ally_banner_blocked")),
                    "objective_secured": bool(hc.get("objective_secured")),
                    "ally_banner_blocked": bool(hc.get("ally_banner_blocked")),
                    "min_hp_pct": hc.get("min_hp_pct"),
                }
                repeat = 2 if act in ("quadrakill", "pentakill") else 1
                for _ in range(repeat):
                    if hc_examples_added >= 24:
                        break
                    _add_case(pload)
                    hc_examples_added += 1
        except Exception:
            pass

    # 2. Prawdziwe przepisy z recipes_archive/ (priorytet dla FIT_CONFIRMED RWI >= 75 oraz najnowszych, do 30 szt.)
    p48 = (directive.get("post_48h_gate_summary") or {}) if isinstance(directive, dict) else {}
    high_rwi_ids = set(str(vid) for vid in (p48.get("high_rwi_video_ids") or []) if vid)
    arch_dir = lol_dir / "recipes_archive"
    if arch_dir.exists():
        arch_files = sorted(
            arch_dir.glob("*.recipe.json"),
            key=lambda p: (0 if p.name[:-len(".recipe.json")] in high_rwi_ids else 1, -p.stat().st_mtime),
        )[:30]
        for rp in arch_files:
            try:
                rec = json.loads(rp.read_text(encoding="utf-8"))
                ts = sorted(float(p[0]) for p in (rec.get("peaks_in_clip") or []) if isinstance(p, (list, tuple)) and p)
                gaps = [round(b - a, 2) for a, b in zip(ts, ts[1:])]
                _add_case({
                    "action_type": rec.get("action_type", "outplay"),
                    "champion": rec.get("champion", "Katarina"),
                    "duration": rec.get("clip_seconds_in", 15.0),
                    "kill_timestamps": ts,
                    "gaps": gaps,
                    "gap_has_combat": False,
                    "objective_secured": False,
                    "ally_banner_blocked": False,
                })
            except Exception:
                continue

    # 3. Bogata siatka scenariuszy kontrastowych pokrywająca wszystkie 5 operacji i suwaki
    by_act = p48.get("by_action_type") or {}
    scenarios = [
        # KEEP_FULL_CONTINUOUS (objective / teamfight / ally_banner)
        ("quadrakill", "Katarina", 24.0, [11.5, 16.0, 21.0, 28.0], True, True, True, 1.3),
        ("pentakill", "Katarina", 23.0, [3.0, 6.2, 10.5, 14.0, 18.2], True, False, True, 8.0),
        ("triple", "Katarina", 19.5, [2.8, 7.2, 13.5], True, True, True, 14.0),
        ("quadrakill", "Samira", 20.0, [2.5, 5.0, 7.8, 10.5], False, False, True, 22.0),
        ("triple", "Viego", 16.5, [3.2, 6.0, 8.8], False, False, True, 35.0),
        ("solo_bolo", "Katarina", 13.5, [7.5], False, False, False, 19.0),
        ("solo_bolo", "Zed", 14.0, [8.2], False, False, False, 11.0),
        ("clutch", "Katarina", 15.0, [5.5, 9.0], False, False, True, 2.4),
        # DROP_ISOLATED_FIRST_KILL (1. frag oddalony >6s przed główną akcją bez walki)
        ("triple", "Katarina", 22.0, [2.0, 12.0, 14.5], False, False, False, 48.0),
        ("triple", "Yone", 21.5, [1.8, 10.2, 12.4], False, False, False, 55.0),
        ("quadrakill", "Katarina", 25.0, [2.5, 11.5, 14.0, 16.5], False, False, False, 42.0),
        ("triple", "Akali", 20.0, [1.5, 9.5, 11.8], False, False, False, 30.0),
        ("double", "Katarina", 18.0, [1.2, 8.8, 10.6], False, False, False, 61.0),
        ("outplay", "Irelia", 21.0, [2.2, 10.0, 12.2], False, False, False, 33.0),
        # DROP_ISOLATED_LAST_KILL (ostatni frag po >6s martwego pościgu)
        ("triple", "Katarina", 23.0, [4.0, 6.0, 16.5], False, False, False, 60.0),
        ("triple", "Talon", 22.5, [3.5, 5.8, 14.8], False, False, False, 52.0),
        ("quadrakill", "Katarina", 24.5, [3.0, 5.0, 7.2, 16.0], False, False, False, 38.0),
        ("double", "Zed", 19.5, [3.2, 5.1, 13.0], False, False, False, 70.0),
        ("outplay", "Master Yi", 20.5, [2.8, 4.9, 13.5], False, False, False, 45.0),
        # BRIDGE_GAP_SPEED_RAMP (przerwa 4.3-6.0s lub brak pustego izolatu)
        ("outplay", "Katarina", 18.0, [3.0, 8.2], False, False, False, 28.0),
        ("double", "Katarina", 17.5, [2.5, 7.8], False, False, False, 31.0),
        ("triple", "Akali", 20.0, [2.4, 7.5, 12.6], False, False, False, 24.0),
        ("outplay", "Ekko", 16.5, [3.1, 7.9], False, False, False, 19.0),
        ("double", "Yasuo", 18.5, [2.8, 8.1], False, False, False, 40.0),
        ("quadrakill", "Diana", 21.0, [2.0, 5.5, 9.0, 13.5], False, False, True, 9.5),
        ("triple", "Sylas", 17.0, [2.2, 6.8, 12.1], False, False, False, 16.0),
        ("solo_bolo", "Akali", 12.8, [6.5], False, False, False, 7.0),
    ]
    for act, ch, dur, ts_pts, obj_s, ally_b, gap_c, min_hp in scenarios:
        gaps = [round(b - a, 2) for a, b in zip(ts_pts, ts_pts[1:])]
        _add_case({
            "action_type": act,
            "champion": ch,
            "duration": dur,
            "kill_timestamps": ts_pts,
            "gaps": gaps,
            "gap_has_combat": gap_c,
            "objective_secured": obj_s,
            "ally_banner_blocked": ally_b,
            "min_hp_pct": min_hp,
            "historical_avg_rwi": (by_act.get(act) or {}).get("avg_rwi", 72.0),
        })

    # Dwa wyraźne przypadki SWITCH_STYLE_IN_MEDIA_RES przy historycznie niskim RWI < 68
    for act_low, ts_low in [("double", [7.5, 9.5]), ("outplay", [6.8, 9.0]), ("triple", [7.0, 9.2, 11.4])]:
        gaps_low = [round(b - a, 2) for a, b in zip(ts_low, ts_low[1:])]
        _add_case(
            {
                "action_type": act_low,
                "champion": "Katarina",
                "duration": 15.0,
                "kill_timestamps": ts_low,
                "gaps": gaps_low,
                "gap_has_combat": False,
                "objective_secured": False,
                "ally_banner_blocked": False,
                "historical_avg_rwi": 63.5,
            },
            custom_ans={
                "operation": "SWITCH_STYLE_IN_MEDIA_RES",
                "style": "IN_MEDIA_RES",
                "buildup_sec": 0.4,
                "outro_sec": 1.2,
                "zoom_aggression": 1.22,
                "slowmo_duration": 1.0,
                "camera_mode": "tight_player",
                "drop_anchor": "first_kill_engage" if len(ts_low) >= 2 and ts_low[-1] > 8.5 else "climax_final_kill",
                "rationale": f"Historyczne RWI {act_low} < 68 przy długim wejściu — przełączono na IN_MEDIA_RES (buildup=0.4s).",
            },
        )

    # 4. Wnioski strukturalne z zewnętrznych wirali (yt_viral_patterns_cache.json) + legacy-protected pentakill
    try:
        from lol_agent.lol_yt_pattern_miner import mine_top_youtube_patterns
        viral_patterns = mine_top_youtube_patterns(max_results=16, force_refresh=False)[:8]
        for pat in viral_patterns:
            bp = pat.get("edit_blueprint") or {}
            anchor = str(bp.get("recommended_drop_anchor") or "climax_final_kill")
            buildup = float(bp.get("recommended_buildup_sec") or 1.2)
            target_dur = float(bp.get("target_duration_s") or pat.get("duration_s") or 15.0)
            act_v = "pentakill" if anchor == "first_kill_engage" else "outplay"
            ts_v = [1.5, 4.0, 6.8, 9.5, 12.2] if act_v == "pentakill" else [5.2, 8.8]
            gaps_v = [round(b - a, 2) for a, b in zip(ts_v, ts_v[1:])]
            _add_case(
                {
                    "action_type": act_v,
                    "champion": "Katarina",
                    "duration": min(24.0, max(11.0, target_dur)),
                    "kill_timestamps": ts_v,
                    "gaps": gaps_v,
                    "gap_has_combat": act_v == "pentakill",
                    "objective_secured": False,
                    "ally_banner_blocked": False,
                    "viral_reference_title": pat.get("title", ""),
                    "viral_hook_type": bp.get("hook_type") or pat.get("hook_type") or "DIRECT",
                    "viral_pacing_bucket": bp.get("pacing_bucket") or "balanced_13_20s",
                },
                custom_ans={
                    "operation": "KEEP_FULL_CONTINUOUS" if act_v == "pentakill" else "BRIDGE_GAP_SPEED_RAMP",
                    "style": "PRIMARY" if act_v == "pentakill" else "SPEED_RAMP_FLOW",
                    "buildup_sec": round(min(2.2, max(0.4, buildup)), 2),
                    "outro_sec": 1.3,
                    "zoom_aggression": 1.20,
                    "slowmo_duration": 0.9,
                    "camera_mode": "tight_player",
                    "drop_anchor": anchor,
                    "rationale": f"Wzorzec wirala LoL ({pat.get('views', 0)} wyśw., pacing={bp.get('pacing_bucket', 'balanced_13_20s')}, hook={bp.get('hook_type', 'DIRECT')}) — zachowaj multikill i wejście na {anchor}.",
                },
            )
    except Exception:
        pass

    # Jawne przypadki ochrony Pentakill/Quadrakill przed starymi ucięciami sprzed Etapu 16
    _add_case(
        {
            "action_type": "pentakill",
            "champion": "Katarina",
            "duration": 22.5,
            "kill_timestamps": [2.2, 5.1, 8.4, 12.0, 16.5],
            "gaps": [2.9, 3.3, 3.6, 4.5],
            "gap_has_combat": True,
            "objective_secured": False,
            "ally_banner_blocked": True,
            "historical_note": "legacy_pentakill_protected_after_etap16",
        },
        custom_ans={
            "operation": "KEEP_FULL_CONTINUOUS",
            "style": "PRIMARY",
            "buildup_sec": 1.4,
            "outro_sec": 1.6,
            "zoom_aggression": 1.18,
            "slowmo_duration": 1.0,
            "camera_mode": "tight_player",
            "drop_anchor": "first_kill_engage",
            "rationale": "Pentakill po poprawkach Etapu 16 nie może być zdegradowany przez historyczne ucięcia — pełna ciągłość i pewne zakończenie.",
        },
    )

    return out


def _make_overnight_cand(
    cid: str,
    fn: str,
    champ: str = "Katarina",
    action: str = "double",
    tier: str = "doublekill",
    kills: int = 2,
    dur: float = 12.0,
    hype: float = 76.0,
    watch: float = 82.0,
    qa: float = 92.0,
    final: float = 78.5,
    vis: float = 0.96,
    edge: float = 0.02,
    peak_px: float = 110.0,
    gap_s: float = 2.8,
    fk_s: float = 2.2,
    black_end: bool = False,
    hook_ok: bool = True,
    clip_cnt: int = 0,
    mismatch: bool = False,
    defects: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": cid,
        "filename": fn,
        "champion_name": champ,
        "champion_mismatch": mismatch,
        "action_type": action,
        "event_tier": tier,
        "kill_count": kills,
        "duration_s": dur,
        "hype_score": hype,
        "watchability_score": watch,
        "qa_score": qa,
        "final_score": final,
        "player_visible_ratio": vis,
        "player_edge_clip_ratio": edge,
        "camera_peak_step_px": peak_px,
        "longest_gap_out_sec": gap_s,
        "first_kill_out_sec": fk_s,
        "black_end_frame": black_end,
        "frame0_hook_legible": hook_ok,
        "audio_clip_gt_096": clip_cnt,
        "defects": list(defects or []),
    }


def _build_overnight_rank_training_examples() -> List[Dict[str, str]]:
    """Generuje >=18 przykładów QLoRA dla `overnight_rank` z twardymi zasadami Sykofankcja 0."""
    scenarios = [
        # 1. black_end_frame odrzucenie
        (
            [
                _make_overnight_cand("1", "kat_quad_blk.mp4", action="quadrakill", tier="quadrakill", kills=4, hype=88.0, watch=58.0, qa=65.0, final=72.0, black_end=True, defects=["black_end_frame"]),
                _make_overnight_cand("2", "kat_tri_clean.mp4", action="triple", tier="triplekill", kills=3, hype=78.0, watch=84.5, qa=94.0, final=81.2, fk_s=2.0),
                _make_overnight_cand("3", "kat_dbl_ok.mp4", hype=70.0, watch=79.0, qa=90.0, final=74.8, fk_s=2.5),
            ],
            "2",
            "Wybrano #2 (Katarina triple, Final 81.2, Watch 84.5) — czysty montaż i szybkie wejście (fk=2.0s). Klip #1 mimo wyższego hype odpada przez czarną klatkę końcową.",
            {"1": "Odrzucono: krytyczna wada black_end_frame=true i niski Watch 58.0.", "2": "Lider: Katarina triple, Final 81.2, Watch 84.5, czyste zakończenie.", "3": "Poprawny zapas Katarina double (Final 74.8)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_blk_2.mp4", action="triple", tier="triplekill", kills=3, hype=82.0, watch=61.0, qa=70.0, final=74.0, black_end=True, defects=["black_end_frame"]),
                _make_overnight_cand("2", "kat_1v1_clean.mp4", action="solo_bolo", tier="kill", kills=1, hype=74.0, watch=86.0, qa=95.0, final=80.1, fk_s=1.8),
            ],
            "2",
            "Wybrano #2 (Katarina solo_bolo, Final 80.1, Watch 86.0) z czystym kadrem i końcem. Klip #1 zdyskwalifikowany przez black_end_frame=true.",
            {"1": "Wada krytyczna black_end_frame=true — czarny ekran na końcu.", "2": "Czysta akcja 1v1 Katariny (Final 80.1, fk=1.8s)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_edge.mp4", hype=72.0, watch=76.0, qa=88.0, final=74.0, vis=0.71, defects=["player_offscreen_frames"]),
                _make_overnight_cand("2", "kat_blk.mp4", hype=80.0, watch=62.0, qa=68.0, final=73.5, black_end=True, defects=["black_end_frame"]),
                _make_overnight_cand("3", "kat_clean_win.mp4", action="triple", tier="triplekill", kills=3, hype=79.5, watch=83.0, qa=92.0, final=81.5, fk_s=2.1),
            ],
            "3",
            "Liderem jest #3 (Katarina triple, Final 81.5, Watch 83.0) — pełna widoczność 96% i zero wad krytycznych. #1 traci kadr gracza, a #2 ma czarny koniec.",
            {"1": "Słabsza widoczność gracza (player_visible_ratio=0.71).", "2": "Odrzucono: black_end_frame=true.", "3": "Najczystszy Katarina triple (Final 81.5, fk=2.1s)."},
        ),
        # 2. frame0_hook_legible=false odrzucenie
        (
            [
                _make_overnight_cand("1", "kat_nohook.mp4", action="quadrakill", tier="quadrakill", kills=4, hype=84.0, watch=69.0, qa=76.0, final=77.0, hook_ok=False, defects=["frame0_hook_illegible"]),
                _make_overnight_cand("2", "kat_goodhook.mp4", action="triple", tier="triplekill", kills=3, hype=77.0, watch=83.5, qa=94.0, final=80.4, hook_ok=True, fk_s=1.9),
            ],
            "2",
            "Wybrano #2 (Katarina triple, Final 80.4, Watch 83.5), ponieważ ma czytelny hook od klatki 0. Klip #1 odpada przez nieczytelny napis startowy.",
            {"1": "Odrzucono: frame0_hook_legible=false — nieczytelny hook na starcie.", "2": "Czytelny hook od 0.0s i wysoki Watch 83.5."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_dark0.mp4", hype=76.0, watch=66.0, qa=72.0, final=72.5, hook_ok=False, defects=["frame0_hook_illegible"]),
                _make_overnight_cand("2", "kat_ok0.mp4", action="double", tier="doublekill", kills=2, hype=75.0, watch=82.0, qa=92.0, final=79.2, fk_s=2.3),
            ],
            "2",
            "Zwycięzcą jest #2 (Katarina double, Final 79.2, Watch 82.0) — wyraźny banner startowy i płynna akcja. #1 traci otwarcie przez nieczytelny hook.",
            {"1": "Wada krytyczna: frame0_hook_legible=false.", "2": "Solidny double Katariny bez usterek technicznych (Final 79.2)."},
        ),
        # 3. audio_clip_gt_096 > 10 odrzucenie
        (
            [
                _make_overnight_cand("1", "kat_clip_audio.mp4", action="triple", tier="triplekill", kills=3, hype=81.0, watch=71.0, qa=74.0, final=76.2, clip_cnt=18, defects=["audio_clipping"]),
                _make_overnight_cand("2", "kat_audio_ok.mp4", action="double", tier="doublekill", kills=2, hype=75.5, watch=84.0, qa=93.0, final=80.0, clip_cnt=1, fk_s=2.0),
            ],
            "2",
            "Wybrano #2 (Katarina double, Final 80.0, Watch 84.0) z czystym miksem audio (clip=1). Klip #1 ma 18 przesterów audio >0.96.",
            {"1": "Odrzucono: przesterowane audio (audio_clip_gt_096=18).", "2": "Czysty dźwięk i wysoka oglądalność (Watch 84.0)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_audio_24.mp4", hype=79.0, watch=70.0, qa=72.0, final=74.8, clip_cnt=24, defects=["audio_clipping"]),
                _make_overnight_cand("2", "kat_slow_bad.mp4", hype=71.0, watch=68.0, qa=86.0, final=71.0, fk_s=5.9, defects=["slow_intro_gt_4.8s"]),
                _make_overnight_cand("3", "kat_clean_audio.mp4", action="triple", tier="triplekill", kills=3, hype=78.0, watch=85.0, qa=94.0, final=81.6, clip_cnt=0, fk_s=2.2),
            ],
            "3",
            "Liderem jest #3 (Katarina triple, Final 81.6, Watch 85.0, audio_clip=0). #1 ma przestery dźwięku (24), a #2 zbyt wolne wejście (5.9s).",
            {"1": "Przestery dźwięku (audio_clip_gt_096=24).", "2": "Wolne wejście (first_kill_out_sec=5.9s > 4.5s).", "3": "Czysty audio/wideo lider Katarina triple (Final 81.6)."},
        ),
        # 4. watchability_score < 65 odrzucenie
        (
            [
                _make_overnight_cand("1", "kat_lowwatch.mp4", action="quadrakill", tier="quadrakill", kills=4, hype=86.0, watch=54.0, qa=85.0, final=71.5, fk_s=6.8, vis=0.69, defects=["slow_intro_gt_4.8s", "player_offscreen_frames"]),
                _make_overnight_cand("2", "kat_highwatch.mp4", action="triple", tier="triplekill", kills=3, hype=76.0, watch=83.0, qa=92.0, final=79.8, fk_s=2.4),
            ],
            "2",
            "Wybrano #2 (Katarina triple, Final 79.8, Watch 83.0) mimo mniejszej liczby fragów niż #1. Klip #1 ma Watch 54.0 (<65), późny kill (6.8s) i ucina bohatera.",
            {"1": "Niska oglądalność Watch 54.0 (<65), późny start 6.8s i słaby kadr (0.69).", "2": "Stabilny Katarina triple (Watch 83.0, fk=2.4s)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_watch61.mp4", hype=78.0, watch=61.2, qa=84.0, final=71.0, peak_px=245.0, defects=["camera_jank_jump"]),
                _make_overnight_cand("2", "kat_watch84.mp4", hype=74.0, watch=84.2, qa=93.0, final=79.9, fk_s=1.7),
            ],
            "2",
            "Wybrano #2 (Katarina double, Final 79.9, Watch 84.2) dzięki płynnej kamerze i szybkiemu otwarciu (1.7s). #1 spada poniżej progu Watch 65 przez skoki kamery.",
            {"1": "Odrzucono: Watch 61.2 < 65 oraz szarpana kamera (245px).", "2": "Płynne śledzenie i Watch 84.2 (Final 79.9)."},
        ),
        # 5. champion_mismatch=True (inny bohater vs Katarina)
        (
            [
                _make_overnight_cand("1", "yone_mismatch.mp4", champ="Yone", mismatch=True, action="triple", tier="triplekill", kills=3, hype=79.0, watch=81.0, qa=91.0, final=80.2, fk_s=2.4, defects=["champion_mismatch"]),
                _make_overnight_cand("2", "kat_match.mp4", champ="Katarina", mismatch=False, action="double", tier="doublekill", kills=2, hype=76.0, watch=83.0, qa=93.0, final=79.8, fk_s=2.0),
            ],
            "2",
            "Preferowano #2 (Katarina double, Final 79.8, Watch 83.0) zgodnie z profilem kanału Katariny. Klip #1 to mismatch bohatera (Yone, champion_mismatch=true).",
            {"1": "UWAGA champion_mismatch=true (Yone zamiast Katariny) przy zbliżonym wyniku.", "2": "Czysty klip Katariny zgodny z profilem kanału (Watch 83.0)."},
        ),
        (
            [
                _make_overnight_cand("1", "khazix_mismatch.mp4", champ="Khazix", mismatch=True, action="double", tier="doublekill", kills=2, hype=77.0, watch=80.5, qa=90.0, final=78.9, fk_s=6.1, defects=["champion_mismatch", "slow_intro_gt_4.8s"]),
                _make_overnight_cand("2", "kat_fast.mp4", champ="Katarina", mismatch=False, action="double", tier="doublekill", kills=2, hype=75.0, watch=82.5, qa=92.0, final=78.6, fk_s=1.9),
            ],
            "2",
            "Wybrano #2 (Katarina double, Final 78.6, Watch 82.5) z błyskawicznym wejściem 1.9s. #1 odpada przez mismatch bohatera (Khazix) i wolne intro 6.1s.",
            {"1": "champion_mismatch=true (Khazix) i zbyt długi wstęp fk=6.1s.", "2": "Zgodny z kanałem Katarina double, szybki hook fk=1.9s."},
        ),
        (
            [
                _make_overnight_cand("1", "zed_offbrand.mp4", champ="Zed", mismatch=True, action="quadrakill", tier="quadrakill", kills=4, hype=81.0, watch=79.0, qa=89.0, final=80.5, defects=["champion_mismatch"]),
                _make_overnight_cand("2", "kat_quad_onbrand.mp4", champ="Katarina", mismatch=False, action="triple", tier="triplekill", kills=3, hype=78.5, watch=82.8, qa=92.0, final=80.1, fk_s=2.1),
            ],
            "2",
            "Wybrano #2 (Katarina triple, Final 80.1, Watch 82.8) mimo nieznacznie niższego Final od #1, bo #1 ma champion_mismatch=true (Zed).",
            {"1": "Klip z innym bohaterem (Zed — champion_mismatch=true).", "2": "Najlepszy klip Katariny bez wad technicznych (Watch 82.8)."},
        ),
        # 6. slow_intro_gt_4.8s i player_visible_ratio < 0.75
        (
            [
                _make_overnight_cand("1", "kat_slow_58.mp4", action="triple", tier="triplekill", kills=3, hype=79.0, watch=74.0, qa=90.0, final=77.5, fk_s=5.8, defects=["slow_intro_gt_4.8s"]),
                _make_overnight_cand("2", "kat_fast_18.mp4", action="double", tier="doublekill", kills=2, hype=76.5, watch=85.5, qa=94.0, final=81.0, fk_s=1.8),
            ],
            "2",
            "Wybrano #2 (Katarina double, Final 81.0, Watch 85.5, fk=1.8s), bo łapie uwagę od razu. Klip #1 ma 5.8s martwego wstępu przed pierwszym killem.",
            {"1": "Ostrzeżenie: powolny wstęp first_kill_out_sec=5.8s (>4.5s).", "2": "Mocny hook i 1. kill już w 1.8s (Watch 85.5)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_offscr_62.mp4", action="triple", tier="triplekill", kills=3, hype=80.0, watch=70.0, qa=88.0, final=76.0, vis=0.62, edge=0.22, defects=["player_offscreen_frames"]),
                _make_overnight_cand("2", "kat_centered_97.mp4", action="triple", tier="triplekill", kills=3, hype=77.5, watch=86.0, qa=95.0, final=82.1, vis=0.97, fk_s=2.0),
            ],
            "2",
            "Liderem jest #2 (Katarina triple, Final 82.1, Watch 86.0) z widocznością gracza 97%. W #1 Katarina ucieka poza kadr (vis=0.62).",
            {"1": "Katarina poza kadrem w zbyt wielu klatkach (player_visible_ratio=0.62).", "2": "Kadr wycentrowany (vis=0.97) i wysoki Watch 86.0."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_gap6s.mp4", action="double", tier="doublekill", kills=2, hype=73.0, watch=72.0, qa=90.0, final=73.5, gap_s=6.4, defects=["slow_gap_gt_5.5s"]),
                _make_overnight_cand("2", "kat_tight_gap.mp4", action="double", tier="doublekill", kills=2, hype=75.0, watch=84.0, qa=94.0, final=80.2, gap_s=2.3, fk_s=1.9),
            ],
            "2",
            "Wybrano #2 (Katarina double, Final 80.2, Watch 84.0) o zwartym tempie (gap=2.3s). Klip #1 ma 6.4s przerwy bez akcji między zabójstwami.",
            {"1": "Zbyt długa przerwa między fragami (longest_gap_out_sec=6.4s).", "2": "Dynamiczne tempo (gap=2.3s, fk=1.9s) bez przestojów."},
        ),
        # 7. Czyste wielokrotne rankingi Katariny (quadra / penta / triple / double)
        (
            [
                _make_overnight_cand("1", "kat_quad_top.mp4", action="quadrakill", tier="quadrakill", kills=4, dur=16.5, hype=89.0, watch=86.5, qa=95.0, final=88.2, vis=0.97, fk_s=2.1),
                _make_overnight_cand("2", "kat_tri_2.mp4", action="triple", tier="triplekill", kills=3, dur=13.2, hype=79.0, watch=83.0, qa=93.0, final=81.4, vis=0.95, fk_s=2.4),
                _make_overnight_cand("3", "kat_dbl_3.mp4", action="double", tier="doublekill", kills=2, dur=11.0, hype=72.0, watch=80.0, qa=92.0, final=76.5, vis=0.94, fk_s=2.0),
            ],
            "1",
            "Bezkonkurencyjny lider #1 (Katarina quadrakill, Final 88.2, Watch 86.5) z pełną widocznością 97% i szybkim 1. fragiem (2.1s). Kandydata #2 można użyć jako zapas na drugi slot.",
            {"1": "Najmocniejszy materiał batcha: czysta quadra Katariny (Final 88.2, Watch 86.5).", "2": "Solidny zapasowy triple (Final 81.4).", "3": "Poprawny double na wypełnienie kolejki (Final 76.5)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_penta_clean.mp4", action="pentakill", tier="pentakill", kills=5, dur=19.8, hype=93.0, watch=85.0, qa=94.0, final=90.1, vis=0.96, fk_s=2.2),
                _make_overnight_cand("2", "kat_dbl_clean.mp4", action="double", tier="doublekill", kills=2, dur=10.8, hype=73.0, watch=84.0, qa=92.0, final=78.1, fk_s=1.7),
            ],
            "1",
            "Zwycięża #1 (Katarina pentakill, Final 90.1, Watch 85.0) — pełny 5-kill bez czarnych klatek ani ucinania kamery. #2 jest dobrym krótkim rezerwowym klipem.",
            {"1": "Czysty pentakill Katariny (Final 90.1, Watch 85.0, vis=0.96).", "2": "Szybki double z hookiem w 1.7s (Final 78.1)."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_dbl_a.mp4", action="double", tier="doublekill", kills=2, dur=11.2, hype=74.0, watch=79.0, qa=91.0, final=76.8, fk_s=3.6),
                _make_overnight_cand("2", "kat_tri_b.mp4", action="triple", tier="triplekill", kills=3, dur=14.1, hype=81.5, watch=84.2, qa=94.0, final=83.1, vis=0.96, fk_s=1.8),
                _make_overnight_cand("3", "kat_clutch_c.mp4", action="clutch", tier="kill", kills=1, dur=10.5, hype=76.0, watch=81.0, qa=92.0, final=78.4, fk_s=2.5),
            ],
            "2",
            "Wybrano #2 (Katarina triple, Final 83.1, Watch 84.2) dzięki szybszemu wejściu (1.8s) i wyraźnemu wyższemu wynikowi nad #1 i #3.",
            {"1": "Przeciętny wstęp 3.6s (Final 76.8).", "2": "Lider: Katarina triple, szybki kill 1.8s, Watch 84.2.", "3": "Dobry krótki clutch 1% HP (Final 78.4)."},
        ),
        # 8. Wszystkie kandydaty z wadami -> uczciwe ostrzeżenie Sykofankcja 0 (wybór najmniej zepsutego z jawną blokadą)
        (
            [
                _make_overnight_cand("1", "kat_flaw_a.mp4", action="double", tier="doublekill", kills=2, hype=73.0, watch=69.5, qa=86.0, final=71.2, fk_s=5.4, vis=0.73, defects=["slow_intro_gt_4.8s", "player_offscreen_frames"]),
                _make_overnight_cand("2", "kat_flaw_b.mp4", action="double", tier="doublekill", kills=2, hype=71.0, watch=59.0, qa=70.0, final=65.0, black_end=True, defects=["black_end_frame"]),
            ],
            "1",
            "UWAGA (Sykofankcja 0): oba klipy wymagają poprawki przed publikacją. #1 (Katarina double, Final 71.2, Watch 69.5) jest mniejszym złem od #2 z black_end_frame, ale ma wolne wejście 5.4s i słaby kadr (0.73).",
            {"1": "UWAGA wady: slow_intro_gt_4.8s (5.4s) i niska widoczność 0.73 — wymaga korekty.", "2": "Odrzucono całkowicie: black_end_frame=true i Watch 59.0."},
        ),
        (
            [
                _make_overnight_cand("1", "kat_quad_fix.mp4", action="quadrakill", tier="quadrakill", kills=4, hype=84.0, watch=79.5, qa=91.0, final=82.4, vis=0.94, fk_s=2.3),
                _make_overnight_cand("2", "kat_dbl_off.mp4", action="double", tier="doublekill", kills=2, hype=74.0, watch=68.0, qa=87.0, final=71.8, vis=0.67, defects=["player_offscreen_frames"]),
                _make_overnight_cand("3", "kat_tri_clip.mp4", action="triple", tier="triplekill", kills=3, hype=79.0, watch=74.0, qa=76.0, final=76.1, clip_cnt=14, defects=["audio_clipping"]),
                _make_overnight_cand("4", "kat_dbl_blk.mp4", action="double", tier="doublekill", kills=2, hype=75.0, watch=62.0, qa=69.0, final=68.5, black_end=True, defects=["black_end_frame"]),
            ],
            "1",
            "Jedynym czystym kandydatem do publikacji jest #1 (Katarina quadrakill, Final 82.4, Watch 79.5). Pozostałe mają kolejno ucięty kadr (#2), przestery audio (#3) oraz czarną klatkę (#4).",
            {"1": "Czysta quadra Katariny gotowa do kolejki (Final 82.4, fk=2.3s).", "2": "Wada: player_offscreen_frames (vis=0.67).", "3": "Wada: audio_clip_gt_096=14.", "4": "Odrzucono: black_end_frame=true."},
        ),
    ]

    out: List[Dict[str, str]] = []
    for cands, win_id, summary_pl, notes_pl in scenarios:
        qual = sum(1 for c in cands if not c["black_end_frame"] and c["frame0_hook_legible"] and c["watchability_score"] >= 65.0)
        pload = {
            "candidates": cands,
            "scan_stats": {"qualified": qual, "rejected": max(0, len(cands) - qual)},
        }
        ans = {
            "winner_id": win_id,
            "summary_pl": summary_pl,
            "notes_pl": notes_pl,
        }
        out.append({
            "instruction": build_synapsa_instruction("overnight_rank", pload),
            "output": json.dumps(ans, ensure_ascii=False),
        })
    return out


def _tokenize_completion_only(ex: Dict[str, Any], tokenizer: Any, max_length: int) -> Dict[str, Any]:
    """Maskuje tokeny promptu wartością -100 w `labels`, trenując stratę wyłącznie na odpowiedzi JSON."""
    prompt_str = f"### Instruction:\n{ex['instruction']}\n\n### Response:\n"
    resp_str = f"{ex['output']}<|endoftext|>"
    prompt_ids = list(tokenizer(prompt_str, add_special_tokens=True)["input_ids"])
    resp_ids = list(tokenizer(resp_str, add_special_tokens=False)["input_ids"])
    if not resp_ids and tokenizer.eos_token_id is not None:
        resp_ids = [int(tokenizer.eos_token_id)]

    # Zostaw miejsce dla pełnej odpowiedzi JSON, obcinając prompt tylko w razie przepełnienia max_length
    min_resp = min(len(resp_ids), max(96, max_length // 3))
    max_prompt = max(64, max_length - max(len(resp_ids), min_resp))
    if len(prompt_ids) > max_prompt:
        prompt_ids = prompt_ids[:max_prompt]
    avail_resp = max(16, max_length - len(prompt_ids))
    if len(resp_ids) > avail_resp:
        resp_ids = resp_ids[:avail_resp]

    input_ids = prompt_ids + resp_ids
    attention_mask = [1] * len(input_ids)
    labels = ([-100] * len(prompt_ids)) + list(resp_ids)

    pad_id = int(tokenizer.pad_token_id if tokenizer.pad_token_id is not None else (tokenizer.eos_token_id or 0))
    pad_len = max(0, max_length - len(input_ids))
    if pad_len > 0:
        input_ids.extend([pad_id] * pad_len)
        attention_mask.extend([0] * pad_len)
        labels.extend([-100] * pad_len)

    if not any(lbl != -100 for lbl in labels):
        labels[-1] = int(tokenizer.eos_token_id or pad_id)
    return {
        "input_ids": input_ids[:max_length],
        "attention_mask": attention_mask[:max_length],
        "labels": labels[:max_length],
    }


def _close_lazy_safetensors(mu_mod: Any) -> None:
    for sd in getattr(mu_mod, "_lazy_sds", []):
        sd.close_and_clear()
    if hasattr(mu_mod, "_lazy_sds"):
        mu_mod._lazy_sds.clear()
    gc.collect()


def train_title_lora(
    dataset_path: Path = DATASET_PATH,
    output_dir: str = TITLE_ADAPTER_DIR,
    max_steps: int = 60,
) -> Dict[str, Any]:
    """Trenuje QLoRA adapter dla Synapsy na RTX 3060 12 GB (completion masking + 90/10 eval_loss)."""
    _setup_windows_triton_mock()
    _install_lazy_safetensors_loader()
    import torch
    import transformers.modeling_utils as mu
    from datasets import load_dataset
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
        default_data_collator,
    )

    if not dataset_path.exists():
        raise FileNotFoundError(f"Brak zbioru treningowego: {dataset_path}")

    out_path = Path(output_dir)
    if (out_path / "adapter_config.json").is_file():
        backup_dir = Path(SYNAPSA_ROOT) / "adapters_shortsyt_titles_backup_prev"
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.copytree(out_path, backup_dir)

    ds = load_dataset("json", data_files=str(dataset_path), split="train")
    eval_n = max(12, min(len(ds) // 5, int(round(len(ds) * 0.1)))) if len(ds) >= 24 else max(1, len(ds) // 10)
    split_ds = ds.train_test_split(test_size=eval_n, seed=42)
    train_raw = split_ds["train"]
    eval_raw = split_ds["test"]

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    out_path.mkdir(parents=True, exist_ok=True)
    tmp_ckpt_dir = out_path / "_checkpoints"

    last_err: Optional[Exception] = None
    used_max_len = 1024
    train_res = None
    eval_res: Dict[str, Any] = {}
    trained_model = None

    for try_len in (1024, 768):
        model = None
        trainer = None
        try:
            gc.collect()
            torch.cuda.empty_cache()
            tok_train = train_raw.map(lambda ex: _tokenize_completion_only(ex, tokenizer, try_len), remove_columns=train_raw.column_names)
            tok_eval = eval_raw.map(lambda ex: _tokenize_completion_only(ex, tokenizer, try_len), remove_columns=eval_raw.column_names)

            model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_NAME,
                quantization_config=bnb_config,
                device_map={"": 0},
                trust_remote_code=True,
                low_cpu_mem_usage=True,
                local_files_only=True,
            )
            _close_lazy_safetensors(mu)
            model = prepare_model_for_kbit_training(model)
            model.gradient_checkpointing_enable()
            model.config.use_cache = False
            model = get_peft_model(model, peft_config)

            trainer = Trainer(
                model=model,
                train_dataset=tok_train,
                eval_dataset=tok_eval,
                args=TrainingArguments(
                    output_dir=str(tmp_ckpt_dir),
                    per_device_train_batch_size=1,
                    per_device_eval_batch_size=1,
                    gradient_accumulation_steps=4,
                    optim="paged_adamw_8bit",
                    learning_rate=1.5e-4,
                    lr_scheduler_type="cosine",
                    warmup_ratio=0.08,
                    max_steps=max_steps,
                    fp16=True,
                    logging_steps=10,
                    eval_strategy="steps",
                    eval_steps=40,
                    prediction_loss_only=True,
                    save_strategy="no",
                    report_to="none",
                    dataloader_num_workers=0,
                ),
                data_collator=default_data_collator,
            )
            train_res = trainer.train()
            eval_res = trainer.evaluate()
            used_max_len = try_len
            trained_model = model
            break
        except Exception as exc:
            _close_lazy_safetensors(mu)
            is_oom = isinstance(exc, torch.cuda.OutOfMemoryError) or "out of memory" in str(exc).lower()
            if trainer is not None:
                del trainer
            if model is not None:
                del model
            gc.collect()
            torch.cuda.empty_cache()
            last_err = exc
            if is_oom and try_len == 1024:
                print("⚠️ CUDA OOM przy max_length=1024 — ponawiam trening z max_length=768...")
                continue
            raise

    if trained_model is None or train_res is None:
        raise RuntimeError(f"Trening QLoRA nie powiódł się: {last_err}")

    trained_model.save_pretrained(str(out_path))
    tokenizer.save_pretrained(str(out_path))

    cfg_file = out_path / "adapter_config.json"
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        cfg["base_model_name_or_path"] = BASE_MODEL_NAME
        cfg_file.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    metrics = {
        "base_model": BASE_MODEL_NAME,
        "adapter_dir": str(out_path),
        "dataset_examples": len(ds),
        "train_examples": len(train_raw),
        "eval_examples": len(eval_raw),
        "max_length": used_max_len,
        "max_steps": max_steps,
        "train_loss": round(float(train_res.training_loss), 4),
        "eval_loss": round(float(eval_res.get("eval_loss", 0.0)), 4) if eval_res.get("eval_loss") is not None else None,
        "runtime_s": round(float((train_res.metrics or {}).get("train_runtime", 0.0)), 2),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_path / "training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if tmp_ckpt_dir.exists():
        shutil.rmtree(tmp_ckpt_dir, ignore_errors=True)
    del trained_model
    gc.collect()
    torch.cuda.empty_cache()
    print("SYNAPSA_TRAIN_METRICS:", json.dumps(metrics))
    return metrics


def evaluate_synapsa_adapter(
    adapter_dir: str = TITLE_ADAPTER_DIR,
    eval_tag: str = "eval",
) -> Dict[str, Any]:
    """Stały benchmark 12 zadań dla adaptera Synapsy (Before vs After z rollbackiem w razie regresji)."""
    _setup_windows_triton_mock()
    _install_lazy_safetensors_loader()
    import torch
    import transformers.modeling_utils as mu
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    eval_cases: List[Dict[str, Any]] = [
        # 4 lol_metadata
        {
            "id": "meta_double",
            "group": "lol_metadata",
            "task": "lol_metadata",
            "action_type": "double",
            "max_new_tokens": 320,
            "payload": {"champion": "Katarina", "action_type": "double", "kill_count": 2, "kill_span_s": 2.1, "min_hp_pct": 64.0, "low_hp_survival": False, "enemies_in_fight": 2, "map_zone": "Mid Lane", "hud_spells_verified": False},
        },
        {
            "id": "meta_triple",
            "group": "lol_metadata",
            "task": "lol_metadata",
            "action_type": "triple",
            "max_new_tokens": 320,
            "payload": {"champion": "Katarina", "action_type": "triple", "kill_count": 3, "kill_span_s": 2.8, "min_hp_pct": 48.0, "low_hp_survival": False, "enemies_in_fight": 3, "map_zone": "River", "hud_spells_verified": False},
        },
        {
            "id": "meta_quadra",
            "group": "lol_metadata",
            "task": "lol_metadata",
            "action_type": "quadrakill",
            "max_new_tokens": 320,
            "payload": {"champion": "Katarina", "action_type": "quadrakill", "kill_count": 4, "kill_span_s": 3.4, "min_hp_pct": 35.0, "low_hp_survival": False, "enemies_in_fight": 4, "map_zone": "Dragon Pit", "hud_spells_verified": False},
        },
        {
            "id": "meta_clutch_1hp",
            "group": "lol_metadata",
            "task": "lol_metadata",
            "action_type": "clutch",
            "max_new_tokens": 320,
            "payload": {"champion": "Katarina", "action_type": "clutch", "kill_count": 1, "kill_span_s": 0.0, "min_hp_pct": 4.2, "low_hp_survival": True, "enemies_in_fight": 2, "map_zone": "Top Lane", "hud_spells_verified": False},
        },
        # 3 montage_director
        {
            "id": "dir_clean_triple",
            "group": "montage_director",
            "task": "montage_director",
            "max_new_tokens": 180,
            "payload": {"action_type": "triple", "champion": "Katarina", "duration": 15.0, "kill_timestamps": [2.2, 5.1, 8.2], "gaps": [2.9, 3.1], "gap_has_combat": True, "objective_secured": False, "ally_banner_blocked": False, "min_hp_pct": 38.0, "param_ranges": {k: (v.get("range") or v.get("allowed")) for k, v in PARAM_EFFECT_CONTRACT.items()}},
        },
        {
            "id": "dir_slow_intro",
            "group": "montage_director",
            "task": "montage_director",
            "max_new_tokens": 180,
            "payload": {"action_type": "double", "champion": "Katarina", "duration": 16.0, "kill_timestamps": [7.5, 9.8], "gaps": [2.3], "gap_has_combat": False, "objective_secured": False, "ally_banner_blocked": False, "historical_avg_rwi": 63.0, "param_ranges": {k: (v.get("range") or v.get("allowed")) for k, v in PARAM_EFFECT_CONTRACT.items()}},
        },
        {
            "id": "dir_long_gap_quad",
            "group": "montage_director",
            "task": "montage_director",
            "max_new_tokens": 180,
            "payload": {"action_type": "quadrakill", "champion": "Katarina", "duration": 22.0, "kill_timestamps": [2.0, 11.2, 13.8, 16.4], "gaps": [9.2, 2.6, 2.6], "gap_has_combat": False, "objective_secured": False, "ally_banner_blocked": False, "param_ranges": {k: (v.get("range") or v.get("allowed")) for k, v in PARAM_EFFECT_CONTRACT.items()}},
        },
        # 3 overnight_rank Sykofankcja 0
        {
            "id": "rank_black_end",
            "group": "overnight_rank",
            "task": "overnight_rank",
            "expected_winner": "2",
            "max_new_tokens": 420,
            "payload": {
                "candidates": [
                    _make_overnight_cand("1", "blk.mp4", action="quadrakill", tier="quadrakill", kills=4, hype=88.0, watch=58.0, qa=65.0, final=72.0, black_end=True, defects=["black_end_frame"]),
                    _make_overnight_cand("2", "clean.mp4", action="triple", tier="triplekill", kills=3, hype=78.0, watch=84.5, qa=94.0, final=81.2, fk_s=2.0),
                ],
                "scan_stats": {"qualified": 1, "rejected": 1},
            },
        },
        {
            "id": "rank_mismatch_slow",
            "group": "overnight_rank",
            "task": "overnight_rank",
            "expected_winner": "2",
            "max_new_tokens": 420,
            "payload": {
                "candidates": [
                    _make_overnight_cand("1", "yone.mp4", champ="Yone", mismatch=True, action="triple", tier="triplekill", kills=3, hype=79.0, watch=79.5, qa=90.0, final=79.2, fk_s=6.1, defects=["champion_mismatch", "slow_intro_gt_4.8s"]),
                    _make_overnight_cand("2", "kat.mp4", champ="Katarina", mismatch=False, action="double", tier="doublekill", kills=2, hype=76.0, watch=83.0, qa=93.0, final=79.8, fk_s=1.9),
                ],
                "scan_stats": {"qualified": 2, "rejected": 0},
            },
        },
        {
            "id": "rank_watch_audio",
            "group": "overnight_rank",
            "task": "overnight_rank",
            "expected_winner": "3",
            "max_new_tokens": 420,
            "payload": {
                "candidates": [
                    _make_overnight_cand("1", "loww.mp4", hype=80.0, watch=54.0, qa=72.0, final=69.5, clip_cnt=18, defects=["audio_clipping"]),
                    _make_overnight_cand("2", "nohk.mp4", hype=75.0, watch=68.0, qa=74.0, final=71.0, hook_ok=False, defects=["frame0_hook_illegible"]),
                    _make_overnight_cand("3", "ok3.mp4", action="triple", tier="triplekill", kills=3, hype=78.5, watch=84.0, qa=94.0, final=81.5, fk_s=2.0),
                ],
                "scan_stats": {"qualified": 1, "rejected": 2},
            },
        },
        # 2 niche / social
        {
            "id": "niche_kebab_pl",
            "group": "niche_social",
            "task": "account_metadata",
            "max_new_tokens": 320,
            "payload": {"account_name": "Kebab Królewski Gdańsk", "content_mode": "FOOD_GASTRO", "language": "PL", "subject_name": "Rollo Wołowe z Pieca", "action_type": "przygotowanie", "value_proposition": "Chrupiące ciasto i świeże zioła w 2 minuty", "cta_text": "Odwiedź lokal na ul. Długiej 👇", "forbidden_words": ["Katarina", "League of Legends", "Pentakill"]},
        },
        {
            "id": "social_ig_clean",
            "group": "niche_social",
            "task": "social_caption",
            "max_new_tokens": 220,
            "payload": {"platform": "instagram", "champion": "Katarina", "action_type": "quadrakill", "kill_span_s": 3.1},
        },
    ]

    adapter_cfg = Path(adapter_dir) / "adapter_config.json"
    base_name = BASE_MODEL_NAME
    use_adapter = adapter_cfg.is_file()
    if use_adapter:
        try:
            base_name = json.loads(adapter_cfg.read_text(encoding="utf-8")).get("base_model_name_or_path", BASE_MODEL_NAME)
        except Exception:
            pass

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_name,
        quantization_config=bnb_config,
        torch_dtype=torch.float16,
        device_map={"": 0} if torch.cuda.is_available() else "auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    tok_src = str(adapter_dir) if use_adapter else base_name
    tokenizer = AutoTokenizer.from_pretrained(tok_src, trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    if use_adapter:
        model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()
    _close_lazy_safetensors(mu)

    valid_ops = {"KEEP_FULL_CONTINUOUS", "DROP_ISOLATED_FIRST_KILL", "DROP_ISOLATED_LAST_KILL", "BRIDGE_GAP_SPEED_RAMP", "SWITCH_STYLE_IN_MEDIA_RES"}
    valid_styles = {"PRIMARY", "SPEED_RAMP_FLOW", "IN_MEDIA_RES"}
    bad_terms = (*_AI_JARGON_PHRASES, *_BANNED_TITLE_PHRASES, *_SPELL_TERMS)

    case_results: List[Dict[str, Any]] = []
    try:
        for case in eval_cases:
            inst = build_synapsa_instruction(case["task"], case["payload"])
            prompt_text = f"### Instruction:\n{inst}\n\n### Response:\n"
            inputs = tokenizer([prompt_text], return_tensors="pt").to(model.device)
            with torch.no_grad():
                out_ids = model.generate(
                    **inputs,
                    max_new_tokens=int(case["max_new_tokens"]),
                    do_sample=False,
                    repetition_penalty=1.12,
                    pad_token_id=tokenizer.eos_token_id,
                )
            gen_ids = out_ids[0][inputs["input_ids"].shape[1]:]
            raw_reply = tokenizer.decode(gen_ids, skip_special_tokens=True)
            parsed: Optional[Dict[str, Any]] = None
            json_ok = False
            try:
                parsed = _extract_first_json_object(raw_reply)
                json_ok = isinstance(parsed, dict) and len(parsed) > 0
            except Exception:
                parsed = None

            item_rec: Dict[str, Any] = {
                "id": case["id"],
                "group": case["group"],
                "json_ok": json_ok,
                "raw_preview": raw_reply[:240],
            }
            if json_ok and parsed is not None:
                if case["group"] == "lol_metadata":
                    cands = [str(x) for x in (parsed.get("title_candidates") or []) if isinstance(x, str)]
                    hook = str(parsed.get("hook_text") or "")
                    desc = str(parsed.get("description") or "")
                    pin = str(parsed.get("pinned_comment") or "")
                    combined = " ".join(cands + [hook, desc, pin]).lower()
                    jargon_free = not any(bt in combined for bt in bad_terms)
                    act_low = case["action_type"].lower()
                    tier_clean = True
                    if act_low == "double" and re.search(r"\b(triple|quadra|penta)\b", " ".join(cands).lower()):
                        tier_clean = False
                    elif act_low == "triple" and re.search(r"\b(quadra|penta)\b", " ".join(cands).lower()):
                        tier_clean = False
                    elif act_low == "quadrakill" and re.search(r"\b(triple|penta)\b", " ".join(cands).lower()):
                        tier_clean = False
                    generic_hook = hook.strip().upper() in ("", "INSANE OUTPLAY!", "NICE PLAY!")
                    item_rec["zero_jargon_ok"] = bool(jargon_free and tier_clean and len(cands) >= 3 and not generic_hook)
                elif case["group"] == "montage_director":
                    op = str(parsed.get("operation") or "")
                    st = str(parsed.get("style") or "")
                    cm = str(parsed.get("camera_mode") or "")
                    da = str(parsed.get("drop_anchor") or "")
                    bounds_ok = True
                    for pk in ("buildup_sec", "outro_sec", "zoom_aggression", "slowmo_duration"):
                        lo, hi = PARAM_EFFECT_CONTRACT[pk]["range"]
                        val = parsed.get(pk)
                        if not isinstance(val, (int, float)) or float(val) < lo - 0.05 or float(val) > hi + 0.05:
                            bounds_ok = False
                    item_rec["director_ok"] = bool(op in valid_ops and st in valid_styles and cm in {"tight_player", "duel_centroid"} and da in {"first_kill_engage", "climax_final_kill"} and bounds_ok)
                elif case["group"] == "overnight_rank":
                    wid = str(parsed.get("winner_id") or "").strip().lstrip("#")
                    item_rec["winner_id"] = wid
                    item_rec["rank_ok"] = wid == case["expected_winner"]
                elif case["group"] == "niche_social":
                    text_blob = json.dumps(parsed, ensure_ascii=False).lower()
                    if case["id"] == "niche_kebab_pl":
                        cands = parsed.get("title_candidates") or []
                        has_gaming = any(g in text_blob for g in ("katarina", "league of legends", "pentakill", "ranked", "outplay", "dagger"))
                        item_rec["niche_clean_ok"] = bool(isinstance(cands, list) and len(cands) >= 2 and not has_gaming)
                    else:
                        cap = str(parsed.get("caption") or "").strip()
                        has_spam = any(s in cap.lower() for s in ("facebook.com", "rate 1-10", "rate this"))
                        item_rec["niche_clean_ok"] = bool(len(cap) >= 12 and not has_spam)
            case_results.append(item_rec)
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()

    def _rate(group: str, field: str) -> float:
        sub = [r for r in case_results if group == "*" or r["group"] == group]
        return round(sum(1 for r in sub if r.get(field)) / max(1, len(sub)), 4)

    json_rate = _rate("*", "json_ok")
    jargon_rate = _rate("lol_metadata", "zero_jargon_ok")
    director_rate = _rate("montage_director", "director_ok")
    rank_rate = _rate("overnight_rank", "rank_ok")
    niche_rate = _rate("niche_social", "niche_clean_ok")
    benchmark_score = round(25.0 * json_rate + 25.0 * jargon_rate + 20.0 * director_rate + 20.0 * rank_rate + 10.0 * niche_rate, 2)

    report = {
        "eval_tag": eval_tag,
        "adapter_dir": str(adapter_dir),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(case_results),
        "json_valid_rate": json_rate,
        "zero_jargon_rate": jargon_rate,
        "valid_director_enum_rate": director_rate,
        "sykofankcja0_rank_accuracy": rank_rate,
        "niche_pl_clean_rate": niche_rate,
        "benchmark_score": benchmark_score,
        "cases": case_results,
    }
    report_path = Path(SYNAPSA_ROOT) / f"eval_report_{eval_tag}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    summary_line = {k: report[k] for k in ("eval_tag", "total_cases", "json_valid_rate", "zero_jargon_rate", "valid_director_enum_rate", "sykofankcja0_rank_accuracy", "niche_pl_clean_rate", "benchmark_score")}
    summary_line["report_path"] = str(report_path)
    print("SYNAPSA_EVAL_METRICS:", json.dumps(summary_line, ensure_ascii=False))
    return report


def sync_incremental_training_dataset(
    directive: Optional[Dict[str, Any]] = None,
    min_new_for_retrain: int = 5,
    write_dataset: bool = True,
    output_path: Optional[Path] = None,
    adapter_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Odświeża zbiór QLoRA z najnowszymi danymi 48h i hard_cases_memory.json
    oraz zwraca status gotowości do okresowego dotrenowania (`retrain_ready`).
    """
    target_ds = Path(output_path) if output_path is not None else DATASET_PATH
    should_write = bool(write_dataset or output_path is not None)
    info = build_training_dataset(
        output_path=target_ds,
        mine_youtube=False,
        directive_override=directive,
        write_file=should_write,
    )
    total_examples = int(info.get("total_examples", 0))
    target_adapter = Path(adapter_dir) if adapter_dir is not None else Path(TITLE_ADAPTER_DIR)
    metrics_path = target_adapter / "training_metrics.json"
    last_trained_examples = 0
    trained_at = None
    if metrics_path.is_file():
        try:
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
            last_trained_examples = int(m.get("dataset_examples") or 0)
            trained_at = m.get("trained_at") or datetime.fromtimestamp(metrics_path.stat().st_mtime, timezone.utc).isoformat()
        except Exception:
            pass
    new_examples = max(0, total_examples - last_trained_examples)
    return {
        "dataset_path": str(target_ds),
        "dataset_written": should_write,
        "total_examples": total_examples,
        "director_examples": int(info.get("director_examples", 0)),
        "overnight_rank_examples": int(info.get("overnight_rank_examples", 0)),
        "engineering_cause_effect_examples": int(info.get("engineering_cause_effect_examples", 0)),
        "watchability_examples": int(info.get("watchability_examples", 0)),
        "historical_evolution_examples": int(info.get("historical_evolution_examples", 0)),
        "last_trained_examples": last_trained_examples,
        "new_examples_since_train": new_examples,
        "min_new_for_retrain": int(min_new_for_retrain),
        "retrain_ready": bool(new_examples >= int(min_new_for_retrain)),
        "trained_at": trained_at,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dataset", action="store_true")
    ap.add_argument("--sync-memory", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--eval-tag", type=str, default="eval")
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--no-yt-mine", action="store_true")
    args = ap.parse_args()

    if args.sync_memory:
        from lol_agent.synapsa_conversation_learner import sync_engineering_memory
        print("ENGINEERING_MEMORY:", json.dumps(sync_engineering_memory(include_transcripts=True), ensure_ascii=False))
    if args.build_dataset or (args.train and not DATASET_PATH.exists()):
        info = build_training_dataset(mine_youtube=not args.no_yt_mine)
        print("DATASET_BUILT:", json.dumps(info, ensure_ascii=False))
    if args.train:
        train_title_lora(max_steps=args.steps)
    if args.eval:
        evaluate_synapsa_adapter(eval_tag=args.eval_tag)
