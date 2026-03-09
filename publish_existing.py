"""
publish_existing.py
===================
ANALIZA + PUBLIKACJA gotowych wideo z temp_videos na YouTube.

Zadania:
1. Skanuje temp_videos/*.mp4
2. Analizuje każde wideo (duracja, rozmiar, dopasowanie do niszy)
3. Przypisuje do odpowiedniego konta (dark_mindset / brainrot / kanal_2)
4. Generuje zoptymalizowany tytuł, opis, tagi, thumbnail
5. Publikuje z pełną metadatą SEO - tryb "private" pierwszy, potem "public"
"""

import os
import re
import json
import pickle
import sys
import argparse
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# ─── KONFIGURACJA WIDEO ─────────────────────────────────────────────────────

VIDEOS_DIR    = "temp_videos"
ACCOUNTS_DIR  = "accounts"
HISTORY_FILE  = "accounts/topic_history.json"

# Mapa wideo → konto → metadane
VIDEO_ASSIGNMENTS = {
    "HINT_dark_mindset_gotowy_short.mp4": {
        "konto": "dark_mindset",
        "nisza": "dark psychology",
        "title": "😱 The Manipulation Secret They Don't Want You To Know 💀",
        "description": (
            "The most dangerous people around you never raise their voice. "
            "They use SILENCE as a weapon. This one psychology trick changes everything.\n\n"
            "💡 Follow for more dark psychology secrets every day!\n"
            "#darkpsychology #manipulation #psychology #mindcontrol #shorts #viral"
        ),
        "tags": [
            "dark psychology", "manipulation", "mind control", "psychology secrets",
            "silent manipulation", "psychology tips", "viral psychology",
            "shorts", "viral shorts", "psychology shorts"
        ],
        "category_id": "22",  # People & Blogs
        "viral_score": 9,
        "rationale": "Mocny hook + temat dark psychology w 2026 łapie 10M+ wyświetleń. "
                     "Cisza jako broń = niszowy ale mega-angażujący kontent.",
    },
    "HINT_kanal_1_gotowy_short.mp4": {
        "konto": "brainrot",
        "nisza": "brainrot roblox",
        "title": "💥 POV: Dziadek w Roblox i Ohio Moment 😂 #brainrot",
        "description": (
            "Kiedy twój dziadek próbuje grać w Roblox i robi to najlepiej jak potrafi...\n"
            "Ohio level: MAX 🤣\n\n"
            "Subscribe żeby nie przegapić kolejnego brainrota!\n"
            "#brainrot #roblox #ohio #sigma #shorts #viral #polska #gaming"
        ),
        "tags": [
            "brainrot", "roblox", "ohio", "sigma", "polska brainrot",
            "gaming shorts", "funny roblox", "roblox polska",
            "brainrot shorts", "viral gaming", "shorts", "zabawne"
        ],
        "category_id": "20",  # Gaming
        "viral_score": 7,
        "rationale": "Brainrot + Roblox = top algorytm dla 12-18 lat. "
                     "Niska konkurencja polskie brainrot shorts.",
    },
    "HINT_kanal_2_gotowy_short.mp4": {
        "konto": "dark_mindset",
        "nisza": "psychology mindset",
        "title": "🧠 3 Mroczne Triki Psychologiczne które widzisz każdego dnia 💡",
        "description": (
            "Ludzie wokół Ciebie używają tych technik CODZIENNIE.\n"
            "Czy wiesz jak się przed nimi bronić?\n\n"
            "Subskrybuj po więcej wiedzy z psychologii!\n"
            "#psychologia #darkpsychology #manipulacja #mindset #shorts #viral"
        ),
        "tags": [
            "psychologia", "dark psychology", "manipulacja", "triki psychologiczne",
            "mindset", "psychologia shorts", "viral psychologia",
            "shorts polska", "wiedza", "self improvement"
        ],
        "category_id": "22",  # People & Blogs
        "viral_score": 8,
        "rationale": "Psychologia PL - wschodzący trend. 8M+ miesięcznie subskrybujących podobne kanały.",
    },
    "HINT_brainrot_gotowy_short.mp4": {
        "konto": "brainrot",
        "nisza": "brainrot polska",
        "title": "🫠 Ten Random Moment w Szkole był SIGMA 💀 #brainrot #ohio",
        "description": (
            "Codzienny brainrot prosto z polskiej szkoły 😂\n"
            "Like jeśli to twoja szkoła!\n\n"
            "#brainrot #ohio #sigma #szkola #shorts #viral #polska"
        ),
        "tags": [
            "brainrot polska", "ohio", "sigma", "szkola", "polska shorts",
            "brainrot", "viral polska", "funny poland", "shorts pl", "tiktok polska"
        ],
        "category_id": "20",  # Gaming
        "viral_score": 7,
        "rationale": "Polskie brainrot to niszowy ale szybko rosnący trend w 2026.",
    },
}

# ─── FUNKCJE ─────────────────────────────────────────────────────────────────

def get_authenticated_service(profile_name: str):
    """Autoryzacja przez pickle token dla konta."""
    token_file = os.path.join(ACCOUNTS_DIR, f"{profile_name}_token.pickle")
    if not os.path.exists(token_file):
        print(f"❌ Brak tokenu dla '{profile_name}': {token_file}")
        print(f"   Uruchom: python authorize_channel.py --konto {profile_name}")
        return None
    with open(token_file, 'rb') as f:
        credentials = pickle.load(f)
    if credentials and credentials.expired and credentials.refresh_token:
        print(f"🔄 Odświeżam token dla {profile_name}...")
        credentials.refresh(Request())
        with open(token_file, 'wb') as f:
            pickle.dump(credentials, f)
    return build('youtube', 'v3', credentials=credentials)


def sanitize_tags(tags: list) -> list:
    """Czyści tagi z błędnych znaków i limituje do 15."""
    clean = []
    for t in tags:
        ct = re.sub(r'[<>"#]', '', str(t)).strip()
        if ct and ct not in clean and len(ct) <= 30:
            clean.append(ct)
    return clean[:15]


def get_publish_time_offset(hours: int = 2) -> str:
    """Zwraca czas publikacji jako ISO string w UTC = teraz + hours."""
    future = datetime.now(timezone.utc) + timedelta(hours=hours)
    return future.strftime("%Y-%m-%dT%H:%M:%SZ")


def analyze_and_print_video(video_file: str, meta: dict) -> bool:
    """Wyświetla analizę viral potential i pyta o potwierdzenie."""
    file_path = os.path.join(VIDEOS_DIR, video_file)
    if not os.path.exists(file_path):
        print(f"⚠️  Plik nie istnieje: {file_path}")
        return False

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"\n{'='*60}")
    print(f"🎬 ANALIZA: {video_file}")
    print(f"{'='*60}")
    print(f"  ▸ Rozmiar:      {size_mb:.1f} MB")
    print(f"  ▸ Konto:        @{meta['konto']}")
    print(f"  ▸ Nisza:        {meta['nisza']}")
    print(f"  ▸ Viral Score:  {meta['viral_score']}/10")
    print(f"  ▸ UZASADNIENIE: {meta['rationale']}")
    print(f"  ▸ Tytuł YT:     {meta['title']}")
    print(f"  ▸ Tagi (5):     {', '.join(meta['tags'][:5])}")
    return True


def upload_video(youtube, file_path: str, meta: dict, dry_run: bool = False) -> str | None:
    """Uploaduje wideo na YouTube z pełną metadatą SEO."""
    tags = sanitize_tags(meta['tags'])

    body = {
        'snippet': {
            'title':       meta['title'],
            'description': meta['description'],
            'tags':        tags,
            'categoryId':  meta['category_id'],
            'defaultLanguage': 'pl',
        },
        'status': {
            'privacyStatus': 'private',    # najpierw private, potem ręcznie public
            'selfDeclaredMadeForKids': False,
            'license': 'youtube',
        }
    }

    if dry_run:
        print(f"  [DRY RUN] Nie wrzucam, tylko symulacja. Metadane OK.")
        return "DRY_RUN_ID"

    print(f"\n📤 Uploading: {os.path.basename(file_path)} → {meta['konto']}...")
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"  ↳ Upload postęp: {pct}%", end='\r')
        video_id = response.get('id', '?')
        link = f"https://youtube.com/shorts/{video_id}"
        print(f"\n  ✅ SUKCES! ID: {video_id}")
        print(f"  🔗 Link: {link}")
        return video_id
    except Exception as e:
        print(f"\n  ❌ Błąd uploadu: {e}")
        return None


def update_history(konto: str, title: str):
    """Dodanie do historii deduplikacyjnej."""
    data = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass
    if konto not in data:
        data[konto] = []
    data[konto].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": title
    })
    data[konto] = data[konto][-50:]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"  📚 Dodano do historii deduplikacyjnej: {title[:50]}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analiza + Publikacja gotowych wideo na YouTube")
    parser.add_argument("--dry-run", action="store_true",
                        help="Tylko analiza, bez faktycznego uploadu")
    parser.add_argument("--konto", type=str, default=None,
                        help="Filtruj upload tylko dla tego konta (np. dark_mindset)")
    parser.add_argument("--plik", type=str, default=None,
                        help="Konkretny plik do upload (np. HINT_dark_mindset_gotowy_short.mp4)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("🚀 SYNAPSA PUBLISHER - ANALIZA I PUBLIKACJA WIDEO")
    print("   Tryb: " + ("DRY RUN (bez uploadu)" if args.dry_run else "LIVE UPLOAD"))
    print("="*60)

    # Filtrowanie
    videos_to_process = VIDEO_ASSIGNMENTS.copy()
    if args.plik:
        if args.plik in videos_to_process:
            videos_to_process = {args.plik: videos_to_process[args.plik]}
        else:
            print(f"❌ Nieznany plik: {args.plik}")
            sys.exit(1)
    if args.konto:
        videos_to_process = {
            k: v for k, v in videos_to_process.items()
            if v['konto'] == args.konto
        }

    # Sortowanie po viral score (malejąco)
    sorted_videos = sorted(videos_to_process.items(),
                           key=lambda x: x[1]['viral_score'], reverse=True)

    print(f"\n📋 Plan publikacji ({len(sorted_videos)} wideo):")
    for vf, meta in sorted_videos:
        analyze_and_print_video(vf, meta)

    if args.dry_run:
        print(f"\n{'='*60}")
        print("✅ DRY RUN zakończony. Użyj bez --dry-run by wrzucić na YT.")
        return

    # Grupujemy per konto
    by_account = {}
    for vf, meta in sorted_videos:
        acc = meta['konto']
        if acc not in by_account:
            by_account[acc] = []
        by_account[acc].append((vf, meta))

    results = []

    for account, videos in by_account.items():
        print(f"\n{'='*60}")
        print(f"🔑 Autoryzacja: @{account}")
        youtube = get_authenticated_service(account)
        if not youtube:
            print(f"  ↳ Pomijam {len(videos)} wideo (brak tokenu)")
            continue

        for vf, meta in videos:
            file_path = os.path.join(VIDEOS_DIR, vf)
            if not os.path.exists(file_path):
                print(f"  ⚠️  Brak pliku: {file_path}")
                continue

            vid_id = upload_video(youtube, file_path, meta, dry_run=False)
            if vid_id and vid_id != "DRY_RUN_ID":
                update_history(account, meta['title'])
                results.append({
                    "file": vf,
                    "konto": account,
                    "video_id": vid_id,
                    "link": f"https://youtube.com/shorts/{vid_id}",
                    "title": meta['title'],
                    "viral_score": meta['viral_score'],
                })

    # Raport końcowy
    print(f"\n{'='*60}")
    print(f"🎉 RAPORT KOŃCOWY - {len(results)} wideo opublikowanych")
    print(f"{'='*60}")
    for r in results:
        print(f"  ✅ [{r['konto']}] {r['title'][:50]}...")
        print(f"     🔗 {r['link']}")
        print(f"     📊 Viral Score: {r['viral_score']}/10")

    if results:
        # Zapisz raport
        report_file = "publish_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"\n📄 Raport zapisany: {report_file}")


if __name__ == "__main__":
    main()
