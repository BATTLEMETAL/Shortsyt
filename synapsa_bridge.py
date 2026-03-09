import os
import sys
import json
import subprocess
import argparse

# Środowisko bogate z AI po stronie Synapsy
SYNAPSA_PYTHON = r"C:\Users\mz100\PycharmProjects\Synapsa\venv\Scripts\python.exe"
SYNAPSA_ROOT = r"C:\Users\mz100\PycharmProjects\Synapsa"

# ==============================================================================
# === 1. ZEGAR STERUJĄCY - IPC (Metody do importowania w the Cash Cow)
# ==============================================================================
def _run_synapsa_subprocess(command_args):
    """Wywołuje ten sam plik, ale używając ciężkiego środowiska Pytorch Synapsy i odczytując odpowiedź JSON z wyjścia."""
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
            except:
                continue
                
        print(f"❌ [SYNAPSA BRIDGE] Nie odnaleziono poprawnego wyjścia w STDOUT. Treść:\n{result.stdout}")
        return None
    except subprocess.TimeoutExpired:
        print(f"⏰ [SYNAPSA BRIDGE] TIMEOUT! Model AI nie odpowiedział w ciągu 5 minut. Sprawdź czy Synapsa działa.")
        return None
    except Exception as e:
        print(f"❌ [SYNAPSA BRIDGE] Błąd komunikacji wywołania podprocesu Python: {e}")
        return None

def generate_viral_script_with_synapsa(viral_context, niche_topic, channel_rule="", forbidden_topics=None):
    """Metoda wołana z The Cash Cow. Prosi podproces by skompilował LORA Model."""
    context_str = "||".join(viral_context) # Używamy delimiterów do wysłania komend w CLI
    
    # [BUG FIX] Omijamy limit argumentów w Windowsie (8191 zn.) używając Env Vars for Payload
    os.environ["SYNAPSA_CONTEXT_PAYLOAD"] = context_str
    os.environ["SYNAPSA_RULE_PAYLOAD"] = channel_rule
    
    cmd_args = ["--action", "script", "--niche", niche_topic]
    if forbidden_topics:
        os.environ["SYNAPSA_FORBIDDEN_PAYLOAD"] = "||".join(forbidden_topics)
    else:
        # Clear it just in case of environment bleed
        if "SYNAPSA_FORBIDDEN_PAYLOAD" in os.environ:
            os.environ.pop("SYNAPSA_FORBIDDEN_PAYLOAD")
        
    data = _run_synapsa_subprocess(cmd_args)
    if data:
        return data  # Teraz zwracamy całościowy słownik reżysera
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
                forbidden_str = "\nNEVER USE THE FOLLOWING TOPICS (THEY WERE ALREADY USED):\n" + "\n".join(f_list) + "\n"

        niche_lower = args.niche.lower()
        is_dark = any(k in niche_lower for k in ["psychology", "dark", "mindset", "manipulation"])
        
        persona = "Dark Psychology and Mindset expert" if is_dark else "Gen-Z internet culture expert"
        tone = "Cold, analytical, and objective. Use dark psychology terms." if is_dark else "Energetic, using modern slang like brainrot, ohio, sigma."
        vibe = "liminal space, dark rainy city, noir" if is_dark else "Roblox parkour, Minecraft gameplay, Subway Surfers"
        
        env_adaptation = os.getenv("SYNAPSA_ADAPTATION_DIRECTIVE", "").strip()
        adaptation_str = f"\n\n{env_adaptation}\n" if env_adaptation else ""
        
        prompt = f"""You are a professional YouTube Shorts scriptwriter. 
Your task is to write a highly viral, ultra-short script about: "{args.niche}".

TRENDING TITLES FOR INSPIRATION (Do not copy them):
{context_str}
{forbidden_str}
YOUR PERSONA: {persona}
TONE: {tone}
VISUAL VIBE: {vibe}

{env_rule}{adaptation_str}

EXTREMELY IMPORTANT: DO NOT YAP. DO NOT WRITE ANYTHING ELSE OR ANY INTRODUCTIONS. JUST GIVE ME THE SCRIPT.

RESPOND EXACTLY MATCHING THE FORMAT SHOWN IN THE EXAMPLE ABOVE. DO NOT USE JSON. DO NOT YAP.
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

            # First, try to find text explicitly under [TITLE]
            if "[TITLE]" in clean_text:
                parts = clean_text.split("[TITLE]")
                if len(parts) > 1:
                    t_lines = [l.strip() for l in parts[1].splitlines() if l.strip() and not l.strip().startswith('[')]
                    if t_lines:
                        title_candidate = t_lines[0].replace('"', '')

            for line in lines:
                # Remove common hallucinated stop strings
                if '[--' in line or '--]' in line:
                    continue
                # Skip lines that are clearly structural tags like [Prompt] [Title] [SCRIPT]
                if re.match(r'^\[\w[\w\s]*\]$', line):
                    continue
                # Skip lines that look like metadata labels (e.g. 'Description: ...')
                if re.match(r'^(Description|Script|Tags|Title|Warning|Trick|Hook|Prompt):', line, re.IGNORECASE):
                    continue
                # Collect inline tags like [tag1=...] or #hashtag
                if re.match(r'^(\[tag|#)', line):
                    tag_lines.append(line)
                    continue
                
                word_count = len(line.split())
                
                # If we still don't have a title, grab the first short line
                if title_candidate is None and word_count <= 10 and not any(c in line for c in ['.', '!', '?']):
                    title_candidate = line
                    continue
                
                # Script-like lines: real sentences (skip the title repeat)
                if 3 <= word_count <= 300 and line != title_candidate:
                    script_lines.append(line)

            if not script_lines:
                raise ValueError("Nie udalo sie wyodrebnic skryptu z odpowiedzi modelu.")

            # The AI prompt should enforce conciseness; do NOT arbitrarily truncate the text, 
            # because that destroys the CTA and loop mechanics.
            raw_script = ' '.join(script_lines)
            script_str = raw_script
            if title_candidate is not None:
                # Clean colons and weird trailing chars
                title_str = str(title_candidate).rstrip(':,- ')
                # Ensure it has a viral vibe
                if not any(emoji in title_str for emoji in ['🚨', '🧠', '👁️', '💀', '⚠️']):
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
            
            desc_str = f"Watch until the end. This changes everything. \n\n#{' #'.join(extracted_tags[:8])} #shorts #viral"

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

