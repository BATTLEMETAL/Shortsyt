"""
LOL Agent — Smart Titles
Pobiera statystyki istniejących shortów z YouTube i generuje tytuły
na podstawie tego co historycznie działało (CTR, views, retention).
"""
import sys, os, re, pickle, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from googleapiclient.discovery import build
    YOUTUBE_API_OK = True
except ImportError:
    YOUTUBE_API_OK = False

from google import genai

try:
    from lol_agent.lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, ACTION_LABELS
    from lol_agent.lol_title_database import get_few_shot_examples, PROVEN_STYLE_TEMPLATES
except ImportError:
    from lol_config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS, ACTION_LABELS
    from lol_title_database import get_few_shot_examples, PROVEN_STYLE_TEMPLATES

# Medal DB — auto-detection of champion and action type
try:
    from lol_agent.medal_db import get_clip_metadata, parse_medal_title
    MEDAL_DB_OK = True
except ImportError:
    try:
        from medal_db import get_clip_metadata, parse_medal_title
        MEDAL_DB_OK = True
    except ImportError:
        MEDAL_DB_OK = False

TOKEN_PATH = os.path.join(os.path.dirname(__file__), '..', 'accounts', 'lol_token.pickle')
CACHE_PATH = os.path.join(os.path.dirname(__file__), 'yt_perf_cache.json')


# ─── Medal metadata ────────────────────────────────────────────────────────────

def extract_medal_metadata(filepath: str) -> dict:
    """
    Wyciąga metadane klipu z Medal DB (SQLite) lub z nazwy pliku jako fallback.
    Medal DB zawiera tytuł klipu np. 'Pentakill - Katarina' z typem killa i championem.
    """
    # Najpierw próbuj Medal DB (pełne metadane)
    if MEDAL_DB_OK and filepath:
        try:
            db_meta = get_clip_metadata(filepath)
            if db_meta.get("source") == "medal_db" and db_meta.get("title"):
                print(f"🏅 Medal DB: '{db_meta['title']}' → {db_meta['action_type']} | {db_meta['champion']}")
                # Dodaj kompatybilne pola
                db_meta["game"] = "League of Legends"
                # Wyciągnij clip_id z nazwy pliku
                fname = os.path.basename(filepath)
                id_match = re.search(r'trim-(\d+)', fname)
                if id_match:
                    db_meta["clip_id"] = id_match.group(1)
                    db_meta["medal_url"] = f"https://medal.tv/clip/{db_meta['clip_id']}"
                return db_meta
        except Exception as e:
            print(f"⚠️  Medal DB fallback: {e}")

    # Fallback: parsuj nazwę pliku
    fname = os.path.basename(filepath)
    meta = {"game": "League of Legends", "clip_id": None, "timestamp": None,
            "champion": "", "action_type": "outplay", "title": "", "source": "filename"}

    ts_match = re.search(r'(\d{14,17})', fname)
    if ts_match:
        meta["timestamp"] = ts_match.group(1)

    id_match = re.search(r'trim-(\d+)', fname)
    if id_match:
        meta["clip_id"] = id_match.group(1)
        meta["medal_url"] = f"https://medal.tv/clip/{meta['clip_id']}"

    if "LeagueofLegends" in fname or "LeagueOfLegends" in fname:
        meta["game"] = "League of Legends"
    elif "Valorant" in fname:
        meta["game"] = "Valorant"

    return meta


# ─── YouTube Performance ───────────────────────────────────────────────────────

def _get_yt_service():
    """Inicjalizuje klienta YouTube API z zapisanym tokenem."""
    if not YOUTUBE_API_OK:
        return None
    if not os.path.exists(TOKEN_PATH):
        return None
    try:
        with open(TOKEN_PATH, 'rb') as f:
            creds = pickle.load(f)
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        print(f"⚠️  YT API init error: {e}")
        return None


def fetch_channel_shorts_performance(max_results: int = 25) -> list:
    """
    Pobiera listę opublikowanych shortów kanału z widokami.
    Zwraca listę dicts: {title, views, likes, videoId, duration}
    """
    # Sprawdź cache (maks 4h)
    import time
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        if time.time() - cache.get("fetched_at", 0) < 4 * 3600:
            print(f"📦 YT perf cache hit ({len(cache['videos'])} filmów)")
            return cache["videos"]

    yt = _get_yt_service()
    if not yt:
        print("⚠️  Brak tokenu YT — pomijam analizę zasięgów")
        return []

    try:
        # Znajdź channel ID
        ch = yt.channels().list(part='id,snippet', mine=True).execute()
        channel_id = ch['items'][0]['id']
        ch_name = ch['items'][0]['snippet']['title']
        print(f"📺 Kanał: {ch_name}")

        # Pobierz ostatnie filmy
        search = yt.search().list(
            part='id,snippet',
            channelId=channel_id,
            maxResults=max_results,
            order='date',
            type='video'
        ).execute()

        video_ids = [item['id']['videoId'] for item in search.get('items', [])]
        if not video_ids:
            return []

        # Pobierz statystyki
        stats = yt.videos().list(
            part='snippet,statistics,contentDetails',
            id=','.join(video_ids)
        ).execute()

        videos = []
        for item in stats.get('items', []):
            duration_str = item['contentDetails'].get('duration', 'PT0S')
            # Parse ISO 8601 duration — PT1M30S = 90s
            dur_match = re.findall(r'(\d+)([HMS])', duration_str)
            dur_secs = sum(int(v) * {'H': 3600, 'M': 60, 'S': 1}[u] for v, u in dur_match)

            # Filtruj tylko Shorty (<= 60s)
            if dur_secs > 62:
                continue

            sn = item['snippet']
            st = item.get('statistics', {})

            videos.append({
                "videoId": item['id'],
                "title": sn.get('title', ''),
                "views": int(st.get('viewCount', 0)),
                "likes": int(st.get('likeCount', 0)),
                "comments": int(st.get('commentCount', 0)),
                "duration": dur_secs,
                "published": sn.get('publishedAt', ''),
                "url": f"https://youtu.be/{item['id']}"
            })

        # Sortuj po views
        videos.sort(key=lambda x: x['views'], reverse=True)

        # Zapisz cache
        import time as _time
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump({"fetched_at": _time.time(), "videos": videos}, f, ensure_ascii=False, indent=2)

        print(f"✅ Pobrano {len(videos)} shortów z YouTube")
        return videos

    except Exception as e:
        print(f"⚠️  YT fetch error: {e}")
        return []


def get_top_title_patterns(videos: list, top_n: int = 8) -> str:
    """
    Zwraca sformatowany string z najlepszymi tytułami do promptu AI.
    """
    if not videos:
        return "(brak danych z YouTube)"

    top = videos[:top_n]
    lines = []
    for v in top:
        lines.append(f"  - \"{v['title']}\" → {v['views']:,} views ({v['likes']:,} likes)")
    return "\n".join(lines)


def analyze_by_action_type(videos: list) -> dict:
    """
    Analizuje historyczne wyniki YT pogrupowane po typie akcji.
    Szuka słów kluczowych w tytułach, np. 'Triple Kill' → triple.
    
    Returns: {
        'triple': {'count': 8, 'avg_views': 8200, 'best_title': '...', 'best_views': 24420},
        'quadrakill': {'count': 3, 'avg_views': 2100, ...},
    }
    """
    TITLE_PATTERNS = {
        'pentakill': [r'pentakill', r'penta kill', r'penta\b'],
        'quadrakill': [r'quadra\s*kill', r'quadra\b'],
        'triple': [r'triple\s*kill', r'triple\b'],
        'double': [r'double\s*kill', r'double\b'],
        'oneshot': [r'one\s*shot', r'oneshot'],
        'baron': [r'baron'],
        'dragon': [r'dragon', r'drake'],
        'clutch': [r'clutch', r'save', r'steal'],
        'outplay': [r'outplay'],
    }
    
    results = {}
    categorized = set()
    
    for action, patterns in TITLE_PATTERNS.items():
        matched_videos = []
        for v in videos:
            title_lower = v.get('title', '').lower()
            for pat in patterns:
                if re.search(pat, title_lower):
                    matched_videos.append(v)
                    categorized.add(v.get('videoId', ''))
                    break
        
        if matched_videos:
            total_views = sum(v['views'] for v in matched_videos)
            results[action] = {
                'count': len(matched_videos),
                'avg_views': total_views // len(matched_videos),
                'best_views': max(v['views'] for v in matched_videos),
                'best_title': max(matched_videos, key=lambda x: x['views'])['title'],
                'total_views': total_views,
            }
    
    # Niekategoryzowane → 'other'
    uncategorized = [v for v in videos if v.get('videoId', '') not in categorized]
    if uncategorized:
        total = sum(v['views'] for v in uncategorized)
        results['other'] = {
            'count': len(uncategorized),
            'avg_views': total // len(uncategorized),
            'best_views': max(v['views'] for v in uncategorized),
            'best_title': max(uncategorized, key=lambda x: x['views'])['title'],
            'total_views': total,
        }
    
    return results


# ─── Smart Title Generator ─────────────────────────────────────────────────────

def generate_smart_title(
    action_type: str,
    champion_name: str,
    rank: str = "Gold",
    clip_path: str = "",
    language: str = "en",
    kill_context: dict = None,
) -> dict:
    """
    Generates an optimised title based on:
    1. Historical YouTube data (what got the most views)
    2. Medal clip metadata (game, clip_id)
    3. Action type and champion
    """
    # Auto-detect z Medal DB jeśli nie podano champion/action
    medal_meta = extract_medal_metadata(clip_path) if clip_path else {}
    
    # Użyj Medal metadata jeśli parametry nie podane
    if not champion_name and medal_meta.get("champion"):
        champion_name = medal_meta["champion"]
        print(f"🏅 Auto-champion z Medal: {champion_name}")
    if action_type == "outplay" and medal_meta.get("action_type") not in ("outplay", "", None):
        action_type = medal_meta["action_type"]
        print(f"🏅 Auto-action z Medal: {action_type}")

    action_label = ACTION_LABELS.get(action_type, "OUTPLAY").replace("🔥","").replace("⚡","").replace("💥","").replace("🎯","").replace("👑","").strip()

    # Pobierz dane z YouTube
    yt_videos = fetch_channel_shorts_performance()
    top_patterns = get_top_title_patterns(yt_videos)

    # Analiza wyników per typ akcji
    action_perf = analyze_by_action_type(yt_videos)
    
    # Buduj kontekst wyników per action type
    action_perf_text = ""
    if action_perf:
        lines = []
        for act, stats in sorted(action_perf.items(), key=lambda x: -x[1]['avg_views']):
            lines.append(f"  - {act.upper()}: {stats['count']} shorts, avg {stats['avg_views']:,} views, best: {stats['best_views']:,}")
            lines.append(f"    Best title: \"{stats['best_title']}\"")
        action_perf_text = "\n".join(lines)

    medal_context = ""
    if medal_meta.get("title"):
        medal_context = f"Medal title: {medal_meta['title']}"
    elif medal_meta.get("clip_id"):
        medal_context = f"Medal Clip ID: {medal_meta['clip_id']}"

    # Channel summary stats
    total_views = sum(v['views'] for v in yt_videos)
    avg_views = total_views // len(yt_videos) if yt_videos else 0
    best_views = yt_videos[0]['views'] if yt_videos else 0

    few_shot_context = get_few_shot_examples(action_type, limit=6)
    templates_for_action = PROVEN_STYLE_TEMPLATES.get(action_type.lower(), PROVEN_STYLE_TEMPLATES["pentakill"])
    templates_formatted = "\n".join([f"- \"{t.format(Champion=champion_name)}\"" for t in templates_for_action])

    # Buduj blok kontekstu akcji dla promptu
    kc = kill_context or {}
    kill_count    = kc.get("kill_count", 0)
    kill_sequence = kc.get("kill_sequence", [])
    kill_timings  = kc.get("kill_timings", [])
    kill_spread   = kc.get("kill_spread", "unknown")
    game_time     = kc.get("game_time", "")
    clip_duration = kc.get("clip_duration", "")

    # Infer solo/team from kill sequence spread
    if kill_sequence and kill_timings:
        _context_note = f"Kill sequence: {', '.join(kill_sequence)} at {', '.join(kill_timings)}. Spread: {kill_spread}."
    else:
        _context_note = f"No OCR kill data — action detected via motion/VFX analysis."

    # Solo vs teamfight signal based on timing
    if kill_spread != "unknown" and kill_spread != "instant":
        try:
            _spread_val = float(kill_spread.split("s")[0])
            _solo_hint = "rapid solo burst (kills < 3s apart)" if _spread_val < 3.0 else "extended multi-kill (spread over fight)"
        except Exception:
            _solo_hint = ""
    else:
        _solo_hint = "instant burst" if kill_spread == "instant" else ""

    _context_block = f"""NEW CLIP CONTEXT (use this to make the title ACCURATE to the actual situation):
- Action type: {action_label}
- Champion: {champion_name}
- Rank: {rank}
- Kill count: {kill_count if kill_count else 'unknown (OCR missed)'}
- {_context_note}
- Solo/team signal: {_solo_hint}
- Game phase: {game_time if game_time else 'unknown'}
- Clip duration: {clip_duration}
{medal_context}

TITLE ACCURACY RULES (critical — avoid wrong context):
- If game_time is "early game" → jungle skirmishes, invades, early picks (NOT dives/sieges)
- If game_time is "late game" → teamfights, baron/dragon, base defense
- If solo burst < 3s → player outplayed enemies alone (emphasize speed/skill)
- If extended fight → surviving a 1vX → emphasize resilience/clutch
- "Dive" implies enemy tried to tower dive — ONLY use if kill happened under tower
- "Carry" implies multiple enemies killed in teamfight
- Match the title to the REAL situation, not a generic pattern"""

    prompt = f"""You are a YouTube Shorts title & metadata creator for the League of Legends channel 'Dwannellenga'.

!!! CRITICAL RULE: ALL output MUST be 100% in ENGLISH. ZERO Polish words allowed anywhere.
If you write ANY Polish word (roku, nie, jest, tak, który, przez, tego, szans, etc.) the output is INVALID. English ONLY. !!!

REAL PROVEN TOP-PERFORMING TITLES FROM THIS EXACT CHANNEL (sorted by views):
{few_shot_context}

PROVEN TITLE ARCHETYPES FOR {action_label.upper()} ON THIS CHANNEL:
{templates_formatted}

{_context_block}

TASK:
1. Replicate the EXACT tone, brevity, emoji placement, and punchiness of Dwannellenga's top-performing videos.
2. The title MUST be short, engaging, and story-driven — and ACCURATE to the actual clip context above.
3. Do NOT invent overly robotic or generic AI titles like "Pentakill Rampage!".
4. Do NOT use "dive" unless it was actually a tower dive. Use context clues above.

FORBIDDEN PATTERNS:
- Generic "[Champion] Pentakill Rampage!"
- "[Champion]'s Unstoppable [Action]!"
- "[Champion] MELTS Entire Team"
- Any title starting with the champion name followed directly by an action noun
- Titles that don't match the game phase or situation described above

Return ONLY valid JSON (no markdown, no comments):
{{
  "title": "Short punchy title (35-55 chars), matching the style of channel top hits AND accurate to context. ENGLISH ONLY.",
  "description": "Short engaging description (80-120 words) with hype, champion context, and subscription call to action. ENGLISH ONLY.",
  "tags": ["15-20 tags in English, NO # symbol in tags, plain lowercase keywords: league of legends, {champion_name.lower()}, {action_type.lower()}"],
  "hook_text": "3-4 word ALL CAPS overlay (e.g. THEY NEVER SAW IT / NO WAY OUT / 1V5 DEFENSE). ENGLISH ONLY.",
  "why_this_title": "One sentence explaining which top channel video pattern this title matches AND why it fits the actual clip context"
}}"""


    client = genai.Client(api_key=GEMINI_API_KEY)
    models_to_try = GEMINI_FALLBACK_MODELS if "GEMINI_FALLBACK_MODELS" in globals() else [GEMINI_MODEL]

    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            text = response.text.strip()

            # Wyciągnij JSON
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            data = json.loads(text)

            # Strip # from tags — # belongs in description hashtags, NOT in YouTube API tags
            if "tags" in data:
                data["tags"] = [t.lstrip("#").strip() for t in data["tags"] if t.strip()]

            # Wymuś hashtagi w opisie (Gemini często pomija lub daje niepełne)
            try:
                from lol_agent.lol_metadata_generator import _ensure_shorts_tag
            except ImportError:
                from lol_metadata_generator import _ensure_shorts_tag

            data["description"] = _ensure_shorts_tag(
                data.get("description", ""),
                champion_name,
                action_type,
            )

            # Polish language detection — detect common Polish words and retry if found
            POLISH_MARKERS = [
                "roku", "nie ma", "szans", "który", "która", "przez",
                "tego", " jest ", " tak ", "ale ", "czyli", "żeby", "można",
                "kiedy", "każdy", "bardzo", "zawsze", "nigdy", "tylko",
            ]
            title_lower = data.get("title", "").lower()
            hook_lower = data.get("hook_text", "").lower()
            combined = title_lower + " " + hook_lower
            detected_polish = [p for p in POLISH_MARKERS if p in combined]
            if detected_polish:
                print(f"⚠️  Polish detected in output ({detected_polish}) — trying next model / fallback")
                continue

            data["champion"] = champion_name
            data["rank"] = rank
            data["action_type"] = action_type
            data["yt_context"] = {
                "videos_analyzed": len(yt_videos),
                "avg_views": avg_views,
                "best_views": best_views
            }

            print(f"\n✅ Smart title generated ({model_name}):")
            print(f"   📌 {data.get('title', '?')}")
            print(f"   💡 {data.get('why_this_title', '')}")
            print(f"   🏷️  Hook: {data.get('hook_text', '')}")
            return data

        except Exception as e:
            print(f"⚠️  Smart title ({model_name}) error: {e}")
            continue

    print("⚠️  All Gemini models failed — using static metadata fallback")
    try:
        from lol_agent.lol_metadata_generator import generate_metadata
    except ImportError:
        from lol_metadata_generator import generate_metadata
    return generate_metadata(action_type, champion_name, rank)


# ─── CLI Test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("== Smart Title Generator Test ==\n")
    result = generate_smart_title(
        action_type="clutch",
        champion_name="Katarina",
        rank="Gold",
        clip_path=r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4"
    )
    print(f"\n📋 WYNIK KOŃCOWY:")
    print(f"Tytuł: {result.get('title', '?')}")
    print(f"Hook:  {result.get('hook_text', '?')}")
    print(f"Tagi:  {', '.join(result.get('tags', [])[:8])}...")
    print(f"\nAnaliza YT: {result.get('yt_context', {})}")
