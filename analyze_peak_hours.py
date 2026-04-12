"""
analyze_peak_hours.py — Analizator Szczytowych Godzin Trafficu
==============================================================
Weryfikuje kiedy shortsy osiągają największy ruch na podstawie:
  1. Danych z YouTube Analytics API (views by hour/day)
  2. Historii publikacji + wyświetleń (korelacja godziny publikacji z views)
  3. Velocity score (views/hour) dla filmów opublikowanych w różnych porach
  4. Zapisuje optymalne godziny do adaptation_directive.json

Użycie:
    python analyze_peak_hours.py                    # pełna analiza
    python analyze_peak_hours.py --days 30          # ostatnie 30 dni
    python analyze_peak_hours.py --update-directive # aktualizuje directive JSON automatycznie
"""

import os
import sys
import json
import pickle
import re
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    _GOOGLE_AVAILABLE = True
except ImportError:
    _GOOGLE_AVAILABLE = False

G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"

PROFILE_NAME       = "dark_mindset"
TOKEN_FILE         = os.path.join("accounts", f"{PROFILE_NAME}_token.pickle")
CLIENT_SECRETS     = "client_secret.json"
DIRECTIVE_FILE     = "adaptation_directive.json"
SMART_ANALYSIS_DIR = "."
DAYS_BACK          = 90  # domyślny zakres analizy

DAYS_PL = {0: "Poniedziałek", 1: "Wtorek", 2: "Środa",
           3: "Czwartek", 4: "Piątek", 5: "Sobota", 6: "Niedziela"}
DAYS_SHORT = {0: "Pn", 1: "Wt", 2: "Śr", 3: "Czw", 4: "Pt", 5: "Sob", 6: "Nd"}


# ─── Auth ─────────────────────────────────────────────────────────────────────
def _load_credentials():
    if not _GOOGLE_AVAILABLE:
        return None
    if not os.path.exists(TOKEN_FILE):
        print(f"{Y}⚠️  Brak tokenu: {TOKEN_FILE}{X}")
        return None
    try:
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)
        return creds
    except Exception as e:
        print(f"{Y}⚠️  Błąd credentials: {e}{X}")
        return None


def get_yt_client():
    creds = _load_credentials()
    if not creds:
        return None
    return build("youtube", "v3", credentials=creds)


def get_analytics_client():
    creds = _load_credentials()
    if not creds:
        return None
    try:
        return build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        print(f"{Y}⚠️  Analytics API niedostępny: {e}{X}")
        return None


# ─── Metoda 1: YouTube Analytics API — views by day ───────────────────────────
def fetch_analytics_hourly(analytics, days_back: int = 90) -> dict:
    """
    YouTube Analytics API v2 NIE udostępnia 'hour' jako wymiaru dla kanałów.
    Zamiast tego pobieramy views per day i mapujemy na wzorzec ruchu tygodniowego.
    Zwraca {weekday_int: total_views, ...}
    """
    if not analytics:
        return {}

    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    print(f"\n{C}📊 Analytics API: views per dzień tygodnia (ostatnie {days_back} dni)...{X}")

    weekday_views = defaultdict(int)
    weekday_counts = defaultdict(int)

    try:
        # Pobierz views per dzień
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=today,
            metrics="views,estimatedMinutesWatched",
            dimensions="day",
            maxResults=365,
        ).execute()

        rows = resp.get("rows", [])
        for row in rows:
            day_str = row[0]  # format: "2026-03-28"
            views = int(row[1])
            try:
                dt = datetime.strptime(day_str, "%Y-%m-%d")
                wd = dt.weekday()
                weekday_views[wd] += views
                weekday_counts[wd] += 1
            except Exception:
                pass

        if weekday_views:
            print(f"  {G}✅ Dane analityczne pobrane dla {len(rows)} dni.{X}")

        # Normalizuj do avg/dzień
        avg_weekday = {
            wd: round(weekday_views[wd] / max(weekday_counts[wd], 1))
            for wd in weekday_views
        }
        return avg_weekday

    except Exception as e:
        err = str(e)
        if "insufficientPermissions" in err or "403" in err:
            print(f"  {Y}⚠️  Brak scope Analytics API — uruchom authorize_channel.py{X}")
        else:
            print(f"  {Y}⚠️  Analytics API error: {e}{X}")
        return {}


def fetch_analytics_by_video(analytics, yt, days_back: int = 90) -> list:
    """
    Pobiera listę filmów z Analytics — views, AVD, estimated minutes.
    Metoda alternatywna gdy 'hour' jest niedostępny.
    """
    if not analytics or not yt:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    print(f"\n{C}📊 Analytics API: pobieranie per-video metrics...{X}")
    try:
        resp = analytics.reports().query(
            ids="channel==MINE",
            startDate=start,
            endDate=today,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            dimensions="video",
            sort="-views",
            maxResults=50,
        ).execute()

        videos_analytics = []
        for row in resp.get("rows", []):
            videos_analytics.append({
                "video_id": row[0],
                "views": int(row[1]),
                "est_minutes": float(row[2]),
                "avg_view_s": round(float(row[3]), 1),
                "avg_view_pct": round(float(row[4]), 1),
            })

        print(f"  {G}✅ Dane dla {len(videos_analytics)} filmów pobrane.{X}")
        return videos_analytics

    except Exception as e:
        print(f"  {Y}⚠️  Błąd per-video analytics: {e}{X}")
        return []


# ─── Metoda 2: Historia lokalnych smart_analysis JSONów ────────────────────────
def load_smart_analysis_history(days_back: int = 30) -> list:
    """
    Laduje dane z lokalnych plików smart_analysis_*.json
    Zawierają one snapshoty kanału robione codziennie.
    """
    videos_all = []
    cutoff = datetime.now() - timedelta(days=days_back)

    for fname in os.listdir(SMART_ANALYSIS_DIR):
        if not fname.startswith("smart_analysis_") or not fname.endswith(".json"):
            continue
        try:
            date_str = fname.replace("smart_analysis_", "").replace(".json", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                continue
        except Exception:
            continue

        try:
            with open(os.path.join(SMART_ANALYSIS_DIR, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            for v in data.get("top_5", []) + data.get("last_2", []):
                if v not in videos_all:
                    videos_all.append(v)
        except Exception:
            pass

    # Deduplikacja po ID
    seen = set()
    unique = []
    for v in videos_all:
        vid_id = v.get("id") or v.get("video_id")
        if vid_id and vid_id not in seen:
            seen.add(vid_id)
            unique.append(v)

    return unique


# ─── Metoda 3: Korelacja godziny publikacji z wyświetleniami ──────────────────
def analyze_publish_time_correlation(videos: list) -> dict:
    """
    Dla każdej godziny publikacji (UTC) liczy średnią liczbę wyświetleń.
    Zwraca słownik: {hour_utc: {"avg_views": X, "count": N, "total_views": Y}}
    """
    hour_data = defaultdict(lambda: {"total_views": 0, "count": 0, "velocities": []})

    for v in videos:
        pub_str = v.get("published", "")
        views = v.get("views", 0)
        velocity = v.get("velocity", 0)

        if not pub_str:
            continue

        try:
            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            hour = pub_dt.hour
            hour_data[hour]["total_views"] += views
            hour_data[hour]["count"] += 1
            if velocity > 0:
                hour_data[hour]["velocities"].append(velocity)
        except Exception:
            pass

    result = {}
    for hour, d in hour_data.items():
        count = d["count"]
        if count == 0:
            continue
        avg_vel = (sum(d["velocities"]) / len(d["velocities"])) if d["velocities"] else 0
        result[hour] = {
            "avg_views": round(d["total_views"] / count),
            "count": count,
            "total_views": d["total_views"],
            "avg_velocity": round(avg_vel, 2),
        }

    return result


def analyze_weekday_performance(videos: list) -> dict:
    """Korelacja dnia tygodnia publikacji z wyświetleniami."""
    weekday_data = defaultdict(lambda: {"total_views": 0, "count": 0})

    for v in videos:
        pub_str = v.get("published", "")
        views = v.get("views", 0)
        if not pub_str:
            continue
        try:
            pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            wd = pub_dt.weekday()
            weekday_data[wd]["total_views"] += views
            weekday_data[wd]["count"] += 1
        except Exception:
            pass

    result = {}
    for wd, d in weekday_data.items():
        count = d["count"]
        if count == 0:
            continue
        result[wd] = {
            "avg_views": round(d["total_views"] / count),
            "count": count,
            "total_views": d["total_views"],
            "day_name": DAYS_PL[wd],
            "day_short": DAYS_SHORT[wd],
        }

    return result


# ─── Metoda 4: Fetch live video data from YT API ──────────────────────────────
def fetch_channel_videos_with_timing(yt, max_videos: int = 100) -> list:
    """
    Pobiera filmy z kanału z pełnymi danymi czasowymi.
    Oblicza velocity (views/h od publikacji) dla korelacji godzin.
    """
    if not yt:
        return []

    print(f"\n{C}📡 Pobieranie filmów z kanału (max {max_videos})...{X}")

    try:
        ch_res = yt.channels().list(part="contentDetails,statistics", mine=True).execute()
        uploads = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        video_ids = []
        next_page = None
        while len(video_ids) < max_videos:
            pl = yt.playlistItems().list(
                part="contentDetails", playlistId=uploads,
                maxResults=50, pageToken=next_page
            ).execute()
            for item in pl.get("items", []):
                video_ids.append(item["contentDetails"]["videoId"])
            next_page = pl.get("nextPageToken")
            if not next_page:
                break

        videos = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            details = yt.videos().list(
                part="snippet,statistics,contentDetails", id=",".join(batch)
            ).execute()

            for v in details.get("items", []):
                stats = v.get("statistics", {})
                snippet = v.get("snippet", {})
                pub_str = snippet.get("publishedAt", "")
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))

                age_h = 1.0
                if pub_str:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    age_h = max(1.0, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600)

                velocity = round(views / age_h, 2)
                engagement = round((likes + comments) / max(views, 1) * 100, 2)

                videos.append({
                    "id": v["id"],
                    "title": snippet.get("title", ""),
                    "published": pub_str,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "velocity": velocity,
                    "engagement": engagement,
                    "age_hours": round(age_h, 1),
                })

        print(f"  {G}✅ Pobrano {len(videos)} filmów.{X}")
        videos.sort(key=lambda x: x["views"], reverse=True)
        return videos

    except Exception as e:
        print(f"  {R}❌ Błąd pobierania filmów: {e}{X}")
        return []


# ─── Wyświetlanie raportu ──────────────────────────────────────────────────────
def _bar(value: float, max_value: float, width: int = 30, char: str = "█") -> str:
    """Rysuje pasek postępu proporcjonalny do wartości."""
    if max_value <= 0:
        return "." * width
    filled = min(width, int(value / max_value * width))
    return char * filled + "." * (width - filled)


def print_hourly_report(hour_corr: dict, weekday_perf: dict,
                        analytics_weekday: dict, videos_analytics: list):
    """Wyświetla kompleksowy raport godzin i dni."""

    print(f"\n{C}{'='*70}{X}")
    print(f"{B}⏰ ANALIZA SZCZYTOWYCH GODZIN TRAFFICU — Dark Mindset Channel{X}")
    print(f"{C}{'='*70}{X}")

    # ── Sekcja 1: Korelacja godziny publikacji z wyświetleniami ──
    if hour_corr:
        print(f"\n{C}── 1. GODZINY PUBLIKACJI vs WYŚWIETLENIA (UTC) ─────────────────{X}")
        print(f"   (korelacja: o której godzinie opublikowane filmy mają średnio więcej views)\n")

        max_avg = max(d["avg_views"] for d in hour_corr.values()) or 1
        sorted_hours = sorted(hour_corr.items(), key=lambda x: x[1]["avg_views"], reverse=True)

        # Top 5 godzin
        print(f"  {'GODZ UTC':>8} {'GODZ PL':>8} {'FILMY':>6} {'AVG VIEWS':>10} {'VELOCITY':>10}  ROZKŁAD")
        for h, d in sorted_hours[:8]:
            is_best = h == sorted_hours[0][0]
            col = G if is_best else (Y if sorted_hours.index((h, d)) < 3 else X)
            bar = _bar(d["avg_views"], max_avg, width=20)
            tag = " ◄ OPTIMUM" if is_best else ""
            pl_h = (h + 1) % 24  # CET (+1)
            print(f"  {col}{h:>6}:00 {pl_h:>7}:00 {d['count']:>6} {d['avg_views']:>10,.0f} "
                  f"{d['avg_velocity']:>10.1f}  {bar}{tag}{X}")

        best_hour_utc = sorted_hours[0][0]
        best_hour_pl = (best_hour_utc + 1) % 24
        print(f"\n  {G}{B}🏆 NAJLEPSZA GODZINA: {best_hour_utc:02d}:00 UTC = {best_hour_pl:02d}:00 PL{X}")
    else:
        best_hour_utc = 18  # fallback
        print(f"\n  {Y}⚠️  Brak danych godzinowych z historii (za mało filmów).{X}")
        print(f"  Używam fallback: 18:00 UTC = 19:00 PL")

    # ── Sekcja 2: Dzień tygodnia (z historii) ──
    if weekday_perf:
        print(f"\n{C}── 2. DZIEŃ TYGODNIA vs WYŚWIETLENIA (historia publikacji) ─────{X}\n")
        max_wd = max(d["avg_views"] for d in weekday_perf.values()) or 1
        sorted_wd = sorted(weekday_perf.items(), key=lambda x: x[1]["avg_views"], reverse=True)

        print(f"  {'DZIEŃ':>14} {'FILMY':>6} {'AVG VIEWS':>10}  ROZKŁAD")
        for wd, d in sorted_wd:
            is_best = wd == sorted_wd[0][0]
            col = G if is_best else (Y if sorted_wd.index((wd, d)) < 2 else X)
            bar = _bar(d["avg_views"], max_wd, width=22)
            tag = " ◄ BEST" if is_best else ""
            print(f"  {col}{d['day_name']:>14} {d['count']:>6} {d['avg_views']:>10,.0f}  {bar}{tag}{X}")

        best_wd = sorted_wd[0][0]
        print(f"\n  {G}{B}🏆 NAJLEPSZY DZIEŃ: {DAYS_PL[best_wd]} ({DAYS_SHORT[best_wd]}){X}")
    else:
        best_wd = 2  # fallback: środa

    # ── Sekcja 3: Analytics API (tygodniowy) ──
    if analytics_weekday:
        print(f"\n{C}── 3. ANALYTICS API — VIEWS PER DZIEŃ TYGODNIA (avg) ───────────{X}\n")
        max_av = max(analytics_weekday.values()) or 1
        sorted_av = sorted(analytics_weekday.items(), key=lambda x: x[1], reverse=True)

        print(f"  {'DZIEŃ':>14} {'AVG VIEWS':>10}  ROZKŁAD")
        for wd, avg_v in sorted_av:
            is_best = wd == sorted_av[0][0]
            col = G if is_best else (Y if sorted_av.index((wd, avg_v)) < 2 else X)
            day_name = DAYS_PL.get(wd, f"Dzień {wd}")
            bar = _bar(avg_v, max_av, width=22)
            tag = " ◄ PEAK" if is_best else ""
            print(f"  {col}{day_name:>14} {avg_v:>10,.0f}  {bar}{tag}{X}")

    # ── Sekcja 4: Top filmy i ich timing ──
    if videos_analytics:
        print(f"\n{C}── 4. PER-VIDEO ANALYTICS (top performers) ─────────────────────{X}\n")
        print(f"  {'VIEWS':>8} {'AVD':>6} {'AVD%':>6}  TYTUŁ")
        for v in videos_analytics[:10]:
            avd = v.get("avg_view_s", 0)
            pct = v.get("avg_view_pct", 0)
            vid_title = v.get("title", v.get("video_id", "?"))[:50]
            col = G if pct >= 60 else (Y if pct >= 40 else R)
            print(f"  {v['views']:>8,} {avd:>5.0f}s {col}{pct:>5.0f}%{X}  {vid_title}")

    # ── Podsumowanie rekomendacji ──
    best_hour_pl_final = (best_hour_utc + 1) % 24
    print(f"\n{C}{'='*70}{X}")
    print(f"{B}📋 REKOMENDACJE OPTYMALNE:{X}")
    print(f"  🕐 Film 1 (natychmiastowy): rano {best_hour_pl_final - 8 if best_hour_pl_final > 8 else best_hour_pl_final}:00 PL")
    print(f"  🕐 Film 2 (zaplanowany):   {best_hour_pl_final:02d}:00 PL = {best_hour_utc:02d}:00 UTC")
    print(f"  📅 Najlepszy dzień: {DAYS_PL.get(best_wd, '?')}")
    print(f"\n  Dodaj do adaptation_directive.json:")
    print(f"  \"best_publish_hour_utc\": {best_hour_utc}")

    return best_hour_utc, best_wd


# ─── Update directive ─────────────────────────────────────────────────────────
def update_directive(best_hour_utc: int, best_weekday: int):
    """Aktualizuje adaptation_directive.json z optymalną godziną publikacji."""
    data = {}
    if os.path.exists(DIRECTIVE_FILE):
        try:
            with open(DIRECTIVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    old_hour = data.get("best_publish_hour_utc", "brak")
    data["best_publish_hour_utc"] = best_hour_utc
    data["best_publish_weekday"] = best_weekday
    data["peak_analysis_date"] = datetime.now().isoformat()

    # Zaktualizuj też tekst dyrektywy
    directive_text = data.get("directive", "")
    # Dodaj info o godzinie do dyrektywy jeśli jej tam nie ma
    hour_marker = "PEAK AKTYWNOŚCI"
    pl_hour = (best_hour_utc + 1) % 24
    new_segment = (f"OPTYMALNY CZAS PUBLIKACJI (z analizy velocity): {best_hour_utc:02d}:00 UTC"
                   f" = {pl_hour:02d}:00 PL — Wrzucaj film 2 o tej porze dla max zasięgów!")

    if hour_marker not in directive_text:
        data["directive"] = directive_text + " | " + new_segment if directive_text else new_segment

    with open(DIRECTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"\n{G}✅ adaptation_directive.json zaktualizowany:{X}")
    print(f"   best_publish_hour_utc: {old_hour} → {best_hour_utc} ({pl_hour:02d}:00 PL)")
    print(f"   best_publish_weekday:  {DAYS_PL.get(best_weekday, '?')}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Analizator szczytowych godzin trafficu")
    parser.add_argument("--days", type=int, default=DAYS_BACK,
                        help=f"Ile dni wstecz analizować (domyślnie {DAYS_BACK})")
    parser.add_argument("--update-directive", action="store_true",
                        help="Automatycznie zaktualizuj adaptation_directive.json")
    parser.add_argument("--offline", action="store_true",
                        help="Tylko z lokalnych smart_analysis JSONów (bez API)")
    args = parser.parse_args()

    print(f"\n{B}{'='*70}")
    print(f"  ⏰ ANALYZER SZCZYTOWYCH GODZIN TRAFFICU")
    print(f"  Profil: {PROFILE_NAME} | Zakres: {args.days} dni")
    print(f"{'='*70}{X}")

    yt = None
    analytics = None
    if not args.offline:
        yt = get_yt_client()
        analytics = get_analytics_client()

    # ── Dane 1: Live z YT API ──
    live_videos = []
    if yt and not args.offline:
        live_videos = fetch_channel_videos_with_timing(yt, max_videos=100)

    # ── Dane 2: Lokalne snapshoty ──
    snapshot_videos = load_smart_analysis_history(days_back=args.days)
    if snapshot_videos:
        print(f"\n{G}📂 Załadowano {len(snapshot_videos)} filmów ze snapshot'ów lokalnych.{X}")

    # Połącz źródła — live ma priorytet
    all_videos = live_videos if live_videos else snapshot_videos
    if not all_videos:
        print(f"{R}❌ Brak danych o filmach. Uruchom agenta przynajmniej raz.{X}")
        sys.exit(1)

    # ── Dane 3: Analytics API ──
    analytics_weekday = {}
    if analytics and not args.offline:
        analytics_weekday = fetch_analytics_hourly(analytics, days_back=args.days)

    # ── Dane 4: Per-video analytics ──
    videos_analytics = []
    if analytics and not args.offline:
        raw = fetch_analytics_by_video(analytics, yt, days_back=args.days)
        # Wzbogać o tytuły z live_videos
        id_to_title = {v["id"]: v["title"] for v in all_videos}
        for v in raw:
            v["title"] = id_to_title.get(v["video_id"], v["video_id"])
        videos_analytics = raw

    # ── Analiza korelacji ──
    hour_corr    = analyze_publish_time_correlation(all_videos)
    weekday_perf = analyze_weekday_performance(all_videos)

    # ── Raport ──
    best_hour_utc, best_wd = print_hourly_report(
        hour_corr, weekday_perf, analytics_weekday, videos_analytics
    )

    # ── Aktualizacja directive ──
    if args.update_directive:
        update_directive(best_hour_utc, best_wd)
    else:
        print(f"\n{Y}💡 Dodaj --update-directive aby zapisać optymalną godzinę automatycznie.{X}")


if __name__ == "__main__":
    main()
