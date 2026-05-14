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
import argparse
import shutil
import json
from datetime import datetime

# Dodaj ścieżkę projektu
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from lol_config import LOL_TEMP_DIR, LOL_ARCHIVE_DIR
from lol_clip_analyzer import scan_input_folder, analyze_clip, archive_clip
from lol_editor import render_short
from lol_metadata_generator import generate_metadata
from lol_publisher import get_lol_youtube_service, upload_lol_short


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
    dry_run: bool = False,
    no_slowmo: bool = False,
):
    """Uruchamia pełny pipeline LOL."""
    log("="*60)
    log("🚀 LOL AGENT PIPELINE START")
    log("="*60)

    # === ETAP 1: Znajdź klip ===
    log("\n[ETAP 1/4] Wyszukiwanie klipu...")

    if video_path:
        if not os.path.exists(video_path):
            log(f"❌ Plik nie istnieje: {video_path}")
            return
        source_clip = video_path
        log(f"📹 Użyję podanego pliku: {os.path.basename(source_clip)}")
    else:
        source_clip = scan_input_folder()
        if not source_clip:
            log("⏸️  Brak klipów w folderze input. Wrzuć plik do:")
            log(f"   {os.path.dirname(__file__)}")
            log("   C:\\Users\\mz100\\OneDrive\\Pulpit\\yt\\filmy\\")
            return

    # === ETAP 2: Analiza klipu ===
    log(f"\n[ETAP 2/4] Analiza klipu: {os.path.basename(source_clip)}")
    analysis = analyze_clip(source_clip)

    log(f"   🎯 Akcja: {analysis['action_type'].upper()}")
    log(f"   ⏱️  Okno: {analysis['peak_start']:.1f}s → {analysis['peak_end']:.1f}s")

    # === ETAP 3: Montaż ===
    log(f"\n[ETAP 3/4] Montaż Shorta...")
    output_name = f"lol_short_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"

    final_video = render_short(
        source_path=source_clip,
        clip_start=analysis["peak_start"],
        clip_end=analysis["peak_end"],
        action_type=analysis["action_type"],
        champion_name=champion,
        rank=rank,
        use_slowmo=not no_slowmo,
        output_filename=output_name,
    )

    # === ETAP 4: Metadane + Publikacja ===
    log(f"\n[ETAP 4/4] Generowanie metadanych...")
    metadata = generate_metadata(
        action_type=analysis["action_type"],
        champion_name=champion or metadata_champion_guess(source_clip),
        rank=rank,
    )

    log(f"   📌 Tytuł: {metadata['title']}")

    if dry_run:
        log(f"\n🔍 DRY RUN — Pominięto upload.")
        log(f"   📹 Gotowy plik: {final_video}")
        log(f"   📌 Tytuł: {metadata['title']}")
        log(f"   🏷️  Tagi: {', '.join(metadata['tags'][:8])}...")

        # Zapisz wyniki dry run
        dry_run_report = {
            "timestamp": datetime.now().isoformat(),
            "source_clip": source_clip,
            "output_file": final_video,
            "metadata": metadata,
            "analysis": {k: v for k, v in analysis.items() if k != "video_path"},
        }
        report_path = os.path.join(os.path.dirname(__file__), "last_dry_run.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(dry_run_report, f, ensure_ascii=False, indent=2)
        log(f"   📊 Raport: {report_path}")
        return final_video

    # Upload
    log("\n🚀 Publikacja na YouTube...")
    result = upload_lol_short(
        video_path=final_video,
        title=metadata["title"],
        description=metadata["description"],
        tags=metadata["tags"],
    )

    log(f"\n🎉 SUKCES! Short opublikowany!")
    log(f"   🔗 {result['url']}")

    # Archiwizacja źródłowego klipu
    if not video_path or video_path != source_clip:
        archive_clip(source_clip)

    # Cleanup temp
    cleanup_temp()

    # Zapis do logu publikacji
    pub_log = {
        "timestamp": datetime.now().isoformat(),
        "video_id": result["video_id"],
        "url": result["url"],
        "title": result["title"],
        "action_type": analysis["action_type"],
        "champion": champion,
    }
    pub_log_path = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")
    with open(pub_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pub_log, ensure_ascii=False) + "\n")

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


def cleanup_temp():
    """Usuwa pliki tymczasowe po zakończeniu pipeline."""
    if os.path.exists(LOL_TEMP_DIR):
        shutil.rmtree(LOL_TEMP_DIR, ignore_errors=True)
        log(f"🧹 Wyczyszczono temp: {LOL_TEMP_DIR}")


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
        dry_run=args.dry_run,
        no_slowmo=args.no_slowmo,
    )


if __name__ == "__main__":
    main()
