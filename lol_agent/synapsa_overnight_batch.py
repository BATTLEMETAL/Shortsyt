"""
LOL Agent / Synapsa — Tryb Nocny („Opcja Nocna”: Skan -> Top 5 Montaży -> Rekomendacja)
========================================================================================
Skanuje wszystkie nieopublikowane klipy w folderze nagrań (Outplayed / Medal / custom),
bezwzględnie odrzuca przeciętne i puste klipy, wybiera 5 najbardziej hypowanych akcji,
montuje wszystkie 5 lokalnie pełnym pipeline'em (ZERO auto-uploadu), bada oglądalność
każdego gotowego shorta (`inspect_rendered_short` + `ffprobe`) i wyłania finalną
rekomendację Synapsy `#1` (`PICK_WINNER`) w trybie `Sykofankcja 0`.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

LOL_AGENT_DIR = Path(__file__).resolve().parent
OVERNIGHT_DIR = LOL_AGENT_DIR / "overnight_batches"
LATEST_BATCH_FILE = OVERNIGHT_DIR / "latest_batch.json"
SCAN_CACHE_FILE = LOL_AGENT_DIR / "overnight_scan_cache.json"
SCAN_CACHE_SCHEMA_VERSION = 3

TIER_FILTER_MIN_RANK: Dict[str, int] = {
    "auto": -1,
    "all": -1,
    "any_kill": 1,
    "double_plus": 2,
    "triple_plus": 3,
    "quadra_plus": 4,
}
_TIER_BY_RANK: Dict[int, str] = {
    0: "assist_only",
    1: "single_kill",
    2: "double",
    3: "triple",
    4: "quadrakill",
    5: "pentakill",
}
_BANNER_BY_RANK: Dict[int, str] = {
    1: "KILL",
    2: "DOUBLE KILL",
    3: "TRIPLE KILL",
    4: "QUADRA KILL",
    5: "PENTA KILL",
}

_OVERNIGHT_LOCK = threading.Lock()
_MANIFEST_LOCK = threading.Lock()
_OVERNIGHT_CANCEL = threading.Event()
_OVERNIGHT_THREAD: Optional[threading.Thread] = None

_OVERNIGHT_STATE: Dict[str, Any] = {
    "status": "idle",  # idle | scanning | rendering | evaluating | done | error | stopped
    "batch_id": None,
    "phase": "Oczekuje",
    "progress": 0,
    "total_clips": 0,
    "scanned_clips": 0,
    "skipped_published": 0,
    "qualified_count": 0,
    "rejected_count": 0,
    "selected_count": 0,
    "rendered_count": 0,
    "current_clip": "",
    "recommended_filename": None,
    "summary_pl": "",
    "error": None,
    "started_at": None,
    "finished_at": None,
    "logs": [],
}

_ACTION_BASE_HYPE: Dict[str, float] = {
    "pentakill": 86.0,
    "quadrakill": 78.0,
    "triple": 68.0,
    "double": 54.0,
    "clutch": 52.0,
    "solo_bolo": 38.0,
    "outplay": 34.0,
}

_VERDICT_CRITICAL_REASONS = (
    "black_end_frame",
    "frame0_hook_illegible",
    "audio_clipping_gt_10",
    "av_desync_gt_025s",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, text: str) -> None:
    """Atomowo zapisuje tekst UTF-8 przez plik tymczasowy w tym samym katalogu i os.replace."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _update_overnight_state(**kwargs: Any) -> None:
    log_line = kwargs.pop("log", None)
    with _OVERNIGHT_LOCK:
        _OVERNIGHT_STATE.update(kwargs)
        if log_line:
            ts = datetime.now().strftime("%H:%M:%S")
            _OVERNIGHT_STATE["logs"].append(f"[{ts}] {log_line}")
            _OVERNIGHT_STATE["logs"] = _OVERNIGHT_STATE["logs"][-60:]


def get_overnight_status() -> Dict[str, Any]:
    """Zwraca wątkowo-bezpieczną kopię aktualnego statusu trybu nocnego."""
    with _OVERNIGHT_LOCK:
        return {**_OVERNIGHT_STATE, "logs": list(_OVERNIGHT_STATE["logs"])}


def stop_overnight_batch() -> bool:
    """Przerywa trwającą sesję trybu nocnego (gdy aktywna) i zatrzymuje aktywny render FFmpeg."""
    with _OVERNIGHT_LOCK:
        if _OVERNIGHT_STATE.get("status") not in ("scanning", "rendering", "evaluating"):
            return False
        _OVERNIGHT_CANCEL.set()
        _OVERNIGHT_STATE["phase"] = "Zatrzymywanie..."
        ts = datetime.now().strftime("%H:%M:%S")
        _OVERNIGHT_STATE["logs"].append(f"[{ts}] Zażądano zatrzymania trybu nocnego.")
        _OVERNIGHT_STATE["logs"] = _OVERNIGHT_STATE["logs"][-60:]

    try:
        from lol_agent.api import pipeline_runner
    except ImportError:
        from api import pipeline_runner  # type: ignore
    try:
        pipeline_runner.stop_pipeline(clear_queue=True)
    except Exception:
        pass
    return True


_DEFAULT_PROD_SCAN_CACHE = LOL_AGENT_DIR / "overnight_scan_cache.json"


def _is_blocked_test_cache_write() -> bool:
    try:
        return bool(os.environ.get("PYTEST_CURRENT_TEST")) and SCAN_CACHE_FILE.resolve() == _DEFAULT_PROD_SCAN_CACHE.resolve()
    except Exception:
        return False


def _load_scan_cache() -> Dict[str, Any]:
    if _is_blocked_test_cache_write() or not SCAN_CACHE_FILE.is_file():
        return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}
    try:
        data = json.loads(SCAN_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema") == SCAN_CACHE_SCHEMA_VERSION:
            entries = data.get("entries")
            if isinstance(entries, dict):
                return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": entries}
    except Exception:
        pass
    return {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}


def _save_scan_cache(cache_data: Dict[str, Any]) -> None:
    if _is_blocked_test_cache_write():
        return
    try:
        entries = cache_data.get("entries") or {}
        if len(entries) > 600:
            # Zachowaj ostatnie 600 wpisów bez rozrastania JSON-a w nieskończoność
            trimmed = dict(list(entries.items())[-600:])
            cache_data = {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": trimmed}
        _atomic_write_text(SCAN_CACHE_FILE, json.dumps(cache_data, indent=2, ensure_ascii=False))
    except Exception:
        pass


def _cache_key_for(path: str, size_bytes: int, mtime_sec: float) -> str:
    return f"{Path(path).resolve()}|{int(size_bytes)}|{int(mtime_sec)}|{SCAN_CACHE_SCHEMA_VERSION}"


def _check_trailing_survival(video_path: str, clip_end: float, fps: float) -> bool:
    """
    Sprawdza w ostatnich 2.2s okna klipu czy gracz przeżył.
    Wspiera zarówno Standard Mode (zielony pasek HP), jak i Colorblind (złoty) + dolny HUD.
    """
    cap = None
    try:
        try:
            from lol_agent.autonomous.evaluator import _player_hp_mask
            from lol_agent.lol_frag_detector import _measure_player_hp
        except ImportError:
            from autonomous.evaluator import _player_hp_mask  # type: ignore
            from lol_frag_detector import _measure_player_hp  # type: ignore

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        v_fps = fps if fps > 0 else (cap.get(cv2.CAP_PROP_FPS) or 30.0)
        end_t = max(1.5, float(clip_end))
        start_t = max(0.0, end_t - 2.2)

        hp_px_counts: List[int] = []
        hud_hp_vals: List[float] = []
        saturations: List[float] = []

        for t in np.linspace(start_t, max(start_t + 0.1, end_t - 0.15), 5):
            f_idx = min(max(0, total_frames - 1), int(float(t) * v_fps))
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            hp_px_counts.append(int(np.count_nonzero(_player_hp_mask(frame))))
            hud_hp = _measure_player_hp(frame)
            if hud_hp is not None:
                hud_hp_vals.append(float(hud_hp))
            h_f, w_f = frame.shape[:2]
            roi = frame[int(h_f * 0.2):int(h_f * 0.8), int(w_f * 0.2):int(w_f * 0.8)]
            if roi.size > 0:
                hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                saturations.append(float(np.mean(hsv[:, :, 1])))

        has_world_hp = bool(hp_px_counts) and max(hp_px_counts) >= 6
        has_hud_hp = bool(hud_hp_vals) and max(hud_hp_vals) >= 4.0
        tail_gray = len(saturations) >= 2 and all(s < 38.0 for s in saturations[-2:])
        if tail_gray:
            return True
        return not (has_world_hp or has_hud_hp)
    except Exception:
        return False
    finally:
        if cap is not None:
            cap.release()


def _normalize_action_type_in_window(
    raw_detected_frag_type: str,
    kills_in_win: List[Dict[str, Any]],
    is_clutch: bool,
) -> str:
    """Klasyfikuje akcję wyłącznie po banerach/zabójstwach mieszczących się w oknie shorta."""
    det = str(raw_detected_frag_type or "outplay").lower().strip()
    n_k = len(kills_in_win)
    max_tier = max([int(k.get("tier", 0) or 0) for k in kills_in_win], default=0)
    if max_tier >= 5:
        return "pentakill"
    if max_tier == 4:
        return "quadrakill"
    if max_tier == 3:
        return "triple"
    if max_tier == 2:
        return "double"
    if is_clutch and n_k >= 1:
        return "clutch"
    if det == "solo_bolo" or any(str(k.get("label") or "").upper() == "FIRST BLOOD" for k in kills_in_win):
        return "solo_bolo"
    return "outplay"


def _score_and_classify_candidate(raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Przelicza klasyfikację okienkową, filtrację i hype_score na surowym lub zcache'owanym wpisie."""
    entry = dict(raw_entry)
    if entry.get("rejection_code") in (
        "REJECT_UNREADABLE",
        "REJECT_LOW_TECH",
        "REJECT_ASSIST_ONLY",
        "REJECT_WRONG_CHAMPION",
        "REJECT_TIER_FILTER",
        "REJECT_SINGLE_KILL_MULTIKILLS_AVAILABLE",
    ):
        return entry

    clip_start = float(entry.get("clip_start") or 0.0)
    clip_end = float(entry.get("clip_end") or 0.0)
    window_dur = max(1.0, round(clip_end - clip_start, 2))
    raw_kills = list(entry.get("kills") or [])

    kills_in_win = [
        k for k in raw_kills
        if (clip_start - 0.6) <= float(k.get("timestamp", 0.0)) <= (clip_end + 0.6)
    ]
    kill_count_in_win = len(kills_in_win)
    ts_in_win = sorted(float(k.get("timestamp", 0.0)) for k in kills_in_win)
    kill_span_s = round(max(0.0, ts_in_win[-1] - ts_in_win[0]), 2) if len(ts_in_win) >= 2 else 0.0
    first_kill_offset_s = round(max(0.0, ts_in_win[0] - clip_start), 2) if ts_in_win else round(window_dur, 2)

    is_clutch = bool(entry.get("is_clutch_1hp"))
    raw_det = str(entry.get("raw_detected_frag_type") or entry.get("action_type") or "outplay").lower().strip()
    action_type = _normalize_action_type_in_window(raw_det, kills_in_win, is_clutch)

    event_source = str(entry.get("event_source") or "")
    outplayed_rank_raw = entry.get("event_tier_rank")
    outplayed_rank = int(outplayed_rank_raw) if isinstance(outplayed_rank_raw, (int, float)) else None
    is_outplayed = event_source.startswith("outplayed_")
    if is_outplayed and outplayed_rank is not None:
        if outplayed_rank >= 2:
            action_type = _TIER_BY_RANK.get(min(5, outplayed_rank), action_type)
            kill_count_in_win = max(kill_count_in_win, outplayed_rank)
        elif outplayed_rank == 1 and action_type in ("double", "triple", "quadrakill", "pentakill"):
            # Riot API widzi pojedynczego killa -> zapobiegaj halucynacji OCR multikilla
            action_type = "clutch" if is_clutch else "solo_bolo"
            kill_count_in_win = max(1, min(kill_count_in_win, 1))

    objective_secured = bool(entry.get("objective_secured"))
    min_hp = float(entry.get("min_hp_percentage") if entry.get("min_hp_percentage") is not None else 100.0)
    conf = float(entry.get("confidence") or 0.0)
    ally_blocked = bool(entry.get("ally_banner_blocked"))
    player_died = bool(entry.get("player_died"))
    raw_ok = bool(entry.get("raw_viable", True))
    raw_reason = str(entry.get("raw_reason") or "")
    raw_code = entry.get("raw_code")
    is_favorite = bool(entry.get("is_favorite"))
    total_kills_in_clip = int(entry.get("total_kills_in_clip") or 0)

    base_key = action_type if kill_count_in_win > 0 else "outplay"
    hype = _ACTION_BASE_HYPE.get(base_key, 34.0) if kill_count_in_win > 0 else 10.0
    if objective_secured:
        hype += 10.0
    if is_clutch or min_hp <= 20.0:
        hype += 9.0
    elif min_hp <= 35.0 and kill_count_in_win >= 1:
        hype += 4.0
    if is_favorite:
        hype += 14.0
    if total_kills_in_clip >= 4:
        hype += 4.0
    if kill_count_in_win >= 3 and kill_span_s <= 6.5:
        hype += 6.0
    elif kill_count_in_win == 2 and kill_span_s <= 3.0:
        hype += 5.0
    if conf >= 0.85 and not ally_blocked and kill_count_in_win >= 1:
        hype += 4.0
    if 10.0 <= window_dur <= 24.0 and kill_count_in_win >= 1:
        hype += 3.0

    if player_died:
        hype -= 18.0
    if ally_blocked:
        hype -= 3.0
    if window_dur > 32.0:
        hype -= 10.0
    elif window_dur < 6.0:
        hype -= 6.0
    if first_kill_offset_s > 6.0 and not objective_secured and not is_outplayed:
        hype -= 10.0

    rejection_code: Optional[str] = None
    rejection_reason = ""
    fallback_eligible = False

    if kill_count_in_win == 0 and not objective_secured:
        rejection_code = "REJECT_NO_KILLS"
        rejection_reason = "Brak potwierdzonych zabójstw OCR w oknie klipu i brak zabezpieczonego obiektu"
        hype = min(hype, 15.0)
    elif player_died and kill_count_in_win <= 2 and not objective_secured:
        rejection_code = "REJECT_DIED_LOW_IMPACT"
        rejection_reason = f"Gracz zginął na końcu akcji przy zaledwie {kill_count_in_win} kill(ach) w oknie"
        hype = min(hype, 24.0)
    elif window_dur > 28.0 and kill_count_in_win <= 1 and not objective_secured:
        rejection_code = "REJECT_WALKING_SIM"
        rejection_reason = f"Rozwleczony klip ({window_dur:.1f}s) z {kill_count_in_win} killem — symulator chodzenia"
        hype = min(hype, 28.0)
    elif (not is_outplayed) and kill_count_in_win >= 3 and conf < 0.45 and ally_blocked:
        rejection_code = "REJECT_LOW_CONFIDENCE"
        rejection_reason = f"Podejrzany OCR multikilla przy zablokowanym banerze sojusznika (conf={conf:.2f})"
        hype = min(hype, 35.0)
    elif kill_count_in_win == 1 and not is_clutch and min_hp > 25.0 and not objective_secured:
        rejection_code = "REJECT_MEDIOCRE_1KILL"
        rejection_reason = f"Przeciętny pojedynczy kill bez clutcha (min_HP={min_hp:.0f}%, brak obiektu)"
        hype = min(hype, 42.0)
        fallback_eligible = raw_ok
    elif (not is_outplayed or (outplayed_rank or 0) < 2) and (not raw_ok and kill_count_in_win <= 1 and not objective_secured):
        rejection_code = str(raw_code or "REJECT_RAW_GATE")
        rejection_reason = str(raw_reason or "Odrzucono przez bramkę jakości surowca")
        hype = min(hype, 38.0)

    hype_score = round(max(0.0, min(100.0, hype)), 1)
    qualified = rejection_code is None

    hook_text = str(entry.get("hook_text") or "").strip()
    hk_up = hook_text.upper()
    if action_type not in ("pentakill",) and "PENTA" in hk_up:
        hook_text = ""
    if action_type not in ("pentakill", "quadrakill") and "QUADRA" in hk_up:
        hook_text = ""
    if action_type in ("triple", "quadrakill", "pentakill") and "DOUBLE" in hk_up:
        hook_text = ""
    if action_type in ("double", "quadrakill", "pentakill") and "TRIPLE" in hk_up:
        hook_text = ""

    entry.update({
        "raw_detected_frag_type": raw_det,
        "action_type": action_type,
        "kill_count": kill_count_in_win,
        "kill_count_total_file": len(raw_kills),
        "kills_in_window": kills_in_win,
        "kill_span_s": kill_span_s,
        "first_kill_offset_s": first_kill_offset_s,
        "window_dur": window_dur,
        "hook_text": hook_text,
        "hype_score": hype_score,
        "qualified": qualified,
        "fallback_eligible": fallback_eligible,
        "fallback_mediocre": False,
        "rejection_code": rejection_code,
        "rejection_reason": rejection_reason,
    })
    return entry


def _apply_outplayed_anchor(
    clip_info: Dict[str, Any],
    raw_kills: List[Dict[str, Any]],
    raw_det: str,
    clip_start: float,
    clip_end: float,
    peak_moment: float,
    combat_segs: Optional[List[Tuple[float, float]]],
    duration: float,
) -> Tuple[List[Dict[str, Any]], str, float, float, float, Optional[List[Tuple[float, float]]]]:
    """Kotwiczy okno montażowe do znacznika Riot API z Outplayed przy multikillu lub długim klipie."""
    event_source = str(clip_info.get("event_source") or "")
    best_t = clip_info.get("best_event_time_s")
    tier_rank = clip_info.get("event_tier_rank")
    if (
        not event_source.startswith("outplayed_")
        or best_t is None
        or not isinstance(tier_rank, (int, float))
        or int(tier_rank) < 2
    ):
        return raw_kills, raw_det, clip_start, clip_end, peak_moment, combat_segs

    t_ev = max(0.0, min(duration, float(best_t)))
    t_rank = int(tier_rank)
    event_tier = str(clip_info.get("event_tier") or _TIER_BY_RANK.get(t_rank, raw_det))

    ocr_in_win = [
        k for k in raw_kills
        if (clip_start - 0.6) <= float(k.get("timestamp", 0.0)) <= (clip_end + 0.6)
    ]
    ocr_max_tier = max([int(k.get("tier") or 0) for k in ocr_in_win], default=0)
    window_covers_peak = (
        (clip_start + 1.5 <= t_ev <= clip_end - 1.0)
        and (clip_end - clip_start) <= 28.0
        and ocr_max_tier >= t_rank
    )
    if window_covers_peak:
        return raw_kills, event_tier, clip_start, clip_end, peak_moment, combat_segs

    events_summary = clip_info.get("events_summary")
    best_past_s = clip_info.get("best_event_past_s")
    best_future_s = clip_info.get("best_event_future_s")
    est_first_kill_s = clip_info.get("est_first_kill_s")
    est_last_kill_s = clip_info.get("est_last_kill_s")
    if (events_summary is None or est_last_kill_s is None) and clip_info.get("path"):
        try:
            try:
                from lol_agent.outplayed_db import get_outplayed_clip_info
            except ImportError:
                from outplayed_db import get_outplayed_clip_info  # type: ignore
            full_op = get_outplayed_clip_info(str(clip_info["path"]))
            if full_op:
                events_summary = events_summary if events_summary is not None else full_op.get("events_summary")
                best_past_s = best_past_s if best_past_s is not None else full_op.get("best_event_past_s")
                best_future_s = best_future_s if best_future_s is not None else full_op.get("best_event_future_s")
                est_first_kill_s = est_first_kill_s if est_first_kill_s is not None else full_op.get("est_first_kill_s")
                est_last_kill_s = est_last_kill_s if est_last_kill_s is not None else full_op.get("est_last_kill_s")
        except Exception:
            pass

    kill_times = sorted(
        float(ev["time_s"])
        for ev in (events_summary or [])
        if isinstance(ev, dict)
        and ev.get("type") == "kill"
        and isinstance(ev.get("time_s"), (int, float))
        and float(ev["time_s"]) <= t_ev + 0.5
    )
    burst: List[float] = [t_ev]
    for kt in reversed(kill_times):
        if kt >= burst[0] - 0.25:
            continue
        if (burst[0] - kt) <= 10.5 and (t_ev - kt) <= 18.0:
            burst.insert(0, kt)
        else:
            break

    anchor_end_k = max(t_ev, float(est_last_kill_s)) if isinstance(est_last_kill_s, (int, float)) else t_ev
    anchor_end_k = min(duration, anchor_end_k)

    burst_first = burst[0]
    anchor_start_k = (
        min(burst_first, float(est_first_kill_s))
        if isinstance(est_first_kill_s, (int, float))
        else burst_first
    )
    if anchor_start_k < anchor_end_k - 1.0 and burst_first < t_ev - 1.0:
        new_start = max(0.0, anchor_start_k - 3.5)
    elif isinstance(est_first_kill_s, (int, float)) and float(est_first_kill_s) < anchor_end_k - 1.5:
        new_start = max(0.0, float(est_first_kill_s) - 4.5)
    else:
        default_lead = 11.0 if t_rank >= 4 else (9.0 if t_rank == 3 else 8.0)
        lead = float(best_past_s) if isinstance(best_past_s, (int, float)) and float(best_past_s) > 0 else default_lead
        max_lead = 11.5 if t_rank >= 4 else 9.5
        lead = max(7.0, min(max_lead, lead))
        new_start = max(0.0, t_ev - lead)

    is_merged_est = isinstance(est_last_kill_s, (int, float)) and float(est_last_kill_s) > t_ev + 0.5
    tail_s = 2.0 if is_merged_est else max(2.8, min(4.2, float(best_future_s) if isinstance(best_future_s, (int, float)) and float(best_future_s) > 0 else 3.2))
    new_end = min(duration, max(new_start + 10.0, anchor_end_k + tail_s))
    if new_end - new_start > 24.0:
        new_start = max(0.0, new_end - 22.0)

    anchored_peak_t = min(max(new_start + 0.5, anchor_end_k), new_end - 0.8)

    filtered_segs: Optional[List[Tuple[float, float]]] = None
    if combat_segs:
        segs = [
            (max(new_start, float(s[0])), min(new_end, float(s[1])))
            for s in combat_segs
            if float(s[1]) > new_start + 0.5 and float(s[0]) < new_end - 0.5
        ]
        if segs:
            filtered_segs = [(round(a, 2), round(b, 2)) for a, b in segs if b - a >= 1.5] or None

    # Uzupełnij listę zabójstw w zakotwiczonym oknie znacznikami Riot API, jeśli OCR nie trafił klatek
    anchored_ocr = [
        k for k in raw_kills
        if (new_start - 0.5) <= float(k.get("timestamp", 0.0)) <= (new_end + 0.5)
    ]
    ocr_anch_max = max([int(k.get("tier") or 0) for k in anchored_ocr], default=0)
    merged_kills = list(raw_kills)
    if ocr_anch_max < t_rank or len(anchored_ocr) < min(t_rank, 2):
        # Dodaj brakujące punkty Riot w nowym oknie, unikając duplikatów <1.0s
        op_points: List[Tuple[float, int]] = []
        in_win_kt = [kt for kt in kill_times if new_start - 0.3 <= kt <= new_end + 0.3]
        for idx_kt, kt in enumerate(in_win_kt):
            is_peak = abs(kt - t_ev) <= 0.4
            op_points.append((round(kt, 2), t_rank if is_peak else min(t_rank, idx_kt + 1)))
        if not any(abs(pt[0] - anchored_peak_t) <= 0.5 for pt in op_points):
            op_points.append((round(anchored_peak_t, 2), t_rank))
        for pt_t, pt_tier in op_points:
            near_idx = next(
                (i for i, k in enumerate(merged_kills) if abs(float(k.get("timestamp", -99.0)) - pt_t) <= 1.0),
                None,
            )
            banner_lbl = _BANNER_BY_RANK.get(pt_tier, "KILL")
            if near_idx is not None:
                if int(merged_kills[near_idx].get("tier") or 0) < pt_tier:
                    merged_kills[near_idx] = {
                        **merged_kills[near_idx],
                        "tier": pt_tier,
                        "label": banner_lbl,
                        "source": event_source,
                    }
            else:
                merged_kills.append({
                    "timestamp": pt_t,
                    "tier": pt_tier,
                    "label": banner_lbl,
                    "confidence": 0.96,
                    "source": event_source,
                })
        merged_kills.sort(key=lambda k: float(k.get("timestamp", 0.0)))

    return merged_kills, event_tier, new_start, new_end, anchored_peak_t, filtered_segs


def _analyze_single_clip_for_overnight(clip_info: Dict[str, Any]) -> Dict[str, Any]:
    """Analizuje pojedynczy plik wideo pod kątem jakości surowca, hype i przydatności pod montaż."""
    path = str(clip_info.get("path") or "")
    filename = str(clip_info.get("filename") or Path(path).name)
    modified = float(clip_info.get("modified") or 0.0)
    size_mb = float(clip_info.get("size_mb") or 0.0)

    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            return {
                "filename": filename,
                "path": path,
                "modified": modified,
                "size_mb": size_mb,
                "qualified": False,
                "fallback_eligible": False,
                "rejection_code": "REJECT_UNREADABLE",
                "rejection_reason": "Nie można otworzyć pliku wideo",
                "hype_score": 0.0,
            }
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        frame_cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()

    duration = (frame_cnt / fps) if fps > 0 else 0.0
    if height < 720 or fps < 24.0 or duration < 5.0 or duration > 180.0:
        return {
            "filename": filename,
            "path": path,
            "modified": modified,
            "size_mb": size_mb,
            "duration": round(duration, 2),
            "width": width,
            "height": height,
            "fps": round(fps, 1),
            "qualified": False,
            "fallback_eligible": False,
            "rejection_code": "REJECT_LOW_TECH",
            "rejection_reason": f"Parametry poza zakresem ({width}x{height}@{fps:.0f}fps, {duration:.1f}s)",
            "hype_score": 0.0,
        }

    try:
        from lol_agent.lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window
        from lol_agent.lol_quality_validator import is_raw_material_viable
    except ImportError:
        from lol_frag_detector import analyze_clip_frags, compute_optimal_clip_window  # type: ignore
        from lol_quality_validator import is_raw_material_viable  # type: ignore

    frag_res = analyze_clip_frags(path, sample_fps=1.0)
    raw_kills = list(frag_res.kills or [])
    raw_det = str(frag_res.detected_frag_type or "outplay").lower().strip()
    pre_act = _normalize_action_type_in_window(raw_det, raw_kills, bool(frag_res.is_clutch_1hp))

    clip_start, clip_end, peak_moment, combat_segs = compute_optimal_clip_window(
        frag_res,
        duration,
        action_type=pre_act,
    )
    raw_kills, raw_det, clip_start, clip_end, peak_moment, combat_segs = _apply_outplayed_anchor(
        clip_info=clip_info,
        raw_kills=raw_kills,
        raw_det=raw_det,
        clip_start=clip_start,
        clip_end=clip_end,
        peak_moment=peak_moment,
        combat_segs=combat_segs,
        duration=duration,
    )
    window_dur = max(1.0, round(float(clip_end) - float(clip_start), 2))
    player_died = _check_trailing_survival(path, clip_end, fps)

    peaks_tuples = [(float(k["timestamp"]), str(k.get("label", "KILL"))) for k in raw_kills]
    raw_ok, raw_code, raw_reason = is_raw_material_viable(
        peaks=peaks_tuples,
        clip_start=clip_start,
        clip_end=clip_end,
        source_size=(width, height),
        source_fps=fps,
    )

    raw_entry = {
        "filename": filename,
        "path": path,
        "modified": modified,
        "size_mb": size_mb,
        "duration": round(duration, 2),
        "width": width,
        "height": height,
        "fps": round(fps, 1),
        "raw_detected_frag_type": raw_det,
        "kills": raw_kills,
        "clip_start": round(float(clip_start), 2),
        "clip_end": round(float(clip_end), 2),
        "peak_moment": round(float(peak_moment), 2),
        "window_dur": window_dur,
        "combat_segments": [list(s) for s in combat_segs] if combat_segs else None,
        "hook_text": str(frag_res.suggested_title_hook or "").strip(),
        "confidence": round(float(frag_res.confidence or 0.0), 3),
        "min_hp_percentage": round(float(frag_res.min_hp_percentage if frag_res.min_hp_percentage is not None else 100.0), 1),
        "is_clutch_1hp": bool(frag_res.is_clutch_1hp),
        "objective_secured": bool(frag_res.objective_secured),
        "objective_label": str(frag_res.objective_label or ""),
        "ally_banner_blocked": bool(frag_res.ally_banner_blocked),
        "player_died": player_died,
        "raw_viable": bool(raw_ok),
        "raw_code": raw_code,
        "raw_reason": raw_reason,
        "champion": clip_info.get("champion") or "",
        "is_favorite": bool(clip_info.get("is_favorite", False)),
        "event_tier": clip_info.get("event_tier") or "",
        "event_tier_rank": clip_info.get("event_tier_rank"),
        "event_source": clip_info.get("event_source") or "none",
        "best_event_time_s": clip_info.get("best_event_time_s"),
        "est_first_kill_s": clip_info.get("est_first_kill_s"),
        "est_last_kill_s": clip_info.get("est_last_kill_s"),
        "total_kills_in_clip": clip_info.get("total_kills_in_clip"),
        "match_folder": clip_info.get("match_folder") or "",
        "match_date": clip_info.get("match_date") or "",
        "clip_base_key": clip_info.get("clip_base_key") or "",
        "match_kda": clip_info.get("match_kda") or "",
    }
    return _score_and_classify_candidate(raw_entry)


def _select_top_diverse_candidates(
    qualified: List[Dict[str, Any]],
    rejected: List[Dict[str, Any]],
    top_n: int,
) -> List[Dict[str, Any]]:
    """Wybiera Top N najlepszych kandydatów z deduplikacją par (_0/_1) i dywersyfikacją między meczami."""
    sort_key = lambda c: (
        float(c.get("hype_score", 0.0)),
        int(c.get("kill_count", 0)),
        bool(c.get("is_favorite", False)),
        bool(c.get("objective_secured", False)),
        float(c.get("confidence", 0.0)),
        float(c.get("modified", 0.0)),
    )
    q_sorted = sorted(qualified, key=sort_key, reverse=True)
    selected: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    seen_base_keys: set[str] = set()
    match_counts: Dict[str, int] = {}

    def _base_key(cand: Dict[str, Any]) -> str:
        bk = str(cand.get("clip_base_key") or "").strip().lower()
        if bk:
            return bk
        p = Path(str(cand.get("path") or ""))
        return re.sub(r"_\d+$", "", p.stem).lower()

    def _is_near_duplicate(cand: Dict[str, Any], chosen: List[Dict[str, Any]]) -> bool:
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            return True
        c_dir = str(Path(str(cand.get("path") or "")).parent)
        c_m = float(cand.get("modified") or 0.0)
        for prev in chosen:
            if str(Path(str(prev.get("path") or "")).parent) == c_dir and abs(c_m - float(prev.get("modified") or 0.0)) < 20.0:
                return True
        return False

    for cand in q_sorted:
        if len(selected) >= top_n:
            break
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            continue
        mf = str(cand.get("match_folder") or "").strip()
        if _is_near_duplicate(cand, selected) or (mf and match_counts.get(mf, 0) >= 2):
            deferred.append(cand)
        else:
            selected.append(cand)
            if c_bk:
                seen_base_keys.add(c_bk)
            if mf:
                match_counts[mf] = match_counts.get(mf, 0) + 1

    # Jeśli po dywersyfikacji brakło różnych meczów do top_n, dobierz z odłożonych (zawsze pomijając duplikaty _0/_1)
    for cand in deferred:
        if len(selected) >= top_n:
            break
        c_bk = _base_key(cand)
        if c_bk and c_bk in seen_base_keys:
            continue
        selected.append(cand)
        if c_bk:
            seen_base_keys.add(c_bk)

    # Jeśli zakwalifikowanych jest mniej niż top_n, dopuszczamy WYŁĄCZNIE fallback_eligible (1-kill raw_ok),
    # NIGDY 0-kill śmieci ani zgonów o niskim wpływie
    if len(selected) < top_n:
        fb_pool = sorted(
            [c for c in rejected if c.get("fallback_eligible")],
            key=sort_key,
            reverse=True,
        )
        for cand in fb_pool:
            if len(selected) >= top_n:
                break
            c_bk = _base_key(cand)
            if c_bk and c_bk in seen_base_keys:
                continue
            copy_c = dict(cand)
            copy_c["fallback_mediocre"] = True
            selected.append(copy_c)
            if c_bk:
                seen_base_keys.add(c_bk)

    return selected


def _make_prerejected_entry(cl: Dict[str, Any], code: str, reason: str) -> Dict[str, Any]:
    return {
        "filename": cl.get("filename", "?"),
        "path": str(cl.get("path") or ""),
        "modified": float(cl.get("modified") or 0.0),
        "size_mb": float(cl.get("size_mb") or 0.0),
        "action_type": str(cl.get("event_tier") or "outplay"),
        "champion": cl.get("champion") or "",
        "is_favorite": bool(cl.get("is_favorite", False)),
        "event_tier": cl.get("event_tier") or "",
        "event_tier_rank": cl.get("event_tier_rank"),
        "event_source": cl.get("event_source") or "none",
        "best_event_time_s": cl.get("best_event_time_s"),
        "total_kills_in_clip": cl.get("total_kills_in_clip"),
        "match_folder": cl.get("match_folder") or "",
        "match_date": cl.get("match_date") or "",
        "clip_base_key": cl.get("clip_base_key") or "",
        "match_kda": cl.get("match_kda") or "",
        "qualified": False,
        "fallback_eligible": False,
        "rejection_code": code,
        "rejection_reason": reason,
        "hype_score": 0.0,
    }


def _merge_fresh_metadata_into_cached(cached_item: Dict[str, Any], cl: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(cached_item)
    for k in (
        "champion",
        "is_favorite",
        "event_tier",
        "event_tier_rank",
        "event_source",
        "best_event_time_s",
        "est_first_kill_s",
        "est_last_kill_s",
        "total_kills_in_clip",
        "match_folder",
        "match_date",
        "clip_base_key",
        "match_kda",
    ):
        if k in cl and cl.get(k) not in (None, ""):
            merged[k] = cl.get(k)
        elif k == "is_favorite" and "is_favorite" in cl:
            merged[k] = bool(cl["is_favorite"])
    return merged


def scan_and_rank_all_clips(
    folder: Optional[str] = None,
    top_n: int = 5,
    skip_published: bool = True,
    use_cache: bool = True,
    max_workers: int = 3,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    champion_name: Optional[str] = "Katarina",
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
) -> Dict[str, Any]:
    """
    Skanuje wszystkie nagrania w folderze, filtruje wstępnie wg telemetrii Riot Outplayed,
    odfiltrowuje opublikowane oraz przeciętne klipy i zwraca Top N kandydatów o najwyższym `hype_score`.
    """
    try:
        from lol_agent.api.routers.clips import scan_available_clips
    except ImportError:
        from api.routers.clips import scan_available_clips  # type: ignore

    all_clips = scan_available_clips(folder)
    total_found = len(all_clips)
    skipped_published = 0
    champ_ok_pool: List[Dict[str, Any]] = []
    pre_rejected: List[Dict[str, Any]] = []
    req_champ = str(champion_name or "").strip().lower()
    tf_key = str(tier_filter or "auto").strip().lower()
    min_rank = TIER_FILTER_MIN_RANK.get(tf_key, -1)

    for cl in all_clips:
        if skip_published and cl.get("already_published"):
            skipped_published += 1
            continue
        cl_champ = str(cl.get("champion") or "").strip()
        if only_channel_champion and req_champ and cl_champ and cl_champ.lower() != req_champ:
            pre_rejected.append(
                _make_prerejected_entry(
                    cl,
                    "REJECT_WRONG_CHAMPION",
                    f"Inny bohater w telemetry ({cl_champ} != {champion_name})",
                )
            )
            continue
        champ_ok_pool.append(cl)

    # Policz ile unikalnych klipów (bez duplikatów _0/_1) to potwierdzone multikille (>= Double)
    multikill_base_keys: set[str] = set()
    for cl in champ_ok_pool:
        src = str(cl.get("event_source") or "")
        rk = cl.get("event_tier_rank")
        if (src.startswith("outplayed_") or src == "medal_db") and isinstance(rk, (int, float)) and int(rk) >= 2:
            bk = str(cl.get("clip_base_key") or "").strip().lower() or str(cl.get("path") or "")
            multikill_base_keys.add(bk)
    multikills_available = len(multikill_base_keys)

    pool: List[Dict[str, Any]] = []
    for cl in champ_ok_pool:
        src = str(cl.get("event_source") or "")
        rk_raw = cl.get("event_tier_rank")
        has_db_tier = (src.startswith("outplayed_") or src == "medal_db") and isinstance(rk_raw, (int, float))
        if has_db_tier:
            t_rank = int(rk_raw)
            if t_rank == 0 and tf_key != "all":
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_ASSIST_ONLY",
                        "Tylko asysta w telemetrii Riot Outplayed (pominięto przed OCR)",
                    )
                )
                continue
            if min_rank >= 1 and t_rank < min_rank:
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_TIER_FILTER",
                        f"Tier '{cl.get('event_tier')}' poniżej filtra '{tf_key}'",
                    )
                )
                continue
            if tf_key == "auto" and t_rank == 1 and multikills_available >= max(1, int(top_n)):
                pre_rejected.append(
                    _make_prerejected_entry(
                        cl,
                        "REJECT_SINGLE_KILL_MULTIKILLS_AVAILABLE",
                        f"Single kill w bazie Outplayed pominięty przed OCR (dostępne {multikills_available} multikilli)",
                    )
                )
                continue
        pool.append(cl)

    cache_data = _load_scan_cache() if use_cache else {"schema": SCAN_CACHE_SCHEMA_VERSION, "entries": {}}
    entries = cache_data["entries"]
    results: List[Dict[str, Any]] = list(pre_rejected)
    analyzed_cached: List[Dict[str, Any]] = []
    to_analyze: List[Tuple[Dict[str, Any], str]] = []

    for cl in pool:
        p = str(cl.get("path") or "")
        try:
            st = Path(p).stat()
            ckey = _cache_key_for(p, st.st_size, st.st_mtime)
        except Exception:
            ckey = _cache_key_for(p, int(cl.get("size_mb", 0) * 1024 * 1024), float(cl.get("modified", 0)))

        cached_item = entries.get(ckey) if use_cache else None
        if isinstance(cached_item, dict) and Path(p).exists():
            merged_cached = _merge_fresh_metadata_into_cached(cached_item, cl)
            analyzed_cached.append(_score_and_classify_candidate(merged_cached))
        else:
            to_analyze.append((cl, ckey))

    results.extend(analyzed_cached)
    done_count = len(analyzed_cached)
    total_to_scan = len(pool)
    if progress_cb and (analyzed_cached or pre_rejected):
        progress_cb(
            done_count,
            total_to_scan,
            f"Pre-filtr: odrzucono {len(pre_rejected)}, cache {done_count}/{total_to_scan}",
        )

    if to_analyze:
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        workers = max(1, min(int(max_workers or 1), len(to_analyze)))
        cache_lock = threading.Lock()

        def _worker(item: Tuple[Dict[str, Any], str]) -> Tuple[str, Dict[str, Any]]:
            cl_item, ckey = item
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Skan przerwany przez użytkownika")
            res = _analyze_single_clip_for_overnight(cl_item)
            return ckey, res

        ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        cancelled = False
        try:
            future_map = {ex.submit(_worker, item): item[0] for item in to_analyze}
            newly_scanned = 0
            for fut in concurrent.futures.as_completed(future_map):
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    for pending in future_map:
                        pending.cancel()
                    break
                cl_meta = future_map[fut]
                done_count += 1
                try:
                    ckey, res = fut.result()
                    results.append(res)
                    newly_scanned += 1
                    if use_cache:
                        with cache_lock:
                            entries[ckey] = res
                            if newly_scanned % 5 == 0:
                                _save_scan_cache(cache_data)
                except InterruptedError:
                    cancelled = True
                    for pending in future_map:
                        pending.cancel()
                    break
                except Exception as exc:
                    results.append({
                        "filename": cl_meta.get("filename", "?"),
                        "path": cl_meta.get("path", ""),
                        "modified": float(cl_meta.get("modified") or 0.0),
                        "qualified": False,
                        "fallback_eligible": False,
                        "rejection_code": "REJECT_SCAN_ERROR",
                        "rejection_reason": str(exc),
                        "hype_score": 0.0,
                    })
                if progress_cb:
                    progress_cb(done_count, total_to_scan, str(cl_meta.get("filename", "")))
        finally:
            ex.shutdown(wait=not cancelled, cancel_futures=cancelled)

    if use_cache and to_analyze:
        _save_scan_cache(cache_data)

    qualified = [r for r in results if r.get("qualified")]
    rejected = [r for r in results if not r.get("qualified")]
    selected = _select_top_diverse_candidates(qualified, rejected, max(1, int(top_n)))

    rejection_breakdown: Dict[str, int] = {}
    for r in rejected:
        code = str(r.get("rejection_code") or "REJECT_OTHER")
        rejection_breakdown[code] = rejection_breakdown.get(code, 0) + 1

    return {
        "folder": folder or "Outplayed + Medal",
        "total_clips_found": total_found,
        "skipped_published": skipped_published,
        "scanned_unpublished": len(results),
        "qualified_count": len(qualified),
        "rejected_count": len(rejected),
        "rejection_breakdown": rejection_breakdown,
        "selected": selected,
        "all_qualified": sorted(qualified, key=lambda c: float(c.get("hype_score", 0.0)), reverse=True),
        "rejected_sample": sorted(rejected, key=lambda c: float(c.get("hype_score", 0.0)), reverse=True)[:15],
    }


def _extract_defects(insp: Dict[str, Any], ig_ready: bool, item: Optional[Dict[str, Any]] = None) -> Tuple[List[str], bool]:
    defects: List[str] = []
    critical = False
    if insp.get("black_end_frame"):
        defects.append("black_end_frame")
        critical = True
    if not insp.get("frame0_hook_legible", True):
        defects.append("frame0_hook_illegible")
        critical = True
    if int(insp.get("audio_clip_gt_096") or 0) > 10:
        defects.append("audio_clipping_gt_10")
        critical = True
    if float(insp.get("av_delta_s") or 0.0) > 0.25:
        defects.append("av_desync_gt_025s")
        critical = True
    if insp.get("kill_overlay_zone") == "center_blocking":
        defects.append("center_blocking_overlay")
    vis_r = float(insp.get("player_visible_ratio") if insp.get("player_visible_ratio") is not None else 1.0)
    if 0.0 < vis_r < 0.55:
        defects.append("low_player_visibility")
    elif 0.0 < vis_r < 0.72:
        defects.append("player_offscreen_frames")
    if float(insp.get("player_edge_clip_ratio") or 0.0) > 0.35:
        defects.append("high_edge_clipping")
    if insp.get("first_kill_out_sec") is not None and float(insp.get("first_kill_out_sec") or 0.0) > 4.8:
        defects.append("slow_intro_gt_4.8s")
    if insp.get("hook_is_generic"):
        defects.append("generic_hook")
    if item and item.get("champion_mismatch"):
        defects.append(f"wrong_champion:{item.get('champion_name')}!={item.get('requested_champion')}")
    if not ig_ready:
        defects.append("ig_needs_transcode_on_upload")
    return defects, critical


_DISALLOWED_TEXT_RE = re.compile(r"[^\x20-\x7E\nąćęłńóśźżĄĆĘŁŃÓŚŹŻ–—’„”•]")
_BROKEN_PL_RE = re.compile(r"\b(?:triunf\w*|katarinsk\w*|obserwator\w*|dwuekranow\w*|z\s+obiektywem)\b", re.IGNORECASE)
_SCORE_MENTION_RE = re.compile(
    r"(?:final(?:_score)?\s*[=:]\s*|wynik\s*[=:]\s*|ocena\s*[=:]\s*|(?<!\d))(\d{2}(?:\.\d+)?)\s*(?=/100|\b)",
    re.IGNORECASE,
)


def _is_clean_consistent_polish_note(note: str, item: Dict[str, Any]) -> bool:
    """Weryfikuje poprawność językową, brak halucynacji tieru/wad i spójność liczb w notkach LoRA."""
    txt = str(note or "").strip()
    if len(txt) < 38:
        return False
    if _DISALLOWED_TEXT_RE.search(txt) or _BROKEN_PL_RE.search(txt):
        return False
    if not re.search(r"[a-ząćęłńóśźż]{4,}", txt.lower()):
        return False

    low = txt.lower()
    crit = bool(item.get("has_critical_defect"))
    real_defects = [d for d in (item.get("defects") or []) if d != "ig_needs_transcode_on_upload"]
    praise_tokens = ("świetn", "idealn", "niesamow", "perfekc", "najlepsz", "bez wątpliwości")
    if (crit or real_defects) and any(tok in low for tok in praise_tokens):
        return False
    if int(item.get("overnight_rank") or 1) >= 2 and any(tok in low for tok in ("najlepsz", "zwycięzc", "#1")):
        return False
    if (not real_defects) and "regresj" in low:
        return False

    act = str(item.get("action_type") or "").lower()
    if act == "triple" and re.search(r"\b(?:dwufrag\w*|double)\b", low):
        return False
    if act == "double" and re.search(r"\b(?:tr[oó]jk\w*|trzy\s+frag\w*|triple|quadr\w*|pent\w*)\b", low):
        return False
    if act == "quadrakill" and re.search(r"\b(?:dwufrag\w*|tr[oó]jk\w*)\b", low):
        return False

    fs = item.get("final_score")
    known_metrics = [
        float(item[k])
        for k in ("final_score", "hype_score", "watchability_score", "qa_score")
        if isinstance(item.get(k), (int, float))
    ]
    if known_metrics:
        # Każda nieoznaczona liczba >= 30 (niebędąca sekundami/godzinami ani mianownikiem /100) musi odpowiadać realnej metryce tego shorta
        for m in re.finditer(r"(?<![\d./])(\d{2,3}(?:\.\d+)?)(?!\s*(?:s\b|ms\b|h\b|px\b|fps\b|k\b|%\b))", txt, re.IGNORECASE):
            end_pos = m.end()
            if txt[end_pos : end_pos + 1] == "/" and txt[end_pos + 1 : end_pos + 4] != "100":
                continue
            try:
                num_v = float(m.group(1))
            except Exception:
                continue
            if 30.0 <= num_v <= 100.0 and not any(abs(num_v - km) <= 1.8 for km in known_metrics):
                return False

    if isinstance(fs, (int, float)):
        fs_val = float(fs)
        for m in re.finditer(
            r"(?:final(?:_score)?\s*[=:]\s*|wynik\s*[=:]\s*|ocena\s*[=:]\s*)(\d{2}(?:\.\d+)?)|(\d{2}(?:\.\d+)?)\s*/\s*100|\((\d{2}(?:\.\d+)?)\)",
            txt,
            re.IGNORECASE,
        ):
            val_s = m.group(1) or m.group(2) or m.group(3)
            try:
                val = float(val_s)
            except Exception:
                continue
            if abs(val - fs_val) > 2.5:
                return False
        for labeled_re, key_name in (
            (r"hype\s*[=:]\s*(\d{2}(?:\.\d+)?)", "hype_score"),
            (r"watch(?:ability)?\s*[=:]\s*(\d{2}(?:\.\d+)?)", "watchability_score"),
            (r"qa\s*[=:]\s*(\d{2}(?:\.\d+)?)", "qa_score"),
        ):
            ref = item.get(key_name)
            if isinstance(ref, (int, float)):
                for m in re.finditer(labeled_re, txt, re.IGNORECASE):
                    try:
                        if abs(float(m.group(1)) - float(ref)) > 2.5:
                            return False
                    except Exception:
                        pass
    return True


def _build_honest_short_comment_pl(item: Dict[str, Any]) -> str:
    act = str(item.get("action_type", "outplay")).upper()
    champ = str(item.get("champion_name") or "?")
    hype = item.get("hype_score", 0)
    watch = item.get("watchability_score", 0)
    qa = item.get("qa_score", 0)
    defects = [d for d in (item.get("defects") or []) if d != "ig_needs_transcode_on_upload"]
    defect_txt = f" | UWAGA wady: {', '.join(defects)}" if defects else " | brak defektów krytycznych"
    fb_txt = " [fallback słabszy 1-kill]" if item.get("fallback_mediocre") else ""
    return (
        f"{champ} {act}{fb_txt}: hype={hype}, watch={watch}, qa={qa}, "
        f"klatka0={'OK' if item.get('frame0_hook_legible', True) else 'NIE'} "
        f"({item.get('kill_overlay_zone', '?')}){defect_txt}."
    )


def rank_rendered_overnight_shorts(
    rendered_items: List[Dict[str, Any]],
    scan_stats: Dict[str, Any],
    use_local_ai: bool = True,
) -> Dict[str, Any]:
    """
    Szereguje wyrenderowane shorty (#1..#5) z twardym strażnikiem anty-sykofankcji (Sykofankcja 0).
    """
    valid_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []

    for it in rendered_items:
        item = dict(it)
        if not item.get("render_ok") or not item.get("output_path") or not Path(str(item["output_path"])).is_file():
            item["final_score"] = 0.0
            item["verdict"] = "RENDER_ERROR"
            item["has_critical_defect"] = True
            item["synapsa_comment_pl"] = f"Błąd renderowania: {item.get('error') or 'brak pliku .mp4'}."
            failed_items.append(item)
            continue

        hype = float(item.get("hype_score") or 0.0)
        watch = float(item.get("watchability_score") or 0.0)
        qa = float(item.get("qa_score") or 0.0)
        defects = list(item.get("defects") or [])
        has_crit = bool(item.get("has_critical_defect"))

        raw_final = round(0.45 * hype + 0.40 * watch + 0.15 * qa, 1)
        if item.get("champion_mismatch"):
            raw_final -= 6.0
        if has_crit:
            raw_final = min(raw_final, 65.0)
        vis_r = float(item.get("player_visible_ratio") if item.get("player_visible_ratio") is not None else 1.0)
        if (0.0 < vis_r < 0.55) or float(item.get("player_edge_clip_ratio") or 0.0) > 0.35:
            raw_final = min(raw_final, 68.0)
        elif 0.0 < vis_r < 0.72:
            raw_final = min(raw_final, 74.0)
        if item.get("fallback_mediocre"):
            raw_final = min(raw_final, 64.0)

        item["final_score"] = round(max(0.0, min(100.0, raw_final)), 1)
        item["defects"] = defects
        valid_items.append(item)

    valid_items.sort(
        key=lambda x: (
            not bool(x.get("has_critical_defect")),
            float(x.get("final_score", 0.0)),
            float(x.get("watchability_score", 0.0)),
            float(x.get("hype_score", 0.0)),
        ),
        reverse=True,
    )

    ai_resp: Optional[Dict[str, Any]] = None
    id_to_item: Dict[str, Dict[str, Any]] = {str(i): x for i, x in enumerate(valid_items, start=1)}
    item_to_id: Dict[int, str] = {id(x): str(i) for i, x in enumerate(valid_items, start=1)}
    if valid_items and use_local_ai:
        try:
            try:
                from lol_agent.synapsa_engine import generate_with_synapsa, is_synapsa_available
            except ImportError:
                from synapsa_engine import generate_with_synapsa, is_synapsa_available  # type: ignore

            if is_synapsa_available():
                compact_cands = [
                    {
                        "id": str(i),
                        "filename": x.get("output_filename"),
                        "champion_name": x.get("champion_name"),
                        "champion_mismatch": bool(x.get("champion_mismatch")),
                        "action_type": x.get("action_type"),
                        "kill_count": x.get("kill_count"),
                        "hype_score": x.get("hype_score"),
                        "watchability_score": x.get("watchability_score"),
                        "qa_score": x.get("qa_score"),
                        "final_score": x.get("final_score"),
                        "player_visible_ratio": x.get("player_visible_ratio"),
                        "first_kill_out_sec": x.get("first_kill_out_sec"),
                        "black_end_frame": bool(x.get("black_end_frame")),
                        "frame0_hook_legible": bool(x.get("frame0_hook_legible", True)),
                        "audio_clip_gt_096": int(x.get("audio_clip_gt_096") or 0),
                        "defects": [d for d in (x.get("defects") or []) if d != "ig_needs_transcode_on_upload"],
                    }
                    for i, x in enumerate(valid_items, start=1)
                ]
                ai_resp = generate_with_synapsa(
                    "overnight_rank",
                    {"candidates": compact_cands, "scan_stats": {"qualified": scan_stats.get("qualified_count"), "rejected": scan_stats.get("rejected_count")}},
                    timeout=180,
                )
        except Exception:
            ai_resp = None

    objective_leader = valid_items[0] if valid_items else None
    chosen_leader = objective_leader
    guard_override = False
    rec_source = "synapsa_deterministic_judge"

    if ai_resp and valid_items:
        winner_id_raw = str(ai_resp.get("winner_id") or "").strip().lstrip("#")
        ai_fn = str(ai_resp.get("recommended_filename") or "").strip()
        by_fn = {str(x.get("output_filename")): x for x in valid_items}
        ai_pick = id_to_item.get(winner_id_raw) or by_fn.get(ai_fn)
        if ai_pick is not None and objective_leader is not None:
            gap = float(objective_leader["final_score"]) - float(ai_pick["final_score"])
            if ai_pick.get("has_critical_defect") or gap >= 8.0:
                guard_override = True
                chosen_leader = objective_leader
                rec_source = "synapsa_guard_override"
            else:
                chosen_leader = ai_pick
                rec_source = "synapsa_local_lora_judge"
                if chosen_leader is not objective_leader:
                    valid_items.remove(chosen_leader)
                    valid_items.insert(0, chosen_leader)

    ai_notes = ai_resp.get("notes_pl") if (ai_resp and isinstance(ai_resp.get("notes_pl"), dict)) else {}
    ai_per_short = ai_resp.get("per_short_pl") if (ai_resp and isinstance(ai_resp.get("per_short_pl"), dict)) else {}

    ranked_all: List[Dict[str, Any]] = []
    seen_ai_comments: set[str] = set()
    for idx, item in enumerate(valid_items, start=1):
        item["overnight_rank"] = idx
        fs = float(item.get("final_score") or 0.0)
        ws = float(item.get("watchability_score") or 0.0)
        crit = bool(item.get("has_critical_defect"))
        if idx == 1:
            item["verdict"] = "PICK_WINNER" if (fs >= 70.0 and ws >= 68.0 and not crit and not item.get("fallback_mediocre")) else "NEEDS_TWEAK"
        elif idx <= 3:
            item["verdict"] = "STRONG_ALT" if (fs >= 65.0 and ws >= 65.0 and not crit) else ("NEEDS_TWEAK" if fs >= 50.0 else "SKIP")
        elif fs >= 75.0 and ws >= 80.0 and not crit and not item.get("fallback_mediocre"):
            item["verdict"] = "STRONG_ALT"
        else:
            item["verdict"] = "NEEDS_TWEAK" if fs >= 50.0 else "SKIP"

        orig_id = item_to_id.get(id(item), str(idx))
        raw_ai_comment = str(ai_notes.get(orig_id) or ai_per_short.get(str(item.get("output_filename") or ""), "") or "").strip()
        metrics_comment = _build_honest_short_comment_pl(item)
        has_digits = any(ch.isdigit() for ch in raw_ai_comment)
        norm_ai = raw_ai_comment.lower()
        is_dup_ai = bool(norm_ai and norm_ai in seen_ai_comments)
        note_clean = (not is_dup_ai) and _is_clean_consistent_polish_note(raw_ai_comment, item)
        if not guard_override and note_clean and len(raw_ai_comment) >= 38 and has_digits:
            item["synapsa_comment_pl"] = raw_ai_comment
            seen_ai_comments.add(norm_ai)
        elif not guard_override and note_clean and len(raw_ai_comment) >= 38:
            item["synapsa_comment_pl"] = f"{raw_ai_comment.rstrip('.')} — {metrics_comment}"
            seen_ai_comments.add(norm_ai)
        else:
            item["synapsa_comment_pl"] = metrics_comment
        ranked_all.append(item)

    for fail_it in failed_items:
        fail_it["overnight_rank"] = len(ranked_all) + 1
        ranked_all.append(fail_it)

    ai_summary = str((ai_resp or {}).get("summary_pl") or "").strip()
    if chosen_leader is not None:
        summary_ok = _is_clean_consistent_polish_note(ai_summary, chosen_leader) and len(ai_summary) >= 30
        if guard_override or not summary_ok:
            leader_fn = chosen_leader.get("output_filename")
            leader_ch = chosen_leader.get("champion_name") or "?"
            other_note = (
                f" Drugi: {valid_items[1].get('output_filename')} ({valid_items[1].get('champion_name', '?')}, final={valid_items[1].get('final_score')})."
                if len(valid_items) >= 2
                else ""
            )
            weak_note = ""
            if int(scan_stats.get("qualified_count") or 0) < int(len(valid_items)):
                weak_note = f" UWAGA: tylko {scan_stats.get('qualified_count')} klipy spełniły ostry próg hype (reszta to fallback)."
            mismatch_note = (
                f" Uwaga: klip #{1} ma bohatera {leader_ch} (poza {chosen_leader.get('requested_champion')})."
                if chosen_leader.get("champion_mismatch")
                else ""
            )
            summary_pl = (
                f"Rekomendacja #1: {leader_fn} ({leader_ch} {str(chosen_leader.get('action_type', '')).upper()}, "
                f"final={chosen_leader.get('final_score')}/100, hype={chosen_leader.get('hype_score')}, "
                f"watch={chosen_leader.get('watchability_score')}, qa={chosen_leader.get('qa_score')})."
                f"{mismatch_note}{other_note}{weak_note}"
            )
        else:
            summary_pl = ai_summary
    else:
        summary_pl = "Żaden short z tej paczki nie wyrenderował się poprawnie."

    return {
        "recommended_filename": chosen_leader.get("output_filename") if chosen_leader else None,
        "recommended_verdict": chosen_leader.get("verdict") if chosen_leader else None,
        "recommendation_source": rec_source,
        "guard_override": guard_override,
        "summary_pl": summary_pl,
        "items": ranked_all,
    }


def _persist_batch_manifest(manifest: Dict[str, Any]) -> str:
    OVERNIGHT_DIR.mkdir(parents=True, exist_ok=True)
    bid = str(manifest.get("batch_id") or datetime.now().strftime("%Y%m%d_%H%M%S"))
    batch_file = OVERNIGHT_DIR / f"batch_{bid}.json"
    text = json.dumps(manifest, indent=2, ensure_ascii=False)
    _atomic_write_text(batch_file, text)
    _atomic_write_text(LATEST_BATCH_FILE, text)
    return str(batch_file)


def _thumb_search_dirs(output_path: Optional[str] = None) -> List[Path]:
    """Zwraca listę katalogów, w których mogą znajdować się miniaturki 9:16."""
    dirs: List[Path] = []
    if output_path:
        try:
            dirs.append(Path(str(output_path)).parent)
        except Exception:
            pass
    try:
        try:
            from lol_agent.api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR
        except ImportError:
            from api.config import LOL_TEMP_DIR, LOL_OUTPUT_DIR  # type: ignore
        dirs.extend([Path(LOL_TEMP_DIR), Path(LOL_OUTPUT_DIR)])
    except Exception:
        pass
    dirs.extend([LOL_AGENT_DIR / "lol_temp", LOL_AGENT_DIR / "thumbnails"])
    unique: List[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _resolve_thumbnail_for_output(
    output_filename: str,
    existing_thumb_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Zwraca (pełna ścieżka, nazwa pliku) istniejącej miniaturki dla danego shorta lub (None, None)."""
    if existing_thumb_path:
        p = Path(str(existing_thumb_path))
        if p.is_file():
            return str(p), p.name
    safe_name = Path(str(output_filename or "")).name
    if not safe_name:
        return None, None
    stem = Path(safe_name).stem
    thumb_name = f"{stem}_thumb.jpg"
    for d in _thumb_search_dirs(output_path):
        cand = d / thumb_name
        if cand.is_file():
            return str(cand), cand.name
    return None, None


def update_overnight_item_thumbnail(output_filename: str, thumb_path: str) -> bool:
    """Aktualizuje ścieżkę i nazwę miniaturki w manifeście paczki nocnej (`latest_batch.json` + `batch_*.json`)."""
    safe_video = Path(str(output_filename or "")).name
    tp = Path(str(thumb_path or ""))
    if not safe_video or not tp.name:
        return False
    tp_str = str(tp)
    tp_name = tp.name

    def _patch_manifest(mf_path: Path) -> Tuple[bool, Optional[str]]:
        if not mf_path.is_file():
            return False, None
        try:
            data = json.loads(mf_path.read_text(encoding="utf-8"))
        except Exception:
            return False, None
        if not isinstance(data, dict):
            return False, None
        changed = False
        for it in (data.get("items") or []):
            if not isinstance(it, dict):
                continue
            if Path(str(it.get("output_filename") or "")).name == safe_video:
                it["thumbnail_path"] = tp_str
                it["thumbnail_filename"] = tp_name
                changed = True
        if changed:
            _atomic_write_text(mf_path, json.dumps(data, indent=2, ensure_ascii=False))
        return changed, data.get("batch_id")

    with _MANIFEST_LOCK:
        updated, batch_id = _patch_manifest(LATEST_BATCH_FILE)
        if batch_id:
            _patch_manifest(OVERNIGHT_DIR / f"batch_{batch_id}.json")
        return updated


def load_latest_overnight_batch() -> Optional[Dict[str, Any]]:
    """Odczytuje ostatni zapisany manifest paczki nocnej lub None (z uzupełnieniem miniaturek)."""
    if not LATEST_BATCH_FILE.is_file():
        return None
    try:
        data = json.loads(LATEST_BATCH_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        for it in (data.get("items") or []):
            if not isinstance(it, dict):
                continue
            t_path, t_name = _resolve_thumbnail_for_output(
                str(it.get("output_filename") or ""),
                it.get("thumbnail_path"),
                output_path=it.get("output_path"),
            )
            it["thumbnail_path"] = t_path
            it["thumbnail_filename"] = t_name
        return data
    except Exception:
        return None


def list_overnight_batches(limit: int = 10) -> List[Dict[str, Any]]:
    """Zwraca listę ostatnich paczek nocnych z katalogu `overnight_batches/`."""
    if not OVERNIGHT_DIR.exists():
        return []
    files = sorted(OVERNIGHT_DIR.glob("batch_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: List[Dict[str, Any]] = []
    for p in files[:max(1, int(limit))]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                out.append(d)
        except Exception:
            continue
    return out


def _annotate_output_metas(ranked_items: List[Dict[str, Any]], batch_id: str) -> None:
    try:
        from lol_agent.api.helpers import _save_meta
    except ImportError:
        from api.helpers import _save_meta  # type: ignore

    for it in ranked_items:
        out_fn = it.get("output_filename")
        if not out_fn or not it.get("render_ok"):
            continue
        try:
            _save_meta(str(out_fn), {
                "source_path": it.get("source_path") or "",
                "champion_name": it.get("champion_name") or "Katarina",
                "action_type": it.get("action_type") or "outplay",
                "rank": it.get("rank") or "Master",
                "clip_start": it.get("clip_start"),
                "clip_end": it.get("clip_end"),
                "peak_moment": it.get("peak_moment"),
                "thumbnail_path": it.get("thumbnail_path") or "",
                "thumbnail_filename": it.get("thumbnail_filename") or "",
                "title": it.get("title") or "",
                "title_variant_b": it.get("title_variant_b") or "",
                "description": it.get("description") or "",
                "pinned_comment": it.get("pinned_comment") or "",
                "overnight_batch_id": batch_id,
                "overnight_rank": it.get("overnight_rank"),
                "overnight_verdict": it.get("verdict"),
                "hype_score": it.get("hype_score"),
                "watchability_score": it.get("watchability_score"),
                "final_score": it.get("final_score"),
                "synapsa_comment_pl": it.get("synapsa_comment_pl"),
            })
        except Exception:
            pass


def _probe_ig_compliance(mp4_path: str) -> Dict[str, Any]:
    try:
        try:
            from lol_agent.instagram_publisher import _probe_video_for_ig, _needs_ig_transcode
        except ImportError:
            from instagram_publisher import _probe_video_for_ig, _needs_ig_transcode  # type: ignore
        vp = Path(mp4_path)
        size_bytes = vp.stat().st_size
        probe = _probe_video_for_ig(vp)
        need_tx, reasons = _needs_ig_transcode(probe, size_bytes)
        return {
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "bitrate_mbps": round(float(probe.get("video_bitrate") or 0) / 1_000_000.0, 2),
            "audio_kbps": round(float(probe.get("audio_bitrate") or 0) / 1000.0, 1),
            "audio_sr": int(probe.get("audio_sample_rate") or 0),
            "r_fps": round(float(probe.get("r_fps") or 0.0), 2),
            "avg_fps": round(float(probe.get("avg_fps") or 0.0), 2),
            "ig_ready": not need_tx,
            "ig_issues": reasons,
        }
    except Exception:
        return {"ig_ready": True, "ig_issues": []}


def run_overnight_batch(
    folder: Optional[str] = None,
    top_n: int = 5,
    champion_name: str = "Katarina",
    rank: str = "Master",
    skip_published: bool = True,
    use_cache: bool = True,
    use_local_ai: bool = True,
    output_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    clear_cancel: bool = True,
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
) -> Dict[str, Any]:
    """
    Uruchamia pełny tryb nocny (synchronicznie):
      1. Skanuje cały folder i wybiera Top N najbardziej hypowanych klipów.
      2. Renderuje każdy lokalnie (ZERO auto-uploadu).
      3. Inspekcjonuje każdy wyrenderowany short i zwraca rekomendację Synapsy #1..#N.
    """
    try:
        from lol_agent.api import pipeline_runner
        from lol_agent.synapsa_watchability_judge import inspect_rendered_short
    except ImportError:
        from api import pipeline_runner  # type: ignore
        from synapsa_watchability_judge import inspect_rendered_short  # type: ignore

    cur_pipe = pipeline_runner.get_state()
    if cur_pipe.get("status") == "running":
        raise RuntimeError("Inny render pipeline już trwa — poczekaj lub zatrzymaj przed uruchomieniem trybu nocnego.")

    if clear_cancel:
        _OVERNIGHT_CANCEL.clear()
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:5]
    started_at = _now_iso()

    def _emit_status(**fields: Any) -> None:
        _update_overnight_state(**fields)
        if progress_cb:
            progress_cb(get_overnight_status())

    _emit_status(
        status="scanning",
        batch_id=batch_id,
        phase="Skanowanie całego folderu nagrań...",
        progress=2,
        total_clips=0,
        scanned_clips=0,
        skipped_published=0,
        qualified_count=0,
        rejected_count=0,
        selected_count=0,
        rendered_count=0,
        current_clip="",
        recommended_filename=None,
        summary_pl="",
        error=None,
        started_at=started_at,
        finished_at=None,
        log=f"Start trybu nocnego (top_n={top_n}, skip_published={skip_published}, folder={folder or 'Outplayed + Medal'})",
    )

    def _on_scan_prog(done: int, total: int, name: str) -> None:
        pct = 5 + int((done / max(1, total)) * 25)
        _emit_status(
            phase=f"Skanowanie {done}/{total}",
            progress=pct,
            scanned_clips=done,
            total_clips=total,
            current_clip=name,
        )

    scan_res = scan_and_rank_all_clips(
        folder=folder,
        top_n=top_n,
        skip_published=skip_published,
        use_cache=use_cache,
        max_workers=3,
        progress_cb=_on_scan_prog,
        cancel_event=_OVERNIGHT_CANCEL,
        champion_name=champion_name,
        tier_filter=tier_filter,
        only_channel_champion=only_channel_champion,
    )
    if _OVERNIGHT_CANCEL.is_set():
        _emit_status(status="stopped", phase="Anulowano podczas skanu", finished_at=_now_iso())
        return {"batch_id": batch_id, "status": "stopped", "scan_stats": scan_res, "items": []}

    selected = list(scan_res.get("selected") or [])
    _emit_status(
        status="rendering",
        phase=f"Wybrano {len(selected)} kandydatów do montażu",
        progress=32,
        total_clips=scan_res.get("total_clips_found", 0),
        skipped_published=scan_res.get("skipped_published", 0),
        qualified_count=scan_res.get("qualified_count", 0),
        rejected_count=scan_res.get("rejected_count", 0),
        selected_count=len(selected),
        log=(
            f"Skan gotowy: {scan_res['scanned_unpublished']} nieopublikowanych -> "
            f"{scan_res['qualified_count']} mocnych, {scan_res['rejected_count']} odrzuconych przeciętnych, "
            f"wybrano {len(selected)}."
        ),
    )

    rendered_items: List[Dict[str, Any]] = []
    for idx, cand in enumerate(selected, start=1):
        if _OVERNIGHT_CANCEL.is_set():
            _emit_status(status="stopped", phase=f"Przerwano przed renderem {idx}/{len(selected)}", finished_at=_now_iso())
            break

        safe_act = re.sub(r"[^a-z0-9_]+", "", str(cand.get("action_type") or "outplay").lower()) or "outplay"
        # Nazwa MUSI zawierać "short", bo endpoint GET /outputs filtruje po "short" / "test".
        out_filename = f"short_overnight_{batch_id}_r{idx}_{safe_act}.mp4"
        pct = 32 + int(((idx - 1) / max(1, len(selected))) * 58)
        _emit_status(
            status="rendering",
            phase=f"Montaż {idx}/{len(selected)}: {cand.get('filename')}",
            progress=pct,
            current_clip=str(cand.get("filename") or ""),
            log=f"Render #{idx}/{len(selected)}: {cand.get('filename')} -> {out_filename} (hype={cand.get('hype_score')})",
        )

        # Czyścimy ewentualny flag/kolejkę poprzedniego uruchomienia
        with pipeline_runner._lock:
            pipeline_runner._cancel_event.clear()
            pipeline_runner._job_queue.clear()

        combat_segs = None
        if safe_act != "solo_bolo" and cand.get("combat_segments"):
            combat_segs = [(float(s[0]), float(s[1])) for s in cand["combat_segments"]]

        cand_champ = str(cand.get("champion") or "").strip()
        if cand_champ and str(cand.get("event_source") or "").startswith("outplayed_"):
            detected_champ = cand_champ
        else:
            detected_champ = champion_name
            try:
                try:
                    from lol_agent.lol_screen_inspector import detect_champion_local
                except ImportError:
                    from lol_screen_inspector import detect_champion_local  # type: ignore
                if Path(str(cand["path"])).is_file():
                    detected_champ = detect_champion_local(str(cand["path"]), default_champion=champion_name) or champion_name
            except Exception:
                detected_champ = champion_name
        champ_mismatch = bool(champion_name and detected_champ and detected_champ.lower() != champion_name.lower())

        safe_hook = str(cand.get("hook_text") or "").strip()
        if not safe_hook or (safe_act in ("triple", "quadrakill", "pentakill") and "DOUBLE" in safe_hook.upper()):
            if safe_act == "triple":
                safe_hook = "TRIPLE KILL - 3 DOWN"
            elif safe_act == "quadrakill":
                safe_hook = "QUADRAKILL - ONE MORE"
            elif safe_act == "pentakill":
                safe_hook = "PENTAKILL WIPE"

        run_exc_msg: Optional[str] = None
        try:
            pipeline_runner._run_pipeline(
                source_path=str(cand["path"]),
                clip_start=float(cand.get("clip_start") or 0.0),
                clip_end=float(cand.get("clip_end") or 15.0),
                action_type=str(cand.get("action_type") or "outplay"),
                champion_name=detected_champ,
                rank=rank,
                peak_moment=float(cand.get("peak_moment") or 8.0),
                hook_text=safe_hook,
                output_filename=out_filename,
                use_speed_ramp=True,
                use_zoom_punch=True,
                use_smart_camera=True,
                notify_token=None,
                combat_segments=combat_segs,
                game_type="lol",
            )
        except Exception as run_err:
            run_exc_msg = str(run_err)
            _emit_status(log=f"Błąd renderu #{idx} ({cand.get('filename')}): {run_exc_msg}")

        p_state = pipeline_runner.get_state()
        out_path = p_state.get("output_path")
        render_ok = (not run_exc_msg) and (p_state.get("status") == "done") and bool(out_path) and Path(str(out_path)).is_file()
        resolved_out_name = Path(str(out_path)).name if render_ok else out_filename

        thumb_path, thumb_filename = _resolve_thumbnail_for_output(
            resolved_out_name,
            p_state.get("thumbnail_path") if not run_exc_msg else None,
            output_path=str(out_path) if out_path else None,
        )
        if render_ok and out_path and not thumb_path:
            try:
                try:
                    from lol_agent.lol_thumbnail import generate_thumbnail as _gen_thumb
                except ImportError:
                    from lol_thumbnail import generate_thumbnail as _gen_thumb  # type: ignore
                eff_start = float(p_state.get("clip_start") if p_state.get("clip_start") is not None else (cand.get("clip_start") or 0.0))
                eff_end = float(p_state.get("clip_end") if p_state.get("clip_end") is not None else (cand.get("clip_end") or 15.0))
                eff_peak = float(cand.get("peak_moment") or eff_end)
                eff_dur = max(1.0, eff_end - eff_start)
                safe_peak_rel = min(max(0.2, eff_peak - eff_start), max(0.3, eff_dur - 1.0))
                fallback_thumb_out = str(Path(str(out_path)).with_name(f"{Path(str(out_path)).stem}_thumb.jpg"))
                act_lbl = str(p_state.get("action_type") or cand.get("action_type") or "outplay").upper().replace("_", " ")
                _gen_thumb(
                    video_path=str(out_path),
                    peak_moment=safe_peak_rel,
                    action_label=act_lbl,
                    champion_name=detected_champ,
                    output_path=fallback_thumb_out,
                    source_clip_path=str(cand.get("path")) if cand.get("path") and os.path.isfile(str(cand.get("path"))) else None,
                    source_peak_moment=float(eff_peak),
                )
                thumb_path, thumb_filename = _resolve_thumbnail_for_output(
                    resolved_out_name,
                    fallback_thumb_out,
                    output_path=str(out_path),
                )
            except Exception as thumb_err:
                _emit_status(log=f"Miniaturka fallback warning (#{idx}): {thumb_err}")

        item_record: Dict[str, Any] = {
            "candidate_rank": idx,
            "source_filename": cand.get("filename"),
            "source_path": cand.get("path"),
            "output_filename": resolved_out_name,
            "output_path": out_path if not run_exc_msg else None,
            "thumbnail_path": thumb_path,
            "thumbnail_filename": thumb_filename,
            "champion_name": detected_champ,
            "requested_champion": champion_name,
            "champion_mismatch": champ_mismatch,
            "rank": rank,
            "action_type": p_state.get("action_type") or cand.get("action_type"),
            "kill_count": cand.get("kill_count"),
            "kill_span_s": cand.get("kill_span_s"),
            "objective_secured": cand.get("objective_secured"),
            "is_clutch_1hp": cand.get("is_clutch_1hp"),
            "min_hp_percentage": cand.get("min_hp_percentage"),
            "is_favorite": bool(cand.get("is_favorite", False)),
            "event_tier": cand.get("event_tier") or "",
            "event_source": cand.get("event_source") or "none",
            "best_event_time_s": cand.get("best_event_time_s"),
            "est_first_kill_s": cand.get("est_first_kill_s"),
            "est_last_kill_s": cand.get("est_last_kill_s"),
            "total_kills_in_clip": cand.get("total_kills_in_clip"),
            "match_folder": cand.get("match_folder") or "",
            "match_date": cand.get("match_date") or "",
            "clip_base_key": cand.get("clip_base_key") or "",
            "match_kda": cand.get("match_kda") or "",
            "clip_start": p_state.get("clip_start") if p_state.get("clip_start") is not None else cand.get("clip_start"),
            "clip_end": p_state.get("clip_end") if p_state.get("clip_end") is not None else cand.get("clip_end"),
            "peak_moment": cand.get("peak_moment"),
            "title": p_state.get("title") or "",
            "title_variant_b": p_state.get("title_variant_b") or "",
            "description": p_state.get("description") or "",
            "pinned_comment": p_state.get("pinned_comment") or "",
            "hype_score": cand.get("hype_score"),
            "fallback_mediocre": bool(cand.get("fallback_mediocre")),
            "qa_status": p_state.get("qa_status"),
            "qa_score": p_state.get("qa_score") or 0,
            "render_ok": render_ok,
            "error": run_exc_msg or p_state.get("error"),
        }

        if render_ok and out_path:
            try:
                insp = inspect_rendered_short(str(out_path))
                ig_info = _probe_ig_compliance(str(out_path))
                defects, has_crit = _extract_defects(insp, bool(ig_info.get("ig_ready", True)), item=item_record)
                item_record.update({
                    "watchability_score": float(insp.get("watchability_score") or 0.0),
                    "frame0_hook_legible": bool(insp.get("frame0_hook_legible", True)),
                    "kill_overlay_zone": insp.get("kill_overlay_zone"),
                    "player_visible_ratio": insp.get("player_visible_ratio"),
                    "player_edge_clip_ratio": insp.get("player_edge_clip_ratio"),
                    "audio_clip_gt_096": int(insp.get("audio_clip_gt_096") or 0),
                    "av_delta_s": float(insp.get("av_delta_s") or 0.0),
                    "black_end_frame": bool(insp.get("black_end_frame")),
                    "hook_is_generic": bool(insp.get("hook_is_generic")),
                    "hook_text": insp.get("hook_text") or "",
                    "duration_s": float(insp.get("video_dur_s") or 0.0),
                    "camera_peak_step_px": insp.get("camera_peak_step_px"),
                    "first_kill_out_sec": insp.get("first_kill_out_sec"),
                    "ig_compliance": ig_info,
                    "defects": defects,
                    "has_critical_defect": has_crit,
                })
            except Exception as insp_err:
                item_record["watchability_score"] = float(p_state.get("qa_score") or 0.0)
                item_record["defects"] = [f"inspect_error:{insp_err}"]
                item_record["has_critical_defect"] = False

        rendered_items.append(item_record)
        _emit_status(rendered_count=len(rendered_items), log=f"Ukończono #{idx}: ok={render_ok}, qa={item_record.get('qa_score')}, watch={item_record.get('watchability_score')}")

    if _OVERNIGHT_CANCEL.is_set():
        _emit_status(status="stopped", phase="Przerwano przez użytkownika", finished_at=_now_iso())
        return {"batch_id": batch_id, "status": "stopped", "scan_stats": scan_res, "items": rendered_items}

    _emit_status(
        status="evaluating",
        phase="Synapsa ocenia 5 shortów i wybiera #1...",
        progress=94,
        log="Uruchamiam ocenę Synapsy (Sykofankcja 0) wszystkich wyrenderowanych shortów...",
    )

    ranked_res = rank_rendered_overnight_shorts(rendered_items, scan_res, use_local_ai=use_local_ai)
    _annotate_output_metas(ranked_res["items"], batch_id=batch_id)

    finished_at = _now_iso()
    manifest: Dict[str, Any] = {
        "batch_id": batch_id,
        "status": "done",
        "auto_publish": False,
        "champion_name": champion_name,
        "tier_filter": tier_filter,
        "only_channel_champion": only_channel_champion,
        "rank": rank,
        "folder": scan_res.get("folder"),
        "started_at": started_at,
        "finished_at": finished_at,
        "scan_stats": {
            "total_clips_found": scan_res.get("total_clips_found", 0),
            "skipped_published": scan_res.get("skipped_published", 0),
            "scanned_unpublished": scan_res.get("scanned_unpublished", 0),
            "qualified_count": scan_res.get("qualified_count", 0),
            "rejected_count": scan_res.get("rejected_count", 0),
            "rejection_breakdown": scan_res.get("rejection_breakdown") or {},
        },
        "recommended_filename": ranked_res["recommended_filename"],
        "recommended_verdict": ranked_res["recommended_verdict"],
        "recommendation_source": ranked_res["recommendation_source"],
        "guard_override": ranked_res["guard_override"],
        "summary_pl": ranked_res["summary_pl"],
        "items": ranked_res["items"],
    }
    if output_dir:
        out_p = Path(output_dir)
        _atomic_write_text(
            out_p / f"overnight_manifest_{batch_id}.json",
            json.dumps(manifest, indent=2, ensure_ascii=False),
        )
    _persist_batch_manifest(manifest)

    _emit_status(
        status="done",
        phase="Gotowe — sprawdź rekomendację Synapsy",
        progress=100,
        rendered_count=sum(1 for x in ranked_res["items"] if x.get("render_ok")),
        recommended_filename=ranked_res["recommended_filename"],
        summary_pl=ranked_res["summary_pl"],
        finished_at=finished_at,
        log=ranked_res["summary_pl"],
    )
    return manifest


def start_overnight_batch_async(
    folder: Optional[str] = None,
    top_n: int = 5,
    champion_name: str = "Katarina",
    rank: str = "Master",
    skip_published: bool = True,
    use_cache: bool = True,
    use_local_ai: bool = True,
    tier_filter: str = "auto",
    only_channel_champion: bool = True,
) -> bool:
    """Uruchamia tryb nocny w wątku w tle. Zwraca False jeśli sesja lub pipeline już trwa."""
    global _OVERNIGHT_THREAD
    try:
        from lol_agent.api import pipeline_runner
    except ImportError:
        from api import pipeline_runner  # type: ignore

    with _OVERNIGHT_LOCK:
        if _OVERNIGHT_STATE.get("status") in ("scanning", "rendering", "evaluating"):
            return False
        if pipeline_runner.get_state().get("status") == "running":
            return False
        _OVERNIGHT_CANCEL.clear()
        _OVERNIGHT_STATE["status"] = "scanning"
        _OVERNIGHT_STATE["phase"] = "Inicjalizacja trybu nocnego..."
        _OVERNIGHT_STATE["progress"] = 1
        _OVERNIGHT_STATE["error"] = None

    def _runner() -> None:
        try:
            run_overnight_batch(
                folder=folder,
                top_n=top_n,
                champion_name=champion_name,
                rank=rank,
                skip_published=skip_published,
                use_cache=use_cache,
                use_local_ai=use_local_ai,
                clear_cancel=False,
                tier_filter=tier_filter,
                only_channel_champion=only_channel_champion,
            )
        except Exception as exc:
            _update_overnight_state(
                status="error",
                phase="Błąd trybu nocnego",
                error=str(exc),
                finished_at=_now_iso(),
                log=f"ERROR: {exc}",
            )
        finally:
            with _OVERNIGHT_LOCK:
                if _OVERNIGHT_STATE.get("status") in ("scanning", "rendering", "evaluating"):
                    _OVERNIGHT_STATE["status"] = "stopped" if _OVERNIGHT_CANCEL.is_set() else "error"
                    if not _OVERNIGHT_STATE.get("finished_at"):
                        _OVERNIGHT_STATE["finished_at"] = _now_iso()

    _OVERNIGHT_THREAD = threading.Thread(target=_runner, daemon=True)
    _OVERNIGHT_THREAD.start()
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synapsa Tryb Nocny (Skan -> Top 5 -> Rekomendacja)")
    parser.add_argument("--folder", default=None, help="Opcjonalny folder klipów")
    parser.add_argument("--top", type=int, default=5, help="Liczba najlepszych klipów do montażu")
    parser.add_argument("--champion", default="Katarina")
    parser.add_argument("--tier-filter", default="auto", choices=sorted(TIER_FILTER_MIN_RANK.keys()))
    parser.add_argument("--all-champions", action="store_true")
    parser.add_argument("--rank", default="Master")
    parser.add_argument("--include-published", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-local-ai", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    ns = parser.parse_args()

    def _cli_scan_prog(done: int, total: int, label: str) -> None:
        print(f"[SCAN {done}/{total}] {label}", flush=True)

    def _cli_batch_prog(st: Dict[str, Any]) -> None:
        print(f"[OVERNIGHT {st.get('progress', 0)}%] {st.get('phase')} | {st.get('current_clip')}", flush=True)

    if ns.scan_only:
        res = scan_and_rank_all_clips(
            folder=ns.folder,
            top_n=ns.top,
            skip_published=not ns.include_published,
            use_cache=not ns.no_cache,
            progress_cb=_cli_scan_prog,
            champion_name=ns.champion,
            tier_filter=ns.tier_filter,
            only_channel_champion=not ns.all_champions,
        )
        print(json.dumps({k: v for k, v in res.items() if k not in ("all_qualified",)}, indent=2, ensure_ascii=False))
    else:
        manifest = run_overnight_batch(
            folder=ns.folder,
            top_n=ns.top,
            champion_name=ns.champion,
            rank=ns.rank,
            skip_published=not ns.include_published,
            use_cache=not ns.no_cache,
            use_local_ai=not ns.no_local_ai,
            progress_cb=_cli_batch_prog,
            tier_filter=ns.tier_filter,
            only_channel_champion=not ns.all_champions,
        )
        print(json.dumps({
            "batch_id": manifest.get("batch_id"),
            "scan_stats": manifest.get("scan_stats"),
            "recommended_filename": manifest.get("recommended_filename"),
            "summary_pl": manifest.get("summary_pl"),
            "items": [
                {
                    "rank": it.get("overnight_rank"),
                    "output_filename": it.get("output_filename"),
                    "source_filename": it.get("source_filename"),
                    "action_type": it.get("action_type"),
                    "hype_score": it.get("hype_score"),
                    "watchability_score": it.get("watchability_score"),
                    "qa_score": it.get("qa_score"),
                    "final_score": it.get("final_score"),
                    "verdict": it.get("verdict"),
                    "defects": it.get("defects"),
                    "synapsa_comment_pl": it.get("synapsa_comment_pl"),
                }
                for it in (manifest.get("items") or [])
            ],
        }, indent=2, ensure_ascii=False))
