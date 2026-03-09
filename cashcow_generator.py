import os
import json
import subprocess
import glob
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

def generate_speech_and_subs(text: str, output_audio: str, output_subs_ass: str, voice: str = VOICE_PL, profile_name: str = "brainrot"):
    """META 2026: Generuje audio (Edge-TTS) a następnie napisy 1-po-1 z animacją i kolorowaniem rotacyjnym (Hormozi)"""
    print(f"🗣️ Generowanie bezwzględnego audio (Edge-TTS: {voice})...")
    import sys
    
    # Rozwiązywanie błędu "Invalid data found" - Edge-TTS psuje argumenty w CLI przy polskich znakach.
    # Bezpieczniej jest zapisać skrypt do pliku .txt i podać poleceniem --file
    temp_txt_path = f"temp_videos/temp_script_{profile_name}.txt"
    with open(temp_txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    edge_tts_bin = os.path.join(os.path.dirname(sys.executable), "edge-tts.exe")
    if not os.path.exists(edge_tts_bin):
        edge_tts_bin = "edge-tts" # fallback do globalnego

    cmd = [
        edge_tts_bin,
        "--voice", voice,
        "--rate", "+15%" if "pl" in voice else "+18%",  # Zmiana na +18% dla j.angielskiego (hiper-szybkie tempo = wyższa retencja yt shorts)
        "--file", temp_txt_path,
        "--write-media", output_audio
    ]
    subprocess.run(cmd, check=True)
    
    # 1B. Silence Trimming (Usuwanie martwej ciszy Edge-TTS pod gładką pętlę - Loop)
    print("✂️ Usuwanie martwej ciszy na końcach audio (FFmpeg silenceremove)...")
    temp_trimmed = output_audio.replace(".mp3", "_trimmed.mp3")
    trim_cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", output_audio,
        "-af", "silenceremove=start_periods=1:stop_periods=-1:detection=peak",
        temp_trimmed
    ]
    try:
        result_trim = subprocess.run(
            trim_cmd, check=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        if result_trim.returncode == 0 and os.path.exists(temp_trimmed) and os.path.getsize(temp_trimmed) > 1024:
            import shutil
            shutil.move(temp_trimmed, output_audio)
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
    print("🧠 Uruchamiam AI Whisper do ekstrakcji i wpalenia słów co 1 sekundę...")
    import whisper
    # Wczytaj Base, bo to szybki lektor polski, jakość będzie 100% po dyktowaniu AI
    # Whisper 'small' = lepsze word-level timestamps niż 'base' (kluczowe dla sync napisów)
    w_model = whisper.load_model("small")
    result = w_model.transcribe(output_audio, word_timestamps=True, fp16=False)

    # 3. Format nagłówka ASS (Styl Hormozi - potężne animacje, dwa odrębne tryby Niche)
    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PopWordBrainrot,Impact,175,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,1,0,0,0,100,100,2,0,1,8,3,5,20,20,820,1
Style: PopWordDark,Arial Black,160,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,1,0,0,0,100,100,1,0,1,9,4,5,20,20,820,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Kolory rotacyjne dla efektu "Hormozi" - przyciągają uwagę co X słów
    rotational_colors = ["{\\c&H00FFFF&}", "{\\c&H00FF00&}", "{\\c&H00A5FF&}"] # Żółty, Zielony, Pomarańczowy (w HEX ASS to BGR)
    blood_red_color = "{\\c&H0000FF&}"  # Czysty czerwony (BGR: 0x0000FF = czerwony)
    highlight_yellow = "{\\c&H00FFFF&}"  # Żółty (BGR)
    # Rozszerzony zestaw dark trigger keywords (emocje + manipulacja + zastraszenie)
    dark_keywords = [
        "MANIPULATION", "SECRET", "DESTROY", "DARK", "POWER", "CONTROL",
        "DANGER", "PSYCHOLOGY", "TRICK", "MIND", "TOXIC", "WEAPON",
        "WARNING", "BRAIN", "FEAR", "VICTIM", "TRAP", "ENEMY", "LIES",
        "WEAK", "DOMINATE", "SILENT", "STARE", "NEVER", "ALWAYS",
        "NOBODY", "EVERYBODY", "TRUTH", "EXPOSED", "HIDDEN", "RULE",
        "OBEY", "SUBMIT", "BROKEN", "CRUSHING", "ABSOLUTE", "BRUTAL"
    ]

    is_dark = "dark" in profile_name.lower() or "psychologia" in profile_name.lower()
    active_style = "PopWordDark" if is_dark else "PopWordBrainrot"

    # Zapisz słowa do profesjonalnego .ass animowanego
    with open(output_subs_ass, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for segment in result.get('segments', []):
            if 'words' in segment:
                # Maksymalnie optymalizone (Meta 2026): po 1 do 2 słów per ekran dla hiper szybkiego tempa
                for i, word_data in enumerate(segment['words']):
                    start = format_ass_time(word_data['start'])
                    end = format_ass_time(word_data['end'])
                    word_text_raw = word_data['word'].strip().upper()
                    word_text = word_text_raw.replace('"', '').replace("'", "")
                    
                    if not word_text:
                        continue
                    
                    # Selektywne podświetlanie (Highlight)
                    color_tag = ""
                    if is_dark:
                        # Krwista czerwień dla psychologicznych triggerów emocjonalnych
                        if any(kw in word_text_raw for kw in dark_keywords):
                            color_tag = blood_red_color
                    else:
                        # Dla brainrot co drugie słowo ma agresywny the kolor
                        color_tag = rotational_colors[i % len(rotational_colors)] if i % 3 == 0 else ""
                        
                    # Zawsze podświetlaj koniec zdania żółtym (Hormozi Rule)
                    if any(p in word_text_raw for p in [".", "!", "?", "..."]):
                        color_tag = highlight_yellow
                    
                    # Animacja pop-up — Dark nieco wolniejsza (kinowa), Brainrot agresywna
                    anim_scale = "122" if not is_dark else "112"
                    # Dla dark  - słowo czerwone jeśli keyword, żółte na końcu zdania
                    # Dla brainrot - rotacyjne kolory
                    if is_dark:
                        final_color = color_tag
                    else:
                        final_color = color_tag
                    line = (f"Dialogue: 0,{start},{end},{active_style},,0,0,0,,"
                            f"{{\\an5\\t(0,60,\\fscx{anim_scale}\\fscy{anim_scale})}}"
                            f"{final_color}{word_text}\n")
                    f.write(line)
                    
            else:
                start = format_ass_time(segment['start'])
                end = format_ass_time(segment['end'])
                text = segment['text'].strip().upper().replace('"', '')
                anim_scale = "115" if not is_dark else "105"
                line = f"Dialogue: 0,{start},{end},{active_style},,0,0,0,,{{\\an5\\t(0,80,\\fscx{anim_scale}\\fscy{anim_scale})}}{text}\n"
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
    
    audio_clip = AudioFileClip(audio_path)
    video_clip = VideoFileClip(bg_video_path)
    
    # Przetnij video, żeby pętlowało się do długości audio lub zrób randomowy start
    if video_clip.duration > audio_clip.duration:
        start_cut = random.uniform(0, max(0, video_clip.duration - audio_clip.duration - 1))
        video_clip = video_clip.subclip(start_cut, start_cut + audio_clip.duration)
    else:
        video_clip = video_clip.subclip(0, video_clip.duration)
        audio_clip = audio_clip.subclip(0, video_clip.duration)
    
    # formatowanie do 9:16 Shorts
    w, h = video_clip.size
    crop_width = h * 9 / 16
    if crop_width > w:
        crop_width = w
    
    video_clip = crop(video_clip, width=crop_width, x_center=w / 2)
    video_clip = resize(video_clip, newsize=(1080, 1920))
    
    # Implementacja filtra Zoom-in w celu likwidacji statycznego tła (skala od 1.0 do 1.08 dla lepszej retencji vira)
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
        search_kw = "phonk phonk no copyright" if "brainrot" in profile_name else "dark ambient creepy no copyright music"
        query = f"ytsearch1:{search_kw}"
        dl_music_cmd = [
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--force-overwrites",
            "-o", os.path.join(music_folder_path, "bg_music_%(id)s.%(ext)s"),
            query
        ]
        subprocess.run(dl_music_cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        music_files = glob.glob(os.path.join(music_folder_path, "*.mp3"))

    if music_files:
        bg_music = AudioFileClip(random.choice(music_files))
        # Mix audio zoptymalizowane do standardów viral: 
        # Głos musi być w 100% wyraźny, muzyka tylko nadaje wajb.
        # Dark Psychology = 10%, Brainrot = 8%
        music_vol = 0.10 if ("dark" in profile_name.lower() or "psychologia" in profile_name.lower()) else 0.08
        bg_music = bg_music.subclip(0, video_clip.duration).volumex(music_vol)
        final_audio = CompositeAudioClip([audio_clip, bg_music])
        video_clip = video_clip.set_audio(final_audio)

    video_clip.write_videofile(temp_no_subs, fps=30, codec="libx264", audio_codec="aac", threads=6, logger=None)
    video_clip.close()
    audio_clip.close()

    # NAPISY - dodajemy natywnie z użyciem ffmpeg (100x szybsze i stabilniejsze na Windows niż ImageMagick)
    print("💬 Wypalanie darmowych napisów VTT (ffmpeg)...")
    try:
        # Prawidłowe formatowanie ścieżki dla ffmpeg vf subtitles na windows
        subs_path_esc = subs_path.replace('\\', '/')
        if ':' in subs_path_esc:
            subs_path_esc = subs_path_esc.replace(':', r'\:')
            
        # Już używamy naszego pliku .ass, który wygenerowaliśmy przy użyciu Whisper z idealnymi animacjami Pop.
        # Filtry loudnorm nadają radiowy głośny profil głosowy (-14 LUFS z limiterem -1.5dB True Peak = IDEAŁ NA YOUTUBE)
        cmd = [
            'ffmpeg', '-y', '-nostdin', '-i', temp_no_subs,
            '-vf', f"subtitles='{subs_path_esc}'",
            '-af', 'loudnorm=I=-14:LRA=11:TP=-1.5',
            '-c:v', 'libx264', '-crf', '18', '-c:a', 'aac', '-b:a', '192k',
            output_path
        ]
        subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"🎉 Sukces! Wygenerowano Shortsa Cash Cow: {output_path}")
    except Exception as e:
        print(f"Błąd podczas wpalania napisów FFmpeg: {e}")
        # Przepisuje bez napisów w razie błędu ffmpeg filter
        import shutil
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
