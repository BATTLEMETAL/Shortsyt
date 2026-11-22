"""
LOL Agent — Synapsa Local AI Engine (Qwen2.5-7B-4bit + LoRA na RTX 3060)
=========================================================================
Przejmuje zadania generatywne z płatnych/limitowanych API chmurowych (Gemini):
  - generowanie 5 kandydatów tytułów + selekcja #1 i #2 wg wag learning_directive.json
  - generowanie komentarza przypiętego ściśle z telemetrii klipu (zero spelli bez potwierdzenia HUD)
  - generowanie opisów TikTok / Instagram / Facebook oraz metadanych Multi-Account
  - generowanie 2 propozycji odpowiedzi na komentarze widzów (tryb 1-klik w UI)
"""
from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SYNAPSA_PROC_LOCK = threading.Lock()

SYNAPSA_PYTHON = os.environ.get(
    "SYNAPSA_PYTHON",
    r"C:\Users\mz100\PycharmProjects\Synapsa\venv\Scripts\python.exe",
)
SYNAPSA_ROOT = os.environ.get(
    "SYNAPSA_ROOT",
    r"C:\Users\mz100\PycharmProjects\Synapsa",
)
BASE_MODEL_NAME = os.environ.get(
    "SYNAPSA_BASE_MODEL",
    "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit",
)
TITLE_ADAPTER_DIR = os.environ.get(
    "SYNAPSA_TITLE_ADAPTER",
    str(Path(SYNAPSA_ROOT) / "adapters_shortsyt_titles"),
)

_JSON_START = "<<<SYNAPSA_JSON_START>>>"
_JSON_END = "<<<SYNAPSA_JSON_END>>>"

_BANNED_TITLE_PHRASES = (
    "bad idea", "hunting grounds", "massacre", "reset machine", "mistake", "regret",
    "rate 1-10", "rate this", "1 to 10", "part #", "road to",
)
_SPELL_TERMS = ("flash", "flashed", "ignite", "exhaust", "zhonya", "teleport", "tower dive", "dived")
_RANK_PREFIX_RE = re.compile(r"^(master|diamond|challenger|grandmaster|emerald|platinum|gold|silver|bronze)\s+", re.I)


def _load_camera_shunpo_rule() -> Dict[str, Any]:
    """Ładuje regułę kamery Katariny (Shunpo E -> sztylet/wróg + centrowanie) z engine_rules.json."""
    fallback: Dict[str, Any] = {
        "champion": "Katarina",
        "motion_rule": "smooth_pan_or_instant_shunpo_snap",
        "max_smooth_step_px": 80.0,
        "valid_jump_targets": ["katarina_passive_dagger", "enemy_champion_hp_bar"],
        "post_snap_behavior": "center_on_katarina",
        "post_snap_center_lock_frames": 2,
    }
    try:
        rp = Path(__file__).resolve().parent / "engine_rules.json"
        if rp.exists():
            raw = json.loads(rp.read_text(encoding="utf-8"))
            pol = raw.get("camera_shunpo_policy")
            if isinstance(pol, dict) and pol:
                merged = dict(fallback)
                merged.update(pol)
                return merged
    except Exception:
        pass
    return fallback


KATARINA_SHUNPO_CAMERA_RULE: Dict[str, Any] = _load_camera_shunpo_rule()


# ── Scoring i Selekcja Kandydatów (działa błyskawicznie lokalnie w venv313) ──

def _classify_structure_local(title: str) -> str:
    t_up = (title or "").upper()
    if any(k in t_up for k in ("SOLO BOLO", "1V1", "DISRESPECT", "SCHOOLED", "DUEL", "EGO CHECK")):
        return "DISRESPECT_1V1"
    if any(k in t_up for k in ("1% HP", "1 HP", "1% ", "SURVIVING ON", "MIRACLE", "TURNAROUND")):
        return "CLUTCH_1HP"
    if any(k in t_up for k in ("THEY THOUGHT", "THEY TRIED", "THEY GROUPED", "WALKING UP", "GREEDY")):
        return "EGO_CHECK"
    if any(k in t_up for k in ("PENTAKILL", "FIVE KILLS", "RAMPAGE", "ENTIRE TEAM", "VANISH", "IN 2 SEC", "SECONDS")):
        return "RAMPAGE"
    if "?" in title or any(t_up.startswith(k) for k in ("DID YOU", "HOW DID", "WHY ", "CAN YOU")):
        return "QUESTION"
    return "CLEAN_OUTPLAY"


def _strip_tags_clean(title: str) -> str:
    return re.sub(r"#\S+", "", title or "").strip()


def score_title_candidate(
    title: str,
    action_type: str = "outplay",
    extra_context: Optional[Dict[str, Any]] = None,
    directive: Optional[Dict[str, Any]] = None,
    recent_titles: Optional[List[str]] = None,
) -> float:
    """
    Ocenia pojedynczego kandydata tytułu (wyższy wynik = lepsze dopasowanie do kanału i faktów).
    """
    if not title or not isinstance(title, str):
        return -999.0

    ctx = extra_context or {}
    dir_data = directive or {}
    body = _strip_tags_clean(title)
    if len(body) < 8:
        return -500.0

    score = 50.0
    low = body.lower()

    # 1. Twarda blokada halucynacji, zakazanych fraz, sprzecznych tierów i bełkotu
    if any(bp in low for bp in _BANNED_TITLE_PHRASES):
        score -= 100.0
    if _RANK_PREFIX_RE.match(body):
        score -= 100.0

    act_low = (action_type or "").lower()
    if "quadra" in act_low and re.search(r"\b(triple|penta|pentakill|double)\b", low):
        score -= 120.0
    elif "penta" in act_low and re.search(r"\b(quadra|quadrakill|triple|double)\b", low):
        score -= 120.0
    elif "triple" in act_low and re.search(r"\b(quadra|quadrakill|penta|pentakill|double)\b", low):
        score -= 120.0
    elif "double" in act_low and re.search(r"\b(triple|quadra|quadrakill|penta|pentakill)\b", low):
        score -= 120.0

    if any(em in body for em in ("🧵", "🧶", "🪴", "🧺", "🪡", "🧷")) or "damage away" in low:
        score -= 80.0

    hud_spells = ctx.get("hud_spells_used") or {}
    spells_ok = bool(hud_spells.get("verified")) and any(hud_spells.get(k) for k in ("d_used", "f_used", "r_used"))
    if not spells_ok and any(sp in low for sp in _SPELL_TERMS):
        score -= 100.0

    _mz = ctx.get("map_zone")
    z_label = (
        (_mz.get("zone_label") or _mz.get("zone") or "")
        if isinstance(_mz, dict)
        else str(_mz or "")
    ).lower()
    if "baron" in low and "baron" not in z_label and "baron" not in (action_type or "").lower():
        score -= 80.0
    if "dragon" in low and "dragon" not in z_label and "dragon" not in (action_type or "").lower():
        score -= 80.0

    # 2. Dopasowanie do zwycięskich struktur i statystyk konwersji z learning_directive.json
    st = _classify_structure_local(body)
    st_stats = (dir_data.get("title_structure_stats") or {}).get(st) or {}
    ratio_w = float(st_stats.get("median_ratio_within_action") or st_stats.get("avg_ratio") or 1.0)
    conv_1k = float(st_stats.get("avg_conversion_per_1k") or 0.0)
    score += (ratio_w - 1.0) * 28.0 + min(12.0, conv_1k * 0.4)
    if st == "QUESTION":
        score -= 14.0  # w danych kanału QUESTION ma ratio 0.67

    # 3. Słowa CTR i unikane (granice słów: 'KATA' nie karze 'KATARINA')
    low_words_clean = re.sub(r"[^\w\s]", " ", low)
    for kw in (dir_data.get("winning_keywords") or [])[:10]:
        if kw and re.search(rf"\b{re.escape(str(kw).lower())}\b", low_words_clean):
            score += 4.5
    for ak in (dir_data.get("avoid_keywords") or [])[:10]:
        if ak and re.search(rf"\b{re.escape(str(ak).lower())}\b", low_words_clean):
            score -= 12.0

    # 4. Zgodność z telemetrią ekranu
    low_hp = bool(ctx.get("low_hp_survival"))
    kill_span = float(ctx.get("kill_span_s") or 0.0)
    if low_hp and any(k in low for k in ("1 hp", "1% hp", "surviv", "sliver", "clutch")):
        score += 18.0
    elif (not low_hp) and any(k in low for k in ("1 hp", "1% hp")):
        score -= 40.0  # nie kłam o 1 HP jeśli HP nie spadło

    if 0.3 <= kill_span <= 3.0 and any(k in low for k in ("second", "instant", "vanish", "blink")):
        score += 14.0

    # 5. Długość idealna dla YouTube Shorts (24-52 znaki przed hashtagami)
    if 22 <= len(body) <= 52:
        score += 10.0
    elif len(body) > 65:
        score -= 12.0

    # 6. Kara za powtarzanie 2 pierwszych słów z ostatnich filmów kanału
    words = re.sub(r"[^\w\s]", "", low).split()
    if len(words) >= 2 and recent_titles:
        op2 = " ".join(words[:2])
        recent_op2 = {
            " ".join(re.sub(r"[^\w\s]", "", _strip_tags_clean(rt).lower()).split()[:2])
            for rt in recent_titles[-20:]
        }
        if op2 in recent_op2:
            score -= 60.0

    return round(score, 2)


def score_and_select_best_titles(
    candidates: List[str],
    action_type: str = "outplay",
    extra_context: Optional[Dict[str, Any]] = None,
    directive: Optional[Dict[str, Any]] = None,
    recent_titles: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """Wybiera najlepszy wariant A (#1) i odmienny wariant B (#2) spośród kandydatów."""
    deduped: List[str] = []
    seen = set()
    for c in (candidates or []):
        s = str(c or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            deduped.append(s)

    if not deduped:
        return "", ""

    ranked = sorted(
        deduped,
        key=lambda t: score_title_candidate(t, action_type, extra_context, directive, recent_titles),
        reverse=True,
    )
    best_a = ranked[0]
    best_b = ranked[1] if len(ranked) > 1 else ranked[0]
    return best_a, best_b


# ── Wywołanie Lokalnego GPU RTX 3060 (VRAM Guard + Subproces Synapsy) ────────

def check_vram_available(min_gb: float = 4.2) -> bool:
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if res.returncode == 0:
            free_mb = int(res.stdout.strip().splitlines()[0].strip())
            return (free_mb / 1024.0) >= min_gb
    except Exception:
        pass
    return False


def is_synapsa_available() -> bool:
    if os.environ.get("SYNAPSA_DISABLE") == "1":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("SYNAPSA_TEST_FORCE") != "1":
        return False
    return Path(SYNAPSA_PYTHON).is_file() and check_vram_available(min_gb=4.2)


def build_synapsa_instruction(task_type: str, payload: Dict[str, Any]) -> str:
    """Buduje spójny prompt tekstowy dla workera Synapsy i dla trenera LoRA."""
    compact = json.dumps(payload, ensure_ascii=False)
    if task_type == "lol_metadata":
        return (
            "Generate YouTube Shorts metadata in ENGLISH ONLY as strict JSON. "
            "RULES: Use ONLY facts from telemetry; DO NOT invent Flash/Ignite/Exhaust/Tower Dive/Baron; "
            "DO NOT use 'Master' prefix, 'Part #', 'Rate 1-10', 'Bad Idea', 'Regret', or facebook links.\n"
            f"TELEMETRY: {compact}\n"
            'Return JSON with keys: "title_candidates" (5 short punchy hooks <=48 chars without hashtags), '
            '"hook_text" (2-5 punchy ALL CAPS words tied to clip telemetry e.g. "DRAGON STEAL + QUADRA" or "3 KILLS IN 4.2S", NEVER generic "INSANE OUTPLAY!"), '
            '"description" (2 concise English sentences), '
            '"pinned_comment" (1 debate question grounded in telemetry), "tags" (list of 6 lowercase keywords).'
        )
    if task_type == "account_metadata":
        return (
            "Generate short-form video metadata strictly matching the brand guidelines as JSON.\n"
            f"ACCOUNT_AND_CLIP: {compact}\n"
            'Return JSON with keys: "title_candidates" (3 titles <=55 chars), "title_variant_b", '
            '"hook_text" (3-4 ALL CAPS words), "description" (2-3 concrete sentences + CTA), '
            '"pinned_comment" (debate/action question), "tags" (5 lowercase keywords).'
        )
    if task_type == "social_caption":
        return (
            "Write a short platform caption (no quotes, no invented spells) as JSON.\n"
            f"REQUEST: {compact}\n"
            'Return JSON: {"caption": "text"}'
        )
    if task_type == "comment_reply":
        return (
            "Write 2 short, authentic gaming replies (<=12 words each) to a viewer comment based strictly on the clip recipe.\n"
            f"COMMENT_CONTEXT: {compact}\n"
            'Return JSON: {"replies": ["calm/appreciative reply", "playful gamer banter"]}'
        )
    if task_type == "montage_director":
        return (
            "Choose ONE discrete montage strategy from "
            "[KEEP_FULL_CONTINUOUS, DROP_ISOLATED_FIRST_KILL, DROP_ISOLATED_LAST_KILL, BRIDGE_GAP_SPEED_RAMP, SWITCH_STYLE_IN_MEDIA_RES] "
            "and tuning parameters strictly within PARAM_EFFECT_CONTRACT bounds based on OpenCV clip telemetry and 48h Action->Effect history. "
            "Honor camera_policy (smooth pan <=80px or instant snap on Katarina E Shunpo to passive dagger/enemy, then center on Katarina) and high_retention_benchmarks.\n"
            f"DIRECTOR_TELEMETRY: {compact}\n"
            'Return JSON: {"operation": "...", "style": "PRIMARY|SPEED_RAMP_FLOW|IN_MEDIA_RES", '
            '"buildup_sec": 0.7, "outro_sec": 1.4, "zoom_aggression": 1.2, "slowmo_duration": 1.0, '
            '"camera_mode": "tight_player|duel_centroid", "drop_anchor": "first_kill_engage|climax_final_kill", "rationale": "1 sentence"}'
        )
    if task_type == "engineering_cause_effect":
        return (
            "Analyze verified engineering or montage attribute changes (Before -> After) strictly from telemetry/facts as JSON.\n"
            f"CAUSE_EFFECT_EVIDENCE: {compact}\n"
            'Return JSON: {"verdict": "IMPROVED|REGRESSED|MIXED|NEUTRAL", '
            '"affected_metrics": {}, "causal_rule": "1 concise cause->effect sentence", '
            '"recommended_action": "KEEP_CHANGE|REVERT_OR_TIGHTEN|KEEP_SAFE_GUARD"}'
        )
    if task_type == "predict_change_effect":
        return (
            "Deduce BEFORE rendering how proposed_changes will alter video watchability metrics (Sykofankcja 0: predict WORSE if risky or NO_CHANGE if cosmetic).\n"
            f"CHANGE_PROPOSAL: {compact}\n"
            'Return JSON: {"expected_verdict": "BETTER|WORSE|NO_CHANGE|MIXED", '
            '"expected_metric_shifts": {}, "risks": ["1 short risk"], '
            '"deduction_rationale": "1 strict causal sentence"}'
        )
    if task_type == "watchability_compare":
        return (
            "Compare inspected Before vs After shorts strictly from measured visual/audio deltas (Sykofankcja 0: report NO_CHANGE if unchanged, WORSE on regression).\n"
            f"WATCHABILITY_DIFF: {compact}\n"
            'Return JSON: {"verdict": "BETTER|WORSE|NO_CHANGE|MIXED", "actually_changed": true, '
            '"hypothesis_status": "CONFIRMED|PARTIAL|NO_EFFECT|REFUTED", '
            '"watchability_summary": "1-2 factual sentences", "next_fix": "concrete action or none"}'
        )
    if task_type == "overnight_rank":
        return (
            "Rank the rendered overnight shorts strictly from metrics (Sykofankcja 0: NEVER praise or pick a short with black_end_frame=true, "
            "frame0_hook_legible=false, audio_clip_gt_096>10, or watchability_score<65 over a clean higher-scoring short. "
            "If champion_mismatch=true e.g. Yone vs channel Katarina, player_visible_ratio<0.75, or first_kill_out_sec>4.5, "
            "explicitly note it in Polish and prefer a clean channel-champion clip when scores are close).\n"
            f"OVERNIGHT_CANDIDATES: {compact}\n"
            'Return strict JSON ONLY: {"winner_id": "1", "summary_pl": "2 factual Polish sentences mentioning champion and scores", '
            '"notes_pl": {"1": "concise Polish note with score", "2": "concise Polish note", "3": "concise Polish note", "4": "concise Polish note", "5": "concise Polish note"}}'
        )
    return f"TASK={task_type} DATA={compact}\nReturn strict JSON."


PARAM_EFFECT_CONTRACT: Dict[str, Dict[str, Any]] = {
    "buildup_sec": {
        "range": [0.4, 2.2],
        "effect": "Większa wartość wydłuża wejście przed 1. killem (rośnie first_kill_out_sec; mała <0.8s przyspiesza hook).",
    },
    "outro_sec": {
        "range": [0.8, 2.0],
        "effect": "Czas po ostatnim ciosie na wybrzmienie banera/CTA; >1.8s zwiększa ryzyko OVERESTIMATED_PACING i swipu.",
    },
    "zoom_aggression": {
        "range": [1.10, 1.28],
        "effect": "Siła zoom-puncha na cios; za duży zoom w gęstym teamfighcie zwiększa camera_peak_step_px.",
    },
    "slowmo_duration": {
        "range": [0.6, 1.8],
        "effect": "Długość zwolnienia na decydujący cios; w 1v1 podbija AVD%, w szybkim multi-killu spowalnia tempo.",
    },
    "camera_mode": {
        "allowed": ["tight_player", "duel_centroid"],
        "effect": "tight_player trzyma bohatera w chaotycznym teamfighcie; duel_centroid kadruje obu walczących w 1v1.",
    },
    "drop_anchor": {
        "allowed": ["first_kill_engage", "climax_final_kill"],
        "effect": "first_kill_engage wrzuca główny drop bitu już na 1. kill/engage przy dłuższych multikillach; climax_final_kill zostawia drop na finale (1v1/clutch).",
    },
}


def _clamp_contract_float(val: Any, low: float, high: float, default: float) -> float:
    try:
        num = float(val)
        return round(max(low, min(high, num)), 2)
    except Exception:
        return round(max(low, min(high, default)), 2)


DIRECTOR_OPERATIONS: Dict[str, Dict[str, str]] = {
    "KEEP_FULL_CONTINUOUS": {
        "style": "PRIMARY",
        "effect": "Zachowuje pełne ciągłe okno akcji (c_start - 0.8s .. final_kill + outro) bez ucinania fragów.",
    },
    "DROP_ISOLATED_FIRST_KILL": {
        "style": "PRIMARY",
        "effect": "Ucina izolowanego 1. fraga oddalonego >6s bez walki, poprawiając hook_latency_s.",
    },
    "DROP_ISOLATED_LAST_KILL": {
        "style": "PRIMARY",
        "effect": "Ucina izolowanego ostatniego fraga po martwym pościgu >6s bez walki, chroniąc outro.",
    },
    "BRIDGE_GAP_SPEED_RAMP": {
        "style": "SPEED_RAMP_FLOW",
        "effect": "Zachowuje wszystkie fragi i przyspiesza martwy bieg w środku klipu przez speed-ramp.",
    },
    "SWITCH_STYLE_IN_MEDIA_RES": {
        "style": "IN_MEDIA_RES",
        "effect": "Ustawia pierwszego killa w ~2.5s (IN_MEDIA_RES) przy niskim historycznym RWI dla danego typu akcji.",
    },
}


def decide_montage_with_synapsa(
    telemetry: Dict[str, Any],
    directive: Optional[Dict[str, Any]] = None,
    use_local_ai: bool = True,
) -> Dict[str, Any]:
    """
    Hybrydowy selektor strategii reżysera: wybiera 1 z 5 dyskretnych operacji montażowych
    oraz bezpieczne parametry wykonawcze z PARAM_EFFECT_CONTRACT na bazie telemetrii OpenCV,
    historii Bramki 48h i (gdy dostępne GPU) lokalnego modelu Synapsa.
    """
    t_data = telemetry or {}
    dir_data = directive or {}
    act = str(t_data.get("action_type") or "outplay").lower().strip()
    kills_raw = t_data.get("kills") or t_data.get("peaks") or []
    ts_list: List[float] = []
    for k in kills_raw:
        if isinstance(k, dict):
            ts_list.append(float(k.get("timestamp", 0.0)))
        elif isinstance(k, (list, tuple)) and k:
            ts_list.append(float(k[0]))
    ts_list.sort()
    gaps = t_data.get("gaps")
    if gaps is None:
        gaps = [round(max(0.0, b - a), 2) for a, b in zip(ts_list, ts_list[1:])]

    objective_secured = bool(t_data.get("objective_secured"))
    ally_banner_blocked = bool(t_data.get("ally_banner_blocked"))
    gap_has_combat = bool(t_data.get("gap_has_combat"))

    p48 = (dir_data.get("post_48h_gate_summary") or {}) if isinstance(dir_data, dict) else {}
    act_stats = ((p48.get("by_action_type") or {}).get(act)) or {}
    hist_avg_rwi = float(act_stats.get("avg_rwi", 72.0)) if act_stats else 72.0
    adj_48 = ((p48.get("director_adjustments_by_action") or {}).get(act)) or {}
    op_stats_48h = (p48.get("by_director_operation") or {}) if isinstance(p48, dict) else {}

    recent_ce: List[Dict[str, Any]] = []
    high_ret_ctx: Dict[str, Any] = {}
    try:
        try:
            from lol_agent.synapsa_conversation_learner import (
                get_cause_effect_context_for_director,
                get_high_retention_context_for_director,
            )
        except ImportError:
            from synapsa_conversation_learner import (
                get_cause_effect_context_for_director,
                get_high_retention_context_for_director,
            )
        recent_ce = get_cause_effect_context_for_director(action_type=act, limit=3)
        high_ret_ctx = get_high_retention_context_for_director(action_type=act)
    except Exception:
        recent_ce = []
        high_ret_ctx = {}

    champ_raw = str(t_data.get("champion") or "").strip()
    if "katarina" in champ_raw.lower():
        cam_policy: Dict[str, Any] = {
            "champion": "Katarina",
            "rule": KATARINA_SHUNPO_CAMERA_RULE.get("motion_rule", "smooth_pan_or_instant_shunpo_snap"),
            "max_smooth_step_px": float(KATARINA_SHUNPO_CAMERA_RULE.get("max_smooth_step_px", 80.0)),
            "shunpo_e_targets": list(
                KATARINA_SHUNPO_CAMERA_RULE.get("valid_jump_targets", ["katarina_passive_dagger", "enemy_champion_hp_bar"])
            ),
            "post_shunpo_action": KATARINA_SHUNPO_CAMERA_RULE.get("post_snap_behavior", "center_on_katarina"),
        }
    else:
        cam_policy = {
            "champion": champ_raw or "generic",
            "rule": "smooth_pan_with_confirmed_target_snap",
            "max_smooth_step_px": float(KATARINA_SHUNPO_CAMERA_RULE.get("max_smooth_step_px", 80.0)),
            "post_shunpo_action": "center_on_player",
        }

    first_kill_lead_s = round(float(ts_list[0]), 2) if ts_list else 0.0
    dead_intro_detected = bool(t_data.get("dead_intro_detected"))

    payload = {
        "action_type": act,
        "champion": t_data.get("champion", ""),
        "duration": round(float(t_data.get("duration") or 0.0), 2),
        "first_kill_lead_s": first_kill_lead_s,
        "dead_intro_detected": dead_intro_detected,
        "kill_timestamps": ts_list,
        "gaps": gaps,
        "gap_has_combat": gap_has_combat,
        "objective_secured": objective_secured,
        "ally_banner_blocked": ally_banner_blocked,
        "min_hp_pct": t_data.get("min_hp_pct"),
        "historical_avg_rwi": hist_avg_rwi,
        "director_operation_stats": op_stats_48h,
        "param_ranges": {k: (v.get("range") or v.get("allowed")) for k, v in PARAM_EFFECT_CONTRACT.items()},
        "camera_policy": cam_policy,
    }
    if high_ret_ctx:
        payload["high_retention_benchmarks"] = high_ret_ctx
    if recent_ce:
        payload["verified_cause_effect_lessons"] = recent_ce

    ai_res = generate_with_synapsa("montage_director", payload, timeout=120) if (use_local_ai and is_synapsa_available()) else None
    ai_op = str((ai_res or {}).get("operation") or "").strip().upper()
    ai_rationale = str((ai_res or {}).get("rationale") or "").strip()

    # Twarda weryfikacja kontraktu przyczynowo-skutkowego (zero błędnych ucięć teamfightów)
    if objective_secured or ally_banner_blocked or gap_has_combat:
        op = "KEEP_FULL_CONTINUOUS"
        rationale = "Wielofazowa akcja z epickim obiektem / zablokowanym banerem / walką w przerwie — zachowano pełne ciągłe okno."
    elif len(gaps) >= 2 and gaps[0] > 6.0 and not gap_has_combat and max(gaps[1:]) <= 4.0:
        op = "DROP_ISOLATED_FIRST_KILL"
        rationale = f"Izolowany 1. frag oddalony o {gaps[0]:.1f}s bez walki przed głównym klastrem — ucięcie poprawia hook."
    elif len(gaps) >= 2 and gaps[-1] > 6.0 and not gap_has_combat and max(gaps[:-1]) <= 4.0:
        op = "DROP_ISOLATED_LAST_KILL"
        rationale = f"Izolowany ostatni frag po {gaps[-1]:.1f}s bez walki — ucięcie skraca martwe outro."
    elif dead_intro_detected and first_kill_lead_s > 4.5 and not objective_secured:
        op = "SWITCH_STYLE_IN_MEDIA_RES"
        rationale = f"Martwe intro przed 1. killem ({first_kill_lead_s:.1f}s > 4.5s) — przełączono na szybkie wejście IN_MEDIA_RES."
    elif (float(t_data.get("duration") or 0.0) > 18.0 and gaps and any(g > 3.8 for g in gaps) and not gap_has_combat and not objective_secured) or (gaps and any(g > 4.2 for g in gaps) and not gap_has_combat):
        op = "BRIDGE_GAP_SPEED_RAMP"
        rationale = f"Przerwa między fragami ({max(gaps):.1f}s) przy braku pustego izolatu — zastosowano przyspieszenie speed-ramp dla retencji 14-17s."
    elif ai_op in DIRECTOR_OPERATIONS:
        op = ai_op
        rationale = ai_rationale or DIRECTOR_OPERATIONS[op]["effect"]
    elif hist_avg_rwi < 68.0 and act not in ("pentakill", "quadrakill"):
        op = "SWITCH_STYLE_IN_MEDIA_RES"
        rationale = f"Historyczne RWI dla {act} wynosi {hist_avg_rwi:.1f} (<68) — przełączono na szybsze wejście IN_MEDIA_RES."
    else:
        op = "KEEP_FULL_CONTINUOUS"
        rationale = "Zwarty układ fragów — utrzymano ciągły montaż PRIMARY."

    style = DIRECTOR_OPERATIONS[op]["style"]

    # Bazowe parametry wg klasy akcji i operacji (zgodne z PARAM_EFFECT_CONTRACT)
    is_solo = act in ("solo_bolo", "solo", "1v1", "duel", "disrespect", "ego_check")
    is_multi = act in ("triple", "quadrakill", "pentakill", "quadra", "penta") or objective_secured or ally_banner_blocked
    if is_solo:
        base_b, base_o, base_z, base_s, base_cam = 1.3, 1.6, 1.18, 1.4, "duel_centroid"
    elif op == "SWITCH_STYLE_IN_MEDIA_RES":
        base_b, base_o, base_z, base_s, base_cam = 0.4, 1.2, 1.22, 1.0, "tight_player"
    elif is_multi:
        base_b, base_o, base_z, base_s, base_cam = 0.7, 1.4, 1.20, 0.9, "tight_player"
    else:
        base_b, base_o, base_z, base_s, base_cam = 0.9, 1.5, 1.20, 1.2, "tight_player"

    # Uwzględnij propozycję suwaków z AI tylko jeśli nie łamie twardych reguł
    ai_dict = ai_res if isinstance(ai_res, dict) else {}
    b_val = _clamp_contract_float(ai_dict.get("buildup_sec", base_b), 0.4, 2.2, base_b) if ai_dict else base_b
    o_val = _clamp_contract_float(ai_dict.get("outro_sec", base_o), 0.8, 2.0, base_o) if ai_dict else base_o
    z_val = _clamp_contract_float(ai_dict.get("zoom_aggression", base_z), 1.10, 1.28, base_z) if ai_dict else base_z
    s_val = _clamp_contract_float(ai_dict.get("slowmo_duration", base_s), 0.6, 1.8, base_s) if ai_dict else base_s
    ai_cam = str(ai_dict.get("camera_mode") or "").strip().lower()
    cam_val = ai_cam if ai_cam in ("tight_player", "duel_centroid") else base_cam
    if is_multi and not is_solo:
        cam_val = "tight_player"
        if objective_secured or ally_banner_blocked:
            b_val = min(b_val, 0.8)

    default_drop_anchor = (
        "first_kill_engage"
        if (len(ts_list) >= 2 and not is_solo and 0.8 <= ts_list[0] <= 7.0 and ts_list[-1] > 8.5)
        else "climax_final_kill"
    )
    ai_anchor = str(ai_dict.get("drop_anchor") or "").strip().lower()
    drop_anchor = ai_anchor if ai_anchor in ("first_kill_engage", "climax_final_kill") else default_drop_anchor
    if is_solo or len(ts_list) < 2:
        drop_anchor = "climax_final_kill"

    # Korekty z Bramki 48h (jeśli nie kolidują z ochroną wielofazowego obiektu)
    if isinstance(adj_48, dict) and not objective_secured:
        if adj_48.get("buildup_sec_delta"):
            b_val = _clamp_contract_float(b_val + float(adj_48["buildup_sec_delta"]), 0.4, 2.2, b_val)
        if adj_48.get("outro_sec_delta"):
            o_val = _clamp_contract_float(o_val + float(adj_48["outro_sec_delta"]), 0.8, 2.0, o_val)

    return {
        "operation": op,
        "style": style,
        "buildup_sec": b_val,
        "outro_sec": o_val,
        "zoom_aggression": z_val,
        "slowmo_duration": s_val,
        "camera_mode": cam_val,
        "drop_anchor": drop_anchor,
        "camera_policy": cam_policy,
        "high_retention_benchmarks": high_ret_ctx,
        "param_contracts_applied": True,
        "expected_effect": DIRECTOR_OPERATIONS[op]["effect"],
        "rationale": rationale,
        "historical_avg_rwi": hist_avg_rwi,
        "director_operation_stats": op_stats_48h,
        "source": "synapsa_local_lora_director" if ai_res else "synapsa_hybrid_director",
    }


def generate_with_synapsa(
    task_type: str,
    payload: Dict[str, Any],
    timeout: int = 120,
) -> Optional[Dict[str, Any]]:
    """
    Wywołuje lokalny model Synapsy (Qwen2.5-7B-4bit + adapter LoRA) w izolowanym
    środowisku Pythona (`Synapsa/venv`) i zwraca sparsowany obiekt JSON lub None.
    """
    if not is_synapsa_available():
        return None

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump({"task_type": task_type, "payload": payload}, tf, ensure_ascii=False)
        req_path = tf.name

    try:
        run_env = os.environ.copy()
        run_env["PYTHONIOENCODING"] = "utf-8"
        run_env["WBITS_USE_TRITON"] = "0"
        run_env["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
        run_env["TORCH_CUDA_ARCH_LIST"] = "8.6"
        with _SYNAPSA_PROC_LOCK:
            res = subprocess.run(
                [SYNAPSA_PYTHON, str(Path(__file__).resolve()), "--worker", "--task", task_type, "--input-file", req_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=run_env,
                timeout=timeout,
            )
        stdout = res.stdout or ""
        if _JSON_START in stdout and _JSON_END in stdout:
            raw_block = stdout.split(_JSON_START, 1)[1].split(_JSON_END, 1)[0].strip()
            parsed = json.loads(raw_block)
            if isinstance(parsed, dict) and not parsed.get("_worker_error"):
                return parsed
    except Exception:
        pass
    finally:
        try:
            os.remove(req_path)
        except OSError:
            pass
    return None


# ── Worker uruchamiany wewnątrz środowiska Synapsy (torch + peft + bitsandbytes) ─

def _setup_windows_triton_mock() -> None:
    os.environ["WBITS_USE_TRITON"] = "0"
    os.environ["XFORMERS_FORCE_DISABLE_TRITON"] = "1"
    os.environ["TORCH_CUDA_ARCH_LIST"] = "8.6"
    warnings.filterwarnings("ignore")
    try:
        import triton  # noqa: F401
        if hasattr(triton, "language"):
            return
    except ImportError:
        pass
    dummy_code = (
        "class _M:\n"
        "    def __getattr__(self, _k): return self\n"
        "    def __call__(self, *a, **kw): return self\n"
        "_m = _M()\n"
        "class language:\n"
        "    class dtype:\n"
        "        pass\n"
        "class compiler:\n"
        "    pass\n"
        "def cdiv(x, y): return (x + y - 1) // y\n"
        "def next_power_of_2(n): return 1\n"
        "def autotune(*a, **kw): return lambda fn: fn\n"
        "def jit(*a, **kw): return lambda fn: fn\n"
        "Config = _m\n"
        "compile = _m\n"
    )
    tmp_mod = Path(tempfile.gettempdir()) / "triton_synapsa_worker_mock.py"
    tmp_mod.write_text(dummy_code, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("triton", str(tmp_mod))
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["triton"] = mod
        spec.loader.exec_module(mod)


def _extract_first_json_object(raw_text: str) -> Dict[str, Any]:
    txt = (raw_text or "").strip()
    if "```json" in txt:
        txt = txt.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in txt:
        txt = txt.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    start = txt.find("{")
    end = txt.rfind("}")
    if start != -1 and end > start:
        candidate = re.sub(r",\s*([}\]])", r"\1", txt[start:end + 1])
        return json.loads(candidate)
    raise ValueError("Brak poprawnego JSON w odpowiedzi modelu Synapsa")


def _install_lazy_safetensors_loader() -> None:
    """Zastępuje mmap-owy safe_load_file w transformers leniwym odczytem pojedynczych tensorów (chroni przed Windows Commit Limit / access violation przy 16 GB RAM)."""
    import inspect
    import struct
    import torch
    import transformers.modeling_utils as mu

    dtypes = {
        "F16": torch.float16,
        "BF16": torch.bfloat16,
        "F32": torch.float32,
        "U8": torch.uint8,
        "I8": torch.int8,
        "I32": torch.int32,
        "I64": torch.int64,
        "BOOL": torch.bool,
    }

    created_sds = []

    class _LazySD(dict):
        def __init__(self, path: str):
            super().__init__()
            self._path = path
            self._fp = open(path, "rb", buffering=8 * 1024 * 1024)
            hlen = struct.unpack("<Q", self._fp.read(8))[0]
            hdr = json.loads(self._fp.read(hlen).decode("utf-8"))
            self._base = 8 + hlen
            self._meta = dict(
                sorted(
                    ((k, v) for k, v in hdr.items() if k != "__metadata__"),
                    key=lambda kv: kv[1]["data_offsets"][0],
                )
            )
            self._small = {}
            for k, m in self._meta.items():
                super().__setitem__(k, None)
                s, e = m["data_offsets"]
                if (e - s) <= 2_000_000:
                    self._small[k] = self._read_tensor(m)
            created_sds.append(self)

        def _read_tensor(self, m: dict):
            s, e = m["data_offsets"]
            self._fp.seek(self._base + s)
            raw = bytearray(self._fp.read(e - s))
            return torch.frombuffer(raw, dtype=dtypes[m["dtype"]]).reshape(m["shape"])

        def __getitem__(self, k: str):
            if k in self._small:
                return self._small[k]
            return self._read_tensor(self._meta[k])

        def get(self, k: str, default=None):
            return self[k] if k in self._meta else default

        def items(self):
            frame = inspect.currentframe()
            caller = frame.f_back.f_code.co_name if frame and frame.f_back else ""
            del frame
            if caller == "create_quantized_param":
                yield from self._small.items()
                return
            for k in self._meta:
                yield k, self[k]

        def values(self):
            for k in self._meta:
                yield self[k]

        def close_and_clear(self) -> None:
            self._small.clear()
            try:
                if getattr(self, "_fp", None) is not None and not self._fp.closed:
                    self._fp.close()
            except Exception:
                pass

        def __del__(self):
            self.close_and_clear()

    mu._lazy_sds = created_sds
    mu.safe_load_file = lambda path, *a, **kw: _LazySD(path)


def _run_worker(task_type: str, input_file: str) -> None:
    _setup_windows_triton_mock()
    _install_lazy_safetensors_loader()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel

    req = json.loads(Path(input_file).read_text(encoding="utf-8"))
    payload = req.get("payload") or {}
    instruction = build_synapsa_instruction(task_type, payload)

    adapter_cfg = Path(TITLE_ADAPTER_DIR) / "adapter_config.json"
    use_adapter = adapter_cfg.is_file()
    base_name = BASE_MODEL_NAME
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

    import transformers.modeling_utils as mu
    try:
        model = AutoModelForCausalLM.from_pretrained(
            base_name,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map={"": 0} if torch.cuda.is_available() else "auto",
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            local_files_only=True,
        )
        tok_src = TITLE_ADAPTER_DIR if use_adapter else base_name
        tokenizer = AutoTokenizer.from_pretrained(tok_src, trust_remote_code=True, local_files_only=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        if use_adapter:
            model = PeftModel.from_pretrained(model, TITLE_ADAPTER_DIR)
        model.eval()
    finally:
        for sd in getattr(mu, "_lazy_sds", []):
            sd.close_and_clear()
        if hasattr(mu, "_lazy_sds"):
            mu._lazy_sds.clear()
        gc.collect()

    prompt_text = f"### Instruction:\n{instruction}\n\n### Response:\n"
    inputs = tokenizer([prompt_text], return_tensors="pt").to(model.device)
    is_deterministic = task_type in ("montage_director", "engineering_cause_effect", "overnight_rank")
    gen_kwargs: Dict[str, Any] = {
        "max_new_tokens": 520 if task_type == "overnight_rank" else (160 if is_deterministic else 320),
        "repetition_penalty": 1.12 if is_deterministic else 1.18,
        "pad_token_id": tokenizer.eos_token_id,
    }
    if is_deterministic:
        gen_kwargs["do_sample"] = False
    else:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = 0.65
        gen_kwargs["top_p"] = 0.90

    with torch.no_grad():
        out_ids = model.generate(**inputs, **gen_kwargs)
    gen_ids = out_ids[0][inputs["input_ids"].shape[1]:]
    raw_reply = tokenizer.decode(gen_ids, skip_special_tokens=True)
    parsed = _extract_first_json_object(raw_reply)
    parsed["_synapsa_adapter"] = TITLE_ADAPTER_DIR if use_adapter else "base_4bit"
    print(_JSON_START)
    print(json.dumps(parsed, ensure_ascii=False))
    print(_JSON_END)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--task", default="lol_metadata")
    parser.add_argument("--input-file", default="")
    ns = parser.parse_args()
    if ns.worker:
        try:
            _run_worker(ns.task, ns.input_file)
        except Exception as exc:
            print(_JSON_START)
            print(json.dumps({"_worker_error": str(exc)}, ensure_ascii=False))
            print(_JSON_END)
            sys.exit(1)
