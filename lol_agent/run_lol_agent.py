"""
LOL Agent — Główny skrypt uruchamiający cały pipeline
Użycie:
    python run_lol_agent.py                          # Automatycznie z folderu input
    python run_lol_agent.py --file "klip.mp4"        # Podaj plik ręcznie
    python run_lol_agent.py --file "klip.mp4" --champion "Jinx" --rank "Diamond"
    python run_lol_agent.py --authorize              # Tylko autoryzacja YT
    python run_lol_agent.py --dry-run               # Montaż bez uploadu
"""
import os
import sys
import re
import subprocess
import hashlib
import argparse
import shutil
import json
from datetime import datetime

# Dodaj ścieżkę projektu
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from lol_config import LOL_TEMP_DIR, LOL_ARCHIVE_DIR, YT_PRIVACY
from lol_clip_analyzer import scan_input_folder, analyze_clip, archive_clip
from lol_editor import render_short
from lol_metadata_generator import generate_metadata
from lol_publisher import get_lol_youtube_service, upload_lol_short, post_pinned_comment

try:
    from lol_momentum_analyzer import find_combat_segments
    COMBAT_SEG_OK = True
except ImportError:
    COMBAT_SEG_OK = False

# Thumbnail generator
try:
    from lol_thumbnail import generate_thumbnail
    THUMBNAIL_OK = True
except ImportError:
    THUMBNAIL_OK = False
    print("⚠️  lol_thumbnail.py niedostepny — miniaturki wylaczone")

# Medal DB integration
try:
    from medal_db import get_clip_metadata
    MEDAL_DB_OK = True
except ImportError:
    MEDAL_DB_OK = False

# Smart titles z YT performance
try:
    from lol_smart_titles import generate_smart_title
    SMART_TITLES_OK = True
except ImportError:
    SMART_TITLES_OK = False

# Quality scorer — compares rendered Short vs original
try:
    from lol_quality_scorer import score_short, save_quality_log, QUALITY_THRESHOLD
    QUALITY_SCORER_OK = True
except ImportError:
    QUALITY_SCORER_OK = False
    QUALITY_THRESHOLD = 0

# Clip ranker — scans all clips and picks the best one
try:
    from lol_clip_ranker import scan_and_rank, get_best_clip
    CLIP_RANKER_OK = True
except ImportError:
    CLIP_RANKER_OK = False

# Performance tracker — 48h YT stats + optimization
try:
    from lol_performance_tracker import schedule_check, run_pending_checks, generate_recommendations
    PERF_TRACKER_OK = True
except ImportError:
    PERF_TRACKER_OK = False


LOG_FILE = os.path.join(os.path.dirname(__file__), "lol_agent.log")


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def authorize_only():
    """Przeprowadza tylko autoryzację kanału LoL."""
    print("\n" + "="*60)
    print("🔐 AUTORYZACJA KANAŁU LOL (Dwannellenga)")
    print("="*60)
    print("\n📋 INSTRUKCJA:")
    print("1. Za chwilę otworzy się przeglądarka")
    print("2. Zaloguj się na konto Google DWANNELLENGA")
    print("3. Wybierz kanał League of Legends")
    print("4. Zezwól na dostęp\n")

    try:
        service = get_lol_youtube_service()
        channels = service.channels().list(part="snippet,statistics", mine=True).execute()

        print("\n✅ AUTORYZACJA ZAKOŃCZONA SUKCESEM!")
        print("\n📺 Dostępne kanały na tym koncie:")
        for ch in channels.get("items", []):
            name = ch["snippet"]["title"]
            subs = ch["statistics"].get("subscriberCount", "?")
            videos = ch["statistics"].get("videoCount", "?")
            print(f"   → {name} ({subs} subskrybentów, {videos} filmów)")

        print(f"\n🎮 Token zapisany w: accounts/lol_token.pickle")
        print("✅ Agent LoL jest gotowy do pracy!")

    except Exception as e:
        print(f"\n❌ Błąd autoryzacji: {e}")
        sys.exit(1)


def _find_ffmpeg() -> str:
    """Auto-detect ffmpeg binary."""
    candidates = [
        r"C:\ffmpeg\ffmpeg-8.0-full_build\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "ffmpeg"


def merge_split_clips(video_path: str) -> str:
    """
    Automatycznie wykrywa i łączy wieloczęściowe klipy (np. *_0.mp4, *_1.mp4).
    Jeśli podany plik jest częścią podzielonego klipu i istnieją kolejne części,
    scala je bezstratnie przez FFmpeg concat do LOL_TEMP_DIR i zwraca nową ścieżkę.
    """
    if not video_path or not os.path.exists(video_path):
        return video_path

    dirname = os.path.dirname(os.path.abspath(video_path))
    filename = os.path.basename(video_path)

    # Match pattern np. "ClipName_0.mp4"
    match = re.match(r"^(.*?)(?:_(\d+))(\.[a-zA-Z0-9]+)$", filename)
    if not match:
        return video_path

    base_name, current_idx, ext = match.groups()

    # Znajdź wszystkie pliki o tym samym base_name i rozszerzeniu
    parts = []
    idx = 0
    while True:
        part_candidate = os.path.join(dirname, f"{base_name}_{idx}{ext}")
        if os.path.exists(part_candidate):
            parts.append(part_candidate)
            idx += 1
        else:
            break

    if len(parts) <= 1:
        return video_path

    log(f"   🧩 Wykryto podzielony klip ({len(parts)} części): {', '.join([os.path.basename(p) for p in parts])}")

    os.makedirs(LOL_TEMP_DIR, exist_ok=True)
    clean_base = re.sub(r'[^a-zA-Z0-9_-]', '_', base_name)
    merged_output = os.path.join(LOL_TEMP_DIR, f"merged_{clean_base}{ext}")

    # Sprawdź czy scalony plik już istnieje i jest aktualny
    if os.path.exists(merged_output):
        merged_mtime = os.path.getmtime(merged_output)
        if all(merged_mtime >= os.path.getmtime(p) for p in parts):
            log(f"   ⚡ Używam istniejącego scalonego klipu: {os.path.basename(merged_output)}")
            return merged_output

    # Przygotuj listę dla FFmpeg concat demuxer
    concat_list_file = os.path.join(LOL_TEMP_DIR, f"concat_{clean_base}.txt")
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for part in parts:
            safe_part_path = part.replace("\\", "/")
            f.write(f"file '{safe_part_path}'\n")

    ffmpeg_bin = _find_ffmpeg()
    log(f"   🎬 Scalanie {len(parts)} części przez FFmpeg...")

    # 1. Próba szybkiego concat bez re-encode (-c copy)
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_file,
        "-c", "copy",
        merged_output
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 2. Fallback na re-encode jeśli -c copy się nie powiedzie
    if res.returncode != 0 or not os.path.exists(merged_output) or os.path.getsize(merged_output) == 0:
        log("   ⚠️  Concat stream copy nie powiódł się — ponawiam z transkodowaniem...")
        cmd_reencode = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_file,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac",
            merged_output
        ]
        res = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if res.returncode == 0 and os.path.exists(merged_output) and os.path.getsize(merged_output) > 0:
        log(f"   ✅ Pomyślnie scalono klipy w: {os.path.basename(merged_output)}")
        return merged_output
    else:
        log(f"   ❌ Błąd scalania klipów FFmpeg (kod: {res.returncode}). Używam oryginalnego pliku.")
        return video_path


def run_pipeline(
    video_path: str = None,
    champion: str = "",
    rank: str = "",
    action: str = "",
    dry_run: bool = False,
    no_slowmo: bool = False,
    force: bool = False,
    privacy: str = YT_PRIVACY,
    clip_start_override: float = None,
    clip_end_override: float = None,
    preferred_music: str = None,
    custom_title: str = "",
    schedule: str = "",
    segments_override: list = None,   # ręczne segmenty jump-cut [(s1,e1),(s2,e2)]
    peak_override: float = None,      # ręczny peak_moment w sekundach (bezwzgl.)
    peaks_override: list = None,      # ręczne kill peaks [(t_abs, label)] np. [(42.0,'PENTAKILL')]
):
    """Uruchamia pełny pipeline LOL."""
    log("="*60)
    log("🚀 LOL AGENT PIPELINE START")
    log("="*60)

    # === Check pending 48h performance reviews ===
    if PERF_TRACKER_OK:
        try:
            run_pending_checks()
        except Exception as _e:
            if "invalid_grant" in str(_e).lower():
                log("⚠️  Token YT wygasł (invalid_grant) — uruchom: python run_lol_agent.py --authorize")
            else:
                log(f"⚠️  Performance check error: {_e}")

    # === ETAP 1: Znajdź klip ===
    log("\n[ETAP 1/4] Wyszukiwanie klipu...")

    if video_path:
        if not os.path.exists(video_path):
            log(f"ERROR File not found: {video_path}")
            return
        source_clip = video_path
        log(f"   Source: {os.path.basename(source_clip)}")
    else:
        # Use clip ranker to pick best clip if available
        if CLIP_RANKER_OK:
            log("   Ranking all clips in input folder...")
            source_clip = get_best_clip()
            if not source_clip:
                log("   No clips scored above quality threshold.")
                log("   Check lol_clip_ranker.py output for details.")
                return
            log(f"   Best clip selected: {os.path.basename(source_clip)}")
        else:
            source_clip = scan_input_folder()
        if not source_clip:
            log("No clips in input folder.")
            log(f"   Drop a file into: {os.path.dirname(__file__)}")
            return

    original_source_file = source_clip

    # === Deduplication Check 1: Przed scaleniem i analizą ===
    if not dry_run:
        is_dup, dup_reason, dup_info = check_duplicate_clip(source_clip, original_source_file)
        if is_dup:
            log(f"🛑 DUPLICATE BLOCKED ({dup_reason}): ten klip został już opublikowany!")
            log(f"   URL: {dup_info.get('url', '?')}")
            log(f"   Tytuł: '{dup_info.get('title', '?')}' (Data: {dup_info.get('date', '?')})")
            log("   Użyj --force, aby wymusić ponowny montaż.")
            if not force:
                return

    # === Auto-Merge Split Clips (np. _0.mp4 + _1.mp4) ===
    source_clip = merge_split_clips(source_clip)

    # === Deduplication Check 2: Po scaleniu (MD5 & stem scalonego pliku) ===
    if not dry_run:
        is_dup, dup_reason, dup_info = check_duplicate_clip(source_clip, original_source_file)
        if is_dup:
            log(f"🛑 DUPLICATE BLOCKED ({dup_reason}): ten klip został już opublikowany!")
            log(f"   URL: {dup_info.get('url', '?')}")
            log(f"   Tytuł: '{dup_info.get('title', '?')}' (Data: {dup_info.get('date', '?')})")
            log("   Użyj --force, aby wymusić ponowny montaż.")
            if not force:
                return


    # === ETAP 2: Analiza klipu ===
    log(f"\n[ETAP 2/5] Analiza klipu: {os.path.basename(source_clip)}")
    analysis = analyze_clip(source_clip, champion=champion, action_hint=(action or "").lower())
    if not champion and analysis.get("champion"):
        champion = analysis["champion"]

    # === Medal DB Auto-Detection ===
    medal_meta = {}
    if MEDAL_DB_OK:
        medal_meta = get_clip_metadata(source_clip)
        if medal_meta.get("source") == "medal_db":
            log(f"   🏅 Medal DB: '{medal_meta.get('title', '?')}'")
            if medal_meta.get("champion"):
                champion = medal_meta["champion"]
                log(f"   🏅 Auto-champion: {champion}")
            if medal_meta.get("action_type") and medal_meta["action_type"] != "outplay":
                analysis["action_type"] = medal_meta["action_type"]
                log(f"   🏅 Auto-action: {analysis['action_type']}")

    # Override action_type z CLI jesli podany
    if action:
        analysis["action_type"] = action.lower()
        log(f"   🎮 Action override (CLI): {action.upper()}")

    # Override okna klipu z CLI (--start / --end)
    if clip_start_override is not None:
        analysis["peak_start"] = clip_start_override
        log(f"   ✂️  Start override (CLI): {clip_start_override:.1f}s")
    if clip_end_override is not None:
        analysis["peak_end"] = clip_end_override
        log(f"   ✂️  End override (CLI): {clip_end_override:.1f}s")
    if clip_start_override is not None or clip_end_override is not None:
        analysis["clip_duration"] = analysis["peak_end"] - analysis["peak_start"]

    log(f"   🎯 Akcja: {analysis['action_type'].upper()}")
    log(f"   ⏱️  Okno: {analysis['peak_start']:.1f}s → {analysis['peak_end']:.1f}s")
    if champion:
        log(f"   🎮 Champion: {champion}")

    # === Semantic Action Deduplication (Fingerprint) ===
    action_fp = _compute_action_fingerprint(
        peaks=analysis.get("peaks", []),
        champion=champion,
        action_type=analysis.get("action_type", "")
    )
    analysis["action_fingerprint"] = action_fp

    processed_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
    processed = {}
    if os.path.exists(processed_path):
        with open(processed_path, encoding="utf-8") as f:
            processed = json.load(f)

    is_dup_action, dup_info = _is_duplicate_action(action_fp, processed)
    if is_dup_action:
        log("⚠️  DUPLICATE GAMEPLAY DETECTED!")
        log(f"   Identical kill sequence was already uploaded in: {dup_info.get('url', '?')}")
        log(f"   Title: '{dup_info.get('title', '?')}' (uploaded {dup_info.get('date', '?')})")
        if not dry_run and not force:
            log("   SKIPPING upload to avoid duplicate content strike. Use --force to override.")
            return

    # === ETAP 3: Montaż ===
    log(f"\n[ETAP 3/5] Montaż Shorta...")
    output_name = f"lol_short_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    # Smart titles: generuj hook_text przed renderem
    hook_text = ""
    smart_meta = None
    if SMART_TITLES_OK:
        try:
            # Buduj kontekst akcji — Gemini dostaje REALNE dane o tym jak przebiegła akcja
            _peaks = analysis.get("peaks") or []
            _kill_labels = [lbl for (_, lbl) in _peaks] if _peaks else []
            _kill_times  = [t for (t, _) in _peaks] if _peaks else []
            _clip_dur    = analysis.get("clip_duration") or analysis.get("peak_end", 0) - analysis.get("peak_start", 0)
            # Czas pierwszego killa w meczu (wg nazwy pliku: HH-MM-SS → minuty gry)
            _fname = os.path.basename(source_clip)
            _game_time_hint = ""
            import re as _re
            _ts = _re.search(r'(\d{2})-(\d{2})-(\d{2})-', _fname)
            if _ts:
                _h, _m, _s = int(_ts.group(1)), int(_ts.group(2)), int(_ts.group(3))
                _total_min = _h * 60 + _m
                if _total_min < 15:
                    _game_time_hint = "early game (before 15 min)"
                elif _total_min < 25:
                    _game_time_hint = "mid game (15-25 min)"
                else:
                    _game_time_hint = "late game (25+ min)"

            kill_context = {
                "kill_count":    len(_peaks),
                "kill_sequence": _kill_labels,              # np. ["TRIPLE KILL"]
                "kill_timings":  [f"{t:.1f}s" for t in _kill_times],
                "clip_duration": f"{_clip_dur:.1f}s",
                "game_time":     _game_time_hint,
                # spread: czas między pierwszym a ostatnim killem
                "kill_spread":   f"{(_kill_times[-1]-_kill_times[0]):.1f}s between first and last kill" if len(_kill_times) > 1 else "instant",
            }
            smart_meta = generate_smart_title(
                action_type=analysis["action_type"],
                champion_name=champion,
                rank=rank,
                clip_path=source_clip,
                kill_context=kill_context,
            )
            hook_text = smart_meta.get("hook_text", "")
            log(f"   ✅ Smart hook (AI): '{hook_text}'")
        except Exception as e:
            log(f"   ⚠️  Smart titles error: {e}")

    # Hook override: dla akcji z JASNA ETYKIETA (kills) zawsze uzyj tej etykiety.
    # AI generuje kreatywne ale BLEDNE hooki np. 'FIVE KILLS INSTANT' zamiast 'PENTAKILL'.
    # Etykieta zabojstwa = to co widz OCZEKUJE zobaczyc w pierwszej sekundzie.
    _KILL_HOOKS = {
        "pentakill":  "PENTAKILL!",
        "quadrakill": "QUADRAKILL!",
        "triple":     "TRIPLE KILL!",
        "double":     "DOUBLE KILL!",
        "oneshot":    "ONE SHOT!",
        "baron":      "BARON STEAL!",
        "dragon":     "DRAGON STEAL!",
    }
    _forced_hook = _KILL_HOOKS.get(analysis["action_type"], "")
    if _forced_hook:
        hook_text = _forced_hook
        log(f"   🎯 Hook override (label): '{hook_text}'")

    # Wybierz peak moment: preferuj main_peak_in_clip z momentum analyzera
    peak_moment_in_clip = analysis.get("main_peak_in_clip",
                                       analysis.get("clip_duration", 0) * 0.65)

    # Override dla PENTAKILL / QUADRAKILL:
    _clip_dur = analysis["peak_end"] - analysis["peak_start"]
    if analysis["action_type"] in ("pentakill", "quadrakill") and _clip_dur > 8.0:
        peaks_list = analysis.get("peaks", [])
        if peaks_list:
            last_k_time = peaks_list[-1][0] - analysis["peak_start"]
            if 0 < last_k_time < _clip_dur:
                peak_moment_in_clip = last_k_time
        else:
            penta_peak = _clip_dur - 2.5
            if penta_peak > peak_moment_in_clip:
                peak_moment_in_clip = penta_peak
        log(f"   🎯 Peak moment ({analysis['action_type']}): {peak_moment_in_clip:.1f}s")
        if clip_end_override is None:
            after_k_sec = 3.8 if analysis["action_type"] in ("pentakill", "quadrakill") else 2.0
            new_end = min(analysis["peak_end"], analysis["peak_start"] + peak_moment_in_clip + after_k_sec)
            if new_end < analysis["peak_end"] - 0.5:
                log(f"   ✂️  Clip end trimmed: {analysis['peak_end']:.1f}s → {new_end:.1f}s "
                    f"(+{after_k_sec}s po peak {peak_moment_in_clip:.1f}s)")
                analysis["peak_end"] = new_end
                analysis["clip_duration"] = new_end - analysis["peak_start"]
    peak_moment_in_clip = max(2.0, min(peak_moment_in_clip,
                                       analysis["peak_end"] - analysis["peak_start"] - 0.5))

    # ── Oblicz segmenty walki (jump-cut gaps) ────────────────────────────────
    combat_segs = None
    if segments_override:
        combat_segs = segments_override
        log(f"   ✂️  Segmenty ręczne (CLI): {[(f'{s:.1f}', f'{e:.1f}') for s, e in combat_segs]}")
    elif COMBAT_SEG_OK:
        # Skanuj w granicach wyznaczonego okna aktywności z momentum_analyzer (lub override z CLI)
        scan_s = clip_start_override if clip_start_override is not None else analysis.get("peak_start", 0.0)
        scan_e = clip_end_override if clip_end_override is not None else analysis.get("peak_end", None)
        combat_segs = find_combat_segments(
            peaks=analysis.get("peaks", []),
            curve=analysis.get("momentum_curve", []),
            clip_start=scan_s,
            clip_end=scan_e,
            activity_threshold=35.0,
            pre_roll=2.5,
            post_roll=1.2,
            merge_gap=3.5,
            min_segment_dur=2.5,
            max_total_duration=17.0,  # FIX: 26.0→17.0 — raw ~17s po slow-mo/efektach daje ~15s final (15s SNAP obsługuje do 22s)
        )
        if len(combat_segs) == 1:
            seg_s, seg_e = combat_segs[0]
            log(f"   📋 Combat segment: 1 okno ciągłe ({seg_s:.1f}s → {seg_e:.1f}s)")
            analysis["peak_start"] = seg_s
            analysis["peak_end"]   = seg_e
            analysis["clip_duration"] = seg_e - seg_s
            combat_segs = None
        else:
            log(f"   ✂️  Combat segments: {len(combat_segs)}x jump-cut aktywny ({sum(e-s for s, e in combat_segs):.1f}s total)")

    # ── Oblicz docelowy peak_moment dla beat-sync / slowmo ───────────────────
    final_peaks = analysis.get("peaks", [])
    if peaks_override:
        final_peaks = peaks_override
        log(f"   💀 Kill peaks override (CLI): {peaks_override}")
        labels = [lbl.upper() for _, lbl in peaks_override]
        if any("PENTAKILL" in l for l in labels):
            analysis["action_type"] = "pentakill"
            log("   🎮 Action type → pentakill (z peaks override)")
        elif any("QUADRA" in l for l in labels):
            analysis["action_type"] = "quadrakill"

    if peak_override is not None:
        target_climax_t = peak_override
    elif final_peaks:
        # Climax = ostatni zabójczy cios w sekwencji
        target_climax_t = final_peaks[-1][0]
    else:
        target_climax_t = analysis.get("main_peak_in_clip", 0.0) + analysis.get("peak_start", 0.0)

    if combat_segs:
        cursor = 0.0
        matched = False
        for seg_s, seg_e in combat_segs:
            if seg_s <= target_climax_t <= seg_e:
                peak_moment_in_clip = cursor + (target_climax_t - seg_s)
                matched = True
                break
            cursor += (seg_e - seg_s)
        if not matched:
            total_dur = sum(e - s for s, e in combat_segs)
            peak_moment_in_clip = total_dur * 0.70
    else:
        peak_moment_in_clip = max(0.0, target_climax_t - analysis.get("peak_start", 0.0))

    log(f"   🎯 Zsynchronizowany Climax @ {peak_moment_in_clip:.1f}s (oryg: {target_climax_t:.1f}s)")

    final_video = render_short(
        source_path=source_clip,
        clip_start=analysis["peak_start"],
        clip_end=analysis["peak_end"],
        action_type=analysis["action_type"],
        champion_name=champion,
        rank=rank,
        use_speed_ramp=not no_slowmo,
        peak_moment=peak_moment_in_clip,
        hook_text=hook_text,
        peaks=final_peaks,
        output_filename=output_name,
        preferred_track=preferred_music,
        combat_segments=combat_segs,
    )



    # === Miniaturka 9:16 w stylu kanalu ===
    thumbnail_path = None
    if THUMBNAIL_OK:
        try:
            thumb_name = output_name.replace(".mp4", "_thumb.jpg")
            thumb_out = os.path.join(LOL_TEMP_DIR, thumb_name)

            # Etykieta: typ akcji (PENTAKILL, TRIPLE KILL itp) - czysty, bez hook sloganow
            action_label = analysis["action_type"].upper().replace("_", " ")

            # Klatka: +1.5s po ostatnim killu → baner "TRIPLE KILL" / "PENTAKILL" zawsze widoczny
            # Kill feed trzyma się ~2s na ekranie, +1.5s zawsze go złapie
            peaks_list = analysis.get("peaks", [])
            if peaks_list:
                last_peak_abs_t = peaks_list[-1][0]           # absolutny czas w source clip
                last_peak_in_clip = last_peak_abs_t - analysis["peak_start"]
                thumb_time = min(last_peak_in_clip + 1.5, analysis.get("clip_duration", 10) - 0.3)
                source_thumb_t = last_peak_abs_t + 1.5        # +1.5s po killu w oryginale
            else:
                thumb_time = min(peak_moment_in_clip + 1.0, analysis.get("clip_duration", 10) - 0.3)
                source_thumb_t = analysis["peak_start"] + max(0.5, thumb_time)

            thumbnail_path = generate_thumbnail(
                video_path=final_video,
                peak_moment=max(0.5, thumb_time),
                action_label=action_label,
                champion_name=champion,
                output_path=thumb_out,
                source_clip_path=source_clip,
                source_peak_moment=source_thumb_t,  # absolutny czas w oryginalnym klipie
            )
            # Copy to permanent thumbnails directory so it survives cleanup_temp
            if thumbnail_path and os.path.exists(thumbnail_path):
                perm_thumb_dir = os.path.join(os.path.dirname(__file__), "thumbnails")
                os.makedirs(perm_thumb_dir, exist_ok=True)
                perm_thumb_path = os.path.join(perm_thumb_dir, thumb_name)
                shutil.copy2(thumbnail_path, perm_thumb_path)
                thumbnail_path = perm_thumb_path
                log(f"   🖼️  Miniaturka zapisana trwale: {thumbnail_path}")
        except Exception as e:
            log(f"   ⚠️  Thumbnail error: {e}")

    # === ETAP 4: Metadane ===
    log(f"\n[ETAP 4/5] Generowanie metadanych...")
    if smart_meta and smart_meta.get("title"):
        metadata = smart_meta
        log(f"   📑 Smart title: {metadata['title']}")
        log(f"   💡 {metadata.get('why_this_title', '')}")
    else:
        metadata = generate_metadata(
            action_type=analysis["action_type"],
            champion_name=champion or metadata_champion_guess(source_clip),
            rank=rank,
        )

    if custom_title:
        metadata["title"] = custom_title
        log(f"   🎯 Tytuł wymuszony (custom): {custom_title}")

    log(f"   📑 Tytuł: {metadata['title']}")

    if dry_run:
        log(f"\n🔍 DRY RUN — Pominieto upload.")
        log(f"   📹 Gotowy plik: {final_video}")
        if thumbnail_path:
            log(f"   🖼️  Miniaturka: {thumbnail_path}")
        log(f"   📑 Tytul: {metadata['title']}")
        log(f"   🏷️  Tagi: {', '.join(metadata.get('tags', [])[:8])}...")
        if hook_text:
            log(f"   🖥️  Overlay: {hook_text}")
        if medal_meta.get('title'):
            log(f"   🏅 Medal: {medal_meta['title']}")

        # Zapisz wyniki dry run
        # Zapisz wyniki dry run (bez momentum_curve — za duży do JSON)
        serializable_analysis = {
            k: v for k, v in analysis.items()
            if k not in ("video_path", "momentum_curve")
        }
        # Peaks to list of tuples — konwertuj na list of lists dla JSON
        if "peaks" in serializable_analysis:
            serializable_analysis["peaks"] = [
                [t, label] for t, label in serializable_analysis["peaks"]
            ]
        dry_run_report = {
            "timestamp": datetime.now().isoformat(),
            "source_clip": source_clip,
            "output_file": final_video,
            "metadata": metadata,
            "analysis": serializable_analysis,
            "medal_metadata": medal_meta,
        }
        report_path = os.path.join(os.path.dirname(__file__), "last_dry_run.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(dry_run_report, f, ensure_ascii=False, indent=2)
        log(f"   Report: {report_path}")
        # NOTE: nie czyścimy lol_temp na dry-run — QA skrypt potrzebuje output pliku
        return final_video

    # === Quality gate: score montage before uploading ===
    quality_result = None
    if QUALITY_SCORER_OK:
        from lol_editor import MUSIC_DROP_MAP
        music_fname = os.path.basename(getattr(render_short, '_last_music', '') or '')
        # Find which music was used by checking lol_temp for audio files
        import glob as _glob
        used_music = ""
        for mf in _glob.glob(os.path.join(os.path.dirname(__file__), "lol_music", "*.mp3")):
            if os.path.basename(mf) in str(final_video):
                used_music = mf
                break

        beat_drop_used = MUSIC_DROP_MAP.get(os.path.basename(used_music), 30.0)
        quality_result = score_short(
            rendered_path=final_video,
            source_path=source_clip,
            analysis=analysis,
            beat_drop_time=beat_drop_used,
            music_file=os.path.basename(used_music),
        )
        save_quality_log(quality_result)

        if not quality_result["pass"]:
            log(f"Quality score {quality_result['score']:.0f}/100 below threshold {QUALITY_THRESHOLD}")
            log(f"   Issues: {'; '.join(quality_result['issues'][:2])}")
            if quality_result.get("recommendation"):
                log(f"   Suggestion: {quality_result['recommendation']}")
            log("   Proceeding with upload anyway (score gate is advisory)")
        else:
            log(f"Quality gate PASSED: {quality_result['score']:.0f}/100")

    # Upload
    log("\n🚀 Publishing to YouTube... [ETAP 5/5]")
    youtube = get_lol_youtube_service()
    result = upload_lol_short(
        video_path=final_video,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
        privacy=privacy,
        thumbnail_path=thumbnail_path,
        publish_at=schedule if schedule else None,
    )

    if schedule:
        log(f"\n🎉 SUKCES! Short ZAPLANOWANY do publikacji!")
    else:
        log(f"\n🎉 SUKCES! Short opublikowany!")
    log(f"   🔗 {result['url']}")

    # Przypiety komentarz (engagement signal dla algorytmu)
    pinned_comment = (
        f"Which champion should I play next? 👇\n"
        f"Like if you want more {champion or 'Katarina'} clips! 🔥"
    )
    post_pinned_comment(youtube, result["video_id"], pinned_comment)

    # Zapis do logu publikacji
    pub_log = {
        "timestamp": datetime.now().isoformat(),
        "video_id": result["video_id"],
        "url": result["url"],
        "title": result["title"],
        "action_type": analysis["action_type"],
        "champion": champion,
        "thumbnail": thumbnail_path,
        "scheduled_publish_at": schedule if schedule else None,
    }
    pub_log_path = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
    with open(pub_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")

    # Save clip hash & stem so same clip is never uploaded twice
    try:
        processed_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
        processed = {}
        if os.path.exists(processed_path):
            with open(processed_path, encoding="utf-8") as f:
                processed = json.load(f)

        orig_name = os.path.basename(original_source_file or source_clip)
        stem = _extract_clip_stem(orig_name)
        save_entry = {
            "date": datetime.now().isoformat(),
            "url": result["url"],
            "title": result["title"],
            "source": orig_name,
            "stem": stem,
            "action_fingerprint": analysis.get("action_fingerprint", {}),
        }

        # Zapisz pod hashem wyrenderowanego/scalonego pliku
        clip_hash = _clip_hash(source_clip)
        processed[clip_hash] = save_entry

        # Zapisz takze pod hashem oryginalnego pliku (np. _0.mp4)
        if original_source_file and os.path.exists(original_source_file) and original_source_file != source_clip:
            try:
                orig_hash = _clip_hash(original_source_file)
                processed[orig_hash] = save_entry
            except Exception:
                pass

        with open(processed_path, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        log("   🔒 Zapisano sygnatury duplikatow (Hash + Nazwa + Stem + OCR Fingerprint)")
    except Exception as e:
        log(f"   ⚠️  Could not save clip hash: {e}")

    # Schedule 48h performance check
    if PERF_TRACKER_OK:
        schedule_check(
            video_id=result["video_id"],
            video_url=result["url"],
            title=metadata["title"],
            action_type=analysis["action_type"],
            champion=champion or "",
            quality_score=quality_result["score"] if quality_result else 0,
            music_file=os.path.basename(used_music) if 'used_music' in dir() else "",
            beat_sync_error=quality_result["beat_sync_error_seconds"] if quality_result else 0,
            kill_coverage_pct=quality_result["kill_coverage_pct"] if quality_result else 0,
        )

    cleanup_temp()
    return result


def metadata_champion_guess(video_path: str) -> str:
    """Próbuje odgadnąć championa z nazwy pliku."""
    filename = os.path.basename(video_path).lower()
    champions = [
        "jinx", "yasuo", "zed", "ahri", "lee sin", "thresh", "vayne",
        "master yi", "katarina", "lux", "yone", "viego", "akali",
        "ezreal", "caitlyn", "sylas", "fizz", "rengar"
    ]
    for champ in champions:
        if champ.replace(" ", "").lower() in filename.replace(" ", "").lower():
            return champ.title()
    return ""


def _clip_hash(video_path: str) -> str:
    """MD5 hash of first 2MB of clip — fast deduplication check."""
    h = hashlib.md5()
    with open(video_path, "rb") as f:
        h.update(f.read(2 * 1024 * 1024))
    return h.hexdigest()


def _extract_clip_stem(filename: str) -> str:
    """Ekstrahuje bazowy rdzen nazwy pliku (usuwajac _0, _1, trim, rozszerzenia)."""
    if not filename:
        return ""
    clean = os.path.basename(filename)
    clean = os.path.splitext(clean)[0]
    if clean.startswith("merged_"):
        clean = clean[7:]
    clean = re.sub(r'_\d+$', '', clean)
    clean = re.sub(r'-trim-\d+$', '', clean)
    return clean.strip()


def check_duplicate_clip(source_path: str, original_path: str = None) -> tuple:
    """
    Sprawdza, czy klip byl juz opublikowany na YouTube (Wielowarstwowa ochrona przed duplikatami):
    1. MD5 Hash (pliku zrodlowego oraz czesci _0.mp4)
    2. Nazwa pliku i bazowy rdzen (stem)
    3. Wpis w published_videos.jsonl

    Zwraca: (is_duplicate: bool, reason: str, dup_info: dict)
    """
    processed_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
    pub_path = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")

    hashes_to_check = set()
    stems_to_check = set()
    filenames_to_check = set()

    for p in [source_path, original_path]:
        if not p:
            continue
        fname = os.path.basename(p)
        if fname:
            filenames_to_check.add(fname.lower())
            stem = _extract_clip_stem(fname).lower()
            if stem:
                stems_to_check.add(stem)
        if os.path.exists(p):
            try:
                hashes_to_check.add(_clip_hash(p))
            except Exception:
                pass

    # 1. Sprawdz processed_hashes.json
    if os.path.exists(processed_path):
        try:
            with open(processed_path, "r", encoding="utf-8") as f:
                processed = json.load(f)
            for h in hashes_to_check:
                if h in processed:
                    return True, f"MD5 Hash Match ({h[:8]}...)", processed[h]

            for entry_hash, entry in processed.items():
                entry_src = entry.get("source", "").lower()
                entry_stem = entry.get("stem", "").lower() or _extract_clip_stem(entry_src).lower()
                if entry_src and entry_src in filenames_to_check:
                    return True, f"Identyczna nazwa pliku ({entry.get('source')})", entry
                if entry_stem and entry_stem in stems_to_check and len(entry_stem) >= 6:
                    return True, f"Ten sam mecz / rdzeń nagrania ({entry.get('source', entry_stem)})", entry
        except Exception as e:
            log(f"   ⚠️  Blad odczytu processed_hashes.json: {e}")

    # 2. Sprawdz published_videos.jsonl
    if os.path.exists(pub_path):
        try:
            with open(pub_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line.strip())
                    thumb = item.get("thumbnail", "").lower()
                    title = item.get("title", "").lower()
                    for stem in stems_to_check:
                        if stem and len(stem) >= 8 and (stem in thumb or stem in title):
                            return True, f"Wpis w historii publikacji ({item.get('title')})", item
        except Exception:
            pass

    return False, "", {}


def _compute_action_fingerprint(peaks: list, champion: str, action_type: str) -> dict:
    """
    Computes a semantic game action fingerprint based on relative kill timings and labels.
    Invariant to clip start/end trimming.
    """
    if not peaks:
        return {
            "champion": champion.lower() if champion else "",
            "action_type": action_type.lower() if action_type else "",
            "kills": []
        }

    first_t = float(peaks[0][0])
    kills = [
        {"label": str(label).upper(), "rel_t": round(float(t) - first_t, 1)}
        for t, label in peaks
    ]
    return {
        "champion": champion.lower() if champion else "",
        "action_type": action_type.lower() if action_type else "",
        "kills": kills
    }


def _is_duplicate_action(current_fp: dict, processed_data: dict, tolerance: float = 0.8) -> tuple:
    """
    Checks if current game action matches any previously processed/uploaded action.
    Returns (is_duplicate: bool, matched_entry: dict).
    """
    cur_kills = current_fp.get("kills", [])
    if not cur_kills or len(cur_kills) < 2:
        return False, {}

    cur_champ = current_fp.get("champion", "").lower()
    cur_action = current_fp.get("action_type", "").lower()

    for clip_key, entry in processed_data.items():
        entry_fp = entry.get("action_fingerprint")
        if not entry_fp:
            continue

        ent_kills = entry_fp.get("kills", [])
        if len(ent_kills) != len(cur_kills):
            continue

        ent_champ = entry_fp.get("champion", "").lower()
        if cur_champ and ent_champ and cur_champ != ent_champ:
            continue

        matched = True
        for (k_cur, k_ent) in zip(cur_kills, ent_kills):
            if k_cur["label"] != k_ent["label"]:
                matched = False
                break
            if abs(k_cur["rel_t"] - k_ent["rel_t"]) > tolerance:
                matched = False
                break

        if matched:
            return True, entry

    return False, {}


def cleanup_temp():
    """Remove temp files after pipeline completes."""
    if os.path.exists(LOL_TEMP_DIR):
        shutil.rmtree(LOL_TEMP_DIR, ignore_errors=True)
        log(f"Cleaned temp: {LOL_TEMP_DIR}")


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🎮  LOL AGENT  —  Dwannellenga          ║
║     League of Legends Shorts Automation Bot      ║
╚══════════════════════════════════════════════════╝
""")


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description="LOL Agent — Automatyczny pipeline YouTube Shorts dla League of Legends"
    )
    parser.add_argument("--file", "-f", type=str, help="Ścieżka do surowego klipu (mp4/mkv/mov)")
    parser.add_argument("--champion", "-c", type=str, default="", help="Nazwa championa (np. Jinx)")
    parser.add_argument("--rank", "-r", type=str, default="", help="Ranga (np. Diamond)")
    parser.add_argument("--authorize", "-a", action="store_true", help="Tylko autoryzacja kanału YT")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Montaż bez uploadu na YT")
    parser.add_argument("--no-slowmo", action="store_true", help="Wyłącz slow-motion")
    parser.add_argument("--cleanup", action="store_true", help="Tylko cleanup folderów temp")
    parser.add_argument("--force",   action="store_true", help="Pomijaj dedup — przetwarzaj nawet już wgrany klip")
    parser.add_argument("--action",  type=str, default="",  help="Wymus typ akcji (np. pentakill, doublekill, outplay)")
    parser.add_argument("--privacy", type=str, default=YT_PRIVACY, help="Status prywatnosci YT (public, private, unlisted)")
    parser.add_argument("--start",   type=float, default=None, help="Ręczny start klipu w sekundach (override auto-trim)")
    parser.add_argument("--end",     type=float, default=None, help="Ręczny koniec klipu w sekundach (override auto-trim)")
    parser.add_argument("--music",   type=str, default="", help="Wymuszenie konkretnej ścieżki dźwiękowej (np. ncs_lost_sky_dreams_pt2.mp3)")
    parser.add_argument("--title",   type=str, default="", help="Ręczny tytuł filmu (override)")
    parser.add_argument("--schedule", type=str, default="", help="Zaplanuj publikację na godzinę (np. '18:00', '08:30', 'morning', 'evening' lub ISO string)")
    parser.add_argument("--segments", type=str, default="", help="Ręczne segmenty jump-cut (JSON) np. '[[18,30],[39.5,53]]'")
    parser.add_argument("--peak",     type=float, default=None, help="Ręczny peak_moment w sekundach oryginalnego klipu (override slowmo)")
    parser.add_argument("--peaks",    type=str, default="", help="Ręczne kill peaks JSON np. '[[42.0,\"PENTAKILL\"]]'")


    args = parser.parse_args()

    if args.authorize:
        authorize_only()
        return

    if args.cleanup:
        cleanup_temp()
        return

    import json as _json
    _segments_override = None
    if args.segments:
        try:
            _raw = _json.loads(args.segments)
            _segments_override = [(float(s), float(e)) for s, e in _raw]
        except Exception as _e:
            print(f"⚠️  Nieprawidłowy format --segments (oczekiwano JSON np. '[[18,30],[39.5,53]]'): {_e}")

    _peaks_override = None
    if args.peaks:
        try:
            _raw_peaks = _json.loads(args.peaks)
            _peaks_override = [(float(t), str(lbl)) for t, lbl in _raw_peaks]
        except Exception as _e:
            print(f"⚠️  Nieprawidłowy format --peaks (oczekiwano JSON np. '[[42.0,\"PENTAKILL\"]]'): {_e}")

    run_pipeline(
        video_path=args.file,
        champion=args.champion,
        rank=args.rank,
        action=args.action,
        dry_run=args.dry_run,
        no_slowmo=args.no_slowmo,
        force=args.force,
        privacy=args.privacy,
        clip_start_override=args.start,
        clip_end_override=args.end,
        preferred_music=args.music,
        custom_title=args.title,
        schedule=args.schedule,
        segments_override=_segments_override,
        peak_override=args.peak,
        peaks_override=_peaks_override,
    )




if __name__ == "__main__":
    main()
