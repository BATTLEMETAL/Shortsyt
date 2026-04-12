import os
import sys
import json
import subprocess
import argparse
import re
import logging
from dotenv import load_dotenv

load_dotenv()  # Load .env for API keys
logger = logging.getLogger("synapsa_bridge")

# Środowisko bogate z AI po stronie Synapsy
SYNAPSA_PYTHON = r"C:\Users\mz100\PycharmProjects\Synapsa\venv\Scripts\python.exe"
SYNAPSA_ROOT = r"C:\Users\mz100\PycharmProjects\Synapsa"

# ==============================================================================
# === 1. ZEGAR STERUJĄCY - IPC (Metody do importowania w the Cash Cow)
# ==============================================================================
def _check_vram_available(min_gb: float = 4.0) -> bool:
    """Sprawdza czy GPU ma wystarczająco wolnego VRAM. Zwraca False jeśli gra/inna aplikacja zajmuje kartę."""
    try:
        import subprocess as _sp
        # Używamy nvidia-smi zamiast torch (torch nie jest dostępny w shortsyt venv)
        result = _sp.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            free_mb = int(result.stdout.strip().split("\n")[0].strip())
            free_gb = free_mb / 1024
            if free_gb < min_gb:
                print(f"⚠️  [SYNAPSA] Za mało VRAM! Wolne: {free_gb:.1f}GB (potrzeba {min_gb}GB).")
                print(f"   Zamknij gry/aplikacje GPU i spróbuj ponownie.")
                return False
            print(f"✅ [SYNAPSA] VRAM OK: {free_gb:.1f}GB wolne — startuje model AI.")
            return True
    except Exception:
        pass  # nvidia-smi niedostępne — kontynuuj bez check
    return True

def _run_synapsa_subprocess(command_args):
    """Wywołuje ten sam plik, ale używając ciężkiego środowiska Pytorch Synapsy i odczytując odpowiedź JSON z wyjścia."""
    # GUARD: sprawdź VRAM przed uruchomieniem modelu AI
    if not _check_vram_available(min_gb=4.5):
        return None

    script_path = os.path.abspath(__file__)
    cmd = [SYNAPSA_PYTHON, script_path] + command_args

    try:
        # Kodowanie cp1250 może łamać się na Windowsie dla Polskich znaków w STDOUT
        run_env = os.environ.copy()
        run_env["PYTHONIOENCODING"] = "utf-8"
        # FIX AUDYT: timeout=300s (5 min) zabezpiecza przed zawieszeniem całego pipeline'u
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=run_env, timeout=300)
        if result.returncode != 0:
            print(f"❌ [SYNAPSA BRIDGE] Podproces AI zwrócił błąd!\n{result.stderr}")
            return None
            
        # Parowanie ostatniej linii, która musi być zczyszczonym obiektem JSON od skryptu wewnętrznego
        lines = result.stdout.strip().split('\n')
        # Przeszukiwamy logi od dołu w poszukiwaniu odpowiedniego wyjścia z the agent.
        for line in reversed(lines):
            try:
                data = json.loads(line)
                return data
            except (json.JSONDecodeError, ValueError):
                continue
                
        print(f"❌ [SYNAPSA BRIDGE] Nie odnaleziono poprawnego wyjścia w STDOUT. Treść:\n{result.stdout}")
        return None
    except subprocess.TimeoutExpired:
        print(f"⏰ [SYNAPSA BRIDGE] TIMEOUT! Model AI nie odpowiedział w ciągu 5 minut. Sprawdź czy Synapsa działa.")
        return None
    except Exception as e:
        print(f"❌ [SYNAPSA BRIDGE] Błąd komunikacji wywołania podprocesu Python: {e}")
        return None

def _gemini_fallback(niche_topic: str, forbidden_topics: list = None, viral_context: list = None) -> dict:
    """Gemini 2.0 Flash fallback — WYŁĄCZONY (brak quota na free tier)."""
    return None


def generate_viral_script_with_synapsa(viral_context, niche_topic, channel_rule="", forbidden_topics=None):
    """Metoda wołana z The Cash Cow.
    Priorytet:
      1. Lokalny model Qwen/Synapsa (gdy VRAM ≥ 4.5GB)
      2. Gemini 2.0 Flash API     (gdy Synapsa failuje — 1 req/dzień max)
      3. Statyczne skrypty       (w agent_dark_psychology.py — last resort)
    """
    context_str = "||".join(viral_context)

    # [BUG FIX] omijamy limit arg Windowsa używając Env Vars for Payload
    os.environ["SYNAPSA_CONTEXT_PAYLOAD"] = context_str
    os.environ["SYNAPSA_RULE_PAYLOAD"] = channel_rule

    cmd_args = ["--action", "script", "--niche", niche_topic]
    if forbidden_topics:
        os.environ["SYNAPSA_FORBIDDEN_PAYLOAD"] = "||".join(forbidden_topics)
    else:
        if "SYNAPSA_FORBIDDEN_PAYLOAD" in os.environ:
            os.environ.pop("SYNAPSA_FORBIDDEN_PAYLOAD")

    # ── ETAP 1: Sprawdź VRAM przed uruchomieniem lokalnego modelu ─────────
    if not _check_vram_available(min_gb=4.5):
        print("🤖 [SYNAPSA BRIDGE] VRAM niewystarczający — zamknij gry/aplikacje GPU!")
        return {"error": f"[VRAM] Za mało VRAM dla Synapsy. Zamknij gry. (Nisza: {niche_topic})"}

    # ── ETAP 2: Uruchom lokalny model ─────────────────────────────────────
    data = _run_synapsa_subprocess(cmd_args)
    if data:
        return data  # Zwracamy pełny słownik reżysera

    return {"error": f"Synapsa nie dała rady obsłużyć żądania podprocesu. (Nisza: {niche_topic})"}

def generate_metadata_with_synapsa(topic: str):
    """Metoda wołana z The Cash Cow do The Synapsy RTx."""
    data = _run_synapsa_subprocess(["--action", "meta", "--topic", topic])
    if data and "tytul" in data:
        return data["tytul"], data["opis"], data["tagi"]
    return f"{topic} #shorts", f"Akcja z gry: {topic}!", ["gaming", "shorts", "viral"]

# ==============================================================================
# === 2. WNĘTRZE KONTENERA AI (Metody wołane wyłącznie po stronie PYTORCH/SYNAPSA VENV)
# ==============================================================================

if __name__ == "__main__":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", type=str)
    parser.add_argument("--niche", type=str, default="")
    parser.add_argument("--topic", type=str, default="")
    parser.add_argument("--rule", type=str, default="")
    args = parser.parse_args()
    
    # Odbierz z environment
    env_context = os.environ.get("SYNAPSA_CONTEXT_PAYLOAD", "")
    env_forbidden = os.environ.get("SYNAPSA_FORBIDDEN_PAYLOAD", "")
    env_rule = os.environ.get("SYNAPSA_RULE_PAYLOAD", args.rule)
    
    # Dodajemy źródło, by dało się zaimportować The Agent
    if SYNAPSA_ROOT not in sys.path:
        sys.path.insert(0, SYNAPSA_ROOT)
        
    try:
        from agent import SmartAgent
    except ImportError as e:
        print(json.dumps({"error": f"Brak bibliotek ML lub nieprawidłowy katalog: {e}"}))
        sys.exit(1)

    # Bootujemy LORA (WYŁĄCZONA NA POTRZEBY TESTU LOOPA - HALUCYNUJE POEZJE)
    adapter_path = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
        
    local_agent = SmartAgent(
            adapter_path=adapter_path, 
            target_project=r"C:\Users\mz100\PycharmProjects\shortsyt", 
            context_window=8192
    )

    if args.action == "script":
        context_list = env_context.split("||")
        context_str = "\n".join(context_list)
        
        forbidden_str = ""
        if env_forbidden:
            f_list = [f"- {t}" for t in env_forbidden.split("||") if t.strip()]
            if f_list:
                forbidden_str = "\nCRITICAL RULE - NEVER USE THESE TOPICS (THEY WERE ALREADY USED):\n" + "\n".join(f_list) + "\nYOU MUST SELECT A COMPLETELY DIFFERENT, OBSCURE FACT.\n"

        niche_lower = args.niche.lower()
        is_dark = any(k in niche_lower for k in ["psychology", "dark", "mindset", "manipulation"])
        
        persona = "Dark Psychology and Mindset expert" if is_dark else "Gen-Z internet culture expert"
        tone = "Cold, analytical, and objective. Use dark psychology terms." if is_dark else "Energetic, using modern slang like brainrot, ohio, sigma."
        vibe = "Peaky Blinders, American Psycho, mysterious figure in suit, wolves, dark city at night, dark red/navy colors" if is_dark else "Minecraft parkour daytime, clear blue sky, minimal chaos"
        
        env_adaptation = os.getenv("SYNAPSA_ADAPTATION_DIRECTIVE", "").strip()
        adaptation_str = f"\n\nDATA-DRIVEN DIRECTIVES FROM CHANNEL ANALYTICS (FOLLOW STRICTLY):\n{env_adaptation}\n" if env_adaptation else ""

        env_trend_today = os.getenv("SYNAPSA_TREND_TODAY", "").strip()
        trend_str = f"\n\n{env_trend_today}\n" if env_trend_today else ""

        # Curated facts from facts_database.py — 3 specific psychology facts per video
        env_facts = os.getenv("SYNAPSA_FACTS_PAYLOAD", "").strip()
        facts_str = f"\n{env_facts}\n" if env_facts else ""
        
        prompt = f"""You are an elite YouTube Shorts scriptwriter specializing in viral dark psychology content.
Your task: Write a SHORT (11-20 second) ultra-viral script about a SPECIFIC, OBSCURE sub-topic of: "{args.niche}".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 TITLE FORMAT RULES (DATA-PROVEN — VIOLATION = FAILURE):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ USE ONE OF THESE TWO PROVEN FORMATS (alternate between them):

FORMAT A — QUESTION (personal, curiosity-triggering):
   - "Have you ever felt someone draining your energy? 🧠 #shorts"
   - "Can you spot the dark psychology tactic used on you? 👁️ #shorts"
   - "Have you noticed how some people command respect effortlessly? 🧠 #shorts"

FORMAT B — NUMBERED LIST (highest global views, 90K+ confirmed):
   - "5 Dark Psychology Tricks to Control Anyone 🧠 #shorts"
   - "3 Signs Someone Is Manipulating You Right Now 👁️ #shorts"
   - "2 Dark Body Language Signals Most People Miss 💀 #shorts"

🚫 ABSOLUTELY FORBIDDEN title formats:
   - NEVER start with [Name's ...] or any [WORD] bracket prefix
   - NEVER use: 'revealed', 'disappears', 'save', 'unveiled', 'behind'
   - Those patterns get ZERO views. Algorithmically punished.

{facts_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔬 MANDATORY FACTS — BUILD YOUR SCRIPT AROUND THESE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If curated psychology facts are provided above — you MUST use them as the core of your 3 reveals.
Each fact = 1-2 sentences max. Fact 1 shocks, Fact 2 deepens, Fact 3 gives viewer a weapon.
If NO facts provided — invent an equally specific, obscure, sourced psychological mechanism.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 MANDATORY SCRIPT STRUCTURE (FOLLOW EXACTLY — ALL 7 LINES REQUIRED):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Line 1: PRE-HOOK (4-6 words, pattern interrupt). Choose ONE:
  • "Most people don't know this."
  • "Stop. Don't scroll."
  • "They removed this from textbooks."
  • "Nobody talks about this."
  • "You're being controlled right now."

Line 2: QUESTION HOOK (curiosity trigger, makes viewer stay):
  • "Have you noticed how some people..."
  • "Have you ever felt..."
  • "Can you spot when someone..."

Lines 3-5: CORE CONTENT (specific scenario + psychology fact + named mechanism):
  • Name the EXACT psychological mechanism (e.g. "tactical mirroring", "status anchoring", "intermittent reinforcement")
  • Give a SPECIFIC real-world scenario (not generic advice)
  • Include ONE statistic or researcher name (e.g. "Paul Ekman", "93 percent accuracy", "Festinger 1957")

Line 6: RE-HOOK (dramatic pivot before the payoff):
  • "But here's the dark part —"
  • "But here's what nobody tells you —"
  • "And here's why this matters —"

Line 7: PAYOFF + CTA (actionable takeaway + engagement trigger):
  • End with: "Follow for more." or "Can you spot who uses this on you?"

🚨 CRITICAL: Your script MUST contain ALL 7 elements above. If PRE-HOOK, RE-HOOK, or CTA is missing, the script will be REJECTED. Total length: 40-65 words.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPOND ONLY IN THIS EXACT FORMAT (no preamble, no explanations):
[TITLE]
Your viral YouTube Shorts title here 🧠 #shorts
[SCRIPT]
Your 40-65 word script here. Cold. Analytical. MUST include PRE-HOOK + QUESTION HOOK + CORE + RE-HOOK + CTA.
[TAGS]
darkpsychology, manipulation, psychology, mindset, sigma, power, secrets, viral

DO NOT ADD INTRODUCTIONS. DO NOT YAP. RESPOND ONLY WITH THE FORMAT ABOVE.
"""
        response = local_agent.ask_brain(prompt, max_new_tokens=1500, mode="precise")
        import re
        
        # Loguj surową odpowiedź modelu dla DEBUG
        safe_niche = "".join([c if c.isalnum() else "_" for c in args.niche])[:15]
        with open(f"synapsa_raw_{safe_niche}.log", "w", encoding="utf-8") as _log:
            _log.write(response)
        
        # Robust heuristic extractor — tolerant of Qwen's non-standard output format
        try:
            # 1. Strip markdown fences
            clean_text = response.replace("```json", "").replace("```text", "").replace("```", "").strip()
            
            # 1.5 Normalize AI conversational labels into strict blocks
            clean_text = re.sub(r'(?i)^\s*\*?\*?Title:\*?\*?\s*', '[TITLE]\n', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'(?i)^\s*\*?\*?Script:\*?\*?\s*', '[SCRIPT]\n', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'(?i)^\s*\*?\*?Tags:\*?\*?\s*', '[TAGS]\n', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'(?i)\[TITLE\]', '\n[TITLE]\n', clean_text)
            clean_text = re.sub(r'(?i)\[SCRIPT\]', '\n[SCRIPT]\n', clean_text)
            clean_text = re.sub(r'(?i)\[TAGS\]', '\n[TAGS]\n', clean_text)
            
            # 2. Strip hallucinated suffixes (e.g. '---', '✅ If this response was helpful...')
            for stop_marker in ['---', '\u2705 If this response', 'Let me know', 'Feel free', 'I hope this']:
                idx = clean_text.find(stop_marker)
                if idx != -1:
                    clean_text = clean_text[:idx].strip()

            # 3. Parse lines
            lines = [l.strip() for l in clean_text.splitlines() if l.strip()]

            # 4. Identify script body lines & extract title robustly
            script_lines = []
            tag_lines = []
            title_candidate = None

            # PRIORITY 1: Extract text explicitly from [TITLE] block
            if "[TITLE]" in clean_text:
                parts = clean_text.split("[TITLE]")
                if len(parts) > 1:
                    t_lines = [l.strip() for l in parts[1].splitlines() if l.strip() and not l.strip().startswith('[')]
                    if t_lines:
                        # Take only what's before [SCRIPT] or [TAGS] — i.e. just the title text
                        raw_title = t_lines[0]
                        # Strip structural tags like [SCRIPT], [TAGS] if they sneak in
                        raw_title = re.sub(r'\[\w+\]', '', raw_title).strip()
                        if raw_title:
                            title_candidate = raw_title.replace('"', '')

            # ── BLOCK-BASED EXTRACTION (Priority fix: prevents tags from leaking into TTS) ──
            # Extract script ONLY from between [SCRIPT] and [TAGS]/[TAG] markers
            _block_extracted = False
            if "[SCRIPT]" in clean_text:
                script_block = clean_text.split("[SCRIPT]", 1)[1]
                # Cut at [TAGS] or [TAG] if present
                for tag_marker in ["[TAGS]", "[TAG]", "[Tags]", "[Tag]"]:
                    if tag_marker in script_block:
                        _tag_part = script_block.split(tag_marker, 1)[1]
                        tag_lines = [l.strip() for l in _tag_part.splitlines() if l.strip()]
                        script_block = script_block.split(tag_marker, 1)[0]
                        break
                block_lines = [l.strip() for l in script_block.splitlines()
                               if l.strip() and not re.match(r'^\[\w+\]$', l.strip())]
                if block_lines:
                    script_lines = block_lines
                    _block_extracted = True

            # Fallback: line-by-line heuristic (only if block extraction failed)
            if not _block_extracted:
                for line in lines:
                    if '[--' in line or '--]' in line:
                        continue
                    if re.match(r'^\[\w[\w\s]*\]$', line):
                        continue
                    if re.match(r'^(Description|Script|Tags|Title|Warning|Trick|Hook|Prompt):', line, re.IGNORECASE):
                        continue
                    if re.match(r'^(\[tag|#)', line):
                        tag_lines.append(line)
                        continue
                    word_count = len(line.split())
                    if 3 <= word_count <= 300 and line != title_candidate:
                        script_lines.append(line)

            if not script_lines:
                raise ValueError("Nie udalo sie wyodrebnic skryptu z odpowiedzi modelu.")

            # Join and clean script text
            raw_script = ' '.join(script_lines)

            # Strip leaked comma-separated tag lists at the end of script
            # Pattern: "...follow for more. darkpsychology, manipulation, psychology, viral"
            raw_script = re.sub(r',\s*(?:dark\w+|psychology\w*|manipulation\w*|mindset\w*|sigma\w*|viral\w*|shorts?\w*|power\w*|secrets?\w*|stoic\w*|brain\w*|behavior\w*|social\w*|cognitive\w*|hidden\w*|trick\w*|persuasion\w*|respect\w*|body\w*|language\w*)(?:\s*,\s*(?:dark\w*|psychology\w*|manipulation\w*|mindset\w*|sigma\w*|viral\w*|shorts?\w*|power\w*|secrets?\w*|stoic\w*|brain\w*|behavior\w*|social\w*|cognitive\w*|hidden\w*|trick\w*|persuasion\w*|respect\w*|body\w*|language\w*))+\s*$', '', raw_script, flags=re.IGNORECASE).strip()

            # Strip standalone "short" or "#short" leaked from title parsing
            raw_script = re.sub(r'^\s*#?short\s+', '', raw_script, flags=re.IGNORECASE).strip()

            # ── AGGRESSIVE TAG CLEANUP (Priority fix: tags leaking into TTS audio) ──
            # 1. Strip any #hashtags from script text entirely
            raw_script = re.sub(r'#\w+', '', raw_script).strip()
            # 2. Strip trailing tag-like words (no comma, just space-separated at the end)
            #    Pattern: "...Follow for more. darkpsychology manipulation psychology viral shorts"
            TAG_WORDS = r'(?:dark(?:psychology)?|psychology(?:facts)?|manipulation|mindset|sigma|viral|shorts?|power|secrets?|stoic(?:ism)?|brain(?:rot)?|behavior|social|cognitive|hidden|tricks?|persuasion|respect|body|language|trending|fyp|psychologyfacts|humanbehavior|subconscious|psychologyshorts)'
            raw_script = re.sub(rf'(?:,?\s+{TAG_WORDS})+\s*$', '', raw_script, flags=re.IGNORECASE).strip()
            # 3. Strip trailing lone punctuation or whitespace
            raw_script = raw_script.rstrip(' ,;.')
            # 4. Ensure script doesn't end mid-sentence weirdly — re-add period if needed
            if raw_script and raw_script[-1] not in '.!?':
                raw_script += '.'

            script_str = raw_script

            # PRIORITY 2 FALLBACK: If no [TITLE] found, extract the Hook sentence from the script
            if title_candidate is None or len(title_candidate.split()) < 3:
                # Take the first sentence (up to first ., !, or ?) from the script
                hook_match = re.match(r'^([^.!?]{15,120}[.!?])', script_str.strip())
                if hook_match:
                    title_candidate = hook_match.group(1).strip()
                else:
                    # Last-resort: take first 8 words
                    title_candidate = ' '.join(script_str.split()[:8]) + '...'

            if title_candidate is not None:
                # Clean colons and weird trailing chars
                title_str = str(title_candidate).rstrip(':,- ')
                # Cap length at 80 chars (YouTube Shorts title best practice)
                if len(title_str) > 80:
                    title_str = title_str[:77] + '...'
                # Ensure it has a viral vibe emoji
                if not any(emoji in title_str for emoji in ['🚨', '🧠', '👁️', '💀', '⚠️', '🔥', '❗']):
                    title_str += " 🧠"
            else:
                 title_str = f"Dark Truth About {args.niche} 🧠"
            # 5. Parse tags from tag_lines or extract hashtags from all text
            raw_tags = ','.join(tag_lines)
            extracted_tags = re.findall(r'[A-Za-z][A-Za-z0-9]+', raw_tags)
            if not extracted_tags:
                extracted_tags = re.findall(r'#([A-Za-z][A-Za-z0-9]+)', clean_text)
            if not extracted_tags:
                extracted_tags = ["darkpsychology", "manipulation", "psychology", "mindset", "sigma", "viral", "shorts"]
            
            # Generate a UNIQUE description based on script content (identical desc = YouTube spam penalty)
            script_preview = script_str[:120].strip().rstrip('.,!?')
            hook_angle = script_str.split('.')[0][:80].strip() if '.' in script_str else script_preview[:60]
            hashtag_str = ' #'.join(extracted_tags[:8])
            # Rotate through 5 description templates — ensures every video has unique metadata (Priority 5)
            desc_templates = [
                # Template 1: Curiosity gap
                f"{hook_angle}... Most people never realize this is happening to them every single day.\n\nFollow for more dark psychology insights that change how you see people.\n\n#{hashtag_str} #shorts #viral #darkpsychology",
                # Template 2: Warning / urgency
                f"WARNING: {hook_angle}... If you can't spot this, you're already vulnerable to it.\n\nFollow before this gets too uncomfortable to watch.\n\n#{hashtag_str} #shorts #viral #darkpsychology",
                # Template 3: Social proof
                f"{hook_angle}... Thousands of people have recognized this pattern in someone close to them.\n\nComment below if this hit different for you. 👇\n\n#{hashtag_str} #shorts #viral #darkpsychology",
                # Template 4: Transformation / revelation
                f"{hook_angle}... Once you understand this, you can never unsee it in people around you.\n\nFollow for more secrets about the hidden mechanics of human behavior.\n\n#{hashtag_str} #shorts #viral #darkpsychology",
                # Template 5: Authority
                f"{hook_angle}... Dark psychology researchers have studied this pattern for decades — and it explains almost everything.\n\nSave this. You'll need it.\n\n#{hashtag_str} #shorts #viral #darkpsychology",
            ]
            desc_idx = abs(hash(script_str[:40])) % len(desc_templates)
            desc_str = desc_templates[desc_idx]

            parsed = {
                "viral_score": 9,
                "vs_top_shorts": "Heuristic extraction active",
                "viral_reasoning": "Content generated successfully",
                "script_text": script_str,
                "background_vibe": vibe,
                "music_folder": "dark_mindset" if is_dark else "brainrot",
                "title": title_str[:90],
                "description": desc_str,
                "seo_tags": extracted_tags[:20]
            }

            # Clean script: keep letters, punctuation, apostrophes; strip emoji/special chars
            script_raw = parsed.get('script_text', '').strip()
            parsed['script_text'] = re.sub(r'[^\w\s.,!?;:\-\u0105\u0119\u00f3\u015b\u017a\u017c\u0107\u0144\u0104\u0118\u00d3\u015a\u0179\u017b\u0106\u0143\']', '', script_raw)
            print(json.dumps(parsed, ensure_ascii=False))
        except Exception as e:
            print(f"Błąd parsowania odpowiedzi jako JSON: {e}")
            is_dark = any(x in args.niche.lower() for x in ['dark', 'psychology', 'manipulation', 'mind', 'body', 'language'])
            category_key = "dark_mindset" if is_dark else "brainrot"
            bg_vibe = "dark rainy city walk no copyright 4k"

            # Zwracamy pusty script_text by wyzwolić retry w głownym agencie
            err_json = {
                "script_text": "",
                "background_vibe": bg_vibe,
                "music_folder": category_key,
                "viral_score": 0,
                "vs_top_shorts": "Błąd parsowania.",
                "title": f"The dark truth about {args.niche} #shorts",
                "description": f"Must watch! #darkpsychology #shorts",
                "seo_tags": ["darkpsychology"],
                "error_parser": str(e),
                "error": "Synapsa zwrocila nieprawidlowy JSON."
            }
            print(json.dumps(err_json, ensure_ascii=False))

    elif args.action == "meta":
        prompt = f"""
Jesteś wziętym twórcą na YouTube znanym z klikalnych szortów o AVD 110%. 
Temat filmu: "{args.topic}". 

Zbuduj i WYPISZ TYLKO CZYSTY JSON, bez wstępów formatujących:
{{
  "tytul": "Twój zatrzymujący scrollowanie tytuł z jednym emoji",
  "opis": "Twój opis z FOMO",
  "tagi": ["słowo1", "słowo2", "słowo3"]
}}
"""
        response = local_agent.ask_brain(prompt, max_new_tokens=400)
        import re
        json_str = response
        if "```json" in response:
            json_str = re.search(r'```json(.*?)```', response, re.DOTALL).group(1)
        elif "```" in response:
            json_str = re.search(r'```(.*?)```', response, re.DOTALL).group(1)
            
        try:
            metadata = json.loads(json_str.strip())
            # Ensure proper keys
            output = {
                "tytul": metadata.get("tytul", f"Genialny short o {args.topic} #viral"),
                "opis": metadata.get("opis", f"Masz wiedzę na temat {args.topic}? Ten film zwali Cię z nóg! #shorts"),
                "tagi": [str(x) for x in metadata.get("tagi", [])]
            }
            print(json.dumps(output, ensure_ascii=False))
        except BaseException as e:
            print(json.dumps({
                "tytul": f"Epicki short o {args.topic} #shorts",
                "opis": f"Wideo sztucznej inteligencji: {args.topic}. {str(e)}",
                "tagi": ["viral", "gaming", "shorts", "ai"]
            }, ensure_ascii=False))

