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
# Styl SPEED_RAMP_FLOW (zamiast cięć): martwy czas między killami leci szybciej
FAST_FORWARD_SPEED = 3.0     # 2.5–3.5 wg dyrektywy bramek jakości
FAST_GAP_MIN = 3.5           # s przerwy między killami, od której przyspieszamy
FAST_TAIL = 0.9              # s po killu w normalnym tempie (widać skutek)
FAST_LEAD = 1.0              # s przed następnym killem w normalnym tempie (widać wejście)


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


def apply_fast_forward(segments: List[Dict], kill_times: Optional[List[float]], speed: float = FAST_FORWARD_SPEED) -> List[Dict]:
    """
    Styl SPEED_RAMP_FLOW: zero cięć. Odcinki w tempie 1.0 leżące w przerwie między killami dłuższej niż FAST_GAP_MIN
    dostają prędkość `speed`; FAST_TAIL po killu i FAST_LEAD przed następnym zostają w tempie 1.0.
    Zwolnień i zoomów nie rusza. kill_times: czasy killi w klipie (czas źródłowy).
    """
    ks = sorted(float(k) for k in (kill_times or []))
    windows = [(a + FAST_TAIL, b - FAST_LEAD) for a, b in zip(ks, ks[1:]) if (b - a) > FAST_GAP_MIN]
    windows = [(a, b) for a, b in windows if b - a > 0.3]
    if not windows:
        return segments
    out: List[Dict] = []
    for sg in segments:
        if abs(sg["speed"] - 1.0) > 1e-6 or sg.get("zoom"):
            out.append(sg); continue
        cuts = [sg["start"], sg["end"]]
        for a, b in windows:
            cuts += [x for x in (a, b) if sg["start"] < x < sg["end"]]
        cuts = sorted(set(cuts))
        for a, b in zip(cuts, cuts[1:]):
            if b - a < 0.05:
                continue
            mid = (a + b) / 2.0
            fast = any(wa <= mid <= wb for wa, wb in windows)
            out.append({"start": float(a), "end": float(b), "speed": float(speed if fast else 1.0), "zoom": False})
    return out


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


def coalesce_audio_segments(segments: List[Dict]) -> List[Dict]:
    """Łączy sąsiednie odcinki audio o tej samej prędkości (zoom nie dzieli dźwięku)."""
    merged: List[Dict] = []
    for s in (segments or []):
        start = float(s["start"])
        end = float(s["end"])
        speed = float(s["speed"])
        if end <= start + 1e-4:
            continue
        if merged and abs(merged[-1]["speed"] - speed) < 1e-4 and abs(merged[-1]["end"] - start) <= 0.06:
            merged[-1]["end"] = end
        else:
            merged.append({"start": start, "end": end, "speed": speed})
    return merged


def audio_warp_filter(
    segments: List[Dict],
    in_label: str,
    out_label: str,
    mode: str = "atempo",
) -> str:
    """
    Filtr FFmpeg rozciągający dźwięk gry zgodnie z osią czasu montażu.
    - mode='atempo': zachowuje zgodność z klasycznymi testami (po segmencie + atempo).
    - mode='clean': scala odcinki o stałej prędkości, normalizuje do 44.1kHz stereo,
      dla slow-mo (<1.0) stosuje płynny tape slowdown (asetrate+aresample bez artefaktów WSOLA
      i bez rozjazdu A/V), a na stykach dodaje mikro-fade 5ms eliminujący trzaski.
    """
    if not segments:
        return f"[{in_label}]anull[{out_label}]"

    if mode != "clean":
        parts, labels = [], []
        for i, s in enumerate(segments):
            lbl = f"gw{i}"
            tempo = f",atempo={s['speed']:.4f}" if abs(s["speed"] - 1.0) > 1e-6 else ""
            parts.append(f"[{in_label}]atrim=start={s['start']:.3f}:end={s['end']:.3f},asetpts=PTS-STARTPTS{tempo}[{lbl}]")
            labels.append(f"[{lbl}]")
        parts.append("".join(labels) + f"concat=n={len(segments)}:v=0:a=1[{out_label}]")
        return ";".join(parts)

    merged = coalesce_audio_segments(segments)
    if not merged:
        return f"[{in_label}]anull[{out_label}]"

    parts, labels = [], []
    for i, s in enumerate(merged):
        lbl = f"gw{i}"
        sp = s["speed"]
        dur_out = (s["end"] - s["start"]) / max(sp, 1e-3)
        if abs(sp - 1.0) <= 1e-4:
            speed_flt = ""
        elif sp < 1.0:
            # Czyste zwolnienie bez ziarnistości/echa WSOLA i bez dryfu synchronizacji
            speed_flt = f",asetrate=44100*{sp:.6f},aresample=44100"
        else:
            speed_flt = f",atempo={sp:.4f}"
        fade_flt = ""
        if dur_out > 0.04:
            fade_out_st = max(0.0, dur_out - 0.006)
            fade_flt = f",afade=t=in:st=0:d=0.005,afade=t=out:st={fade_out_st:.4f}:d=0.005"
        parts.append(
            f"[{in_label}]atrim=start={s['start']:.3f}:end={s['end']:.3f},"
            f"aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS{speed_flt}{fade_flt}[{lbl}]"
        )
        labels.append(f"[{lbl}]")
    parts.append("".join(labels) + f"concat=n={len(merged)}:v=0:a=1[{out_label}]")
    return ";".join(parts)


def vertical_crop_width(source_h: int) -> int:
    """Szerokość kadru 9:16 w pikselach źródła, zawsze PARZYSTA w górę (1080 → 608, nie 607: NVENC, AWARIA 8)."""
    w = int(round(source_h * 9 / 16))
    return w + (w % 2)
