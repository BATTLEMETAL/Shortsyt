"""
synapsa_live_trainer.py
=======================
ŻYWY TRENER SYNAPSY — pobiera TERAZ VIRALOWE SHORTY z YouTube API
i generuje z nich gotowe dane szkoleniowe JSONL dla Synapsy (Qwen2.5).

Mechanizm:
1. Łączy się z YT API przez istniejące tokeny kont
2. Wyszukuje TOP viralowe Shorty (7 dni, sort=viewCount) dla każdej niszy
3. Pobiera tytuły, opisy, statystyki (wyświetlenia, lajki)
4. Analizuje co sprawia że dane wideo "eksplodowało" (hook, temat, emocja)
5. Generuje pary (prompt → idealny JSON) i dołącza do training_data.jsonl
6. Opcjonalnie wzbogaca viral_patterns.json o realne dane

Uruchomienie (potrzebny token YT):
    python synapsa_live_trainer.py
    python synapsa_live_trainer.py --konto brainrot --max 10
    python synapsa_live_trainer.py --obie-nisze --max 15 --dry-run
"""

import os
import sys
import json
import re
import pickle
import argparse
from datetime import datetime, timezone, timedelta

# =============================================================================
# === PATCH Python 3.13 / google.api_core ===
# google.api_core wywołuje importlib.metadata.packages_distributions() które
# w Python 3.13 może crashować przez dist.files = None (zmiana w pathlib).
# Ten patch musi być PRZED importem googleapiclient.
# =============================================================================
import importlib.metadata as _imd

if not hasattr(_imd, "packages_distributions") or True:
    # Zastąp failującą implementację bezpieczną wersją
    def _safe_packages_distributions():
        result = {}
        try:
            for dist in _imd.distributions():
                try:
                    pkg_name = dist.metadata.get("Name", "")
                    if not pkg_name:
                        continue
                    files = dist.files  # może być None w Py 3.13
                    if not files:
                        continue
                    for f in files:
                        try:
                            top = f.parts[0] if f.parts else None
                            if top and not top.endswith((".dist-info", ".data")):
                                result.setdefault(top, []).append(pkg_name)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        return result

    _imd.packages_distributions = _safe_packages_distributions
# =============================================================================

from googleapiclient.discovery import build
from google.auth.transport.requests import Request



# =============================================================================
# === KONFIGURACJA NISZ ===
# =============================================================================

NICHE_CONFIG = {
    "brainrot": {
        "token":       "accounts/brainrot_token.pickle",
        "lang":        "pl",
        "rule":        (
            "[DYREKTYWA KANAŁU: BRAINROT - JĘZYK POLSKI]\n"
            "ZASADA 1 [HOOK]: Zacznij natychmiast od szokującego pytania lub absurdalnego faktu.\n"
            "ZASADA 2 [LOOP]: Ostatnie zdanie musi być urwane tak, by łączyło się z pierwszym.\n"
            "ZASADA 3 [GRAMATYKA]: 100% poprawny gramatycznie tekst do lektora. ZERO nawiasów [].\n"
            "ZASADA 4 [DŁUGOŚĆ]: Dokładnie 80-120 słów. Nie za długo, nie za krótko."
        ),
        "searches": [
            "brainrot polska funny viral",
            "roblox ohio sigma brainrot shorts",
            "polska brainrot compilation 2026",
            "skibidi ohio sigma rizz viral polska",
            "brainrot shorts polskie viral 2026",
        ],
        "music_folder": "brainrot",
        "bg_default":   "subway surfers gameplay no copyright 4k vertical",
    },
    "dark_mindset": {
        "token":       "accounts/dark_mindset_token.pickle",
        "lang":        "en",
        "rule":        (
            "[DYREKTYWA KANAŁU: DARK MINDSET - JĘZYK ANGIELSKI]\n"
            "ZASADA 1 [HOOK]: Start with a cold, psychological punch. No 'welcome back'.\n"
            "ZASADA 2 [LOOP]: End mid-sentence so it loops back to the beginning seamlessly.\n"
            "ZASADA 3 [PURITY]: Pure narration text ONLY. English only. Zero brackets, zero stage directions.\n"
            "ZASADA 4 [LENGTH]: Exactly 80-120 words. Direct, cold, commanding."
        ),
        "searches": [
            "dark psychology secrets viral shorts",
            "manipulation tactics psychology shorts 2026",
            "sigma mindset cold psychology viral",
            "dark psychology shorts 10 million views",
            "psychology manipulation viral 2025 2026",
        ],
        "music_folder": "dark_mindset",
        "bg_default":   "dark rainy city night noir cinematic no copyright 4k",
    },
}

# Stałe pliki wyjściowe
TRAINING_FILE = "accounts/training_data.jsonl"
VIRAL_PATTERNS_FILE = "accounts/viral_patterns.json"
LIVE_CONTEXT_FILE = "accounts/live_viral_context.json"


# =============================================================================
# === AUTORYZACJA ===
# =============================================================================

def get_youtube(konto: str):
    """Autoryzacja przez pickle token. Obsługa invalid_grant przez re-auth."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cfg = NICHE_CONFIG[konto]
    token_path = cfg["token"]
    CLIENT_SECRETS = "client_secret.json"
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
    ]

    # Wczytaj istniejący token
    creds = None
    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    # Spróbuj odświeżyć
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            err_str = str(e).lower()
            if "invalid_grant" in err_str or "bad request" in err_str:
                print(f"  ⚠️  Token dla '{konto}' wygasł (invalid_grant).")
                print(f"     Usuwam stary token i uruchamiam re-autoryzację przez przeglądarkę...")
                os.remove(token_path)
                creds = None  # wymusi nowy flow poniżej
            else:
                print(f"  ⚠️  Błąd odświeżania tokenu: {e}")
                return None

    # Nowy flow OAuth (przeglądarka)
    if not creds or not creds.valid:
        if not os.path.exists(CLIENT_SECRETS):
            print(f"  ❌ Brak {CLIENT_SECRETS}! Pobierz z Google Cloud Console.")
            return None
        print(f"  🌐 Otwieram przeglądarkę dla konta '{konto}' — zaloguj się na właściwe konto Google...")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent select_account")
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)
        print(f"  ✅ Nowy token zapisany: {token_path}")

    return build("youtube", "v3", credentials=creds)



# =============================================================================
# === POBIERANIE WIRALOWYCH SHORTÓW ===
# =============================================================================

def fetch_viral_shorts(youtube, query: str, max_results: int = 10,
                       days_back: int = 7) -> list[dict]:
    """
    Pobiera TOP viralowe Shorty z YT dla danego zapytania.
    Zwraca listę słowników z tytułem, opisem, statystykami.
    """
    publishedAfter = (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # Krok 1: Szukaj shortsów
        search_resp = youtube.search().list(
            q=f"{query} #shorts",
            part="snippet",
            type="video",
            videoDuration="short",
            order="viewCount",
            maxResults=max_results,
            publishedAfter=publishedAfter,
        ).execute()

        items = search_resp.get("items", [])
        if not items:
            return []

        # Krok 2: Pobierz statystyki dla każdego wideo
        video_ids = [item["id"]["videoId"] for item in items
                     if item.get("id", {}).get("videoId")]

        stats_resp = youtube.videos().list(
            part="statistics,snippet,contentDetails",
            id=",".join(video_ids)
        ).execute()

        results = []
        for item in stats_resp.get("items", []):
            snip  = item.get("snippet", {})
            stats = item.get("statistics", {})
            vid_id = item.get("id", "")

            views    = int(stats.get("viewCount",    0))
            likes    = int(stats.get("likeCount",    0))
            comments = int(stats.get("commentCount", 0))
            title    = snip.get("title", "")
            desc     = snip.get("description", "")[:200]
            channel  = snip.get("channelTitle", "")

            # Engagement rate
            engagement = round(likes / max(views, 1) * 100, 2)

            results.append({
                "video_id":   vid_id,
                "title":      title,
                "channel":    channel,
                "description": desc,
                "views":      views,
                "likes":      likes,
                "comments":   comments,
                "engagement": engagement,
                "url":        f"https://youtube.com/shorts/{vid_id}",
            })

        # Sortuj po wyświetleniach malejąco
        results.sort(key=lambda x: x["views"], reverse=True)
        return results

    except Exception as e:
        print(f"  ⚠️  fetch_viral_shorts error: {e}")
        return []


# =============================================================================
# === ANALIZA HEURYSTYCZNA POTENCJAŁU WIRALU ===
# =============================================================================

def analyze_hook_pattern(title: str, lang: str = "pl") -> dict:
    """
    Analizuje tytuł i wyciąga wzorce hookowe.
    Zwraca diagnozę: typ hooka, emocja, kluczowe słowo.
    """
    title_lower = title.lower()

    # Polskie wzorce hookowe
    pl_hooks = {
        "szok_faktu":       ["nie wiedziałeś", "nikt ci nie mówi", "serio", "prawda o", "sekret"],
        "absurd_gaming":    ["ohio", "sigma", "roblox", "minecraft", "skibidi", "brainrot"],
        "emocja_smiechu":   ["😂", "💀", "😭", "xd", "lmao", "haha", "kiedy"],
        "challenge":        ["nie możesz", "spróbuj", "nie dasz rady", "impossible"],
        "pov":              ["pov:", "jak to jest", "wyobraź sobie"],
        "kontrowersja":     ["dlaczego", "problem z", "koniec", "zniknie", "zakazane"],
    }

    # Angielskie wzorce hookowe
    en_hooks = {
        "dark_revelation":  ["they don't", "nobody tells", "secret", "truth", "dark", "dangerous"],
        "social_dynamics":  ["manipulation", "respect", "power", "control", "dominance", "silence"],
        "identity":         ["sigma", "alpha", "real", "weak", "strong", "mindset"],
        "shock_stat":       ["study shows", "scientists found", "research", "fact:"],
        "direct_address":   ["you need", "stop doing", "if you", "watch what", "the moment"],
    }

    hooks = pl_hooks if lang == "pl" else en_hooks
    detected = []

    for hook_type, keywords in hooks.items():
        for kw in keywords:
            if kw in title_lower or kw in title:
                detected.append(hook_type)
                break

    # Sprawdź emoji obecność (pozytywna)
    has_emoji = bool(re.search(r'[^\x00-\x7F]', title))
    has_number = bool(re.search(r'\d', title))
    has_question = "?" in title
    length_ok = 20 <= len(title) <= 70

    return {
        "detected_hooks":  list(set(detected)),
        "has_emoji":       has_emoji,
        "has_number":      has_number,
        "has_question":    has_question,
        "title_length_ok": length_ok,
        "hook_count":      len(set(detected)),
    }


def compute_viral_score(video: dict, lang: str = "pl") -> int:
    """Oblicza viral score 1-10 na podstawie realnych danych."""
    views    = video.get("views", 0)
    likes    = video.get("likes", 0)
    comments = video.get("comments", 0)
    engagement = video.get("engagement", 0.0)

    score = 5  # baza

    # Wyświetlenia
    if views > 5_000_000:   score += 3
    elif views > 1_000_000: score += 2
    elif views > 100_000:   score += 1
    elif views < 10_000:    score -= 2

    # Engagement
    if engagement > 5.0:  score += 1
    elif engagement < 0.5: score -= 1

    # Komentarze (high controversy = viral)
    if comments > 1000: score += 1

    # Hook analiza
    hook = analyze_hook_pattern(video.get("title", ""), lang)
    if hook["hook_count"] >= 2: score += 1
    if hook["has_emoji"]: score += 0.5

    return max(1, min(10, int(score)))


# =============================================================================
# === GENERATOR PRZYKŁADÓW SZKOLENIOWYCH ===
# =============================================================================

def video_to_training_example(video: dict, niche: str, cfg: dict,
                               similar_videos: list[dict]) -> dict | None:
    """
    Konwertuje jeden viralowy film z YT na parę szkoleniową.
    """
    title      = video.get("title", "")
    desc       = video.get("description", "")
    views      = video.get("views", 0)
    channel    = video.get("channel", "")
    lang       = cfg["lang"]
    viral_score = compute_viral_score(video, lang)

    if views < 5000:  # pomiń wideo z za małym ruchem
        return None

    hook_info = analyze_hook_pattern(title, lang)

    # Kontekst: podobne filmy jako trending reference
    context_lines = [
        f"[TREND] {v['title']} | {v['views']:,} views | Kanał: {v['channel']}"
        for v in similar_videos[:5]
    ]

    # Zbuduj "ideal" output inspirowany tym wiralowym wideo
    # Nie kopiujemy techstu - budujemy wzorzec z analizy
    hook_types   = hook_info.get("detected_hooks", ["szok_faktu"])
    hook_type_str = ", ".join(hook_types) if hook_types else "szok_faktu"

    if lang == "pl":
        script_inspiration = (
            f"[WZORZEC Z TRENDU] Tytuł '{title}' osiągnął {views:,} wyświetleń. "
            f"Typ hooka: {hook_type_str}. "
            f"Engagement: {video.get('engagement', 0):.1f}%. "
            f"Wygeneruj NOWY, ORYGINALNY skrypt w tym samym klimacie ale z inną historią."
        )
        background_vibe = cfg["bg_default"]
        # Dopasuj tło do tytułu
        if "roblox" in title.lower():
            background_vibe = "roblox obby gameplay no copyright funny vertical"
        elif "minecraft" in title.lower():
            background_vibe = "minecraft parkour no copyright satisfying vertical"
        elif "subway" in title.lower():
            background_vibe = "subway surfers gameplay no copyright 4k vertical"
    else:
        script_inspiration = (
            f"[TREND PATTERN] Title '{title}' got {views:,} views. "
            f"Hook type: {hook_type_str}. "
            f"Engagement: {video.get('engagement', 0):.1f}%. "
            f"Generate NEW, ORIGINAL script in the same vibe but with different angle."
        )
        background_vibe = cfg["bg_default"]
        if "city" in title.lower() or "rain" in title.lower():
            background_vibe = "dark rainy city cinematic no copyright 4k"
        elif "office" in title.lower() or "sigma" in title.lower():
            background_vibe = "sigma male dark office cinematic no copyright"

    vs_note = (
        f"Uczę się od: '{title[:50]}' ({views:,} views). "
        f"Hook types: {hook_type_str}. Engagement: {video.get('engagement',0):.1f}%."
    )

    ideal_output = {
        "viral_score":     viral_score,
        "vs_top_shorts":   vs_note,
        "viral_reasoning": (
            f"Wzorzec z trendu: {hook_type_str}. "
            + ("Polskie brainrot + absurd gaming." if lang == "pl"
               else "Dark psychology recognition hook. Viewer feels seen.")
        ),
        "script_text":     (
            "[DO GENERACJI przez fine-tuned model — bazuje na wzorcu trendu powyżej]"
            if lang == "pl" else
            "[TO BE GENERATED by fine-tuned model — based on trend pattern above]"
        ),
        "background_vibe": background_vibe,
        "music_folder":    cfg["music_folder"],
        "title":           f"[INSPIRACJA: {title[:40]}...] #shorts",
        "description":     (
            desc[:100] + "... #shorts #viral" if desc
            else f"#{niche.replace('_', '')} #shorts #viral"
        ),
        "seo_tags": (
            ["brainrot", "ohio", "sigma", "polska", "shorts", "viral", "gaming"]
            if lang == "pl" else
            ["dark psychology", "manipulation", "mindset", "sigma", "shorts", "viral"]
        ),
    }

    # Buduj prompt instrukcję
    prompt = (
        f"### Instruction:\n"
        f"Jesteś Master Director AI generującym skrypty YouTube Shorts.\n\n"
        f"Nisza: {niche.replace('_', ' ')}\n"
        f"Dyrektywa kanału: {cfg['rule'][:300]}\n\n"
        f"Kontekst trendów (TOP wideo z ostatnich 7 dni — REALNE DANE YouTube):\n"
        + "\n".join(context_lines) +
        f"\n\nAnaliza wzorca wiralu:\n{script_inspiration}\n\n"
        f"Wygeneruj TYLKO poprawny JSON wg schematu. Zero słów poza JSON.\n\n"
        f"### Response:"
    )

    return {
        "text":        f"{prompt}\n{json.dumps(ideal_output, ensure_ascii=False)}",
        "instruction": prompt,
        "output":      json.dumps(ideal_output, ensure_ascii=False),
        "metadata": {
            "niche":          niche,
            "source":         "live_youtube_trend",
            "video_id":       video.get("video_id", ""),
            "original_title": title,
            "original_views": views,
            "viral_score":    viral_score,
            "hook_types":     hook_types,
            "fetched_at":     datetime.utcnow().isoformat(),
        }
    }


# =============================================================================
# === AKTUALIZACJA viral_patterns.json ===
# =============================================================================

def update_viral_patterns(niche: str, videos: list[dict]):
    """Aktualizuje viral_patterns.json o realne dane z YT."""
    patterns = {}
    if os.path.exists(VIRAL_PATTERNS_FILE):
        try:
            with open(VIRAL_PATTERNS_FILE, "r", encoding="utf-8") as f:
                patterns = json.load(f)
        except:
            pass

    top3 = sorted(videos, key=lambda x: x["views"], reverse=True)[:3]
    avg_views = sum(v["views"] for v in videos) // max(len(videos), 1)

    patterns[niche] = {
        "updated":    datetime.utcnow().isoformat(),
        "top_videos": [{"title": v["title"], "views": v["views"],
                        "likes": v["likes"], "url": v["url"]} for v in top3],
        "avg_views":  avg_views,
        "total_analyzed": len(videos),
    }

    with open(VIRAL_PATTERNS_FILE, "w", encoding="utf-8") as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)

    print(f"  💾 viral_patterns.json zaktualizowany dla '{niche}' "
          f"(avg: {avg_views:,} views, top: {top3[0]['views']:,} views)")


# =============================================================================
# === GŁÓWNA LOGIKA ===
# =============================================================================

def run_live_trainer(konto: str, max_per_query: int = 8, dry_run: bool = False,
                     days_back: int = 7, append: bool = True):
    """Pobiera trendy i generuje dane szkoleniowe dla danego konta/niszy."""
    cfg = NICHE_CONFIG[konto]

    print(f"\n{'='*64}")
    print(f"🧠 SYNAPSA LIVE TRAINER — Pobieranie trendów dla: @{konto.upper()}")
    print(f"   Zapytań: {len(cfg['searches'])} | Max/zapytanie: {max_per_query} | "
          f"Zakres: {days_back} dni | Dry run: {dry_run}")
    print(f"{'='*64}")

    # 1. Autoryzacja YT
    youtube = get_youtube(konto)
    if not youtube:
        print(f"  ❌ Nie można połączyć się z YouTube. Sprawdź token.")
        return 0

    # 2. Pobierz viralowe shorty dla każdego zapytania
    all_videos = []
    seen_ids = set()

    for i, query in enumerate(cfg["searches"], 1):
        print(f"\n  [{i}/{len(cfg['searches'])}] Szukam: '{query}'...")
        videos = fetch_viral_shorts(youtube, query, max_results=max_per_query,
                                    days_back=days_back)

        new_vids = []
        for v in videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                new_vids.append(v)

        print(f"    ✅ Znaleziono {len(new_vids)} unikalnych wiralowych shortów")
        for v in new_vids[:3]:
            print(f"       👁 {v['views']:>8,} | 👍 {v['likes']:>6,} | "
                  f"📊 {v['engagement']:.1f}% | 📝 {v['title'][:55]}")

        all_videos.extend(new_vids)

    print(f"\n{'='*64}")
    print(f"📊 ŁĄCZNIE ZEBRANYCH FILMÓW: {len(all_videos)}")

    if not all_videos:
        print("  ⚠️  Brak wyników. Możliwe przyczyny: quota API, brak tokenów, błąd sieci.")
        return 0

    # 3. Aktualizuj viral_patterns.json
    if not dry_run:
        update_viral_patterns(konto, all_videos)

    # 4. Generuj przykłady szkoleniowe
    print(f"\n🔨 Generuję przykłady szkoleniowe...")
    examples = []
    skipped = 0

    for video in all_videos:
        ex = video_to_training_example(
            video=video,
            niche=konto,
            cfg=cfg,
            similar_videos=all_videos,  # przekazujemy cały kontekst
        )
        if ex:
            examples.append(ex)
        else:
            skipped += 1

    print(f"  ✅ Wygenerowano: {len(examples)} przykładów")
    if skipped:
        print(f"  ⏭️  Pominięto: {skipped} (za mało wyświetleń < 5k)")

    if not examples:
        return 0

    # 5. Pokaż top 3 przykłady
    print(f"\n  🏆 TOP 3 wideo wg wyświetleń (nowe dane treningowe):")
    top3 = sorted(all_videos, key=lambda x: x["views"], reverse=True)[:3]
    for rank, v in enumerate(top3, 1):
        hook = analyze_hook_pattern(v["title"], cfg["lang"])
        print(f"\n  #{rank} [{v['views']:,} views | engagement {v['engagement']:.1f}%]")
        print(f"     Tytuł: {v['title'][:70]}")
        print(f"     Kanał: {v['channel']}")
        print(f"     Hook types: {', '.join(hook['detected_hooks']) or 'brak wykrytych'}")
        print(f"     Emoji: {hook['has_emoji']} | Pytanie: {hook['has_question']}")
        print(f"     🔗 {v['url']}")

    # 6. Zapisz do JSONL (append lub nowy plik)
    if dry_run:
        print(f"\n  [DRY RUN] Nie zapisuję. Wygenerowano by {len(examples)} przykładów.")
        return len(examples)

    mode = "a" if append and os.path.exists(TRAINING_FILE) else "w"
    action = "Dołączam do" if mode == "a" else "Tworzę"
    with open(TRAINING_FILE, mode, encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n  💾 {action} {TRAINING_FILE} — dodano {len(examples)} linii")

    # 7. Zapisz także kontekst live do użycia przez auto_cashcow (jako gotowy kontekst virali)
    live_ctx = {
        "niche": konto,
        "fetched_at": datetime.utcnow().isoformat(),
        "videos": [{"title": v["title"], "views": v["views"],
                    "channel": v["channel"]} for v in all_videos[:20]]
    }
    ctx_path = LIVE_CONTEXT_FILE.replace(".json", f"_{konto}.json")
    with open(ctx_path, "w", encoding="utf-8") as f:
        json.dump(live_ctx, f, indent=2, ensure_ascii=False)
    print(f"  📡 Kontekst live zapisany: {ctx_path} (używany przez one_click_cashcow)")

    return len(examples)


# =============================================================================
# === LICZNIK PRZYKŁADÓW W PLIKU ===
# =============================================================================

def count_jsonl_examples(file_path: str) -> dict:
    """Zlicza przykłady w pliku JSONL po źródle."""
    if not os.path.exists(file_path):
        return {}
    counts = {}
    total = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
                src = ex.get("metadata", {}).get("source", "unknown")
                counts[src] = counts.get(src, 0) + 1
                total += 1
            except:
                pass
    counts["TOTAL"] = total
    return counts


# =============================================================================
# === MAIN ===
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Synapsa Live Trainer — Pobiera viralowe trendy z YT i tworzy dane szkoleniowe"
    )
    parser.add_argument("--konto",      type=str, default=None,
                        choices=list(NICHE_CONFIG.keys()),
                        help="Konto do trenowania (brainrot / dark_mindset)")
    parser.add_argument("--obie-nisze", action="store_true",
                        help="Uruchom dla OBU nisz")
    parser.add_argument("--max",        type=int, default=8,
                        help="Max wyników na zapytanie (default: 8)")
    parser.add_argument("--days",       type=int, default=7,
                        help="Zakres dni wstecz (default: 7)")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Analiza bez zapisywania")
    parser.add_argument("--reset",      action="store_true",
                        help="Wyczyść plik JSONL przed dopisaniem")
    args = parser.parse_args()

    print("\n" + "=" * 64)
    print("🧬 SYNAPSA LIVE TRAINER — Start")
    print(f"   Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Plik wyjściowy: {TRAINING_FILE}")
    print("=" * 64)

    os.makedirs("accounts", exist_ok=True)

    # Opcja reset pliku
    if args.reset and os.path.exists(TRAINING_FILE):
        os.remove(TRAINING_FILE)
        print(f"🗑️  Wyczyszczono {TRAINING_FILE}")

    # Wybór kont
    if args.obie_nisze:
        konta = list(NICHE_CONFIG.keys())
    elif args.konto:
        konta = [args.konto]
    else:
        # Domyślnie: oba konta jeśli mają tokeny
        konta = [k for k in NICHE_CONFIG if os.path.exists(NICHE_CONFIG[k]["token"])]
        if not konta:
            print("❌ Brak tokenów! Uruchom: python authorize_channel.py --konto brainrot")
            sys.exit(1)
        print(f"  🔑 Automatycznie wykryto konta z tokenami: {konta}")

    # Główna pętla
    total_generated = 0
    for konto in konta:
        n = run_live_trainer(
            konto=konto,
            max_per_query=args.max,
            dry_run=args.dry_run,
            days_back=args.days,
            append=True,
        )
        total_generated += n

    # Podsumowanie
    print(f"\n{'='*64}")
    print(f"🎉 LIVE TRAINER ZAKOŃCZONY")
    print(f"   Wygenerowanych przykładów szkoleniowych: {total_generated}")

    if not args.dry_run and os.path.exists(TRAINING_FILE):
        stats = count_jsonl_examples(TRAINING_FILE)
        print(f"\n  📊 Stan pliku {TRAINING_FILE}:")
        for source, count in sorted(stats.items()):
            print(f"     {source:<28} : {count} przykładów")

    print(f"\n  📌 Następny krok: fine-tuning Synapsy:")
    print(f"     python synapsa_benchmark.py --runs 4 --verbose  (przed)")
    print(f"     # Uruchom fine-tuning Unsloth w venv Synapsy")
    print(f"     python synapsa_benchmark.py --runs 4 --verbose  (po)")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
