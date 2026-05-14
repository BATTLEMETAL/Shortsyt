"""
pw_upload_single.py — Jednorazowy upload konkretnego shorta na kanał prettywoman
=================================================================================
Użycie:
    python pw_upload_single.py
    python pw_upload_single.py --dry-run
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from upload_youtube import get_authenticated_service, upload_video

# ── Konfiguracja ──────────────────────────────────────────────────────────────
PROFILE_NAME = "prettywoman"

VIDEO_PATH = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\snaptik_7616464658181983520_v3.mp4"

# ── Metadane (zgodnie z życzeniem użytkownika) ────────────────────────────────
TITLE = "ZNASZ TO UCZUCIE? 😂 Afroloki 3 dni roboty... #shorts #afroloki #braiderka"

DESCRIPTION = """\
ZNASZ TO UCZUCIE? 😂

Kiedy robisz punktowe Afroloki… sama sobie… i nagle okazuje się, że ta fryzura powstaje 3 dni.

Bo przecież każda braiderka wie jak to wygląda…
👉 trochę po pracy
👉 trochę przed pracą
👉 trochę w pracy
👉 trochę wieczorem na kanapie

I tak chodzisz po mieście z połową głowy zaplecioną, bo dopóki nie skończysz… nie ma opcji odpuścić 😂

Braiderki! Przyznajcie się w komentarzach — też tak robicie swoje włosy?

A teraz pytanie do naszych klientek…
ZNASZ TO UCZUCIE, kiedy w końcu masz na głowie świeżutkie, sprężyste Afroloki?
Ten moment kiedy patrzysz w lustro i myślisz:
„Wow… nie ma nic lepszego!" 😍

Bo dobrze zrobione loki to nie tylko fryzura…
to pewność siebie, wygoda i efekt WOW każdego dnia ❤️🔥

📍 Salon Kosmetyczny Pretty Woman
ul. Ofiar Oświęcimskich 28, Świdnica
📞 788-945-643

🎓 Prowadzimy również szkolenia z Afroloków dla osób, które chcą nauczyć się tej techniki.

🛍️ Nasze produkty i włosy znajdziesz w sklepie online:
https://sklep.salon-prettywoman.pl/index.php

#afroloki #afrolokiświdnica #braiderka #braidinghair #warkoloki #warkoczykisyntetyczne \
#warkoczykiafrykańskie #loczki #kręconewłosy #crochethair #hairextensions \
#protectivestyles #naturalhairstyles #świdnica #wrocław #wałbrzych \
#dolnyslask #szkoleniaafroloki #pieknewlosy #shorts"""

# ── Tagi własne + sugerowane przez YouTube dla tej niszy ─────────────────────
TAGS = [
    "afroloki",               # core niche
    "afrolokiświdnica",       # lokalne SEO
    "braiderka",              # engagement – dla braiderek
    "braidinghair",           # sugerowany YT
    "braids",                 # sugerowany YT (globalny)
    "loczki",                 # PL niche
    "crochethair",            # sugerowany YT
    "protectivestyles",       # sugerowany YT
    "naturalhairstyles",      # sugerowany YT
    "boxbraids",              # sugerowany YT
    "hairextensions",         # sugerowany YT
    "hairstyle",              # sugerowany YT
    "warkoloki",
    "warkoczykisyntetyczne",
    "warkoczykiafrykańskie",
    "krecone wlosy",
    "swidnica",
    "wroclaw",
    "dolnyslask",
    "szkolenia afroloki",
    "shorts",
]

CATEGORY_ID = "26"      # Howto & Style
PRIVACY     = "public"

# ── Komentarz CTA (taki sam jak na pozostałych filmach kanału) ────────────────
CTA_COMMENT = """\
🔥 SALON PRETTY WOMAN — Afroloki, Warkoczyki, Box Braids
📍 Świdnica, Dolny Śląsk

🌐 Rezerwacja wizyty:
https://salon.prettywoman.pl

🛍️ Sklep z produktami do włosów:
https://sklep.salon-prettywoman.pl/index.php

🎵 Więcej filmów na TikTok:
https://www.tiktok.com/@salonprettywoman

💬 Napisz CHCĘ w komentarzu — odezwiemy się! 🙌"""

# ── Główna logika ─────────────────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("  🌸 SALON PRETTY WOMAN — Single Short Uploader")
    print("=" * 60)

    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Nie znaleziono pliku:\n   {VIDEO_PATH}")
        return

    size_mb = os.path.getsize(VIDEO_PATH) / 1024 / 1024
    print(f"\n🎬 Plik:   {os.path.basename(VIDEO_PATH)}")
    print(f"   Rozmiar: {size_mb:.1f} MB")
    print(f"\n📌 Tytuł:\n   {TITLE}")
    print(f"\n🏷️  Tagi:\n   {', '.join(TAGS)}")

    if dry_run:
        print("\n[DRY-RUN] Pominięto upload. Metadane wyglądają OK.")
        return

    print(f"\n🔑 Autoryzacja konta: {PROFILE_NAME}...")
    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Brak tokenu! Uruchom: python authorize_channel.py --konto prettywoman")
        return

    video_id = upload_video(
        youtube=youtube,
        file_path=VIDEO_PATH,
        title=TITLE,
        description=DESCRIPTION,
        tags=TAGS,
        category_id=CATEGORY_ID,
        privacy_status=PRIVACY,
    )

    if video_id:
        print(f"\n✅ Opublikowano!")
        print(f"   🔗 https://www.youtube.com/shorts/{video_id}")
        print(f"   📺 Studio: https://studio.youtube.com")

        # ── Auto-komentarz CTA ────────────────────────────────────────────────
        print("\n💬 Dodaję komentarz CTA...")
        try:
            youtube.commentThreads().insert(
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
            print("   ✅ Komentarz dodany!")
        except Exception as ce:
            print(f"   ⚠️  Komentarz pominięty: {type(ce).__name__} — {str(ce)[:120]}")
    else:
        print("\n❌ Upload nieudany. Sprawdź logi powyżej.")


if __name__ == "__main__":
    main()
