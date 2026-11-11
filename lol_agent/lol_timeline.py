"""
LOL Agent — Timeline (jedna oś czasu dla całego montażu)
=======================================================
Speed-ramp (slow-mo) rozciąga czas wideo. Do 11.11.2026 trzy miejsca liczyły to rozciągnięcie każde po swojemu:
apply_editor_effects (obraz), build_dynamic_captions_filters (napisy) i merge_music (muzyka: wcale). Stąd rozjazdy:
drop muzyki przed ciosem przy multikillach, napisy obok killa, dźwięk gry wyprzedzający obraz.

Ten moduł jest JEDYNYM miejscem, które wie, jak czas źródłowy (klip po wycięciu, 0..clip_duration) przechodzi w czas
wyjściowy (gotowy short). Wszystko inne pyta:  warp_time(segments, t).

Czyste funkcje, bez FFmpeg i bez plików: testy w tests/test_timeline.py działają na każdym komputerze.
"""
from typing import List, Dict, Optional, Tuple

# ── Limity bezpieczeństwa montażu (jedno miejsce; opis w engine_rules.json → "edit_limits") ─────────────────────────
ZOOM_MAX = 1.12              # większy zoom-punch ucina walkę u dołu kadru 9:16
ZOOM_WINDOW_MAX = 0.40       # s po ciosie z zoomem
SLOWMO_WINDOW_MAX = 0.70     # s po ciosie w zwolnieniu (dłuższe = martwy obraz po fragu, PROJECT_GUIDELINES 2C)
MINI_SLOWMO_SPEED = 0.70     # zwolnienie na killach pośrednich
MINI_SLOWMO_LEAD = 0.30      # s przed killem pośrednim
MINI_SLOWMO_WINDOW = 0.70    # s całego okna killa pośredniego
EASE_MAX = 0.15              # s rampy wejścia / wyjścia


def effective_edit_values(zoom_level: float, zoom_duration: float, slowmo_duration: float) -> Dict[str, float]:
    """To, co edytor NAPRAWDĘ zastosuje po limitach. Reżyser i tuning mogą prosić o więcej; tu widać, ile dostaną."""
    return {
        "zoom_level": min(float(zoom_level), ZOOM_MAX),
        "zoom_window": min(float(zoom_duration), ZOOM_WINDOW_MAX),
        "slowmo_window": min(float(slowmo_duration), SLOWMO_WINDOW_MAX),
    }


def build_speed_segments(clip_duration: float,
                         peak_moment: float = 0.0,
                         slowmo_speed: float = 0.75,
                         slowmo_duration: float = 1.5,
                         zoom_duration: float = 0.8,
                         intermediate_peaks: Optional[List[float]] = None,
                         use_easing: bool = True) -> List[Dict]:
    """
    Dzieli klip (czas źródłowy 0..clip_duration) na odcinki o stałej prędkości.
    Zwraca listę {"start", "end", "speed", "zoom"} — w tej kolejności są sklejane w obrazie.
    Logika 1:1 z apply_editor_effects sprzed 11.11.2026 (obraz wychodzi identyczny).
    """
    t0 = 0.0
    t4 = float(clip_duration)
    lead_in = 0.20 if slowmo_speed >= 0.65 else 0.25
    t1 = max(t0, peak_moment - lead_in)
    t2 = peak_moment + min(zoom_duration, ZOOM_WINDOW_MAX)
    t3 = peak_moment + min(slowmo_duration, SLOWMO_WINDOW_MAX)
    t1 = max(t0, min(t1, t4))
    t2 = max(t1, min(t2, t4))
    t3 = max(t2, min(t3, t4))

    slow = slowmo_speed < 0.95
    ease_in_dur = min(EASE_MAX, max(0.0, (t1 - t0) * 0.35)) if (use_easing and slow) else 0.0
    ease_out_dur = min(EASE_MAX, max(0.0, (t4 - t3) * 0.35)) if (use_easing and slow) else 0.0
    ease_in_speed = round(1.0 - 0.5 * (1.0 - slowmo_speed), 3)
    ease_out_speed = round(slowmo_speed + 0.5 * (1.0 - slowmo_speed), 3)

    segs: List[Dict] = []
    curr_t = t0

    def add(start, end, speed, zoom=False):
        segs.append({"start": float(start), "end": float(end), "speed": float(speed), "zoom": bool(zoom)})

    if intermediate_peaks and slow:
        valid_inter = [p for p in sorted(intermediate_peaks) if (p > curr_t + 0.35 and p < (t1 - 0.50))]
        for ip in valid_inter:
            m_start = max(curr_t, ip - MINI_SLOWMO_LEAD)
            m_end = min(t1 - 0.15, ip + (MINI_SLOWMO_WINDOW - MINI_SLOWMO_LEAD))
            if m_start > curr_t + 0.05:
                add(curr_t, m_start, 1.0)
            if m_end > m_start + 0.05:
                add(m_start, m_end, MINI_SLOWMO_SPEED)
            curr_t = m_end

    t1_norm = t1 - ease_in_dur
    if t1_norm > curr_t + 0.05:
        add(curr_t, t1_norm, 1.0)
    if ease_in_dur > 0.04 and t1 > t1_norm + 0.04:
        add(t1_norm, t1, ease_in_speed)
    if t2 > t1 + 0.05:
        add(t1, t2, slowmo_speed, zoom=True)
    if t3 > t2 + 0.05:
        add(t2, t3, slowmo_speed)
    t3_ease_end = t3 + ease_out_dur
    if ease_out_dur > 0.04:
        add(t3, t3_ease_end, ease_out_speed)
    if t4 > t3_ease_end + 0.05:
        add(t3_ease_end, t4, 1.0)
    return segs


def output_duration(segments: List[Dict]) -> float:
    """Długość gotowego obrazu po rozciągnięciu."""
    return sum((s["end"] - s["start"]) / s["speed"] for s in segments)


def warp_time(segments: List[Dict], t: float) -> float:
    """
    Czas źródłowy → czas w gotowym shorcie. Odcinki mogą mieć dziury do 0.05 s (tak je skleja edytor):
    czas w dziurze przypada na początek następnego odcinka. Poza końcem: koniec filmu.
    """
    out = 0.0
    for s in segments:
        if t <= s["start"]:
            return out
        if t <= s["end"]:
            return out + (t - s["start"]) / s["speed"]
        out += (s["end"] - s["start"]) / s["speed"]
    return out


def warp_peaks(segments: List[Dict], peaks: Optional[List[Tuple[float, str]]]) -> List[Tuple[float, str]]:
    """Lista (czas, etykieta) przeniesiona na oś gotowego shorta."""
    return [(round(warp_time(segments, float(t)), 3), lbl) for (t, lbl) in (peaks or [])]


def music_start_for_drop(drop_time: float, peak_in_output: float) -> Tuple[float, float]:
    """
    Gdzie zacząć utwór, żeby drop trafił w cios. Zwraca (start_utworu, błąd_w_sekundach).
    błąd > 0: drop jest wcześniej w utworze niż cios w filmie, więc padnie o tyle sekund ZA WCZEŚNIE
    (utwór grany od zera); wtedy lepiej wybrać inny utwór albo dłuższy lead-in.
    """
    if drop_time <= 0.0:
        return 0.0, 0.0
    start = drop_time - peak_in_output
    if start >= 0.0:
        return round(start, 3), 0.0
    return 0.0, round(-start, 3)


def audio_warp_filter(segments: List[Dict], in_label: str, out_label: str) -> str:
    """
    Filtr FFmpeg, który rozciąga DŹWIĘK GRY tak samo jak obraz (atrim + atempo na odcinek, potem concat),
    żeby uderzenia było słychać wtedy, kiedy je widać. atempo przyjmuje 0.5–100, nasze prędkości to 0.55–1.0.
    """
    if not segments:
        return f"[{in_label}]anull[{out_label}]"
    parts, labels = [], []
    for i, s in enumerate(segments):
        lbl = f"gw{i}"
        tempo = f",atempo={s['speed']:.4f}" if abs(s["speed"] - 1.0) > 1e-6 else ""
        parts.append(f"[{in_label}]atrim=start={s['start']:.3f}:end={s['end']:.3f},asetpts=PTS-STARTPTS{tempo}[{lbl}]")
        labels.append(f"[{lbl}]")
    parts.append("".join(labels) + f"concat=n={len(segments)}:v=0:a=1[{out_label}]")
    return ";".join(parts)


def vertical_crop_width(source_h: int) -> int:
    """Szerokość kadru 9:16 w pikselach źródła, zawsze PARZYSTA w górę (1080 → 608, nie 607: NVENC, AWARIA 8)."""
    w = int(round(source_h * 9 / 16))
    return w + (w % 2)
