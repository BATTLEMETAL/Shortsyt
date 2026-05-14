"""
prettywoman_tiktok_analyzer.py
===============================
Analizuje profil TikTok @salonprettywoman:
  - Pobiera metadane wszystkich filmów (yt-dlp, bez watermark)
  - Oblicza score viralowości (views/age, engagement)
  - Wybiera TOP filmiki do przeniesienia na YT Shorts
  - Zapisuje wyniki do prettywoman_analysis.json
  - Generuje ADAPTATION_DIRECTIVE dla Synapsy

Użycie: python prettywoman_tiktok_analyzer.py
"""

import subprocess
import json
import os
import sys
import re
from datetime import datetime, timezone

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

TIKTOK_URL   = "https://www.tiktok.com/@salonprettywoman"
OUTPUT_FILE  = "prettywoman_analysis.json"
DIRECTIVE_FILE = "accounts/prettywoman_directive.txt"
TOP_N        = 10   # ile top filmów wybrać do transferu na YT

# ── Znane dane z TikTok Studio (24.04.2026) ────────────────────────────────
# Zebrane ręcznie ze zrzutów ekranu — używamy jako dane bazowe/fallback
KNOWN_ANALYTICS = {
    "channel": "Afroloki Świdnica (@salonprettywoman)",
    "followers": 1100,
    "total_likes": 13600,
    "audience_gender": {"women": 88, "men": 10, "other": 2},
    "audience_age": {"18-24": 4.3, "25-34": 18.1, "35-44": 31.5, "45-54": 27.0, "55+": 19.9},
    "audience_location": {"Polska": 72.5, "Niemcy": 10.1, "Wielka Brytania": 1.7},
    "traffic_sources": {"for_you": 79.7, "personal_profile": 13.4, "search": 6.5},
    "top_search_terms": ["warkoczyki pół głowy", "warkoczyki na lato", "afroloki", "pomka tutorial"],
    "peak_activity_hour_utc": 0,
    "peak_activity_day": "czwartek",
    "top_posts_7d": [
        {"title": "Panda kucyki Tworzymy ręcznie tkane panda-Afroloki", "views_7d": 2800, "views_total": 2800},
        {"title": "Topor zbaczony specjalnie dla naszej klientki każdy topor", "views_7d": 1000, "views_total": 1000},
        {"title": "AbyToper szybka metamorfoza w 1 minutę", "views_7d": 557, "views_total": 6900},
        {"title": "Nowości game changer Gotowe panda na spacer", "views_7d": 449, "views_total": 6300},
        {"title": "Jak nosimy nasze kucyki na ściągaczu", "views_7d": 400, "views_total": 49100},
        {"title": "Zapraszamy na Afroloki oraz Szkolenia", "views_7d": 380, "views_total": 29500},
        {"title": "Pani Sandra jej nowe fryzura totally szkol", "views_7d": 415, "views_total": 452},
        {"title": "Nasze kucyki szybka metamorfoza WOW w kilka chwili", "views_7d": 402, "views_total": 421},
        {"title": "Włosy w pełni Pani Alina rozmawiła Afroloki z dobrym", "views_7d": 550, "views_total": 550},
        {"title": "Kulisy naszych Rolek", "views_7d": 300, "views_total": 16200},
    ],
    "competitors_audience_also_watches": [
        "Spring outfit kind of day @dżanna Sołec - 1.9M",
        "Mój sekret na idealny ceny bez efektu madz - 1.3M",
        "A psychologia o moich włosach - 1M",
        "wiosenne stylizacje Które wybierać - 1.9M",
    ]
}


def fetch_tiktok_metadata() -> list:
    """Próbuje pobrać metadane filmów przez yt-dlp."""
    print("📡 Pobieranie metadanych TikTok przez yt-dlp...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp",
             "--flat-playlist", "--dump-json",
             "--no-warnings",
             "--extractor-args", "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com",
             TIKTOK_URL],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60
        )
        videos = []
        for line in result.stdout.strip().splitlines():
            try:
                v = json.loads(line)
                videos.append(v)
            except Exception:
                pass
        if videos:
            print(f"  ✅ Pobrano {len(videos)} filmów przez yt-dlp")
        else:
            print("  ⚠️  yt-dlp nie zwrócił danych (TikTok blokuje) — używam znanych danych analitycznych")
        return videos
    except Exception as e:
        print(f"  ⚠️  yt-dlp error: {e} — używam znanych danych analitycznych")
        return []


def score_video(v: dict) -> float:
    """Oblicza score viralowości (wyższy = lepszy kandydat na YT)."""
    views     = v.get("view_count", 0) or 0
    likes     = v.get("like_count", 0) or 0
    comments  = v.get("comment_count", 0) or 0
    shares    = v.get("repost_count", 0) or 0
    duration  = v.get("duration", 30) or 30

    engagement = (likes + comments * 3 + shares * 5) / max(views, 1) * 100
    duration_bonus = 1.2 if 15 <= duration <= 45 else 1.0  # optymalny czas dla Shorts

    score = (views * 0.5 + engagement * 1000) * duration_bonus
    return round(score, 2)


def detect_content_type(title: str) -> str:
    """Wykrywa typ contentu na podstawie tytułu."""
    t = title.lower()
    if any(k in t for k in ["panda", "kucyki", "warkoczyki", "afroloki"]):
        return "afroloki_warkoczyki"
    if any(k in t for k in ["metamorfoza", "zmiana", "transformation", "przed i po", "before", "after"]):
        return "metamorfoza"
    if any(k in t for k in ["szkoleni", "tutorial", "jak", "poradnik"]):
        return "edukacja"
    if any(k in t for k in ["nowości", "game changer", "nowy produkt"]):
        return "nowosci_produkty"
    if any(k in t for k in ["zaprasz", "sklep", "zamówi"]):
        return "promo"
    return "ogolne"


def build_yt_hook(title: str, content_type: str) -> str:
    """Generuje lepszy hook dla YT Shorts na podstawie tytułu TikTok."""
    hooks = {
        "afroloki_warkoczyki": [
            f"Masz dość codziennej fryzury? Zobacz co zrobiłyśmy z włosami tej klientki...",
            f"Warkoczyki, które robią WOW — efekt po 1 wizycie w salonie",
            f"Takich afroloków w Polsce szukałaś? Jesteśmy w Świdnicy!",
        ],
        "metamorfoza": [
            f"Ta klientka nie poznała się w lustrze — PRZED i PO w 60 sekund",
            f"Metamorfoza, która zajęła nam 1 wizytę. Efekt? Musisz zobaczyć",
            f"Przyszła z taką fryzurą... wyszła zupełnie inna osoba",
        ],
        "edukacja": [
            f"Jeden trik, który zmieni Twoje warkoczyki na zawsze",
            f"Dlaczego Twoje afroloki wyglądają gorzej niż powinny? Oto odpowiedź",
            f"Nikt Ci o tym nie mówił — tajemnica trwałych warkoczyków",
        ],
        "nowosci_produkty": [
            f"Właśnie dotarła do nas nowość, która zmienia WSZYSTKO",
            f"Ten produkt do włosów to game changer — pokazujemy jak działa",
            f"Stop! Zanim zamówisz warkoczyki — musisz to zobaczyć",
        ],
        "promo": [
            f"Chcesz takie afroloki? Znajdź nas w Świdnicy!",
            f"Rezerwuj wizytę zanim miejsca się skończą",
        ],
    }
    import random
    options = hooks.get(content_type, [f"Musisz to zobaczyć — efekt naszej pracy"])
    return random.choice(options)


def analyze_known_data() -> list:
    """Analizuje znane dane z TikTok Studio i buduje listę kandydatów."""
    candidates = []
    for p in KNOWN_ANALYTICS["top_posts_7d"]:
        title = p["title"]
        views = p["views_total"]
        views_7d = p["views_7d"]
        content_type = detect_content_type(title)

        # Score: wysoki total views + wysoki stosunek 7d/total (nowe viralne) = najlepsze
        recency_ratio = views_7d / max(views, 1)
        score = views * 0.6 + views_7d * 2.0 + (recency_ratio * 10000)

        yt_hook = build_yt_hook(title, content_type)

        candidates.append({
            "tiktok_title": title,
            "views_total":  views,
            "views_7d":     views_7d,
            "content_type": content_type,
            "score":        round(score, 1),
            "yt_hook":      yt_hook,
            "recommended":  views >= 5000 or views_7d >= 800,
            "yt_title_formula": get_yt_title_formula(content_type),
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def get_yt_title_formula(content_type: str) -> str:
    formulas = {
        "afroloki_warkoczyki": "QUESTION: 'Gdzie zrobić afroloki w Polsce?' | NUMBERED: '5 rzeczy o warkoczykach'",
        "metamorfoza": "BEFORE_AFTER: 'Nie uwierzysz w tę przemianę' | STATEMENT: 'Metamorfoza w 1 wizycie'",
        "edukacja": "QUESTION: 'Dlaczego Twoje warkoczyki nie wyglądają tak?' | HOW_TO",
        "nowosci_produkty": "CONTRARIAN: 'Stop kupować X zanim to przeczytasz' | STATEMENT",
        "promo": "LOCAL_CTA: 'Salon Świdnica — rezerwuj teraz'",
    }
    return formulas.get(content_type, "QUESTION or STATEMENT format")


def generate_adaptation_directive(candidates: list) -> str:
    """Generuje dyrektywę dla Synapsy specyficzną dla PrettyWoman."""
    top3 = candidates[:3]
    top_types = {}
    for c in candidates[:5]:
        ct = c["content_type"]
        top_types[ct] = top_types.get(ct, 0) + 1

    best_type = max(top_types, key=top_types.get) if top_types else "afroloki_warkoczyki"
    best_video = top3[0] if top3 else {}

    directive = (
        f"CHANNEL: Afroloki Świdnica (@salonprettywoman) | "
        f"NICHE: beauty salon specialty hair (afroloki, warkoczyki, panda kucyki) | "
        f"AUDIENCE: 88% kobiety, 35-54 lat, Polska 72.5% | "
        f"TOP CONTENT TYPE: {best_type} ({top_types.get(best_type,0)} z top 5) | "
        f"#1 VIDEO ALL TIME: '{best_video.get('tiktok_title','?')}' ({best_video.get('views_total',0):,} views) | "
        f"PROVEN HOOKS: Przed-i-po transformacja, '1 minutowa metamorfoza', 'game changer nowość', warkoczyki na lato | "
        f"YT ADVANTAGE: Dodaj polskie słowa kluczowe (warkoczyki Świdnica, afroloki Polska), "
        f"hook werbalny zamiast tylko tekstu na ekranie, CTA: 'link w opisie do rezerwacji' | "
        f"FORBIDDEN: dark psychology style, manipulacja, szokujące fakty — "
        f"STYL: ciepły, profesjonalny, inspirujący, kobiecy | "
        f"MUSIC: soft elegant background, nie phonk/rap | "
        f"FILTERS: warm beauty (nie zimny cinematic dark) | "
        f"PEAK PUBLISH TIME: czwartek 0-7 UTC = 1-8 rano PL | "
        f"SEARCH TERMS TO TARGET: warkoczyki na lato, afroloki Świdnica, panda kucyki jak zrobić, "
        f"szybka metamorfoza włosy"
    )
    return directive


def main():
    print("=" * 60)
    print("  💇 PRETTYWOMAN TIKTOK ANALYZER")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Spróbuj pobrać przez yt-dlp
    yt_dlp_videos = fetch_tiktok_metadata()

    # 2. Zawsze analizuj znane dane
    candidates = analyze_known_data()

    # 3. Jeśli yt-dlp dało wyniki, uzupełnij/zastąp
    if yt_dlp_videos:
        print(f"\n📊 Analizuję {len(yt_dlp_videos)} filmów z yt-dlp...")
        live_candidates = []
        for v in yt_dlp_videos:
            title = v.get("title", "") or v.get("description", "") or ""
            views = v.get("view_count", 0) or 0
            content_type = detect_content_type(title)
            sc = score_video(v)
            live_candidates.append({
                "tiktok_title":     title[:120],
                "tiktok_url":       v.get("url") or v.get("webpage_url", ""),
                "views_total":      views,
                "views_7d":         0,
                "duration_s":       v.get("duration", 0),
                "likes":            v.get("like_count", 0),
                "comments":         v.get("comment_count", 0),
                "content_type":     content_type,
                "score":            sc,
                "yt_hook":          build_yt_hook(title, content_type),
                "recommended":      views >= 5000,
                "yt_title_formula": get_yt_title_formula(content_type),
            })
        live_candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = live_candidates

    # 4. Wybierz TOP N
    top_candidates = candidates[:TOP_N]

    # 5. Drukuj raport
    print(f"\n🏆 TOP {TOP_N} FILMÓW DO TRANSFERU NA YT SHORTS:")
    print("-" * 60)
    for i, c in enumerate(top_candidates, 1):
        rec = "✅ REKOMENDOWANY" if c.get("recommended") else "📋 rozważ"
        print(f"\n#{i} [{rec}] Score: {c['score']}")
        print(f"  TikTok: {c['tiktok_title'][:70]}")
        print(f"  Views:  {c['views_total']:,} total | Typ: {c['content_type']}")
        print(f"  YT Hook: {c['yt_hook'][:80]}")
        print(f"  YT Format: {c['yt_title_formula']}")

    # 6. Generuj dyrektywę
    directive = generate_adaptation_directive(candidates)
    print(f"\n📋 ADAPTATION DIRECTIVE:\n{directive[:300]}...")

    # 7. Zapisz wyniki
    output = {
        "generated_at":      datetime.now(timezone.utc).isoformat(),
        "channel":           KNOWN_ANALYTICS["channel"],
        "known_analytics":   KNOWN_ANALYTICS,
        "top_candidates":    top_candidates,
        "adaptation_directive": directive,
        "yt_strategy": {
            "hooks":    ["Przed-i-po transformacja", "1 minutowa metamorfoza",
                         "Nie uwierzysz w efekt", "Ta klientka nie poznała się w lustrze"],
            "keywords": ["warkoczyki Świdnica", "afroloki Polska", "panda kucyki",
                         "warkoczyki na lato", "szybka metamorfoza włosy", "salon Świdnica"],
            "filters":  "warm_beauty",
            "music":    "soft elegant background no copyright",
            "cta":      "Link do rezerwacji w opisie | Komentarz 'CHCĘ' = wysyłamy info",
            "publish_hour_utc": 0,
            "publish_day": "czwartek lub piątek",
            "forbidden": ["dark psychology", "manipulacja", "shock tactics", "phonk music"],
        }
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Wyniki zapisane: {OUTPUT_FILE}")

    os.makedirs("accounts", exist_ok=True)
    with open(DIRECTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(directive)
    print(f"✅ Dyrektywa zapisana: {DIRECTIVE_FILE}")

    print("\n📌 NASTĘPNY KROK:")
    print("   python prettywoman_agent.py --download")
    print("   (pobiera TOP filmy z TikToka bez watermark i re-edytuje dla YT)")


if __name__ == "__main__":
    main()
