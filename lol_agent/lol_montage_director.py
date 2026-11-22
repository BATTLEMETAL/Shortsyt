"""
LOL Agent — AI Montage Director
===============================
Inteligentny reżyser montażu adaptacyjnego (Clip-Adaptive Montage Director).
Automatycznie analizuje złożoność, tempo i strukturę klipu z LoL i dobiera
optymalną strategię montażu (teamfight vs 1v1 vs spaced rampage).

Eliminuje problem 'kamera głupieje w teamfightach' i błędnych cięć jump-cut.
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional


HIGH_MOBILITY_CHAMPIONS = {
    "katarina", "zed", "akali", "leblanc", "talon", "qiyana",
    "fizz", "pyke", "yasuo", "yone", "irelia", "riven", "viego",
    "master yi", "kassadin", "samira", "ahri", "ekko"
}


@dataclass
class MontageDirectorDecision:
    archetype: str                     # CHAOTIC_TEAMFIGHT, SPACED_RAMPAGE, SOLO_DUEL, CLUTCH_OUTPLAY
    allow_jump_cut: bool               # czy wolno dzielić na segmenty jump-cut
    buildup_sec: float                 # czas wejścia przed pierwszym uderzeniem (hook)
    outro_sec: float                   # czas po ostatnim fragu
    zoom_aggression: float             # siła zoom-punch przy eliminacjach (1.10 - 1.30)
    slowmo_duration: float             # długość zwolnienia na decydujący cios
    camera_mode: str                   # tight_player, duel_centroid, predictive_lead
    kill_lock_enabled: bool            # czy blokować kadr w oknie eliminacji
    rationale: str                     # wyjaśnienie decyzji reżysera AI
    tuning_profile: Dict[str, Any] = field(default_factory=dict)
    synapsa_decision: Dict[str, Any] = field(default_factory=dict)


# Style zapasowe bramki jakości (OPUS_QUALITY_GATES_DIRECTIVE.md, punkt 4). Wybiera je lol_quality_gate.py,
# gdy dobry materiał nie przejdzie oceny po renderze. Co każdy styl NAPRAWDĘ zmienia w edytorze:
FALLBACK_STYLES = {
    "SPEED_RAMP_FLOW": "zero cięć; martwy czas między killami przyspieszony (lol_timeline.apply_fast_forward)",
    "IN_MEDIA_RES":    "start klipu przesunięty tak, by pierwszy kill wypadł w IN_MEDIA_RES_FIRST_KILL_AT s; zero cięć",
    "CINEMATIC_DUEL":  "spokojna kamera (mniejszy krok i LERP), zero cięć, zoom 1.15 (po limicie 1.12), zwolnienie na ostatni cios",
    "BEAT_REALIGN":    "ten sam montaż z innym utworem o sprawdzonym dropie (utwór wybiera bramka)",
}
IN_MEDIA_RES_FIRST_KILL_AT = 2.5     # s; uderzenie poprzedza kill, a detektora pierwszego uderzenia nie ma
DUEL_CAMERA = {"max_pan_px": 50.0, "lerp_alpha": 0.30}


def direct_clip_montage(
    action_type: str,
    champion_name: str,
    duration: float,
    peaks: Optional[List[Tuple[float, str]]] = None,
    user_pacing_override: Optional[str] = None,
    force_style: Optional[str] = None,
    objective_secured: bool = False,
    ally_banner_blocked: bool = False,
    min_hp_pct: Optional[float] = None,
    dead_intro_detected: bool = False,
) -> MontageDirectorDecision:
    """
    Główna funkcja decyzyjna reżysera AI.
    Dopasowuje montaż indywidualnie pod dynamikę i specyfikę klipu.
    """
    act = (action_type or "outplay").lower().strip()
    champ = (champion_name or "").lower().strip()
    is_assassin = champ in HIGH_MOBILITY_CHAMPIONS

    peaks = peaks or []
    kill_count = len(peaks)
    
    # Oblicz przerwy między fragami
    gaps = []
    if kill_count >= 2:
        sorted_p = sorted(peaks, key=lambda p: p[0] if isinstance(p, (tuple, list)) else p.get("timestamp", 0.0))
        for i in range(len(sorted_p) - 1):
            t1 = sorted_p[i][0] if isinstance(sorted_p[i], (tuple, list)) else sorted_p[i].get("timestamp", 0.0)
            t2 = sorted_p[i+1][0] if isinstance(sorted_p[i+1], (tuple, list)) else sorted_p[i+1].get("timestamp", 0.0)
            gaps.append(max(0.0, t2 - t1))

    has_long_running_gap = any(g > 4.2 for g in gaps)
    is_tight_burst = (kill_count >= 2 and all(g <= 3.8 for g in gaps))

    # ── 1. ARCHETYP: CHAOTIC_TEAMFIGHT ──────────────────────────────────────────
    # Zwarta, gęsta walka drużynowa (np. Katarina ult, ciasny Triple/Quadra/Penta)
    # W takich akcjach jump-cut jest ZAKAZANY — niszczy płynność i reset animacji!
    if (kill_count >= 2 and is_tight_burst) or (act in ("triple", "quadrakill", "pentakill") and not has_long_running_gap):
        decision = MontageDirectorDecision(
            archetype="CHAOTIC_TEAMFIGHT",
            allow_jump_cut=False,
            buildup_sec=0.6,
            outro_sec=1.4,
            zoom_aggression=1.25,
            slowmo_duration=1.0,
            camera_mode="tight_player",
            kill_lock_enabled=True,
            rationale=(
                f"Wykryto zwarty teamfight ({kill_count} eliminacji w odstępach <=3.8s dla {champ.capitalize()}). "
                f"Wyłączono jump-cut dla zachowania pełnej ciągłości walki i resetów. "
                f"Włączono Kill Anchor Lock gwarantujący obecność każdego fraga w centrum kadru 9:16."
            ),
        )

    # ── 2. ARCHETYP: SPACED_RAMPAGE ───────────────────────────────────────────
    # Rozproszony multi-kill z długimi przerwami na bieg między alejami/rzeką (>4.2s)
    elif kill_count >= 2 and has_long_running_gap and duration > 22.0:
        decision = MontageDirectorDecision(
            archetype="SPACED_RAMPAGE",
            allow_jump_cut=True,
            buildup_sec=0.8,
            outro_sec=1.5,
            zoom_aggression=1.20,
            slowmo_duration=1.2,
            camera_mode="tight_player",
            kill_lock_enabled=True,
            rationale=(
                f"Wykryto rozproszony multi-kill ({kill_count} fragów) z przerwą {max(gaps):.1f}s na bieg. "
                f"Aktywowano selektywny jump-cut aby wyeliminować martwy czas i utrzymać retencję >100%."
            ),
        )

    # ── 3. ARCHETYP: SOLO_DUEL ────────────────────────────────────────────────
    # Pojedynek 1v1 / Solo Bolo / Disrespect / Outplay na linii
    elif act in ("solo_bolo", "solo", "1v1", "duel", "disrespect", "ego_check"):
        decision = MontageDirectorDecision(
            archetype="SOLO_DUEL",
            allow_jump_cut=False,
            buildup_sec=1.4,
            outro_sec=1.8,
            zoom_aggression=1.18,
            slowmo_duration=1.6,
            camera_mode="duel_centroid",
            kill_lock_enabled=True,
            rationale=(
                f"Pojedynek 1v1 ({act.upper()}). Zastosowano kinowy buildup (1.4s) budujący napięcie, "
                f"zerowy jump-cut i kinowe slow-mo na rozstrzygający cios."
            ),
        )

    # ── 4. ARCHETYP: CLUTCH_OUTPLAY / DOMYŚLNY ────────────────────────────────
    else:
        decision = MontageDirectorDecision(
            archetype="CLUTCH_OUTPLAY",
            allow_jump_cut=False,
            buildup_sec=0.9,
            outro_sec=1.5,
            zoom_aggression=1.20,
            slowmo_duration=1.2,
            camera_mode="tight_player",
            kill_lock_enabled=True,
            rationale=(
                f"Dynamiczny outplay ({act.upper()}). Płynny kadr 9:16 skupiony na championie "
                f"z automatyczną blokadą punktu eliminacji."
            ),
        )

    # ── STYL ZAPASOWY (bramka jakości): nadpisuje archetyp, reszta parametrów zostaje z diagnozy klipu ──
    style = (force_style or "").upper().strip()
    if style in FALLBACK_STYLES:
        base = decision.archetype
        decision.archetype = style
        decision.allow_jump_cut = False
        if style == "IN_MEDIA_RES":
            decision.buildup_sec = 0.2
        elif style == "CINEMATIC_DUEL":
            decision.zoom_aggression = 1.15
            decision.slowmo_duration = 1.6
            decision.camera_mode = "duel_centroid"
        decision.rationale = f"Styl zapasowy {style} (po nieudanej ocenie montażu {base}): {FALLBACK_STYLES[style]}."
    else:
        # Zastosuj wyuczone korekty z Bramki 48h (jeśli dostępne dla tego typu akcji)
        try:
            try:
                from lol_agent.learning_engine import get_learning_directive
            except ImportError:
                from learning_engine import get_learning_directive
            d_48 = (get_learning_directive() or {}).get("post_48h_gate_summary") or {}
            adj = (d_48.get("director_adjustments_by_action") or {}).get(act)
            if isinstance(adj, dict):
                if adj.get("buildup_sec_delta"):
                    decision.buildup_sec = max(0.3, round(decision.buildup_sec + float(adj["buildup_sec_delta"]), 2))
                if adj.get("outro_sec_delta"):
                    decision.outro_sec = max(0.8, round(decision.outro_sec + float(adj["outro_sec_delta"]), 2))
                decision.rationale += f" [Korekta Bramki 48h dla {act}: buildup={decision.buildup_sec}s, outro={decision.outro_sec}s]"
        except Exception:
            pass

    # Zastosuj hybrydowy selektor strategii Synapsa + pełny Kontrakt Skutków Parametrów
    synapsa_dec: Dict[str, Any] = {}
    try:
        try:
            from lol_agent.synapsa_engine import decide_montage_with_synapsa
            from lol_agent.learning_engine import get_learning_directive
        except ImportError:
            from synapsa_engine import decide_montage_with_synapsa
            from learning_engine import get_learning_directive
        synapsa_dec = decide_montage_with_synapsa(
            telemetry={
                "action_type": act,
                "champion": champ,
                "duration": duration,
                "peaks": peaks,
                "gaps": gaps,
                "objective_secured": objective_secured,
                "ally_banner_blocked": ally_banner_blocked,
                "min_hp_pct": min_hp_pct,
                "dead_intro_detected": dead_intro_detected,
            },
            directive=get_learning_directive(),
        )
        decision.synapsa_decision = synapsa_dec
        if style not in FALLBACK_STYLES and isinstance(synapsa_dec, dict) and synapsa_dec.get("param_contracts_applied"):
            decision.buildup_sec = float(synapsa_dec.get("buildup_sec", decision.buildup_sec))
            decision.outro_sec = float(synapsa_dec.get("outro_sec", decision.outro_sec))
            decision.zoom_aggression = float(synapsa_dec.get("zoom_aggression", decision.zoom_aggression))
            decision.slowmo_duration = float(synapsa_dec.get("slowmo_duration", decision.slowmo_duration))
            decision.camera_mode = str(synapsa_dec.get("camera_mode") or decision.camera_mode)
    except Exception:
        pass

    # Zbuduj słownik profilu tuningowego do bezpośredniego użycia w edytorze
    _is_solo_act = act in ("solo_bolo", "solo", "1v1", "duel", "disrespect", "ego_check")
    _peak_ts = sorted(
        float(p[0] if isinstance(p, (tuple, list)) else p.get("timestamp", 0.0))
        for p in peaks
    ) if peaks else []
    _fallback_anchor = (
        "first_kill_engage"
        if (len(_peak_ts) >= 2 and not _is_solo_act and 0.8 <= _peak_ts[0] <= 7.0 and _peak_ts[-1] > 8.5)
        else "climax_final_kill"
    )
    decision.tuning_profile = {
        "buildup_sec": decision.buildup_sec,
        "outro_sec": decision.outro_sec,
        "zoom_aggression": decision.zoom_aggression,
        "slowmo_duration": decision.slowmo_duration,
        "camera_mode": decision.camera_mode,
        "kill_lock_enabled": decision.kill_lock_enabled,
        "allow_jump_cut": decision.allow_jump_cut,
        "archetype": decision.archetype,
        "preferred_montage_style": (synapsa_dec or {}).get("style", "PRIMARY"),
        "drop_anchor": (synapsa_dec or {}).get("drop_anchor") or _fallback_anchor,
        "synapsa_decision": synapsa_dec,
    }

    return decision
