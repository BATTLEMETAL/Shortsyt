"""
LOL Agent — Quality Gate (bramka jakości po renderze + pętla ponownego montażu)
==============================================================================
Realizuje OPUS_QUALITY_GATES_DIRECTIVE.md: short poniżej progu NIE jest publikowany. Dobry materiał dostaje
diagnozę (kod błędu), styl zapasowy i ponowny render; po max_retries nieudanych próbach trafia do rejected_montages/.

Trzy rzeczy, których stary kod nie robił:
  1. Beat sync jest MIERZONY z przepisu shorta (<plik>.recipe.json: start muzyki, cios w gotowym filmie, drop).
     Stara ocena liczyła go ze wzoru edytora, więc błąd wychodził 0 zawsze, gdy drop był późniejszy niż cios,
     a użyty utwór nigdy nie był rozpoznawany (zawsze drop 30.0 s).
  2. Ocena poniżej progu zatrzymuje publikację (dawniej: "Proceeding with upload anyway (score gate is advisory)").
  3. Nieudany montaż dobrego materiału jest powtarzany innym stylem, a nie wyrzucany ani publikowany.

Czyste funkcje + jedna pętla; render i ocenę dostaje jako funkcje, więc testy działają bez FFmpeg.
"""
import json
import os
import shutil
import time
from typing import Callable, Dict, List, Optional

try:
    from lol_agent import lol_timeline as TL
except ImportError:
    import lol_timeline as TL

_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine_rules.json")
_DEFAULTS = {
    "threshold": 70, "max_retries": 2, "beat_ok_sec": 0.5, "beat_warn_sec": 1.0, "beat_fail_sec": 1.5,
    "kill_coverage_min": 0.75, "hook_first_frame_min": 50, "hook_first_kill_max_sec": 8.0,
    "camera_peak_step_max_px": 65.0, "unverified_drop_score": 60,
    "fallback": {"ERR_PACING": "SPEED_RAMP_FLOW", "ERR_BEAT_SYNC": "BEAT_REALIGN",
                 "ERR_HOOK": "IN_MEDIA_RES", "ERR_CAMERA": "CINEMATIC_DUEL"},
}
# Kolejność prób, gdy diagnoza nie wskazuje stylu albo wskazany już był użyty
_STYLE_ORDER = ["SPEED_RAMP_FLOW", "IN_MEDIA_RES", "CINEMATIC_DUEL", "BEAT_REALIGN"]


def load_rules() -> Dict:
    """Progi bramki z engine_rules.json → "quality_gate" (brak pliku = wartości domyślne z dyrektywy)."""
    rules = dict(_DEFAULTS)
    try:
        with open(_RULES_PATH, encoding="utf-8") as f:
            rules.update({k: v for k, v in (json.load(f).get("quality_gate") or {}).items() if k in _DEFAULTS})
    except Exception:
        pass
    return rules


def read_recipe(video_path: str) -> Optional[Dict]:
    """Przepis shorta zapisany przez render_short obok filmu."""
    try:
        with open(os.path.splitext(video_path)[0] + ".recipe.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def attach_publication_to_recipe(
    video_path: str,
    video_id: Optional[str] = None,
    platform_ids: Optional[Dict] = None,
    archive_dir: Optional[str] = None,
) -> Optional[str]:
    """Dopisuje ID publikacji (YouTube + multi-platform) do <plik>.recipe.json i archiwizuje przepis w recipes_archive/."""
    recipe_path = os.path.splitext(video_path)[0] + ".recipe.json"
    if not os.path.isfile(recipe_path):
        return None
    try:
        with open(recipe_path, encoding="utf-8") as f:
            recipe = json.load(f)
    except Exception:
        return None

    from datetime import datetime, timezone

    if video_id:
        recipe["video_id"] = str(video_id)
    recipe["published_at"] = recipe.get("published_at") or datetime.now(timezone.utc).isoformat()
    if platform_ids and isinstance(platform_ids, dict):
        allowed_keys = (
            "video_id",
            "url",
            "youtube_url",
            "tiktok_publish_id",
            "instagram_media_id",
            "facebook_video_id",
            "scheduled_publish_at",
        )
        cleaned = {k: platform_ids[k] for k in allowed_keys if platform_ids.get(k) is not None}
        if not cleaned.get("tiktok_publish_id") and isinstance(platform_ids.get("tiktok"), dict):
            tt_id = platform_ids["tiktok"].get("publish_id")
            if tt_id:
                cleaned["tiktok_publish_id"] = tt_id
        if not cleaned.get("instagram_media_id") and isinstance(platform_ids.get("instagram"), dict):
            ig_id = platform_ids["instagram"].get("media_id")
            if ig_id:
                cleaned["instagram_media_id"] = ig_id
        if not cleaned.get("facebook_video_id") and isinstance(platform_ids.get("facebook"), dict):
            fb_id = platform_ids["facebook"].get("video_id")
            if fb_id:
                cleaned["facebook_video_id"] = fb_id
        recipe["publication"] = {**(recipe.get("publication") or {}), **cleaned}

    try:
        with open(recipe_path, "w", encoding="utf-8") as f:
            json.dump(recipe, f, indent=2, ensure_ascii=False)
        if video_id and (archive_dir is not None or "PYTEST_CURRENT_TEST" not in os.environ):
            target_archive = archive_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes_archive")
            os.makedirs(target_archive, exist_ok=True)
            archive_path = os.path.join(target_archive, f"{video_id}.recipe.json")
            with open(archive_path, "w", encoding="utf-8") as af:
                json.dump(recipe, af, indent=2, ensure_ascii=False)
        return recipe_path
    except Exception:
        return None


def measure(recipe: Optional[Dict]) -> Dict:
    """Wielkości zmierzone z przepisu: błąd dropu, czas pierwszego killa w gotowym filmie, krok kamery, najdłuższa przerwa."""
    out = {"beat_error_sec": None, "drop_verified": None, "first_kill_out_sec": None,
           "camera_peak_step_px": None, "longest_gap_out_sec": None, "style": "PRIMARY", "track": None}
    if not recipe:
        return out
    out["style"] = recipe.get("montage_style") or "PRIMARY"
    out["camera_peak_step_px"] = recipe.get("camera_peak_step_px")
    music = recipe.get("music") or {}
    if music:
        out["track"] = music.get("track")
        out["drop_verified"] = bool(music.get("drop_verified"))
        if float(music.get("drop_time") or 0.0) > 0.0:
            # gdzie drop pada w filmie minus gdzie jest cios
            drop_in_video = float(music["drop_time"]) - float(music.get("music_start") or 0.0)
            out["beat_error_sec"] = round(abs(drop_in_video - float(music.get("peak_in_output") or recipe.get("peak_in_output") or 0.0)), 3)
    segs = recipe.get("time_segments") or []
    kills = sorted(float(t) for (t, _l) in (recipe.get("peaks_in_clip") or []))
    if kills:
        outs = [TL.warp_time(segs, k) if segs else k for k in kills]
        out["first_kill_out_sec"] = round(outs[0], 3)
        out["longest_gap_out_sec"] = round(max([b - a for a, b in zip(outs, outs[1:])] or [0.0]), 3)
    return out


def rescore(
    quality_result: Dict,
    recipe: Optional[Dict],
    rules: Optional[Dict] = None,
    qa_report: Optional[Dict] = None,
) -> Dict:
    """
    Ocena z lol_quality_scorer.score_short poprawiona o zmierzony beat sync, raport QA i próg z reguł.
    Zwraca NOWY słownik: score, pass, threshold, measured, codes; reszta pól bez zmian.
    """
    rules = rules or load_rules()
    q = json.loads(json.dumps(quality_result, default=str))
    m = measure(recipe)
    br = q.get("breakdown") or {}
    issues = list(q.get("issues") or [])
    if "beat_sync" in br and recipe and (recipe.get("music") is not None):
        e = m["beat_error_sec"]
        if e is None:
            s, val = float(rules["unverified_drop_score"]), "brak znanego dropu"
        elif e <= rules["beat_ok_sec"]:
            s, val = 100.0, f"{e:.2f}s (zmierzone)"
        elif e <= rules["beat_warn_sec"]:
            s, val = 80.0, f"{e:.2f}s (zmierzone)"
        elif e <= rules["beat_fail_sec"]:
            s, val = 55.0, f"{e:.2f}s (zmierzone)"
        else:
            s, val = max(0.0, 100.0 - e * 20.0), f"{e:.2f}s (zmierzone)"
            issues.append(f"Drop muzyki {e:.1f}s od ciosu (zmierzone z przepisu).")
        if e is not None and not m["drop_verified"]:
            s = min(s, float(rules["unverified_drop_score"]) + 20.0)
            val += ", drop niesprawdzony uchem"
        br["beat_sync"] = dict(br["beat_sync"], score=s, value=val)
        q["beat_sync_error_seconds"] = e
    total_w = sum(float(p.get("weight", 0.0)) for p in br.values())
    if total_w > 0:
        q["score"] = round(sum(float(p.get("score", 0.0)) * float(p.get("weight", 0.0)) for p in br.values()) / total_w, 1)

    if qa_report and isinstance(qa_report, dict):
        checks = qa_report.get("checks") or {}
        qa_penalty = 0.0
        sil = checks.get("silence_at_start") or {}
        if sil and sil.get("ok") is False:
            qa_penalty += 8.0
            m["silence_at_start_s"] = sil.get("silence_at_start_s")
            issues.append(f"QA: cisza na początku ({sil.get('silence_at_start_s', '?')}s)")
        cam = checks.get("camera_velocity") or {}
        if cam and cam.get("ok") is False:
            qa_penalty += 6.0
            peak_vel = cam.get("peak_velocity_px") or cam.get("max_delta_px") or (float(rules["camera_peak_step_max_px"]) + 1.0)
            m["camera_peak_step_px"] = max(float(m.get("camera_peak_step_px") or 0.0), float(peak_vel))
            issues.append(f"QA: skok kamery ({peak_vel}px)")
        kill_chk = checks.get("kill_timing") or {}
        if kill_chk and kill_chk.get("ok") is False:
            qa_penalty += 4.0
            issues.append("QA: brak potwierdzonego napisu kill (OCR)")
        if qa_penalty > 0:
            q["score"] = round(max(0.0, float(q.get("score", 0.0)) - qa_penalty), 1)
        q["qa_report"] = {
            "status": qa_report.get("status"),
            "issues": list(qa_report.get("issues") or []),
            "warnings": list(qa_report.get("warnings") or []),
            "penalty": qa_penalty,
        }

    q["breakdown"], q["issues"] = br, issues
    q["threshold"] = rules["threshold"]
    q["pass"] = float(q.get("score", 0.0)) >= float(rules["threshold"])
    q["measured"] = m
    q["codes"] = [] if q["pass"] else diagnose(q, rules)
    return q


def diagnose(q: Dict, rules: Optional[Dict] = None) -> List[str]:
    """Kody błędów od najpoważniejszego. Każdy kod ma styl zapasowy w regułach ("fallback")."""
    rules = rules or load_rules()
    m, br = q.get("measured") or {}, q.get("breakdown") or {}
    found = []   # (waga problemu, kod)
    e = m.get("beat_error_sec")
    if e is not None and e > rules["beat_fail_sec"]:
        found.append((60 + e, "ERR_BEAT_SYNC"))
    cov = q.get("kill_coverage_pct")
    if cov is not None and cov < rules["kill_coverage_min"] * 100:
        found.append((80 - cov / 2, "ERR_PACING"))
    elif (m.get("longest_gap_out_sec") or 0.0) > TL.FAST_GAP_MIN and m.get("style") != "SPEED_RAMP_FLOW":
        found.append((30 + m["longest_gap_out_sec"], "ERR_PACING"))
    ff = (br.get("first_frame") or {}).get("score")
    fk = m.get("first_kill_out_sec")
    if (ff is not None and ff < rules["hook_first_frame_min"]) or (fk is not None and fk > rules["hook_first_kill_max_sec"]):
        found.append((50 + (fk or 0.0), "ERR_HOOK"))
    step = m.get("camera_peak_step_px")
    if step is not None and step > rules["camera_peak_step_max_px"]:
        found.append((40 + step / 4, "ERR_CAMERA"))
    return [c for _w, c in sorted(found, reverse=True)] or ["ERR_UNDIAGNOSED"]


def next_style(codes: List[str], tried: List[str], rules: Optional[Dict] = None, alt_tracks: Optional[List[str]] = None) -> Optional[str]:
    """Styl zapasowy dla pierwszego kodu, którego stylu jeszcze nie próbowano; potem stała kolejność."""
    rules = rules or load_rules()
    wanted = [rules["fallback"].get(c) for c in codes if rules["fallback"].get(c)] + _STYLE_ORDER
    for st in wanted:
        if st in tried:
            continue
        if st == "BEAT_REALIGN" and not alt_tracks:
            continue          # nie ma innego utworu o sprawdzonym dropie
        return st
    return None


def run_gate(first_video: str,
             render_fn: Callable[..., str],
             render_kwargs: Dict,
             score_fn: Callable[..., Dict],
             score_kwargs: Dict,
             verified_tracks: Optional[List[str]] = None,
             rejected_dir: Optional[str] = None,
             log: Callable[[str], None] = print,
             rules: Optional[Dict] = None,
             qa_fn: Optional[Callable[..., Dict]] = None) -> Dict:
    """
    Ocenia gotowy short; gdy nie przechodzi, renderuje go ponownie stylem zapasowym (do max_retries razy).
    Zwraca {"video": ścieżka albo None, "quality": ostatnia ocena, "attempts": [...], "rejected_path": ...}.
    video None = NIE PUBLIKOWAĆ.
      render_fn(**render_kwargs, montage_style=..., preferred_track=...) → ścieżka filmu (lol_editor.render_short)
      score_fn(rendered_path=..., beat_drop_time=..., music_file=..., **score_kwargs) → słownik (score_short)
    """
    rules = rules or load_rules()
    video, tried, attempts, q = first_video, [], [], None
    for attempt in range(int(rules["max_retries"]) + 1):
        recipe = read_recipe(video)
        music = (recipe or {}).get("music") or {}
        raw = score_fn(rendered_path=video, beat_drop_time=float(music.get("drop_time") or 0.0),
                       music_file=music.get("track") or "", **score_kwargs)
        qa_rep = qa_fn(video, source_path=render_kwargs.get("source_path")) if qa_fn else None
        q = rescore(raw, recipe, rules, qa_report=qa_rep)
        style = (q.get("measured") or {}).get("style") or "PRIMARY"
        attempts.append({"attempt": attempt + 1, "style": style, "score": q["score"], "pass": q["pass"], "codes": q["codes"]})
        if q["pass"]:
            log(f"✅ Bramka jakości: {q['score']:.0f}/100 (próg {rules['threshold']}), styl {style}, próba {attempt + 1}")
            return {"video": video, "quality": q, "attempts": attempts, "rejected_path": None}
        log(f"❌ Bramka jakości: {q['score']:.0f}/100 poniżej {rules['threshold']} [{', '.join(q['codes'])}], styl {style}")
        if attempt >= int(rules["max_retries"]):
            break
        alt = [t for t in (verified_tracks or []) if t != music.get("track")]
        style_next = next_style(q["codes"], tried + [style], rules, alt)
        if not style_next:
            log("   Brak kolejnego stylu zapasowego.")
            break
        tried.append(style_next)
        kw = dict(render_kwargs)
        if style_next == "BEAT_REALIGN":
            kw["preferred_track"] = alt[0]          # ten sam montaż, inny utwór o sprawdzonym dropie
        else:
            kw["montage_style"] = style_next
        log(f"🔁 Ponowny montaż: {style_next}" + (f" (utwór {alt[0]})" if style_next == "BEAT_REALIGN" else ""))
        video = render_fn(**kw)
    rejected_path = None
    try:
        rejected_dir = rejected_dir or os.path.join(os.path.dirname(os.path.abspath(video)), "rejected_montages")
        os.makedirs(rejected_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        rejected_path = os.path.join(rejected_dir, f"{stamp}_{os.path.basename(video)}")
        shutil.move(video, rejected_path)
        rec = os.path.splitext(video)[0] + ".recipe.json"
        if os.path.exists(rec):
            shutil.move(rec, os.path.splitext(rejected_path)[0] + ".recipe.json")
        with open(os.path.splitext(rejected_path)[0] + ".rejection.json", "w", encoding="utf-8") as f:
            json.dump({"attempts": attempts, "quality": q}, f, indent=1, ensure_ascii=False, default=str)
    except Exception as e:
        log(f"   [gate] Nie udało się przenieść odrzuconego filmu: {e}")
    log(f"⛔ HARD REJECT po {len(attempts)} próbach: short NIE zostanie opublikowany ({rejected_path or video})")
    return {"video": None, "quality": q, "attempts": attempts, "rejected_path": rejected_path}


def _extract_kill_ts(k_item) -> float:
    if isinstance(k_item, dict):
        return float(k_item.get("timestamp", 0.0))
    if isinstance(k_item, (list, tuple)) and k_item:
        return float(k_item[0])
    return float(k_item)


def simulate_and_guard_director_decision(
    base_window: tuple,
    proposed_window: tuple,
    all_kills_abs: list,
    proposed_style: str = "PRIMARY",
    objective_secured: bool = False,
) -> Dict:
    """
    Dry-Run Symulator i Rollback Guard przed FFmpeg.
    Symuluje wynik bramki dla wariantu bazowego i propozycji Synapsy; blokuje regresję.
    """
    kill_times = sorted(_extract_kill_ts(k) for k in (all_kills_abs or []))

    def _score_window(win: tuple, style: str) -> float:
        w_start, w_end = float(win[0]), float(win[1])
        dur = max(0.0, w_end - w_start)
        score = 100.0
        if dur < 8.0 or dur > 25.0:
            score -= 35.0

        in_win = [t for t in kill_times if (w_start - 0.3) <= t <= (w_end + 0.3)]
        dropped = len(kill_times) - len(in_win)
        if objective_secured and dropped > 0:
            score -= 40.0 * dropped
        elif len(in_win) < 1 or dropped > 1:
            score -= 50.0
        elif dropped == 1:
            # Pojedyncze odcięcie ma lekki koszt rekompensowany poprawą hooka/tempa
            score -= 3.0

        if in_win:
            first_rel = max(0.0, in_win[0] - w_start)
            if first_rel > 8.5 and not objective_secured:
                score -= (first_rel - 8.0) * 4.0
            gaps = [b - a for a, b in zip(in_win, in_win[1:])]
            max_gap = max(gaps) if gaps else 0.0
            if max_gap > 5.0 and style != "SPEED_RAMP_FLOW" and not objective_secured:
                score -= (max_gap - 4.5) * 5.0

        return score

    base_score = _score_window(base_window, "PRIMARY")
    prop_score = _score_window(proposed_window, proposed_style)

    if prop_score + 0.5 < base_score or prop_score < 70.0:
        return {
            "approved": False,
            "rollback_triggered": True,
            "selected_window": base_window,
            "selected_style": "PRIMARY",
            "base_score": round(base_score, 1),
            "proposed_score": round(prop_score, 1),
            "reason": "Rollback Guard: propozycja obniżała wynik symulatora bramki",
        }

    return {
        "approved": True,
        "rollback_triggered": False,
        "selected_window": proposed_window,
        "selected_style": proposed_style,
        "base_score": round(base_score, 1),
        "proposed_score": round(prop_score, 1),
        "reason": "Symulator potwierdził utrzymanie lub wzrost wyniku bramki",
    }
