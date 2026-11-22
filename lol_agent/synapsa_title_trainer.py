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
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from lol_agent.synapsa_engine import (
    BASE_MODEL_NAME,
    SYNAPSA_ROOT,
    TITLE_ADAPTER_DIR,
    _install_lazy_safetensors_loader,
    _setup_windows_triton_mock,
    build_synapsa_instruction,
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

    # Pula viralowych tytułów alternatywnych (POV / Curiosity-Gap / Ego-Check / Time-Math)
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
            "When They Group Straight Into Resets 🔥",
            "Wait For The Fifth Reset Kill 👑",
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
            "Double Takedown on Pure Spacing 🔥",
            "Cleanest 2-for-0 Turnaround 👑",
        ],
        "outplay": [
            "POV: Pixel-Perfect Reset Execution ⚡",
            "How Did That Actually Work? 🧠",
            "They Overextended Straight Into This 💀",
            "Wait Until You See The Flip 🔥",
        ],
    }

    examples: List[Dict[str, str]] = []
    for idx, row in enumerate(source_rows):
        clean_title = _strip_title_tags(row.get("title", ""))
        # Usuń stare prefiksy/spelle z historycznych przykładów przy treningu
        clean_title = re.sub(r"^(Master|Diamond|Emerald|Gold)\s+", "", clean_title, flags=re.I).strip()
        if any(bad in clean_title.lower() for bad in ("flash", "ignite", "exhaust", "bad idea", "rate 1-10", "mistake", "regret")):
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
            "triple": "TRIPLE RESET CHAIN",
            "double": "INSTANT DOUBLE DOWN",
        }
        out_json = {
            "title_candidates": cands,
            "hook_text": hook_map.get(act, "CLEAN MECHANICAL OUTPLAY"),
            "description": f"High-tempo Katarina {act.replace('_', ' ')} execution powered by tight reset spacing. Would you have chased here or backed off?",
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
    ]

    for task, pload, out_obj in multi_acc_samples:
        examples.append({
            "instruction": build_synapsa_instruction(task, pload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    # 4. Przykłady Montage Director z hard_cases_memory.json + kontrastowych scenariuszy 48h
    director_examples = _build_director_training_examples(directive, lol_dir)
    examples.extend(director_examples)

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
        "channel_and_yt_examples": len(examples) - len(multi_acc_samples) - len(director_examples) - len(cause_effect_examples) - len(watchability_examples) - len(historical_examples),
        "multi_account_and_reply_examples": len(multi_acc_samples),
        "director_examples": len(director_examples),
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
                    "operation": "KEEP_FULL_CONTINUOUS" if act_v == "pentakill" else "SPEED_RAMP_FLOW",
                    "style": "AGGRESSIVE_ZOOM" if act_v == "pentakill" else "SPEED_RAMP_FLOW",
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
            "style": "AGGRESSIVE_ZOOM",
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


def train_title_lora(
    dataset_path: Path = DATASET_PATH,
    output_dir: str = TITLE_ADAPTER_DIR,
    max_steps: int = 60,
) -> Dict[str, Any]:
    """Trenuje QLoRA adapter dla Synapsy na RTX 3060 12 GB (uruchamiane z Synapsa/venv)."""
    _setup_windows_triton_mock()
    _install_lazy_safetensors_loader()
    import torch
    from datasets import load_dataset
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    if not dataset_path.exists():
        raise FileNotFoundError(f"Brak zbioru treningowego: {dataset_path}")

    torch.cuda.empty_cache()
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        local_files_only=True,
    )
    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, peft_config)

    ds = load_dataset("json", data_files=str(dataset_path), split="train")

    def _tok_fn(ex):
        txt = f"### Instruction:\n{ex['instruction']}\n\n### Response:\n{ex['output']}<|endoftext|>"
        tok = tokenizer(txt, truncation=True, max_length=640, padding="max_length")
        tok["labels"] = tok["input_ids"].copy()
        return tok

    tok_ds = ds.map(_tok_fn, remove_columns=ds.column_names)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    tmp_ckpt_dir = out_path / "_checkpoints"

    trainer = Trainer(
        model=model,
        train_dataset=tok_ds,
        args=TrainingArguments(
            output_dir=str(tmp_ckpt_dir),
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            optim="paged_adamw_8bit",
            warmup_steps=8,
            max_steps=max_steps,
            learning_rate=2e-4,
            fp16=True,
            logging_steps=10,
            save_strategy="no",
            report_to="none",
            dataloader_num_workers=0,
        ),
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
    )

    train_res = trainer.train()
    model.save_pretrained(str(out_path))
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
        "max_steps": max_steps,
        "train_loss": round(float(train_res.training_loss), 4),
        "runtime_s": round(float((train_res.metrics or {}).get("train_runtime", 0.0)), 2),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_path / "training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if tmp_ckpt_dir.exists():
        import shutil
        shutil.rmtree(tmp_ckpt_dir, ignore_errors=True)
    print("SYNAPSA_TRAIN_METRICS:", json.dumps(metrics))
    return metrics


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
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--no-yt-mine", action="store_true")
    args = ap.parse_args()

    if args.sync_memory:
        from lol_agent.synapsa_conversation_learner import sync_engineering_memory
        print("ENGINEERING_MEMORY:", json.dumps(sync_engineering_memory(include_transcripts=True), ensure_ascii=False))
    if args.build_dataset or not DATASET_PATH.exists():
        info = build_training_dataset(mine_youtube=not args.no_yt_mine)
        print("DATASET_BUILT:", json.dumps(info, ensure_ascii=False))
    if args.train:
        train_title_lora(max_steps=args.steps)
