import sys
sys.stdout.reconfigure(encoding="utf-8")
from upload_youtube import get_authenticated_service

yt = get_authenticated_service("prettywoman")

CTA = (
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

VIDEOS = [
    ("ynaYIgb6BxE", "Chciałabyś zostać Braiderką?"),
    ("O7G3CjqFGFY", "Nasze Kucyki 🫶 Nie Mylić z Krabami!"),
]

for vid_id, title in VIDEOS:
    print(f"\n▶ {title[:60]}")
    try:
        r = yt.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": vid_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": CTA}
                    }
                }
            }
        ).execute()
        comment_id = r.get("id", "?")
        print(f"  ✅ Komentarz dodany! ID: {comment_id}")
    except Exception as e:
        print(f"  ❌ Błąd: {e}")

print("\n✅ Gotowe!")
