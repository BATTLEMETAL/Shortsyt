"""
Shortsyt / Synapsa — Moduł Dedukcji Zmian, Oglądania Shortsów i Oceny Oglądalności (Etap 10)
=============================================================================================
Zamyka pełną pętlę inżyniersko-naukową Synapsy (Sykofankcja 0, 100% lokalnie na RTX 3060 + CV/FFmpeg):
  1. `predict_change_effect()`      — wstępna dedukcja PRZED zmianą (co powinno wzrosnąć/spaść i dlaczego)
  2. `inspect_rendered_short()`     — twardy odczyt wideo i audio z gotowego `.mp4` (klatka 0.0s, pas killi,
                                      widoczność/krawędzie gracza, czarna końcówka, clipping, delta A/V)
  3. `compare_shorts_and_verify()`  — porównanie Before vs After (`BETTER`/`WORSE`/`NO_CHANGE`/`MIXED`)
                                      + weryfikacja hipotezy (`CONFIRMED`/`PARTIAL`/`NO_EFFECT`/`REFUTED`)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

LOL_AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_RULES_PATH = LOL_AGENT_DIR / "engine_rules.json"
DEFAULT_VERIFICATION_LOG = LOL_AGENT_DIR / "synapsa_verification_log.jsonl"

_DEFAULT_RUBRIC: Dict[str, Any] = {
    "weights": {
        "hook_frame0": 22.0,
        "framing": 24.0,
        "overlay_clarity": 20.0,
        "audio_sync": 20.0,
        "pacing": 14.0,
    },
    "no_change_thresholds": {
        "mean_frame_mad_lt": 1.8,
        "changed_frames_ratio_lt": 0.08,
        "abs_delta_watchability_lt": 1.5,
        "abs_delta_dur_lt": 0.20,
        "abs_delta_clip_lte": 2,
        "abs_delta_av_lt": 0.02,
    },
    "verdict_thresholds": {
        "better_delta_min": 2.5,
        "worse_delta_max": -2.5,
        "critical_clip_increase": 20,
        "acceptable_shunpo_step_px": 520.0,
        "chaotic_cam_step_px": 600.0,
    },
}


def load_watchability_rubric(rules_path: Optional[Path] = None) -> Dict[str, Any]:
    """Ładuje rubrykę oceny oglądalności z `engine_rules.json["watchability_rubric"]`."""
    rp = Path(rules_path) if rules_path is not None else DEFAULT_RULES_PATH
    rubric = {k: dict(v) for k, v in _DEFAULT_RUBRIC.items()}
    try:
        if rp.is_file():
            raw = json.loads(rp.read_text(encoding="utf-8"))
            custom = raw.get("watchability_rubric")
            if isinstance(custom, dict):
                for sect in ("weights", "no_change_thresholds", "verdict_thresholds"):
                    if isinstance(custom.get(sect), dict):
                        rubric[sect].update(custom[sect])
    except Exception:
        pass
    return rubric


def _import_player_checker():
    try:
        from lol_agent.lol_quality_validator import _check_player_in_frame
        return _check_player_in_frame
    except ImportError:
        from lol_quality_validator import _check_player_in_frame
        return _check_player_in_frame


def _import_warp_time():
    try:
        from lol_agent.lol_timeline import warp_time
        return warp_time
    except ImportError:
        from lol_timeline import warp_time
        return warp_time


def _import_generic_hooks() -> Tuple[set, Any]:
    try:
        from lol_agent.lol_metadata_generator import _GENERIC_HOOKS
    except ImportError:
        from lol_metadata_generator import _GENERIC_HOOKS
    return set(_GENERIC_HOOKS), None


def _import_synapsa():
    try:
        from lol_agent.synapsa_engine import generate_with_synapsa, is_synapsa_available
        return generate_with_synapsa, is_synapsa_available
    except ImportError:
        from synapsa_engine import generate_with_synapsa, is_synapsa_available
        return generate_with_synapsa, is_synapsa_available


def _read_recipe_for_mp4(mp4_path: Path, recipe_path: Optional[str] = None) -> Dict[str, Any]:
    candidates: List[Path] = []
    if recipe_path:
        candidates.append(Path(recipe_path))
    candidates.append(mp4_path.with_suffix(".recipe.json"))
    for rp in candidates:
        if rp.is_file():
            try:
                data = json.loads(rp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return {}


def _overlay_text_scores(roi_bgr: np.ndarray) -> Tuple[float, float, float]:
    """Zwraca (bright_text_ratio, dark_box_ratio, edge_ratio) w wybranym wycinku klatki."""
    if roi_bgr is None or roi_bgr.size == 0:
        return 0.0, 0.0, 0.0
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    h_ch, s_ch, v_ch = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    white = (v_ch > 205) & (s_ch < 75)
    gold = (h_ch >= 12) & (h_ch <= 38) & (s_ch > 105) & (v_ch > 175)
    bright_ratio = float(np.mean(white | gold))
    dark_ratio = float(np.mean(v_ch < 65))
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 90, 220)
    edge_ratio = float(np.mean(edges > 0))
    return bright_ratio, dark_ratio, edge_ratio


def _probe_video_and_audio(mp4_path: Path) -> Dict[str, Any]:
    """Odczytuje dokładne długości strumieni A/V z `ffprobe` oraz metryki PCM z `ffmpeg`."""
    out: Dict[str, Any] = {
        "video_dur_s": 0.0,
        "audio_dur_s": 0.0,
        "av_delta_s": 0.0,
        "audio_peak": 0.0,
        "audio_rms": 0.0,
        "audio_clip_gt_096": 0,
        "audio_dropout_blocks": 0,
        "silence_at_start_s": 0.0,
    }
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(mp4_path)],
        capture_output=True, text=True, check=False,
    )
    streams = json.loads(r.stdout or "{}").get("streams", [])
    v_dur: Optional[float] = None
    a_dur: Optional[float] = None
    for s in streams:
        if s.get("codec_type") == "video" and v_dur is None and s.get("duration") is not None:
            v_dur = float(s["duration"])
        elif s.get("codec_type") == "audio" and a_dur is None and s.get("duration") is not None:
            a_dur = float(s["duration"])
    out["video_dur_s"] = round(v_dur or 0.0, 3)
    out["audio_dur_s"] = round(a_dur or 0.0, 3)
    if v_dur is not None and a_dur is not None:
        out["av_delta_s"] = round(abs(a_dur - v_dur), 3)

    if a_dur is None or a_dur <= 0.0:
        return out

    wav_r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4_path), "-vn", "-ac", "1", "-ar", "44100", "-f", "f32le", "pipe:1"],
        capture_output=True, check=False,
    )
    samples = np.frombuffer(wav_r.stdout, dtype=np.float32) if wav_r.stdout else np.zeros(0, dtype=np.float32)
    if samples.size == 0:
        return out

    abs_s = np.abs(samples)
    out["audio_peak"] = round(float(np.max(abs_s)), 4)
    out["audio_rms"] = round(float(np.sqrt(np.mean(samples ** 2))), 4)
    out["audio_clip_gt_096"] = int(np.sum(abs_s > 0.96))

    # Sprawdź zaniki dźwięku w środkowym oknie filmu (0.25s bloki poniżej RMS 0.005)
    block_n = 11025
    dropouts = 0
    edge_pad = min(22050, len(samples) // 6)
    mid_samples = samples[edge_pad: max(edge_pad, len(samples) - edge_pad)]
    for i in range(0, len(mid_samples), block_n):
        seg = mid_samples[i: i + block_n]
        if seg.size >= block_n // 2:
            if float(np.sqrt(np.mean(seg ** 2))) < 0.005:
                dropouts += 1
    out["audio_dropout_blocks"] = dropouts

    # Wykryj ciszę na początku klipu (20ms ramki)
    win = 882
    sil_frames = 0
    for i in range(0, min(len(samples), 44100), win):
        seg = samples[i: i + win]
        if seg.size < win // 2:
            break
        if float(np.sqrt(np.mean(seg ** 2))) < 0.004:
            sil_frames += 1
        else:
            break
    out["silence_at_start_s"] = round(sil_frames * 0.02, 2)
    return out


def _is_hook_generic(hook_text: str, action_type: str, objective_secured: bool) -> bool:
    generic_set, _ = _import_generic_hooks()
    cleaned = " ".join(str(hook_text or "").upper().split()).strip()
    if not cleaned or len(cleaned) < 6:
        return True
    if cleaned.rstrip("!.") in generic_set:
        return True
    if any(tok in cleaned for tok in ("INSANE OUTPLAY", "NICE PLAY")):
        return True
    if cleaned.rstrip("!.").endswith((" CLIP", " HIGHLIGHT", " VIDEO", " PLAY")):
        return True
    act = (action_type or "").lower()
    if objective_secured and any(k in act for k in ("quadra", "triple", "penta")):
        if not any(k in cleaned for k in ("DRAGON", "DRAKE", "BARON", "STEAL", "OBJECTIVE")):
            return True
    return False


def _compute_watchability_subscores(metrics: Dict[str, Any], rubric: Dict[str, Any]) -> Tuple[Dict[str, float], float]:
    w = rubric["weights"]
    vt = rubric["verdict_thresholds"]

    # 1. Hook i klatka 0.0s
    hook_frac = 1.0
    if not metrics.get("frame0_hook_legible", True):
        hook_frac -= 0.45
    if metrics.get("hook_is_generic", False):
        hook_frac -= 0.25
    fk = metrics.get("first_kill_out_sec")
    fk_limit = 5.5 if metrics.get("objective_secured") else 4.5
    if fk is not None and float(fk) > fk_limit:
        excess = min(1.0, (float(fk) - fk_limit) / 4.0)
        hook_frac -= 0.35 * excess
    hook_score = round(w["hook_frame0"] * max(0.0, hook_frac), 2)

    # 2. Kadrowanie i kamera
    frame_frac = 1.0
    vis_ratio = float(metrics.get("player_visible_ratio") if metrics.get("player_visible_ratio") is not None else 1.0)
    if 0.0 < vis_ratio < 0.75:
        frame_frac -= min(0.45, (0.75 - vis_ratio) * 1.1)
    edge_clip = float(metrics.get("player_edge_clip_ratio") or 0.0)
    intro_vis = float(metrics.get("intro_player_visible_ratio") if metrics.get("intro_player_visible_ratio") is not None else 1.0)
    if edge_clip > 0.05:
        frame_frac -= min(0.55, edge_clip * 2.0)
    if intro_vis < 0.40:
        frame_frac -= min(0.35, (0.40 - intro_vis) * 1.2)
    cam_step = metrics.get("camera_peak_step_px")
    if cam_step is not None:
        cs = float(cam_step)
        if cs > float(vt["chaotic_cam_step_px"]):
            frame_frac -= min(0.35, (cs - float(vt["chaotic_cam_step_px"])) / 400.0 + 0.15)
        elif cs > float(vt["acceptable_shunpo_step_px"]):
            frame_frac -= 0.10
    framing_score = round(w["framing"] * max(0.0, frame_frac), 2)

    # 3. Czytelność nakładek (brak zasłaniania środka ekranu)
    overlay_frac = 1.0
    if metrics.get("kill_overlay_zone") == "center_blocking":
        cb = max(0.4, float(metrics.get("center_blocked_kills_ratio") or 1.0))
        overlay_frac -= min(0.85, 0.45 + 0.40 * cb)
    elif float(metrics.get("center_blocked_kills_ratio") or 0.0) > 0.2:
        overlay_frac -= min(0.7, float(metrics["center_blocked_kills_ratio"]))
    overlay_score = round(w["overlay_clarity"] * max(0.0, overlay_frac), 2)

    # 4. Audio i synchronizacja A/V
    audio_frac = 1.0
    clips = int(metrics.get("audio_clip_gt_096") or 0)
    if clips > 0:
        audio_frac -= min(0.45, 0.12 + clips / 180.0)
    av_d = float(metrics.get("av_delta_s") or 0.0)
    if av_d > 0.04:
        audio_frac -= min(0.35, (av_d - 0.04) * 5.0 + 0.12)
    if metrics.get("black_end_frame", False):
        audio_frac -= 0.45
    if float(metrics.get("silence_at_start_s") or 0.0) > 0.35:
        audio_frac -= 0.25
    if int(metrics.get("audio_dropout_blocks") or 0) > 0:
        audio_frac -= min(0.40, 0.15 * int(metrics["audio_dropout_blocks"]))
    audio_score = round(w["audio_sync"] * max(0.0, audio_frac), 2)

    # 5. Pacing / długość pod retencję
    dur = float(metrics.get("video_dur_s") or 0.0)
    act = str(metrics.get("action_type") or "outplay").lower()
    is_epic_multi = any(k in act for k in ("quadra", "penta")) or bool(metrics.get("objective_secured"))
    ideal_lo, ideal_hi = (14.0, 24.5) if is_epic_multi else (10.0, 17.5)
    pace_frac = 1.0
    if dur > ideal_hi:
        pace_frac -= min(0.80, (dur - ideal_hi) / 6.0)
    elif 0.0 < dur < ideal_lo:
        pace_frac -= min(0.60, (ideal_lo - dur) / 5.0)
    pacing_score = round(w["pacing"] * max(0.0, pace_frac), 2)

    subscores = {
        "hook_frame0": hook_score,
        "framing": framing_score,
        "overlay_clarity": overlay_score,
        "audio_sync": audio_score,
        "pacing": pacing_score,
    }
    total = round(sum(subscores.values()), 2)
    return subscores, total


def inspect_rendered_short(mp4_path: str, recipe_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Ogląda gotowy plik `.mp4` klatka po klatce (OpenCV) + analizuje strumień audio (`ffmpeg`/`ffprobe`)
    i przepis `.recipe.json`, zwracając obiektywny profil oglądalności `watchability_score` (`0..100`).
    """
    p = Path(mp4_path)
    if not p.is_file():
        raise FileNotFoundError(f"Brak pliku wideo do obejrzenia: {p}")

    rubric = load_watchability_rubric()
    recipe = _read_recipe_for_mp4(p, recipe_path=recipe_path)
    audio_av = _probe_video_and_audio(p)

    cap = cv2.VideoCapture(str(p))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Nie mozna otworzyc wideo: {p}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cv_dur = frame_cnt / fps if fps > 0 else 0.0
        dur = audio_av["video_dur_s"] or cv_dur

        def _read_at(t_sec: float) -> Optional[np.ndarray]:
            target_t = min(max(0.0, float(t_sec)), max(0.0, cv_dur - 0.03))
            cap.set(cv2.CAP_PROP_POS_MSEC, target_t * 1000.0)
            ok, fr = cap.read()
            return fr if ok and fr is not None else None

        # 1. Klatka 0.0s hook legibility (`t=0.04s` vs `t=0.70s`)
        fr_0 = _read_at(0.04)
        fr_07 = _read_at(min(0.70, max(0.25, cv_dur * 0.25))) if cv_dur > 0.35 else fr_0
        frame0_hook_legible = True
        bright_004, bright_070, dark_004 = 0.0, 0.0, 0.0
        if fr_0 is not None and fr_07 is not None and width > 0 and height > 0:
            y0, y1 = int(height * 0.072), int(height * 0.185)
            x0, x1 = int(width * 0.16), int(width * 0.84)
            bright_004, dark_004, edge_004 = _overlay_text_scores(fr_0[y0:y1, x0:x1])
            bright_070, dark_070, edge_070 = _overlay_text_scores(fr_07[y0:y1, x0:x1])
            if bright_070 >= 0.008 and (bright_004 / max(bright_070, 1e-6)) < 0.48:
                frame0_hook_legible = False
            elif dark_004 >= 0.14 and bright_004 < 0.005:
                frame0_hook_legible = False

        # 2. Pas napisów przy killach (`upper_safe` y=0.21..0.30 vs `center_blocking` y=0.47..0.60)
        warp_time = _import_warp_time()
        peaks_raw = recipe.get("peaks_in_clip") or []
        t_segs = recipe.get("time_segments") or []
        warped_kills: List[float] = []
        for item in peaks_raw:
            if isinstance(item, (list, tuple)) and item:
                kt = float(item[0])
                wt = warp_time(t_segs, kt) if t_segs else kt
                if 0.0 <= wt <= max(0.5, cv_dur):
                    warped_kills.append(round(wt, 2))
        first_kill_out_sec = warped_kills[0] if warped_kills else None

        sample_kill_ts = [min(cv_dur - 0.15, kt + 0.45) for kt in warped_kills if kt + 0.45 < cv_dur]
        if not sample_kill_ts and cv_dur > 1.0:
            sample_kill_ts = [cv_dur * f for f in (0.35, 0.65, 0.88)]

        center_hits = 0
        upper_hits = 0
        for kt in sample_kill_ts:
            kfr = _read_at(kt)
            if kfr is None or width <= 0 or height <= 0:
                continue
            x0, x1 = int(width * 0.20), int(width * 0.80)
            cb, cd, ce = _overlay_text_scores(kfr[int(height * 0.48):int(height * 0.60), x0:x1])
            ub, ud, ue = _overlay_text_scores(kfr[int(height * 0.215):int(height * 0.305), x0:x1])
            if cb >= 0.014 and cd >= 0.18 and ce >= 0.035:
                center_hits += 1
            if ub >= 0.012 and ud >= 0.080 and ue >= 0.012:
                upper_hits += 1

        if sample_kill_ts and center_hits > upper_hits and (upper_hits == 0 or center_hits >= 2 * upper_hits):
            kill_overlay_zone = "center_blocking"
        elif upper_hits > 0:
            kill_overlay_zone = "upper_safe"
        else:
            kill_overlay_zone = "none"
        if kill_overlay_zone == "upper_safe" and center_hits <= 1:
            center_blocked_ratio = 0.0
        else:
            center_blocked_ratio = round(center_hits / max(1, len(sample_kill_ts)), 3)

        # 3. Kadrowanie gracza (próbki w intro + całym filmie przez wspólny _check_player_in_frame)
        player_check = _import_player_checker()
        intro_hi = min(2.8, max(0.4, cv_dur * 0.35))
        intro_ts = list(np.linspace(0.2, intro_hi, 5)) if cv_dur >= 0.6 else [0.1]
        body_ts = list(np.linspace(0.15, max(0.2, cv_dur - 0.15), 18)) if cv_dur > 0.5 else [0.05]

        intro_vis = 0
        for ts in intro_ts:
            fr = _read_at(float(ts))
            if fr is not None:
                ok_p, _, _ = player_check(fr)
                if ok_p:
                    intro_vis += 1

        vis_cnt, center_cnt, clip_cnt = 0, 0, 0
        for ts in body_ts:
            fr = _read_at(float(ts))
            if fr is not None and width > 0:
                ok_p, _, mean_pt = player_check(fr)
                if ok_p and mean_pt is not None:
                    vis_cnt += 1
                    nx = float(mean_pt[0]) / float(width)
                    if 0.18 <= nx <= 0.82:
                        center_cnt += 1
                    if nx < 0.18 or nx > 0.82:
                        clip_cnt += 1

        # 4. Ostatnia klatka (wykrywanie czarnej końcówki)
        last_luma = -1.0
        last_std = 0.0
        if frame_cnt >= 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_cnt - 1))
            ok_last, fr_last = cap.read()
            if ok_last and fr_last is not None:
                last_luma = round(float(np.mean(fr_last)), 1)
                last_std = round(float(np.std(fr_last)), 1)
    finally:
        cap.release()

    black_end_frame = bool((0.0 <= last_luma < 8.0) or (audio_av["av_delta_s"] > 0.055 and last_luma < 15.0))
    hook_text = str(recipe.get("hook_text") or "")
    action_type = str(recipe.get("action_type") or "outplay")
    objective_secured = bool(
        recipe.get("objective_secured")
        or ("DRAGON" in hook_text.upper())
        or (recipe.get("director", {}).get("synapsa_decision", {}).get("operation") == "KEEP_FULL_CONTINUOUS" and "quadra" in action_type.lower())
    )
    hook_is_generic = _is_hook_generic(hook_text, action_type, objective_secured) if hook_text else False

    metrics: Dict[str, Any] = {
        "mp4_path": str(p),
        "filename": p.name,
        "source": recipe.get("source") or "",
        "action_type": action_type,
        "objective_secured": objective_secured,
        "montage_style": recipe.get("montage_style") or "",
        "director_operation": recipe.get("director_operation") or "",
        "camera_peak_step_px": recipe.get("camera_peak_step_px"),
        "hook_text": hook_text,
        "hook_is_generic": hook_is_generic,
        "frame0_hook_legible": frame0_hook_legible,
        "frame0_bright_ratio": round(bright_004, 5),
        "frame07_bright_ratio": round(bright_070, 5),
        "kill_overlay_zone": kill_overlay_zone,
        "center_blocked_kills_ratio": center_blocked_ratio,
        "first_kill_out_sec": first_kill_out_sec,
        "warped_kill_ts": warped_kills,
        "intro_player_visible_ratio": round(intro_vis / max(1, len(intro_ts)), 3),
        "player_visible_ratio": round(vis_cnt / max(1, len(body_ts)), 3),
        "player_centered_ratio": round(center_cnt / max(1, vis_cnt), 3) if vis_cnt else 0.0,
        "player_edge_clip_ratio": round(clip_cnt / max(1, vis_cnt), 3) if vis_cnt else 0.0,
        "last_frame_luma": last_luma,
        "last_frame_std": last_std,
        "black_end_frame": black_end_frame,
        **audio_av,
    }
    subscores, total_score = _compute_watchability_subscores(metrics, rubric)
    metrics["subscores"] = subscores
    metrics["watchability_score"] = total_score
    return metrics


def _compute_visual_frame_diff(mp4_a: str, mp4_b: str, n_frames: int = 16) -> Dict[str, Any]:
    """Porównuje równomierne klatki dwóch plików `.mp4` w 160x284 grayscale."""
    cap_a = cv2.VideoCapture(str(mp4_a))
    cap_b = cv2.VideoCapture(str(mp4_b))
    try:
        fps_a = cap_a.get(cv2.CAP_PROP_FPS) or 30.0
        fps_b = cap_b.get(cv2.CAP_PROP_FPS) or 30.0
        dur_a = (cap_a.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps_a
        dur_b = (cap_b.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps_b
        span = min(dur_a, dur_b)
        if span <= 0.1:
            return {"mean_frame_mad": 99.0, "changed_frames_ratio": 1.0, "samples": 0}
        ts = np.linspace(0.04, max(0.05, span - 0.05), n_frames)
        mads: List[float] = []
        for t in ts:
            cap_a.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            cap_b.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
            oka, fa = cap_a.read()
            okb, fb = cap_b.read()
            if not (oka and okb and fa is not None and fb is not None):
                continue
            ga = cv2.cvtColor(cv2.resize(fa, (160, 284)), cv2.COLOR_BGR2GRAY)
            gb = cv2.cvtColor(cv2.resize(fb, (160, 284)), cv2.COLOR_BGR2GRAY)
            mads.append(float(np.mean(cv2.absdiff(ga, gb))))
        if not mads:
            return {"mean_frame_mad": 99.0, "changed_frames_ratio": 1.0, "samples": 0}
        changed = sum(1 for m in mads if m > 3.0)
        return {
            "mean_frame_mad": round(float(np.mean(mads)), 3),
            "changed_frames_ratio": round(changed / len(mads), 3),
            "samples": len(mads),
        }
    finally:
        cap_a.release()
        cap_b.release()


def predict_change_effect(
    before_inspection: Dict[str, Any],
    proposed_changes: Dict[str, Any],
    use_local_ai: bool = True,
) -> Dict[str, Any]:
    """
    Wstępna dedukcja PRZED zmianą: przewiduje, jak `proposed_changes` wpłyną na metryki
    oglądalności i czy efekt będzie `BETTER`, `WORSE`, `MIXED` czy `NO_CHANGE`.
    """
    b = dict(before_inspection or {})
    ch = dict(proposed_changes or {})
    shifts: Dict[str, str] = {}
    est_delta = 0.0
    risks: List[str] = []

    desc_low = str(ch.get("description") or ch.get("notes") or "").lower()

    # 1. Hook frame 0 fade-in
    if "hook_fade_in" in ch or "hook_fade_in_at_t0" in ch or "fade_in" in desc_low:
        fi = ch.get("hook_fade_in", ch.get("hook_fade_in_at_t0"))
        if fi is False or "fade_in=false" in desc_low or "no fade" in desc_low:
            if not b.get("frame0_hook_legible", True):
                shifts["frame0_hook_legible"] = "UP"
                est_delta += 8.5
            else:
                shifts["frame0_hook_legible"] = "SAME"
        elif fi is True:
            shifts["frame0_hook_legible"] = "DOWN"
            est_delta -= 8.5
            risks.append("Fade-in na t=0 ukryje tekst hooka na pierwszej klatce.")

    # 2. Strefa napisów killi (upper_safe vs center_blocking)
    by = ch.get("banner_kill_y_ratio", ch.get("overlay_y_ratio"))
    cz = str(ch.get("kill_overlay_zone") or "").lower()
    if (by is not None and float(by) <= 0.32) or cz == "upper_safe" or "upper" in desc_low:
        if b.get("kill_overlay_zone") == "center_blocking" or float(b.get("center_blocked_kills_ratio") or 0.0) > 0.1:
            shifts["center_blocked_kills_ratio"] = "DOWN"
            est_delta += 14.0
        else:
            shifts["center_blocked_kills_ratio"] = "SAME"
    elif (by is not None and float(by) >= 0.45) or cz == "center_blocking":
        shifts["center_blocked_kills_ratio"] = "UP"
        est_delta -= 14.0
        risks.append("Napisy na y>=0.45 zasłonią Katarinę podczas killi.")

    # 3. Synchronizacja A/V (`-shortest`, `atrim`)
    if ch.get("audio_atrim") or ch.get("shortest") or "shortest" in desc_low or "atrim" in desc_low:
        if float(b.get("av_delta_s") or 0.0) > 0.035 or b.get("black_end_frame"):
            shifts["av_delta_s"] = "DOWN"
            if b.get("black_end_frame"):
                shifts["black_end_frame"] = "DOWN"
                est_delta += 7.0
            est_delta += 3.0
    elif ch.get("disable_shortest") is True:
        shifts["av_delta_s"] = "UP"
        est_delta -= 4.0

    # 4. Audio limiter (`alimiter`)
    if ch.get("disable_audio_limiter") is True:
        shifts["audio_clip_gt_096"] = "UP"
        est_delta -= 8.0
        risks.append("Wyłączenie limitera wywoła przestery AAC (>0.96).")
    elif ch.get("alimiter_level_disabled") or (ch.get("alimiter_limit") is not None and float(ch["alimiter_limit"]) <= 0.85):
        if int(b.get("audio_clip_gt_096") or 0) > 0:
            shifts["audio_clip_gt_096"] = "DOWN"
            est_delta += 5.0

    # 5. Hook Synapsy przed renderem / zakaz generyków
    if ch.get("pre_render_synapsa_hook") or ch.get("sanitize_hook_text"):
        if b.get("hook_is_generic", False):
            shifts["hook_is_generic"] = "DOWN"
            est_delta += 5.0
        else:
            shifts["hook_is_generic"] = "SAME"

    # 6. Lead-in do 1. killa
    if ch.get("lead_in_max_s") is not None:
        lim = float(ch["lead_in_max_s"])
        cur_fk = b.get("first_kill_out_sec")
        if cur_fk is not None and lim < float(cur_fk) - 0.3:
            shifts["first_kill_out_sec"] = "DOWN"
            est_delta += 4.5
        elif cur_fk is not None and lim > float(cur_fk) + 1.5:
            shifts["first_kill_out_sec"] = "UP"
            est_delta -= 4.0

    # 7. Kamera Shunpo i margines krawędziowy
    if ch.get("shunpo_edge_guard_px") or ch.get("shunpo_lists_restored") or ch.get("fix_shunpo_camera"):
        if float(b.get("player_edge_clip_ratio") or 0.0) > 0.05:
            shifts["player_edge_clip_ratio"] = "DOWN"
            est_delta += 5.0
        if b.get("camera_peak_step_px") is not None and float(b["camera_peak_step_px"]) > 560.0:
            shifts["camera_peak_step_px"] = "DOWN"
            est_delta += 3.5

    # 8. Historyczne prawa zmian wartości sprzed rozmowy i limit IG Reels
    sw_val = ch.get("smooth_win")
    mp_val = ch.get("max_pan_px")
    la_val = ch.get("lerp_alpha")
    if (
        (sw_val is not None and float(sw_val) > 8.0)
        or (mp_val is not None and 0.0 < float(mp_val) < 50.0)
        or (la_val is not None and (0.0 < float(la_val) < 0.25 or float(la_val) > 0.75))
    ):
        shifts["player_edge_clip_ratio"] = "UP"
        est_delta -= 7.0
        risks.append("Regresja kamery 8f73898/v37: smooth_win>8 lub max_pan<50px spóźnia kadr za dashem (docelowo smooth_win=5, max_pan=80px, lerp=0.45).")

    ef_val = ch.get("end_freeze_sec")
    ml_val = ch.get("min_lead_in_sec")
    ot_val = ch.get("outro_sec")
    if (
        (ef_val is not None and float(ef_val) > 0.8)
        or (ml_val is not None and 0.0 < float(ml_val) < 3.5)
        or (ot_val is not None and float(ot_val) > 2.5)
    ):
        shifts["watchability_score"] = "DOWN"
        est_delta -= 6.5
        risks.append("Regresja timingu 2dbc526: end_freeze>0.8s mrozi koniec przed fragiem, a lead_in<3.5s ucina walkę (docelowo end_freeze<=0.6s, buildup>=4.5s).")

    zm_val = ch.get("zoom_max")
    sl_val = ch.get("slowmo_window_max")
    pac_str = str(ch.get("pacing") or "").lower()
    if (
        (zm_val is not None and float(zm_val) > 1.2)
        or (sl_val is not None and float(sl_val) > 1.5)
        or pac_str.startswith("cinematic")
    ):
        shifts["camera_peak_step_px"] = "UP"
        est_delta -= 6.0
        risks.append("Przekroczenie edit_limits (zoom>1.12, slowmo>0.7s) lub tryb cinematic (1543 views < 1830 w balanced_14_17s).")

    mb_val = ch.get("min_sample_for_bucket")
    sk_val = ch.get("shrink_k")
    if (mb_val is not None and 0.0 < float(mb_val) < 5.0) or (sk_val is not None and float(sk_val) < 3.0):
        shifts["watchability_score"] = "DOWN"
        est_delta -= 5.0
        risks.append("Regresja uczenia 4f0e0a0: min_bucket<5 lub shrink_k<3 zamienia szum małej próby w regułę (docelowo min_bucket=8, shrink_k=10).")

    if (
        ch.get("nvenc_unbounded_cq18") is True
        or float(ch.get("video_bitrate_mbps") or 0.0) > 25.0
        or float(ch.get("audio_bitrate_kbps") or 0.0) > 160.0
        or str(ch.get("fps_mode") or "").lower() == "vfr"
    ):
        shifts["watchability_score"] = "DOWN"
        est_delta -= 9.0
        risks.append("Bitrate >25 Mbps / VFR / audio >160 kbps przekracza limit Instagram Reels i wywołuje ProcessingFailedError na rupload.")

    # Określ kierunek łączny
    pos_metrics = sum(
        1 for k, d in shifts.items()
        if (k in ("frame0_hook_legible", "watchability_score") and d == "UP")
        or (k not in ("frame0_hook_legible", "watchability_score") and d == "DOWN")
    )
    neg_metrics = sum(
        1 for k, d in shifts.items()
        if (k in ("frame0_hook_legible", "watchability_score") and d == "DOWN")
        or (k not in ("frame0_hook_legible", "watchability_score") and d == "UP")
    )

    if pos_metrics > 0 and neg_metrics == 0:
        expected_verdict = "BETTER"
        shifts["watchability_score"] = "UP"
    elif neg_metrics > 0 and pos_metrics == 0:
        expected_verdict = "WORSE"
        shifts["watchability_score"] = "DOWN"
    elif pos_metrics > 0 and neg_metrics > 0:
        expected_verdict = "MIXED"
        shifts["watchability_score"] = "UP" if est_delta >= 2.0 else ("DOWN" if est_delta <= -2.0 else "SAME")
    else:
        expected_verdict = "NO_CHANGE"
        shifts["watchability_score"] = "SAME"
        risks.append("Proponowana zmiana nie dotyka żadnej aktywnej metryki obrazu ani dźwięku.")

    rationale = (
        f"Dedukcja ({expected_verdict}, delta~{est_delta:+.1f} pkt): "
        + (", ".join(f"{k}->{v}" for k, v in shifts.items() if v != "SAME") or "brak wpływu na metryki renderu.")
    )
    src = "synapsa_causal_predictor"

    if use_local_ai:
        gen_fn, avail_fn = _import_synapsa()
        if avail_fn():
            ai_payload = {
                "before": {
                    "score": b.get("watchability_score"),
                    "frame0_legible": b.get("frame0_hook_legible"),
                    "kill_zone": b.get("kill_overlay_zone"),
                    "clip": b.get("audio_clip_gt_096"),
                    "av_delta": b.get("av_delta_s"),
                    "cam_step": b.get("camera_peak_step_px"),
                    "edge_clip": b.get("player_edge_clip_ratio"),
                    "hook_generic": b.get("hook_is_generic"),
                },
                "proposed_changes": ch,
                "rule_verdict": expected_verdict,
                "rule_risks": risks[:3],
            }
            ai_out = gen_fn("predict_change_effect", ai_payload, timeout=120)
            if isinstance(ai_out, dict):
                ai_verdict = str(ai_out.get("expected_verdict") or "").strip().upper()
                ai_rat = str(ai_out.get("deduction_rationale") or "").strip()
                verdict_ok = (not ai_verdict) or (ai_verdict == expected_verdict)
                prose_ok = len(ai_rat) >= 24 and not ai_rat.lower().startswith("test")
                if verdict_ok and prose_ok:
                    rationale = ai_rat
                    if isinstance(ai_out.get("risks"), list):
                        for r in ai_out["risks"]:
                            rs = str(r).strip()
                            if rs and not rs.lower().startswith("test") and rs not in risks:
                                risks.append(rs)
                    src = "synapsa_local_lora_predictor"

    hid = "hyp_" + hashlib.sha1(json.dumps({"b": b.get("filename"), "c": ch}, sort_keys=True, default=str).encode()).hexdigest()[:10]
    return {
        "hypothesis_id": hid,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "expected_verdict": expected_verdict,
        "expected_metric_shifts": shifts,
        "expected_watchability_delta": round(est_delta, 2),
        "risks": risks,
        "deduction_rationale": rationale,
        "source": src,
    }


def _actual_shift(before_val: Any, after_val: Any, tol: float) -> Optional[str]:
    if before_val is None or after_val is None:
        return None
    if isinstance(before_val, bool) and isinstance(after_val, bool):
        if before_val == after_val:
            return "SAME"
        return "UP" if (after_val and not before_val) else "DOWN"
    diff = float(after_val) - float(before_val)
    if abs(diff) <= tol:
        return "SAME"
    return "UP" if diff > 0 else "DOWN"


def verify_prediction(hypothesis: Dict[str, Any], comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Rozlicza trafność dedukcji PRZED zmianą względem realnie zmierzonych zmian PO obejrzeniu filmu."""
    exp_shifts = dict(hypothesis.get("expected_metric_shifts") or {})
    exp_verdict = str(hypothesis.get("expected_verdict") or "NO_CHANGE")
    act_verdict = str(comparison.get("verdict") or "NO_CHANGE")
    b = comparison.get("before") or {}
    a = comparison.get("after") or {}

    tols = {
        "watchability_score": 1.5,
        "frame0_hook_legible": 0.5,
        "center_blocked_kills_ratio": 0.05,
        "player_edge_clip_ratio": 0.03,
        "audio_clip_gt_096": 2.0,
        "av_delta_s": 0.015,
        "camera_peak_step_px": 20.0,
        "first_kill_out_sec": 0.3,
        "hook_is_generic": 0.5,
        "black_end_frame": 0.5,
    }

    checked = 0
    matched = 0
    opposite_hits = 0
    surprises: List[str] = []

    for metric, exp_dir in exp_shifts.items():
        if exp_dir not in ("UP", "DOWN", "SAME"):
            continue
        actual_dir = _actual_shift(b.get(metric), a.get(metric), tols.get(metric, 0.05))
        if actual_dir is None:
            continue
        checked += 1
        if actual_dir == exp_dir:
            matched += 1
        elif exp_dir in ("UP", "DOWN") and actual_dir in ("UP", "DOWN") and actual_dir != exp_dir:
            opposite_hits += 1
            surprises.append(f"{metric}: oczekiwano {exp_dir}, zmierzono {actual_dir} ({b.get(metric)}->{a.get(metric)})")
        elif exp_dir in ("UP", "DOWN") and actual_dir == "SAME":
            surprises.append(f"{metric}: oczekiwano {exp_dir}, brak zmiany ({b.get(metric)}->{a.get(metric)})")

    # Wykryj też duże nieprzewidziane skoki poza listą hipotezy
    for m_key, tol in tols.items():
        if m_key not in exp_shifts:
            ad = _actual_shift(b.get(m_key), a.get(m_key), tol)
            if ad in ("UP", "DOWN"):
                surprises.append(f"nieoczekiwana zmiana {m_key}: {b.get(m_key)}->{a.get(m_key)}")

    acc = round(matched / checked, 3) if checked else (1.0 if act_verdict == exp_verdict else 0.0)

    if act_verdict == "NO_CHANGE" and exp_verdict != "NO_CHANGE":
        status = "NO_EFFECT"
    elif (act_verdict == "WORSE" and exp_verdict == "BETTER") or (act_verdict == "BETTER" and exp_verdict == "WORSE") or opposite_hits > matched:
        status = "REFUTED"
    elif act_verdict == exp_verdict and acc >= 0.65 and opposite_hits == 0:
        status = "CONFIRMED"
    else:
        status = "PARTIAL"

    return {
        "hypothesis_id": hypothesis.get("hypothesis_id"),
        "expected_verdict": exp_verdict,
        "actual_verdict": act_verdict,
        "hypothesis_status": status,
        "checked_metrics": checked,
        "matched_metrics": matched,
        "prediction_accuracy": acc,
        "surprises": surprises[:8],
    }


def compare_shorts_and_verify(
    before_mp4: str,
    after_mp4: str,
    hypothesis: Optional[Dict[str, Any]] = None,
    proposed_changes: Optional[Dict[str, Any]] = None,
    use_local_ai: bool = True,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Ogląda oba shortsy (`before_mp4` vs `after_mp4`), porównuje piksel-po-pikselu i dźwiękowo,
    orzeka `BETTER` / `WORSE` / `NO_CHANGE` / `MIXED` i rozlicza wcześniejszą hipotezę Synapsy.
    """
    rubric = load_watchability_rubric()
    nc = rubric["no_change_thresholds"]
    vt = rubric["verdict_thresholds"]

    b = inspect_rendered_short(before_mp4)
    if hypothesis is None and proposed_changes is not None:
        hypothesis = predict_change_effect(b, proposed_changes, use_local_ai=use_local_ai)
    a = inspect_rendered_short(after_mp4)
    vis_diff = _compute_visual_frame_diff(before_mp4, after_mp4)

    delta_watch = round(float(a["watchability_score"]) - float(b["watchability_score"]), 2)
    delta_dur = round(float(a["video_dur_s"]) - float(b["video_dur_s"]), 3)
    delta_clip = int(a["audio_clip_gt_096"]) - int(b["audio_clip_gt_096"])
    delta_av = round(float(a["av_delta_s"]) - float(b["av_delta_s"]), 3)

    metric_deltas: Dict[str, Any] = {
        "watchability_score": delta_watch,
        "video_dur_s": delta_dur,
        "audio_clip_gt_096": delta_clip,
        "av_delta_s": delta_av,
        "center_blocked_kills_ratio": round(float(a["center_blocked_kills_ratio"]) - float(b["center_blocked_kills_ratio"]), 3),
        "player_edge_clip_ratio": round(float(a["player_edge_clip_ratio"]) - float(b["player_edge_clip_ratio"]), 3),
    }
    if b.get("camera_peak_step_px") is not None and a.get("camera_peak_step_px") is not None:
        metric_deltas["camera_peak_step_px"] = round(float(a["camera_peak_step_px"]) - float(b["camera_peak_step_px"]), 1)
    if b.get("first_kill_out_sec") is not None and a.get("first_kill_out_sec") is not None:
        metric_deltas["first_kill_out_sec"] = round(float(a["first_kill_out_sec"]) - float(b["first_kill_out_sec"]), 2)

    improvements: List[str] = []
    regressions: List[str] = []
    unchanged: List[str] = []
    major_imp, major_reg, critical_reg = 0, 0, False

    def _pair_bool(field: str, good_when_true: bool, weight_major: bool = True, critical_drop: bool = False):
        nonlocal major_imp, major_reg, critical_reg
        bv, av = bool(b.get(field)), bool(a.get(field))
        if bv == av:
            unchanged.append(f"{field}={av}")
            return
        improved = (av and good_when_true) or (not av and not good_when_true)
        tag = f"{field}: {bv} -> {av}"
        if improved:
            improvements.append(tag)
            if weight_major:
                major_imp += 1
        else:
            regressions.append(tag)
            if weight_major:
                major_reg += 1
            if critical_drop:
                critical_reg = True

    _pair_bool("frame0_hook_legible", good_when_true=True, critical_drop=True)
    _pair_bool("hook_is_generic", good_when_true=False)
    _pair_bool("black_end_frame", good_when_true=False, critical_drop=True)

    # Strefa napisów killi
    bz, az = b.get("kill_overlay_zone"), a.get("kill_overlay_zone")
    if bz == "center_blocking" and az != "center_blocking":
        improvements.append(f"kill_overlay_zone: {bz} -> {az}")
        major_imp += 1
    elif bz != "center_blocking" and az == "center_blocking":
        regressions.append(f"kill_overlay_zone: {bz} -> {az}")
        major_reg += 1
        critical_reg = True
    elif bz == az:
        unchanged.append(f"kill_overlay_zone={az}")

    # Clipping audio
    if delta_clip <= -5:
        improvements.append(f"audio_clip_gt_096: {b['audio_clip_gt_096']} -> {a['audio_clip_gt_096']}")
        if abs(delta_clip) >= 10:
            major_imp += 1
    elif delta_clip >= 5:
        regressions.append(f"audio_clip_gt_096: {b['audio_clip_gt_096']} -> {a['audio_clip_gt_096']}")
        major_reg += 1
        if delta_clip >= int(vt["critical_clip_increase"]):
            critical_reg = True

    # Synchronizacja A/V
    if delta_av <= -0.025:
        improvements.append(f"av_delta_s: {b['av_delta_s']} -> {a['av_delta_s']}")
        major_imp += 1
    elif delta_av >= 0.025:
        regressions.append(f"av_delta_s: {b['av_delta_s']} -> {a['av_delta_s']}")
        major_reg += 1

    # Krawędzie gracza
    dec_edge = float(metric_deltas["player_edge_clip_ratio"])
    if dec_edge <= -0.04:
        improvements.append(f"player_edge_clip_ratio: {b['player_edge_clip_ratio']} -> {a['player_edge_clip_ratio']}")
        major_imp += 1
    elif dec_edge >= 0.04:
        regressions.append(f"player_edge_clip_ratio: {b['player_edge_clip_ratio']} -> {a['player_edge_clip_ratio']}")
        major_reg += 1

    # Kamera step px
    if "camera_peak_step_px" in metric_deltas:
        dc = float(metric_deltas["camera_peak_step_px"])
        if dc <= -40.0:
            improvements.append(f"camera_peak_step_px: {b['camera_peak_step_px']} -> {a['camera_peak_step_px']}")
            major_imp += 1
        elif dc >= 40.0 and float(a["camera_peak_step_px"]) > float(vt["acceptable_shunpo_step_px"]):
            regressions.append(f"camera_peak_step_px: {b['camera_peak_step_px']} -> {a['camera_peak_step_px']}")
            major_reg += 1

    # Pacing: czas do 1. killa
    if "first_kill_out_sec" in metric_deltas:
        df = float(metric_deltas["first_kill_out_sec"])
        if df <= -0.5:
            improvements.append(f"first_kill_out_sec: {b['first_kill_out_sec']} -> {a['first_kill_out_sec']}")
            major_imp += 1
        elif df >= 0.8 and float(a["first_kill_out_sec"]) > 5.2:
            regressions.append(f"first_kill_out_sec: {b['first_kill_out_sec']} -> {a['first_kill_out_sec']}")
            major_reg += 1

    # Czy faktycznie zaszła jakakolwiek realna zmiana?
    no_real_change = (
        vis_diff["mean_frame_mad"] < float(nc["mean_frame_mad_lt"])
        and vis_diff["changed_frames_ratio"] < float(nc["changed_frames_ratio_lt"])
        and abs(delta_watch) < float(nc["abs_delta_watchability_lt"])
        and abs(delta_dur) < float(nc["abs_delta_dur_lt"])
        and abs(delta_clip) <= int(nc["abs_delta_clip_lte"])
        and abs(delta_av) < float(nc["abs_delta_av_lt"])
        and not improvements
        and not regressions
    )

    if no_real_change:
        verdict = "NO_CHANGE"
        actually_changed = False
    elif critical_reg and major_imp == 0:
        verdict = "WORSE"
        actually_changed = True
    elif major_imp > 0 and major_reg > 0 and abs(delta_watch) < 4.5:
        verdict = "MIXED"
        actually_changed = True
    elif delta_watch >= float(vt["better_delta_min"]) and not critical_reg and major_imp >= major_reg:
        verdict = "BETTER"
        actually_changed = True
    elif delta_watch <= float(vt["worse_delta_max"]) or critical_reg:
        verdict = "WORSE"
        actually_changed = True
    elif improvements and not regressions:
        verdict = "BETTER"
        actually_changed = True
    elif regressions and not improvements:
        verdict = "WORSE"
        actually_changed = True
    else:
        verdict = "MIXED"
        actually_changed = True

    result: Dict[str, Any] = {
        "verdict": verdict,
        "actually_changed": actually_changed,
        "delta_watchability": delta_watch,
        "visual_diff": vis_diff,
        "metric_deltas": metric_deltas,
        "improvements": improvements,
        "regressions": regressions,
        "unchanged": unchanged,
        "before": b,
        "after": a,
        "hypothesis": hypothesis,
        "verification": None,
        "watchability_summary": (
            f"{verdict}: watchability {b['watchability_score']}->{a['watchability_score']} ({delta_watch:+.1f}), "
            f"MAD={vis_diff['mean_frame_mad']}. Plusy: {len(improvements)}, Regresje: {len(regressions)}."
        ),
        "next_fix": (regressions[0] if regressions else ("none" if verdict in ("BETTER", "NO_CHANGE") else "")),
        "source": "synapsa_watchability_judge",
    }

    if hypothesis is not None:
        result["verification"] = verify_prediction(hypothesis, result)

    if use_local_ai:
        gen_fn, avail_fn = _import_synapsa()
        if avail_fn():
            ai_req = {
                "verdict": verdict,
                "actually_changed": actually_changed,
                "delta_watchability": delta_watch,
                "mean_frame_mad": vis_diff["mean_frame_mad"],
                "improvements": improvements[:5],
                "regressions": regressions[:5],
                "hypothesis_status": (result["verification"] or {}).get("hypothesis_status"),
            }
            ai_res = gen_fn("watchability_compare", ai_req, timeout=120)
            if isinstance(ai_res, dict):
                ai_v = str(ai_res.get("verdict") or "").strip().upper()
                ai_sum = str(ai_res.get("watchability_summary") or "").strip()
                ai_fix = str(ai_res.get("next_fix") or "").strip()
                v_ok = (not ai_v) or (ai_v == verdict)
                s_ok = len(ai_sum) >= 24 and not ai_sum.lower().startswith("test")
                if v_ok and s_ok:
                    result["watchability_summary"] = ai_sum
                    if ai_fix and not ai_fix.lower().startswith("test"):
                        result["next_fix"] = ai_fix
                    result["source"] = "synapsa_local_lora_judge"

    target_log = Path(log_path) if log_path is not None else (None if os.environ.get("PYTEST_CURRENT_TEST") else DEFAULT_VERIFICATION_LOG)
    if target_log is not None:
        try:
            target_log.parent.mkdir(parents=True, exist_ok=True)
            log_rec = {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "before_file": b["filename"],
                "after_file": a["filename"],
                "action_type": a["action_type"],
                "verdict": verdict,
                "actually_changed": actually_changed,
                "before_score": b["watchability_score"],
                "after_score": a["watchability_score"],
                "delta_watchability": delta_watch,
                "mean_frame_mad": vis_diff["mean_frame_mad"],
                "improvements": improvements,
                "regressions": regressions,
                "proposed_changes": proposed_changes or {},
                "expected_verdict": (hypothesis or {}).get("expected_verdict"),
                "hypothesis_status": (result.get("verification") or {}).get("hypothesis_status"),
            }
            with open(target_log, "a", encoding="utf-8") as lf:
                lf.write(json.dumps(log_rec, ensure_ascii=False) + "\n")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Synapsa Watchability Judge & Hypothesis Verifier")
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--changes-json", default="{}")
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args()
    ch_obj = json.loads(args.changes_json) if args.changes_json else {}
    rep = compare_shorts_and_verify(
        args.before,
        args.after,
        proposed_changes=ch_obj or None,
        use_local_ai=not args.no_ai,
    )
    compact = {k: v for k, v in rep.items() if k not in ("before", "after")}
    compact["before_score"] = rep["before"]["watchability_score"]
    compact["after_score"] = rep["after"]["watchability_score"]
    print(json.dumps(compact, indent=2, ensure_ascii=False))
