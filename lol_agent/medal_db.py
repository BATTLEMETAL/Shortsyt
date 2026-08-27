"""
Medal DB Integration — Odczyt metadanych klipów z lokalnej bazy Medal.
Medal przechowuje w SQLite: tytuł klipu (np. "Pentakill - Katarina"),
czas trwania, ścieżkę do thumbnail, itp.

Metadata w tabeli 'contents' jest w formacie MessagePack (binarny).
Parsujemy ją regex-em na surowych bajtach (nie wymaga msgpack library).
"""
import os
import re
import sys
import sqlite3
import glob
from typing import Optional, List

sys.stdout.reconfigure(encoding='utf-8')

# ─── Medal DB Path ─────────────────────────────────────────────────────────────
MEDAL_STORE_DIR = os.path.join(os.environ.get("APPDATA", ""), "Medal")


def _find_medal_db() -> Optional[str]:
    """Znajduje główną bazę Medal SQLite (medal-<userId>.db)."""
    if not os.path.isdir(MEDAL_STORE_DIR):
        return None
    pattern = os.path.join(MEDAL_STORE_DIR, "medal-*.db")
    dbs = glob.glob(pattern)
    # Filtruj guest DB
    dbs = [d for d in dbs if "guest" not in os.path.basename(d).lower()]
    if not dbs:
        return None
    # Bierz największą (główne konto)
    return max(dbs, key=os.path.getsize)


# ─── Title → Action Type Mapping ──────────────────────────────────────────────
MEDAL_TITLE_MAP = {
    "pentakill":   "pentakill",
    "penta kill":  "pentakill",
    "quadra kill": "quadrakill",
    "quadrakill":  "quadrakill",
    "triple kill": "triple",
    "double kill": "double",
    "baron":       "baron",
    "dragon":      "dragon",
    "steal":       "clutch",
}


def parse_medal_title(title: str) -> dict:
    """
    Parsuje tytuł Medal do action_type i champion_name.
    
    Przykłady:
        'Pentakill - Katarina'  → {'action_type': 'pentakill', 'champion': 'Katarina'}
        'Triple Kill - Yone'    → {'action_type': 'triple',    'champion': 'Yone'}
        'Double Kill - Jinx'    → {'action_type': 'double',    'champion': 'Jinx'}
        'Kill - Zed'            → {'action_type': 'oneshot',   'champion': 'Zed'}
    """
    result = {"action_type": "outplay", "champion": "", "raw_title": title}
    
    if not title:
        return result
    
    title_lower = title.lower().strip()
    
    # Spróbuj dopasować action type z mapy (od najdłuższego klucza)
    for pattern, action in sorted(MEDAL_TITLE_MAP.items(), key=lambda x: -len(x[0])):
        if pattern in title_lower:
            result["action_type"] = action
            break
    else:
        # Fallback: jeśli "kill" jest w tytule ale nie matchuje specyficznie
        if "kill" in title_lower:
            result["action_type"] = "oneshot"
    
    # Wyciągnij championa (po " - " w tytule Medal)
    if " - " in title:
        parts = title.split(" - ", 1)
        champion = parts[1].strip()
        # Oczyść z ewentualnych tagów/emojis
        champion = re.sub(r'[^\w\s]', '', champion).strip()
        if champion:
            result["champion"] = champion
    
    return result


def _extract_metadata_from_blob(blob: bytes) -> dict:
    """
    Wyciąga metadane z binarnego blobu MessagePack.
    Używa regex-a na surowych bajtach — nie wymaga biblioteki msgpack.
    """
    meta = {}
    
    if not blob:
        return meta
    
    # Szukaj tytułu: "title" followed by string
    # MessagePack string format: 0xc7 <len> <string> or 0xa0-0xbf fixstr
    try:
        text = blob.decode('utf-8', errors='replace')
    except Exception:
        text = str(blob)
    
    # Szukaj pola "title" + wartości
    title_match = re.search(r'title(.{1,3}?)([\w\s\-\']+(?:\s*-\s*[\w\s]+)?)', text)
    if title_match:
        raw_title = title_match.group(2).strip()
        # Oczyść nieprintable chars
        raw_title = ''.join(c for c in raw_title if c.isprintable())
        meta["title"] = raw_title
    
    # Szukaj clipDuration
    dur_match = re.search(r'clipDuration.{1,3}?([\d.]+)', text)
    if dur_match:
        try:
            meta["duration"] = float(dur_match.group(1))
        except ValueError:
            pass
    
    # Szukaj gameSessionId lub innych pól
    game_match = re.search(r'gameSessionId.{1,3}?([\w-]+)', text)
    if game_match:
        meta["game_session"] = game_match.group(1)
    
    return meta


def get_clip_metadata(video_path: str) -> dict:
    """
    Pobiera metadane klipu z Medal DB na podstawie ścieżki do pliku.
    
    Returns:
        {
            'title': 'Pentakill - Katarina',
            'champion': 'Katarina',
            'action_type': 'pentakill',
            'duration': 28.3,
            'thumbnail': 'C:\\Medal\\Thumbnails\\...jpg',
            'created_at': 1778590998,
            'source': 'medal_db'
        }
    
    Jeśli brak w bazie, zwraca dict z source='filename_guess'.
    """
    result = {
        "title": "",
        "champion": "",
        "action_type": "outplay",
        "duration": 0.0,
        "thumbnail": "",
        "created_at": 0,
        "source": "none"
    }
    
    # Normalizuj ścieżkę
    video_path_norm = os.path.normpath(video_path)
    
    db_path = _find_medal_db()
    if db_path:
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            # Szukaj po ścieżce
            c.execute(
                "SELECT created_at, video_path, thumbnail_path, metadata "
                "FROM contents WHERE video_path = ?",
                (video_path_norm,)
            )
            row = c.fetchone()
            
            # Fallback: szukaj po nazwie pliku
            if not row:
                fname = os.path.basename(video_path)
                c.execute(
                    "SELECT created_at, video_path, thumbnail_path, metadata "
                    "FROM contents WHERE video_path LIKE ?",
                    (f"%{fname}",)
                )
                row = c.fetchone()
            
            if row:
                created_at, db_path_val, thumb, metadata_blob = row
                result["created_at"] = created_at or 0
                result["thumbnail"] = thumb or ""
                result["source"] = "medal_db"
                
                # Parsuj metadata blob
                if metadata_blob:
                    blob_meta = _extract_metadata_from_blob(metadata_blob)
                    if blob_meta.get("title"):
                        result["title"] = blob_meta["title"]
                        parsed = parse_medal_title(blob_meta["title"])
                        result["champion"] = parsed["champion"]
                        result["action_type"] = parsed["action_type"]
                    if blob_meta.get("duration"):
                        result["duration"] = blob_meta["duration"]
            
            conn.close()
            
        except Exception as e:
            print(f"⚠️  Medal DB read error: {e}")
    
    # Fallback: filename guess
    if not result["champion"]:
        result["source"] = "filename_guess"
        fname = os.path.basename(video_path).lower()
        champions = [
            "jinx", "yasuo", "zed", "ahri", "lee sin", "thresh", "vayne",
            "master yi", "katarina", "lux", "yone", "viego", "akali",
            "ezreal", "caitlyn", "sylas", "fizz", "rengar", "irelia",
            "riven", "fiora", "camille", "qiyana", "talon", "diana",
            "leblanc", "ekko", "kassadin", "kayn", "khazix", "samira",
        ]
        for champ in champions:
            if champ.replace(" ", "") in fname.replace(" ", ""):
                result["champion"] = champ.title()
                break
    
    return result


def get_all_clips(limit: int = 50) -> List[dict]:
    """
    Pobiera wszystkie klipy z Medal DB posortowane od najnowszych.
    Przydatne do batch processing.
    """
    clips = []
    db_path = _find_medal_db()
    
    if not db_path:
        print("⚠️  Nie znaleziono bazy Medal")
        return clips
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "SELECT created_at, video_path, thumbnail_path, metadata "
            "FROM contents ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        
        for row in c.fetchall():
            created_at, video_path, thumb, metadata_blob = row
            clip = {
                "video_path": video_path,
                "thumbnail": thumb or "",
                "created_at": created_at or 0,
                "title": "",
                "champion": "",
                "action_type": "outplay",
                "duration": 0.0,
            }
            
            if metadata_blob:
                blob_meta = _extract_metadata_from_blob(metadata_blob)
                if blob_meta.get("title"):
                    clip["title"] = blob_meta["title"]
                    parsed = parse_medal_title(blob_meta["title"])
                    clip["champion"] = parsed["champion"]
                    clip["action_type"] = parsed["action_type"]
                if blob_meta.get("duration"):
                    clip["duration"] = blob_meta["duration"]
            
            clips.append(clip)
        
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Medal DB error: {e}")
    
    return clips


# ─── CLI Test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("🏅 MEDAL DB READER — Test")
    print("=" * 60)
    
    # Test 1: Pobierz wszystkie klipy
    clips = get_all_clips()
    print(f"\n📋 Znaleziono {len(clips)} klipów w Medal DB:\n")
    for i, clip in enumerate(clips, 1):
        print(f"  {i}. {clip['title'] or '(brak tytułu)'}")
        print(f"     🎮 Champion: {clip['champion'] or '?'} | Action: {clip['action_type']}")
        print(f"     ⏱️  Duration: {clip['duration']:.1f}s")
        print(f"     📁 {os.path.basename(clip['video_path'] or '')}")
        print()
    
    # Test 2: Pobierz metadata dla konkretnego klipu
    test_path = r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4"
    if os.path.exists(test_path):
        print(f"\n🔍 Test get_clip_metadata:")
        meta = get_clip_metadata(test_path)
        for k, v in meta.items():
            print(f"   {k}: {v}")
