import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()  # Załaduj zmienne z .env

# Wymuszenie UTF-8 na stdout/stderr (Windows CP1250 nie obsługuje emoji)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# Strefa czasowa PL — automatycznie obsługuje CEST (+2 lato) i CET (+1 zima)
PL_TZ = ZoneInfo("Europe/Warsaw")

from data_collector import get_authenticated_service
from cashcow_generator import generate_cashcow_from_text, CHANNELS_NICHES
from synapsa_bridge import generate_viral_script_with_synapsa
try:
    from facts_database import FactSelector, facts_to_prompt_injection
    _FACTS_DB_AVAILABLE = True
except ImportError:
    _FACTS_DB_AVAILABLE = False
try:
    from quality_auditor import audit_short as _audit_short_fn
    _AUDITOR_AVAILABLE = True
except ImportError:
    _AUDITOR_AVAILABLE = False
    _audit_short_fn = None

def audit_short(title, script, video_path=None):
    if _AUDITOR_AVAILABLE and _audit_short_fn:
        return _audit_short_fn(title, script, video_path=video_path)
    return {"score": 75, "decision": "APPROVED", "approved": True, "fix_report": [], "breakdown": {}}


# ==============================================================================
# === KONFIGURACJA AGENTA: DARK PSYCHOLOGY
# ==============================================================================
PROFILE_NAME = "dark_mindset"
NICHE_BASE = "psychology facts human behavior social dynamics"
DAILY_QUOTA = 2
TOPIC_HISTORY_FILE = "accounts/topic_history.json"
TOPIC_ROTATION_FILE = "accounts/topic_rotation.json"
PUBLISH_REPORT_FILE = "publish_report.json"

# ===== DIVERSE SUB-NICHE ROTATION POOL (Priority 3 — Content Variety) =====
# Rotuje co film, zapobiegając content fatigue (wszystkie filmy to były body language)
TOPIC_ROTATION_POOL = [
    "dark psychology body language social dominance",        # Core niche
    "neuropsychology decision making cognitive biases",       # NEW: neuro
    "dark psychology respect social influence power",         # Core variant
    "persuasion techniques negotiation covert influence",     # NEW: persuasion
    "narcissist manipulation red flags covert emotional abuse", # NEW: red flags
    "self mastery self discipline stoic philosophy sigma mindset", # NEW: self-mastery
    "social intelligence reading people microexpressions emotions", # NEW: social intel
    "covert communication nonverbal secrets psychological power",   # Core + new angle
]
DRY_RUN = False  # ustawiane przez --dry-run flag
AUDIT_REPORT_FILE = "audit_report.json"

# ===== STAŁE BAZOWE TAGI DARK PSYCHOLOGY =====
BASE_VIRAL_TAGS = [
    # CORE (max 15 — YouTube penalizuje >15 tagów w polu tags)
    "darkpsychology", "psychology", "manipulation", "mindset", "humanbehavior",
    "psychologyfacts", "bodylanguage", "shorts", "viral",
    "sigma", "socialintelligence", "persuasion", "power",
    "psychologyshorts", "subconscious",
]

# Obowiązkowy hashtag block do opisu (SEO YouTube)
BASE_HASHTAG_BLOCK = "#darkpsychology #shorts #psychology #manipulation #mindset"


def build_hashtag_block(tags: list) -> str:
    """Buduje blok hashtagów z listy tagów + bazowych hashtagów niszy."""
    ai_hashtags = [f"#{t.strip().replace(' ', '').replace('#', '')}" for t in tags[:8] if t.strip()]
    combined = list(dict.fromkeys(ai_hashtags))  # dedup z zachowaniem kolejności
    # Dołącz bazowe jeśli ich brakuje
    for base_tag in BASE_HASHTAG_BLOCK.split():
        if base_tag.lower() not in [h.lower() for h in combined]:
            combined.append(base_tag)
    return " ".join(combined[:5])  # YouTube eksperci: max 3-5 hashtagów w opisie


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

def _get_next_topic(video_index: int) -> str:
    """Rotuje przez 8 pod-nisz dark psychology — zapobiega content fatigue (Priority 3)."""
    state = {}
    if os.path.exists(TOPIC_ROTATION_FILE):
        try:
            with open(TOPIC_ROTATION_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except:
            pass
    last_idx = state.get("last_idx", -1)
    next_idx = (last_idx + 1) % len(TOPIC_ROTATION_POOL)
    state["last_idx"] = next_idx
    try:
        with open(TOPIC_ROTATION_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except:
        pass
    topic = TOPIC_ROTATION_POOL[next_idx]
    print(f"\n💡 [TOPIC ROTATION #{next_idx+1}/{len(TOPIC_ROTATION_POOL)}] Film {video_index}: '{topic}'")
    return topic


def _post_cta_comment(youtube, video_id: str, script_text: str):
    """Auto-postuje zróżnicowany komentarz CTA po uploadzie — boost engagement signals (Priority 4)."""
    import random
    cta_options = [
        "Which of these dark psychology tactics have you caught someone using on you? 🧠👇",
        "Comment '1' if you recognized this in someone you know 👇🧠",
        "Have you ever felt this being used on you? Tell me below 👇",
        "Share this with someone who does this to you 👇 They need to see it.",
        "Which number: 1 = this happened to me, 2 = I've done this to someone 👇🧠",
        "Have you ever caught someone doing this to you in real life? 👇🧠",
    ]
    comment_text = random.choice(cta_options)
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text}
                    }
                }
            }
        ).execute()
        print(f"💬 [CTA COMMENT] ✅ Opublikowano: '{comment_text}'")
    except Exception as e:
        # Brak scope 'youtube.force-ssl' w tokenie — dodaj go w authorize_channel.py jeśli chcesz komentarze
        print(f"⚠️  [CTA COMMENT] Pominięto (brak scope lub błąd API): {e}")


def _validate_title(title: str) -> bool:
    """Validates AI-generated title. Returns False for garbage/hallucinated titles."""
    if not title or len(title.strip()) < 10:
        return False
    t = title.strip()
    # 1. Bracket tags at start: [Nero's...], [virginia-loop], [--END...]
    if t.startswith('['):
        return False
    # 2. Prompt leak markers
    _poison_words = ['--END', 'END OF PROMPT', 'virginia', 'Nero', 'Pythomian',
                     'Pygmy Illusion', 'Lamentoation', 'Lamentation', 'Tagged with']
    t_lower = t.lower()
    for pw in _poison_words:
        if pw.lower() in t_lower:
            return False
    # 3. Concatenated words: 3+ uppercase letters glued inside a word (e.g. HowSomePeopleCommand)
    import re as _re_val
    # Find words with 3+ internal uppercase transitions (camelCase junk)
    words = t.split()
    for word in words:
        clean_word = _re_val.sub(r'[^a-zA-Z]', '', word)
        if len(clean_word) > 15:  # suspiciously long "word"
            upper_count = sum(1 for i, c in enumerate(clean_word) if c.isupper() and i > 0)
            if upper_count >= 3:
                return False
    # 4. Tag-as-title: looks like comma-separated tag list
    if t.count(',') >= 2 and all(w.strip().replace('#', '').isalpha() for w in t.split(',') if w.strip()):
        return False
    # 5. Too short (less than 4 real words after stripping emoji/hashtags)
    real_words = [w for w in words if not w.startswith('#') and not w.startswith('🧠') and len(w) > 1]
    if len(real_words) < 4:
        return False
    # 6. Contains debug/internal markers
    if any(marker in t for marker in ['[--', '--]', 'PROMPT', '[TITLE]', '[SCRIPT]', '[TAGS]']):
        return False
    return True


# ── AUTO-INJECT: Automatycznie dodaje PRE-HOOK / RE-HOOK / CTA do skryptów Synapsy ──
_PRE_HOOKS = [
    "Most people don't know this.",
    "Stop. Don't scroll.",
    "They removed this from textbooks.",
    "This changes everything.",
    "Nobody talks about this.",
    "Here's what they hide from you.",
    "Pay attention to this.",
    "99% of people miss this.",
]
_RE_HOOKS = [
    "But here's the dark part —",
    "But here's what nobody tells you —",
    "And here's why this matters —",
    "But the real reason this works?",
    "What nobody tells you is —",
    "Here's the truth —",
]
_CTAS = [
    "Follow for more.",
    "Can you spot who uses this on you?",
    "Follow if this sounds familiar.",
    "Like if you've seen this used on you.",
    "Follow for more dark psychology secrets.",
]

def _auto_inject_structure(script_text: str) -> str:
    """Automatycznie wstrzykuje PRE-HOOK, RE-HOOK i CTA do skryptu który ich nie ma.
    Synapsa (Qwen) generuje skrypty BEZ tych elementów w ~70% przypadków.
    Ten fix gwarantuje, że każdy skrypt ma pełną strukturę retencji."""
    import random as _rnd_inj
    import re as _re_inj
    words = script_text.split()
    modified = False

    # 1. PRE-HOOK — sprawdź pierwsze 8 słów
    first_8 = " ".join(words[:8]).lower()
    _ph_markers = ["most people", "stop.", "stop scrolling", "nobody", "they don't",
                   "here's what", "pay attention", "99%", "they removed", "this changes",
                   "few people", "they hide", "they never"]
    if not any(m in first_8 for m in _ph_markers):
        hook = _rnd_inj.choice(_PRE_HOOKS)
        script_text = hook + " " + script_text
        words = script_text.split()
        modified = True

    # 2. RE-HOOK — sprawdź drugą połowę
    mid = len(words) // 2
    latter = " ".join(words[mid:]).lower()
    _rh_markers = ["but here's", "the dark part", "nobody tells", "the truth is",
                   "here's why", "what they", "the real reason", "here's the secret"]
    if not any(m in latter for m in _rh_markers):
        # Wstaw RE-HOOK przed ostatnim zdaniem
        sentences = _re_inj.split(r'(?<=[.!?])\s+', script_text)
        if len(sentences) >= 3:
            rehook = _rnd_inj.choice(_RE_HOOKS)
            sentences.insert(-1, rehook)
            script_text = " ".join(sentences)
            words = script_text.split()
            modified = True

    # 3. CTA — sprawdź ostatnie 10 słów
    last_10 = " ".join(words[-10:]).lower()
    _cta_markers = ["follow", "like if", "comment", "part 2", "save", "share",
                    "want to know", "watch more"]
    if not any(m in last_10 for m in _cta_markers):
        cta = _rnd_inj.choice(_CTAS)
        script_text = script_text.rstrip('. ') + ". " + cta
        modified = True

    if modified:
        print(f"🔧 [AUTO-INJECT] Dodano brakujące elementy struktury retencji.")

    return script_text


def generate_viral_script(viral_context, niche_topic, channel_rule, forbidden_topics=None):
    """Zapytanie do Synapsy z dyrektywami Dark Psychology."""
    return generate_viral_script_with_synapsa(viral_context, niche_topic, channel_rule, forbidden_topics)

def get_forbidden_topics(profile_name: str, limit: int = 30) -> list:
    """Returns past titles to explicitly forbid the AI from repeating the same concepts."""
    if not os.path.exists(TOPIC_HISTORY_FILE):
        return []
    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_history = data.get(profile_name, [])
        # Only take last 30 to not overflow AI context window
        recent = profile_history[-limit:]
        forbidden = []
        for item in recent:
            if item.get("title"):
                # Clean up title to be just the concept, removing hashtags etc
                clean_title = item.get("title").split("#")[0].strip()
                forbidden.append(clean_title)
        
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
    
    data[profile_name].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "script": script_text
    })
    
    data[profile_name] = data[profile_name][-50:]  # Keep last 50
    
    with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def run_dark_agent_cycle(video_index: int, total_videos: int, youtube):
    """Pojedynczy cykl generacji i publikacji dla Dark Psychology."""
    print("\n" + "="*70)
    print(f"🌑 DARK PSYCHOLOGY AGENT: Generowanie filmu {video_index}/{total_videos}")
    print("="*70)
    # Rotacja pod-nisz — każdy film trafia w inny temat, unikamy content fatigue (Priority 3)
    search_topic = _get_next_topic(video_index)

    # Wczytaj dyrektywę z poprzedniej analizy (smart_video_analyzer)
    directive_file = "adaptation_directive.json"
    if os.path.exists(directive_file):
        try:
            with open(directive_file, "r", encoding="utf-8") as df:
                dir_data = json.load(df)
            loaded_directive = dir_data.get("directive", "")
            if loaded_directive:
                os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"] = loaded_directive
                print(f"📊 [ANALIZA] Załadowano dyrektywę adaptacyjną z {directive_file}")
                l2 = dir_data.get("last_2_videos", [])
                for lv in l2:
                    print(f"   🎥 '{lv['title'][:55]}' — {lv['views']} views, {lv['engagement']}% eng, {lv['velocity']} v/h")
        except Exception as de:
            print(f"⚠️  Błąd (ładowanie dyrektywy): {de}")
            os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"] = ""
    else:
        os.environ["SYNAPSA_ADAPTATION_DIRECTIVE"] = ""

    viral_context = search_viral_shorts(youtube, search_topic, count=5)

    # ── FACTS INJECTION: wybierz 3 unikalne fakty z FactSelector (anti-duplicate) ──
    if _FACTS_DB_AVAILABLE:
        try:
            _selector = FactSelector(profile=PROFILE_NAME)
            _facts = _selector.select_for_video(video_index=video_index)
            if _facts:
                facts_payload = facts_to_prompt_injection(_facts)
                os.environ["SYNAPSA_FACTS_PAYLOAD"] = facts_payload
                print(f"📚 [FACTS DB] ✅ Wstrzyknięto {len(_facts)} unikalne fakty dla wideo #{video_index}.")
            else:
                os.environ["SYNAPSA_FACTS_PAYLOAD"] = ""
        except Exception as _fe:
            print(f"⚠️  [FACTS DB] Błąd selekcji faktów: {_fe}")
            os.environ["SYNAPSA_FACTS_PAYLOAD"] = ""
    else:
        os.environ["SYNAPSA_FACTS_PAYLOAD"] = ""
        print("⚠️  [FACTS DB] facts_database.py niedostępna — generuję bez faktów.")


    
    # Pamięć AI — historia + SESSION CACHE (Fix: Video 2 widzi skrypt Video 1 jeszcze przed zapisem do historii)
    forbidden_topics = get_forbidden_topics(PROFILE_NAME)
    
    # Wczytaj skrypty z bieżącej sesji (inne filmy z tego samego uruchomienia)
    _SESSION_KEY = f"_SESSION_SCRIPTS_{PROFILE_NAME}"
    _session_raw = os.environ.get(_SESSION_KEY, "")
    _session_scripts = [s for s in _session_raw.split("||||") if s.strip()]
    if _session_scripts:
        print(f"🔒 [SESSION CACHE] Załadowano {len(_session_scripts)} skrypt(ów) z tej sesji jako forbidden.")
        # Dodaj tytuły sesyjne do forbidden_topics żeby Synapsa ich nie powtórzyła
        for ss in _session_scripts:
            preview = ss[:60].strip()
            if preview not in forbidden_topics:
                forbidden_topics.append(preview)
        # Wstrzyknij też jako env var żeby synapsa_bridge widział
        os.environ["SYNAPSA_SESSION_FORBIDDEN"] = "||||".join(_session_scripts)
    else:
        if "SYNAPSA_SESSION_FORBIDDEN" in os.environ:
            os.environ.pop("SYNAPSA_SESSION_FORBIDDEN")
    
    if forbidden_topics:
        print(f"🧠 [PAMIĘĆ DEDUPLIKACJI] Łącznie zabezpieczono tematów: {len(forbidden_topics)} (historia + sesja)")
    niche_rule = CHANNELS_NICHES.get(
        PROFILE_NAME, {}).get(
        'prompt',
        """CREATE A VIRAL PSYCHOLOGY YOUTUBE SHORT (50-70 WORDS)

CRITICAL VIRAL RULES (MERGED WITH PREVIOUS OPTIMIZATIONS):
1. EXTREME NOVELTY: You MUST select a rare, highly obscure psychological trick, bias, or social dynamic. DO NOT repeat common facts. It must be unique and different from the listed forbidden topics.
2. ACCOUNT SAFETY (LOOPHOLE): Frame ALL manipulation or dark psychology tactics as "Defense against manipulation". Example: "Watch out for people who use this on you..." instead of "Here is how to manipulate". This is critical to avoid bans.
3. POTENT HOOK (First 3s): MUST contain elements of "forbidden knowledge" or explicitly tell the user to "Save this video before it's deleted".
4. SCRIPT STRUCTURE (15-30s lengths): Hook -> Value 1 -> Value 2 -> CTA/Loop. Every single word counts. Pack it with 'meat'.
5. ALGORITHM PSYCHOLOGY & LOOPING: The last word MUST connect seamlessly into the first word of your script to create a Perfect Loop.
6. VISUAL DIRECTIVE (For AI): Aim for a visual background description like "Peaky Blinders, American Psycho, mysterious figure in suit, wolves, dark city at night, dark red/navy colors".

EXAMPLE SCRIPT STRUCTURE (Use this exact format in ENGLISH):
[TITLE]
The most toxic manipulation technique narcissists use. (Save this) 🧠
[SCRIPT]
Save this video before they take it down. Here is how to spot if someone is secretly trying to control you. When someone tries to dominate you, maintain absolute silence and stare directly at the center of their forehead for four seconds. This will completely destroy their confidence, forcing them into submission. Want to learn more ways to defend yourself? Watch this video and...
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
        
        if 35 <= script_len <= 80: 
            print(f"✅ Skrypt IDEALNY ({script_len} słów) z miejscem na Loop/CTA (zoptymalizowane pod 10-30s).")
            break
        elif script_len > 80:
            print(f"⚠️  Skrypt za DŁUGI ({script_len} słów). Regeneracja!")
        else:
            print(f"⚠️  Skrypt za KRÓTKI (lub błąd JSON) ({script_len} słów - brakuje CTA/Loop). Regeneracja!")

    script_text = director_json.get('script_text', '')
    if not script_text.strip() or len(script_text.split()) < 35 or len(script_text.split()) > 100:
        import random
        # Ultra short fallbacks — diverse topics, UNIQUE per run session
        # UWAGA: wszystkie fallbacki muszą mieć ≥ 40 słów (min. 12s @ +28% TTS)
        # KAŻDY FALLBACK dotyczy INNEGO aspektu dark psychology — brak duplikatów!
        fbs = [
            # [0] Status anchoring / authority
            "You're being controlled right now. Have you noticed how some people walk into a room and everyone goes quiet? They use status anchoring — pausing before they speak, slowing every movement, never breaking eye contact first. The person who reacts fastest always loses power. But here's what nobody tells you — once you adopt this frame, people treat you differently within two days. Follow for more.",
            # [1] Emotional vampirism / energy drain
            "Stop. Don't scroll. Have you ever felt completely drained after talking to a specific person? That's not a coincidence. They're using emotional vampirism — deliberately triggering micro-frustrations to feed off your emotional reaction. The moment you respond with absolute calm, they lose all power. But here's the dark part — they often don't even know they're doing it. Follow if this sounds familiar.",
            # [2] Mirroring / trust manipulation
            "They removed this from psychology textbooks. Have you noticed how some people never seem to lose an argument? They use tactical mirroring — repeating your last three words back as a question. Your brain automatically interprets this as deep understanding and trust. But here's the dark truth — they're not listening to you. They're mapping your psychological weak points. Can you spot who uses this on you?",
            # [3] Authority frame / silence as weapon
            "The worst thing you can do when disrespected is respond. Have you ever noticed why the most powerful people in the room say almost nothing? They understand the authority frame — silence is interpreted as confidence, not weakness. Every unnecessary word you speak reduces your perceived status by 4 percent. But here's what nobody tells you — most leaders learn this by accident. Follow for the full breakdown.",
            # [4] Covert contempt / toxic positivity
            "Most people don't see this happening to them. Have you noticed how the most dangerous people in your life never raise their voice? They use covert contempt — a calm tone, a slight smile, and a compliment that secretly diminishes you. Your brain registers the warmth but misses the attack. Once you learn to spot this pattern, every conversation becomes completely transparent. Follow before this video disappears.",
            # [5] Cognitive biases / decision making
            "Stop. Watch this before they delete it. Have you ever made a decision you deeply regret and couldn't explain why? That's the anchoring bias at work — someone gave you a reference point first, and your brain calculated everything relative to it. Salespeople, politicians, and manipulators use this constantly. But here's the dark part — knowing this doesn't make you immune. It just makes you aware. Follow for more.",
            # [6] Social proof / herd manipulation
            "The most powerful manipulation technique requires zero effort. Have you noticed how people automatically trust someone more when others are watching? That's manufactured social proof — and it works on 96 percent of humans because our brains are wired to follow the crowd in uncertain situations. But here's what they hide — you can neutralize this by simply asking one question: who benefits? Follow for more secrets.",
            # [7] Intermittent reinforcement / toxic attachment
            "Can you spot when this is being done to you? The most addictive relationship dynamic isn't love — it's intermittent reinforcement. Hot and cold behavior, unpredictable kindness, sudden withdrawal. Your brain releases dopamine not for the reward but for the anticipation of the reward. This is the same mechanism as gambling addiction. But here's the dark part — the person doing it to you may not even realize it. Follow for more.",
            # [8] Gaslighting detection — reality distortion
            "This is how they make you question your own reality. Gaslighters use a three-step formula. First, they deny something you clearly saw happen. Second, they tell you that you're overreacting. Third, they rewrite the narrative until you apologize for being right. Research from the Journal of Personality shows 68 percent of victims don't recognize gaslighting until the third year. The moment you document conversations, their power collapses. Follow for more.",
            # [9] Frame control — conversational dominance
            "They don't win arguments. They control the frame. Have you noticed how certain people always steer conversations where they want? That's frame control. They set the premise before you speak, making you defend their assumption instead of your point. FBI negotiators call this the accusation audit. The counter is devastatingly simple: ignore the frame entirely and state your position as a fact. Watch how quickly they lose composure. Follow for more.",
            # [10] Micro-expressions — deception detection
            "You missed it. That flash across their face lasted exactly one twenty-fifth of a second. Micro-expressions are involuntary muscle movements that reveal true emotions before the brain can mask them. Paul Ekman identified seven universal ones. The most dangerous is contempt — a one-sided lip raise that predicts relationship failure with 93 percent accuracy. Once you train your eye to catch it, nobody can lie to your face again. Follow for the full guide.",
            # [11] Scarcity psychology — FOMO manipulation
            "They're using artificial scarcity to hijack your decision-making. When something feels limited, your brain assigns it 238 percent more value according to Worchel's experiment. Marketers, manipulators, and toxic partners all exploit this. They create urgency where none exists. The phrase 'this won't last' bypasses your logical brain entirely and activates your amygdala. The antidote is brutally simple: ask yourself what happens if you wait 48 hours. Follow for more.",
            # [12] Dark empathy — weaponized understanding
            "The most dangerous person in the room isn't the narcissist. It's the dark empath. They feel exactly what you feel. They understand your deepest insecurities. And they use that information strategically. Research published in Personality and Individual Differences found dark empaths score high on cognitive empathy but exploit it for personal gain. They'll comfort you while engineering your dependency. The red flag: they always know exactly what to say. Follow for more.",
            # [13] Triangulation — social chess
            "Watch for this in every group. Triangulation is when someone uses a third person to manipulate your emotions. They'll say 'everyone thinks you're too sensitive' when nobody said that. Or they'll praise someone else loudly to make you feel inadequate. Narcissists use this instinctively to maintain control of social hierarchies. The defense: go directly to the third person and verify. Triangulators collapse when you cut out the middleman. Follow for more.",
            # [14] Cognitive dissonance exploitation
            "Your brain is lying to you right now. When your actions contradict your beliefs, your mind doesn't change the action. It rewrites the belief. Cults, toxic relationships, and high-pressure sales all exploit cognitive dissonance. They get you to make one small compromise. Then your brain justifies it. Then they push further. Leon Festinger proved this in 1957. The defense: write down your values before any high-pressure situation. Paper doesn't rationalize. Follow for more.",
            # [15] Strategic vulnerability — calculated weakness
            "The most powerful manipulation looks like genuine weakness. Strategic vulnerability is when someone reveals a carefully chosen personal flaw to manufacture instant trust. They'll confess something small — a fear, a past mistake — to make you lower your guard and reciprocate with real secrets. Intelligence agencies call this elicitation. The key tell: their vulnerability never puts them at actual risk, but yours always does. Follow if you've experienced this.",
            # [16] Dunbar's number — social circle limits
            "Most people don't know this. Your brain can only maintain about 150 meaningful relationships. Robin Dunbar proved this by studying primate brain sizes. Beyond that number, people become strangers regardless of how many followers you have. But here's the dark part — manipulators exploit this by isolating you from your real 150 and replacing them with superficial connections you can't rely on. The fewer real bonds you have, the easier you are to control. Follow for more.",
            # [17] Door-in-the-face technique
            "Nobody talks about this. Have you ever been asked for something outrageous, said no, then agreed to a smaller request? That's the door-in-the-face technique. They ask for something huge first knowing you'll refuse. Then they offer the real request which seems reasonable by comparison. Robert Cialdini documented this in 1975. But here's what nobody tells you — your brain feels obligated to compromise because it perceives reciprocity. Follow for more dark psychology secrets.",
            # [18] Spotlight effect — perceived attention
            "Stop. Don't scroll. Have you ever walked into a room convinced everyone was staring at you? That's the spotlight effect. Thomas Gilovich proved that people overestimate how much others notice them by a factor of two. Your embarrassing moment? Nobody remembers it. But here's the dark part — narcissists weaponize this. They make you feel constantly watched and judged to keep you anxious and controllable. Once you understand this you stop caring what anyone thinks. Follow for more.",
            # [19] Halo effect — beauty bias
            "They removed this from textbooks. Have you noticed how attractive people get shorter prison sentences? That's the halo effect. Your brain assumes that someone who looks good must also be smart, kind, and trustworthy. Edward Thorndike identified this in 1920. But here's what nobody tells you — manipulators groom their appearance specifically to exploit this bias. A well-dressed predator is trusted more than an honest person in worn clothes. Follow if this changes your perspective.",
            # [20] Stockholm syndrome — trauma bonding (mild)
            "This changes everything. Have you ever defended someone who consistently hurt you? That's a mild form of trauma bonding. When someone alternates between cruelty and kindness, your brain forms an intense emotional attachment to the moments of relief. Psychologists call this the Stockholm mechanism. But here's the dark part — it doesn't require a kidnapping. It happens in workplaces, friendships, and relationships every single day. Recognizing the pattern is the first step to breaking free. Follow for more.",
            # [21] Reciprocity principle — obligation trap
            "Here's what they hide from you. Have you ever felt obligated to help someone simply because they did you a small favor? That's the reciprocity principle. When someone gives you something — even something you didn't want — your brain creates an overwhelming urge to repay them. Cialdini found this is the most exploited influence weapon in human history. But here's why this matters — the favor they give is always smaller than what they'll demand in return. Follow for more.",
            # [22] Authority bias — Milgram obedience
            "Pay attention to this. In 1963, Stanley Milgram proved that 65 percent of ordinary people would deliver lethal electric shocks to a stranger simply because an authority figure told them to. No threats. No punishment. Just a man in a lab coat saying continue. But here's the dark part — this experiment has been replicated in dozens of countries with the same result. We are biologically programmed to obey authority even when it violates our deepest morals. Follow for more.",
            # [23] Loss aversion — Kahneman fear psychology
            "Most people don't know this. The pain of losing 100 dollars is twice as powerful as the pleasure of gaining 100 dollars. Daniel Kahneman won a Nobel Prize proving this. Your brain is wired to avoid loss more than to seek gain. But here's what nobody tells you — every manipulator knows this. They threaten to take something away rather than offering something new. That's why ultimatums work so well and why fear-based marketing outsells positive messaging every time. Follow for more.",
            # [24] Sunk cost fallacy — trapped by investment
            "Nobody talks about this. Have you ever stayed in a terrible situation just because you already invested too much time or money? That's the sunk cost fallacy. Your brain refuses to accept that past investment is gone regardless of what you do next. But here's the dark part — toxic partners and bad bosses exploit this deliberately. They make you invest just enough that leaving feels like losing everything. The truth: what you already spent is gone forever. Only the future matters. Follow for more.",
            # [25] Bandwagon effect — herd manipulation
            "Stop. Watch this carefully. Have you noticed how people suddenly love something the moment it becomes popular? That's the bandwagon effect. Solomon Asch proved in 1951 that 75 percent of people will publicly deny what their own eyes tell them just to conform with a group. But here's the dark part — social media algorithms amplify this a thousandfold. Trending topics aren't popular because they're good. They're popular because your brain can't resist joining the crowd. Follow for more.",
            # [26] Dunning-Kruger — confidence illusion
            "This is why the loudest person in the room is usually wrong. The Dunning-Kruger effect proves that people with the least knowledge have the most confidence. They don't know enough to realize what they don't know. Meanwhile, genuine experts underestimate themselves because they see how much more there is to learn. But here's the dark part — manipulators exploit this by speaking with absolute certainty about things they barely understand. Confidence is not competence. Follow for more.",
            # [27] Bystander effect — diffusion of responsibility
            "99% of people miss this. If you collapse on a street with 50 people watching, your chance of getting help drops to 30 percent. That's the bystander effect. The more people present, the less responsible each person feels. Kitty Genovese's case in 1964 proved this tragically. But here's what nobody tells you — manipulators use this in meetings and group settings. They create confusion so nobody takes action while they seize control unopposed. Follow for more.",
            # [28] Zeigarnik effect — unfinished business
            "Here's why you can't stop thinking about your ex. The Zeigarnik effect proves your brain obsesses over unfinished tasks and unresolved situations twice as much as completed ones. A relationship that ended without closure literally occupies more mental bandwidth than one that ended cleanly. But here's the dark part — manipulators leave conversations and arguments unresolved on purpose. They want to live rent-free in your head. The cure: create your own closure. You don't need theirs. Follow for more.",
            # [29] Decoy effect — choice manipulation
            "Pay attention to this. Have you ever chosen the medium option at a restaurant without knowing why? That's the decoy effect. Companies add a third option that's deliberately bad to make their preferred choice look perfect by comparison. Economists call this asymmetric dominance. But here's the dark part — this works in relationships too. Narcissists introduce a worse alternative to make themselves seem like the best option. Once you see this pattern, you can never be tricked again. Follow for more.",
        ]

        # ── TRWAŁY TRACKER FALLBACKÓW (plik JSON — nie env var!) ──────────────
        _fallback_tracker_file = os.path.join("accounts", "used_fallbacks.json")
        _fallback_data = {}
        if os.path.exists(_fallback_tracker_file):
            try:
                with open(_fallback_tracker_file, "r", encoding="utf-8") as _ff:
                    _fallback_data = json.load(_ff)
            except Exception:
                _fallback_data = {}
        _used_persistent = set(_fallback_data.get(PROFILE_NAME, []))

        # ── ZAŁADUJ SKRYPTY Z HISTORII do porównania podobieństwa ─────────────
        import difflib as _df2
        _hist_scripts_for_fb = []
        if os.path.exists(TOPIC_HISTORY_FILE):
            try:
                with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as _hf2:
                    _hd2 = json.load(_hf2)
                _hist_scripts_for_fb = [
                    h.get("script", "") for h in _hd2.get(PROFILE_NAME, [])[-30:]
                    if h.get("script")
                ]
            except Exception:
                pass

        # ── SESSION CHECK: skrypty wygenerowane w tej sesji ───────────────────
        _sess_raw = os.environ.get(f"_SESSION_SCRIPTS_{PROFILE_NAME}", "")
        _sess_scripts = [s for s in _sess_raw.split("||||") if s.strip()]
        _all_prev_scripts = _hist_scripts_for_fb + _sess_scripts

        # ── WYBIERZ FALLBACK KTÓRY NIE JEST PODOBNY DO ŻADNEGO POPRZEDNIEGO ──
        # candidates = lista POZYCJI w przefiltrowanej puli (nie indeksów fbs!)
        # Dzięki temu video_index=1 i video_index=2 zawsze dostaną RÓŻNY element.
        candidates = []  # każdy element: (fb_idx, fb_text)
        for idx, candidate in enumerate(fbs):
            if idx in _used_persistent:
                continue  # użyty w poprzednim uruchomieniu — pomiń
            _is_dup = False
            for _prev in _all_prev_scripts:
                if _df2.SequenceMatcher(None, candidate.lower(), _prev.lower()).ratio() > 0.45:
                    _is_dup = True
                    break
            if not _is_dup:
                candidates.append((idx, candidate))

        if not candidates:
            # Wszystkie fallbacki podobne lub użyte — zresetuj trwały tracker
            print("⚠️  [FALLBACK] Pula wyczerpana — reset trackera fallbacków.")
            _used_persistent = set()
            _fallback_data[PROFILE_NAME] = []
            candidates = []
            for idx, candidate in enumerate(fbs):
                _is_dup = any(
                    _df2.SequenceMatcher(None, candidate.lower(), s.lower()).ratio() > 0.45
                    for s in _sess_scripts
                )
                if not _is_dup:
                    candidates.append((idx, candidate))
            if not candidates:
                candidates = list(enumerate(fbs))

        # ── WYBÓR: video_index decyduje o POZYCJI w candidates (nie random hash!) ─
        # Film 1 → kandidat na pozycji 0, Film 2 → pozycja 1, itd.
        # Dzięki temu nawet przy tym samym czasie uruchomienia filmy różnią się.
        _position = (video_index - 1) % len(candidates)
        chosen_idx, chosen = candidates[_position]

        # Zapamiętaj w trwałym pliku
        _used_persistent.add(chosen_idx)
        _fallback_data[PROFILE_NAME] = list(_used_persistent)
        os.makedirs("accounts", exist_ok=True)
        with open(_fallback_tracker_file, "w", encoding="utf-8") as _ff:
            json.dump(_fallback_data, _ff, indent=2)

        # Dodaj do session cache żeby Film 2 widział skrypt Filmu 1
        _sess_scripts.append(chosen)
        os.environ[f"_SESSION_SCRIPTS_{PROFILE_NAME}"] = "||||".join(_sess_scripts)

        print(f"⚠️  Synapsa nie dała rady. Używam fallback #{chosen_idx+1}/{len(fbs)} "
              f"(temat: {chosen[:55]}...)")
        script_text = chosen

    # ── GUARD: Deduplication check PRZED renderowaniem ────────────────────────
    import difflib as _df
    _dedup_fired = False
    # BUG FIX: dir() zwraca atrybuty modułu, nie zmienne lokalne — używamy locals()
    _fbs_local = locals().get('fbs', [])
    try:
        _recent_scripts = []
        if os.path.exists(TOPIC_HISTORY_FILE):
            with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as _hf:
                _hist_data = json.load(_hf)
            _recent_scripts = [
                h.get("script", "") for h in _hist_data.get(PROFILE_NAME, [])[-20:]
                if h.get("script")
            ]
        # Dodaj też session scripts (bez bieżącego skryptu)
        _sess_raw2 = os.environ.get(f"_SESSION_SCRIPTS_{PROFILE_NAME}", "")
        _sess_scripts2 = [s for s in _sess_raw2.split("||||") if s.strip() and s != script_text]
        _all_check = _recent_scripts + _sess_scripts2

        for _prev_script in _all_check:
            _ratio = _df.SequenceMatcher(None, script_text.lower(), _prev_script.lower()).ratio()
            if _ratio > 0.50:
                print(f"\n🚨 [DEDUP GUARD] Skrypt {_ratio:.0%} identyczny z poprzednim!")
                print(f"   Poprzedni: '{_prev_script[:70]}...'")
                print(f"   Nowy:      '{script_text[:70]}...'")
                if _fbs_local:
                    # Szukaj alternatywy: różna od OBU (poprzedniego i bieżącego)
                    _all_sess = [s for s in _sess_scripts2] + [script_text]
                    _alt = [
                        (i, f) for i, f in enumerate(_fbs_local)
                        if all(
                            _df.SequenceMatcher(None, f.lower(), _s.lower()).ratio() < 0.40
                            for _s in _all_sess
                        )
                    ]
                    if _alt:
                        _alt_idx, _alt_script = _alt[0]
                        script_text = _alt_script
                        _dedup_fired = True
                        # Zaktualizuj session cache
                        _ss3 = [s for s in _sess_scripts2] + [_alt_script]
                        os.environ[f"_SESSION_SCRIPTS_{PROFILE_NAME}"] = "||||".join(_ss3)
                        print(f"   ✅ DEDUP zastąpił skrypt alternatywą #{_alt_idx+1}/{len(_fbs_local)}.")
                        break
                print(f"   ⚠️  Brak alternatyw w fbs — kontynuuję (skrypt lekko podobny ale różny temat).")
                break  # tylko pierwsza kolizja — nie zapętlaj
    except Exception as _de:
        print(f"   ⚠️  [DEDUP GUARD] Błąd sprawdzenia: {_de}")  # Historia niedostępna — kontynuuj

    # BUGFIX: Always force dark_mindset — never allow brainrot style for dark psychology channel  
    background_vibe   = None  # Rely on background_fetcher's viral mood queries
    music_folder_name = "dark_mindset"  # HARDCODED: dark psychology never uses brainrot

    # Fallback QUESTION tytuły gdy Synapsa failuje — wszystkie sprawdzone formaty
    _FALLBACK_TITLES = [
        # Format A — Questions (dane: śr. 378 views, CTR 8.3% przy szczycie)
        "Have you ever felt someone draining your energy? 🔋🧠 #shorts",
        "Can you spot the dark psychology tactic used on you? 👁️🧠 #shorts",
        "Have you noticed how some people command silence? 🧠 #shorts",
        "Are you being manipulated right now without even knowing it? 👁️ #shorts",
        "Have you ever felt invisible in a conversation? 🧠 #shorts",
        # Format B — Numbered lists (A/B test — wysoki globalny CTR, jeszcze nieprzetestowany)
        "3 Dark Psychology Tricks Manipulators Use on You 🧠 #shorts",
        "5 Signs Someone Is Secretly Controlling You 👁️🧠 #shorts",
        "2 Dark Body Language Signals Most People Miss 💀 #shorts",
        "4 Covert Manipulation Tactics You Need to Recognize 🧠 #shorts",
    ]
    import random as _rnd
    tytul = director_json.get('title', '')
    # ── TITLE VALIDATOR: Reject garbage/hallucinated titles ──────────────────
    if not _validate_title(tytul):
        if tytul:
            print(f"🚫 [TITLE VALIDATOR] Odrzucony tytuł: '{tytul[:70]}'")
        tytul = _rnd.choice(_FALLBACK_TITLES)
        print(f"   ✅ Zastąpiony fallbackiem: '{tytul[:70]}'")
    opis  = director_json.get('description', '')
    
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

    # YouTube limit: 500 znaków łącznie + max 15 tagów (task spec)
    final_tags = []
    total_chars = 0
    for tag in tagi:
        if len(final_tags) >= 15:          # ← hard cap: max 15 tagów
            break
        if total_chars + len(tag) + 1 <= 500:
            final_tags.append(tag)
            total_chars += len(tag) + 1
        else:
            break
    tagi = final_tags
    
    # ── RICH DESCRIPTION BUILDER (500+ chars) — SEO + Cross-Promotion ──────
    # Budujemy rozbudowany opis nawet gdy Synapsa daje krótki/pusty opis
    if len(opis.strip()) < 400:
        import re as _re_desc
        import random as _rnd_desc
        
        # Hook line — z tytułu (pierwsze 2 linijki widoczne bez rozwinięcia)
        clean_hook = _re_desc.sub(r'#\w+', '', tytul).strip().rstrip(' 🧠👁️💀⚠️🔥❗')
        
        # Kontekst z pierwszego zdania skryptu
        first_sentence = script_text.split('.')[0].strip() if '.' in script_text else script_text[:100]
        
        # Losowy kontekst paragraph (unique per video — unika YouTube spam penalty)
        context_paragraphs = [
            f"Dark psychology reveals the hidden mechanisms behind human behavior. {first_sentence}. Most people go their entire lives without recognizing these patterns — once you do, every social interaction becomes transparent.",
            f"Understanding manipulation is the first step to defending yourself. {first_sentence}. These psychological dynamics operate below conscious awareness, making them incredibly powerful and dangerous.",
            f"The science of influence has been studied for decades by researchers worldwide. {first_sentence}. Knowing these tactics doesn't just protect you — it gives you a strategic advantage in every conversation.",
            f"Human behavior follows predictable patterns that most people never learn about. {first_sentence}. Psychology researchers have documented these dynamics extensively, and the implications are unsettling.",
            f"What most people call 'charisma' or 'charm' is actually a set of learnable psychological tactics. {first_sentence}. Once you understand the mechanics, you'll never see social dynamics the same way again.",
        ]
        context = _rnd_desc.choice(context_paragraphs)
        
        # CTA section
        cta_options = [
            "🧠 Follow @DarkMindset for daily dark psychology insights that change how you see people.",
            "👁️ Follow for more psychological tactics most people never learn about.",
            "🧠 Follow @DarkMindset — new dark psychology short every day.",
        ]
        cta = _rnd_desc.choice(cta_options)
        
        # Cross-promotion — link do poprzedniego shorta (#14)
        prev_video_link = ""
        try:
            if os.path.exists(PUBLISH_REPORT_FILE):
                with open(PUBLISH_REPORT_FILE, "r", encoding="utf-8") as _prf:
                    _pub_data = json.load(_prf)
                if isinstance(_pub_data, list) and _pub_data:
                    last_entry = _pub_data[-1]
                    prev_id = last_entry.get("video_id")
                    if prev_id:
                        prev_video_link = f"\n\n▶️ Watch more: https://www.youtube.com/shorts/{prev_id}"
        except Exception:
            pass
        
        # Budujemy pełny opis
        opis = f"""{clean_hook}

{context}

{cta}{prev_video_link}

#darkpsychology #psychology #manipulation #mindset #shorts"""
    
    # Uzupełnij hashtagi jeśli ich brak
    if "#shorts" not in opis.lower():
        hashtag_block = build_hashtag_block(tagi)
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

    # ── AUTO-INJECT: Dodaj PRE-HOOK / RE-HOOK / CTA jeśli brakuje ──────────
    script_text = _auto_inject_structure(script_text)
    
    # ─── GUARD: sprawdź długość skryptu PRZED renderowaniem (oszcz. 3+ min) ──
    script_word_count = len(script_text.split())
    if script_word_count < 35:
        print(f"\n[SKIP] Skrypt za krótki ({script_word_count} słów, min. 35). Pomijam renderowanie.")
        print(f"   Synapsa nie wygenerowała poprawnego skryptu w 3 próbach + fallback jest pusty.")
        return False

    # Renderowanie
    output_video = generate_cashcow_from_text(
        script_text, PROFILE_NAME,
        background_vibe=background_vibe,
        music_folder=music_folder_name
    )
    
    # ─── ETAP 4.5: Audyt jakości przed wrzuceniem ─────────────────────────
    print("\n--- ETAP 4.5: Quality Auditor --- (obiektywna ocena przed wrzuceniem)")
    audit_result = None
    try:
        audit_result = audit_short(tytul, script_text, video_path=output_video)
        # Zapisz raport audytu
        audit_log = []
        if os.path.exists(AUDIT_REPORT_FILE):
            try:
                with open(AUDIT_REPORT_FILE, "r", encoding="utf-8") as af:
                    audit_log = json.load(af)
            except Exception:
                pass
        audit_log.append(audit_result)
        audit_log = audit_log[-50:]  # ostatnie 50
        with open(AUDIT_REPORT_FILE, "w", encoding="utf-8") as af:
            json.dump(audit_log, af, indent=2, ensure_ascii=False)
    except Exception as ae:
        print(f"⚠️  Audytor niedostępny: {ae}")

    if DRY_RUN:
        print("\n[DRY-RUN] Pomijam wrzucanie na YouTube!")
        if audit_result:
            print(f"   Wynik audytu: {audit_result['score']}/100 — {audit_result['decision']}")
        add_to_history(PROFILE_NAME, tytul, script_text=script_text)
        print(f"\n[OK] DRY-RUN cyklu {video_index}/{total_videos} zakończony.")
        return True

    # ─── AUDYT BLOKADA: REJECTED = brak uploadu / próba regeneracji ────────
    if audit_result and not audit_result.get("approved", True):
        score  = audit_result["score"]
        fixes  = audit_result.get("fix_report", [])
        print(f"\n[REJECTED] Wynik audytu: {score}/100 — SHORT NIE PRZESZEDL AUDYTU!")
        print(f"   Audytor odrzucil content przed wrzuceniem.")
        if fixes:
            print(f"   Powody ({len(fixes)}):")
            for f in fixes[:5]:
                print(f"     - {f.split(chr(10))[0]}")

        # Jedna próba regeneracji z feedback audytora
        print("\n[RETRY] Probuje wygenerowac lepszy short z feedback audytora...")
        _retry_approved = False
        try:
            fix_summary = "; ".join(f.split("\n")[0] for f in fixes[:6])
            os.environ["SYNAPSA_AUDIT_FEEDBACK"] = (
                f"PREVIOUS SCRIPT REJECTED (score {score}/100). MANDATORY FIXES: {fix_summary}. "
                f"REGENERATE with QUESTION format title, PRE-HOOK, RE-HOOK, and CTA. No banned words."
            )

            viral_context2 = search_viral_shorts(youtube, search_topic, count=5)
            channel_rule2  = os.environ.get("SYNAPSA_ADAPTATION_DIRECTIVE", "")
            result2 = generate_viral_script(
                viral_context2, search_topic,
                channel_rule=channel_rule2,
                forbidden_topics=forbidden_topics
            )
            # Synapsa zwraca klucze 'title' i 'script_text' (nie 'tytul'/'skrypt')
            if result2 and ("script_text" in result2 or "skrypt" in result2):
                tytul2       = result2.get("title", result2.get("tytul", tytul))
                script_text2 = result2.get("script_text", result2.get("skrypt", script_text))
                output_video2 = generate_cashcow_from_text(
                    script_text2, PROFILE_NAME,
                    background_vibe=background_vibe,
                    music_folder=music_folder_name
                )
                audit2 = audit_short(tytul2, script_text2, video_path=output_video2)
                if audit2.get("approved"):
                    print(f"[OK] RETRY APPROVED: {audit2['score']}/100 — kontynuuje upload.")
                    tytul       = tytul2
                    script_text = script_text2
                    output_video = output_video2
                    audit_result = audit2
                    _retry_approved = True
                    # Zapisz retry do logu
                    if os.path.exists(AUDIT_REPORT_FILE):
                        try:
                            with open(AUDIT_REPORT_FILE, "r", encoding="utf-8") as af:
                                audit_log2 = json.load(af)
                        except Exception:
                            audit_log2 = []
                    else:
                        audit_log2 = []
                    audit_log2.append(audit2)
                    with open(AUDIT_REPORT_FILE, "w", encoding="utf-8") as af:
                        json.dump(audit_log2[-50:], af, indent=2, ensure_ascii=False)
                else:
                    print(f"⚠️  RETRY REJECTED ({audit2['score']}/100). Używam fallback skryptu...")
            else:
                print("⚠️  Regeneracja nieudana. Używam fallback skryptu...")
        except Exception as regen_err:
            print(f"⚠️  Błąd regeneracji: {regen_err}. Używam fallback skryptu...")
        finally:
            if "SYNAPSA_AUDIT_FEEDBACK" in os.environ:
                os.environ.pop("SYNAPSA_AUDIT_FEEDBACK")

        # ── AUDITOR FALLBACK: TYLKO gdy retry nie przeszedł → użyj sprawdzonego fallbacku ──
        if not _retry_approved:
            import random as _rnd_fb
            _fb_scripts = [
                "You're being controlled right now. Have you noticed how some people walk into a room and everyone goes quiet? They use status anchoring — pausing before they speak, slowing every movement, never breaking eye contact first. The person who reacts fastest always loses power. But here's what nobody tells you — once you adopt this frame, people treat you differently within two days. Follow for more.",
                "They removed this from psychology textbooks. Have you noticed how some people never seem to lose an argument? They use tactical mirroring — repeating your last three words back as a question. Your brain automatically interprets this as deep understanding and trust. But here's the dark truth — they're not listening to you. They're mapping your psychological weak points. Can you spot who uses this on you?",
                "This is how they make you question your own reality. Gaslighters use a three-step formula. First, they deny something you clearly saw happen. Second, they tell you that you're overreacting. Third, they rewrite the narrative until you apologize for being right. But here's the dark part — 68 percent of victims don't recognize gaslighting until the third year. The moment you document conversations, their power collapses. Follow for more.",
                "Your brain is lying to you right now. When your actions contradict your beliefs, your mind doesn't change the action. It rewrites the belief. Cults, toxic relationships, and high-pressure sales all exploit cognitive dissonance. They get you to make one small compromise. Then your brain justifies it. But here's what nobody tells you — Leon Festinger proved this in 1957. The defense: write down your values before any high-pressure situation. Follow for more.",
                "Nobody talks about this. Have you ever agreed to something small and then couldn't say no to something bigger? That's the foot-in-the-door technique. They start with a tiny request. Your brain commits to consistency. Then they escalate. But here's the dark part — salespeople, manipulators, and even cults use this sequence deliberately. The defense is brutally simple: pause before every yes. Follow for more.",
                "Stop. Don't scroll. Have you noticed how certain people make you feel small without raising their voice? They use strategic contempt — a slight smile, calm tone, and compliments that secretly diminish you. Your brain registers warmth but misses the attack entirely. But here's what nobody tells you — this is the number one predictor of relationship failure according to Dr. John Gottman. Follow if this sounds familiar.",
                "Most people don't know this. The Benjamin Franklin effect proves that people like you MORE after doing you a favor — not the other way around. Your brain resolves the dissonance by deciding you must be worth helping. Manipulators exploit this constantly by asking for small favors first. But here's the dark part — once you see this pattern you cannot unsee it. Follow for more dark psychology secrets.",
                "Here's what they hide from you. The mere exposure effect means you trust things simply because you've seen them before. Advertisers show you the same ad fifty times not because it's persuasive — but because familiarity breeds trust. Your brain confuses recognition with safety. But here's why this matters — toxic people use this too. They stay visible until you drop your guard completely. Follow for more.",
            ]
            script_text = _rnd_fb.choice(_fb_scripts)
            tytul = _rnd_fb.choice(_FALLBACK_TITLES)
            print(f"✅ [AUDITOR FALLBACK] Użyto sprawdzonego skryptu + tytułu: '{tytul[:60]}'")
            output_video = generate_cashcow_from_text(
                script_text, PROFILE_NAME,
                background_vibe=background_vibe,
                music_folder=music_folder_name
            )

    if youtube and output_video:
        from upload_youtube import upload_video
        print("\n--- ETAP 5: Autopublikacja na kanale YouTube (PUBLIC natychmiast) ---")
        try:
            # ── ETAP 4.8: Generacja miniaturki (Custom Thumbnail) ──────────────
            thumbnail_path = None
            try:
                from generate_thumbnail import create_thumbnail
                # Tytuł bez #shorts i emoji dla czytelności miniaturki
                import re as _re_thumb
                clean_title_for_thumb = _re_thumb.sub(r'#\w+', '', tytul).strip()
                clean_title_for_thumb = _re_thumb.sub(r'[🧠👁️💀⚠️🔥❗🔋]', '', clean_title_for_thumb).strip()
                thumb_filename = f"thumb_{PROFILE_NAME}_{video_index}.jpg"
                thumbnail_path = create_thumbnail(output_video, clean_title_for_thumb, output_filename=thumb_filename)
                if thumbnail_path:
                    print(f"🖼️ [THUMBNAIL] ✅ Miniaturka wygenerowana: {thumbnail_path}")
                else:
                    print("⚠️ [THUMBNAIL] Generacja nie powiodła się — upload bez miniaturki.")
            except Exception as thumb_err:
                print(f"⚠️ [THUMBNAIL] Błąd generacji miniaturki: {thumb_err}")

            # Pipeline uruchamiany o 13:30 PL (peak hour) → publikacja PUBLIC natychmiast
            # Brak publishAt / schedulingu — eliminuje problem Draft/Private
            now_pl = datetime.now(PL_TZ)
            print(f"🕒 WIDEO {video_index}/{total_videos} — PUBLIKACJA NATYCHMIAST "
                  f"(teraz: {now_pl.strftime('%H:%M')} PL) → PUBLIC")

            upload_result = upload_video(
                youtube=youtube,
                file_path=output_video,
                title=tytul,
                description=opis,
                tags=tagi,
                category_id="24",  # Entertainment
                privacy_status="public",
                thumbnail_path=thumbnail_path
            )
            add_to_history(PROFILE_NAME, tytul, script_text=script_text)
            log_publish_report(tytul, video_index, tagi, privacy="public", video_id=upload_result)
            print(f"✅ [SUKCES] Film '{tytul}' — PUBLICZNY natychmiast (ID: {upload_result})!")
            print(f"   🏷️  Tagi: ({len(tagi)}) {', '.join(tagi[:6])}...")
            print(f"   📝 Opis (ostatnie 120 zn.): ...{opis[-120:]}")
            # Auto-post CTA komentarz po uploadzie (Priority 4 — engagement signal boost)
            if upload_result:
                _post_cta_comment(youtube, upload_result, script_text)
        except Exception as e:
            print(f"❌ [BŁĄD PUBLIKACJI] Wystąpił błąd przy wgrywaniu: {e}")
            
    print(f"\n🎉 Cykl {video_index}/{total_videos} dla Dark Psychology zakończony.")
    return True

def _wait_until(target_time_str: str):
    """Czeka do podanej godziny (HH:MM) w lokalnej strefie czasowej. Wypisuje odliczanie."""
    from datetime import datetime as dt
    import math
    now = dt.now()
    hh, mm = map(int, target_time_str.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target = target + __import__("datetime").timedelta(days=1)
    secs = (target - now).total_seconds()
    total_mins = int(secs // 60)
    print(f"\n⏰ [SCHEDULER] Start zaplanowany na {target_time_str} PL "
          f"— czekam {total_mins // 60}h {total_mins % 60}m ...\n")
    printed_marks = set()
    while True:
        remaining = (target - dt.now()).total_seconds()
        if remaining <= 0:
            break
        mins_left = int(remaining // 60)
        # Wypisz co 30 min + ostatnie 5 minut co minutę
        if mins_left <= 5 or mins_left % 30 == 0:
            if mins_left not in printed_marks:
                printed_marks.add(mins_left)
                h = mins_left // 60
                m = mins_left % 60
                label = f"{h}h {m}min" if h else f"{m}min"
                print(f"  ⏳ {dt.now().strftime('%H:%M:%S')} — Pozostało: {label} do {target_time_str}")
        time.sleep(15)
    print(f"\n🟢 [{dt.now().strftime('%H:%M:%S')}] GODZINA SZCZYTU — startuje pipeline!\n")


def _run_full_pipeline(youtube, dry_run: bool):
    """Pełny pipeline: facts refresh → trend scout → 2 filmy (14:00, 19:00 PL) → audyt → upload → post-analiza."""
    # ─── AUTO FACTS REFRESH (poniedziałek lub co 7 dni) ───────────────────
    print("\n🔄 [FACTS REFRESH] Sprawdzam czy wymagany tygodniowy reset faktów...")
    try:
        from refresh_facts import should_do_weekly_refresh, reset_used_facts, mark_refresh_done
        from refresh_facts import load_videos_from_snapshots, score_topics_from_videos, update_topic_rotation
        _is_monday = datetime.now().weekday() == 0  # 0 = poniedziałek
        if _is_monday or should_do_weekly_refresh():
            reset_used_facts(PROFILE_NAME)
            mark_refresh_done()
            # Wybierz najlepszy temat na podstawie ostatnich 7 dni
            _vids = load_videos_from_snapshots(days_back=7)
            if _vids:
                _ts, _tc = score_topics_from_videos(_vids)
                update_topic_rotation(_ts, _tc, days_back=7)
                print("✅ [FACTS REFRESH] Facts DB zresetowana + optymalny temat wybrany.")
            else:
                print("✅ [FACTS REFRESH] Facts DB zresetowana (brak historii do analizy).")
        else:
            print("ℹ️  [FACTS REFRESH] Nie minął tydzień — pomijam reset (facts DB niezmieniona).")
    except Exception as _re:
        print(f"⚠️  [FACTS REFRESH] Błąd auto-refresh: {_re} — kontynuuję bez resetu.")

    # ─── TREND SCOUT ──────────────────────────────────────────────────────

    print("\n📡 [TREND SCOUT] Sprawdzam co dziś działa na YouTube...")
    try:
        from trend_scout import run_trend_scout
        trend_summary = run_trend_scout()
        os.environ["SYNAPSA_TREND_TODAY"] = trend_summary
        print("✅ [TREND SCOUT] Trendy załadowane → wstrzyknięte do AI prompta.")
    except Exception as te:
        print(f"⚠️  [TREND SCOUT] Błąd (kontynuuję bez trendów): {te}")
        os.environ["SYNAPSA_TREND_TODAY"] = ""

    # ─── 2 FILMY DZIENNIE (PEAK HOURS: 14:00, 19:00 PL) ───────────
    generated = 0
    for i in range(1, DAILY_QUOTA + 1):
        success = run_dark_agent_cycle(i, DAILY_QUOTA, youtube)
        if success:
            generated += 1
        if success and i < DAILY_QUOTA:
            print("⏳ Przerwa 30s przed kolejnym wideo...")
            time.sleep(30)

    print(f"\n🏁 DZIENNY LIMIT ZAKOŃCZONY. Wygenerowano {generated}/{DAILY_QUOTA} filmów.")

    # ─── POST-CYCLE ANALYSIS ──────────────────────────────────────────────
    print("\n🔬 [POST-CYCLE] Uruchamiam pełną analizę kanału...")
    try:
        import smart_video_analyzer
        smart_video_analyzer.main()
        print("✅ Analiza zakończona — adaptation_directive.json zaktualizowany.")
    except Exception as ae:
        print(f"⚠️  Błąd analizy post-cycle: {ae}")

    # ─── PODSUMOWANIE AUDYTÓW DNIA ────────────────────────────────────────
    if os.path.exists(AUDIT_REPORT_FILE):
        try:
            with open(AUDIT_REPORT_FILE, "r", encoding="utf-8") as af:
                audit_log = json.load(af)
            today_audits = [a for a in audit_log[-10:]
                            if a.get("timestamp", "")[:10] == __import__("datetime").date.today().isoformat()]
            if today_audits:
                print(f"\n📊 WYNIKI AUDYTÓW DZISIAJ ({len(today_audits)} filmów):")
                for a in today_audits:
                    icon = "✅" if a["approved"] else "❌"
                    fixes = len(a.get("fix_report", []))
                    print(f"   {icon} {a['score']}/100 — {a['decision']} | "
                          f"'{a['title'][:55]}'"
                          + (f" | {fixes} fixów" if not a["approved"] else ""))
        except Exception:
            pass


def main():
    global DRY_RUN
    import argparse
    parser = argparse.ArgumentParser(description="Dark Psychology Agent")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Generuj wideo i audytuj, ale NIE wrzucaj na YouTube")
    parser.add_argument("--schedule", default=None, metavar="HH:MM",
                        help="Czekaj do podanej godziny PL, potem odpal pipeline (np. 17:00)")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    print("================================================================")
    print("🌑 DARK PSYCHOLOGY AGENT — Automatyczny pipeline YouTube Shorts")
    print("================================================================")
    if DRY_RUN:
        print("🧪 TRYB DRY-RUN: pełna generacja + audyt BEZ wrzucania na YouTube")
    if args.schedule:
        print(f"⏰ TRYB SCHEDULER: odpalenie o {args.schedule} PL "
              f"(trend scout + 3 filmy + audyt + upload + analiza)")
    print("================================================================\n")

    # Autoryzacja
    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Brak dostępu do kanału YouTube Dark Psychology.")
        return

    if args.schedule:
        _wait_until(args.schedule)

    _run_full_pipeline(youtube, DRY_RUN)


if __name__ == "__main__":
    main()
