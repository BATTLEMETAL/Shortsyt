"""
pw_add_comments.py — Dodaje komentarz CTA z ofertą salonu do filmów Pretty Woman
==================================================================================
Automatycznie pobiera listę filmów z kanału, sprawdza które nie mają jeszcze
komentarza CTA (od właściciela kanału) i dodaje go.

Użycie:
    python pw_add_comments.py           # dodaje komentarze do filmów bez CTA
    python pw_add_comments.py --dry-run # podgląd bez działania
    python pw_add_comments.py --limit 3 # max 3 filmy
"""

import sys
import argparse

sys.stdout.reconfigure(encoding="utf-8")

PROFILE_NAME = "prettywoman"

# Słowo kluczowe rozpoznające własny komentarz CTA (żeby nie duplikować)
CTA_MARKER = "salon.prettywoman.pl"

# ── Treść komentarza ──────────────────────────────────────────────────────────
CTA_COMMENT = (
    "🔥 SALON PRETTY WOMAN — Afroloki, Warkoczyki, Box Braids\n"
    "📍 Świdnica, Dolny Śląsk\n\n"
    "🌐 Rezerwacja wizyty:\n"
    "https://salon.prettywoman.pl\n\n"
    "🛍️ Sklep z produktami do włosów:\n"
    "https://sklep.salon-prettywoman.pl/index.php\n\n"
    "🎵 Więcej filmów na TikTok:\n"
    "https://www.tiktok.com/@salonprettywoman\n\n"
    "💬 Napisz CHCĘ w komentarzu — odezwiemy się! 🙌"
)


def fetch_channel_videos(youtube, max_results: int = 20) -> list:
    """Pobiera listę filmów z kanału (Shorts) posortowanych od najnowszego."""
    resp = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=max_results,
        order="date"
    ).execute()
    videos = []
    for item in resp.get("items", []):
        vid_id = item["id"]["videoId"]
        title  = item["snippet"]["title"]
        videos.append({"video_id": vid_id, "title": title})
    return videos


def has_cta_comment(youtube, video_id: str) -> bool:
    """Sprawdza czy film ma już komentarz CTA od właściciela kanału."""
    try:
        resp = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=20,
            order="time"
        ).execute()
        for thread in resp.get("items", []):
            text = thread["snippet"]["topLevelComment"]["snippet"].get("textOriginal", "")
            if CTA_MARKER in text:
                return True
    except Exception:
        pass
    return False


def post_comment(youtube, video_id: str, title: str, dry_run: bool) -> bool:
    print(f"\n{'─'*55}")
    print(f"🎬 {title[:65]}")
    print(f"   https://www.youtube.com/shorts/{video_id}")

    if dry_run:
        print("   [DRY-RUN] Pominięto.")
        return True

    try:
        resp = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": CTA_COMMENT}
                    }
                }
            }
        ).execute()
        print(f"   ✅ Komentarz dodany! ID: {resp.get('id', '?')}")
        return True
    except Exception as e:
        err = str(e)
        if "commentsDisabled" in err:
            print("   ⚠️  Komentarze wyłączone dla tego wideo.")
        else:
            print(f"   ❌ Błąd: {err[:200]}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Pretty Woman — dodaj komentarze CTA")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=20, help="Max filmów do sprawdzenia")
    args = parser.parse_args()

    print("=" * 60)
    print("  🌸 SALON PRETTY WOMAN — Comment CTA Bot (Auto)")
    print("=" * 60)
    print(f"  Tryb: {'DRY-RUN' if args.dry_run else 'LIVE'}")

    from upload_youtube import get_authenticated_service

    print(f"\n🔑 Autoryzacja: {PROFILE_NAME}...")
    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Brak tokenu!")
        return

    print(f"\n📡 Pobieram listę filmów z kanału (max {args.limit})...")
    videos = fetch_channel_videos(youtube, max_results=args.limit)
    print(f"   Znaleziono: {len(videos)} filmów")

    added = 0
    skipped = 0
    for v in videos:
        vid_id = v["video_id"]
        title  = v["title"]
        if has_cta_comment(youtube, vid_id):
            print(f"\n⏭️  Ma już CTA: {title[:55]}")
            skipped += 1
            continue
        ok = post_comment(youtube, vid_id, title, args.dry_run)
        if ok:
            added += 1

    print(f"\n{'='*60}")
    print(f"✅ Gotowe! Dodano: {added} | Pominięto (już miały): {skipped}")
    if not args.dry_run:
        print("📺 https://studio.youtube.com")


if __name__ == "__main__":
    main()

