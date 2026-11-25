"""
Flikcut / Shortsyt — Long-Form 16:9 Compilation Engine (`Etap 31.2`)
===================================================================
Składa poziome filmy kompilacyjne `1920x1080@60` dla League of Legends z:
  - 0:00 Cold Open (zapowiedź kulminacji #1 ucięta przed finałowym killem),
  - kolejnością odliczania `#N -> #1` i falą tempa (przeplatanie teamfight/1v1),
  - dyskretną kartą e-sportową lower-third (pozycja + wyświetlenia Shorts + KDA),
  - automatycznym cięciem tabeli TAB (`_detect_tab_scoreboard_start`),
  - rotowanymi przejściami FFmpeg `xfade` z dokładnym próbkowaniem długości segmentów,
  - wieloutworowym podkładem NCS (`acrossfade`) + duckingiem `-3 dB` (`sidechaincompress`),
  - końcową strefą 11-12s pod karty YouTube End-Screen.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

LOL_AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_MUSIC_DIR = LOL_AGENT_DIR / "lol_music"

_XFADE_CYCLE = ("fadewhite", "smoothleft", "zoomin", "dissolve")


def _ascii_safe(text: str) -> str:
    cleaned = re.sub(r"[^\x20-\x7E]", "", str(text or ""))
    return cleaned.replace("'", "").replace(":", " ").replace("\\", "").strip()


def _probe_media(path: str | Path) -> Tuple[float, bool]:
    """Zwraca `(duration_s, has_audio)` dla wskazanego pliku wideo/audio."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return 0.0, False
    try:
        data = json.loads(r.stdout or "{}")
        dur = float((data.get("format") or {}).get("duration") or 0.0)
        has_audio = any(s.get("codec_type") == "audio" for s in (data.get("streams") or []))
        return dur, has_audio
    except Exception:
        return 0.0, False


def _detect_encoder_args() -> List[str]:
    try:
        from lol_agent.lol_editor import detect_hardware, get_optimal_encoder_args
        enc, _ = detect_hardware()
        if enc in ("h264_nvenc", "h264_amf", "h264_qsv"):
            return list(get_optimal_encoder_args("high"))
    except Exception:
        pass
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def _run_ffmpeg_checked(cmd: List[str], timeout: float = 300.0, desc: str = "ffmpeg") -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0 and any("nvenc" in str(a) or "amf" in str(a) or "qsv" in str(a) for a in cmd):
        # Bezpieczny fallback CPU
        cpu_cmd: List[str] = []
        skip_next = False
        hw_flags = {"-c:v", "-preset", "-cq", "-rc", "-b:v", "-maxrate", "-bufsize", "-profile:v", "-spatial-aq", "-temporal-aq", "-rc-lookahead"}
        i = 0
        out_arg = cmd[-1]
        while i < len(cmd) - 1:
            tok = str(cmd[i])
            if skip_next:
                skip_next = False
                i += 1
                continue
            if tok in hw_flags:
                skip_next = True
                i += 1
                continue
            cpu_cmd.append(tok)
            i += 1
        cpu_cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out_arg])
        r = subprocess.run(cpu_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{desc} failed (rc={r.returncode}): {(r.stderr or '')[-500:]}")
    return r


def _interleave_pace_countdown(clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Układa klipy w kolejności rosnącej `#N -> #1` (najmocniejszy klip na koniec),
    przeplatając akcje grupowe z pojedynkami `1v1` / `clutch` dla falowania tempa.
    """
    if len(clips) <= 2:
        return list(reversed(clips))

    # Zakładamy, że `clips` jest posortowane malejąco (`[best, second, ..., weakest]`).
    best = clips[0]
    rest_asc = list(reversed(clips[1:]))  # od słabszych do coraz mocniejszych

    chaotic: List[Dict[str, Any]] = []
    duel: List[Dict[str, Any]] = []
    for c in rest_asc:
        act = str(c.get("action_type") or "").lower()
        if act in ("solo_bolo", "solo", "1v1", "clutch"):
            duel.append(c)
        else:
            chaotic.append(c)

    if duel and chaotic:
        wave: List[Dict[str, Any]] = []
        while chaotic or duel:
            if chaotic:
                wave.append(chaotic.pop(0))
            if chaotic:
                wave.append(chaotic.pop(0))
            if duel:
                wave.append(duel.pop(0))
        rest_ordered = wave
    else:
        rest_ordered = rest_asc

    return rest_ordered + [best]


def _resolve_clip_window(clip: Dict[str, Any], src_dur: float, target_seg_max: float) -> Tuple[float, float, float]:
    cs = float(clip.get("clip_start") or 0.0)
    ce = float(clip.get("clip_end") or 0.0)
    if ce > cs + 3.0 and src_dur > 0.0:
        cs = max(0.0, min(cs, max(0.0, src_dur - 4.0)))
        ce = min(src_dur, max(cs + 3.5, ce))
    elif src_dur > 0.0:
        ce = src_dur
        cs = max(0.0, src_dur - target_seg_max)
    else:
        cs, ce = 0.0, 12.0

    peaks = clip.get("peaks") or []
    last_pk_abs = ce - 2.0
    if peaks:
        try:
            vals = [float(p[0]) for p in peaks if isinstance(p, (list, tuple)) and p]
            if vals:
                last_rel = max(vals)
                last_pk_abs = last_rel if last_rel > (ce - cs) and last_rel >= cs else (cs + last_rel)
        except Exception:
            pass
    last_pk_abs = max(cs + 1.0, min(last_pk_abs, ce - 0.5))

    # Przytnij ewentualny końcowy ekran TAB
    src_path = str(clip.get("resolved_media_path") or clip.get("vault_path") or clip.get("source_path") or "")
    try:
        from lol_agent.lol_editor import _detect_tab_scoreboard_start
        tab_t = _detect_tab_scoreboard_start(src_path, cs, ce, last_pk_abs)
        if tab_t is not None:
            new_ce = max(last_pk_abs + 0.85, tab_t - 0.15)
            if new_ce >= cs + 4.0 and new_ce < ce - 0.2:
                ce = round(new_ce, 2)
    except Exception:
        pass

    if (ce - cs) > target_seg_max:
        trim_s = max(0.0, ce - target_seg_max)
        if trim_s < last_pk_abs - 1.8:
            cs = round(trim_s, 2)

    return round(cs, 2), round(ce, 2), round(last_pk_abs, 2)


def _find_font_safe() -> str:
    try:
        from lol_agent.lol_editor import _get_font_path
        fp = _get_font_path()
        if fp:
            return fp.replace("\\", "/").replace(":", "\\:")
    except Exception:
        pass
    for p in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\segoeui.ttf"):
        if os.path.isfile(p):
            return p.replace("\\", "/").replace(":", "\\:")
    return ""


def _render_normalized_segment(
    src_path: str,
    start_s: float,
    end_s: float,
    out_path: Path,
    enc_args: List[str],
    top_banner: str = "",
    lower_line1: str = "",
    lower_line2: str = "",
    font_safe: str = "",
    zoom_punch: bool = False,
    blur_endscreen: bool = False,
    endscreen_title: str = "",
    audio_gain: float = 1.0,
) -> float:
    dur, has_audio = _probe_media(src_path)
    s = max(0.0, min(start_s, max(0.0, dur - 1.0))) if dur > 0 else start_s
    e = min(dur, max(s + 1.0, end_s)) if dur > 0 else end_s
    seg_len = max(1.0, round(e - s, 3))

    vf_parts = [
        "scale=1920:1080:force_original_aspect_ratio=decrease",
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black",
        "fps=60",
        "setsar=1",
    ]
    if blur_endscreen:
        vf_parts.append("gblur=sigma=12,eq=brightness=-0.20:saturation=0.85,vignette=angle=PI/5")
    elif zoom_punch:
        vf_parts.append("scale=2040:1148:flags=lanczos,crop=1920:1080:(iw-1920)/2:(ih-1080)/2,eq=contrast=1.10:saturation=1.25,vignette=angle=PI/6")
    else:
        vf_parts.append("eq=contrast=1.07:saturation=1.20:brightness=0.02")

    if top_banner and font_safe:
        bt = _ascii_safe(top_banner)
        vf_parts.append(
            f"drawtext=fontfile='{font_safe}':text='{bt}':x=(w-text_w)/2:y=56:"
            f"fontsize=48:fontcolor=0xFFD700:borderw=4:bordercolor=black:"
            f"box=1:boxcolor=black@0.65:boxborderw=14:enable='between(t,0.1,{max(0.5, seg_len - 0.1):.2f})'"
        )

    if lower_line1 and font_safe:
        t1 = _ascii_safe(lower_line1)
        t2 = _ascii_safe(lower_line2)
        show_end = min(seg_len - 0.15, 4.0)
        if show_end > 0.6:
            vf_parts.append(
                f"drawbox=x=46:y=h-172:w=560:h=102:color=0x0B0E14@0.82:t=fill:enable='between(t,0.25,{show_end:.2f})'"
            )
            vf_parts.append(
                f"drawbox=x=46:y=h-172:w=8:h=102:color=0xC89B3C@0.95:t=fill:enable='between(t,0.25,{show_end:.2f})'"
            )
            vf_parts.append(
                f"drawtext=fontfile='{font_safe}':text='{t1}':x=72:y=h-158:"
                f"fontsize=32:fontcolor=0xFFFFFF:borderw=2:bordercolor=black:enable='between(t,0.25,{show_end:.2f})'"
            )
            if t2:
                vf_parts.append(
                    f"drawtext=fontfile='{font_safe}':text='{t2}':x=72:y=h-114:"
                    f"fontsize=23:fontcolor=0xFFD700:borderw=2:bordercolor=black:enable='between(t,0.25,{show_end:.2f})'"
                )

    if endscreen_title and font_safe:
        et = _ascii_safe(endscreen_title)
        vf_parts.append(
            f"drawtext=fontfile='{font_safe}':text='{et}':x=(w-text_w)/2:y=115:"
            f"fontsize=54:fontcolor=0xFFFFFF:borderw=4:bordercolor=black"
        )
        # Ramki pod karty YouTube End-Screen (lewa i prawa strona, bez nakładania)
        vf_parts.append("drawbox=x=180:y=320:w=560:h=315:color=0xC89B3C@0.45:t=4")
        vf_parts.append("drawbox=x=1180:y=320:w=560:h=315:color=0xC89B3C@0.45:t=4")
        vf_parts.append(
            f"drawtext=fontfile='{font_safe}':text='WATCH NEXT':x=345:y=660:fontsize=26:fontcolor=0xE2E8F0:borderw=2:bordercolor=black"
        )
        vf_parts.append(
            f"drawtext=fontfile='{font_safe}':text='SUBSCRIBE':x=1380:y=660:fontsize=26:fontcolor=0xFFD700:borderw=2:bordercolor=black"
        )

    vf_str = ",".join(vf_parts)
    cmd = ["ffmpeg", "-y", "-ss", f"{s:.3f}", "-t", f"{seg_len:.3f}", "-i", str(src_path)]
    if has_audio:
        af_str = f"aresample=48000,aformat=channel_layouts=stereo,volume={audio_gain:.2f}"
        cmd.extend(["-vf", vf_str, "-af", af_str])
    else:
        cmd.extend([
            "-f", "lavfi", "-t", f"{seg_len:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", vf_str,
        ])
    cmd.extend([*enc_args, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out_path)])
    _run_ffmpeg_checked(cmd, timeout=180.0, desc=f"normalize segment {out_path.name}")
    out_dur, _ = _probe_media(out_path)
    return out_dur if out_dur > 0 else seg_len


def _build_music_bed(
    music_dir: Path,
    target_duration: float,
    out_audio_path: Path,
) -> Tuple[Optional[Path], List[str]]:
    """Łączy kolejne tracki NCS (`acrossfade=d=2.0`) na długość całego filmu 16:9."""
    tracks = sorted(music_dir.glob("*.mp3")) + sorted(music_dir.glob("*.wav")) if music_dir.is_dir() else []
    if not tracks:
        return None, []

    chosen: List[Path] = []
    acc_dur = 0.0
    idx = 0
    while acc_dur < target_duration + 6.0 and idx < 24:
        tr = tracks[idx % len(tracks)]
        tr_dur, has_a = _probe_media(tr)
        if tr_dur <= 1.0 or not has_a:
            idx += 1
            continue
        chosen.append(tr)
        acc_dur += max(1.0, tr_dur - (2.0 if len(chosen) > 1 else 0.0))
        idx += 1

    if not chosen:
        return None, []

    cmd = ["ffmpeg", "-y"]
    for tr in chosen:
        cmd.extend(["-i", str(tr)])

    if len(chosen) == 1:
        af = (
            f"[0:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"atrim=0:{target_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.5, target_duration - 2.5):.3f}:d=2.5[m]"
        )
    else:
        fc_parts: List[str] = []
        for i in range(len(chosen)):
            fc_parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[m_in{i}]")
        prev = "m_in0"
        for i in range(1, len(chosen)):
            out_lbl = f"m_xf{i}"
            fc_parts.append(f"[{prev}][m_in{i}]acrossfade=d=2.0:c1=tri:c2=tri[{out_lbl}]")
            prev = out_lbl
        fc_parts.append(
            f"[{prev}]atrim=0:{target_duration:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.5, target_duration - 2.5):.3f}:d=2.5[m]"
        )
        af = ";".join(fc_parts)

    cmd.extend(["-filter_complex", af, "-map", "[m]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out_audio_path)])
    _run_ffmpeg_checked(cmd, timeout=180.0, desc="build music bed")
    used_names = []
    for t in chosen:
        if t.stem not in used_names:
            used_names.append(t.stem)
    return out_audio_path, used_names


def render_longform_compilation(
    clips: List[Dict[str, Any]],
    output_path: str | Path,
    mode: str = "weekly",
    champion: str = "Katarina",
    music_dir: Optional[str | Path] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Składa poziomą kompilację `1920x1080@60`:
      Cold Open -> Klipy `#N..#1` z przeplataniem tempa -> End-Screen 11s.
    """
    if not clips:
        raise ValueError("Brak klipów wejściowych do kompilacji 16:9")

    def _prog(pct: int, msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass

    out_mp4 = Path(output_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    mdir = Path(music_dir) if music_dir is not None else DEFAULT_MUSIC_DIR
    enc_args = _detect_encoder_args()
    font_safe = _find_font_safe()

    # Wybierz docelowy czas per segment dla trybu weekly (~3:30-5:00) vs monthly (~8:15-10:30)
    max_seg_s = 22.0 if mode == "monthly" else 20.0
    ordered_clips = _interleave_pace_countdown(clips)
    n_total = len(ordered_clips)

    _prog(8, f"Przygotowanie {n_total} segmentów w trybie {mode}...")
    tmp_dir = Path(tempfile.mkdtemp(prefix="flikcut_longform_"))
    try:
        segment_records: List[Dict[str, Any]] = []
        total_n = len(ordered_clips)
        hero_clip = ordered_clips[-1]  # Ostatni klip w kolejności odliczania to #1!
        hero_src = str(hero_clip.get("resolved_media_path") or hero_clip.get("vault_path") or hero_clip.get("source_path") or "")
        hero_dur, _ = _probe_media(hero_src)
        hero_cs, hero_ce, hero_pk = _resolve_clip_window(hero_clip, hero_dur, max_seg_s)

        # 0. Cold Open (4.2s zajawki tuż przed finałowym zabójstwem klipu #1)
        co_end = max(hero_cs + 3.2, hero_pk - 0.35)
        co_start = max(0.0, co_end - 4.2)
        co_path = tmp_dir / "seg_00_cold_open.mp4"
        co_dur = _render_normalized_segment(
            hero_src,
            co_start,
            co_end,
            co_path,
            enc_args,
            top_banner="WAIT FOR #1 PLAY...",
            font_safe=font_safe,
            zoom_punch=True,
            audio_gain=1.10,
        )
        segment_records.append({
            "kind": "cold_open",
            "label": "Cold Open — #1 Teaser",
            "path": co_path,
            "duration_s": co_dur,
        })

        # 1..N. Klipy #N -> #1
        for i, clip in enumerate(ordered_clips):
            countdown_pos = total_n - i
            src_p = str(clip.get("resolved_media_path") or clip.get("vault_path") or clip.get("source_path") or "")
            if not src_p or not os.path.isfile(src_p):
                continue
            src_d, _ = _probe_media(src_p)
            cs, ce, pk_abs = _resolve_clip_window(clip, src_d, max_seg_s)
            pct = 15 + int((i / max(1, total_n)) * 45)
            _prog(pct, f"Normalizacja segmentu #{countdown_pos}/{total_n} ({Path(src_p).name})")

            act_lbl = str(clip.get("action_type") or "outplay").replace("_", " ").upper()
            ch_lbl = str(clip.get("champion") or champion or "Katarina").upper()
            views_val = int(clip.get("views") or 0)
            kda_val = str(clip.get("match_kda") or "").strip()
            parts_l2 = []
            if views_val >= 1000:
                parts_l2.append(f"{views_val / 1000.0:.1f}K SHORTS VIEWS")
            elif views_val > 0:
                parts_l2.append(f"{views_val} SHORTS VIEWS")
            else:
                parts_l2.append("WEEKLY HIGHLIGHT")
            if kda_val:
                parts_l2.append(f"KDA {kda_val}")

            seg_path = tmp_dir / f"seg_{i + 1:02d}.mp4"
            seg_dur = _render_normalized_segment(
                src_p,
                cs,
                ce,
                seg_path,
                enc_args,
                lower_line1=f"#{countdown_pos} | {ch_lbl} {act_lbl}",
                lower_line2=" | ".join(parts_l2),
                font_safe=font_safe,
                zoom_punch=(countdown_pos == 1),
                audio_gain=1.0,
            )
            segment_records.append({
                "kind": "clip",
                "rank": countdown_pos,
                "label": f"#{countdown_pos} {ch_lbl} {act_lbl.title()}",
                "path": seg_path,
                "duration_s": seg_dur,
                "clip": clip,
            })

        # N+1. Strefa 11s pod End-Screen
        es_path = tmp_dir / "seg_99_endscreen.mp4"
        es_start = max(0.0, hero_ce - min(11.0, max(5.0, hero_dur * 0.4)))
        es_end = min(hero_dur, es_start + 11.0) if hero_dur > es_start + 1.0 else es_start + 6.0
        es_dur = _render_normalized_segment(
            hero_src,
            es_start,
            es_end,
            es_path,
            enc_args,
            font_safe=font_safe,
            blur_endscreen=True,
            endscreen_title=f"MORE {str(champion or 'KATARINA').upper()} PLAYS",
            audio_gain=0.35,
        )
        segment_records.append({
            "kind": "endscreen",
            "label": "Next Video & Subscribe",
            "path": es_path,
            "duration_s": es_dur,
        })

        # Złożenie segmentów z rotowanymi przejściami xfade + sync acrossfade audio gry
        _prog(68, "Łączenie scen przejściami xfade...")
        stitched_path = tmp_dir / "stitched_base.mp4"
        n_segs = len(segment_records)
        if n_segs == 1:
            shutil.copy2(segment_records[0]["path"], stitched_path)
            total_timeline_dur = float(segment_records[0]["duration_s"])
            chapters = [{"time_s": 0.0, "label": segment_records[0]["label"]}]
        else:
            inputs_cmd = ["ffmpeg", "-y"]
            for rec in segment_records:
                inputs_cmd.extend(["-i", str(rec["path"])])

            fc_lines: List[str] = []
            chapters: List[Dict[str, Any]] = []
            cur_dur = float(segment_records[0]["duration_s"])
            chapters.append({"time_s": 0.0, "label": segment_records[0]["label"]})
            v_prev = "0:v"
            a_prev = "0:a"

            for idx in range(1, n_segs):
                seg_d = float(segment_records[idx]["duration_s"])
                xf = round(min(0.35, max(0.15, min(cur_dur, seg_d) * 0.25)), 3)
                offset = max(0.1, round(cur_dur - xf, 3))
                if idx < n_segs - 1:
                    chapters.append({"time_s": round(offset, 1), "label": segment_records[idx]["label"]})
                tr_name = _XFADE_CYCLE[(idx - 1) % len(_XFADE_CYCLE)]
                v_out = f"vx{idx}"
                a_out = f"ax{idx}"
                fc_lines.append(
                    f"[{v_prev}][{idx}:v]xfade=transition={tr_name}:duration={xf:.3f}:offset={offset:.3f}[{v_out}]"
                )
                fc_lines.append(
                    f"[{a_prev}][{idx}:a]acrossfade=d={xf:.3f}:c1=tri:c2=tri[{a_out}]"
                )
                v_prev = v_out
                a_prev = a_out
                cur_dur = offset + seg_d

            total_timeline_dur = round(cur_dur, 2)
            fc_file = tmp_dir / "xfade_filter.txt"
            fc_file.write_text(";".join(fc_lines), encoding="utf-8")
            inputs_cmd.extend([
                "-filter_complex_script", str(fc_file),
                "-map", f"[{v_prev}]",
                "-map", f"[{a_prev}]",
                *enc_args,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                str(stitched_path),
            ])
            _run_ffmpeg_checked(inputs_cmd, timeout=360.0, desc="xfade stitch longform")

        stitched_dur, _ = _probe_media(stitched_path)
        if stitched_dur > 0:
            total_timeline_dur = round(stitched_dur, 2)

        # Podkład muzyczny NCS + audio ducking `-3 dB` (`sidechaincompress`)
        _prog(84, "Miksowanie wieloutworowego audio NCS z duckingiem...")
        music_bed, tracks_used = _build_music_bed(mdir, total_timeline_dur, tmp_dir / "music_bed.m4a")
        if music_bed and music_bed.is_file():
            mix_fc = (
                "[0:a]asplit=2[ga_sc][ga_mix];"
                "[1:a][ga_sc]sidechaincompress=threshold=0.04:ratio=3.5:attack=25:release=320[m_duck];"
                "[ga_mix]volume=0.74[ga_v];"
                "[m_duck]volume=0.28[m_v];"
                "[ga_v][m_v]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_out]"
            )
            mix_cmd = [
                "ffmpeg", "-y",
                "-i", str(stitched_path),
                "-i", str(music_bed),
                "-filter_complex", mix_fc,
                "-map", "0:v:0", "-map", "[a_out]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart",
                str(out_mp4),
            ]
            try:
                _run_ffmpeg_checked(mix_cmd, timeout=240.0, desc="sidechain music mix")
            except Exception:
                # Bezpieczny fallback bez sidechaincompress
                simple_cmd = [
                    "ffmpeg", "-y", "-i", str(stitched_path), "-i", str(music_bed),
                    "-filter_complex", "[0:a]volume=0.74[g];[1:a]volume=0.26[m];[g][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(out_mp4),
                ]
                _run_ffmpeg_checked(simple_cmd, timeout=240.0, desc="fallback simple music mix")
        else:
            shutil.copy2(stitched_path, out_mp4)

        _prog(100, "Kompilacja 16:9 gotowa")
        final_dur, has_final_audio = _probe_media(out_mp4)
        comp_id = f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:5]}"
        return {
            "comp_id": comp_id,
            "mode": mode,
            "champion": champion,
            "output_path": str(out_mp4),
            "output_filename": out_mp4.name,
            "duration_s": round(final_dur or total_timeline_dur, 2),
            "resolution": "1920x1080",
            "fps": 60,
            "has_audio": has_final_audio,
            "clips_count": sum(1 for s in segment_records if s["kind"] == "clip"),
            "clips_order": [s["label"] for s in segment_records if s["kind"] == "clip"],
            "chapters": chapters,
            "tracks_used": tracks_used,
            "hero_clip": {
                "source_path": hero_src,
                "peak_time_s": hero_pk,
                "action_type": str(hero_clip.get("action_type") or "outplay"),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
