"""
weekly_channel_analyzer.py
Uruchom 1x w tygodniu. Analizuje kanał YT dark_mindset:
- Statystyki wyświetleń, AVD, subskrybentów
- Które shortsy radza sobie najlepiej / najgorzej
- Rekomendacje co poprawić (tagi, tytuł, czas publikacji)
- Zapisuje raport do weekly_report_YYYY-MM-DD.json
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["PYTHONIOENCODING"] = "utf-8"

from data_collector import get_authenticated_service

PROFILE_NAME  = "dark_mindset"
REPORT_FILE   = f"weekly_report_{datetime.now().strftime('%Y-%m-%d')}.json"
DAYS_BACK     = 7

# ─── Kolory CLI ───────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def fetch_channel_stats(youtube):
    """Pobiera podstawowe statystyki kanału."""
    res = youtube.channels().list(
        part="statistics,snippet",
        mine=True
    ).execute()
    ch = res["items"][0]
    return {
        "name":        ch["snippet"]["title"],
        "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
        "total_views": int(ch["statistics"].get("viewCount", 0)),
        "video_count": int(ch["statistics"].get("videoCount", 0))
    }

def fetch_recent_shorts(youtube, days=7):
    """Pobiera shortsy z ostatnich X dni."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    search_res = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        videoDuration="short",
        publishedAfter=since,
        maxResults=50,
        order="date"
    ).execute()

    video_ids = [item["id"]["videoId"] for item in search_res.get("items", [])]
    if not video_ids:
        return []

    # Pobierz szczegóły każdego wideo
    details_res = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids)
    ).execute()

    shorts = []
    for v in details_res.get("items", []):
        stats = v.get("statistics", {})
        shorts.append({
            "id":          v["id"],
            "title":       v["snippet"]["title"],
            "published":   v["snippet"]["publishedAt"],
            "views":       int(stats.get("viewCount", 0)),
            "likes":       int(stats.get("likeCount", 0)),
            "comments":    int(stats.get("commentCount", 0)),
            "link":        f"https://youtube.com/shorts/{v['id']}"
        })
    return sorted(shorts, key=lambda x: x["views"], reverse=True)

def generate_recommendations(channel, shorts):
    """Generuje rekomendacje na podstawie danych."""
    recs = []

    if not shorts:
        recs.append("⚠️  Brak shortów z ostatnich 7 dni — zadbaj o regularność (2/dzień).")
        return recs

    avg_views = sum(s["views"] for s in shorts) / len(shorts)
    top        = shorts[0]
    worst      = shorts[-1]

    recs.append(f"📊 Średnia wyświetleń: {avg_views:.0f} | Najlepszy: '{top['title']}' ({top['views']} views)")
    recs.append(f"📉 Najsłabszy: '{worst['title']}' ({worst['views']} views)")

    # Analiza tytułów
    keyword_first = sum(1 for s in shorts if s["title"].lower().startswith("dark") or "psychology" in s["title"].lower() [:20])
    if keyword_first < len(shorts) * 0.6:
        recs.append("🔴 TYTUŁ: Zbyt mało tytułów zaczyna się od keyword. Cel: 'Dark Psychology: [temat]'")

    # Analiza shortów
    has_shorts_tag = sum(1 for s in shorts if "#shorts" in s["title"].lower())
    if has_shorts_tag < len(shorts):
        recs.append("🟡 TAG: Nie wszystkie filmy mają #shorts w tytule — dodaj.")

    # Zaangażowanie
    avg_likes = sum(s["likes"] for s in shorts) / len(shorts) if shorts else 0
    if avg_views > 0:
        engagement = avg_likes / avg_views * 100
        if engagement < 2:
            recs.append(f"🟡 ENGAGEMENT: Wskaźnik lajków {engagement:.1f}% < 2%. Dodaj CTA na końcu skryptu ('Like if this helped').")
        else:
            recs.append(f"✅ ENGAGEMENT: {engagement:.1f}% — dobry wynik.")

    # Regularność
    if len(shorts) < days_needed(DAYS_BACK):
        recs.append(f"🔴 REGULARNOŚĆ: Tylko {len(shorts)} shortów w {DAYS_BACK} dni. Cel: {DAYS_BACK * 2} (2/dzień).")

    # Najlepszy dzień tygodnia
    if len(shorts) >= 5:
        from collections import Counter
        days_map = {0:"Pon",1:"Wt",2:"Śr",3:"Czw",4:"Pt",5:"Sob",6:"Nd"}
        day_views = Counter()
        for s in shorts:
            day = datetime.fromisoformat(s["published"].replace("Z","+00:00")).weekday()
            day_views[day] += s["views"]
        best_day = days_map[day_views.most_common(1)[0][0]]
        recs.append(f"✅ NAJLEPSZY DZIEŃ: {best_day} — rozważ publikację pierwszego shorta właśnie wtedy.")

    return recs

def days_needed(days_back):
    return days_back  # minimum 1/dzień

def main():
    print(f"\n{'='*55}")
    print(f"  WEEKLY CHANNEL ANALYZER — {PROFILE_NAME.upper()}")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}\n")

    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Błąd autoryzacji YouTube.")
        return

    print("🔍 Pobieranie statystyk kanału...")
    channel = fetch_channel_stats(youtube)

    print(f"✅ Kanał: {channel['name']}")
    print(f"   👥 Subskrybenci: {channel['subscribers']:,}")
    print(f"   👁️  Łączne wyświetlenia: {channel['total_views']:,}")
    print(f"   🎬 Liczba filmów: {channel['video_count']}")

    print(f"\n🔍 Pobieranie shortów z ostatnich {DAYS_BACK} dni...")
    shorts = fetch_recent_shorts(youtube, DAYS_BACK)
    print(f"✅ Znaleziono {len(shorts)} shortów.\n")

    print("┌─ TOP SHORTSY ─────────────────────────────────────┐")
    for i, s in enumerate(shorts[:5], 1):
        print(f"│ #{i} {s['views']:>6} views | 👍{s['likes']:>4} | {s['title'][:42]}")
    print("└────────────────────────────────────────────────────┘\n")

    recs = generate_recommendations(channel, shorts)
    print("┌─ REKOMENDACJE ─────────────────────────────────────┐")
    for r in recs:
        print(f"│ {r}")
    print("└────────────────────────────────────────────────────┘\n")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "shorts_analyzed": shorts,
        "recommendations": recs
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)

    print(f"📋 Raport zapisany: {REPORT_FILE}")
    print("\n✅ Analiza zakończona!")

if __name__ == "__main__":
    main()
