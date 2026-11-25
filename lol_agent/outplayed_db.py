"""
Odporny, wyłącznie do odczytu parser bazy Overwolf Outplayed (Riot API game events).

Czyta najnowszy backup JSON z:
  %APPDATA%\\Overwolf\\cghphpbjeabdkomiphingnegihoigeggcfphdofo\\media-db-backup\\library-*.json
oraz opcjonalną deltę na żywo z logów Chromium IndexedDB LevelDB:
  %LOCALAPPDATA%\\Overwolf\\CefBrowserCache\\Default\\IndexedDB\\overwolf-extension_cghphpbjeabdkomiphingnegihoigeggcfphdofo_0.indexeddb.leveldb\\*.log

Dostarcza deterministyczne tiery multikilli (pentakill -> assist_only), dokładne
znaczniki czasu zdarzeń w klipie, ulubione (isFavorite), wybranego bohatera, datę
i identyfikator meczu oraz grupowanie par klipów (_0 / _1).
"""

from __future__ import annotations

import json
import os
import re
import struct
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


OUTPLAYED_EXT_ID = "cghphpbjeabdkomiphingnegihoigeggcfphdofo"

OUTPLAYED_BACKUP_DIR = (
    Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    / "Overwolf"
    / OUTPLAYED_EXT_ID
    / "media-db-backup"
)
OUTPLAYED_IDB_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "Overwolf"
    / "CefBrowserCache"
    / "Default"
    / "IndexedDB"
    / f"overwolf-extension_{OUTPLAYED_EXT_ID}_0.indexeddb.leveldb"
)

TIER_RANKS: Dict[str, int] = {
    "assist_only": 0,
    "single_kill": 1,
    "double": 2,
    "triple": 3,
    "quadrakill": 4,
    "pentakill": 5,
}

TIER_LABEL_MAP: Dict[str, str] = {
    "penta_kill": "pentakill",
    "pentakill": "pentakill",
    "quadra_kill": "quadrakill",
    "quadrakill": "quadrakill",
    "triple_kill": "triple",
    "triple": "triple",
    "double_kill": "double",
    "double": "double",
    "kill": "single_kill",
    "single_kill": "single_kill",
    "assist": "assist_only",
    "assist_only": "assist_only",
}

_FOLDER_DT_RE = re.compile(
    r"(\d{2})-(\d{2})-(\d{4})[_ ](\d{2})-(\d{2})-(\d{2})(?:-\d+)?"
)
_TRAILING_COPY_RE = re.compile(r"_\d+$")
_MAX_IDB_BYTES = 12 * 1024 * 1024

_INDEX_LOCK = threading.Lock()
_CACHED_SIG: Optional[Tuple[Any, ...]] = None
_CACHED_INDEX: Dict[str, Dict[str, Any]] = {}


def _norm_path_key(path_str: str) -> str:
    return os.path.normcase(os.path.normpath(str(path_str or "").strip()))


def _normalize_tier_label(raw_label: Any, ev_type: Any = "") -> Optional[str]:
    lbl = str(raw_label or "").strip().lower()
    if lbl in TIER_LABEL_MAP:
        return TIER_LABEL_MAP[lbl]
    tp = str(ev_type or "").strip().lower()
    if tp in TIER_LABEL_MAP:
        return TIER_LABEL_MAP[tp]
    return None


def _parse_json_maybe(val: Any) -> Any:
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return val


def parse_outplayed_path_info(video_path: str | Path) -> Dict[str, str]:
    """Wyciąga folder meczu, znormalizowaną datę i bazowy klucz deduplikacji (_0/_1)."""
    p = Path(video_path)
    parent_name = p.parent.name if p.parent and p.parent.name else ""
    stem_base = _TRAILING_COPY_RE.sub("", p.stem).strip().lower()

    match_date = ""
    for candidate in (parent_name, p.stem):
        m = _FOLDER_DT_RE.search(candidate)
        if m:
            mm, dd, yyyy, hh, mi, _ss = m.groups()
            match_date = f"{yyyy}-{mm}-{dd} {hh}:{mi}"
            break

    match_folder = parent_name
    base_prefix = parent_name.lower() if parent_name else ""
    clip_base_key = f"{base_prefix}::{stem_base}" if base_prefix else stem_base
    return {
        "match_folder": match_folder,
        "match_date": match_date,
        "clip_base_key": clip_base_key,
    }


def _classify_clip_events(
    events_raw: Any, clip_duration_s: float = 0.0
) -> Tuple[str, int, Optional[float], Optional[float], Optional[float], int, int, List[Dict[str, Any]]]:
    """Wyznacza najwyższy tier Riot API, czas szczytowego eventu w sekundach i liczbę killi/asyst."""
    if not isinstance(events_raw, list):
        events_raw = []

    kills = 0
    assists = 0
    best_tier: Optional[str] = None
    best_rank = -1
    best_time_s: Optional[float] = None
    best_past_s: Optional[float] = None
    best_future_s: Optional[float] = None
    summary: List[Dict[str, Any]] = []

    for ev in events_raw:
        if not isinstance(ev, dict):
            continue
        ev_type = str(ev.get("type") or "").strip().lower()
        ev_data = _parse_json_maybe(ev.get("data"))
        if not isinstance(ev_data, dict):
            ev_data = {}
        ev_label = ev_data.get("label") or ev.get("label") or ""
        tier = _normalize_tier_label(ev_label, ev_type)

        if ev_type == "kill":
            kills += 1
        elif ev_type == "assist":
            assists += 1

        raw_time = ev.get("time")
        ev_time_s: Optional[float] = None
        if isinstance(raw_time, (int, float)):
            t_val = float(raw_time) / 1000.0
            if clip_duration_s > 0.0:
                t_val = max(0.0, min(clip_duration_s, t_val))
            else:
                t_val = max(0.0, t_val)
            ev_time_s = round(t_val, 2)

        timing = ev.get("timing")
        past_s: Optional[float] = None
        future_s: Optional[float] = None
        if isinstance(timing, dict):
            if isinstance(timing.get("past"), (int, float)):
                past_s = round(max(0.0, float(timing["past"]) / 1000.0), 2)
            if isinstance(timing.get("future"), (int, float)):
                future_s = round(max(0.0, float(timing["future"]) / 1000.0), 2)

        if tier is not None or ev_type in {"kill", "assist", "death", "victory"}:
            summary.append(
                {
                    "type": ev_type or (tier or "event"),
                    "label": str(ev_label or tier or ev_type),
                    "time_s": ev_time_s,
                }
            )

        if tier is None:
            continue
        rank = TIER_RANKS[tier]
        # Przy remisie tieru preferuj późniejsze wydarzenie (kulminacja walki / multikilla)
        if rank > best_rank or (
            rank == best_rank
            and ev_time_s is not None
            and (best_time_s is None or ev_time_s >= best_time_s)
        ):
            best_rank = rank
            best_tier = tier
            best_time_s = ev_time_s
            best_past_s = past_s
            best_future_s = future_s

    if best_tier is None:
        if kills > 0:
            best_tier = "single_kill"
            best_rank = TIER_RANKS["single_kill"]
        elif assists > 0:
            best_tier = "assist_only"
            best_rank = TIER_RANKS["assist_only"]
        else:
            best_tier = "assist_only"
            best_rank = 0

    return (
        best_tier,
        best_rank,
        best_time_s,
        best_past_s,
        best_future_s,
        kills,
        assists,
        summary,
    )


def _format_epoch_ms(epoch_ms: Any) -> str:
    if not isinstance(epoch_ms, (int, float)) or epoch_ms <= 0:
        return ""
    try:
        return datetime.fromtimestamp(float(epoch_ms) / 1000.0).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _build_clip_entry(
    clip_obj: Dict[str, Any],
    match_meta: Optional[Dict[str, Any]],
    source: str,
) -> Optional[Dict[str, Any]]:
    raw_path = str(clip_obj.get("path") or "").strip()
    if not raw_path:
        return None
    low_p = raw_path.replace("/", "\\").lower()
    if "\\recently deleted\\" in low_p or "\\.trash\\" in low_p:
        return None

    path_info = parse_outplayed_path_info(raw_path)
    start_s = clip_obj.get("startTime")
    end_s = clip_obj.get("endTime")
    clip_dur_s = 0.0
    if isinstance(start_s, (int, float)) and isinstance(end_s, (int, float)) and end_s > start_s:
        clip_dur_s = float(end_s - start_s)

    (
        event_tier,
        event_tier_rank,
        best_time_s,
        best_past_s,
        best_future_s,
        kills_in_clip,
        assists_in_clip,
        events_summary,
    ) = _classify_clip_events(clip_obj.get("events"), clip_duration_s=clip_dur_s)

    meta = match_meta or {}
    est_first_kill_s = best_time_s
    est_last_kill_s = best_time_s
    if (
        best_time_s is not None
        and event_tier_rank >= 2
        and best_past_s is not None
        and best_future_s is not None
        and abs(best_past_s - best_future_s) <= 0.25
        and best_future_s >= 8.5
    ):
        raw_last = max(best_time_s, best_time_s + best_future_s - 8.0)
        if clip_dur_s > 0.0:
            raw_last = min(clip_dur_s, raw_last)
        est_last_kill_s = round(raw_last, 2)
        est_first_kill_s = round(max(0.0, min(best_time_s, best_time_s - best_past_s + 12.0)), 2)

    champion = str(
        meta.get("selectedChampion")
        or clip_obj.get("selectedChampion")
        or clip_obj.get("champion")
        or ""
    ).strip()

    match_kda = ""
    if all(k in meta for k in ("killCount", "deathCount", "assistCount")):
        try:
            match_kda = f"{int(meta['killCount'])}/{int(meta['deathCount'])}/{int(meta['assistCount'])}"
        except Exception:
            match_kda = ""

    match_date = path_info["match_date"] or str(meta.get("match_date") or "")

    return {
        "source": source,
        "raw_path": raw_path,
        "filename_lower": Path(raw_path).name.lower(),
        "champion": champion,
        "is_favorite": bool(clip_obj.get("isFavorite", False)),
        "event_tier": event_tier,
        "event_tier_rank": event_tier_rank,
        "best_event_time_s": best_time_s,
        "best_event_past_s": best_past_s,
        "best_event_future_s": best_future_s,
        "est_first_kill_s": est_first_kill_s,
        "est_last_kill_s": est_last_kill_s,
        "total_kills_in_clip": kills_in_clip,
        "total_assists_in_clip": assists_in_clip,
        "match_folder": path_info["match_folder"],
        "match_date": match_date,
        "clip_base_key": path_info["clip_base_key"],
        "match_kda": match_kda,
        "is_victory": meta.get("isVictory"),
        "clip_duration_s": round(clip_dur_s, 2) if clip_dur_s > 0.0 else None,
        "events_summary": events_summary,
    }


def _extract_matches_from_backup_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    matches: List[Dict[str, Any]] = []
    for k, val in payload.items():
        if not str(k).startswith("matches_"):
            continue
        parsed = _parse_json_maybe(val)
        if isinstance(parsed, list):
            matches.extend(m for m in parsed if isinstance(m, dict))
    return matches


def _load_backup_records(backup_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Ładuje najnowszą poprawną kopię library-*.json (z fallbackiem na starsze przy korupcji)."""
    index: Dict[str, Dict[str, Any]] = {}
    if not backup_dir.exists():
        return index

    candidates = sorted(
        backup_dir.glob("library-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for json_path in candidates:
        try:
            with json_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            continue

        matches = _extract_matches_from_backup_payload(payload)
        if not matches and "matches_0" not in payload:
            continue

        for m in matches:
            game_id = m.get("gameId")
            if game_id is not None and int(game_id) != 5426:
                continue
            info = _parse_json_maybe(m.get("info"))
            if not isinstance(info, dict):
                info = {}
            match_meta = {
                **info,
                "match_date": _format_epoch_ms(m.get("startTime")),
            }
            medias = m.get("medias")
            if not isinstance(medias, list):
                continue
            for clip_obj in medias:
                if not isinstance(clip_obj, dict):
                    continue
                entry = _build_clip_entry(clip_obj, match_meta, source="outplayed_backup")
                if entry:
                    _store_entry_keys(index, entry)
        break

    return index


def _extract_balanced_json_at(text: str, start_idx: int, max_len: int = 128000) -> Optional[Tuple[Any, int]]:
    n = min(len(text), start_idx + max_len)
    if start_idx < 0 or start_idx >= n or text[start_idx] not in "{[":
        return None
    open_ch = text[start_idx]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for idx in range(start_idx, n):
        ch = text[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                snippet = text[start_idx : idx + 1]
                try:
                    return json.loads(snippet), idx + 1
                except Exception:
                    return None
    return None


def _upsert_merged(target_map: Dict[str, Dict[str, Any]], entry: Dict[str, Any]) -> None:
    p_key = _norm_path_key(entry["raw_path"])
    f_key = f"name::{entry['filename_lower']}"
    existing = target_map.get(p_key) or target_map.get(f_key)
    merged = _merge_entry(existing, entry)
    _store_entry_keys(target_map, merged)


def _parse_idb_text_fragments(text: str) -> Dict[str, Dict[str, Any]]:
    """Wyciąga rekordy meczów/klipów z surowego tekstu logu IndexedDB."""
    delta: Dict[str, Dict[str, Any]] = {}

    # 1. Pełne rekordy meczów LoL (zawierają info.selectedChampion oraz listę medias)
    for m in re.finditer(r'\{\s*"(?:gameId|id)"\s*:', text):
        parsed_res = _extract_balanced_json_at(text, m.start(), max_len=256000)
        if not parsed_res:
            continue
        obj, _ = parsed_res
        if not isinstance(obj, dict) or not isinstance(obj.get("medias"), list):
            continue
        game_id = obj.get("gameId")
        if game_id is not None and int(game_id) != 5426:
            continue
        info = _parse_json_maybe(obj.get("info"))
        if not isinstance(info, dict):
            info = {}
        match_meta = {**info, "match_date": _format_epoch_ms(obj.get("startTime"))}
        for clip_obj in obj["medias"]:
            if not isinstance(clip_obj, dict):
                continue
            entry = _build_clip_entry(clip_obj, match_meta, source="outplayed_live")
            if entry:
                _upsert_merged(delta, entry)

    # 2. Pojedyncze obiekty klipów z '"path":'... nawet gdy rekord meczu przecięto na granicy bloku LevelDB
    for m in re.finditer(r'"path"\s*:\s*"([^"]+\.(?:mp4|mov|mkv|avi))"', text, flags=re.IGNORECASE):
        pos = m.start()
        search_from = max(0, pos - 4096)
        brace_positions = [i for i in range(pos, search_from - 1, -1) if text[i] == "{"]
        for bp in brace_positions[:12]:
            parsed_res = _extract_balanced_json_at(text, bp, max_len=32000)
            if not parsed_res:
                continue
            obj, _ = parsed_res
            if isinstance(obj, dict) and obj.get("path"):
                window_before = text[max(0, bp - 16000) : bp]
                champ_matches = re.findall(r'"selectedChampion"\s*:\s*"([^"]{2,30})"', window_before)
                match_meta: Dict[str, Any] = {}
                if champ_matches:
                    match_meta["selectedChampion"] = champ_matches[-1]
                kda_m = re.findall(
                    r'"killCount"\s*:\s*(\d+)\s*,\s*"deathCount"\s*:\s*(\d+)\s*,\s*"assistCount"\s*:\s*(\d+)',
                    window_before,
                )
                if kda_m:
                    kc, dc, ac = kda_m[-1]
                    match_meta.update({"killCount": int(kc), "deathCount": int(dc), "assistCount": int(ac)})
                entry = _build_clip_entry(obj, match_meta or None, source="outplayed_live")
                if entry:
                    _upsert_merged(delta, entry)
                break

    return delta


def _read_v8_varint(buf: bytes, pos: int) -> Tuple[Optional[int], int]:
    val = 0
    shift = 0
    n = len(buf)
    while pos < n and shift < 35:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, pos
        shift += 7
    return None, pos


def _read_v8_string(buf: bytes, pos: int, max_chars: int = 1024) -> Tuple[Optional[str], int]:
    if pos >= len(buf):
        return None, pos
    tag = buf[pos]
    if tag not in (0x22, 0x63):  # '"' OneByteString | 'c' TwoByteString
        return None, pos
    byte_len, p = _read_v8_varint(buf, pos + 1)
    if byte_len is None or byte_len < 0 or byte_len > max_chars * (2 if tag == 0x63 else 1) or p + byte_len > len(buf):
        return None, pos
    raw = buf[p : p + byte_len]
    try:
        txt = raw.decode("utf-16le" if tag == 0x63 else "utf-8", errors="ignore")
        return txt, p + byte_len
    except Exception:
        return None, pos


def _read_v8_number(buf: bytes, pos: int) -> Tuple[Optional[float], int]:
    if pos >= len(buf):
        return None, pos
    tag = buf[pos]
    if tag == 0x49:  # 'I' ZigZag varint Int32
        raw, p = _read_v8_varint(buf, pos + 1)
        if raw is None:
            return None, pos
        return float((raw >> 1) ^ -(raw & 1)), p
    if tag == 0x55:  # 'U' unsigned varint Uint32
        raw, p = _read_v8_varint(buf, pos + 1)
        if raw is None:
            return None, pos
        return float(raw), p
    if tag == 0x4E and pos + 9 <= len(buf):  # 'N' IEEE-754 double
        try:
            val = struct.unpack("<d", buf[pos + 1 : pos + 9])[0]
            if val == val:  # skip NaN
                return float(val), pos + 9
        except Exception:
            pass
    return None, pos


def _extract_v8_match_meta_chunk(chunk: bytes) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    sc_idx = chunk.rfind(b'"\x10selectedChampion')
    if sc_idx != -1:
        champ, _ = _read_v8_string(chunk, sc_idx + 18, max_chars=40)
        if champ:
            meta["selectedChampion"] = champ.strip()
        tail = chunk[sc_idx : min(len(chunk), sc_idx + 220)]
        for field_key in (b"killCount", b"assistCount", b"deathCount"):
            fk = b'"' + bytes([len(field_key)]) + field_key
            idx = tail.find(fk)
            if idx != -1:
                num, _ = _read_v8_number(tail, idx + len(fk))
                if num is not None and 0.0 <= num <= 200.0:
                    meta[field_key.decode("ascii")] = int(num)
        iv_idx = tail.find(b'"\tisVictory')
        if iv_idx != -1 and iv_idx + 11 < len(tail):
            b_tag = tail[iv_idx + 11]
            if b_tag in (0x54, 0x46):
                meta["isVictory"] = b_tag == 0x54
    return meta


def _parse_idb_v8_records(raw_bytes: bytes) -> Dict[str, Dict[str, Any]]:
    """
    Dekoduje rekordy Overwolf Outplayed zapisane binarnie w formacie V8 Structured Clone
    wewnątrz plików WAL LevelDB (*.log).
    """
    delta: Dict[str, Dict[str, Any]] = {}
    if not raw_bytes:
        return delta

    # 1. Zmapuj foldery meczów -> metadane (selectedChampion, KDA) z najnowszych nagłówków
    folder_meta_map: Dict[str, Dict[str, Any]] = {}
    for m_sc in re.finditer(re.escape(b'"\x10selectedChampion'), raw_bytes):
        sc_pos = m_sc.start()
        meta = _extract_v8_match_meta_chunk(raw_bytes[sc_pos : min(len(raw_bytes), sc_pos + 240)])
        if not meta.get("selectedChampion"):
            continue
        fwd = raw_bytes[sc_pos : min(len(raw_bytes), sc_pos + 6000)]
        p_match = fwd.find(b'"\x04path')
        if p_match != -1:
            clip_p, _ = _read_v8_string(fwd, p_match + 6, max_chars=512)
            if clip_p:
                mf = parse_outplayed_path_info(clip_p)["match_folder"]
                if mf:
                    folder_meta_map[mf] = meta

    # 2. Przetwórz kolejno obiekty klipów (ostatni wpis w WAL wygrywa po _upsert_merged)
    path_marker = b'"\x04path'
    for m_path in re.finditer(re.escape(path_marker), raw_bytes):
        p_start = m_path.start()
        clip_path, p_after = _read_v8_string(raw_bytes, p_start + len(path_marker), max_chars=512)
        if not clip_path or not re.search(r"\.(?:mp4|mov|mkv|avi)$", clip_path, flags=re.IGNORECASE):
            continue

        # Wyznacz bezpieczny koniec bieżącego klipu (do kolejnego klipu / nowego meczu)
        search_limit = min(len(raw_bytes), p_after + 16384)
        next_candidates = []
        for sep in (b'"\x04path', b'o"\tstartTimeN', b'"\x10selectedChampion'):
            nxt = raw_bytes.find(sep, p_after + 12, search_limit)
            if nxt != -1:
                next_candidates.append(nxt)
        clip_end_pos = min(next_candidates) if next_candidates else search_limit
        clip_tail = raw_bytes[p_after:clip_end_pos]
        clip_head = raw_bytes[max(0, p_start - 420) : p_start]

        # Czasy start/end klipu i ulubione mogą stać bezpośrednio przed "path"
        start_time = None
        end_time = None
        st_idx = clip_head.rfind(b'"\tstartTime')
        if st_idx != -1:
            start_time, _ = _read_v8_number(clip_head, st_idx + 11)
        et_idx = clip_head.rfind(b'"\x07endTime')
        if et_idx != -1:
            end_time, _ = _read_v8_number(clip_head, et_idx + 9)
        if isinstance(start_time, float) and isinstance(end_time, float) and end_time > start_time:
            if (end_time - start_time) > 1000.0:
                start_time /= 1000.0
                end_time /= 1000.0
        else:
            start_time = None
            end_time = None

        is_favorite = False
        for seg_chk in (clip_head, clip_tail[:400]):
            fv_idx = seg_chk.rfind(b'"\nisFavorite')
            if fv_idx != -1 and fv_idx + 12 < len(seg_chk):
                b_tag = seg_chk[fv_idx + 12]
                if b_tag in (0x54, 0x46):
                    is_favorite = b_tag == 0x54

        # Wyciągnij zdarzenia (kill/assist/death, time ms, past/future, label)
        events: List[Dict[str, Any]] = []
        type_marker = b'"\x04type'
        for m_ev in re.finditer(re.escape(type_marker), clip_tail):
            ev_type, ev_after = _read_v8_string(clip_tail, m_ev.start() + len(type_marker), max_chars=32)
            if not ev_type or ev_type.lower() not in {"kill", "assist", "death", "victory"}:
                continue
            nxt_ev = clip_tail.find(type_marker, ev_after)
            ev_end = min(len(clip_tail), nxt_ev if nxt_ev != -1 else (ev_after + 520))
            ev_slice = clip_tail[ev_after:ev_end]

            ev_time_ms = None
            t_idx = ev_slice.find(b'"\x04time')
            if t_idx != -1:
                ev_time_ms, _ = _read_v8_number(ev_slice, t_idx + 6)

            timing_dict: Dict[str, float] = {}
            past_idx = ev_slice.find(b'"\x04past')
            if past_idx != -1:
                past_ms, _ = _read_v8_number(ev_slice, past_idx + 6)
                if past_ms is not None:
                    timing_dict["past"] = past_ms
            fut_idx = ev_slice.find(b'"\x06future')
            if fut_idx != -1:
                fut_ms, _ = _read_v8_number(ev_slice, fut_idx + 8)
                if fut_ms is not None:
                    timing_dict["future"] = fut_ms

            ev_label = ""
            lbl_idx = ev_slice.find(b'"\x05label')
            if lbl_idx != -1:
                lbl_s, _ = _read_v8_string(ev_slice, lbl_idx + 7, max_chars=32)
                if lbl_s:
                    ev_label = lbl_s

            events.append({
                "type": ev_type.lower(),
                "time": ev_time_ms,
                "timing": timing_dict,
                "data": {"label": ev_label} if ev_label else {},
            })

        mf = parse_outplayed_path_info(clip_path)["match_folder"]
        match_meta = dict(folder_meta_map.get(mf) or {})
        if not match_meta.get("selectedChampion"):
            # Fallback do najbliższego poprzedzającego nagłówka info w buforze (max 65 KB wstecz)
            back = raw_bytes[max(0, p_start - 65536) : p_start]
            match_meta = _extract_v8_match_meta_chunk(back)

        clip_obj: Dict[str, Any] = {
            "path": clip_path,
            "isFavorite": is_favorite,
            "events": events,
        }
        if start_time is not None and end_time is not None:
            clip_obj["startTime"] = start_time
            clip_obj["endTime"] = end_time
        if match_meta.get("selectedChampion"):
            clip_obj["selectedChampion"] = match_meta["selectedChampion"]

        entry = _build_clip_entry(clip_obj, match_meta or None, source="outplayed_live")
        if entry:
            _upsert_merged(delta, entry)

    return delta


def _load_live_idb_delta(idb_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Bezpiecznie skanuje tylko do odczytu 2 najnowsze pliki *.log z IndexedDB LevelDB (JSON + V8 binary)."""
    delta: Dict[str, Dict[str, Any]] = {}
    if not idb_dir.exists():
        return delta

    try:
        log_files = sorted(
            idb_dir.glob("*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:2]
    except Exception:
        return delta

    for log_path in reversed(log_files):
        try:
            with log_path.open("rb") as f:
                raw_bytes = f.read(_MAX_IDB_BYTES)
        except Exception:
            continue
        if not raw_bytes:
            continue
        for entry in _parse_idb_v8_records(raw_bytes).values():
            _upsert_merged(delta, entry)
        text = raw_bytes.decode("utf-8", errors="ignore")
        parsed = _parse_idb_text_fragments(text)
        for entry in parsed.values():
            _upsert_merged(delta, entry)

    return delta


def _store_entry_keys(index: Dict[str, Dict[str, Any]], entry: Dict[str, Any]) -> None:
    path_key = _norm_path_key(entry["raw_path"])
    fname_key = f"name::{entry['filename_lower']}"
    index[path_key] = entry
    index[fname_key] = entry


def _merge_entry(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return dict(incoming)
    merged = dict(existing)
    for k, v in incoming.items():
        if v in (None, "", []):
            continue
        merged[k] = v
    # Zachowaj najwyższy znany tier, jeśli delta nie ma lepszego eventu (np. tylko zmiana isFavorite)
    if existing.get("event_tier_rank", -1) > incoming.get("event_tier_rank", -1):
        for keep_k in (
            "event_tier",
            "event_tier_rank",
            "best_event_time_s",
            "best_event_past_s",
            "best_event_future_s",
            "est_first_kill_s",
            "est_last_kill_s",
            "total_kills_in_clip",
            "total_assists_in_clip",
            "events_summary",
        ):
            if existing.get(keep_k) is not None:
                merged[keep_k] = existing[keep_k]
    if not merged.get("champion") and existing.get("champion"):
        merged["champion"] = existing["champion"]
    if not merged.get("match_kda") and existing.get("match_kda"):
        merged["match_kda"] = existing["match_kda"]
    return merged


def _compute_dir_signature(backup_dir: Path, idb_dir: Path) -> Tuple[Any, ...]:
    sig_parts: List[Any] = [str(backup_dir), str(idb_dir)]
    try:
        if backup_dir.exists():
            newest = sorted(
                backup_dir.glob("library-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:1]
            for p in newest:
                st = p.stat()
                sig_parts.append(("b", p.name, int(st.st_mtime_ns), st.st_size))
    except Exception:
        pass
    try:
        if idb_dir.exists():
            logs = sorted(
                idb_dir.glob("*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:2]
            for p in logs:
                st = p.stat()
                sig_parts.append(("l", p.name, int(st.st_mtime_ns), st.st_size))
    except Exception:
        pass
    return tuple(sig_parts)


def load_outplayed_index(
    backup_dir: Optional[Path] = None,
    idb_dir: Optional[Path] = None,
    force_reload: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Zwraca zunifikowany indeks metadanych Outplayed (backup JSON + delta IndexedDB).

    W testach pytest (PYTEST_CURRENT_TEST) przy domyślnych katalogach (oba None)
    zwraca pusty słownik, aby nie przeciekały realne pliki użytkownika z AppData.
    """
    global _CACHED_SIG, _CACHED_INDEX

    if backup_dir is None and idb_dir is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return {}

    b_dir = Path(backup_dir) if backup_dir is not None else OUTPLAYED_BACKUP_DIR
    i_dir = Path(idb_dir) if idb_dir is not None else OUTPLAYED_IDB_DIR
    sig = _compute_dir_signature(b_dir, i_dir)

    with _INDEX_LOCK:
        if not force_reload and _CACHED_SIG == sig:
            return dict(_CACHED_INDEX)

        combined = _load_backup_records(b_dir)
        delta = _load_live_idb_delta(i_dir)
        seen_delta_ids: set[int] = set()
        for inc in delta.values():
            if id(inc) in seen_delta_ids:
                continue
            seen_delta_ids.add(id(inc))
            p_key = _norm_path_key(inc["raw_path"])
            f_key = f"name::{inc['filename_lower']}"
            existing = combined.get(p_key) or combined.get(f_key)
            merged = _merge_entry(existing, inc)
            _store_entry_keys(combined, merged)

        _CACHED_SIG = sig
        _CACHED_INDEX = combined
        return dict(combined)


def get_outplayed_clip_info(
    video_path: str | Path,
    index: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Zwraca wpis Riot API Outplayed dla danego klipu lub None jeśli brak w indeksie."""
    idx = index if index is not None else load_outplayed_index()
    if not idx:
        return None
    p = Path(video_path)
    norm_key = _norm_path_key(str(p))
    if norm_key in idx:
        return dict(idx[norm_key])
    try:
        res_key = _norm_path_key(str(p.resolve()))
        if res_key in idx:
            return dict(idx[res_key])
    except Exception:
        pass
    fname_key = f"name::{p.name.lower()}"
    if fname_key in idx:
        return dict(idx[fname_key])
    return None


def summarize_clip_catalog(clips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Buduje podsumowanie katalogu klipów po tierach, bohaterach, ulubionych i meczach."""
    tier_counts: Dict[str, int] = {
        "pentakill": 0,
        "quadrakill": 0,
        "triple": 0,
        "double": 0,
        "single_kill": 0,
        "assist_only": 0,
        "unknown": 0,
    }
    by_champion: Dict[str, Dict[str, int]] = {}
    matches_map: Dict[str, Dict[str, Any]] = {}
    favorites_count = 0
    multikill_clips = 0
    unpublished_clips = 0

    for c in clips:
        if not isinstance(c, dict):
            continue
        if not c.get("already_published", False):
            unpublished_clips += 1
        if c.get("is_favorite", False):
            favorites_count += 1

        tier = str(c.get("event_tier") or c.get("pre_action") or "").strip().lower()
        tier_rank = c.get("event_tier_rank")
        if tier in tier_counts:
            tier_counts[tier] += 1
        else:
            tier_counts["unknown"] += 1

        if (isinstance(tier_rank, (int, float)) and tier_rank >= 2) or tier in {
            "double",
            "triple",
            "quadrakill",
            "pentakill",
        }:
            multikill_clips += 1

        champ = str(c.get("champion") or "").strip() or "Nieznany"
        if champ not in by_champion:
            by_champion[champ] = {"total": 0, "multikill": 0, "favorites": 0}
        by_champion[champ]["total"] += 1
        if (isinstance(tier_rank, (int, float)) and tier_rank >= 2) or tier in {
            "double",
            "triple",
            "quadrakill",
            "pentakill",
        }:
            by_champion[champ]["multikill"] += 1
        if c.get("is_favorite", False):
            by_champion[champ]["favorites"] += 1

        m_folder = str(c.get("match_folder") or "").strip()
        if m_folder:
            if m_folder not in matches_map:
                matches_map[m_folder] = {
                    "match_folder": m_folder,
                    "match_date": str(c.get("match_date") or ""),
                    "champion": champ if champ != "Nieznany" else "",
                    "clips_count": 0,
                    "multikills_count": 0,
                    "highest_tier": "unknown",
                    "_highest_rank": -1,
                    "match_kda": str(c.get("match_kda") or ""),
                }
            me = matches_map[m_folder]
            me["clips_count"] += 1
            if not me["champion"] and champ != "Nieznany":
                me["champion"] = champ
            if not me["match_kda"] and c.get("match_kda"):
                me["match_kda"] = str(c.get("match_kda"))
            rk = int(tier_rank) if isinstance(tier_rank, (int, float)) else TIER_RANKS.get(tier, -1)
            if rk >= 2:
                me["multikills_count"] += 1
            if rk > me["_highest_rank"]:
                me["_highest_rank"] = rk
                me["highest_tier"] = tier or "unknown"

    matches_list = sorted(
        matches_map.values(),
        key=lambda m: (m.get("match_date") or "", m.get("match_folder") or ""),
        reverse=True,
    )
    for m in matches_list:
        m.pop("_highest_rank", None)

    return {
        "total_clips": len(clips),
        "unpublished_clips": unpublished_clips,
        "favorites_count": favorites_count,
        "multikill_clips": multikill_clips,
        "tier_counts": tier_counts,
        "by_champion": by_champion,
        "matches_count": len(matches_list),
        "matches": matches_list,
    }
