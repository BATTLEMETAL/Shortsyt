"""
latest_shorts_analyzer.py
=========================
Analizuje 2 NAJNOWSZE Shortsy z kanału Dark Mindset.
Pobiera pełne dane z YouTube Data API + YouTube Analytics API.
Na końcu generuje listę konkretnych wskazówek CO POPRAWIĆ.

Użycie:
    python latest_shorts_analyzer.py
    python latest_shorts_analyzer.py --profil dark_mindset --top 2
"""

import os
import sys
import json
import pickle
import argparse
import re
from datetime import datetime, timezone, timedelta
from collections import Counter

# ── Encoding fix ────────────────────────────────────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

# ── Google API ───────────────────────────────────────────────
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── Stałe ───────────────────────────────────────────────────
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# ── Kolory CLI ───────────────────────────────────────────────
G  = "\033[92m"   # green
Y  = "\033[93m"   # yellow
R  = "\033[91m"   # red
C  = "\033[96m"   # cyan
B  = "\033[94m"   # blue
M  = "\033[95m"   # magenta
W  = "\033[97m"   # white bold
DIM= "\033[2m"
RST= "\033[0m"


# ═══════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════
def get_service(profile: str = "dark_mindset"):
    token_file = os.path.join("accounts", f"{profile}_token.pickle")
    if not os.path.exists(token_file):
        print(f"{R}❌ Brak tokenu: {token_file}{RST}")
        print(f"   Uruchom najpierw: python authorize_channel.py --konto {profile}")
        sys.exit(1)

    with open(token_file, "rb") as f:
        creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "wb") as f:
                pickle.dump(creds, f)
        else:
            print(f"{R}❌ Token wygasł i nie można go odświeżyć. Re-autoryzuj konto.{RST}")
            sys.exit(1)

    yt  = build("youtube",       "v3",    credentials=creds)
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    return yt, yta


# ═══════════════════════════════════════════════════════════
#  POBIERANIE DANYCH
# ═══════════════════════════════════════════════════════════
def get_channel_id(yt) -> str:
    res = yt.channels().list(part="id,snippet,statistics", mine=True).execute()
    ch = res["items"][0]
    return ch["id"], ch["snippet"]["title"], ch["statistics"]


def get_uploads_playlist(yt, channel_id: str) -> str:
    res = yt.channels().list(part="contentDetails", id=channel_id).execute()
    return res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_latest_videos(yt, playlist_id: str, count: int = 10) -> list:
    """Pobiera N najnowszych filmów z playlisty uploads."""
    res = yt.playlistItems().list(
        part="contentDetails,snippet",
        playlistId=playlist_id,
        maxResults=count
    ).execute()
    return res.get("items", [])


def get_video_details(yt, video_ids: list) -> list:
    """Pobiera pełne dane (snippet + statistics + contentDetails + status) dla listy ID."""
    res = yt.videos().list(
        part="snippet,statistics,contentDetails,status",
        id=",".join(video_ids)
    ).execute()
    return res.get("items", [])


def parse_duration_seconds(iso: str) -> int:
    """Parsuje PT1M30S → 90 sekund."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mi * 60 + s


def get_analytics(yta, channel_id: str, video_id: str, days_back: int = 28) -> dict:
    """
    Pobiera metryki z YouTube Analytics:
    views, estimatedMinutesWatched, averageViewDuration,
    averageViewPercentage, likes, annotationClickThroughRate
    """
    end_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        res = yta.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,"
                    "averageViewPercentage,likes,shares,subscribersGained",
            dimensions="video",
            filters=f"video=={video_id}",
            sort="-views"
        ).execute()

        rows = res.get("rows", [])
        if not rows:
            return {}

        # columns: video, views, estimatedMinutesWatched, averageViewDuration,
        #          averageViewPercentage, likes, shares, subscribersGained
        for row in rows:
            if row[0] == video_id:
                return {
                    "views_analytics": int(row[1]),
                    "est_minutes_watched": float(row[2]),
                    "avg_view_duration_s": float(row[3]),
                    "avg_view_pct": float(row[4]),
                    "likes_analytics": int(row[5]),
                    "shares": int(row[6]),
                    "subs_gained": int(row[7]),
                }
        return {}
    except Exception as e:
        print(f"{Y}  ⚠️  Analytics API niedostępne dla {video_id}: {e}{RST}")
        return {}


# ═══════════════════════════════════════════════════════════
#  ANALIZA & SCORING
# ═══════════════════════════════════════════════════════════
def score_title(title: str) -> tuple[int, list]:
    """
    Ocenia tytuł pod kątem CTR-optymalizacji.
    Zwraca (score 0-100, lista problemów).
    """
    score = 100
    issues = []
    tl = title.lower()

    # Hook w pierwszych słowach
    power_words = [
        "dark", "secret", "hidden", "you don't know", "most people", "never",
        "always", "brutal", "warning", "stop", "real truth", "they don't want",
        "psychology", "manipulation", "control", "power", "weak", "strong",
        "covert", "silent", "body language", "brain", "mind"
    ]
    found_power = sum(1 for w in power_words if w in tl)
    if found_power == 0:
        score -= 30
        issues.append("❌ TYTUŁ: Brak słów-kluczy wywołujących ciekawość (dark, secret, manipulation, warning...)")
    elif found_power == 1:
        score -= 10
        issues.append("🟡 TYTUŁ: Tylko 1 power-word. Spróbuj 2-3 (np. 'Dark Secret + Warning').")

    # Liczba (#2, #3) lub lista — wyższy CTR
    if re.search(r"\d", title):
        score += 5
    else:
        score -= 10
        issues.append("🟡 TYTUŁ: Brak cyfry (#3 Signs, 5 Tricks...). Liczby w tytule = +23% CTR (wg YouTube).")

    # Długość
    if len(title) > 70:
        score -= 10
        issues.append(f"🟡 TYTUŁ: Za długi ({len(title)} znaków). Optymalnie: 40-60 znaków.")
    elif len(title) < 20:
        score -= 20
        issues.append(f"❌ TYTUŁ: Za krótki ({len(title)} znaków). Brak informacji = niższy CTR.")

    # #shorts tag
    if "#shorts" not in tl:
        score -= 15
        issues.append("❌ TAG: Brak #shorts w tytule lub opisie. To kluczowe dla dystrybucji!")

    # Personalizacja (cię, ty, twój, you, your)
    personal = ["cię", "ty", "twój", "twoja", "twoje", "you", "your", "yourself"]
    if any(w in tl for w in personal):
        score += 10
    else:
        score -= 5
        issues.append("🟡 TYTUŁ: Brak personalizacji (ty, cię, you). Widz musi czuć, że TO O NIM.")

    return max(0, min(100, score)), issues


def score_engagement(views: int, likes: int, comments: int, duration_s: int, analytics: dict) -> tuple[int, list]:
    """Ocenia zaangażowanie i retencję."""
    score = 100
    issues = []

    # Like rate
    like_rate = (likes / views * 100) if views > 0 else 0
    if like_rate < 1.0:
        score -= 30
        issues.append(f"❌ LAJKI: Wskaźnik {like_rate:.2f}% (poniżej 1%). Dodaj CTA: 'Tap ❤️ if this shocked you'")
    elif like_rate < 3.0:
        score -= 10
        issues.append(f"🟡 LAJKI: {like_rate:.2f}% — cel to 3%+. Wzmocnij CTA w ostatnich 3s.")
    else:
        issues.append(f"✅ LAJKI: {like_rate:.2f}% — dobry wynik!")

    # Views (dla nowych filmów < 7 dni)
    if views < 100:
        score -= 20
        issues.append(f"❌ WIDOCZNOŚĆ: {views} wyświetleń. YouTube nie boostu­je. Sprawdź: tagi, miniatura, opis.")
    elif views < 500:
        score -= 10
        issues.append(f"🟡 WIDOCZNOŚĆ: {views} wyświetleń. Average dla nowego kanału to 200-1000.")

    # AVD (Average View Duration)
    if analytics:
        avd = analytics.get("avg_view_duration_s", 0)
        avd_pct = analytics.get("avg_view_pct", 0)

        if avd > 0:
            pct_of_dur = (avd / duration_s * 100) if duration_s > 0 else avd_pct
            if pct_of_dur < 40:
                score -= 30
                issues.append(
                    f"❌ RETENCJA (AVD): {avd:.1f}s = {pct_of_dur:.0f}% filmu. "
                    f"Widz wyskakuje wcześnie. Popraw HOOK (pierwsze 0.5s) i LOOP na końcu!"
                )
            elif pct_of_dur < 60:
                score -= 15
                issues.append(
                    f"🟡 RETENCJA (AVD): {avd:.1f}s = {pct_of_dur:.0f}% filmu. "
                    f"Cel: 70%+. Skróć mniej ciekawe fragmenty środkowe."
                )
            else:
                issues.append(f"✅ RETENCJA: {avd:.1f}s = {pct_of_dur:.0f}% — świetnie!")

        subs = analytics.get("subs_gained", 0)
        if subs == 0 and views > 50:
            score -= 10
            issues.append("🟡 SUBSKRYBENCI: 0 nowych z tego Shorta. Brak wyraźnego CTA do subskrybowania.")

    return max(0, min(100, score)), issues


def score_content_structure(title: str, description: str = "") -> tuple[int, list]:
    """Ocenia strukturę contentu na podstawie tytułu i opisu."""
    score = 100
    issues = []
    tl = title.lower()
    dl = description.lower()

    # Hook pattern: pytanie lub stwierdzenie szokujące
    has_question = "?" in title
    has_exclamation = "!" in title
    if not has_question and not has_exclamation:
        score -= 10
        issues.append("🟡 HOOK: Brak pytania (?) lub wykrzyknika (!) w tytule. Pytanie = 2x wyższy CTR.")

    # Dark Psychology format check
    dark_formats = [
        r"\d+\s*(dark|covert|hidden|secret|signs|tricks|ways|tactics|methods)",
        r"(dark|covert|hidden|secret)\s*(psychology|manipulation|body language|trick)",
    ]
    format_match = any(re.search(p, tl) for p in dark_formats)
    if not format_match:
        score -= 20
        issues.append(
            "❌ FORMAT: Tytuł nie pasuje do sprawdzonego formatu Dark Psychology.\n"
            "   Przykłady: '3 Dark Psychology Tricks' / 'Hidden Body Language Signal' / 'Covert Manipulation Tactic'"
        )

    # Emoji w opisie
    if description and not any(c in description for c in ["🧠","💀","⚠️","🔥","❤️","👇","📌"]):
        score -= 5
        issues.append("🟡 OPIS: Brak emoji w opisie. Emoji zwiększają CTR i czytelność.")

    # Hashtagi w opisie
    if "#" not in description:
        score -= 10
        issues.append("🟡 OPIS: Brak hashtagów w opisie (#darkpsychology #shorts #manipulation).")

    return max(0, min(100, score)), issues


# ═══════════════════════════════════════════════════════════
#  RAPORT KOŃCOWY
# ═══════════════════════════════════════════════════════════
def generate_improvement_plan(video_data: dict) -> list:
    """
    Na podstawie scoringu generuje posortowaną listę priorytetów:
    KRYTYCZNE → WAŻNE → DOBRE PRAKTYKI
    """
    all_issues = (
        video_data["title_issues"]
        + video_data["engagement_issues"]
        + video_data["content_issues"]
    )

    critical = [i for i in all_issues if i.startswith("❌")]
    important = [i for i in all_issues if i.startswith("🟡")]
    good      = [i for i in all_issues if i.startswith("✅")]

    plan = []
    if critical:
        plan.append(f"\n  {R}▼ KRYTYCZNE (napraw TERAZ):{RST}")
        for c in critical:
            plan.append(f"     {c}")
    if important:
        plan.append(f"\n  {Y}▼ WAŻNE (następny film):{RST}")
        for i_item in important:
            plan.append(f"     {i_item}")
    if good:
        plan.append(f"\n  {G}▼ CO DZIAŁA DOBRZE:{RST}")
        for g in good:
            plan.append(f"     {g}")

    return plan


def bar(value: float, max_val: float = 100, width: int = 20, color: str = G) -> str:
    """Rysuje prosty pasek postępu."""
    filled = int((value / max_val) * width) if max_val > 0 else 0
    empty  = width - filled
    return f"{color}{'█' * filled}{DIM}{'░' * empty}{RST} {value:.0f}%"


def print_video_report(idx: int, v: dict):
    views    = v["views"]
    likes    = v["likes"]
    comments = v["comments"]
    dur      = v["duration_s"]
    a        = v.get("analytics", {})

    title_score      = v["title_score"]
    engagement_score = v["engagement_score"]
    content_score    = v["content_score"]
    overall          = int((title_score + engagement_score + content_score) / 3)

    grade_color = G if overall >= 70 else (Y if overall >= 40 else R)

    print(f"\n{'─'*62}")
    print(f"{C}  #{idx} — {W}{v['title'][:58]}{RST}")
    print(f"{'─'*62}")
    print(f"  🔗 https://youtube.com/shorts/{v['id']}")
    print(f"  📅 Opublikowano: {v['published'][:10]}  |  ⏱ Długość: {dur}s")
    print()

    print(f"  {B}━━ STATYSTYKI YT DATA API ━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}")
    print(f"  👁  Wyświetlenia : {W}{views:,}{RST}")
    print(f"  ❤️  Lajki        : {W}{likes:,}{RST}  ({likes/views*100:.2f}% like-rate)" if views else f"  ❤️  Lajki        : {likes}")
    print(f"  💬 Komentarze   : {W}{comments:,}{RST}")

    if a:
        print()
        print(f"  {B}━━ STATYSTYKI ANALYTICS (YTA API) ━━━━━━━━━━━━━━━━━{RST}")
        avd = a.get("avg_view_duration_s", 0)
        avd_pct = a.get("avg_view_pct", 0)
        shares  = a.get("shares", 0)
        subs    = a.get("subs_gained", 0)
        views_a = a.get("views_analytics", views)
        print(f"  ⏱  AVD (śr. czas oglądania)  : {W}{avd:.1f}s{RST} ({avd_pct:.1f}% retencji)")
        print(f"  📊 Wyśw. (Analytics)         : {W}{views_a:,}{RST}")
        print(f"  🔁 Udostępnienia             : {W}{shares}{RST}")
        print(f"  ➕ Nowi subskrybenci         : {W}{subs}{RST}")

    print()
    print(f"  {B}━━ SCORING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}")
    print(f"  Tytuł/CTR      : {bar(title_score)}")
    print(f"  Zaangażowanie  : {bar(engagement_score)}")
    print(f"  Struktura      : {bar(content_score)}")
    print(f"  {grade_color}  OGÓLNY WYNIK   : {overall}/100{RST}")

    plan = generate_improvement_plan(v)
    print()
    print(f"  {M}━━ CO POPRAWIĆ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RST}")
    for line in plan:
        print(line)


# ═══════════════════════════════════════════════════════════
#  GŁÓWNA LOGIKA
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Analizuje N najnowszych Shortsów z kanału YT.")
    parser.add_argument("--profil", default="dark_mindset", help="Nazwa profilu (accounts/<name>_token.pickle)")
    parser.add_argument("--top",    type=int, default=2,    help="Ile najnowszych Shortsów analizować (domyślnie 2)")
    parser.add_argument("--dni",    type=int, default=28,   help="Okres dla Analytics (dni wstecz, domyślnie 28)")
    args = parser.parse_args()

    TARGET = args.top
    DAYS   = args.dni

    print(f"\n{'═'*62}")
    print(f"{C}  🎬 LATEST SHORTS ANALYZER — {args.profil.upper()}{RST}")
    print(f"  Analizuję: {TARGET} najnowsze Shortsy  |  Analytics: ostatnie {DAYS} dni")
    print(f"{'═'*62}")

    # 1. Auth
    print(f"\n{DIM}🔐 Autoryzacja...{RST}")
    yt, yta = get_service(args.profil)

    # 2. Dane kanału
    channel_id, channel_name, ch_stats = get_channel_id(yt)
    total_subs  = int(ch_stats.get("subscriberCount", 0))
    total_views = int(ch_stats.get("viewCount", 0))
    total_vids  = int(ch_stats.get("videoCount", 0))

    print(f"\n{G}✅ Kanał: {W}{channel_name}{RST}")
    print(f"   👥 Subskrybenci: {total_subs:,}   |  👁 Łączne wyśw: {total_views:,}  |  🎬 Filmów: {total_vids}")

    # 3. Pobierz najnowsze filmy
    print(f"\n{DIM}🔍 Pobieranie ostatnich filmów...{RST}")
    playlist_id = get_uploads_playlist(yt, channel_id)
    # Pobieramy 20, bo nie wszystkie muszą być Shortsami
    raw_items = get_latest_videos(yt, playlist_id, count=20)

    video_ids = [item["contentDetails"]["videoId"] for item in raw_items]
    details   = get_video_details(yt, video_ids)

    # Filtruj tylko Shortsy (≤ 60s) KTÓRE SĄ JUŻ OPUBLIKOWANE (public)
    shorts = []
    skipped_private = 0
    for v in details:
        privacy = v.get("status", {}).get("privacyStatus", "unknown")
        if privacy != "public":
            pub_at = v["snippet"].get("publishedAt", "?")
            title_short = v["snippet"]["title"][:45]
            print(f"  {Y}⏭  Pomijam [{privacy.upper()}]: '{title_short}' (zaplanowany/prywatny){RST}")
            skipped_private += 1
            continue
        dur_s = parse_duration_seconds(v["contentDetails"]["duration"])
        if dur_s <= 63:   # margines 3s
            shorts.append(v)
        if len(shorts) >= TARGET:
            break

    if skipped_private > 0:
        print(f"  {DIM}→ Pominięto {skipped_private} film(ów) zaplanowanych/prywatnych.{RST}")

    if not shorts:
        print(f"{R}❌ Nie znaleziono Shortsów (filmów ≤ 60s) na kanale!{RST}")
        sys.exit(0)

    print(f"{G}✅ Znaleziono {len(shorts)} Shortsów do analizy.{RST}")

    # 4. Analiza każdego Shorta
    results = []
    for idx, v in enumerate(shorts[:TARGET], start=1):
        vid_id    = v["id"]
        title     = v["snippet"]["title"]
        desc      = v["snippet"].get("description", "")
        published = v["snippet"]["publishedAt"]
        stats     = v.get("statistics", {})
        views     = int(stats.get("viewCount", 0))
        likes     = int(stats.get("likeCount", 0))
        comments  = int(stats.get("commentCount", 0))
        dur_s     = parse_duration_seconds(v["contentDetails"]["duration"])

        print(f"\n{DIM}📊 [{idx}/{len(shorts[:TARGET])}] Pobieranie Analytics dla: {title[:50]}...{RST}")
        analytics = get_analytics(yta, channel_id, vid_id, days_back=DAYS)

        # Scoring
        ts, t_issues = score_title(title)
        es, e_issues = score_engagement(views, likes, comments, dur_s, analytics)
        cs, c_issues = score_content_structure(title, desc)

        record = {
            "id": vid_id,
            "title": title,
            "description": desc[:300],
            "published": published,
            "duration_s": dur_s,
            "views": views,
            "likes": likes,
            "comments": comments,
            "analytics": analytics,
            "title_score": ts,
            "engagement_score": es,
            "content_score": cs,
            "overall_score": int((ts + es + cs) / 3),
            "title_issues": t_issues,
            "engagement_issues": e_issues,
            "content_issues": c_issues,
        }
        results.append(record)

    # 5. Drukuj raporty
    for idx, r in enumerate(results, start=1):
        print_video_report(idx, r)

    # 6. Globalne wnioski (porównanie obu filmów)
    if len(results) >= 2:
        r1, r2 = results[0], results[1]
        print(f"\n{'═'*62}")
        print(f"{C}  📈 PORÓWNANIE OBU SHORTSÓW{RST}")
        print(f"{'═'*62}")

        delta_score = r1["overall_score"] - r2["overall_score"]
        winner = r1 if r1["overall_score"] >= r2["overall_score"] else r2
        loser  = r2 if winner is r1 else r1

        print(f"\n  {G}🏆 Lepszy film: {W}{winner['title'][:55]}{RST}")
        print(f"     Wynik: {winner['overall_score']}/100  |  Views: {winner['views']}  |  Likes: {winner['likes']}")
        print(f"\n  {R}📉 Słabszy film: {W}{loser['title'][:55]}{RST}")
        print(f"     Wynik: {loser['overall_score']}/100  |  Views: {loser['views']}  |  Likes: {loser['likes']}")

        # Co zrobiło różnicę
        print(f"\n  {M}━━ CO BYŁO LEPSZE W WYGRYWAJĄCYM ━━━━━━━━━━━━━━━━━{RST}")
        metrics = [
            ("Tytuł/CTR score",   r1["title_score"],      r2["title_score"]),
            ("Zaangażowanie",     r1["engagement_score"],  r2["engagement_score"]),
            ("Struktura treści",  r1["content_score"],     r2["content_score"]),
            ("Views",            r1["views"],             r2["views"]),
            ("Likes",            r1["likes"],             r2["likes"]),
        ]
        for label, val1, val2 in metrics:
            if val1 > val2:
                icon = G + "↑" + RST
                comment = f"#{1} lepszy o {val1-val2}"
            elif val2 > val1:
                icon = R + "↓" + RST
                comment = f"#{2} lepszy o {val2-val1}"
            else:
                icon = Y + "=" + RST
                comment = "Równe"
            print(f"    {icon} {label:<22}: #{1}={val1}  #{2}={val2}  → {comment}")

    # 7. TOP rekomendacje dla NASTĘPNEGO Shorta
    print(f"\n{'═'*62}")
    print(f"{M}  🚀 PLAN AKCJI: CO ZROBIĆ PRZY NASTĘPNYM SHORCIE{RST}")
    print(f"{'═'*62}")

    # Zbierz wszystkie ❌ krytyczne z obu filmów
    all_criticals = []
    all_importants = []
    for r in results:
        for issue in r["title_issues"] + r["engagement_issues"] + r["content_issues"]:
            if issue.startswith("❌") and issue not in all_criticals:
                all_criticals.append(issue)
            elif issue.startswith("🟡") and issue not in all_importants:
                all_importants.append(issue)

    unique_criticals = list(dict.fromkeys(all_criticals))
    unique_importants = list(dict.fromkeys(all_importants))

    print(f"\n  {R}PRIORYTET 1 — ABSOLUTNE MINIMUM:{RST}")
    if unique_criticals:
        for c in unique_criticals:
            print(f"    {c}")
    else:
        print(f"    {G}✅ Brak krytycznych problemów! Utrzymuj ten poziom.{RST}")

    print(f"\n  {Y}PRIORYTET 2 — OPTYMALIZACJA:{RST}")
    if unique_importants:
        for i in unique_importants:
            print(f"    {i}")
    else:
        print(f"    {G}✅ Wszystko zoptymalizowane!{RST}")

    print(f"\n  {G}━━ KONKRETNY SZABLON TYTUŁU NA NASTĘPNY FILM ━━━━━━━━{RST}")
    examples = [
        "⚠️ 3 Dark Psychology Tricks They Use Against You #shorts",
        "🧠 5 Covert Signs Someone is Manipulating You #shorts",
        "💀 The Silent Power Move Nobody Talks About #shorts",
        "🔥 Warning: This Body Language Trick Controls People #shorts",
    ]
    for ex in examples[:2]:
        print(f"    → {W}{ex}{RST}")

    # 8. Zapis raportu JSON
    report_file = f"shorts_analysis_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": args.profil,
        "channel": channel_name,
        "channel_id": channel_id,
        "videos_analyzed": len(results),
        "results": [
            {k: v for k, v in r.items() if k not in ("title_issues", "engagement_issues", "content_issues")}
            for r in results
        ],
        "critical_issues": unique_criticals,
        "important_issues": unique_importants,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*62}")
    print(f"{G}  ✅ Analiza zakończona! Raport zapisany: {W}{report_file}{RST}")
    print(f"{'═'*62}\n")


if __name__ == "__main__":
    main()
