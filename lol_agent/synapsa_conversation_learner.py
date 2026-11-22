"""
Shortsyt — Most Pamięci Inżynierskiej (Etap 7)
===============================================
Łączy trzy realne źródła wiedzy w ustrukturyzowaną pamięć przyczynowo-skutkową (`engineering_lessons_memory.json`)
oraz zasila zbiory treningowe Synapsy (`dataset_shortsyt_titles.jsonl` + `moj_styl_kodowania.jsonl`):
  1. Wiersze [x] z `TODO.md` (cel -> wdrożona zmiana -> zmierzony rezultat).
  2. Zapis rozmów z `.system_generated/logs/transcript.jsonl` / `transcript_full.jsonl`
     (zgłoszenie użytkownika -> edycje `edit_file`/`write_file` w Shortsyt -> wynik testów/renderów).
  3. Tracker delt atrybutów `Before -> After` między powtórnymi renderami tego samego klipu w `.recipe.json`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOL_AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = LOL_AGENT_DIR.parent
DEFAULT_MEMORY_PATH = LOL_AGENT_DIR / "engineering_lessons_memory.json"
DEFAULT_VERIFICATION_LOG = LOL_AGENT_DIR / "synapsa_verification_log.jsonl"
DEFAULT_TODO_PATH = PROJECT_ROOT / "TODO.md"
DEFAULT_DIRECTIVE_PATH = LOL_AGENT_DIR / "learning_directive.json"
DEFAULT_GOLDEN_BASELINE_PATH = PROJECT_ROOT / "GOLDEN_BASELINE_PARAMS.json"
DEFAULT_ENGINE_RULES_PATH = LOL_AGENT_DIR / "engine_rules.json"
DEFAULT_USER_FEEDBACK_PATH = LOL_AGENT_DIR / "user_feedback_history.json"
DEFAULT_CODING_STYLE_PATH = Path(
    os.environ.get("SYNAPSA_CODING_DATASET", r"C:\Users\mz100\PycharmProjects\Synapsa\moj_styl_kodowania.jsonl")
)
DEFAULT_BRAIN_ROOT = Path(r"C:\Users\mz100\.gemini\antigravity\brain")
ACTIVE_CONVERSATION_ID = "5f422934-7286-47f1-b62f-d3275784a8da"

_CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".bat"}
_VERIF_RE = re.compile(
    r"(\d+\s+passed(?:\s+in\s+[0-9.]+s)?|QUALITY SCORE:\s*\d+/100|"
    r"slowmo11_13_jumps=\d+|clip\(>0\.96\)=\d+|video_id[\"':=\s]+[A-Za-z0-9_-]{8,15}|"
    r"https://www\.youtube\.com/shorts/[A-Za-z0-9_-]+|built in \d+|TESTY PASSED)",
    re.I,
)


def _atomic_write_json(path: Path, data: Any) -> None:
    """Atomowo zapisuje JSON przez plik tymczasowy i os.replace w tym samym katalogu."""
    import threading
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def _clean_text(txt: str, max_len: int = 320) -> str:
    cleaned = re.sub(r"[`*]+", "", str(txt or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max(0, max_len - 3)].rstrip() + "..."


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _decode_transcript_str(val: Any) -> str:
    """Dekoduje ciągi z transcript.jsonl `args` (czasem podwójnie zjsonifikowane lub przycięte)."""
    if val is None:
        return ""
    if not isinstance(val, str):
        return str(val)
    s = val
    if s.startswith('"'):
        try:
            dec = json.loads(s)
            if isinstance(dec, str):
                return dec
        except Exception:
            # Jeśli string z args został ucięty przed domknięciem, odkoduj bezpiecznie fragment
            inner = s[1:-1] if s.endswith('"') else s[1:]
            inner = inner.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
            return inner
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 1. EKSTRAKTOR LEKCJI Z TODO.md
# ══════════════════════════════════════════════════════════════════════════════

def extract_lessons_from_todo(todo_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Wyciąga ukończone lekcje [x] z tabel TODO.md jako wpisy Cause -> Effect."""
    tp = Path(todo_path) if todo_path is not None else DEFAULT_TODO_PATH
    if not tp.is_file():
        return []

    lessons: List[Dict[str, Any]] = []
    current_section = ""
    seen_ids = set()

    for line in tp.read_text(encoding="utf-8", errors="replace").splitlines():
        st = line.strip()
        if st.startswith("## "):
            current_section = _clean_text(st.lstrip("# "), 120)
            continue
        if not st.startswith("|") or st.startswith("| :---") or st.startswith("| Zadanie"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 6:
            continue
        module, goal, change, state, result, expected = cells[:6]
        if "[x]" not in state.lower():
            continue

        lid = "todo_" + _stable_id(module, change[:80])
        if lid in seen_ids:
            continue
        seen_ids.add(lid)

        files = sorted(set(re.findall(r"[A-Za-z0-9_./\\-]+\.(?:py|jsx?|tsx?|json|bat)", f"{module} {change}")))
        lessons.append({
            "lesson_id": lid,
            "kind": "todo_completed",
            "section": current_section,
            "module": _clean_text(module, 120),
            "goal": _clean_text(goal, 180),
            "change": _clean_text(change, 260),
            "measured_result": _clean_text(result, 240),
            "expected_effect": _clean_text(expected, 160),
            "affected_files": files[:8],
        })

    return lessons


# ══════════════════════════════════════════════════════════════════════════════
# 2. EKSTRAKTOR LEKCJI Z TRANSKRYPTU ROZMOWY + KOD DO moj_styl_kodowania.jsonl
# ══════════════════════════════════════════════════════════════════════════════

def _extract_user_request_text(content: str) -> str:
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content or "", re.S)
    txt = m.group(1) if m else (content or "")
    txt = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", txt, flags=re.S)
    return _clean_text(txt, 240)


def _iter_transcript_steps(transcript_path: Path) -> List[Dict[str, Any]]:
    """Wczytuje kroki z transcript.jsonl, dociągając przycięte `tool_calls` z transcript_full.jsonl jeśli istnieje."""
    full_path = transcript_path.with_name("transcript_full.jsonl")
    needed_indices = set()
    compact_rows: List[Dict[str, Any]] = []

    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            compact_rows.append(obj)
            t_fields = obj.get("truncated_fields") or []
            if "tool_calls" in t_fields:
                for tc in (obj.get("tool_calls") or []):
                    if tc.get("name") in ("edit_file", "write_file"):
                        idx = obj.get("step_index")
                        if idx is not None:
                            needed_indices.add(idx)

    full_by_idx: Dict[Any, Dict[str, Any]] = {}
    if needed_indices and full_path.is_file():
        with open(full_path, "r", encoding="utf-8", errors="replace") as ff:
            for line in ff:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                idx = obj.get("step_index")
                if idx in needed_indices:
                    full_by_idx[idx] = obj

    merged: List[Dict[str, Any]] = []
    for obj in compact_rows:
        idx = obj.get("step_index")
        merged.append(full_by_idx.get(idx, obj))
    return merged


def _is_shortsyt_code_file(path_str: str) -> Optional[str]:
    norm = path_str.replace("/", "\\").strip()
    if "shortsyt" not in norm.lower():
        return None
    low = norm.lower()
    if low.endswith("todo.md") or ".recipe.json" in low or ".meta.json" in low:
        return None
    ext = Path(norm).suffix.lower()
    if ext not in _CODE_EXTS:
        return None
    idx = low.find("shortsyt\\")
    return norm[idx + len("shortsyt\\"):] if idx >= 0 else Path(norm).name


def extract_lessons_from_transcripts(
    transcript_paths: Optional[List[Path]] = None,
    max_lessons: int = 35,
    max_coding_samples: int = 45,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Parsuje transkrypty rozmów: łączy prośbę użytkownika -> realne edycje kodu w Shortsyt -> weryfikację.
    Zwraca (engineering_fixes, alpaca_coding_samples).
    """
    if transcript_paths is None:
        cand = DEFAULT_BRAIN_ROOT / ACTIVE_CONVERSATION_ID / ".system_generated" / "logs" / "transcript.jsonl"
        transcript_paths = [cand] if cand.is_file() else []

    fixes: List[Dict[str, Any]] = []
    coding_samples: List[Dict[str, str]] = []
    seen_coding_hashes = set()

    for tp in transcript_paths:
        tp = Path(tp)
        if not tp.is_file():
            continue
        steps = _iter_transcript_steps(tp)
        current_prompt = ""
        current_files: List[str] = []
        current_edits: List[Dict[str, str]] = []
        current_verifs: List[str] = []

        def _flush_turn():
            if not (current_prompt and current_edits):
                return
            fid = "conv_" + _stable_id(tp.parent.parent.parent.name, current_prompt[:80], ",".join(current_files[:3]))
            fixes.append({
                "lesson_id": fid,
                "kind": "conversation_fix",
                "user_request": current_prompt,
                "affected_files": sorted(set(current_files))[:8],
                "edit_count": len(current_edits),
                "fix_summary": _clean_text(" | ".join(e["summary"] for e in current_edits[:3]), 260),
                "verification": sorted(set(current_verifs))[:4],
            })

        for step in steps:
            stype = step.get("type")
            content = str(step.get("content") or "")

            if stype == "USER_INPUT":
                req = _extract_user_request_text(content)
                # Pomijaj jednowyrazowe potwierdzenia typu "tak" / "Continue" jako osobne tematy
                if len(req) >= 12 and req.lower() not in ("continue", "tak", "ok"):
                    _flush_turn()
                    current_prompt = req
                    current_files = []
                    current_edits = []
                    current_verifs = []
                continue

            # Wyłap twarde fakty weryfikacyjne z wyników narzędzi / komunikatów systemowych
            if content:
                for m in _VERIF_RE.findall(content):
                    m_clean = _clean_text(m, 80)
                    if m_clean and m_clean not in current_verifs:
                        current_verifs.append(m_clean)

            for tc in (step.get("tool_calls") or []):
                tname = tc.get("name")
                if tname not in ("edit_file", "write_file"):
                    continue
                args = tc.get("args") or {}
                raw_path = _decode_transcript_str(args.get("Path"))
                rel_path = _is_shortsyt_code_file(raw_path)
                if not rel_path:
                    continue

                if tname == "edit_file":
                    tgt = _decode_transcript_str(args.get("Target")).strip()
                    rep = _decode_transcript_str(args.get("Replacement")).strip()
                else:
                    tgt = ""
                    rep = _decode_transcript_str(args.get("Content")).strip()

                if len(rep) < 40 or rep == tgt:
                    continue

                current_files.append(rel_path)
                skip_lines = {"else:", "try:", "except:", "finally:", "{", "}", "return"}
                cand_lines = [
                    ln.strip() for ln in rep.splitlines()
                    if ln.strip() and not ln.strip().startswith("#") and ln.strip() not in skip_lines and len(ln.strip()) >= 12
                ]
                def_line = next((ln for ln in cand_lines if ln.startswith(("def ", "async def ", "class ", "export ", "const "))), None)
                first_sig = def_line or (cand_lines[0] if cand_lines else rep[:80])
                current_edits.append({
                    "file": rel_path,
                    "summary": f"{Path(rel_path).name}: {_clean_text(first_sig, 90)}",
                })

                # Buduj zwarty przykład Alpaca do moj_styl_kodowania.jsonl (limit długości pod max_length=512)
                if 50 <= len(rep) <= 1350 and current_prompt and len(coding_samples) < max_coding_samples:
                    verif_note = f" Weryfikacja: {', '.join(current_verifs[:2])}." if current_verifs else ""
                    instr = (
                        f"Zmodyfikuj plik `{rel_path}` w projekcie Shortsyt/Flikcut. "
                        f"Kontekst zgłoszenia: {current_prompt}.{verif_note}"
                    )
                    inp = tgt[:450] if (tgt and len(tgt) <= 450) else ""
                    sig_hash = _stable_id(rel_path, rep[:160])
                    if sig_hash not in seen_coding_hashes:
                        seen_coding_hashes.add(sig_hash)
                        coding_samples.append({
                            "instruction": instr,
                            "input": inp,
                            "output": rep,
                        })

        _flush_turn()

    # Preferuj najnowsze lekcje z końca rozmowy (mające weryfikację)
    fixes.sort(key=lambda x: (1 if x.get("verification") else 0, x.get("edit_count", 0)), reverse=True)
    return fixes[:max_lessons], coding_samples


def sync_coding_style_dataset(
    coding_samples: List[Dict[str, str]],
    coding_dataset_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Dopisuje nowe, unikalne przykłady koderskie z Shortsyt do moj_styl_kodowania.jsonl."""
    ds_path = Path(coding_dataset_path) if coding_dataset_path is not None else DEFAULT_CODING_STYLE_PATH
    existing: List[Dict[str, str]] = []
    seen = set()

    if ds_path.is_file():
        for line in ds_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                existing.append(obj)
                seen.add(_stable_id(obj.get("instruction", ""), str(obj.get("output", ""))[:120]))
            except Exception:
                continue

    added = 0
    for ex in coding_samples:
        key = _stable_id(ex.get("instruction", ""), str(ex.get("output", ""))[:120])
        if key in seen:
            continue
        seen.add(key)
        existing.append(ex)
        added += 1

    ds_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ds_path, "w", encoding="utf-8") as f:
        for obj in existing:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return {
        "coding_dataset_path": str(ds_path),
        "existing_before": len(existing) - added,
        "added_from_shortsyt": added,
        "total_coding_examples": len(existing),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. TRACKER DELT ATRYBUTÓW (Before -> After) Z .recipe.json
# ══════════════════════════════════════════════════════════════════════════════

def _extract_attr_snapshot(recipe: Dict[str, Any]) -> Dict[str, Any]:
    director = recipe.get("director") or {}
    applied = recipe.get("applied") or {}
    return {
        "montage_style": recipe.get("montage_style"),
        "director_operation": recipe.get("director_operation"),
        "camera_mode": recipe.get("camera_mode") or director.get("camera_mode"),
        "buildup_sec": director.get("buildup_sec"),
        "outro_sec": director.get("outro_sec"),
        "zoom_aggression": director.get("asked_zoom"),
        "slowmo_duration": director.get("asked_slowmo"),
        "zoom_level": applied.get("zoom_level"),
        "slowmo_speed": applied.get("slowmo_speed"),
        "game_audio_warped": applied.get("game_audio_warped"),
        "has_jump_cut": bool(recipe.get("jump_cut_segments")),
    }


def _measure_recipe_metrics(recipe: Dict[str, Any], perf_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    try:
        from lol_agent import lol_quality_gate as QG
    except ImportError:
        import lol_quality_gate as QG

    m = QG.measure(recipe)
    cam_px = m.get("camera_peak_step_px")
    qa_synth = None
    if cam_px is not None:
        cam_f = float(cam_px)
        qa_synth = {
            "status": "ERROR" if cam_f > 80.0 else "PASS",
            "issues": [f"Camera velocity: skok {cam_f:.1f}px"] if cam_f > 80.0 else [],
        }
    # Bezpieczne oszacowanie bramki jakości samego przepisu (stały punkt bazowy 85.0 pozwala porównać deltę reguł)
    rs = QG.rescore({"score": 85.0}, recipe, qa_report=qa_synth)
    vid_id = str(recipe.get("youtube_video_id") or recipe.get("video_id") or "")
    p_info = perf_map.get(vid_id) or {}
    return {
        "camera_peak_step_px": cam_px,
        "first_kill_out_sec": m.get("first_kill_out_sec"),
        "longest_gap_out_sec": m.get("longest_gap_out_sec"),
        "beat_error_sec": m.get("beat_error_sec"),
        "final_seconds": recipe.get("final_seconds"),
        "estimated_rescore": rs.get("score"),
        "gate_codes": rs.get("codes") or [],
        "rwi": p_info.get("rwi"),
        "views": p_info.get("views"),
    }


def _load_video_perf_map(directive_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    dp = Path(directive_path) if directive_path is not None else DEFAULT_DIRECTIVE_PATH
    if not dp.is_file():
        return {}
    try:
        data = json.loads(dp.read_text(encoding="utf-8"))
        out: Dict[str, Dict[str, Any]] = {}
        for row in (data.get("videos") or []):
            vid = str(row.get("video_id") or "").strip()
            if vid:
                out[vid] = row
        return out
    except Exception:
        return {}


def _diff_numeric(a: Any, b: Any, digits: int = 2) -> Optional[float]:
    if a is None or b is None:
        return None
    try:
        return round(float(b) - float(a), digits)
    except Exception:
        return None


def _compute_delta_entry(
    source_name: str,
    before_name: str,
    before_rec: Dict[str, Any],
    after_name: str,
    after_rec: Dict[str, Any],
    perf_map: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    b_attr = _extract_attr_snapshot(before_rec)
    a_attr = _extract_attr_snapshot(after_rec)
    changed = {
        k: [b_attr.get(k), a_attr.get(k)]
        for k in b_attr
        if b_attr.get(k) != a_attr.get(k)
    }

    b_met = _measure_recipe_metrics(before_rec, perf_map)
    a_met = _measure_recipe_metrics(after_rec, perf_map)
    deltas = {
        "delta_camera_peak_step_px": _diff_numeric(b_met.get("camera_peak_step_px"), a_met.get("camera_peak_step_px"), 1),
        "delta_first_kill_out_sec": _diff_numeric(b_met.get("first_kill_out_sec"), a_met.get("first_kill_out_sec"), 2),
        "delta_final_seconds": _diff_numeric(b_met.get("final_seconds"), a_met.get("final_seconds"), 2),
        "delta_longest_gap_out_sec": _diff_numeric(b_met.get("longest_gap_out_sec"), a_met.get("longest_gap_out_sec"), 2),
        "delta_estimated_rescore": _diff_numeric(b_met.get("estimated_rescore"), a_met.get("estimated_rescore"), 1),
        "delta_rwi": _diff_numeric(b_met.get("rwi"), a_met.get("rwi"), 1),
    }

    # Pomijaj identyczne bliźniaki (np. ten sam render w lol_temp i recipes_archive)
    has_metric_shift = any(v is not None and abs(v) > 0.01 for v in deltas.values())
    if not changed and not has_metric_shift:
        return None

    pos_signals = 0
    neg_signals = 0
    d_rescore = deltas["delta_estimated_rescore"]
    d_cam = deltas["delta_camera_peak_step_px"]
    d_fk = deltas["delta_first_kill_out_sec"]
    d_rwi = deltas["delta_rwi"]
    d_dur = deltas["delta_final_seconds"]
    if d_rescore is not None:
        pos_signals += int(d_rescore >= 1.0)
        neg_signals += int(d_rescore <= -1.0)
    if d_cam is not None:
        pos_signals += int(d_cam <= -30.0)
        neg_signals += int(d_cam >= 30.0 and (a_met.get("camera_peak_step_px") or 0) > 80.0)
    if d_fk is not None:
        pos_signals += int(d_fk <= -0.8)
        neg_signals += int(d_fk >= 1.5 and (a_met.get("first_kill_out_sec") or 0) > 7.0)
    if d_rwi is not None:
        pos_signals += int(d_rwi >= 3.0)
        neg_signals += int(d_rwi <= -3.0)
    # Przywrócenie ciągłości pełnej walki (BRIDGE_GAP_SPEED_RAMP -> KEEP_FULL_CONTINUOUS z większą pulą materiału) to sygnał pozytywny po stronie reżysera
    if (
        b_attr.get("director_operation") == "BRIDGE_GAP_SPEED_RAMP"
        and a_attr.get("director_operation") == "KEEP_FULL_CONTINUOUS"
        and (d_dur or 0.0) >= 3.0
    ):
        pos_signals += 1

    if pos_signals > 0 and neg_signals == 0:
        verdict = "IMPROVED"
    elif neg_signals > 0 and pos_signals == 0:
        verdict = "REGRESSED"
    elif pos_signals == 0 and neg_signals == 0:
        verdict = "NEUTRAL"
    else:
        verdict = "MIXED"

    return {
        "delta_id": "delta_" + _stable_id(source_name, before_rec.get("created_utc"), after_rec.get("created_utc")),
        "source": source_name,
        "action_type": str(after_rec.get("action_type") or before_rec.get("action_type") or "outplay").lower(),
        "champion": after_rec.get("champion") or before_rec.get("champion") or "Katarina",
        "before_file": before_name,
        "after_file": after_name,
        "before_created_utc": before_rec.get("created_utc"),
        "after_created_utc": after_rec.get("created_utc"),
        "changed_attributes": changed,
        "before_metrics": b_met,
        "after_metrics": a_met,
        "deltas": deltas,
        "verdict": verdict,
    }


def extract_attribute_deltas_from_recipes(
    recipes_dirs: Optional[List[Path]] = None,
    directive_path: Optional[Path] = None,
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Grupuje przepisy `.recipe.json` po pliku źródłowym i wylicza pary Before -> After."""
    dirs = [Path(d) for d in recipes_dirs] if recipes_dirs is not None else [
        LOL_AGENT_DIR / "lol_temp",
        LOL_AGENT_DIR / "recipes_archive",
    ]
    perf_map = _load_video_perf_map(directive_path)
    by_source: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    seen_renders = set()

    for d in dirs:
        if not d.is_dir():
            continue
        for rp in sorted(d.glob("*.recipe.json")):
            try:
                rec = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                continue
            src = str(rec.get("source") or "").strip()
            if not src:
                continue
            if source_filter and src != source_filter:
                continue
            dedup_key = (
                src,
                str(rec.get("created_utc") or ""),
                round(float(rec.get("final_seconds") or 0.0), 3),
                str(rec.get("director_operation") or ""),
                rec.get("camera_peak_step_px"),
            )
            if dedup_key in seen_renders:
                # Jeśli kopia z recipes_archive ma video_id, uzupełnij wcześniejszy wpis jeśli go brakowało
                vid_id = (rec.get("published") or {}).get("video_id") or (rp.stem.replace(".recipe", "") if d.name == "recipes_archive" else "")
                if vid_id and src in by_source:
                    for _, prev_r in by_source[src]:
                        if prev_r.get("created_utc") == rec.get("created_utc") and not prev_r.get("youtube_video_id"):
                            prev_r["youtube_video_id"] = vid_id
                continue
            seen_renders.add(dedup_key)
            if d.name == "recipes_archive" and not rec.get("youtube_video_id"):
                rec["youtube_video_id"] = rp.name[:-len(".recipe.json")]
            by_source.setdefault(src, []).append((rp.name, rec))

    deltas_out: List[Dict[str, Any]] = []
    for src, items in by_source.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda pair: str(pair[1].get("created_utc") or ""))
        for (b_name, b_rec), (a_name, a_rec) in zip(items, items[1:]):
            entry = _compute_delta_entry(src, b_name, b_rec, a_name, a_rec, perf_map)
            if entry is not None:
                deltas_out.append(entry)

    deltas_out.sort(key=lambda x: str(x.get("after_created_utc") or ""), reverse=True)
    return deltas_out


# ══════════════════════════════════════════════════════════════════════════════
# 4. PAMIĘĆ ZBIORCZA + KONTEKST DLA REŻYSERA + PRZYKŁADY QLoRA
# ══════════════════════════════════════════════════════════════════════════════

def _load_memory(memory_path: Path) -> Dict[str, Any]:
    if memory_path.is_file():
        try:
            data = json.loads(memory_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {
        "version": 1,
        "updated_utc": None,
        "attribute_deltas": [],
        "todo_lessons": [],
        "conversation_fixes": [],
    }


def _merge_by_id(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], id_key: str) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for row in (existing or []):
        k = row.get(id_key)
        if k:
            merged[k] = row
    for row in (incoming or []):
        k = row.get(id_key)
        if k:
            merged[k] = row
    return list(merged.values())


def record_recipe_delta_on_render(
    recipe_path: str,
    memory_path: Optional[Path] = None,
    recipes_dirs: Optional[List[Path]] = None,
    directive_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Szybki tracker wywoływany po każdym renderze: porównuje nowy `.recipe.json` z wcześniejszym
    renderem tego samego źródła i zapisuje parę `Before -> After` w engineering_lessons_memory.json.
    """
    rp = Path(recipe_path)
    if not rp.is_file():
        return None
    # Podczas pytest bez jawnego `memory_path` nie zaśmiecaj produkcyjnej pamięci na dysku
    if memory_path is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return None

    try:
        rec = json.loads(rp.read_text(encoding="utf-8"))
    except Exception:
        return None
    src = str(rec.get("source") or "").strip()
    if not src:
        return None

    search_dirs = [Path(d) for d in recipes_dirs] if recipes_dirs is not None else [
        rp.parent,
        LOL_AGENT_DIR / "recipes_archive",
    ]
    new_deltas = extract_attribute_deltas_from_recipes(
        recipes_dirs=search_dirs,
        directive_path=directive_path,
        source_filter=src,
    )
    if not new_deltas:
        return None

    if memory_path is None and os.environ.get("PYTEST_CURRENT_TEST"):
        return new_deltas[0]

    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    mem = _load_memory(mp)
    mem["attribute_deltas"] = _merge_by_id(mem.get("attribute_deltas", []), new_deltas, "delta_id")
    mem["attribute_deltas"].sort(key=lambda x: str(x.get("after_created_utc") or ""), reverse=True)
    mem["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(mp, mem)
    return new_deltas[0]


def _median_num(values: List[float]) -> float:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return 0.0
    mid = len(nums) // 2
    if len(nums) % 2 == 1:
        return float(nums[mid])
    return (nums[mid - 1] + nums[mid]) / 2.0


def _load_camera_shunpo_policy(rules_path: Optional[Path] = None) -> Dict[str, Any]:
    """Wczytuje politykę ruchu kamery Katariny (Shunpo E -> sztylet/wróg + centrowanie) z engine_rules.json."""
    rp = Path(rules_path) if rules_path is not None else (LOL_AGENT_DIR / "engine_rules.json")
    default_policy: Dict[str, Any] = {
        "champion": "Katarina",
        "motion_rule": "smooth_pan_or_instant_shunpo_snap",
        "max_smooth_step_px": 80.0,
        "shunpo_range_px_1080p": 520.0,
        "shunpo_target_snap_tol_px": 140.0,
        "valid_jump_targets": ["katarina_passive_dagger", "enemy_champion_hp_bar"],
        "post_snap_behavior": "center_on_katarina",
        "post_snap_center_lock_frames": 2,
    }
    try:
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
            pol = data.get("camera_shunpo_policy")
            if isinstance(pol, dict) and pol:
                merged = dict(default_policy)
                merged.update(pol)
                return merged
    except Exception:
        pass
    return default_policy


def analyze_high_retention_configs(
    yt_cache_path: Optional[Path] = None,
    published_path: Optional[Path] = None,
    directive_path: Optional[Path] = None,
    recipes_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Łączy yt_perf_cache, published_videos, learning_directive oraz archived recipes aby wyłonić wzorce wysokiej retencji."""
    yp = Path(yt_cache_path) if yt_cache_path is not None else (LOL_AGENT_DIR / "yt_perf_cache.json")
    pp = Path(published_path) if published_path is not None else (LOL_AGENT_DIR / "published_videos.jsonl")
    dp = Path(directive_path) if directive_path is not None else DEFAULT_DIRECTIVE_PATH
    rdir = Path(recipes_dir) if recipes_dir is not None else (LOL_AGENT_DIR / "recipes_archive")

    pub_by_id: Dict[str, Dict[str, Any]] = {}
    if pp.exists():
        for raw_line in pp.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                vid = str(rec.get("video_id") or "").strip()
                if vid:
                    pub_by_id[vid] = rec
            except Exception:
                continue

    videos: List[Dict[str, Any]] = []
    if yp.exists():
        try:
            ydata = json.loads(yp.read_text(encoding="utf-8"))
            videos = [v for v in (ydata.get("videos") or []) if isinstance(v, dict)]
        except Exception:
            videos = []

    high_avd: List[Dict[str, Any]] = []
    low_avd: List[Dict[str, Any]] = []
    perf_by_id: Dict[str, Dict[str, Any]] = {}
    for v in videos:
        vid = str(v.get("video_id") or "").strip()
        if vid:
            perf_by_id[vid] = v
        try:
            avd = float(v.get("avg_view_pct") or 0.0)
        except Exception:
            avd = 0.0
        if avd >= 100.0:
            high_avd.append(v)
        elif 0.0 < avd < 85.0:
            low_avd.append(v)

    top_videos: List[Dict[str, Any]] = []
    for v in sorted(high_avd, key=lambda x: float(x.get("avg_view_pct") or 0.0), reverse=True)[:5]:
        vid = str(v.get("video_id") or "")
        p_rec = pub_by_id.get(vid, {})
        top_videos.append({
            "video_id": vid,
            "action_type": v.get("action_type") or p_rec.get("action_type") or "",
            "views": int(v.get("views") or 0),
            "avg_view_pct": round(float(v.get("avg_view_pct") or 0.0), 1),
            "duration_s": round(float(p_rec.get("duration_s") or 0.0), 1) if p_rec.get("duration_s") else None,
            "qa": v.get("initial_qa_score") or p_rec.get("initial_qa_score"),
        })

    dir_data: Dict[str, Any] = {}
    if dp.exists():
        try:
            dir_data = json.loads(dp.read_text(encoding="utf-8"))
        except Exception:
            dir_data = {}

    dur_an = dir_data.get("duration_analysis") or {}
    ret_by_act_raw = ((dir_data.get("retention_by_action") or {}).get("by_action") or {})
    hook_ret_by_act: Dict[str, float] = {}
    for act_k, act_v in ret_by_act_raw.items():
        if isinstance(act_v, dict) and act_v.get("avg_hook_retention_pct") is not None:
            hook_ret_by_act[str(act_k)] = round(float(act_v["avg_hook_retention_pct"]), 1)

    recipe_findings: List[Dict[str, Any]] = []
    if rdir.exists():
        for rfile in sorted(rdir.glob("*.recipe.json")):
            try:
                rdata = json.loads(rfile.read_text(encoding="utf-8"))
            except Exception:
                continue
            vid = str(rdata.get("video_id") or rfile.name.replace(".recipe.json", "")).strip()
            p_info = perf_by_id.get(vid, {})
            avd = p_info.get("avg_view_pct")
            cam_step = rdata.get("camera_peak_step_px")
            try:
                cam_f = round(float(cam_step), 1) if cam_step is not None else None
            except Exception:
                cam_f = None
            avd_f = round(float(avd), 1) if avd is not None else None
            warning = None
            if cam_f is not None and cam_f > 120.0 and avd_f is not None and avd_f < 85.0:
                warning = f"unconfirmed_cam_jump_{cam_f}px_linked_to_low_avd_{avd_f}pct"
            recipe_findings.append({
                "video_id": vid,
                "camera_peak_step_px": cam_f,
                "montage_style": rdata.get("montage_style"),
                "director_operation": rdata.get("director_operation"),
                "final_seconds": rdata.get("final_seconds"),
                "avg_view_pct": avd_f,
                "views": p_info.get("views"),
                "warning": warning,
            })

    high_durs = [
        float(pub_by_id[str(v.get("video_id") or "")]["duration_s"])
        for v in high_avd
        if str(v.get("video_id") or "") in pub_by_id and pub_by_id[str(v.get("video_id") or "")].get("duration_s")
    ]
    target_range = [round(min(high_durs), 1), round(max(high_durs), 1)] if high_durs else [11.8, 17.7]

    return {
        "high_avd_threshold_pct": 100.0,
        "high_avd_count": len(high_avd),
        "high_avd_median_views": int(round(_median_num([float(v.get("views") or 0) for v in high_avd]))),
        "high_avd_median_pct": round(_median_num([float(v.get("avg_view_pct") or 0) for v in high_avd]), 1),
        "low_avd_count": len(low_avd),
        "low_avd_median_views": int(round(_median_num([float(v.get("views") or 0) for v in low_avd]))),
        "low_avd_median_pct": round(_median_num([float(v.get("avg_view_pct") or 0) for v in low_avd]), 1),
        "best_duration_bucket": str(dur_an.get("best_bucket") or "balanced_14_17s"),
        "viral_avg_duration_s": round(float(dur_an.get("viral_avg_duration_s") or 15.0), 1),
        "target_duration_range_s": target_range,
        "hook_retention_by_action": hook_ret_by_act,
        "top_retention_videos": top_videos,
        "recipe_camera_findings": recipe_findings,
        "recommended_config": {
            "style": "PRIMARY",
            "operation": "KEEP_FULL_CONTINUOUS",
            "zoom_max": 1.12,
            "slowmo_window_max": 0.7,
            "min_qa_score": 96,
            "max_smooth_cam_step_px": 80.0,
            "avoid": "533px_unconfirmed_cam_jump_and_clipped_multi_slowmo_audio",
        },
    }


def get_high_retention_context_for_director(
    action_type: Optional[str] = None,
    memory_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Zwraca kompaktowy kontekst konfiguracji high-retention do promptu reżysera Synapsy."""
    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    mem = _load_memory(mp)
    prof = mem.get("high_retention_profile")
    if not isinstance(prof, dict) or not prof:
        prof = analyze_high_retention_configs()
    rec = prof.get("recommended_config") or {}
    hook_map = prof.get("hook_retention_by_action") or {}
    act_key = str(action_type or "").strip().lower()
    act_hook = hook_map.get(act_key)
    findings = prof.get("recipe_camera_findings") or []
    cam_warn = next((f.get("warning") for f in findings if f.get("warning")), "avoid_unconfirmed_cam_jump_gt120px")
    return {
        "best_bucket": prof.get("best_duration_bucket", "balanced_14_17s"),
        "viral_s": prof.get("viral_avg_duration_s", 15.0),
        "high_avd_n": prof.get("high_avd_count", 0),
        "high_vs_low_views": f"{prof.get('high_avd_median_views', 0)}vs{prof.get('low_avd_median_views', 0)}",
        "style": rec.get("style", "PRIMARY"),
        "op": rec.get("operation", "KEEP_FULL_CONTINUOUS"),
        "min_qa": rec.get("min_qa_score", 96),
        "action_hook_pct": act_hook,
        "cam_warn": cam_warn,
    }


def sync_engineering_memory(
    memory_path: Optional[Path] = None,
    todo_path: Optional[Path] = None,
    transcript_paths: Optional[List[Path]] = None,
    recipes_dirs: Optional[List[Path]] = None,
    directive_path: Optional[Path] = None,
    coding_dataset_path: Optional[Path] = None,
    verification_log_path: Optional[Path] = None,
    include_transcripts: bool = True,
    write_files: bool = True,
) -> Dict[str, Any]:
    """Odświeża `engineering_lessons_memory.json` (i opcjonalnie `moj_styl_kodowania.jsonl`) ze wszystkich 3 źródeł."""
    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    mem = _load_memory(mp)

    todo_lessons = extract_lessons_from_todo(todo_path)
    deltas = extract_attribute_deltas_from_recipes(recipes_dirs=recipes_dirs, directive_path=directive_path)
    conv_fixes: List[Dict[str, Any]] = []
    coding_samples: List[Dict[str, str]] = []
    if include_transcripts:
        conv_fixes, coding_samples = extract_lessons_from_transcripts(transcript_paths=transcript_paths)

    mem["todo_lessons"] = _merge_by_id(mem.get("todo_lessons", []), todo_lessons, "lesson_id")
    mem["attribute_deltas"] = _merge_by_id(mem.get("attribute_deltas", []), deltas, "delta_id")
    mem["attribute_deltas"].sort(key=lambda x: str(x.get("after_created_utc") or ""), reverse=True)
    if conv_fixes:
        mem["conversation_fixes"] = _merge_by_id(mem.get("conversation_fixes", []), conv_fixes, "lesson_id")
    mem["camera_shunpo_policy"] = _load_camera_shunpo_policy()
    mem["high_retention_profile"] = analyze_high_retention_configs(directive_path=directive_path)
    mem["historical_value_evolution"] = extract_pre_conversation_value_history(directive_path=directive_path)

    vlp = Path(verification_log_path) if verification_log_path is not None else DEFAULT_VERIFICATION_LOG
    verif_count = 0
    if vlp.is_file():
        for raw_line in vlp.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not raw_line.strip():
                continue
            try:
                if isinstance(json.loads(raw_line), dict):
                    verif_count += 1
            except Exception:
                continue
    mem["watchability_verifications_count"] = verif_count
    mem["updated_utc"] = datetime.now(timezone.utc).isoformat()

    coding_info: Dict[str, Any] = {}
    if write_files:
        _atomic_write_json(mp, mem)
        if coding_samples and not (coding_dataset_path is None and os.environ.get("PYTEST_CURRENT_TEST")):
            coding_info = sync_coding_style_dataset(coding_samples, coding_dataset_path=coding_dataset_path)

    return {
        "memory_path": str(mp),
        "todo_lessons_count": len(mem["todo_lessons"]),
        "attribute_deltas_count": len(mem["attribute_deltas"]),
        "conversation_fixes_count": len(mem.get("conversation_fixes", [])),
        "high_avd_videos_count": mem["high_retention_profile"].get("high_avd_count", 0),
        "watchability_verifications_count": verif_count,
        "historical_value_lessons_count": len(mem["historical_value_evolution"]),
        "has_camera_shunpo_policy": bool(mem.get("camera_shunpo_policy")),
        "coding_sync": coding_info,
    }


HISTORICAL_VALUE_LAWS: List[str] = [
    "Cam v37: smooth_win 13->5, max_pan 25->80, lerp 0.45, freeze<=0.6s",
    "Limits: zoom<=1.12(0.4s), slowmo<=0.7s, crop=608px",
    "Learning: min_bucket 3->8, min_slot=5, shrink_k=10",
    "Retention: balanced 14-17s (1830v)>cinematic; AVD 88.5%->105.3%",
    "IG/NVENC: cap maxrate 16M + CFR 48kHz (<25Mbps limit)",
]

_COMMIT_PARAM_LESSONS: Dict[str, Tuple[str, str, str, str]] = {
    "e8c6c7e": (
        "lerp 0.90->0.30, max_pan 60px, smooth_win 3->9",
        "Wyeliminowano gwałtowne drgania kamery na pojedynczych klatkach.",
        "Agresywny lerp 0.90 powoduje szarpanie; bezpieczne wygładzanie wymaga okna >=5.",
        "KEEP_CHANGE",
    ),
    "9a9602b": (
        "solo_bolo slowmo 0.7x na kill, blokada obcinania startu walki",
        "Brak martwych przestojów po zabójstwie i pełny kontekst 1v1.",
        "Zachowaj start starcia w Solo Bolo oraz krótkie 0.7x slowmo bez pauz.",
        "KEEP_CHANGE",
    ),
    "2dbc526": (
        "deadband_px=30, end_freeze<=0.6s, buildup >=4.5s dla multikilla",
        "Utrzymano retencję >110% (45.8k views/28d) przez pokazanie inicjacji walki.",
        "Ucinać deadband <=30px dla statywu, ale zawsze zostawiać >=4.5s przed 1. fragiem.",
        "KEEP_CHANGE",
    ),
    "f7b9f74": (
        "music_vol 60%->45% + spięcie smart_camera z walidatorem QA",
        "Wyraźniejsze efekty gry pod muzyką i weryfikacja kadrów przed publikacją.",
        "Nie podbijaj głośności muzyki kosztem SFX walki i pilnuj bramki QA.",
        "KEEP_CHANGE",
    ),
    "8f73898": (
        "SMOOTH_WIN 13->5, MAX_PAN_PX 25->80, LERP_ALPHA 0.18->0.35",
        "Reakcja kamery skrócona poniżej 0.4s bez spóźnień w szybkich shortach.",
        "SMOOTH_WIN=13 i MAX_PAN=25px są zbyt wolne dla dynamicznych dashów.",
        "KEEP_CHANGE",
    ),
    "fda9f6f": (
        "pętla user_feedback_history + głośność muzyki I=-17 LUFS",
        "Utrwalenie korekt użytkownika w historii zamiast jednorazowego nadpisania.",
        "Każda ręczna zmiana suwaków musi zasilać pamięć przyszłych decyzji.",
        "KEEP_CHANGE",
    ),
    "a6ec349": (
        "rozdział masek green/gold HP + odrzucanie wież (>180px)",
        "Koniec uciekania kamery na złote VFX Swaina i paski wież.",
        "W trybie standardowym złota maska musi być wyłączona dla uniknięcia fałszywych locków.",
        "KEEP_CHANGE",
    ),
    "67d093d": (
        "śledzenie Shunpo + zero desync PTS audio/wideo",
        "Brak rozjazdu napisów i dźwięku przy szybkich teleportach Katariny.",
        "Korekcja PTS i ciągły timeline zapobiegają pływaniu nakładek.",
        "KEEP_CHANGE",
    ),
    "44d5ef3": (
        "filtr cząsteczek VFX + maska Tab + smooth seams",
        "Stabilny obraz podczas wybuchów umiejętności i brak fałszywych detekcji na tabeli.",
        "Ignoruj HUD/Tab oraz krótkie rozbłyski VFX zamiast gonić je kamerą.",
        "KEEP_CHANGE",
    ),
    "c6d7aba": (
        "binarne drzewo O(log N) dla crop_x + upraszczanie trajektorii",
        "Stabilne wyrażenie FFmpeg bez zatorów filtra przy długich klipach.",
        "Upraszczaj ścieżkę kamery O(log N) zamiast generować ciężkie zagnieżdżenia.",
        "KEEP_CHANGE",
    ),
    "4f0e0a0": (
        "zunifikowany lol_timeline + engine_rules + MIN_SAMPLE_FOR_BUCKET 3->8, MIN_LEAD_TO_WIN=0.15, SHRINK_K=10",
        "Jedna oś czasu dla napisów/audio i brak wyciągania pochopnych wniosków z małych prób.",
        "Nie rekomenduj bucketa przy n<8 i bez >=15% przewagi; zawsze licz czas przez warp_time.",
        "KEEP_CHANGE",
    ),
}


def extract_pre_conversation_value_history(
    project_root: Optional[Path] = None,
    directive_path: Optional[Path] = None,
    feedback_path: Optional[Path] = None,
    rules_path: Optional[Path] = None,
    baseline_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Wyciąga historię zmian parametrów i ich zmierzonych efektów sprzed obecnej rozmowy oraz Etap 11."""
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    dp = Path(directive_path) if directive_path is not None else DEFAULT_DIRECTIVE_PATH
    fp = Path(feedback_path) if feedback_path is not None else DEFAULT_USER_FEEDBACK_PATH
    rp = Path(rules_path) if rules_path is not None else DEFAULT_ENGINE_RULES_PATH
    bp = Path(baseline_path) if baseline_path is not None else DEFAULT_GOLDEN_BASELINE_PATH

    entries: List[Dict[str, Any]] = []
    seen = set()

    def _add(era: str, source_art: str, change: str, effect: str, rule: str, direction: str) -> None:
        hid = _stable_id(era, source_art, change)
        if hid in seen:
            return
        seen.add(hid)
        entries.append({
            "history_id": hid,
            "era": era,
            "source_artifact": source_art,
            "parameter_change": _clean_text(change, 160),
            "measured_effect": _clean_text(effect, 170),
            "causal_rule": _clean_text(rule, 170),
            "direction": direction,
        })

    # 1. Złoty punkt odniesienia (GOLDEN_BASELINE_PARAMS.json, 2026-10-06)
    if bp.is_file():
        try:
            g = json.loads(bp.read_text(encoding="utf-8"))
            vm = (g.get("_meta") or {}).get("verified_metrics") or {}
            at = g.get("active_tuning_config") or {}
            cam = g.get("smart_camera_kinematics") or {}
            if vm and at:
                _add(
                    "pre_conversation",
                    bp.name,
                    f"lerp={cam.get('lerp_alpha')}, max_pan={cam.get('max_pan_px')}, smooth_win={cam.get('smooth_win')}, freeze={cam.get('end_freeze_sec')}s, pacing={at.get('pacing')}, zoom={at.get('zoomAggression')}, slowmo={at.get('slowmoDuration')}s",
                    f"{vm.get('views_28d')} views/28d, retencja {vm.get('retention_range')}, {vm.get('published_shorts_count')} shortów",
                    "Zbalansowany profil 14-17s z responsywną kamerą i music=0.55/game=0.85 utrzymuje >110% retencji.",
                    "KEEP_CHANGE",
                )
        except Exception:
            pass

    # 2. Historia commitów git sprzed obecnej sesji
    try:
        r = subprocess.run(
            ["git", "log", "--format=%h|%ad|%s", "--date=short", "-n", "120"],
            cwd=str(root), capture_output=True, text=True, check=False, timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            for line in r.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                shash, sdate, subj = parts[0].strip(), parts[1].strip(), parts[2].strip()
                if shash in _COMMIT_PARAM_LESSONS:
                    chg, eff, rul, drc = _COMMIT_PARAM_LESSONS[shash]
                    _add("pre_conversation", f"git:{shash} ({sdate})", f"{chg} [{subj[:45]}]", eff, rul, drc)
    except Exception:
        pass

    # 3. Kontrakt progów w engine_rules.json
    if rp.is_file():
        try:
            er = json.loads(rp.read_text(encoding="utf-8"))
            el = er.get("edit_limits") or {}
            lr = er.get("learning") or {}
            if el:
                _add(
                    "pre_conversation",
                    "engine_rules.json:edit_limits",
                    f"zoom_max={el.get('zoom_max')}, zoom_win={el.get('zoom_window_max')}s, slowmo_max={el.get('slowmo_window_max')}s, crop_w={((er.get('frame') or {}).get('crop_width'))}px",
                    "Zapobiega rozmyciu akcji i błędom parzystości NVENC (crop 608px zamiast 607px).",
                    "Reżyser może prosić o zoom 1.25 / slowmo 1.6s, lecz twarde cięcie do 1.12 / 0.7s chroni płynność.",
                    "KEEP_CHANGE",
                )
            if lr:
                _add(
                    "pre_conversation",
                    "engine_rules.json:learning",
                    f"min_bucket={lr.get('min_sample_for_bucket')}, min_slot={lr.get('min_sample_for_slot')}, min_kw={lr.get('min_sample_for_keyword')}, min_lead={lr.get('min_lead_to_win')}, shrink_k={lr.get('shrink_k')}",
                    "Redukuje fałszywe zwycięstwa z małych prób i stabilizuje wagi typów akcji wokół 1.0.",
                    "Bez n>=8 i 15% przewagi zmiana progu jest tylko obserwacją, nie decyzją produkcyjną.",
                    "KEEP_CHANGE",
                )
        except Exception:
            pass

    # 4. Telemetria trendów i bucketów w learning_directive.json
    if dp.is_file():
        try:
            ld = json.loads(dp.read_text(encoding="utf-8"))
            prog = (ld.get("learning_progression") or {}).get("monthly_2026") or {}
            if "2026-08" in prog and "2026-11" in prog:
                m_aug, m_nov = prog["2026-08"], prog["2026-11"]
                cohorts = (ld.get("learning_progression") or {}).get("cohorts") or {}
                c1, cl = cohorts.get("first_half") or {}, cohorts.get("last_15_videos") or {}
                _add(
                    "pre_conversation",
                    "learning_directive.json:monthly_2026",
                    "Ewolucja pipeline 2026-08 -> 2026-11 (smart camera v37 + balanced pacing + timeline)",
                    f"Mediana AVD wzrosła {m_aug.get('median_avd_pct')}% -> {m_nov.get('median_avd_pct')}%; mediana wyświetleń kohort {c1.get('median_views')} -> {cl.get('median_views')}",
                    "Kolejne poprawki kamery, buildupu i dyrektyw realnie podniosły utrzymanie widza i wyświetlenia.",
                    "KEEP_CHANGE",
                )
            bstats = (ld.get("duration_analysis") or {}).get("bucket_stats") or {}
            if "balanced_14_17s" in bstats and "cinematic_18_25s" in bstats:
                b_bal = bstats["balanced_14_17s"]
                b_sho = bstats.get("short_10_13s") or {}
                b_cin = bstats["cinematic_18_25s"]
                _add(
                    "pre_conversation",
                    "learning_directive.json:duration_analysis",
                    "Porównanie długości: short_10_13s vs balanced_14_17s vs cinematic_18_25s",
                    f"balanced_14_17s: med={b_bal.get('median_views')} (score={b_bal.get('composite_score')}) > short={b_sho.get('median_views')} > cinematic={b_cin.get('median_views')}",
                    "Przedział 14-17s wygrywa retencją i odsłonami z krótszymi i rozwlekłymi montażami.",
                    "KEEP_CHANGE",
                )
            astats = ld.get("action_stats") or {}
            if "solo_bolo" in astats and "pentakill" in astats:
                s_sb, s_pk = astats["solo_bolo"], astats["pentakill"]
                _add(
                    "pre_conversation",
                    "learning_directive.json:action_stats",
                    f"Formaty: solo_bolo (RWI={s_sb.get('avg_rwi_48h')}) vs pentakill (RWI={s_pk.get('avg_rwi_48h')})",
                    f"solo_bolo med={s_sb.get('median_views')} ({s_sb.get('performance_ratio_median')}x) vs pentakill med={s_pk.get('median_views')} ({s_pk.get('performance_ratio_median')}x, w={s_pk.get('weight')})",
                    "Chaotyczne pentakille tracą klarowność w 9:16; 1v1 i szybkie trio utrzymują wyższe RWI.",
                    "KEEP_CHANGE",
                )
            tstats = ld.get("title_structure_stats") or {}
            if "DISRESPECT_1V1" in tstats and "CLEAN_OUTPLAY" in tstats:
                td, tc = tstats["DISRESPECT_1V1"], tstats["CLEAN_OUTPLAY"]
                _add(
                    "pre_conversation",
                    "learning_directive.json:title_structure",
                    "Struktury tytułów DISRESPECT_1V1 vs CLEAN_OUTPLAY vs QUESTION",
                    f"DISRESPECT_1V1 ratio={td.get('median_ratio')}, CLEAN_OUTPLAY conv={tc.get('avg_conversion_per_1k')}/1k",
                    "Krótkie prowokujące tytuły biją ogólnikowe pytania typu QUESTION.",
                    "KEEP_CHANGE",
                )
        except Exception:
            pass

    # 5. Realne korekty z user_feedback_history.json (bez wpisów api_test)
    if fp.is_file():
        try:
            ufh = json.loads(fp.read_text(encoding="utf-8"))
            lp = ufh.get("learned_preferences") or {}
            real_corrs = [
                h for h in (ufh.get("history") or [])
                if h.get("type") == "parameter_correction" and h.get("source") != "api_test"
            ]
            if real_corrs:
                last_c = real_corrs[-1]
                _add(
                    "pre_conversation",
                    "user_feedback_history.json",
                    f"{last_c.get('param')}: {last_c.get('old_value')} -> {last_c.get('new_value')} ({len(real_corrs)} korekt użytkownika)",
                    f"Utrwalone preferencje: music={lp.get('music_balance')}, game={lp.get('game_sound_balance')}, smooth_win={lp.get('smooth_win')}, freeze={lp.get('end_freeze_sec')}s",
                    "Nie wracaj do trybu cinematic ani wolnego wygładzania po ręcznym przestawieniu na balanced.",
                    "KEEP_CHANGE",
                )
        except Exception:
            pass

    # 6. Etap 11: limit bitrate NVENC oraz zgodność Instagram Reels
    _add(
        "etap11",
        "hardware_accel.py + instagram_publisher.py",
        "h264_nvenc z -cq 18 -b:v 0 (29.24 Mbps, 87.16 MB, VFR 57.89 fps, AAC 193 kbps) -> -maxrate 16M + pre-upload CFR 14M / AAC 128k 48kHz +faststart",
        "Usunięto przyczynę ProcessingFailedError na rupload IG (rozmiar spadł 87.16 MB -> 30.69 MB, 10.72 Mbps CFR 60 fps).",
        "Nielimitowany NVENC przekracza limit 25 Mbps Instagrama; twardy maxrate <=16M i CFR 48kHz gwarantują akceptację Reels.",
        "KEEP_CHANGE",
    )

    return entries


def get_cause_effect_context_for_director(
    action_type: Optional[str] = None,
    limit: int = 3,
    memory_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Zwraca najnowsze zweryfikowane pary Before -> After oraz skrócone prawa zmian sprzed rozmowy."""
    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    if not mp.is_file():
        return []
    mem = _load_memory(mp)
    deltas = list(mem.get("attribute_deltas") or [])
    hist = list(mem.get("historical_value_evolution") or [])

    if not deltas:
        if not hist:
            return []
        return [{
            "verdict": "HISTORICAL_LAWS",
            "historical_value_laws": HISTORICAL_VALUE_LAWS[:5],
        }]

    act_low = (action_type or "").lower().strip()
    ranked = sorted(
        deltas,
        key=lambda d: (
            1 if (act_low and str(d.get("action_type") or "").lower() == act_low) else 0,
            1 if d.get("verdict") in ("IMPROVED", "REGRESSED") else 0,
            str(d.get("after_created_utc") or ""),
        ),
        reverse=True,
    )
    compact: List[Dict[str, Any]] = []
    for idx, d in enumerate(ranked[: max(1, int(limit))]):
        item: Dict[str, Any] = {
            "action_type": d.get("action_type"),
            "changed_attributes": d.get("changed_attributes"),
            "deltas": {k: v for k, v in (d.get("deltas") or {}).items() if v is not None},
            "verdict": d.get("verdict"),
        }
        if idx == 0 and hist:
            item["historical_value_laws"] = HISTORICAL_VALUE_LAWS[:5]
        compact.append(item)
    return compact


def build_cause_effect_training_examples(
    memory_path: Optional[Path] = None,
    max_examples: int = 40,
) -> List[Dict[str, str]]:
    """Buduje zwięzłe przykłady treningowe `engineering_cause_effect` (mieszczące się w max_length=512)."""
    try:
        from lol_agent.synapsa_engine import build_synapsa_instruction
    except ImportError:
        from synapsa_engine import build_synapsa_instruction

    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    mem = _load_memory(mp)
    examples: List[Dict[str, str]] = []

    # 1. Twarde delty atrybutów Before -> After z renderów
    for d in (mem.get("attribute_deltas") or [])[:20]:
        changed = d.get("changed_attributes") or {}
        if not changed:
            continue
        non_null_deltas = {k: v for k, v in (d.get("deltas") or {}).items() if v is not None}
        payload = {
            "evidence_type": "attribute_delta",
            "action_type": d.get("action_type"),
            "changed_attributes": changed,
            "before_metrics": {k: v for k, v in (d.get("before_metrics") or {}).items() if v is not None},
        }
        verdict = str(d.get("verdict") or "MIXED")
        rule = f"Zmiana {list(changed.keys())[:3]} zmienila metryki o {non_null_deltas}."
        rec_action = (
            "KEEP_CHANGE" if verdict == "IMPROVED"
            else ("REVERT_OR_TIGHTEN" if verdict == "REGRESSED" else "KEEP_SAFE_GUARD")
        )
        out_obj = {
            "verdict": verdict,
            "affected_metrics": non_null_deltas,
            "causal_rule": _clean_text(rule, 160),
            "recommended_action": rec_action,
        }
        examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", payload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    # 2. Lekcje inżynierskie [x] z TODO.md oraz z rozmów
    for row in (mem.get("todo_lessons") or [])[:15]:
        payload = {
            "evidence_type": "todo_engineering_fix",
            "module": _clean_text(row.get("module", ""), 80),
            "goal": _clean_text(row.get("goal", ""), 110),
        }
        out_obj = {
            "verdict": "IMPROVED",
            "affected_metrics": row.get("affected_files", [])[:4],
            "causal_rule": _clean_text(f"{row.get('change', '')} -> {row.get('measured_result', '')}", 180),
            "recommended_action": _clean_text(row.get("expected_effect", "Preserve verified fix"), 100),
        }
        examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", payload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    for fix in (mem.get("conversation_fixes") or [])[:15]:
        if not fix.get("verification"):
            continue
        payload = {
            "evidence_type": "conversation_fix",
            "user_issue": _clean_text(fix.get("user_request", ""), 120),
            "files": (fix.get("affected_files") or [])[:3],
        }
        out_obj = {
            "verdict": "IMPROVED",
            "affected_metrics": (fix.get("verification") or [])[:3],
            "causal_rule": _clean_text(fix.get("fix_summary", ""), 160),
            "recommended_action": "APPLY_PATTERN_ON_SIMILAR_BUG",
        }
        examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", payload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    policy_examples: List[Dict[str, Any]] = []
    shunpo_pol = _load_camera_shunpo_policy()
    if shunpo_pol:
        shunpo_payload = {
            "topic": "katarina_camera_shunpo_e",
            "champion": "Katarina",
            "rule": shunpo_pol.get("motion_rule", "smooth_pan_or_instant_shunpo_snap"),
            "max_smooth_px": shunpo_pol.get("max_smooth_step_px", 80.0),
            "targets": shunpo_pol.get("valid_jump_targets", ["katarina_passive_dagger", "enemy_champion_hp_bar"]),
        }
        shunpo_out = {
            "root_cause": "Unconfirmed particle noise caused 500px camera jitter, while Katarina E Shunpo onto passive daggers or enemies needs instant snap + center.",
            "verified_fix": "Detect passive daggers + enemy HP bars within 520px; pan <=80px normally, snap only on confirmed Shunpo, lock center on Katarina.",
            "measured_result": "Smooth pan with zero false 500px spikes and instant Katarina centering after E Shunpo.",
            "recommended_action": "ENFORCE_KATARINA_SHUNPO_CAMERA_RULE",
        }
        policy_examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", shunpo_payload),
            "output": json.dumps(shunpo_out, ensure_ascii=False),
        })

    hr_ctx = get_high_retention_context_for_director()
    if hr_ctx:
        hr_payload = {
            "topic": "high_retention_montage_config",
            "best_bucket": hr_ctx.get("best_bucket"),
            "high_avd_n": hr_ctx.get("high_avd_n"),
            "views_median": hr_ctx.get("high_vs_low_views"),
        }
        hr_out = {
            "root_cause": "Channel AVD >=100% (median 1982 vs 1485 views) correlates with balanced_14_17s duration, QA >=96, and smooth 63px camera.",
            "verified_fix": "Prefer PRIMARY / KEEP_FULL_CONTINUOUS, zoom <=1.12, single slowmo <=0.7s; avoid unconfirmed 533px camera jumps (78.7% AVD).",
            "measured_result": "Sustains >=100% AVD and median 1982 views vs 1485 low-AVD baseline.",
            "recommended_action": "PREFER_HIGH_RETENTION_MONTAGE_CONFIG",
        }
        policy_examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", hr_payload),
            "output": json.dumps(hr_out, ensure_ascii=False),
        })

    etap9_payload = {
        "topic": "etap9_retention_overlay_sync",
        "lead_in_max_s": 4.2,
        "banner_y_ratio": 0.235,
        "hud_rule": "match_max_banner_tier",
    }
    etap9_out = {
        "root_cause": "Forward combat scan pulled 11s minion farming intro, center captions (y=0.54) hid Katarina, post-render hooks defaulted to INSANE OUTPLAY!, and un-trimmed amix added +64ms black end frame.",
        "verified_fix": "Scan enemy HP backwards (lead_in<=4.2s), render pre-computed Synapsa hook opaque at t=0, place captions at y=0.235 with tier-consistent KILL X/Y, trim audio via atrim+-shortest, and guard 145px Shunpo crop margin.",
        "measured_result": "Unobstructed center combat, opaque frame-0 hook, av_delta_s<=0.02s, zero audio clipping, and centered Katarina after E Shunpo.",
        "recommended_action": "KEEP_ETAP9_RETENTION_AND_OVERLAY_CONTRACT",
    }
    policy_examples.append({
        "instruction": build_synapsa_instruction("engineering_cause_effect", etap9_payload),
        "output": json.dumps(etap9_out, ensure_ascii=False),
    })

    if policy_examples:
        if max_examples is None:
            return examples + policy_examples
        head_cap = max(0, int(max_examples) - len(policy_examples))
        return (examples[:head_cap] + policy_examples)[: int(max_examples)]

    return examples[:max_examples]


def build_watchability_training_examples(
    verification_log_path: Optional[Path] = None,
    max_examples: int = 18,
) -> List[Dict[str, str]]:
    """Buduje zwięzłe przykłady `predict_change_effect` i `watchability_compare` (<=480 tokenów)."""
    try:
        from lol_agent.synapsa_engine import build_synapsa_instruction
    except ImportError:
        from synapsa_engine import build_synapsa_instruction

    anchors: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = [
        (
            "predict_change_effect",
            {
                "before": {"score": 45.95, "frame0_legible": False, "kill_zone": "center_blocking", "clip": 159},
                "proposed_changes": {"hook_fade_in": False, "banner_kill_y_ratio": 0.235, "alimiter_limit": 0.85},
            },
            {
                "expected_verdict": "BETTER",
                "expected_metric_shifts": {
                    "frame0_hook_legible": "UP",
                    "center_blocked_kills_ratio": "DOWN",
                    "audio_clip_gt_096": "DOWN",
                    "watchability_score": "UP",
                },
                "risks": ["Verify frame 0 contrast after disabling fade-in."],
                "deduction_rationale": "Opaque frame-0 hook, upper banner y=0.235, and 0.85 limiter remove center occlusion and AAC clipping.",
            },
        ),
        (
            "predict_change_effect",
            {
                "before": {"score": 100.0, "frame0_legible": True, "kill_zone": "upper_safe", "clip": 0},
                "proposed_changes": {"hook_fade_in": True, "banner_kill_y_ratio": 0.54, "disable_audio_limiter": True},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {
                    "frame0_hook_legible": "DOWN",
                    "center_blocked_kills_ratio": "UP",
                    "audio_clip_gt_096": "UP",
                    "watchability_score": "DOWN",
                },
                "risks": ["Center banner at y=0.54 hides Katarina and un-limited AAC clips."],
                "deduction_rationale": "Fade-in at t=0, center captions, and disabled limiter degrade legibility, combat view, and audio.",
            },
        ),
        (
            "predict_change_effect",
            {
                "before": {"score": 88.0, "frame0_legible": True, "kill_zone": "upper_safe", "clip": 0},
                "proposed_changes": {"description": "cosmetic code cleanup without touching render or audio"},
            },
            {
                "expected_verdict": "NO_CHANGE",
                "expected_metric_shifts": {"watchability_score": "SAME"},
                "risks": ["Cosmetic edit touches no rendered video or audio metric."],
                "deduction_rationale": "No visual framing, overlay, or audio filter changes, so rendered watchability remains unchanged.",
            },
        ),
        (
            "predict_change_effect",
            {
                "before": {"score": 72.0, "first_kill_out_sec": 6.1, "audio_clip_gt_096": 0},
                "proposed_changes": {"lead_in_max_s": 3.5, "disable_audio_limiter": True},
            },
            {
                "expected_verdict": "MIXED",
                "expected_metric_shifts": {
                    "first_kill_out_sec": "DOWN",
                    "audio_clip_gt_096": "UP",
                    "watchability_score": "SAME",
                },
                "risks": ["Faster lead-in helps pacing while disabling limiter causes AAC clipping."],
                "deduction_rationale": "Shorter lead-in tightens the hook, but removing the limiter adds audio distortion.",
            },
        ),
        (
            "watchability_compare",
            {
                "verdict": "BETTER",
                "actually_changed": True,
                "delta_watchability": 16.88,
                "mean_frame_mad": 21.92,
                "improvements": ["hook_is_generic: True -> False", "av_delta_s: 0.067 -> 0.033", "camera_peak_step_px: 615.0 -> 484.0"],
                "regressions": [],
                "hypothesis_status": "CONFIRMED",
            },
            {
                "verdict": "BETTER",
                "actually_changed": True,
                "hypothesis_status": "CONFIRMED",
                "watchability_summary": "BETTER (+16.88, MAD=21.92): specific hook, tighter A/V sync, and safer camera step without regressions.",
                "next_fix": "none",
            },
        ),
        (
            "watchability_compare",
            {
                "verdict": "WORSE",
                "actually_changed": True,
                "delta_watchability": -16.88,
                "mean_frame_mad": 21.92,
                "improvements": [],
                "regressions": ["av_delta_s: 0.033 -> 0.067", "camera_peak_step_px: 484.0 -> 615.0"],
                "hypothesis_status": "REFUTED",
            },
            {
                "verdict": "WORSE",
                "actually_changed": True,
                "hypothesis_status": "REFUTED",
                "watchability_summary": "WORSE (-16.88, MAD=21.92): A/V desync widened and camera jump exceeded Shunpo safety limits.",
                "next_fix": "Restore -shortest atrim sync and 145px Shunpo edge guard.",
            },
        ),
        (
            "watchability_compare",
            {
                "verdict": "NO_CHANGE",
                "actually_changed": False,
                "delta_watchability": 0.0,
                "mean_frame_mad": 0.0,
                "improvements": [],
                "regressions": [],
                "hypothesis_status": "NO_EFFECT",
            },
            {
                "verdict": "NO_CHANGE",
                "actually_changed": False,
                "hypothesis_status": "NO_EFFECT",
                "watchability_summary": "NO_CHANGE (delta=0.0, MAD=0.0): frames and audio stayed identical despite expected improvement.",
                "next_fix": "Verify edit reaches rendered frames or filtergraph.",
            },
        ),
        (
            "watchability_compare",
            {
                "verdict": "MIXED",
                "actually_changed": True,
                "delta_watchability": 2.4,
                "mean_frame_mad": 14.5,
                "improvements": ["first_kill_out_sec: 5.8 -> 4.1"],
                "regressions": ["hook_is_generic: False -> True"],
                "hypothesis_status": "PARTIAL",
            },
            {
                "verdict": "MIXED",
                "actually_changed": True,
                "hypothesis_status": "PARTIAL",
                "watchability_summary": "MIXED (+2.4, MAD=14.5): faster first kill improved pacing while generic hook offset gains.",
                "next_fix": "Restore custom hook text from pre-render Synapsa call.",
            },
        ),
    ]

    examples: List[Dict[str, str]] = [
        {"instruction": build_synapsa_instruction(t, inp), "output": json.dumps(out, ensure_ascii=False)}
        for t, inp, out in anchors
    ]

    vlp = Path(verification_log_path) if verification_log_path is not None else DEFAULT_VERIFICATION_LOG
    seen_keys = set()
    if vlp.is_file():
        for raw_line in vlp.read_text(encoding="utf-8", errors="ignore").splitlines():
            if len(examples) >= int(max_examples):
                break
            if not raw_line.strip():
                continue
            try:
                rec = json.loads(raw_line)
            except Exception:
                continue
            if not isinstance(rec, dict) or not rec.get("verdict"):
                continue
            key = (rec.get("before_file"), rec.get("after_file"), rec.get("verdict"), rec.get("expected_verdict"))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            imps = [_clean_text(x, 60) for x in (rec.get("improvements") or [])[:4]]
            regs = [_clean_text(x, 60) for x in (rec.get("regressions") or [])[:4]]
            verdict = str(rec.get("verdict") or "NO_CHANGE")
            changed = bool(rec.get("actually_changed"))
            hyp_status = str(rec.get("hypothesis_status") or ("CONFIRMED" if verdict == rec.get("expected_verdict") else "NO_EFFECT"))
            delta = float(rec.get("delta_watchability") or 0.0)
            mad = float(rec.get("mean_frame_mad") or 0.0)

            cmp_in = {
                "verdict": verdict,
                "actually_changed": changed,
                "delta_watchability": round(delta, 2),
                "mean_frame_mad": round(mad, 3),
                "improvements": imps,
                "regressions": regs,
                "hypothesis_status": hyp_status,
            }
            next_fix = regs[0] if regs else ("Verify edit reached render." if not changed else "none")
            summary = _clean_text(
                f"{verdict} ({delta:+.2f}, MAD={mad:.2f}): +{len(imps)} / -{len(regs)} metrics; hypothesis {hyp_status}.",
                160,
            )
            cmp_out = {
                "verdict": verdict,
                "actually_changed": changed,
                "hypothesis_status": hyp_status,
                "watchability_summary": summary,
                "next_fix": _clean_text(next_fix, 90),
            }
            examples.append({
                "instruction": build_synapsa_instruction("watchability_compare", cmp_in),
                "output": json.dumps(cmp_out, ensure_ascii=False),
            })

            ch = rec.get("proposed_changes") or {}
            exp_v = rec.get("expected_verdict")
            if ch and exp_v and len(examples) < int(max_examples):
                pred_in = {
                    "before": {"score": rec.get("before_score"), "action": rec.get("action_type")},
                    "proposed_changes": ch,
                }
                pred_out = {
                    "expected_verdict": str(exp_v),
                    "expected_metric_shifts": {"watchability_score": "UP" if exp_v == "BETTER" else ("DOWN" if exp_v == "WORSE" else "SAME")},
                    "risks": [regs[0] if regs else "Check rendered frames and A/V sync against hypothesis."],
                    "deduction_rationale": _clean_text(f"Predicted {exp_v} for {list(ch.keys())[:3]}; measured {verdict} ({delta:+.1f}).", 150),
                }
                examples.append({
                    "instruction": build_synapsa_instruction("predict_change_effect", pred_in),
                    "output": json.dumps(pred_out, ensure_ascii=False),
                })

    return examples[: int(max_examples)]


def build_historical_evolution_training_examples(
    memory_path: Optional[Path] = None,
    max_examples: int = 14,
) -> List[Dict[str, str]]:
    """Buduje zwięzłe przykłady QLoRA (<=480 tokenów) z historii zmian wartości przed rozmową + Etap 11."""
    try:
        from lol_agent.synapsa_engine import build_synapsa_instruction
    except ImportError:
        from synapsa_engine import build_synapsa_instruction

    mp = Path(memory_path) if memory_path is not None else DEFAULT_MEMORY_PATH
    mem = _load_memory(mp) if mp.is_file() else {}
    hist = list(mem.get("historical_value_evolution") or [])
    if not hist:
        hist = extract_pre_conversation_value_history()

    # Kotwice kontrfaktyczne predict_change_effect: ostrzeganie przed cofnięciem wypracowanych limitów
    counterfactual_examples: List[Dict[str, str]] = []
    cf_specs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = [
        (
            {
                "before": {"smooth_win": 5, "max_pan_px": 80.0, "lerp_alpha": 0.45, "watchability": 94.0},
                "proposed_changes": {"smooth_win": 13, "max_pan_px": 25.0, "lerp_alpha": 0.18},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"player_edge_clip_ratio": "UP", "watchability_score": "DOWN"},
                "risks": ["COFNIECIE do SMOOTH_WIN=13 i MAX_PAN=25px spóźnia kamerę za dashem (>0.4s opóźnienia)."],
                "deduction_rationale": "Historyczna zmiana 8f73898 (13->5, 25->80, 0.18->0.45) dała płynny tracking; powrót ucina akcję.",
            },
        ),
        (
            {
                "before": {"end_freeze_sec": 0.6, "buildup_sec": 1.8, "watchability": 92.0},
                "proposed_changes": {"end_freeze_sec": 1.5, "min_lead_in_sec": 1.5},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"first_kill_out_sec": "DOWN", "watchability_score": "DOWN"},
                "risks": ["end_freeze>0.8s mrozi kadr przed ostatnim fragiem, a lead_in<4.5s ucina setup walki."],
                "deduction_rationale": "Złoty baseline 2dbc526 (45.8k views, 112-135% AVD) wymaga freeze<=0.6s i >=4.5s buildup.",
            },
        ),
        (
            {
                "before": {"min_sample_for_bucket": 8, "shrink_k": 10.0, "min_lead_to_win": 0.15},
                "proposed_changes": {"min_sample_for_bucket": 2, "shrink_k": 0.0},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"watchability_score": "DOWN"},
                "risks": ["Próg n=2 zmienia szum kilku filmów w globalną regułę montażu i rozstraja reżysera."],
                "deduction_rationale": "Reguła 4f0e0a0 wymusza min_bucket=8, min_lead=15% i shrink_k=10.0 przeciw fałszywym zwycięzcom.",
            },
        ),
        (
            {
                "before": {"zoom_max": 1.12, "slowmo_window_max": 0.7, "av_delta_s": 0.01},
                "proposed_changes": {"zoom_max": 1.35, "slowmo_window_max": 2.5},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"camera_peak_step_px": "UP", "watchability_score": "DOWN"},
                "risks": ["Zoom 1.35x i slowmo 2.5s powodują mdłości kadru i spadek retencji jak w cinematic."],
                "deduction_rationale": "Kontrakt edit_limits (zoom<=1.12/0.4s, slowmo<=0.7s) utrzymuje 105.3% AVD zamiast rozwlekłego 2.5s.",
            },
        ),
        (
            {
                "before": {"pacing": "balanced_14_17s", "median_views": 1830},
                "proposed_changes": {"pacing": "cinematic_18_25s", "outro_sec": 3.5},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"watchability_score": "DOWN"},
                "risks": ["Bucket cinematic (med=1543 views) przegrywa z balanced 14-17s (med=1830 views) i wydłuża puste outro."],
                "deduction_rationale": "Dane 207 filmów pokazują wyraźną przewagę balanced_14_17s nad rozwlekłym cinematic.",
            },
        ),
        (
            {
                "before": {"nvenc_maxrate": "16M", "audio_bitrate_kbps": 128, "fps_mode": "cfr"},
                "proposed_changes": {"nvenc_unbounded_cq18": True, "video_bitrate_mbps": 29.24, "fps_mode": "vfr"},
            },
            {
                "expected_verdict": "WORSE",
                "expected_metric_shifts": {"watchability_score": "DOWN"},
                "risks": ["Strumień 29.24 Mbps > limit 25 Mbps IG i VFR powodują ProcessingFailedError w rupload."],
                "deduction_rationale": "Bez -maxrate 16M i CFR 48kHz/128k plik urasta do 87 MB i zostaje odrzucony przez Instagram Reels.",
            },
        ),
    ]
    for pred_in, pred_out in cf_specs:
        counterfactual_examples.append({
            "instruction": build_synapsa_instruction("predict_change_effect", pred_in),
            "output": json.dumps(pred_out, ensure_ascii=False),
        })

    # Rekordy przyczynowo-skutkowe z realnej historii projektu (sprzed rozmowy + Etap 11)
    causal_examples: List[Dict[str, str]] = []
    for row in hist:
        payload = {
            "evidence_type": "historical_value_evolution",
            "era": row.get("era", "pre_conversation"),
            "source": _clean_text(row.get("source_artifact", ""), 65),
            "parameter_change": _clean_text(row.get("parameter_change", ""), 130),
        }
        out_obj = {
            "verdict": "IMPROVED",
            "affected_metrics": {"measured_effect": _clean_text(row.get("measured_effect", ""), 135)},
            "causal_rule": _clean_text(row.get("causal_rule", ""), 155),
            "recommended_action": "KEEP_CHANGE",
        }
        causal_examples.append({
            "instruction": build_synapsa_instruction("engineering_cause_effect", payload),
            "output": json.dumps(out_obj, ensure_ascii=False),
        })

    cap = max(1, int(max_examples))
    cf_take = counterfactual_examples[: min(len(counterfactual_examples), cap)]
    hist_cap = max(0, cap - len(cf_take))
    return (causal_examples[:hist_cap] + cf_take)[:cap]
