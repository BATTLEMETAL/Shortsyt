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


def direct_clip_montage(
    action_type: str,
    champion_name: str,
    duration: float,
    peaks: Optional[List[Tuple[float, str]]] = None,
    user_pacing_override: Optional[str] = None,
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

    # Zbuduj słownik profilu tuningowego do bezpośredniego użycia w edytorze
    decision.tuning_profile = {
        "buildup_sec": decision.buildup_sec,
        "outro_sec": decision.outro_sec,
        "zoom_aggression": decision.zoom_aggression,
        "slowmo_duration": decision.slowmo_duration,
        "camera_mode": decision.camera_mode,
        "kill_lock_enabled": decision.kill_lock_enabled,
        "allow_jump_cut": decision.allow_jump_cut,
        "archetype": decision.archetype,
    }

    return decision
