import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Wymuszenie UTF-8 na stdout/stderr (Windows CP1250 nie obsługuje emoji)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from data_collector import get_authenticated_service
from cashcow_generator import generate_cashcow_from_text, CHANNELS_NICHES
from synapsa_bridge import generate_viral_script_with_synapsa

# ==============================================================================
# === KONFIGURACJA AGENTA: DARK PSYCHOLOGY
# ==============================================================================
PROFILE_NAME = "dark_mindset"
NICHE_BASE = "psychology facts human behavior social dynamics"
DAILY_QUOTA = 2
TOPIC_HISTORY_FILE = "accounts/topic_history.json"
PUBLISH_REPORT_FILE = "publish_report.json"

# ===== STAŁE BAZOWE TAGI DARK PSYCHOLOGY =====
BASE_VIRAL_TAGS = [
    # SHORT (branded / high-volume)
    "psychologyfacts", "mindset", "subconscious", "behavior",
    "psychology", "bodylanguage", "socialdynamics", "persuasion",
    "sigma", "alpha", "stoicism", "socialintelligence",
    "humanbehavior", "communication", "power", "secrets", "shorts",
    "viral", "fyp", "trending", "psychologyshorts",
    # LONG-TAIL (niche discovery — algorytm tłumaczy kontekst wideo)
    "psychologytricks", "psychologyfactshuman",
    "mindcontrolsecrets", "persuasiontechniques",
    "humanbehaviorpsychology", "socialsecrets",
    "psychologyhacks", "howtoreadpeople", "sigmarules",
    "psychologyexplained", "subconsciousinfluence"
]

# Obowiązkowy hashtag block do opisu (SEO YouTube)
BASE_HASHTAG_BLOCK = "#psychology #humanbehavior #mindset #psychologyfacts #sigma #power #secrets #shorts #viral"


def build_hashtag_block(tags: list) -> str:
    """Buduje blok hashtagów z listy tagów + bazowych hashtagów niszy."""
    ai_hashtags = [f"#{t.strip().replace(' ', '').replace('#', '')}" for t in tags[:8] if t.strip()]
    combined = list(dict.fromkeys(ai_hashtags))  # dedup z zachowaniem kolejności
    # Dołącz bazowe jeśli ich brakuje
    for base_tag in BASE_HASHTAG_BLOCK.split():
        if base_tag.lower() not in [h.lower() for h in combined]:
            combined.append(base_tag)
    return " ".join(combined[:15])  # YouTube wysyła pierwsze 15 jako kategorie


def log_publish_report(title: str, video_index: int, tagi: list, privacy: str, video_id: str = None):
    """Loguje udaną publikację do publish_report.json (wymagane przez audyt)."""
    report = []
    if os.path.exists(PUBLISH_REPORT_FILE):
        try:
            with open(PUBLISH_REPORT_FILE, "r", encoding="utf-8") as f:
                report = json.load(f)
            if not isinstance(report, list):
                report = []
        except:
            report = []
    report.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "video_index": video_index,
        "tags_count": len(tagi),
        "privacy": privacy,
        "agent": PROFILE_NAME,
        "video_id": video_id
    })
    with open(PUBLISH_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    print(f"📋 [PUBLISH REPORT] Wpis dodany do {PUBLISH_REPORT_FILE}.")

def search_viral_shorts(youtube, query: str, count: int = 5):
    """Skanuje trendy i szuka zapytania by dostarczyć kontekst z ostatnich 7 dni."""
    print(f"\n🌍 [DARK PSYCHOLOGY AGENT] Skanowanie trendów na świecie: '{query}'...")
    try:
        search_query = f"{query} #shorts"
        ostatni_tydzien = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        search_response = youtube.search().list(
            q=search_query,
            part="snippet",
            maxResults=count,
            type="video",
            videoDuration="short",
            order="viewCount",
            publishedAfter=ostatni_tydzien
        ).execute()

        viral_data = []
        for item in search_response.get("items", []):
            title = item["snippet"]["title"]
            desc = item["snippet"]["description"]
            viral_data.append(f"TYTUŁ: {title} | OPIS: {desc[:100]}...")
            
        print(f"✅ Znaleziono {len(viral_data)} hitów nakręcających wyświetlenia w przeciągu ostatnich 7 dni.")
        return viral_data
    except Exception as e:
        print(f"❌ Błąd skanowania API YouTube: {e}")
        return ["Brak danych z YouTube, przejdź do improwizacji z mrocznej psychologii."]

def generate_viral_script(viral_context, niche_topic, channel_rule, forbidden_topics=None):
    """Zapytanie do Synapsy z dyrektywami Dark Psychology."""
    return generate_viral_script_with_synapsa(viral_context, niche_topic, channel_rule, forbidden_topics)

def get_forbidden_topics(profile_name: str, limit: int = 15) -> list:
    """Returns titles + script keywords from history so AI avoids ALL previously used content."""
    if not os.path.exists(TOPIC_HISTORY_FILE):
        return []
    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_history = data.get(profile_name, [])
        recent = profile_history[-limit:]
        forbidden = []
        for item in recent:
            if item.get("title"):
                forbidden.append(item["title"])
            if item.get("script_keywords"):
                forbidden.extend(item["script_keywords"])
        return list(dict.fromkeys(forbidden))  # deduplicate
    except:
        return []

def add_to_history(profile_name: str, title: str, script_text: str = ""):
    if not title: return
    data = {}
    if os.path.exists(TOPIC_HISTORY_FILE):
        try:
            with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
    if profile_name not in data:
        data[profile_name] = []
    
    # Extract meaningful keywords from script for content-level deduplication
    import re as _re
    stopwords = {'the', 'and', 'is', 'it', 'in', 'to', 'a', 'of', 'this', 'you', 'they', 'your',
                 'for', 'with', 'not', 'at', 'are', 'or', 'but', 'their', 'will', 'that', 'when'}
    script_keywords = []
    if script_text:
        words = _re.findall(r'[a-zA-Z]{4,}', script_text.lower())  # 4+ char words only
        script_keywords = [w for w in words if w not in stopwords][:10]
    
    data[profile_name].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "script_keywords": script_keywords
    })
    
    data[profile_name] = data[profile_name][-50:]  # Keep last 50
    
    with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def run_dark_agent_cycle(video_index: int, total_videos: int, youtube):
    """Pojedynczy cykl generacji i publikacji dla Dark Psychology."""
    print("\n" + "="*70)
    print(f"🌑 DARK PSYCHOLOGY AGENT: Generowanie filmu {video_index}/{total_videos}")
    print("="*70)
    
    import dynamic_pattern_agent
    
    # Rozszerzanie zapytania jeśli tworzymy drugi film, by nie był identyczny jak pierwszy
    search_topic = NICHE_BASE
    if video_index == 2:
        search_topic = "dark psychology mind control body language"
        print(f"💡 Szukanie inspiracji w pobocznych niszach na 2-gi film: {search_topic}")
        # FAZA 4: Dynamic Content Adaptation (Real-Time Override z MicroEVS Wideo 1)
        import real_time_monitor_agent
        
        # Docelowo pobiera z YouTube Analytics na podstawie ID ostatniego wideo
        live_micro_evs = real_time_monitor_agent.get_latest_video_micro_evs(PROFILE_NAME)  
        
        # Pobieranie Tytułu (Hooka) ostatniego wideo
        previous_hook = "Have you noticed how some people seem to effortlessly command respect?"
        try:
            with open(PUBLISH_REPORT_FILE, "r", encoding="utf-8") as f:
                rep_data = json.load(f)
                if rep_data:
                    for item in reversed(rep_data):
                        if item.get("agent") == PROFILE_NAME:
                            previous_hook = item.get("title", previous_hook)
                            break
        except Exception:
            pass

        state, directive = dynamic_pattern_agent.get_adaptation_directive(live_micro_evs, search_topic, previous_hook)
        os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"] = directive
        # Puste dla Wideo 1
        os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"] = ""

    viral_context = search_viral_shorts(youtube, search_topic, count=5)
    
    # Pamięć AI
    forbidden_topics = get_forbidden_topics(PROFILE_NAME)
    if forbidden_topics:
        print(f"🧠 [PAMIĘĆ DEDUPLIKACJI] Zabezpieczono starych tematów: {len(forbidden_topics)}")
    niche_rule = CHANNELS_NICHES.get(
        PROFILE_NAME, {}).get(
        'prompt',
        """CREATE A VIRAL PSYCHOLOGY YOUTUBE SHORT (40-70 WORDS)

CRITICAL RULES:
1. STRONG HOOK (First 2 seconds): Start with a direct question or a powerful, shocking statement directed at the viewer to grab attention instantly.
2. NATURAL TITLE: The [TITLE] MUST be a natural, intriguing question or strong statement. ABSOLUTELY NO keyword stuffing (do not use "secrets facts manipulation").
3. STORYTELLING & FACTS: Blend historical facts or storytelling with practical psychology lessons.
4. CALL TO ACTION (COMMENTS): Ask the viewers a specific question to drive comments right before the loop. (e.g., "Have you experienced this? Tell me in the comments.").
5. YOU MUST USE A PERFECT LOOP: The last word of your script MUST connect seamlessly into the first word of your script.
6. NEVER use the word 'forehead'. Choose a completely fresh, NEW concept each time.

EXAMPLE SCRIPT STRUCTURE (Follow this exact style):
[TITLE]
Have you ever fallen for the Benjamin Franklin effect? 🧠
[SCRIPT]
Have you ever fallen for the Benjamin Franklin effect? It's a dark truth about making people like you. Instead of doing favors for them, ask them to do a small favor for you. Their brain will subconsciously convince them they like you. Has this ever worked on you? Tell me in the comments if you...
[TAGS]
darkpsychology, manipulation, psychology, mindset, viral"""
    )
    
    # 3 próby na Synapsie (Anti-Short-Script Loop)
    director_json = {}
    for probe in range(3):
        print(f"🎬 Synapsa Próba #{probe+1}/3: Incepcja Reżysera Mrocznej Psychologii (15s Max)...")
        director_json = generate_viral_script(viral_context, search_topic, niche_rule, forbidden_topics)
        if director_json and "error" in director_json:
            print(f"🔴 BŁĄD PODSYSTEMU SYNAPSA: {director_json['error']}")
        
        script_text = director_json.get('script_text', '')
        script_len = len(script_text.split())
        
        if 30 <= script_len <= 90: 
            print(f"✅ Skrypt IDEALNY ({script_len} słów) z miejscem na Loop/CTA.")
            break
        elif script_len > 90:
            print(f"⚠️  Skrypt za DŁUGI ({script_len} słów). Regeneracja!")
        else:
            print(f"⚠️  Skrypt za KRÓTKI (lub błąd JSON) ({script_len} słów - brakuje CTA/Loop). Regeneracja!")

    script_text = director_json.get('script_text', '')
    if not script_text.strip() or len(script_text.split()) < 20 or len(script_text.split()) > 100:
        import random
        # Ultra short fallbacks — diverse topics, NEVER repeated tricks
        fbs = [
            "Silence is your most powerful weapon. The moment you stop explaining yourself, they lose control over you. Use it. Want part 2?",
            "Your micro-expressions betray you before you speak. Liars unconsciously touch their face. Blink rate doubles under pressure. Would you use this?",
            "Most people set alarms. Elite minds set intentions. Before sleep, your brain is 47% more receptive to suggestion. Program it deliberately.",
            "3 ways they control you without speaking: they mirror your posture, they pause before answering, they never break eye contact first. Notice this tonight.",
            "The loudest person in the room is almost never the most powerful. Real influence is invisible. Can you spot it?",
            "They build you up in public to tear you down in private. This is covert narcissism. Once you see it, it cannot be unseen. Want part 2?"
        ]
        # Pick one that doesn't overlap with forbidden topics
        chosen = random.choice(fbs)
        for candidate in fbs:
            if not any(word.lower() in candidate.lower() for word in (forbidden_topics or [])):
                chosen = candidate
                break
        script_text = chosen

    # BUGFIX: Always force dark_mindset — never allow brainrot style for dark psychology channel  
    background_vibe   = None  # Rely on background_fetcher's viral mood queries
    music_folder_name = "dark_mindset"  # HARDCODED: dark psychology never uses brainrot
    tytul             = director_json.get('title', 'Dark psychology secrets you need to know #shorts')
    opis              = director_json.get('description', 'Master these dark psychology manipulation secrets. #shorts #viral #darkpsychology')
    
    # Używamy globalnej stałej BASE_VIRAL_TAGS

    raw_tagi = director_json.get('seo_tags', [])
    if isinstance(raw_tagi, str):
        raw_tagi = [raw_tagi]
    elif not isinstance(raw_tagi, list):
        raw_tagi = []
        
    tagi = []
    # Merge AI tags with guaranteed viral tags (dedup, limit 500 znakow łącznie)
    for raw_t in raw_tagi + BASE_VIRAL_TAGS:
        for t in str(raw_t).split(','):
            cl_t = t.strip().replace('<', '').replace('>', '').replace('"', '').replace('#', '').replace(' ', '')
            if cl_t and cl_t.lower() not in [xt.lower() for xt in tagi]:
                tagi.append(cl_t)

    # YouTube limit: 500 znakow tagów łącznie
    final_tags = []
    total_chars = 0
    for tag in tagi:
        if total_chars + len(tag) + 1 <= 500:
            final_tags.append(tag)
            total_chars += len(tag) + 1
        else:
            break
    tagi = final_tags

    # Budujemy hashtag block do opisu (SEO)
    hashtag_block = build_hashtag_block(tagi)
    # Dołączamy blok do opisu jeśli go brak
    if not opis.strip().endswith("#shorts") and "#darkpsychology" not in opis:
        opis = f"{opis.strip()}\n\n{hashtag_block}"
    
    print("\n╔══════════════════════════════════════════════════╗")
    print("║     🧠 SYNAPSA MASTER DIRECTOR — DARK RAPORT     ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  🎯 Ocena Viral Score:  {director_json.get('viral_score', '?')}/10")
    print(f"║  📝 Skrypt (początek):  {script_text[:80]}...")
    print(f"║  🎬 Tło wideo:          {background_vibe}")
    print(f"║  📌 Tytuł YT:           {tytul}")
    print(f"║  🔖 Tagi:               {', '.join(tagi[:5])}...")
    print("╚══════════════════════════════════════════════════╝")
    
    # Renderowanie
    output_video = generate_cashcow_from_text(
        script_text, PROFILE_NAME,
        background_vibe=background_vibe,
        music_folder=music_folder_name
    )
    
    if youtube and output_video:
        from upload_youtube import upload_video
        print("\n--- ETAP 5: Autopublikacja na kanale YouTube (1-Click) ---")
        try:
            # Ustalamy datę publikacji - pierwszy film natychmiast/szczyt, drugi po 4 godzinach
            publish_time = None
            if video_index == 2:
                # +3h trafia w wieczorny peak 20:00 (przy autostarcie o 17:00)
                publish_time = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"🕒 AUTOMATYZACJA CZASU: Wideo 2/2 zaplanowano na {publish_time}.")

            upload_result = upload_video(
                youtube=youtube,
                file_path=output_video,
                title=tytul,
                description=opis,
                tags=tagi,
                category_id="24",  # Entertainment
                privacy_status="private" if publish_time else "public",
                publish_at=publish_time
            )
            add_to_history(PROFILE_NAME, tytul, script_text=script_text)
            log_publish_report(tytul, video_index, tagi, privacy="public", video_id=upload_result)
            print(f"✅ [SUKCES] Film '{tytul}' z profilu {PROFILE_NAME} pomyślnie wgrany jako PUBLICZNY (ID: {upload_result})!")
            print(f"   🏷️  Tagi: ({len(tagi)}) {', '.join(tagi[:6])}...")
            print(f"   📝 Opis (ostatnie 120 zn.): ...{opis[-120:]}")
        except Exception as e:
            print(f"❌ [BŁĄD PUBLIKACJI] Wystąpił błąd przy wgrywaniu: {e}")
            
    print(f"\n🎉 Cykl {video_index}/{total_videos} dla Dark Psychology zakończony.")
    return True

def main():
    print("===============================================================")
    print("🌑 DEDYKOWANY AGENT: DARK PSYCHOLOGY (Tryb: 2 filmy dziennie)")
    print("===============================================================")
    
    # Autoryzacja tylko dla konta dark_mindset
    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Błąd! Agent nie uzyskał dostępu do kanału YouTube Dark Psychology.")
        return

    # Pętla generująca zadaną ilość filmów (2 dziennie)
    for i in range(1, DAILY_QUOTA + 1):
        success = run_dark_agent_cycle(i, DAILY_QUOTA, youtube)
        if success and i < DAILY_QUOTA:
            print("⏳ Przerwa przed generowaniem kolejnego wideo (30 sekund dla ochłody systemów)...")
            time.sleep(30)
            
    print("\n🏁 DZIENNY LIMIT ZAKOŃCZONY. Agent Dark Psychology wykonał swoje zadanie.")

if __name__ == "__main__":
    main()
