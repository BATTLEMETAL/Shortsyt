import os
import json
import subprocess
import glob
import shutil
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop, resize
import random
import pysrt


OUTPUT_DIR = "temp_videos"
BACKGROUNDS_DIR = "videos"  # Folder z darmowymi tłami wideo np. Minecraft parkour / GTA
MUSIC_DIR = "music"         # Folder z chwytliwą muzyką lo-fi/phonk w tle
ACCOUNTS_DIR = "accounts"   # Folder przechowujący konfiguracje 5 kont

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(ACCOUNTS_DIR, exist_ok=True)

# ── WALIDACJA: Sprawdź czy ffmpeg jest na PATH ────────────────────────────────
if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    raise RuntimeError(
        "❌ KRYTYCZNE: ffmpeg i ffprobe muszą być zainstalowane i na PATH!\n"
        "   Pobierz z: https://ffmpeg.org/download.html"
    )

# ── CACHE: Model Whisper ładowany raz per sesja (461MB) ────────────────────────
_WHISPER_MODEL = None

def _get_whisper_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        import whisper
        print("🧠 Ładowanie modelu Whisper 'small' (jednorazowo per sesja)...")
        _WHISPER_MODEL = whisper.load_model("small")
    return _WHISPER_MODEL

# Pobieranie ewolucyjnych promptów uczonych przez AI z feedback-loopa
PROMPTS_FILE = os.path.join(ACCOUNTS_DIR, "niche_prompts.json")

def load_niches():
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "kanal_1": {"nazwa": "brainrot", "prompt": "Zbuduj super wesołą, gamingową mini-opowieść (ok. 80 słów) o zabawnej szkolnej wycieczce w świecie Roblox. Używaj młodzieżowego internetowego slangu (np. ohio, sigma). Bądź całkowicie bezpieczny dla dzieci (PG-13). NIE POWTARZAJ ciągle tych samych słów; buduj logiczną, zabawną The fabułę z morałem. Ostatnie zdanie ma łączyć się z pierwszym (stworzenie Loop)."},
        "kanal_2": {"nazwa": "psychologia", "prompt": "Napisz mi 3 mroczne triki psychologiczne, które ludzie stosują na co dzień. Bądź konkretny. Tekst max 40 sekund."},
        "kanal_3": {"nazwa": "finanse", "prompt": "Napisz mi 1 brutalną prawdę o tym dlaczego większość ludzi jest biedna. Tekst ma być ostry i motywujący. Czas 40 sekund."},
        "kanal_4": {"nazwa": "reddit_stories", "prompt": "Napisz mi krótką i wciągającą historię typu Reddit z perspektywy pierwszej osoby o rzekomej zdradzie partnera. Posiadaj plot twist na końcu. Czas max 50 sekund."},
        "kanal_5": {"nazwa": "quizy", "prompt": "Napisz mi 3 pytania quizowe o zwierzętach. Zadaj pytanie, zrób 3 sekundy przerwy, a potem odpowiedź. Tekst 40 sekund."}
    }

CHANNELS_NICHES = load_niches()


# Głosy AI (Edge-TTS)
VOICE_EN = "en-US-ChristopherNeural" # Głęboki, kinowy głos idealny do "Dark Psychology".
VOICE_PL = "pl-PL-MarekNeural"       # Głos męski dla polskich treści.

def get_script_from_ai(prompt: str) -> str:
    """
    Generuje scenariusz przez Synapsę (Qwen2.5-Coder).
    Gemini API usunięte — wszystko lokalnie, bez kluczy API.
    """
    try:
        from synapsa_bridge import generate_viral_script_with_synapsa
        result = generate_viral_script_with_synapsa(
            viral_context=[prompt],
            niche_topic="general",
            channel_rule=prompt,
        )
        if result and "script_text" in result:
            return result["script_text"]
        return prompt  # fallback: użyj promptu jako tekstu wprost
    except Exception as e:
        print(f"❌ Błąd Synapsy (get_script_from_ai): {e}")
        return "Synapsa nie działa. Przykładowy tekst testowy do weryfikacji systemu."

def format_ass_time(seconds_float):
    """Zmienia sekundy z Whispera na format HH:MM:SS.CS dla Advanced SubStation Alpha"""
    hours = int(seconds_float // 3600)
    minutes = int((seconds_float % 3600) // 60)
    seconds = int(seconds_float % 60)
    centiseconds = int(round((seconds_float % 1) * 100))
    if centiseconds == 100:
        centiseconds = 99
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

def _get_audio_duration(path: str) -> float:
    """Zwraca długość pliku audio w sekundach (ffprobe)."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _run_edge_tts_api(text: str, voice: str, rate: str, output_path: str):
    """Wywołuje Edge-TTS przez Python API (asyncio) — obchodzi bug CLI --file na Win/Py3.13."""
    import asyncio
    import edge_tts

    async def _generate():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(output_path)

    # Python 3.10+ — asyncio.run() jest bezpieczne
    asyncio.run(_generate())


def generate_speech_and_subs(text: str, output_audio: str, output_subs_ass: str, voice: str = VOICE_PL, profile_name: str = "brainrot"):
    """META 2026: Generuje audio (Edge-TTS) a następnie napisy 1-po-1 z animacją i kolorowaniem rotacyjnym (Hormozi)"""
    print(f"🗣️ Generowanie bezwzględnego audio (Edge-TTS: {voice})...")
    import sys
    
    # Zapisujemy skrypt do pliku (debug / historia)
    temp_txt_path = f"temp_videos/temp_script_{profile_name}.txt"
    with open(temp_txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    rate = "+15%" if "pl" in voice else "+12%"  # +12% dla EN = wolniejsze, autorytatywne tempo = wyższa retencja

    # ── METODA 1: Python API edge_tts (najstabilniejsza — bez problemów --file) ──
    try:
        _run_edge_tts_api(text, voice, rate, output_audio)
    except Exception as api_err:
        print(f"  ⚠️  Edge-TTS API error: {api_err}. Próbuję CLI --text fallback...")
        # ── METODA 2: CLI --text (nie --file! --file ma bug encoding na Win/Py3.13) ──
        edge_tts_bin = os.path.join(os.path.dirname(sys.executable), "edge-tts.exe")
        if not os.path.exists(edge_tts_bin):
            edge_tts_bin = "edge-tts"
        cmd = [
            edge_tts_bin,
            "--voice", voice,
            "--rate", rate,
            "--text", text,
            "--write-media", output_audio
        ]
        subprocess.run(cmd, check=True, timeout=120)

    # ── GUARD: Walidacja długości audio (KRYTYCZNE — zapobiega 1s renderom) ──────
    audio_dur = _get_audio_duration(output_audio)
    if audio_dur < 5.0:
        print(f"  🚨 [AUDIO GUARD] Audio tylko {audio_dur:.1f}s! Oczekiwano ≥8s. Retry z CLI --text...")
        # Retry z CLI --text jako last resort
        edge_tts_bin = os.path.join(os.path.dirname(sys.executable), "edge-tts.exe")
        if not os.path.exists(edge_tts_bin):
            edge_tts_bin = "edge-tts"
        cmd = [
            edge_tts_bin,
            "--voice", voice,
            "--rate", rate,
            "--text", text,
            "--write-media", output_audio
        ]
        subprocess.run(cmd, check=True, timeout=120)
        audio_dur = _get_audio_duration(output_audio)
        if audio_dur < 5.0:
            raise Exception(f"Edge-TTS FAILED: audio {audio_dur:.1f}s po retry. Skrypt: '{text[:80]}...'")
    print(f"  ✅ Audio OK: {audio_dur:.1f}s")

    # 1B. Silence Trimming (Usuwanie martwej ciszy NA KOŃCACH audio - nie w środku!)
    print("✂️ Usuwanie martwej ciszy na końcach audio (FFmpeg silenceremove)...")
    temp_trimmed = output_audio.replace(".mp3", "_trimmed.mp3")
    trim_cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", output_audio,
        "-af", "silenceremove=start_periods=1:start_threshold=-55dB:start_duration=0.1:stop_periods=-1:stop_threshold=-55dB:stop_duration=0.5",
        "-b:a", "320k",
        temp_trimmed
    ]
    try:
        result_trim = subprocess.run(
            trim_cmd, check=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result_trim.returncode == 0 and os.path.exists(temp_trimmed) and os.path.getsize(temp_trimmed) > 1024:
            # GUARD: sprawdź czy trimmed audio nie jest krótsze niż 5s
            trimmed_dur = _get_audio_duration(temp_trimmed)
            min_acceptable = max(5.0, audio_dur * 0.3)  # min 30% of original or 5s
            if trimmed_dur >= min_acceptable:
                import shutil
                shutil.move(temp_trimmed, output_audio)
                print(f"  ✅ Trimmed: {audio_dur:.1f}s → {trimmed_dur:.1f}s")
            else:
                print(f"  ⚠️  silenceremove skróciło audio do {trimmed_dur:.1f}s (< 30% oryginału {audio_dur:.1f}s) — zachowuję oryginał")
                os.remove(temp_trimmed)
        else:
            # Fallback: audio zbyt krótkie lub błąd silenceremove — zostaw oryginał
            stderr_msg = result_trim.stderr.decode("utf-8", errors="ignore")[:200] if result_trim.stderr else ""
            print(f"  ⚠️  silenceremove pominięty (krótkie audio lub błąd): {stderr_msg[:80]}")
            if os.path.exists(temp_trimmed):
                os.remove(temp_trimmed)
    except Exception as e:
        print(f"  ⚠️  silenceremove wyjątek (kontynuuję bez trima): {e}")
        if os.path.exists(temp_trimmed):
            os.remove(temp_trimmed)
    
    if os.path.exists(output_audio) and os.path.getsize(output_audio) == 0:
        raise Exception("Krytyczny błąd Edge-TTS - plik MP3 jest zerowy! Dalsze parsowanie spali FFMPEG.")
    
    # 2. Transkrypcja Whisper na poziomie słów (Word-by-word timestamps)
    print("🧠 Uruchamiam AI Whisper do ekstrakcji słów (cached model)...")
    w_model = _get_whisper_model()
    result = w_model.transcribe(output_audio, word_timestamps=True, fp16=False)

    # 3. Format nagłówka ASS (Styl Hormozi - potężne animacje, dwa odrębne tryby Niche)
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CinematicDark,Impact,165,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,3,0,1,10,4,5,30,30,0,1
Style: CinematicDarkGold,Impact,165,&H0000E5FF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,3,0,1,10,4,5,30,30,0,1
Style: PopWordBrainrot,Impact,175,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,1,0,0,0,100,100,2,0,1,8,3,5,20,20,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Kolory dla dark psychology — złoty dla key words (BGR: 0x00E5FF = złoto-żółty)
    gold_color        = "{\\c&H0000E5FF&}"   # złoty/żółty highlight
    red_color         = "{\\c&H0000FF&}"     # czerwony dla triggerów
    rotational_colors = ["{\\c&H00FFFF&}", "{\\c&H00FF00&}", "{\\c&H00A5FF&}"]  # brainrot: żółty/zielony/pomarańczowy
    # Rozszerzony zestaw dark trigger keywords
    dark_keywords = [
        "MANIPULATION", "SECRET", "DESTROY", "DARK", "POWER", "CONTROL",
        "DANGER", "PSYCHOLOGY", "TRICK", "MIND", "TOXIC", "WEAPON",
        "WARNING", "BRAIN", "FEAR", "VICTIM", "TRAP", "ENEMY", "LIES",
        "WEAK", "DOMINATE", "SILENT", "STARE", "NEVER", "ALWAYS",
        "NOBODY", "EVERYBODY", "TRUTH", "EXPOSED", "HIDDEN", "RULE",
        "OBEY", "SUBMIT", "BROKEN", "CRUSHING", "ABSOLUTE", "BRUTAL",
        "NARCISSIST", "LIAR", "MANIPULATE", "STOP", "WATCH", "HERE",
    ]
    gold_keywords = [
        "RESPECT", "COMMAND", "EFFORTLESSLY", "POWER", "BODY", "LANGUAGE",
        "SPOT", "NOTICE", "FELT", "KEY", "TRICK", "SIGNAL", "CUE",
    ]

    is_dark = "dark" in profile_name.lower() or "psychologia" in profile_name.lower()
    # Dla dark używamy CinematicDark (dolna 1/3 ekranu, an2), dla brainrot stary styl
    active_style      = "CinematicDark"     if is_dark else "PopWordBrainrot"
    active_style_gold = "CinematicDarkGold" if is_dark else "PopWordBrainrot"

    # Zapisz słowa do .ass — dark: co 2 słowa razem dla lepszego rytmu, brainrot: 1 słowo
    with open(output_subs_ass, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for segment in result.get('segments', []):
            if 'words' in segment:
                words_list = segment['words']
                step = 2 if is_dark else 1  # 2 słowa naraz dla dark = lepszy rytm
                for i in range(0, len(words_list), step):
                    chunk = words_list[i:i+step]
                    if not chunk:
                        continue
                    start    = format_ass_time(chunk[0]['start'])
                    end      = format_ass_time(chunk[-1]['end'])
                    combined = " ".join(w['word'].strip().upper() for w in chunk)
                    word_text = combined.replace('"', '').replace("'", "")
                    if not word_text.strip():
                        continue

                    # Określanie koloru dla dark
                    if is_dark:
                        if any(kw in word_text for kw in dark_keywords):
                            # Czerwony dla triggerów psychologicznych
                            style = active_style
                            color_tag = red_color
                        elif any(kw in word_text for kw in gold_keywords):
                            # Złoty dla pozytywnych emocji / słów kluczowych
                            style = active_style_gold
                            color_tag = ""
                        elif any(p in word_text for p in [".", "!", "?", "..."]):
                            # Złoty na końcu zdania
                            style = active_style_gold
                            color_tag = ""
                        else:
                            style = active_style
                            color_tag = ""
                    else:
                        style = active_style
                        color_tag = rotational_colors[i % len(rotational_colors)] if i % 3 == 0 else ""

                    anim_scale = "116" if is_dark else "122"
                    line = (f"Dialogue: 0,{start},{end},{style},,0,0,0,,"
                            f"{{\\an5\\t(0,70,\\fscx{anim_scale}\\fscy{anim_scale})}}"
                            f"{color_tag}{word_text}\n") if is_dark else (
                            f"Dialogue: 0,{start},{end},{style},,0,0,0,,"
                            f"{{\\an5\\t(0,60,\\fscx{anim_scale}\\fscy{anim_scale})}}"
                            f"{color_tag}{word_text}\n")
                    f.write(line)
            else:
                start = format_ass_time(segment['start'])
                end   = format_ass_time(segment['end'])
                text  = segment['text'].strip().upper().replace('"', '')
                anim_scale = "110" if is_dark else "115"
                pos_tag = "{\\an5"
                line = f"Dialogue: 0,{start},{end},{active_style},,0,0,0,,{pos_tag}\\t(0,80,\\fscx{anim_scale}\\fscy{anim_scale})}}{text}\n"
                f.write(line)

    print("✅ Skonfigurowano brutalnie skuteczne suby i animacje.")

def create_video(audio_path: str, subs_path: str, output_path: str, profile_name: str = "brainrot",
                 background_vibe: str | None = None, music_folder: str | None = None):
    """Łączy wideo w tle z audio i wstawia natywnie napisy po przez ffmpeg.
    background_vibe: konkretne zapytanie dla yt-dlp (np. 'gta 5 car jumping no copyright') - dyktowane przez Synapsę.
    music_folder: który podfolder music użyć (np. 'dark_mindset' lub 'brainrot') - dyktowane przez Synapsę.
    """
    eff_music_folder = music_folder or profile_name
    print(f"🎬 Montaż klipu [{profile_name}] | Tło: {background_vibe or 'auto'} | Muzyka: {eff_music_folder}")
    
    try:
        from background_fetcher import fetch_background_video
        # Jeśli Synapsa określiła konkretny vibe, pobieramy właśnie to
        if background_vibe:
            fetch_background_video(profile_name, search_query_override=background_vibe)
        else:
            fetch_background_video(profile_name)
    except Exception as e:
        print(f"⚠️ Nie udało się pobrać tła: {e}")
        
    bg_folder = os.path.join(BACKGROUNDS_DIR, profile_name) if os.path.exists(os.path.join(BACKGROUNDS_DIR, profile_name)) else BACKGROUNDS_DIR
    background_files = glob.glob(os.path.join(bg_folder, "*.mp4"))
    
    if not background_files:
        print("❌ Brak filmów tłówek w folderze 'videos'. Wgraj chociaż jeden darmowy film.")
        return
    # --- LOGIKA PRZECIWKO POWTÓRZENIOM TŁA ---
    last_bg_tracker = os.path.join(BACKGROUNDS_DIR, profile_name, "last_used_bg.txt")
    last_bg = ""
    if os.path.exists(last_bg_tracker):
        try:
            with open(last_bg_tracker, "r", encoding="utf-8") as f:
                last_bg = f.read().strip()
        except:
            pass

    # Filtrujemy ostatnio użyte tło (jeśli jest więcej niż 1 plik do wyboru)
    available_bgs = [bf for bf in background_files if bf != last_bg]
    if not available_bgs: 
        available_bgs = background_files # Zabezpieczenie dla 1 wideo

    bg_video_path = random.choice(available_bgs)
    
    # Zapisujemy wybrane tło na następny raz
    try:
        with open(last_bg_tracker, "w", encoding="utf-8") as f:
            f.write(bg_video_path)
    except:
        pass
    # ----------------------------------------
    
    audio_clip = None
    video_clip = None
    try:
        audio_clip = AudioFileClip(audio_path)
        video_clip = VideoFileClip(bg_video_path)

        # Przytnij/zapętl video, żeby dopasować do długości audio
        if video_clip.duration >= audio_clip.duration:
            # Tło dłuższe — losowy start, przytnij do długości audio
            start_cut = random.uniform(0, max(0, video_clip.duration - audio_clip.duration - 1))
            video_clip = video_clip.subclip(start_cut, start_cut + audio_clip.duration)
        else:
            # Tło KRÓTSZE niż audio — zapętlamy tło (nie tniemy audio!)
            from moviepy.video.fx.all import loop as loop_fx
            loops_needed = int(audio_clip.duration / video_clip.duration) + 2
            video_clip = loop_fx(video_clip, n=loops_needed).subclip(0, audio_clip.duration)

        # formatowanie do 9:16 Shorts
        w, h = video_clip.size
        crop_width = h * 9 / 16
        if crop_width > w:
            crop_width = w

        video_clip = crop(video_clip, width=crop_width, x_center=w / 2)
        video_clip = resize(video_clip, newsize=(1080, 1920))

        # Implementacja filtra Zoom-in w celu likwidacji statycznego tła
        def zoom_effect(t):
            return 1.0 + 0.08 * (t / max(video_clip.duration, 1.0))

        zoomed_clip = video_clip.resize(zoom_effect)
        video_clip = CompositeVideoClip([zoomed_clip.set_position('center')], size=(1080, 1920))
        video_clip = video_clip.set_audio(audio_clip)

        # Zapisujemy wykadrowany film bez napisów
        temp_no_subs = output_path.replace(".mp4", "_nosubs.mp4")

        # Dodajemy delikatną muzykę w tle jeśli istnieje, zależną od nastroju subkonta
        from moviepy.editor import CompositeAudioClip
        eff_music_folder = music_folder if music_folder else profile_name
        music_folder_path = os.path.join(MUSIC_DIR, eff_music_folder)
        os.makedirs(music_folder_path, exist_ok=True)

        music_files = glob.glob(os.path.join(music_folder_path, "*.mp3"))
        if not music_files:
            print(f"🎵 Brak lokalnej muzyki w {music_folder_path} — Automatyczne pobieranie (YouTube)...")
            search_kw = "phonk phonk no copyright" if "brainrot" in profile_name else "dark synthwave phonk slowed reverb no copyright"
            query = f"ytsearch1:{search_kw}"
            dl_music_cmd = [
                "yt-dlp", "-x", "--audio-format", "mp3",
                "--force-overwrites",
                "--cookies", "cookies.txt",  # PO Token via browser cookies
                "-o", os.path.join(music_folder_path, "bg_music_%(id)s.%(ext)s"),
                query
            ]
            subprocess.run(dl_music_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            music_files = glob.glob(os.path.join(music_folder_path, "*.mp3"))

        if music_files:
            bg_music = AudioFileClip(random.choice(music_files))
            music_vol = 0.18 if ("dark" in profile_name.lower() or "psychologia" in profile_name.lower()) else 0.08

            # BUGFIX: jesli muzyka krotsza niz video — zapetlamy zamiast crashu
            if bg_music.duration < video_clip.duration + 1.0:
                from moviepy.audio.fx.all import audio_loop as _audio_loop
                loops_needed = int(video_clip.duration / bg_music.duration) + 2
                bg_music = _audio_loop(bg_music, nloops=loops_needed)

            safe_start = min(30.0, max(0.0, bg_music.duration - video_clip.duration - 5.0))
            max_start = max(safe_start, bg_music.duration - video_clip.duration - 5.0)
            random_start = random.uniform(safe_start, max_start)

            if random_start < 0 or random_start + video_clip.duration > bg_music.duration:
                random_start = 0

            # Final guard: clamp end to music duration
            end_point = min(random_start + video_clip.duration, bg_music.duration)
            bg_music = bg_music.subclip(random_start, end_point).volumex(music_vol)
            final_audio = CompositeAudioClip([audio_clip, bg_music])
            video_clip = video_clip.set_audio(final_audio)

        video_clip.write_videofile(temp_no_subs, fps=30, codec="libx264", audio_codec="aac", audio_bitrate="192k", temp_audiofile="temp_audio_44k.m4a", remove_temp=True, threads=6, logger=None)
    finally:
        # MEMORY SAFETY: Zawsze zamykaj klipy — nawet przy wyjątku (Windows blokuje pliki!)
        if video_clip:
            try: video_clip.close()
            except Exception: pass
        if audio_clip:
            try: audio_clip.close()
            except Exception: pass

    # NAPISY + FILTRY KINOWE — vignette, zimny kolor, S-curve kontrastu
    print("💬 Wypalanie napisów + filtry kinowe (ffmpeg)...")
    try:
        subs_path_esc = subs_path.replace('\\', '/')
        if ':' in subs_path_esc:
            subs_path_esc = subs_path_esc.replace(':', r'\:')

        # Filtry: napisy + vignette (ciemne krawędzie) + zimny odcień + S-curve kontrastu
        vf_filter = (
            f"subtitles='{subs_path_esc}',"
            "colorbalance=bs=-0.12:bh=-0.08:gs=-0.06:gh=-0.04,"
            "vignette=PI/5,"
            "curves=all='0/0 0.45/0.38 1/0.95'"
        )
        cmd = [
            'ffmpeg', '-y', '-nostdin', '-i', temp_no_subs,
            '-vf', vf_filter,
            '-af', 'loudnorm=I=-14:LRA=11:TP=-1.5,aresample=44100',
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
            '-profile:v', 'high', '-level', '4.1',
            '-c:a', 'aac', '-b:a', '192k',
            '-ar', '44100',        # KRYTYCZNE: standard YT (nie 96kHz!)
            '-r', '30',            # 30fps standard Shorts
            '-pix_fmt', 'yuv420p', # Kompatybilność YT
            '-movflags', '+faststart',
            output_path
        ]
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"🎉 Sukces! Shortsy gotowe: {output_path}")
    except Exception as e:
        print(f"⚠️ Błąd filtrów FFmpeg ({e}). Kopiuję bez filtrów...")
        shutil.copy(temp_no_subs, output_path)
    finally:
        if os.path.exists(temp_no_subs):
            os.remove(temp_no_subs)

def generate_cashcow_from_text(final_text: str, category_name: str,
                               background_vibe: str | None = None, music_folder: str | None = None) -> str:
    """Odpowiada natywnie tylko za proces renderowania z otrzymanego już wysoce zoptymalizowanego tekstu z zewnętrznego systemu"""
    print(f"\n--- 🏭 Silnik Renderujący Cash Cow odpala generację dla: {category_name.upper()} ---")
    if background_vibe:
        print(f"   >> Tło wideo (z Synapsy): {background_vibe}")
    if music_folder:
        print(f"   >> Muzyka (z Synapsy): {music_folder}")
    
    sciezka_audio = os.path.join(OUTPUT_DIR, f"{category_name}_audio.mp3")
    sciezka_ass = os.path.join(OUTPUT_DIR, f"{category_name}_subs.ass")
    sciezka_finalna = os.path.join(OUTPUT_DIR, f"HINT_{category_name}_gotowy_short.mp4")

    # ── SCRIPT CLEANUP: Usuń tagi/hashtagi które wyciekły do tekstu TTS ──────────
    import re as _re_clean
    # Strip #hashtags anywhere in text
    final_text = _re_clean.sub(r'#\w+', '', final_text).strip()
    # Strip [TITLE] / [SCRIPT] / [TAGS] / [--END...] markers
    final_text = _re_clean.sub(r'\[[\w\s\-]+\]', '', final_text).strip()
    # Strip "Tagged with ..." patterns
    final_text = _re_clean.sub(r'(?i)tagged\s+with\s+.*$', '', final_text).strip()
    # Strip trailing comma-separated tag lists (darkpsychologist, manipulation tactics, ...)
    _TAG_WORDS = r'(?:dark\w*|psychology\w*|manipulation\w*|mindset\w*|sigma\w*|viral\w*|shorts?\w*|power\w*|secrets?\w*|stoic\w*|brain\w*|behavior\w*|social\w*|cognitive\w*|hidden\w*|tricks?\w*|persuasion\w*|respect\w*|body\w*|language\w*|trending\w*|fyp\w*|humanbehavior\w*|subconscious\w*|insights?\w*|tactics?\w*|influence\w*|revealed\w*)'
    final_text = _re_clean.sub(rf'(?:,?\s+{_TAG_WORDS})+\s*$', '', final_text, flags=_re_clean.IGNORECASE).strip()
    # Strip standalone tag-like lines at the end (no comma, space-separated)
    final_text = _re_clean.sub(rf'\s+{_TAG_WORDS}(?:\s+{_TAG_WORDS}){{2,}}\s*$', '', final_text, flags=_re_clean.IGNORECASE).strip()
    # Strip social media CTA patterns that contaminate audio
    final_text = _re_clean.sub(r'(?i)\b(?:follow\s+(?:for|me|us)|subscribe|like\s+and\s+share|hit\s+the\s+bell)\b.*$', '', final_text).strip()
    # Strip URLs
    final_text = _re_clean.sub(r'https?://\S+', '', final_text).strip()
    # Strip excessive emoji (keep max 1)
    _emojis_found = _re_clean.findall(r'[\U0001f600-\U0001f9ff\U0001fa00-\U0001fa6f\U0001fa70-\U0001faff\u2600-\u26ff\u2700-\u27bf]', final_text)
    if len(_emojis_found) > 1:
        for _em in _emojis_found[1:]:
            final_text = final_text.replace(_em, '', 1)
    final_text = final_text.strip()
    # Ensure it ends with proper punctuation
    if final_text and final_text[-1] not in '.!?':
        final_text += '.'

    # Ustalanie głosu w zależności od nazwy profilu
    wybrany_glos = VOICE_EN if ("dark" in category_name.lower() or "psychologia" in category_name.lower()) else VOICE_PL

    generate_speech_and_subs(final_text, sciezka_audio, sciezka_ass, voice=wybrany_glos, profile_name=category_name)
    
    create_video(sciezka_audio, sciezka_ass, sciezka_finalna,
                 profile_name=category_name,
                 background_vibe=background_vibe,
                 music_folder=music_folder)
    return sciezka_finalna

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--konto", type=str, default="kanal_1", choices=CHANNELS_NICHES.keys(), 
                        help="Wybierz profil kanału")
    args = parser.parse_args()

    niche_data = CHANNELS_NICHES[args.konto]
    sciezka_audio = os.path.join(OUTPUT_DIR, f"{args.konto}_audio.mp3")
    sciezka_ass = os.path.join(OUTPUT_DIR, f"{args.konto}_subs.ass")
    sciezka_finalna = os.path.join(OUTPUT_DIR, f"HINT_{args.konto}_gotowy_short.mp4")

    skrypt_tekstowy = get_script_from_ai(niche_data['prompt'])
    wybrany_glos = VOICE_EN if ("dark" in args.konto.lower() or "psychologia" in args.konto.lower()) else VOICE_PL
    generate_speech_and_subs(skrypt_tekstowy, sciezka_audio, sciezka_ass, voice=wybrany_glos, profile_name=args.konto)
    create_video(sciezka_audio, sciezka_ass, sciezka_finalna, profile_name=args.konto)

if __name__ == "__main__":
    main()
