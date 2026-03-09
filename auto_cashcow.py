"""
auto_cashcow.py
===============
AUTONOMICZNY AGENT 2-KANAŁOWY — uruchamiaj raz dziennie via Task Scheduler.
"""

import sys
import io
# Wymuszenie UTF-8 na Windows (PowerShell cp1250 crash na emoji)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import json
import pickle
import time
import glob
import re
import argparse
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# ─── ŚCIEŻKI ────────────────────────────────────────────────────────────────
ACCOUNTS_DIR   = "accounts"
TEMP_DIR       = "temp_videos"
HISTORY_FILE   = "accounts/topic_history.json"
PATTERNS_FILE  = "accounts/viral_patterns.json"  # samokorekta

# ─── KONFIGURACJA KANAŁÓW (oddzielne wytyczne) ───────────────────────────────
CHANNEL_CONFIG = {
    "brainrot": {
        "token":       "accounts/brainrot_token.pickle",
        "prompt_rule": (
            "[DYREKTYWA KANAŁU: BRAINROT - JĘZYK POLSKI]\n"
            "Jesteś polskim reżyserem absurdalnych opowieści (styl Gen-Z/Gaming). Masz tylko 80 słów.\n"
            "ZASADA 1 [HOOK]: Zacznij natychmiast od szokującego pytania, intrygi lub absurdalnego faktu. Żadnego wiania nudą.\n"
            "ZASADA 2 [CIAŁO]: Zbuduj pędzącą spójną historię. Możesz okazyjnie (maks 1-2 razy) wpleść modny slang, ale fabuła jest najważniejsza.\n"
            "ZASADA 3 [LOOP]: Ostatnie zdanie musi zostać urwane w takim miejscu, aby czytając je razem z pierwszym zdaniem tworzyło CZYSTY SENS GRAMATYCZNY. Widz na YouTube ogląda film w pętli. Pętla musi być nierozerwalna.\n"
            "ZASADA 4 [GRAMATYKA]: Skrypt musi być w 100% poprawny gramatycznie, pisany wyłącznie do czytania przez Mrocznego Lektora. ZERO znaków specjalnych, ZERO instrukcji w nawiasach."
        ),
        "niche_searches": [
            "polish brainrot shorts viral",
            "roblox ohio sigma funny moments",
            "brainrot compilation polska",
        ],
        "category_id": "20",
        "lang": "pl",
        "count": 1,
    },
    "dark_mindset": {
        "token":       "accounts/dark_mindset_token.pickle",
        "prompt_rule": (
            "[DYREKTYWA KANAŁU: DARK MINDSET - JĘZYK ANGIELSKI]\n"
            "Jesteś anglojęzycznym ekspertem od mrocznej psychologii i manipulacji (Styl: Sigma, Power Dynamics, Cold Mindset). Masz 80 słów.\n"
            "ZASADA 1 [HOOK]: Rozpocznij ekstremalnie mocnym, psychologicznym haczykiem uderzającym w emocje widza. Żadnego 'Welcome back' ani 'Day 1'.\n"
            "ZASADA 2 [CIAŁO]: Mów bezpośrednio do słuchacza ('You'). Przekaż zimną, szokującą radę na temat dominacji społecznej, toksycznych zachowań lub odczytywania intencji.\n"
            "ZASADA 3 [LOOP]: Ostatnie zadanie musi zostać ucięte, tak aby idealnie łączyło się z początkiem tekstu.\n"
            "ZASADA 4 [CZYSTOŚĆ]: Generujesz tylko CZYSTY TEKST do przeczytania. English ONLY. Zero emotikon, zero didaskaliów."
        ),
        "niche_searches": [
            "dark psychology secrets shorts viral",
            "manipulation tactics they don't teach you",
            "mindset dark psychology viral 2025",
        ],
        "category_id": "22",
        "lang": "en",
        "count": 1,
    }
}

# ─── IMPORTY Z PROJEKTU ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from synapsa_bridge import generate_viral_script_with_synapsa
from cashcow_generator import generate_cashcow_from_text, CHANNELS_NICHES, load_niches
from data_collector import search_viral_shorts

# ─── POMOCNICZE ─────────────────────────────────────────────────────────────

def _load_history() -> dict:
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def _save_history(data: dict):
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_forbidden(channel: str, limit: int = 100) -> list:
    """Zwraca listę tytułów które Synapsa ma pominąć (deduplikacja)."""
    data = _load_history()
    return [item["title"] for item in data.get(channel, [])][-limit:]

def add_to_history(channel: str, title: str, vid_id: str):
    data = _load_history()
    if channel not in data:
        data[channel] = []
    data[channel].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title":     title,
        "video_id":  vid_id,
    })
    data[channel] = data[channel][-100:]
    _save_history(data)
    print(f"  📚 Historia deduplikacyjna: zapisano '{title[:50]}'")

def cleanup_temp(channel: str):
    """Usuwa wszystkie pliki tymczasowe (temp_videos + videos/{channel}) po zakończeniu uploadu."""
    removed = 0
    # Temp wideo
    for f in glob.glob(os.path.join(TEMP_DIR, f"*{channel}*")):
        try: os.remove(f); removed += 1
        except: pass
    # Temp pliki audio/ass z procesu generacji
    for ext in ["*.mp3", "*.ass", "*.srt"]:
        for f in glob.glob(ext):
            try: os.remove(f); removed += 1
            except: pass
    # Pobrane tła background (zostawiamy tylko 2 ostatnie per kanał by nie duplikować)
    bg_dir = os.path.join("videos", channel)
    if os.path.exists(bg_dir):
        bgs = sorted(glob.glob(os.path.join(bg_dir, "*.mp4")), key=os.path.getmtime)
        for old_bg in bgs[:-2]:   # zostaw 2 najnowsze
            try: os.remove(old_bg); removed += 1
            except: pass
    print(f"  🧹 Czyszczenie: usunięto {removed} temp plików dla [{channel}]")

def get_youtube(channel: str):
    """OAuth autoryzacja via token pickle."""
    cfg = CHANNEL_CONFIG[channel]
    token_path = cfg["token"]
    if not os.path.exists(token_path):
        print(f"  ❌ Brak tokenu: {token_path}  →  python authorize_channel.py --konto {channel}")
        return None
    with open(token_path, 'rb') as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, 'wb') as f:
            pickle.dump(creds, f)
    return build('youtube', 'v3', credentials=creds)

def upload(youtube, file_path: str, title: str, description: str,
           tags: list, category_id: str) -> str | None:
    """Upload wideo na YouTube, zwraca video_id."""
    # Sanityzacja tagów
    clean_tags = []
    for t in tags:
        ct = re.sub(r'[<>"#]', '', str(t)).strip()
        if ct and len(ct) <= 30 and ct not in clean_tags:
            clean_tags.append(ct)
    clean_tags = clean_tags[:15]

    body = {
        'snippet': {
            'title': title[:100],
            'description': description[:5000],
            'tags': clean_tags,
            'categoryId': category_id,
        },
        'status': {
            'privacyStatus': 'private',       # test the produkcyjny - do the the weryfikacji
            'selfDeclaredMadeForKids': False,
        }
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    try:
        req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                print(f"    ↳ {int(status.progress()*100)}%", end='\r')
        vid_id = response.get('id', '?')
        print(f"\n  ✅ Upload OK: https://youtube.com/shorts/{vid_id}")
        return vid_id
    except Exception as e:
        print(f"\n  ❌ Upload błąd: {e}")
        return None

# ─── SAMOANALIZA WYNIKÓW (po 24h) ────────────────────────────────────────────

def analyze_performance(youtube, channel: str):
    """Sprawdza wyświetlenia ostatnich wideo, zapisuje wzorce do viral_patterns.json."""
    data = _load_history()
    videos = data.get(channel, [])[-10:]   # ostatnie 10
    if not videos:
        return

    print(f"\n📊 SAMOANALIZA [{channel}]: sprawdzam {len(videos)} ostatnich wideo...")
    ids = [v["video_id"] for v in videos if v.get("video_id")]
    if not ids:
        return

    try:
        resp = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(ids)
        ).execute()

        results = []
        for item in resp.get('items', []):
            stats  = item.get('statistics', {})
            snip   = item.get('snippet', {})
            views  = int(stats.get('viewCount', 0))
            likes  = int(stats.get('likeCount', 0))
            title  = snip.get('title', '')
            results.append({"title": title, "views": views, "likes": likes})
            print(f"  ▸ {title[:50]} → 👁 {views:,} | 👍 {likes:,}")

        # Zapisz wzorce (top 3 tytuły po wyświetleniach)
        results.sort(key=lambda x: x["views"], reverse=True)
        patterns = {}
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
                    patterns = json.load(f)
            except:
                pass
        patterns[channel] = {
            "updated": datetime.now(timezone.utc).isoformat(),
            "top_videos": results[:3],
            "avg_views":  sum(r["views"] for r in results) // max(len(results), 1),
        }
        with open(PATTERNS_FILE, 'w', encoding='utf-8') as f:
            json.dump(patterns, f, indent=4, ensure_ascii=False)
        print(f"  💾 Wzorce zapisane: top avg {patterns[channel]['avg_views']:,} wyświetleń")

    except Exception as e:
        print(f"  ⚠️  Błąd analizy: {e}")

# ─── GŁÓWNA PĘTLA KANAŁU ─────────────────────────────────────────────────────

def run_channel(channel: str, dry_run: bool = False):
    cfg = CHANNEL_CONFIG[channel]
    print(f"\n{'='*62}")
    print(f"🎬 URUCHAMIAM KANAŁ: @{channel.upper()}")
    print(f"{'='*62}")

    # 1. Autoryzacja
    youtube = get_youtube(channel)
    if not youtube and not dry_run:
        print(f"  ↳ Brak autoryzacji. Pomiń lub uruchom authorize_channel.py --konto {channel}")
        return

    # 2. Wyszukaj trendy (kontekst dla Synapsy)
    print(f"\n🔍 Szukam trendów dla [{channel}]...")
    viral_context = []
    try:
        niche_q = cfg["niche_searches"][
            datetime.now().day % len(cfg["niche_searches"])   # rotacja codziennie
        ]
        viral_context = search_viral_shorts(youtube, niche_q, max_results=5) if youtube else []
    except Exception as e:
        print(f"  ⚠️  Błąd search: {e}")
    if not viral_context:
        viral_context = [f"Trending: {cfg['niche_searches'][0]}"]

    # 3. Generuj 2 unikalne shorty
    forbidden = get_forbidden(channel, limit=100)
    if forbidden:
        print(f"  🧠 [PAMIĘĆ] Zablokowanych tematów: {len(forbidden)}")

    uploaded = []
    for shot_num in range(1, cfg["count"] + 1):
        print(f"\n--- SHORT #{shot_num} dla @{channel} ---")

        # Generuj JSON z Synapsy (Qwen)
        director = generate_viral_script_with_synapsa(
            viral_context=viral_context,
            niche_topic=channel.replace("_", " "),
            channel_rule=cfg["prompt_rule"],
            forbidden_topics=forbidden + [v.get("title","") for v in uploaded],
        )
        if not director or "error" in director:
            print(f"  ❌ Synapsa nie zwróciła JSON: {director}")
            continue

        script_text  = director.get("script_text", "")
        title        = director.get("title",  f"{channel} #shorts #{shot_num}")
        description  = director.get("description", f"#{channel} #shorts #viral")
        raw_tags     = director.get("seo_tags", [channel, "shorts", "viral"])
        bg_vibe      = director.get("background_vibe", channel)
        music_folder = director.get("music_folder", channel)

        if not script_text:
            print("  ❌ Brak script_text — pomijam")
            continue

        print(f"  📝 Tytuł: {title[:60]}")
        print(f"  📊 Viral Score: {director.get('viral_score','?')}/10")

        if dry_run:
            print(f"  [DRY RUN] Pominięto generację wideo i upload.")
            continue

        # 4. Generacja wideo (render)
        output_file = generate_cashcow_from_text(
            script_text, channel,
            background_vibe=bg_vibe,
            music_folder=music_folder
        )
        if not output_file or not os.path.exists(output_file):
            print(f"  ❌ Nie wygenerowano pliku wideo.")
            continue

        # 5. Upload na YouTube
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split(",")
        vid_id = upload(youtube, output_file, title, description, raw_tags, cfg["category_id"])

        if vid_id:
            add_to_history(channel, title, vid_id)
            forbidden.append(title)   # bieżąca sesja też blokuje duplikaty
            uploaded.append({"title": title, "video_id": vid_id})

        # 6. Usuń temp pliki po każdym shorcie
        cleanup_temp(channel)
        time.sleep(3)   # przerwa między requestami

    # 7. Samoanaliza (statystyki ostatnich wideo)
    if youtube and not dry_run:
        try:
            analyze_performance(youtube, channel)
        except Exception as e:
            print(f"  ⚠️  Samoanaliza nieudana: {e}")

    print(f"\n✅ @{channel} — zakończono. Wrzucono: {len(uploaded)} shortsów.")
    return uploaded

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Autonomiczny Agent 2-Kanałowy: brainrot + dark_mindset"
    )
    parser.add_argument("--only",    type=str, default=None,
                        help="Uruchom tylko jeden kanał: brainrot / dark_mindset")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analiza bez generacji i uploadu")
    parser.add_argument("--analyze", action="store_true",
                        help="Tylko samoanaliza wyświetleń (bez nowych wideo)")
    args = parser.parse_args()

    print("\n" + "="*62)
    print("🤖 SYNAPSA AUTONOMOUS AGENT — START")
    print(f"   Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Tryb: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("="*62)

    channels = list(CHANNEL_CONFIG.keys())
    if args.only and args.only in CHANNEL_CONFIG:
        channels = [args.only]

    if args.analyze:
        # Tylko samoanaliza
        for ch in channels:
            yt = get_youtube(ch)
            if yt:
                analyze_performance(yt, ch)
        return

    # Główna pętla: brainrot → dark_mindset
    for channel in channels:
        run_channel(channel, dry_run=args.dry_run)

    print(f"\n{'='*62}")
    print("🏁 AGENT ZAKOŃCZYŁ PRACĘ")
    print(f"   Możesz zaplanować autostart: schtasks /create /tn 'Synapsa' /tr 'python auto_cashcow.py' /sc daily /st 10:00")
    print("="*62)


if __name__ == "__main__":
    main()
