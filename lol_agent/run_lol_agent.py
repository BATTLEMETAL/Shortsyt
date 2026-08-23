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

    # === Deduplication: skip if this clip was already processed ===
    if not dry_run:
        clip_hash = _clip_hash(source_clip)
        processed_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
        processed = {}
        if os.path.exists(processed_path):
            with open(processed_path, encoding="utf-8") as f:
                processed = json.load(f)
        if clip_hash in processed:
            log(f"SKIP Duplicate detected: this clip was already uploaded on {processed[clip_hash]['date']}")
            log(f"   Video: {processed[clip_hash].get('url', '?')}")
            log("   Use --force to override.")
            if not force:
                return


    # === ETAP 2: Analiza klipu ===
    log(f"\n[ETAP 2/5] Analiza klipu: {os.path.basename(source_clip)}")
    analysis = analyze_clip(source_clip, champion=champion)
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
            smart_meta = generate_smart_title(
                action_type=analysis["action_type"],
                champion_name=champion,
                rank=rank,
                clip_path=source_clip
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
        peaks=analysis.get("peaks", []),
        output_filename=output_name,
        preferred_track=preferred_music,
    )

    # === Miniaturka 9:16 w stylu kanalu ===
    thumbnail_path = None
    if THUMBNAIL_OK:
        try:
            thumb_name = output_name.replace(".mp4", "_thumb.jpg")
            thumb_out = os.path.join(LOL_TEMP_DIR, thumb_name)

            # Etykieta: typ akcji (PENTAKILL, TRIPLE KILL itp) - czysty, bez hook sloganow
            action_label = analysis["action_type"].upper().replace("_", " ")

            # Klatka: ostatni kill peak (najwyzszy kill - np. PENTAKILL, nie QUADRAKILL)
            # Fallback na peak_moment_in_clip jesli brak peaks
            peaks_list = analysis.get("peaks", [])
            if peaks_list:
                # Ostatni peak = najwyzszy kill (Penta > Quadra > Triple)
                last_peak_time = peaks_list[-1][0] - analysis["peak_start"]
                thumb_time = min(last_peak_time, analysis.get("clip_duration", 10) - 0.5)
            else:
                thumb_time = min(peak_moment_in_clip, analysis.get("clip_duration", 10) - 0.5)

            # Czas absolutny w source clip (peak_start + offset w klipie)
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
    )

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
    }
    pub_log_path = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
    with open(pub_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")

    # Save clip hash so same clip is never uploaded twice
    try:
        clip_hash = _clip_hash(source_clip)
        processed_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
        processed = {}
        if os.path.exists(processed_path):
            with open(processed_path, encoding="utf-8") as f:
                processed = json.load(f)
        processed[clip_hash] = {
            "date": datetime.now().isoformat(),
            "url": result["url"],
            "title": result["title"],
            "source": os.path.basename(source_clip),
            "action_fingerprint": analysis.get("action_fingerprint", {}),
        }
        with open(processed_path, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
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

    args = parser.parse_args()

    if args.authorize:
        authorize_only()
        return

    if args.cleanup:
        cleanup_temp()
        return

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
    )


if __name__ == "__main__":
    main()
