import os
import subprocess
import json
import re

VIDEO_PATH = "temp_videos/HINT_dark_mindset_gotowy_short.mp4"
SUBS_PATH = "temp_videos/dark_mindset_subs.ass"

def analyze():
    print("🎬 Analiza Virala - Dark Psychology 🎬\n" + "="*40)
    
    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Brak pliku wideo: {VIDEO_PATH}")
        return

    # 1. Sprawdzanie parametrów wideo (ffprobe)
    print("\\n[1] PARAMETRY WIDEO (ffprobe)")
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", VIDEO_PATH
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        
        # Wideo strumien
        v_stream = next(s for s in data['streams'] if s['codec_type'] == 'video')
        width = int(v_stream.get('width', 0))
        height = int(v_stream.get('height', 0))
        duration = float(data['format'].get('duration', 0))
        
        print(f"  - Rozmiar: {width}x{height} (Wymagane: Pionowe 9:16 np. 1080x1920)")
        if width == 1080 and height == 1920:
             print("    ✅ IDEALNY ROZMIAR ZOPTYMALIZOWANY POD SHORTS")
        else:
             print("    ❌ ZŁY ROZMIAR")
             
        print(f"  - Czas trwania: {duration:.2f}s (Wymagane: 20-45s dla Storytelling Loop)")
        if 20.0 <= duration <= 45.0:
            print("    ✅ IDEALNY CZAS TRWANIA DLA DARK PSYCHOLOGY NARRATIVE")
        else:
            print("    ❌ ZŁY CZAS! Opowieść będzie za płytka (jeśli <20s) lub rozmyta (jeśli >45s).")
            
        # Audio strumien
        a_stream = next((s for s in data['streams'] if s['codec_type'] == 'audio'), None)
        if a_stream:
             print("  - Audio: Znaleziono strumień dźwiękowy")
             print("    ✅ AUDIO JEST OBECNE")
        else:
             print("  - Audio: BRAK!")
             print("    ❌ WIDEO JEST NIEME")
             
    except Exception as e:
        print(f"Błąd czytania ffprobe: {e}")

    # 2. Sprawdzanie napisów (ASS)
    print("\\n[2] DYNAMIKA I NAPISY (ASS)")
    if not os.path.exists(SUBS_PATH):
         print(f"❌ Brak pliku napisów: {SUBS_PATH}")
         return
         
    with open(SUBS_PATH, 'r', encoding='utf-8') as f:
         subs_content = f.read()
         
    events = [line for line in subs_content.splitlines() if line.startswith('Dialogue:')]
    print(f"  - Liczba ekranów z napisami: {len(events)}")
    
    # Check words per screen (pace)
    words_count = 0
    highlighted_count = 0
    blood_red_count = 0
    yellow_count = 0
    anim_pop_count = 0
    
    for ev in events:
        # Dialogue: 0,0:00:00.00,0:00:00.32,PopWordDark,,0,0,0,,{\\an5\\t(0,60,\\fscx112\\fscy112)}SILENCE
        # Extract text part
        parts = ev.split(',,')
        if len(parts) >= 2:
             text_part = parts[-1]
             words_count += len(re.sub(r'\\{.*?\\}', '', text_part).strip().split())
             if '{\\c&H0000FF&}' in text_part:
                 blood_red_count += 1
                 highlighted_count += 1
             if '{\\c&H00FFFF&}' in text_part:
                 yellow_count += 1
                 highlighted_count += 1
             if '\\fscx112' in text_part or '\\fscx122' in text_part or '\\fscx105' in text_part:
                 anim_pop_count += 1

    print(f"  - Łącznie wyrzuconych słów przez Whisper: {words_count}")
    if len(events) > 0:
         wps = words_count / len(events)
         print(f"  - Średnia liczba słów na pop-up (ekran): {wps:.2f} (Wymagane: ok 1.0 dla hyper-pacing mode)")
         if wps <= 2.0:
              print("    ✅ IDEALNE TEMPO DLA TIKTOK/SHORTS (1-2 słowa na ekran)")
         else:
              print("    ❌ ZA DUŻO SŁÓW NA EKRAN! Widz nie zdąży przeczytać.")
              
    print(f"  - Słowa z emocjonalnym kolorem red (\\c&H0000FF&): {blood_red_count}")
    print(f"  - Słowa z kolorem żółtym pętli zdania (\\c&H00FFFF&): {yellow_count}")
    if anim_pop_count == len(events):
         print("  - Efekt Pop-Zoom zaimplementowany na każdym słowie: ✅ TAK (Hormozi Style)")

    print("\\n[3] ANALIZA HOOKA (Pierwsze 3 sekundy - Retention Predictor)")
    hook_words = 0
    hook_text = []
    
    for ev in events:
        # Dialogue: 0,0:00:00.00,0:00:00.32,PopWordDark,,0,0,0,,{\\an5\\t(0,60,\\fscx112\\fscy112)}SILENCE
        parts = ev.split(',', 9)
        if len(parts) >= 10:
            start_time_str = parts[1]
            text_part = parts[9]
            try:
                h, m, s = start_time_str.split(':')
                start_sec = float(h)*3600 + float(m)*60 + float(s)
                if start_sec <= 3.0:
                    clean_word = re.sub(r'\\{.*?\\}', '', text_part).strip()
                    if clean_word:
                        hook_words += len(clean_word.split())
                        hook_text.append(clean_word)
            except Exception:
                pass

    hook_sentence = " ".join(hook_text)
    print(f"  - Treść Hooka (0-3s): '{hook_sentence}'")
    print(f"  - Liczba słów w pierwszych 3s: {hook_words}")
    
    if hook_words > 12:
         print("    ❌ HOOK PRZEŁADOWANY! Widz nie zdąży przeczytać (Ryzyko 75% Swipe Away).")
    elif hook_words < 4:
         print("    ❌ HOOK ZA WOLNY/ZBYT KRÓTKI! Brak dynamiki (Potężne ryzyko 75% Swipe Away).")
    else:
         print("    ✅ HOOK MA IDEALNĄ GĘSTOŚĆ (4-12 słów). Silne zatrzymanie uwagi.")

    # 4. Analiza decybeli za pomocą narzędzia Volumedetect
    print("\\n[4] ANALIZA GŁOŚNOŚCI (ffmpeg volumedetect)")
    vd_cmd = [
        "ffmpeg", "-i", VIDEO_PATH, "-af", "volumedetect", "-vn", "-sn", "-dn", "-f", "null", "NUL"
    ]
    # W Windows NUL zamiast /dev/null
    vd_result = subprocess.run(vd_cmd, capture_output=True, text=True)
    
    # Parse max_volume and mean_volume from stderr
    mean_vol_match = re.search(r'mean_volume:\s*([-0-9.]+)\s*dB', vd_result.stderr)
    max_vol_match = re.search(r'max_volume:\s*([-0-9.]+)\s*dB', vd_result.stderr)
    
    if mean_vol_match and max_vol_match:
         mean_vol = float(mean_vol_match.group(1))
         max_vol = float(max_vol_match.group(1))
         print(f"  - Średnia głośność (RMS): {mean_vol} dB (Zalecane: ok -15 do -13 dB | ~ -14 LUFS)")
         print(f"  - Peak level (Max): {max_vol} dB (Zalecane: ok 0 do -2 dB)")
         
         if -18 <= mean_vol <= -12:
              print("    ✅ GŁOŚNOŚĆ KLAROWNA, IDEALNA POD ALGORITHM (-14 LUFS)")
         else:
              print(f"    ⚠️ GŁOŚNOŚĆ DO POPRAWY (Wymaga lepszej kompresji z cashcow_generator)")
    else:
         print("  - Nie udało się odczytać głośności.")

if __name__ == '__main__':
    analyze()