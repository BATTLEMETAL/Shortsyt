"""
LOL Agent — Music Downloader
Automatically selects and downloads the right royalty-free music
for each action type from NCS (NoCopyrightSounds).

Usage:
    python lol_music_downloader.py                     # Download all missing tracks
    python lol_music_downloader.py --action pentakill  # Download best track for pentakill
    python lol_music_downloader.py --list              # List library + which are downloaded

All NCS tracks are free to use. Required attribution (added to description automatically):
  Track: [Title] by [Artist]
  Music provided by NoCopyrightSounds
  Watch: [URL]
  Download/Stream: [NCS URL]
"""
import os
import sys
import json
import argparse
import subprocess
import glob

# Windows cp1250 fix
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── Curated NCS music library ─────────────────────────────────────────────────
# energy: high / medium / low
# action_types: which LoL actions this track fits best
# drop_approx: estimated drop timestamp (librosa will auto-detect exact value)
# yt_url: official NCS YouTube upload

MUSIC_LIBRARY = {
    # ══ HIGH ENERGY — Pentakill, Quadrakill, Baron ══════════════════════════════
    "ncs_elektronomia_sky_high.mp3": {
        "title":        "Sky High",
        "artist":       "Elektronomia",
        "energy":       "high",
        "action_types": ["pentakill", "quadrakill", "baron"],
        "drop_approx":  30.0,
        "search_query": "NoCopyrightSounds Elektronomia Sky High",
        "ncs_url":      "https://ncs.io/SkyHigh",
        "attribution":  "Sky High by Elektronomia | https://soundcloud.com/elektronomia\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/SkyHigh",
    },
    "ncs_lost_sky_dreams_pt2.mp3": {
        "title":        "Dreams pt. II (feat. Sara Skinner)",
        "artist":       "Lost Sky",
        "energy":       "high",
        "action_types": ["pentakill", "quadrakill"],
        "drop_approx":  40.0,
        "search_query": "NoCopyrightSounds Lost Sky Dreams part II Sara Skinner",
        "ncs_url":      "https://ncs.io/DreamsII",
        "attribution":  "Dreams pt. II by Lost Sky ft Sara Skinner\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/DreamsII",
    },
    "ncs_robin_hustin_light_it_up.mp3": {
        "title":        "Light It Up (feat. Jex)",
        "artist":       "Robin Hustin x TobiMorrow",
        "energy":       "high",
        "action_types": ["pentakill", "baron", "dragon"],
        "drop_approx":  35.0,
        "search_query": "NoCopyrightSounds Robin Hustin TobiMorrow Light It Up Jex",
        "ncs_url":      "https://ncs.io/LightItUp",
        "attribution":  "Light It Up by Robin Hustin x TobiMorrow ft Jex\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/LightItUp",
    },
    "ncs_egzod_royalty.mp3": {
        "title":        "Royalty (feat. Neoni)",
        "artist":       "Egzod & Maestro Chives",
        "energy":       "high",
        "action_types": ["pentakill", "quadrakill", "baron"],
        "drop_approx":  45.0,
        "search_query": "NoCopyrightSounds Egzod Maestro Chives Royalty Neoni",
        "ncs_url":      "https://ncs.io/royalty",
        "attribution":  "Royalty by Egzod & Maestro Chives ft Neoni\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/royalty",
    },
    "ncs_elektronomia_immortality.mp3": {
        "title":        "Immortality",
        "artist":       "Elektronomia & RUD",
        "energy":       "high",
        "action_types": ["pentakill", "quadrakill"],
        "drop_approx":  32.0,
        "search_query": "NoCopyrightSounds Elektronomia RUD Immortality",
        "ncs_url":      "https://ncs.io/Immortality",
        "attribution":  "Immortality by Elektronomia & RUD\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/Immortality",
    },

    # ══ MEDIUM ENERGY — Triple Kill, Outplay, Clutch, Oneshot ═══════════════════
    "ncs_cartoon_on_and_on.mp3": {
        "title":        "On & On (feat. Daniel Levi)",
        "artist":       "Cartoon",
        "energy":       "medium",
        "action_types": ["triple", "outplay", "clutch"],
        "drop_approx":  38.0,
        "search_query": "NoCopyrightSounds Cartoon On and On Daniel Levi",
        "ncs_url":      "https://ncs.io/onandon",
        "attribution":  "On & On by Cartoon ft Daniel Levi\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/onandon",
    },
    "ncs_unknown_brain_superhero.mp3": {
        "title":        "Superhero (feat. Chris Linton)",
        "artist":       "Unknown Brain",
        "energy":       "medium",
        "action_types": ["triple", "outplay", "oneshot"],
        "drop_approx":  38.0,
        "search_query": "NoCopyrightSounds Unknown Brain Superhero Chris Linton",
        "ncs_url":      "https://ncs.io/superhero",
        "attribution":  "Superhero by Unknown Brain ft Chris Linton\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/superhero",
    },
    "ncs_different_heaven_my_heart.mp3": {
        "title":        "My Heart",
        "artist":       "Different Heaven & EH!DE",
        "energy":       "medium",
        "action_types": ["triple", "clutch", "outplay"],
        "drop_approx":  28.0,
        "search_query": "NoCopyrightSounds Different Heaven EHIDE My Heart",
        "ncs_url":      "https://ncs.io/MyHeart",
        "attribution":  "My Heart by Different Heaven & EH!DE\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/MyHeart",
    },
    "ncs_alex_skrindo_euphoria.mp3": {
        "title":        "Euphoria",
        "artist":       "Alex Skrindo",
        "energy":       "medium",
        "action_types": ["triple", "outplay", "oneshot"],
        "drop_approx":  36.0,
        "search_query": "NoCopyrightSounds Alex Skrindo Euphoria",
        "ncs_url":      "https://ncs.io/Euphoria",
        "attribution":  "Euphoria by Alex Skrindo\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/Euphoria",
    },

    # ══ LOW ENERGY — Escape, Double Kill, tense moments ══════════════════════════
    "ncs_jim_yosef_link.mp3": {
        "title":        "Link",
        "artist":       "Jim Yosef",
        "energy":       "low",
        "action_types": ["escape", "double"],
        "drop_approx":  30.0,
        "search_query": "NoCopyrightSounds Jim Yosef Link",
        "ncs_url":      "https://ncs.io/link",
        "attribution":  "Link by Jim Yosef\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/link",
    },
    "ncs_alan_walker_fade.mp3": {
        "title":        "Fade",
        "artist":       "Alan Walker",
        "energy":       "low",
        "action_types": ["escape", "double", "clutch"],
        "drop_approx":  42.0,
        "search_query": "NoCopyrightSounds Alan Walker Fade",
        "ncs_url":      "https://ncs.io/fade",
        "attribution":  "Fade by Alan Walker\nMusic provided by NoCopyrightSounds. Free Download/Stream: https://ncs.io/fade",
    },
}

MUSIC_DIR = os.path.join(os.path.dirname(__file__), "lol_music")
ATTRIBUTION_FILE = os.path.join(os.path.dirname(__file__), "music_attributions.json")


# ─── Download ──────────────────────────────────────────────────────────────────

def is_downloaded(filename: str) -> bool:
    return os.path.exists(os.path.join(MUSIC_DIR, filename))


def download_track(filename: str, track_info: dict) -> bool:
    """
    Download a single NCS track via yt-dlp YouTube search.
    Uses ytsearch1: so no hardcoded video IDs are needed.
    Converts to MP3 192kbps using ffmpeg.
    Returns True on success.
    """
    os.makedirs(MUSIC_DIR, exist_ok=True)
    output_path = os.path.join(MUSIC_DIR, filename)
    search_query = track_info.get("search_query", f"NoCopyrightSounds {track_info['artist']} {track_info['title']}")
    search_url   = f"ytsearch1:{search_query}"

    print(f"\n  Downloading: {track_info['artist']} — {track_info['title']}")
    print(f"  Searching : {search_query}")
    print(f"  Output    : {filename}")

    # yt-dlp: search YouTube, take first result, extract audio as MP3 192k
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "192K",
        "--output", output_path.replace(".mp3", ".%(ext)s"),
        "--no-playlist",
        "--progress",
        "--match-filter", "duration < 600",   # max 10 min — avoids mixes
        search_url,
    ]

    try:
        result = subprocess.run(cmd, timeout=180)

        # Check for successful output
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  OK: {filename} ({size_mb:.1f} MB)")
            _save_attribution(filename, track_info)
            _update_beat_cache(filename, track_info)
            return True

        # yt-dlp sometimes saves with temp extension first
        possible = [f for f in glob.glob(output_path.replace(".mp3", ".*"))
                    if not f.endswith(".part") and not f.endswith(".ytdl")]
        if possible:
            actual = possible[0]
            os.rename(actual, output_path)
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  OK (converted): {filename} ({size_mb:.1f} MB)")
            _save_attribution(filename, track_info)
            _update_beat_cache(filename, track_info)
            return True

        print(f"  FAILED: {filename} — yt-dlp exit code {result.returncode}")
        return False

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {filename} — took too long")
        return False
    except Exception as e:
        print(f"  ERROR: {filename} — {e}")
        return False


def _save_attribution(filename: str, track_info: dict):
    """Save attribution text so it can be added to video descriptions."""
    attrs = {}
    if os.path.exists(ATTRIBUTION_FILE):
        try:
            with open(ATTRIBUTION_FILE, encoding="utf-8") as f:
                attrs = json.load(f)
        except Exception:
            pass
    attrs[filename] = {
        "title":       track_info["title"],
        "artist":      track_info["artist"],
        "attribution": track_info.get("attribution", ""),
        "ncs_url":     track_info.get("ncs_url", ""),
        "energy":      track_info["energy"],
    }
    with open(ATTRIBUTION_FILE, "w", encoding="utf-8") as f:
        json.dump(attrs, f, ensure_ascii=False, indent=2)


def _update_beat_cache(filename: str, track_info: dict):
    """Pre-seed the beat drop cache with the approximate value."""
    cache_path = os.path.join(os.path.dirname(__file__), "beat_drop_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
    # Only add if not already in cache (librosa will overwrite with exact value)
    if filename not in cache:
        cache[filename] = track_info.get("drop_approx", 30.0)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    print(f"  Beat drop cache: {filename} → ~{track_info.get('drop_approx', 30.0)}s (librosa will refine)")


# ─── Selection logic ───────────────────────────────────────────────────────────

def pick_for_action(action_type: str) -> tuple:
    """
    Pick the best downloaded track for a given action type.
    Falls back to energy-level match if exact action not found.
    Returns (filename, track_info) or (None, None).
    """
    # Priority 1: exact action_type match, already downloaded
    candidates = []
    for fname, info in MUSIC_LIBRARY.items():
        if action_type in info["action_types"] and is_downloaded(fname):
            candidates.append((fname, info))

    # Priority 2: energy-level match
    if not candidates:
        from lol_editor import ACTION_ENERGY
        required_energy = ACTION_ENERGY.get(action_type, "any")
        for fname, info in MUSIC_LIBRARY.items():
            if is_downloaded(fname) and (info["energy"] == required_energy or required_energy == "any"):
                candidates.append((fname, info))

    # Priority 3: any downloaded track
    if not candidates:
        for fname, info in MUSIC_LIBRARY.items():
            if is_downloaded(fname):
                candidates.append((fname, info))

    if not candidates:
        return None, None

    import random
    chosen = random.choice(candidates)
    return chosen


def get_attribution(filename: str) -> str:
    """Return the attribution string for a music file (for video description)."""
    if os.path.exists(ATTRIBUTION_FILE):
        try:
            with open(ATTRIBUTION_FILE, encoding="utf-8") as f:
                attrs = json.load(f)
            if filename in attrs:
                return attrs[filename].get("attribution", "")
        except Exception:
            pass
    return ""


# ─── Download commands ─────────────────────────────────────────────────────────

def download_all_missing(verbose: bool = True) -> int:
    """Download all tracks in the library that aren't in lol_music/ yet."""
    missing = [(f, info) for f, info in MUSIC_LIBRARY.items() if not is_downloaded(f)]
    if not missing:
        print(f"  All {len(MUSIC_LIBRARY)} tracks already downloaded.")
        return 0

    print(f"\n  {len(missing)} tracks to download (already have {len(MUSIC_LIBRARY)-len(missing)}):\n")
    for fname, info in missing:
        print(f"    - {info['artist']} — {info['title']} [{info['energy']}]")

    print()
    downloaded = 0
    for fname, info in missing:
        if download_track(fname, info):
            downloaded += 1
        else:
            print(f"  Skipping {fname} — will retry next time")

    print(f"\n  Done: {downloaded}/{len(missing)} tracks downloaded")
    return downloaded


def download_for_action_type(action_type: str) -> bool:
    """
    Ensure at least one track exists for the given action type.
    Downloads if missing.
    """
    # Check if already have a good match
    fname, info = pick_for_action(action_type)
    if fname:
        print(f"  Already have: {fname} ({info['energy']} energy) for {action_type}")
        return True

    # Find best candidate in library
    matches = [(f, i) for f, i in MUSIC_LIBRARY.items()
               if action_type in i["action_types"]]
    if not matches:
        # Fallback: match by energy
        from lol_editor import ACTION_ENERGY
        required = ACTION_ENERGY.get(action_type, "medium")
        matches = [(f, i) for f, i in MUSIC_LIBRARY.items()
                   if i["energy"] == required]

    if not matches:
        print(f"  No track in library for action: {action_type}")
        return False

    fname, info = matches[0]
    return download_track(fname, info)


def print_library_status():
    """Show all tracks with download status."""
    print(f"\n{'='*65}")
    print(f"  LOL AGENT — MUSIC LIBRARY")
    print(f"{'='*65}")
    downloaded = 0
    for fname, info in MUSIC_LIBRARY.items():
        status = "OK" if is_downloaded(fname) else "MISSING"
        mark = "✓" if status == "OK" else "·"
        downloaded += 1 if status == "OK" else 0
        print(f"  [{mark}] {status:<7}  [{info['energy']:<6}]  {info['artist']} — {info['title']}")
        print(f"           Actions: {', '.join(info['action_types'])}")

    print(f"{'─'*65}")
    print(f"  Downloaded: {downloaded}/{len(MUSIC_LIBRARY)}")
    if downloaded < len(MUSIC_LIBRARY):
        print(f"  Run: python lol_music_downloader.py  to download missing tracks")
    print(f"{'='*65}\n")


# ─── Auto-detect and download for a clip ─────────────────────────────────────

def ensure_music_for_clip(clip_path: str = None, action_type: str = None) -> str:
    """
    Main entry point: given a clip path or action_type, ensure the right music
    is downloaded and return the path to use.

    Called automatically by the pipeline before rendering.
    """
    if not action_type and clip_path:
        # Try to detect from filename or Medal DB
        try:
            from lol_clip_ranker import fast_kill_scan
            kills = fast_kill_scan(clip_path)
            if kills:
                highest = kills[-1][1].lower().replace(" ", "")
                action_type = highest
        except Exception:
            pass

    action_type = action_type or "outplay"

    # Try to pick from already downloaded tracks first
    fname, info = pick_for_action(action_type)
    if fname:
        path = os.path.join(MUSIC_DIR, fname)
        print(f"  Music selected: {info['artist']} — {info['title']} [{info['energy']}]")
        return path

    # Download the best track for this action
    print(f"  No music for '{action_type}' found — downloading...")
    download_for_action_type(action_type)

    # Try again
    fname, info = pick_for_action(action_type)
    if fname:
        return os.path.join(MUSIC_DIR, fname)

    return None


# ─── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LOL Agent — Music Downloader")
    parser.add_argument("--list",   action="store_true", help="Show library status")
    parser.add_argument("--all",    action="store_true", help="Download all missing tracks")
    parser.add_argument("--action", type=str,            help="Download best track for this action type")
    parser.add_argument("--url",    type=str,            help="Download a custom URL (saves to lol_music/custom_*.mp3)")
    args = parser.parse_args()

    if args.list:
        print_library_status()

    elif args.all:
        print_library_status()
        download_all_missing()
        # Run librosa on all new files to get exact drop times
        try:
            from lol_beat_detector import detect_beat_drop
            print("\n  Auto-detecting beat drops with librosa...")
            for fname in MUSIC_LIBRARY:
                path = os.path.join(MUSIC_DIR, fname)
                if os.path.exists(path):
                    detect_beat_drop(path)
        except Exception as e:
            print(f"  Librosa detection skipped: {e}")

    elif args.action:
        print(f"\n  Ensuring music for action: {args.action}")
        result = ensure_music_for_clip(action_type=args.action)
        print(f"  Music path: {result}")

    elif args.url:
        # Custom URL download
        os.makedirs(MUSIC_DIR, exist_ok=True)
        import re, time
        safe_name = f"custom_{int(time.time())}.mp3"
        output = os.path.join(MUSIC_DIR, safe_name)
        cmd = [sys.executable, "-m", "yt_dlp",
               "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K",
               "--output", output.replace(".mp3", ".%(ext)s"),
               "--no-playlist", "--progress", args.url]
        subprocess.run(cmd)
        print(f"\n  Saved as: {safe_name}")
        print(f"  Add to MUSIC_ENERGY_MAP in lol_editor.py with energy: high/medium/low")

    else:
        # Default: show status + download missing
        print_library_status()
        answer = input("Download all missing tracks? [y/N]: ").strip().lower()
        if answer == "y":
            download_all_missing()
