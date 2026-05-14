"""
LOL Agent -- Downloader muzyki royalty-free dla gamingu
Pobiera tracki z YouTube (NCS, Epidemic Sound free, gaming music)
"""
import os
import subprocess
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "lol_music")

# Lista URL do pobrania — NCS i royalty-free gaming tracks
# Wszystkie legalne do użycia w monetyzowanych filmach YT
TRACKS = [
    # NCS Gaming Tracks
    {
        "url": "https://www.youtube.com/watch?v=wjLExdRVz0k",
        "name": "ncs_alan_walker_faded",
    },
    {
        "url": "https://www.youtube.com/watch?v=TW9d8vYrVFQ",
        "name": "ncs_cartoon_on_and_on",
    },
    {
        "url": "https://www.youtube.com/watch?v=K4DyBUG242c",
        "name": "ncs_elektronomia_sky_high",
    },
    {
        "url": "https://www.youtube.com/watch?v=9Kw4VeEu9GU",
        "name": "ncs_lensko_circles",
    },
    {
        "url": "https://www.youtube.com/watch?v=yJg-Y5byMMw",
        "name": "ncs_distrion_alex_skrindo_entropy",
    },
    {
        "url": "https://www.youtube.com/watch?v=tgFIuDngrFI",
        "name": "ncs_heroes_tonight",
    },
    {
        "url": "https://www.youtube.com/watch?v=Klif7v3NQYM",
        "name": "ncs_aero_chord_surfboard",
    },
    {
        "url": "https://www.youtube.com/watch?v=ep8T_Gnn7Os",
        "name": "ncs_syn_cole_feel_good",
    },
    # Gaming / Epic Battle
    {
        "url": "https://www.youtube.com/watch?v=ZOPq0bIRqJE",
        "name": "ncs_unknown_brain_superhero",
    },
    {
        "url": "https://www.youtube.com/watch?v=VoQ5OPAYDII",
        "name": "ncs_different_heaven_nekozilla",
    },
]


def get_ytdlp_cmd() -> list:
    """Zwraca komendę yt-dlp jako listę argumentów."""
    # Priorytet 1: moduł Python w tym samym venv (niezawodny na Windows)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        pass

    # Priorytet 2: yt-dlp w PATH
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            return ["yt-dlp"]
    except FileNotFoundError:
        pass

    return None


def check_ytdlp() -> bool:
    """Sprawdza czy yt-dlp jest dostępny."""
    return get_ytdlp_cmd() is not None


def download_track(url: str, name: str, music_dir: str) -> bool:
    """Pobiera jeden utwór z YouTube jako mp3."""
    output_template = os.path.join(music_dir, f"{name}.%(ext)s")
    final_path = os.path.join(music_dir, f"{name}.mp3")

    if os.path.exists(final_path):
        print(f"   Juz istnieje: {name}.mp3 -- pominięto")
        return True

    print(f"   Pobieranie: {name}...")

    ytdlp_base = get_ytdlp_cmd()
    if not ytdlp_base:
        print("   Blad: yt-dlp niedostepny")
        return False

    cmd = ytdlp_base + [
        "-x", "--audio-format", "mp3",
        "--audio-quality", "192K",
        "-o", output_template,
        url
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode == 0 and os.path.exists(final_path):
        size = os.path.getsize(final_path) / 1024 / 1024
        print(f"   OK: {name}.mp3 ({size:.1f} MB)")
        return True
    else:
        err = result.stderr[:300] if result.stderr else "unknown error"
        print(f"   Blad: {err}")
        return False


def download_all_music():
    """Pobiera wszystkie tracki do folderu lol_music/."""
    os.makedirs(MUSIC_DIR, exist_ok=True)

    print("\n=== LOL MUSIC DOWNLOADER ===")
    print("    Royalty-Free Gaming Tracks (NCS)")
    print(f"\nFolder docelowy: {MUSIC_DIR}")
    print(f"Trackow do pobrania: {len(TRACKS)}\n")

    if not check_ytdlp():
        print("❌ yt-dlp nie jest zainstalowany!")
        print("   Zainstaluj: pip install yt-dlp")
        print("   Lub pobierz: https://github.com/yt-dlp/yt-dlp/releases")
        return False

    success = 0
    failed = 0

    for i, track in enumerate(TRACKS, 1):
        print(f"\n[{i}/{len(TRACKS)}] {track['name']}")
        if download_track(track["url"], track["name"], MUSIC_DIR):
            success += 1
        else:
            failed += 1

    print(f"""
{'='*50}
✅ Pobrano:  {success} tracków
❌ Błędy:    {failed} tracków
📂 Folder:   {MUSIC_DIR}
{'='*50}
""")

    if success > 0:
        print("🎮 Muzyka gotowa! Agent LoL może teraz nakładać muzykę automatycznie.")
        return True
    return False


if __name__ == "__main__":
    download_all_music()
