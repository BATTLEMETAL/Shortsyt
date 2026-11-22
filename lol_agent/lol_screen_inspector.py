"""
LOL Agent — Local Screen & HUD Telemetry Inspector (OpenCV + pytesseract, 0 API tokens)
======================================================================================
Analizuje klatki klipu wideo lokalnie (CPU, <0.5s, 0 tokenów chmurowych), wyliczając
twarde fakty o walce na potrzeby generatora tytułów i komentarzy:
  - min_hp_pct (minimalny % HP gracza na pasku zdrowia)
  - enemies_in_fight (liczba wykrytych czerwonych pasków wrogów w kadrze)
  - kill_span_s + combo_tempo (czas między 1. a ostatnim killem z peaks)
  - hud_spells_used (czy wykryto spadek jasności na ikonach D/F/R w dolnym HUD 16:9)
  - detect_champion_local() (eliminuje konieczność wywołań Gemini Vision)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

try:
    from lol_agent.lol_config import CHAMPION_WHITELIST
except ImportError:
    try:
        from lol_config import CHAMPION_WHITELIST
    except ImportError:
        CHAMPION_WHITELIST = ["Katarina", "Zed", "Yasuo", "Yone", "Akali", "Ahri", "Sylas"]

_EXTENDED_CHAMPIONS = tuple(dict.fromkeys([
    *CHAMPION_WHITELIST,
    "Katarina", "Yone", "Yasuo", "Zed", "Akali", "Ahri", "Sylas",
    "Irelia", "Lee Sin", "Vayne", "Jinx", "Samira", "Ezreal", "Lux",
    "Fiora", "Riven", "Master Yi", "Darius", "Kassadin", "Evelynn",
    "Talon", "Fizz", "Ekko", "Qiyana", "LeBlanc", "Kaisa", "Kai'Sa",
]))

_SKILL_TO_CHAMPION = {
    "mortal steel": "Yone",
    "way of the wanderer": "Yone",
    "fate sealed": "Yone",
    "soul unbound": "Yone",
    "death lotus": "Katarina",
    "shunpo": "Katarina",
    "voracity": "Katarina",
    "bouncing blade": "Katarina",
    "twilight shroud": "Akali",
    "perfect execution": "Akali",
    "death mark": "Zed",
    "living shadow": "Zed",
}


def _configure_tesseract() -> None:
    """Ustawia tesseract_cmd jeśli binarka leży poza PATH na Windowsie."""
    try:
        import pytesseract
        for cand in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if os.path.isfile(cand):
                pytesseract.pytesseract.tesseract_cmd = cand
                return
    except Exception:
        pass


def _extract_kill_times(peaks: Optional[list], trim_start: float = 0.0) -> List[float]:
    times: List[float] = []
    for item in (peaks or []):
        try:
            t_raw = float(item[0] if isinstance(item, (list, tuple)) else item)
            t_rel = t_raw - trim_start if (trim_start > 0.0 and t_raw >= trim_start) else t_raw
            if t_rel >= 0.0:
                times.append(t_rel)
        except Exception:
            continue
    return sorted(times)


def _estimate_self_hp_from_frame(frame_bgr: np.ndarray) -> Optional[float]:
    """
    Szacuje wypełnienie paska HP gracza (0-100%) na podstawie żółtego paska nad postacią
    lub dolnego zielonego paska HUD w klatkach 16:9. Zwraca None przy braku wyraźnego paska.
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    h, w = frame_bgr.shape[:2]
    b, g, r = frame_bgr[:, :, 0].astype(np.int16), frame_bgr[:, :, 1].astype(np.int16), frame_bgr[:, :, 2].astype(np.int16)

    # 1) Żółty pasek HP gracza nad postacią (wykluczamy marginesy/HUD)
    y_lo, y_hi = int(h * 0.12), int(h * 0.78)
    roi_r, roi_g, roi_b = r[y_lo:y_hi, :], g[y_lo:y_hi, :], b[y_lo:y_hi, :]
    yellow_mask = (
        (roi_r >= 160) & (roi_g >= 130) & (roi_b <= 110)
        & ((roi_r - roi_b) >= 80) & ((roi_g - roi_b) >= 50)
    ).astype(np.uint8) * 255

    contours, _ = cv2.findContours(yellow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best_ratio: Optional[float] = None
    best_area = 0
    standard_bar_w = max(48.0, w * 0.055)
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if 3 <= bh <= 18 and 10 <= bw <= w * 0.22 and bw > bh * 1.5:
            area = bw * bh
            if area > best_area:
                best_area = area
                best_ratio = min(100.0, max(5.0, (bw / standard_bar_w) * 100.0))

    # 2) Jeśli to klatka 16:9 (szerokość > wysokość), sprawdź dodatkowo dolny zielony pasek HUD
    if w > h * 1.2:
        hy1, hy2 = int(h * 0.89), int(h * 0.965)
        hx1, hx2 = int(w * 0.34), int(w * 0.56)
        hud_r = r[hy1:hy2, hx1:hx2]
        hud_g = g[hy1:hy2, hx1:hx2]
        hud_b = b[hy1:hy2, hx1:hx2]
        green_hud = (
            (hud_g >= 120) & (hud_r <= 115) & (hud_b <= 115) & ((hud_g - hud_r) >= 35)
        ).astype(np.uint8) * 255
        g_cnts, _ = cv2.findContours(green_hud, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hud_max_w = max(80.0, (hx2 - hx1) * 0.85)
        for cnt in g_cnts:
            _, _, bw, bh = cv2.boundingRect(cnt)
            if 5 <= bh <= 26 and bw >= 12:
                hud_pct = min(100.0, max(3.0, (bw / hud_max_w) * 100.0))
                if best_ratio is None or bw * bh > best_area:
                    best_ratio = hud_pct
                    best_area = bw * bh

    return round(best_ratio, 1) if best_ratio is not None else None


def _count_enemy_bars(frame_bgr: np.ndarray) -> int:
    """Zlicza wyraźne czerwone paski zdrowia przeciwników w obszarze walki."""
    if frame_bgr is None or frame_bgr.size == 0:
        return 0
    h, w = frame_bgr.shape[:2]
    y_lo, y_hi = int(h * 0.12), int(h * 0.80)
    roi = frame_bgr[y_lo:y_hi, :]
    b, g, r = roi[:, :, 0].astype(np.int16), roi[:, :, 1].astype(np.int16), roi[:, :, 2].astype(np.int16)
    red_mask = (
        (r >= 150) & (g <= 95) & (b <= 85)
        & ((r - g) >= 60) & ((r - b) >= 70)
    ).astype(np.uint8) * 255
    kernel = np.ones((2, 5), np.uint8)
    red_mask = cv2.dilate(red_mask, kernel, iterations=1)
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    count = 0
    for cnt in contours:
        _, _, bw, bh = cv2.boundingRect(cnt)
        if 16 <= bw <= w * 0.22 and 3 <= bh <= 18 and bw >= bh * 2.2:
            count += 1
    return min(5, count)


def _check_hud_spell_cooldowns(start_bgr: np.ndarray, end_bgr: np.ndarray) -> Dict[str, Any]:
    """
    Sprawdza spadek jasności ikon spelli D/F/R na dolnym pasku HUD (wyłącznie w kadrze 16:9).
    W pionowym 9:16 dolny HUD często jest przycięty -> wtedy verified=False, brak zgadywania.
    """
    out = {"verified": False, "d_used": False, "f_used": False, "r_used": False}
    if start_bgr is None or end_bgr is None or start_bgr.shape != end_bgr.shape:
        return out
    h, w = start_bgr.shape[:2]
    if w < h * 1.2:
        return out

    # Pozycje orientacyjne slotów R, D, F w standardowym HUD 16:9 (dolny środek)
    slots = {
        "r_used": (int(w * 0.455), int(w * 0.478), int(h * 0.85), int(h * 0.90)),
        "d_used": (int(w * 0.483), int(w * 0.502), int(h * 0.85), int(h * 0.895)),
        "f_used": (int(w * 0.504), int(w * 0.523), int(h * 0.85), int(h * 0.895)),
    }
    s_hsv = cv2.cvtColor(start_bgr, cv2.COLOR_BGR2HSV)
    e_hsv = cv2.cvtColor(end_bgr, cv2.COLOR_BGR2HSV)
    for key, (x1, x2, y1, y2) in slots.items():
        s_patch = s_hsv[y1:y2, x1:x2]
        e_patch = e_hsv[y1:y2, x1:x2]
        if s_patch.size == 0 or e_patch.size == 0:
            continue
        s_val = float(np.mean(s_patch[:, :, 2]))
        e_val = float(np.mean(e_patch[:, :, 2]))
        # Ikona na cooldownie w LoL wyraźnie ciemnieje (spadek jasności o >= 28%)
        if s_val > 75.0 and (s_val - e_val) / s_val >= 0.28:
            out[key] = True
    out["verified"] = True
    return out


def inspect_clip_screens(
    video_path: str,
    peaks: Optional[list] = None,
    trim_start: float = 0.0,
    clip_duration: float = 15.0,
) -> Dict[str, Any]:
    """
    Przeprowadza lokalną analizę wizualną screenów klipu oraz czasów zabójstw.
    Zwraca twarde metryki gotowe do wstrzyknięcia w prompt / selektor tytułów i komentarzy.
    """
    kill_times = _extract_kill_times(peaks, trim_start=trim_start)
    if len(kill_times) >= 2:
        kill_span_s = round(max(0.1, kill_times[-1] - kill_times[0]), 2)
    else:
        kill_span_s = 0.0

    if kill_span_s > 0.0 and kill_span_s <= 2.6:
        combo_tempo = "INSTANT_BURST"
    elif kill_span_s > 2.6 and kill_span_s <= 6.0:
        combo_tempo = "FAST_RESET_CHAIN"
    elif kill_span_s > 6.0:
        combo_tempo = "EXTENDED_HUNT"
    else:
        combo_tempo = "SINGLE_TARGET_EXECUTION"

    result: Dict[str, Any] = {
        "frames_sampled": 0,
        "min_hp_pct": None,
        "hp_samples": [],
        "low_hp_survival": False,
        "clean_stomp": False,
        "enemies_in_fight": max(1, min(5, len(kill_times) or 1)),
        "kill_span_s": kill_span_s,
        "combo_tempo": combo_tempo,
        "hud_spells_used": {"verified": False, "d_used": False, "f_used": False, "r_used": False},
    }

    if not video_path or not os.path.isfile(video_path):
        return result

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return result

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        dur = (total_frames / fps) if (fps > 0 and total_frames > 0) else float(clip_duration or 15.0)
        anchor = kill_times[-1] if kill_times else (dur * 0.65)
        sample_ts = sorted({
            round(max(0.2, min(dur - 0.2, t)), 2)
            for t in (0.4, anchor - 1.0, anchor, anchor + 0.6, max(0.5, dur - 0.6))
        })

        sampled_frames: List[np.ndarray] = []
        hp_values: List[float] = []
        enemy_counts: List[int] = []

        for t in sample_ts:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            sampled_frames.append(frame)
            hp = _estimate_self_hp_from_frame(frame)
            if hp is not None:
                hp_values.append(hp)
            eb = _count_enemy_bars(frame)
            if eb > 0:
                enemy_counts.append(eb)

        result["frames_sampled"] = len(sampled_frames)
        if hp_values:
            min_hp = min(hp_values)
            result["hp_samples"] = hp_values
            result["min_hp_pct"] = min_hp
            result["low_hp_survival"] = (min_hp <= 22.0)
            result["clean_stomp"] = (min_hp >= 72.0)

        if enemy_counts:
            result["enemies_in_fight"] = max(result["enemies_in_fight"], max(enemy_counts))

        if len(sampled_frames) >= 2:
            result["hud_spells_used"] = _check_hud_spell_cooldowns(sampled_frames[0], sampled_frames[-1])
    finally:
        cap.release()

    return result


def _match_champion_name(raw_token: str) -> Optional[str]:
    clean_tok = re.sub(r"[^a-z0-9]", "", (raw_token or "").lower())
    if not clean_tok:
        return None
    for champ in _EXTENDED_CHAMPIONS:
        if re.sub(r"[^a-z0-9]", "", champ.lower()) == clean_tok:
            return "Kai'Sa" if champ.lower() in ("kaisa", "kai'sa") else champ
    return None


def detect_champion_local(video_path: str, default_champion: str = "Katarina") -> str:
    """
    Lokalna identyfikacja championa bez użycia Gemini Vision API (0 tokenów).
    Kolejność: nazwa pliku -> Medal DB -> OCR czatu/tooltipów/kill-feedu (3 klatki) -> domyślny.
    """
    fname = Path(video_path).name.lower() if video_path else ""
    clean_f = re.sub(r"[^a-z0-9]", "", fname)
    for champ in _EXTENDED_CHAMPIONS:
        clean_c = re.sub(r"[^a-z0-9]", "", champ.lower())
        if clean_c and clean_c in clean_f:
            return "Kai'Sa" if champ.lower() in ("kaisa", "kai'sa") else champ

    # Sprawdź Medal DB jeśli dostępny
    if video_path:
        try:
            try:
                from lol_agent.medal_db import get_clip_metadata
            except ImportError:
                from medal_db import get_clip_metadata
            meta = get_clip_metadata(video_path) or {}
            matched = _match_champion_name(meta.get("champion") or "")
            if matched:
                return matched
        except Exception:
            pass

    # Sprawdź OCR czatu, tooltipa i kill-feedu na 3 klatkach
    if video_path and os.path.isfile(video_path):
        cap = None
        try:
            _configure_tesseract()
            import pytesseract
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if total > 0:
                    chat_votes: Dict[str, int] = {}
                    direct_votes: Dict[str, int] = {}
                    killfeed_hits: List[str] = []

                    for frac in (0.25, 0.60, 0.88):
                        f_idx = min(max(0, total - 1), int(total * frac))
                        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                        ok, frame = cap.read()
                        if not ok or frame is None:
                            continue
                        h, w = frame.shape[:2]

                        # 1. Dolny-lewy czat + tooltip skilla/itemu (upscale 2x dla drobnej czcionki LoL)
                        chat_crop = frame[int(h * 0.58):int(h * 0.95), :int(w * 0.35)]
                        if chat_crop.size > 0:
                            chat_up = cv2.resize(chat_crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                            txt = pytesseract.image_to_string(chat_up, config="--psm 6") or ""
                            txt_low = txt.lower()

                            # Priorytet 1: bezposrednie przypisanie postaci przy nicku gracza lub tooltipie Source: ... [Champ]
                            for m in re.finditer(
                                r"(?:dwannellenga|source\s*:\s*\w+)\s*[\(\[]\s*([a-zA-Z' ]{3,16})\s*[\)\]]",
                                txt_low,
                            ):
                                m_champ = _match_champion_name(m.group(1))
                                if m_champ:
                                    direct_votes[m_champ] = direct_votes.get(m_champ, 0) + 1

                            # Priorytet 2: unikalne nazwy umiejętności / pasywek na ekranie
                            for sk, sk_champ in _SKILL_TO_CHAMPION.items():
                                if sk in txt_low:
                                    direct_votes[sk_champ] = direct_votes.get(sk_champ, 0) + 1

                            # Zbiorcze głosy po wystąpieniu pełnej nazwy championa w czacie
                            for champ in _EXTENDED_CHAMPIONS:
                                c_name = "Kai'Sa" if champ.lower() in ("kaisa", "kai'sa") else champ
                                if re.search(rf"\b{re.escape(champ.lower())}\b", txt_low):
                                    chat_votes[c_name] = chat_votes.get(c_name, 0) + 1

                        # 2. Prawy-górny kill-feed (tylko dla środkowej klatki jako zapas)
                        if abs(frac - 0.60) < 0.05:
                            kf_crop = frame[int(h * 0.04):int(h * 0.30), int(w * 0.55):w]
                            if kf_crop.size > 0:
                                kf_txt = (pytesseract.image_to_string(kf_crop, config="--psm 6") or "").lower()
                                for champ in _EXTENDED_CHAMPIONS:
                                    if re.search(rf"\b{re.escape(champ.lower())}\b", kf_txt):
                                        killfeed_hits.append("Kai'Sa" if champ.lower() in ("kaisa", "kai'sa") else champ)

                    if direct_votes:
                        return max(direct_votes.items(), key=lambda kv: kv[1])[0]
                    if chat_votes:
                        return max(chat_votes.items(), key=lambda kv: kv[1])[0]
                    if killfeed_hits:
                        return killfeed_hits[0]
        except Exception:
            pass
        finally:
            if cap is not None:
                cap.release()

    return default_champion or "Katarina"
