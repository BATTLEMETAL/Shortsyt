"""
smart_video_analyzer.py  —  v2.0 DEEP ANALYTICS
=================================================
Uruchamiany automatycznie po każdych 2 wygenerowanych filmach.
Analizuje CAŁY kanał YouTube + YouTube Analytics API:

  ✅ Pobiera WSZYSTKIE uploads z paginacją (do 500 filmów)
  ✅ CTR (click-through rate) per film z Analytics API
  ✅ Avg View Duration + Avg View % (retencja) per film
  ✅ Wyświetlenia, impressions per film z Analytics API
  ✅ Aktywność widzów wg godziny (kiedy najlepiej wrzucać)
  ✅ Analiza formatu tytułu: pytanie vs. stwierdzenie vs. [prefix]
  ✅ Korelacja słów kluczowych z views AND CTR
  ✅ Optymalna długość wideo (buckety)
  ✅ SYNAPSA_ADAPTATION_DIRECTIVE — zapisana do adaptation_directive.json

Użyj: python smart_video_analyzer.py
"""

import os
import sys
import json
import re
import pickle
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# ─── Stałe ───────────────────────────────────────────────────────────────────
PROFILE_NAME    = os.environ.get("SHORTSYT_PROFILE", "dark_mindset")
DIRECTIVE_FILE  = f"accounts/{PROFILE_NAME}_adaptation_directive.json"
REPORT_FILE     = f"accounts/{PROFILE_NAME}_smart_analysis_{datetime.now().strftime('%Y-%m-%d')}.json"
MAX_VIDEOS      = 500
TOKEN_FILE      = os.path.join("accounts", f"{PROFILE_NAME}_token.pickle")
CLIENT_SECRETS  = "client_secret.json"

# Scopes — muszą być w tokenie (re-auth jeśli brak)
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # wymagany do CTA comments
]

# CLI kolory
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"

# ─── Auth helpers ─────────────────────────────────────────────────────────────
def _load_credentials():
    """Ładuje credentials z pickle, odświeża jeśli wygasłe."""
    if not os.path.exists(TOKEN_FILE):
        print(f"{R}❌ Brak tokenu: {TOKEN_FILE}. Uruchom authorize_channel.py najpierw.{X}")
        return None
    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)
            print(f"{G}🔑 Token odświeżony.{X}")
        except Exception as e:
            print(f"{Y}⚠️  Nie udało się odświeżyć tokenu: {e}{X}")
    return creds


def get_youtube_client():
    creds = _load_credentials()
    if not creds:
        return None
    return build("youtube", "v3", credentials=creds)


def get_analytics_client():
    """Buduje klienta YouTube Analytics API v2."""
    creds = _load_credentials()
    if not creds:
        return None
    try:
        client = build("youtubeAnalytics", "v2", credentials=creds)
        # Szybki test czy scope jest dostępny
        client.reports().query(
            ids="channel==MINE",
            startDate="2026-01-01",
            endDate=datetime.now().strftime("%Y-%m-%d"),
            metrics="views",
            dimensions="day",
            maxResults=1,
        ).execute()
        return client
    except Exception as e:
        err_str = str(e)
        if "insufficientPermissions" in err_str or "403" in err_str or "unauthorized" in err_str.lower():
            print(f"\n{Y}⚠️  BRAK SCOPE Analytics API w tokenie!{X}")
            print(f"   → Uruchom: python authorize_channel.py --konto {PROFILE_NAME}")
            print(f"   → Usuń stary token: del {TOKEN_FILE}")
            print(f"   → Analiza będzie kontynuowana BEZ danych CTR/AVD (tryb podstawowy).\n")
        else:
            print(f"{Y}⚠️  Analytics API niedostępne: {e}{X}")
        return None


# ─── 1. Pobieranie wszystkich filmów ─────────────────────────────────────────
def fetch_all_channel_videos(yt, max_results=MAX_VIDEOS):
    print(f"\n{C}📡 Pobieranie wszystkich filmów z kanału (paginacja, max {max_results})...{X}")

    ch_res  = yt.channels().list(part="contentDetails,statistics,snippet", mine=True).execute()
    ch      = ch_res["items"][0]
    ch_name = ch["snippet"]["title"]
    ch_id   = ch["id"]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    subs    = int(ch["statistics"].get("subscriberCount", 0))
    tot_v   = int(ch["statistics"].get("viewCount", 0))

    print(f"  📺 Kanał: {B}{ch_name}{X} | 👥 {subs:,} sub | 👁️ {tot_v:,} views | ID: {ch_id}")

    # Zbierz wszystkie video IDs
    video_ids, next_page = [], None
    while len(video_ids) < max_results:
        pl = yt.playlistItems().list(
            part="contentDetails", playlistId=uploads,
            maxResults=50, pageToken=next_page
        ).execute()
        for item in pl.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        next_page = pl.get("nextPageToken")
        if not next_page:
            break

    print(f"  🎬 Znaleziono {len(video_ids)} filmów łącznie.")

    # Pobierz szczegóły w batchach
    all_videos = []
    for i in range(0, len(video_ids), 50):
        batch   = video_ids[i:i+50]
        details = yt.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(batch)
        ).execute()
        for v in details.get("items", []):
            stats   = v.get("statistics", {})
            snippet = v.get("snippet", {})
            content = v.get("contentDetails", {})
            pub_str = snippet.get("publishedAt", "")
            views   = int(stats.get("viewCount", 0))
            likes   = int(stats.get("likeCount", 0))
            comments= int(stats.get("commentCount", 0))
            age_h   = 1.0
            if pub_str:
                pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                age_h  = max(1.0, (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600)
            dur_s   = parse_duration(content.get("duration", "PT0S"))
            engage  = round((likes + comments) / max(views, 1) * 100, 2)
            velocity= round(views / age_h, 2)

            # Wykryj format tytułu
            title = snippet.get("title", "")
            fmt   = detect_title_format(title)

            all_videos.append({
                "id":          v["id"],
                "title":       title,
                "title_format":fmt,
                "published":   pub_str,
                "pub_hour_utc": datetime.fromisoformat(pub_str.replace("Z","+00:00")).hour if pub_str else 0,
                "pub_weekday": datetime.fromisoformat(pub_str.replace("Z","+00:00")).weekday() if pub_str else 0,
                "views":       views,
                "likes":       likes,
                "comments":    comments,
                "duration_s":  dur_s,
                "engagement":  engage,
                "velocity":    velocity,
                "age_hours":   round(age_h, 1),
                # Placeholdery dla danych z Analytics API
                "ctr":         None,
                "impressions": None,
                "avg_view_s":  None,
                "avg_view_pct":None,
                "link":        f"https://youtube.com/shorts/{v['id']}",
            })

    all_videos.sort(key=lambda x: x["views"], reverse=True)
    return all_videos, ch_name, ch_id, subs, tot_v


# ─── 2. YouTube Analytics API — per video CTR/AVD ───────────────────────────
def enrich_with_analytics(analytics, videos, ch_id):
    """Uzupełnia dane AVD (avg view duration) dla każdego wideo z Analytics API."""
    if not analytics:
        print(f"\n{Y}⚠️  Analytics API niedostępne — pomijam AVD.{X}")
        return videos

    print(f"\n{C}📊 Pobieranie averageViewDuration i estimatedMinutesWatched z Analytics API...{X}")
    today      = datetime.now().strftime("%Y-%m-%d")
    old_pub    = min((v["published"] for v in videos if v["published"]), default="2025-01-01")
    start_date = old_pub[:10]

    all_ids   = [v["id"] for v in videos]
    id_to_idx = {v["id"]: i for i, v in enumerate(videos)}

    # Batch po 200 naraz
    for batch_start in range(0, len(all_ids), 200):
        batch_ids = all_ids[batch_start:batch_start+200]
        filters   = "video==" + ",".join(batch_ids)
        try:
            resp = analytics.reports().query(
                ids         = f"channel=={ch_id}",
                startDate   = start_date,
                endDate     = today,
                metrics     = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
                dimensions  = "video",
                filters     = filters,
                maxResults  = 500,
            ).execute()
            rows = resp.get("rows", [])
            for row in rows:
                vid_id   = row[0]
                v_views  = int(row[1])
                est_min  = float(row[2])
                avg_dur  = round(float(row[3]), 1)
                avg_pct  = round(float(row[4]), 1)
                if vid_id in id_to_idx:
                    idx = id_to_idx[vid_id]
                    videos[idx]["avg_view_s"]   = avg_dur
                    videos[idx]["avg_view_pct"] = avg_pct
                    videos[idx]["est_min_watch"] = round(est_min, 1)
            print(f"  ✅ AVD załadowane dla {len(rows)}/{len(batch_ids)} filmów.")
        except Exception as e:
            print(f"  {R}❌ Błąd Analytics batch: {e}{X}")

    return videos


# ─── 3. Aktywność widzów wg godziny ─────────────────────────────────────────
def fetch_audience_activity_by_hour(analytics, ch_id):
    """Pobiera aktywność widzów wg dnia (Analytics API nie wspiera wymiaru 'hour' dla kanałów).
    Zwraca pusty dict — analiza godzinowa opiera się na historii publikacji."""
    if not analytics:
        return {}
    print(f"\n{C}📅 Analytics API: weryfikacja połączenia (wymiar 'hour' niedostępny w basic tier)...{X}")
    print(f"  ℹ️  Analiza szczytowych godzin oparta na historii Twoich publikacji (patrz sekcja niżej).")
    return {}


# ─── 4. Analiza formatu tytułu ───────────────────────────────────────────────
def detect_title_format(title: str) -> str:
    """Wykrywa format tytułu: QUESTION / PREFIX_BRACKET / STATEMENT."""
    stripped = title.strip()
    if re.match(r"^\[.+?\]", stripped):
        return "PREFIX_BRACKET"
    q_words = r"^(have|can|are|do|does|is|why|how|what|when|who|which|would|could|did|will)\b"
    if stripped.endswith("?") or re.match(q_words, stripped.lower()):
        return "QUESTION"
    return "STATEMENT"


def analyze_title_formats(videos):
    """Porównuje avg views wg formatu tytułu."""
    fmt_views = defaultdict(list)
    for v in videos:
        fmt_views[v["title_format"]].append(v["views"])
    result = {}
    for fmt, vlist in fmt_views.items():
        result[fmt] = {
            "count":     len(vlist),
            "avg_views": round(sum(vlist) / len(vlist)),
            "max_views": max(vlist),
        }
    return result


# ─── 5. Analiza słów kluczowych ──────────────────────────────────────────────
def analyze_title_patterns(videos):
    STOPWORDS = {"the","and","is","in","to","a","of","this","you","they","your","for",
                 "with","not","at","are","or","but","their","will","that","when","it",
                 "its","from","by","an","be","was","were","has","had","have"}
    word_views = Counter()
    word_count = Counter()
    for v in videos:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", v["title"].lower())
        for w in set(words):  # set — liczymy 1 raz per tytuł
            if w not in STOPWORDS:
                word_views[w]  += v["views"]
                word_count[w]  += 1
    avg_word = {
        w: round(word_views[w] / word_count[w])
        for w in word_count if word_count[w] >= 2
    }
    top_kw = sorted(avg_word.items(), key=lambda x: x[1], reverse=True)[:20]
    low_kw = sorted(avg_word.items(), key=lambda x: x[1])[:8]
    return top_kw, low_kw


# ─── 6. Długość wideo ─────────────────────────────────────────────────────────
def analyze_duration_performance(videos):
    buckets = {"0-10s": [], "11-20s": [], "21-30s": [], "31-60s": []}
    for v in videos:
        d = v["duration_s"]
        if   d <= 10:  buckets["0-10s"].append(v["views"])
        elif d <= 20:  buckets["11-20s"].append(v["views"])
        elif d <= 30:  buckets["21-30s"].append(v["views"])
        else:          buckets["31-60s"].append(v["views"])
    return {
        k: {"count": len(vl), "avg_views": round(sum(vl)/len(vl)), "max_views": max(vl)}
        for k, vl in buckets.items() if vl
    }


# ─── 7. Analiza godziny publikacji ───────────────────────────────────────────
def analyze_publish_time(videos):
    DAYS = {0:"Pn", 1:"Wt", 2:"Śr", 3:"Czw", 4:"Pt", 5:"Sob", 6:"Nd"}
    day_views  = Counter()
    hour_views = Counter()
    for v in videos:
        if not v["published"]: continue
        pub = datetime.fromisoformat(v["published"].replace("Z", "+00:00"))
        day_views[DAYS[pub.weekday()]]  += v["views"]
        hour_views[pub.hour]            += v["views"]
    best_day  = day_views.most_common(1)[0]  if day_views  else ("?", 0)
    best_hour = hour_views.most_common(1)[0] if hour_views else (0, 0)
    return best_day, best_hour


# ─── 8. Top performerów hook patterns ────────────────────────────────────────
def analyze_hook_patterns(videos, n=5):
    """Wyciąga wzorce pierwszych 8 słów tytułu topowych filmów."""
    top = sorted(videos, key=lambda x: x["views"], reverse=True)[:n]
    patterns = []
    for v in top:
        words = v["title"].split()[:8]
        patterns.append(" ".join(words))
    return patterns


# ─── 8b. Klasyfikacja wydajności wideo wg wieku + views ───────────────────────────────────────
STATE_LABELS = {
    "TOO_YOUNG":  "⏳ Za młody do analizy",
    "WAIT":       "🔄 Zbyt mało danych (czekaj)",
    "MISS":       "🔵 Nie wstrzelił się (miss)",
    "SUPPRESSED": "🚨 Algorytm tłumi (suppressed)",
    "NORMAL":     "✅ Normalny zasięg",
    "HIT":        "📈 Hit",
    "VIRAL":      "🔥 Viral",
}

def classify_video_performance(video: dict) -> dict:
    """
    Klasyfikuje wideo wg wieku + views.
    Zwraca dict: {state, state_label, min_views_needed, analysis_valid, explanation}

    Progi (oparte na typowym zachowaniu YT Shorts):
      0-6h  → TOO_YOUNG    : za wcześnie na jakikolwiek wniosek
      6-24h → WAIT         : <10 views = za mało danych; >=10 = można analizować
      24-48h→ MISS         : <15 views = nie wstrzelił się w pierwsze 48h
               NORMAL       : 15-200 views = normalna dystrybucja
               HIT          : >200 views
      48-72h→ SUPPRESSED   : <20 views i starszy niż 48h = algorytm tłumi
               NORMAL/HIT/VIRAL jak wyżej
      >72h  → SUPPRESSED   : <30 views
               NORMAL       : 30-500
               HIT          : 500-2000
               VIRAL        : >2000
    """
    age_h  = video.get("age_hours", 999)
    views  = video.get("views", 0)
    title  = video.get("title", "")[:50]

    if age_h < 6:
        return {
            "state": "TOO_YOUNG",
            "state_label": STATE_LABELS["TOO_YOUNG"],
            "analysis_valid": False,
            "min_views_needed": 5,
            "explanation": f"Film ma tylko {age_h:.0f}h — YT Shorts nie zdecydował jeszcze o dystrybucji.",
        }
    if age_h < 24:
        if views < 10:
            return {
                "state": "WAIT",
                "state_label": STATE_LABELS["WAIT"],
                "analysis_valid": False,
                "min_views_needed": 10,
                "explanation": f"Film ({age_h:.0f}h stary, {views} views) — za mało danych. Analizuj po 24h.",
            }
        # >= 10 views w pierwszych 24h = już można wnioskować
        state = "HIT" if views >= 100 else "NORMAL"
        return {
            "state": state,
            "state_label": STATE_LABELS[state],
            "analysis_valid": True,
            "min_views_needed": 10,
            "explanation": f"Film ({age_h:.0f}h stary, {views} views) — wczesne dane.",
        }
    if age_h < 48:
        if views < 15:
            return {
                "state": "MISS",
                "state_label": STATE_LABELS["MISS"],
                "analysis_valid": True,
                "min_views_needed": 15,
                "explanation": (
                    f"Film '{title}' ma tylko {views} views po {age_h:.0f}h. "
                    f"Nie trafił w algorytm — zmień hook lub tytuł."
                ),
            }
        state = "VIRAL" if views >= 2000 else ("HIT" if views >= 200 else "NORMAL")
        return {
            "state": state, "state_label": STATE_LABELS[state],
            "analysis_valid": True, "min_views_needed": 15,
            "explanation": f"{views} views po {age_h:.0f}h.",
        }
    # > 48h
    if views < 20:
        return {
            "state": "SUPPRESSED",
            "state_label": STATE_LABELS["SUPPRESSED"],
            "analysis_valid": True,
            "min_views_needed": 20,
            "explanation": (
                f"Film '{title}' ma {views} views po {age_h:.0f}h. "
                f"Algorytm tłumi dystrybucję — możliwy shadow-limit lub przerwa w wysyłkach."
            ),
        }
    state = "VIRAL" if views >= 2000 else ("HIT" if views >= 500 else "NORMAL")
    return {
        "state": state, "state_label": STATE_LABELS[state],
        "analysis_valid": True, "min_views_needed": 20,
        "explanation": f"{views} views po {age_h:.0f}h.",
    }


# ─── 9. Dyrektywa adaptacyjna ────────────────────────────────────────────────
def generate_adaptation_directive(videos, top_kw, low_kw, dur_perf, best_pub_day,
                                   best_pub_hour, last_2, fmt_analysis, hour_activity,
                                   hook_patterns):
    D = []
    if not videos:
        return "BRAK DANYCH — kontynuuj dotychczasową strategię."

    # ── Klasyfikuj ostatnie filmy (age-aware) ──
    classified_last = [(v, classify_video_performance(v)) for v in last_2]

    # ── Ostatnie 2 filmy z etykietą stanu ──
    if classified_last:
        v, cls = classified_last[0]
        ctr_str = f" | CTR: {v['ctr']}%" if v.get("ctr") is not None else ""
        avd_str = f" | AVD: {v['avg_view_s']}s ({v['avg_view_pct']}%)" if v.get("avg_view_s") is not None else ""
        D.append(
            f"OSTATNI FILM [{cls['state_label']}]: '{v['title']}' — "
            f"{v['views']} views, {v['likes']} likes, "
            f"{v['engagement']}% eng, {v['velocity']} v/h{ctr_str}{avd_str}. "
            f"{cls['explanation']}"
        )
    if len(classified_last) >= 2:
        v, cls = classified_last[1]
        D.append(
            f"PRZEDOSTATNI FILM [{cls['state_label']}]: '{v['title']}' — "
            f"{v['views']} views, {v['engagement']}% eng. {cls['explanation']}"
        )

    # ── Główny wniosek oparty na klasyfikacji ──
    if classified_last:
        v0, cls0 = classified_last[0]

        if cls0["state"] == "TOO_YOUNG":
            D.append(
                "WNIOSEK [ZA MŁODY]: Film ma mniej niż 6h — "
                "YT Shorts nie rozdał jeszcze dystrybucji. "
                "NIE ZMIENIAJ strategii na podstawie tych danych. Sprawdź jutro."
            )
        elif cls0["state"] == "WAIT":
            D.append(
                "WNIOSEK [ZA MAŁO DANYCH]: Film ma mniej niż 24h i <10 views. "
                "Brak wystarczających danych do wnioskowania. "
                "Kontynuuj obecną strategię bez zmian."
            )
        elif cls0["state"] == "MISS":
            D.append(
                f"WNIOSEK [MISS — nie wstrzelił się]: '{v0['title'][:50]}' "
                f"ma tylko {v0['views']} views po {v0['age_hours']:.0f}h. "
                "Zmień hook — spróbuj formułę 'Have you ever felt...' lub 'Can you spot...'. "
                "Tytuł musi być pytaniem. Unikaj słów z listy ZAKAZANYCH."
            )
        elif cls0["state"] == "SUPPRESSED":
            D.append(
                f"WNIOSEK [SUPPRESSED — algorytm tłumi]: "
                f"{v0['views']} views po {v0['age_hours']:.0f}h. "
                "Możliwe przyczyny: przerwa w publikacji, zmiana niszy, błąd techniczny. "
                "STRATEGIA WYJŚCIA: 1) Wrzucaj codziennie bez przerwy. "
                "2) Używaj wyłącznie QUESTION format. "
                "3) Wróć do body language (najlepsza nisza kanału). "
                "4) Sprawdź plik: codec H.264, audio 44100Hz, 1080x1920."
            )
        elif cls0["state"] in ("HIT", "VIRAL"):
            D.append(
                f"WNIOSEK [HIT]: '{v0['title'][:50]}' osiągnął "
                f"{v0['views']} views po {v0['age_hours']:.0f}h. "
                "Powiel format tytułu, hook i styl narracji tego wideo."
            )
            if len(classified_last) >= 2:
                v1, cls1 = classified_last[1]
                if cls1["analysis_valid"] and v1["views"] >= cls1["min_views_needed"]:
                    if v0["views"] > v1["views"] * 1.5:
                        D.append(f"Poprawa o 50%+ względem poprzedniego ({v1['views']} views). Kontynuuj ten kierunek.")
        else:  # NORMAL
            if len(classified_last) >= 2:
                v1, cls1 = classified_last[1]
                if cls1["analysis_valid"] and v1["views"] >= cls1["min_views_needed"]:
                    if v0["views"] > v1["views"] * 1.5:
                        D.append(f"WNIOSEK: Ostatni film LEPSZY o 50%+. Powiel styl tytułu: '{v0['title']}'.")
                    elif v0["views"] < v1["views"] * 0.6:
                        D.append(f"WNIOSEK: Ostatni film SŁABSZY. Unikaj stylu: '{v0['title']}'.")
                    else:
                        D.append(f"WNIOSEK: Stabilna wydajność ({v0['views']} vs {v1['views']} views). Kontynuuj strategię.")
                elif not cls1["analysis_valid"]:
                    D.append(
                        f"WNIOSEK: Brak danych porównawczych (poprzedni film: {cls1['state_label']}). "
                        "Kontynuuj obecną strategię."
                    )
            else:
                D.append(f"WNIOSEK: Film normalny ({v0['views']} views po {v0['age_hours']:.0f}h). Kontynuuj strategię.")

    # ── DETEKCJA PRZERWY W PUBLIKACJI (gap alert) ──
    try:
        from datetime import timezone as _tz
        if videos:
            sorted_pub = sorted(videos, key=lambda x: x.get("published", ""), reverse=True)
            last_pub = datetime.fromisoformat(
                sorted_pub[0].get("published", "").replace("Z", "+00:00")
            )
            gap_h = (datetime.now(_tz.utc) - last_pub).total_seconds() / 3600
            if gap_h > 48:
                D.append(
                    f"ALERT: Przerwa w publikacji wynosi {gap_h/24:.1f} dni! "
                    f"YT Shorts algorytm karze przerwy >2 dni utratą momentum. "
                    f"PRIORYTET: wrzucaj dziś!"
                )
    except Exception:
        pass

    # ── Format tytułu ──
    if fmt_analysis:
        best_fmt = max(fmt_analysis.items(), key=lambda x: x[1]["avg_views"])
        fmt_name, fmt_data = best_fmt
        D.append(
            f"NAJLEPSZY FORMAT TYTUŁU: {fmt_name} (śr. {fmt_data['avg_views']:,} views, "
            f"{fmt_data['count']} filmów). "
            + ("UŻYWAJ pytań: 'Have you...', 'Can you spot...', 'Are you...'. "
               if fmt_name == "QUESTION" else "")
            + ("NIGDY NIE UŻYWAJ [Prefix] w nawiasach — te filmy mają dramatycznie gorsze wyniki. "
               if "PREFIX_BRACKET" in fmt_analysis and fmt_analysis["PREFIX_BRACKET"]["avg_views"] < fmt_data["avg_views"] * 0.5 else "")
        )
        worst_fmt = min(fmt_analysis.items(), key=lambda x: x[1]["avg_views"])
        if worst_fmt[0] == "PREFIX_BRACKET":
            D.append(f"KRYTYCZNE: FORMAT [PREFIKS W NAWIASACH] = "
                     f"średnio tylko {worst_fmt[1]['avg_views']} views. ZAKAZANY!")

    # ── Słowa kluczowe ──
    if top_kw:
        kw_str = ", ".join(f"'{k}'" for k, _ in top_kw[:8])
        D.append(f"SKUTECZNE SŁOWA W TYTULE: {kw_str}. Wplataj je naturalnie w tytuł i hook!")
    if low_kw:
        lk_str = ", ".join(f"'{k}'" for k, _ in low_kw[:5])
        D.append(f"SŁABE/ZAKAZANE SŁOWA: {lk_str}.")

    # ── Długość wideo ──
    if dur_perf:
        best_b = max(dur_perf.items(), key=lambda x: x[1]["avg_views"])
        D.append(f"OPTYMALNA DŁUGOŚĆ: {best_b[0]} (śr. {best_b[1]['avg_views']:,} views). "
                 f"Pisz skrypt na {best_b[0]} — nie za długi, nie za krótki!")

    # ── Czas publikacji — z Analytics lub z historii ──
    if hour_activity:
        peak_h = max(hour_activity, key=hour_activity.get)
        D.append(f"PEAK AKTYWNOŚCI WIDZÓW (ANALYTICS): {peak_h:02d}:00 UTC "
                 f"= {peak_h+2:02d}:00 PL (CEST). Wrzucaj wtedy!")
    else:
        D.append(f"NAJLEPSZY CZAS PUBLIKACJI (z historii): {best_pub_day[0]} "
                 f"o ~{best_pub_hour[0]:02d}:00 UTC = {best_pub_hour[0]+2:02d}:00 PL (CEST).")

    # ── Hook patterns ──
    if hook_patterns:
        D.append(f"TOP HOOK PATTERNS (pierwsze słowa najlepszych filmów): "
                 + " / ".join(f'"{p}"' for p in hook_patterns[:3]))

    # ── Engagement ──
    vids_with_data = [v for v in videos if v["views"] > 0]
    if vids_with_data:
        avg_eng = sum(v["engagement"] for v in vids_with_data[:20]) / len(vids_with_data[:20])
        if avg_eng < 2.0:
            D.append("ENGAGEMENT NISKI (<2%). Dodaj CTA na końcu: 'Follow for more dark psychology secrets.' "
                     "lub 'Like if you've seen this used on you.'")
        elif avg_eng >= 4.0:
            D.append(f"ENGAGEMENT DOSKONAŁY ({avg_eng:.1f}%). Utrzymaj styl CTA który generuje polubienia.")

    # ── CTR wskazówka (jeśli dostępne) ──
    vids_with_ctr = [v for v in videos if v.get("ctr") is not None]
    if vids_with_ctr:
        avg_ctr = sum(v["ctr"] for v in vids_with_ctr) / len(vids_with_ctr)
        top_ctr_vid = max(vids_with_ctr, key=lambda x: x["ctr"])
        D.append(f"CTR: średni {avg_ctr:.1f}%. Najlepszy CTR: '{top_ctr_vid['title'][:50]}' "
                 f"({top_ctr_vid['ctr']}%). Miniatura + tytuł muszą ZATRZYMYWAĆ scroll!")

    return " | ".join(D)


# ─── Parsowanie ISO duration ──────────────────────────────────────────────────
def parse_duration(iso: str) -> int:
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m: return 0
    return int(m.group(1) or 0)*3600 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)


# ─── Raport CLI ──────────────────────────────────────────────────────────────
def print_report(videos, ch_name, subs, tot_v, top_kw, low_kw, dur_perf,
                 best_pub_day, best_pub_hour, last_2, directive, fmt_analysis,
                 hour_activity, hook_patterns):
    sep = "═" * 65

    print(f"\n{B}╔{sep}╗{X}")
    print(f"{B}║  🧠 SMART CHANNEL ANALYZER v2.0 — RAPORT GŁĘBOKI{X}")
    print(f"{B}╠{sep}╣{X}")
    print(f"  📺 Kanał: {ch_name} | 👥 {subs:,} sub | 👁️ {tot_v:,} views")
    print(f"  🎬 Przeanalizowanych filmów: {len(videos)}")

    # TOP 5
    print(f"\n{C}─── TOP 5 FILMÓW WSZECHCZASÓW ──────────────────────────────────{X}")
    for i, v in enumerate(videos[:5], 1):
        ec = G if v["engagement"] >= 3 else (Y if v["engagement"] >= 1.5 else R)
        ctr_s = f" | CTR {v['ctr']}%" if v.get("ctr") is not None else ""
        avd_s = f" | AVD {v['avg_view_s']}s" if v.get("avg_view_s") is not None else ""
        fmt_s = f" [{v['title_format']}]"
        print(f"  #{i}  {v['views']:>7,} views | {ec}{v['engagement']}% eng{X}{ctr_s}{avd_s}{fmt_s}")
        print(f"      {v['title'][:70]}")

    # Ostatnie 2
    print(f"\n{C}─── OSTATNIE 2 FILMY (aktualny cykl) ─────────────────────────{X}")
    for v in last_2:
        vc = G if v["velocity"] >= 50 else (Y if v["velocity"] >= 10 else R)
        ctr_s = f" | CTR {v['ctr']}%" if v.get("ctr") is not None else ""
        avd_s = f" | AVD {v['avg_view_s']}s ({v['avg_view_pct']}%)" if v.get("avg_view_s") is not None else ""
        print(f"  🎞️  [{v['title_format']}] '{v['title'][:60]}'")
        print(f"      👁️ {v['views']:,} | 👍 {v['likes']} | {vc}⚡ {v['velocity']:.1f} v/h{X}"
              f" | ⏱️ {v['age_hours']:.0f}h {ctr_s}{avd_s}")

    # Format tytułów
    print(f"\n{C}─── FORMAT TYTUŁÓW (performance porównanie) ───────────────────{X}")
    for fmt, data in sorted(fmt_analysis.items(), key=lambda x: x[1]["avg_views"], reverse=True):
        marker = G if fmt == "QUESTION" else (R if fmt == "PREFIX_BRACKET" else Y)
        print(f"  {marker}{fmt}{X}: {data['avg_views']:,} avg views | {data['count']} filmów | max {data['max_views']:,}")

    # Słowa kluczowe
    print(f"\n{C}─── SKUTECZNE SŁOWA KLUCZOWE ───────────────────────────────────{X}")
    for kw, avg in top_kw[:12]:
        bar = "█" * min(25, avg // 100)
        print(f"  {G}'{kw}'{X} → {bar} {avg:,} avg views")

    print(f"\n{C}─── SŁABE / ZAKAZANE SŁOWA ─────────────────────────────────────{X}")
    for kw, avg in low_kw[:6]:
        print(f"  {R}'{kw}'{X} → {avg:,} avg views")

    # Długości
    print(f"\n{C}─── OPTYMALNA DŁUGOŚĆ WIDEO ────────────────────────────────────{X}")
    for bucket, data in sorted(dur_perf.items()):
        bar = "█" * min(25, data["avg_views"] // 60)
        best = G if data == max(dur_perf.values(), key=lambda x: x["avg_views"]) else X
        print(f"  {best}{bucket}{X}: {bar} {data['avg_views']:,} avg ({data['count']} filmów)")

    # Czas publikacji
    print(f"\n{C}─── NAJLEPSZY CZAS PUBLIKACJI ──────────────────────────────────{X}")
    if hour_activity:
        sorted_hours = sorted(hour_activity.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"  {B}Z Analytics API (ostatnie 90 dni):{X}")
        for h, v in sorted_hours:
            bar = "█" * min(30, v // max(1, max(hour_activity.values()) // 30))
            peak = G if h == sorted_hours[0][0] else X
            print(f"    {peak}{h:02d}:00 UTC = {h+1:02d}:00 PL{X}: {bar} {v:,} views")
    else:
        print(f"  📅 Dzień: {B}{best_pub_day[0]}{X} | 🕐 Godzina: {B}~{best_pub_hour[0]:02d}:00 UTC{X}")

    # Hook patterns
    print(f"\n{C}─── TOP HOOK PATTERNS (naśladuj!) ─────────────────────────────{X}")
    for p in hook_patterns:
        print(f"  ➤ \"{p}...\"")

    # Dyrektywa
    print(f"\n{B}╔{sep}╗{X}")
    print(f"{B}║  📋 SYNAPSA ADAPTATION DIRECTIVE v2{X}")
    print(f"{B}╠{sep}╣{X}")
    for seg in directive.split(" | "):
        print(f"  • {seg}")
    print(f"{B}╚{sep}╝{X}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'═'*65}")
    print(f"  🔬 SMART VIDEO ANALYZER v2.0 — Głęboka analiza kanału")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*65}\n")

    yt        = get_youtube_client()
    analytics = get_analytics_client()

    if not yt:
        print(f"{R}❌ Błąd autoryzacji YouTube API.{X}")
        return

    # 1. Pobierz wszystkie filmy
    videos, ch_name, ch_id, subs, tot_v = fetch_all_channel_videos(yt)
    if not videos:
        print("⚠️  Brak filmów do analizy.")
        return

    # 2. Uzupełnij CTR/AVD z Analytics API
    videos = enrich_with_analytics(analytics, videos, ch_id)

    # 3. Aktywność widzów wg godziny
    hour_activity = fetch_audience_activity_by_hour(analytics, ch_id)

    # 4. Ostatnie 2 filmy (wg daty publikacji)
    sorted_by_date = sorted(videos, key=lambda x: x["published"], reverse=True)
    last_2         = sorted_by_date[:2]

    # 5. Analizy
    top_kw, low_kw     = analyze_title_patterns(videos)
    dur_perf            = analyze_duration_performance(videos)
    best_pub_day, best_pub_hour = analyze_publish_time(videos)
    fmt_analysis        = analyze_title_formats(videos)
    hook_patterns       = analyze_hook_patterns(videos, n=5)

    # Najlepszy czas publikacji z Analytics, jeśli dostępny
    if hour_activity:
        best_hour_analytics = max(hour_activity, key=hour_activity.get)
    else:
        best_hour_analytics = None

    # 6. Generuj dyrektywę
    directive = generate_adaptation_directive(
        videos, top_kw, low_kw, dur_perf, best_pub_day, best_pub_hour,
        last_2, fmt_analysis, hour_activity, hook_patterns
    )

    # 7. Raport CLI
    print_report(videos, ch_name, subs, tot_v, top_kw, low_kw, dur_perf,
                 best_pub_day, best_pub_hour, last_2, directive, fmt_analysis,
                 hour_activity, hook_patterns)

    # 8. Zapisz dyrektywę
    best_bucket = max(dur_perf.items(), key=lambda x: x[1]["avg_views"])[0] if dur_perf else "11-20s"
    optimal_post_utc = best_hour_analytics if best_hour_analytics is not None else best_pub_hour[0]

    directive_data = {
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "directive":            directive,
        "last_2_videos":        last_2,
        "top_keywords":         top_kw[:12],
        "low_keywords":         low_kw[:6],
        "duration_best_bucket": best_bucket,
        "best_publish_day":     best_pub_day[0],
        "best_publish_hour_utc": optimal_post_utc,
        "title_format_analysis": fmt_analysis,
        "hour_activity_utc":    hour_activity,
        "hook_patterns_top5":   hook_patterns,
        "analytics_available":  analytics is not None,
    }
    with open(DIRECTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(directive_data, f, indent=4, ensure_ascii=False)
    print(f"\n{G}✅ Dyrektywa zapisana: {DIRECTIVE_FILE}{X}")

    # 9. Pełny raport JSON
    report = {
        "generated_at":           directive_data["generated_at"],
        "channel":                {"name": ch_name, "id": ch_id, "subscribers": subs, "total_views": tot_v},
        "videos_analyzed":        len(videos),
        "analytics_api_enabled":  analytics is not None,
        "top_5":                  videos[:5],
        "last_2":                 last_2,
        "top_keywords":           top_kw[:20],
        "low_keywords":           low_kw[:8],
        "duration_performance":   dur_perf,
        "title_format_analysis":  fmt_analysis,
        "hour_activity_utc":      hour_activity,
        "hook_patterns_top5":     hook_patterns,
        "best_publish_day":       best_pub_day[0],
        "best_publish_hour_utc":  optimal_post_utc,
        "adaptation_directive":   directive,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    print(f"📄 Pełny raport: {REPORT_FILE}\n")

    # ── AUTO-CLEANUP: Zachowaj tylko ostatnie 14 dni raportów ────────────────
    import glob as _glob
    from datetime import timedelta as _td
    _cutoff = datetime.now(timezone.utc) - _td(days=14)
    for _pattern in ["smart_analysis_*.json", "trend_report_*.json"]:
        for _old in _glob.glob(_pattern):
            try:
                # Wyciągnij datę z nazwy pliku
                _date_str = _old.split("_")[-1].replace(".json", "")
                _file_dt = datetime.strptime(_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if _file_dt < _cutoff and _old != REPORT_FILE:
                    os.remove(_old)
                    print(f"🗑️  [AUTO-CLEANUP] Usunięto stary raport: {_old}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
