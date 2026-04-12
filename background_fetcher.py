import os
import sys
import random
import yt_dlp

# Wymuszenie UTF-8 na stdout/stderr (Windows CP1250 nie obsługuje emoji)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

BACKGROUNDS_DIR = "videos"
MIN_FILE_SIZE_BYTES = 4 * 1024 * 1024  # 4 MB — tło poniżej tej wartości = ultra low quality, do usunięcia

def _cleanup_tiny_backgrounds(target_dir: str, min_size: int = MIN_FILE_SIZE_BYTES) -> int:
    """Usuwa pliki MP4 mniejsze niż min_size bajtów (ultra low quality). Zwraca liczbę usuniętych."""
    removed = 0
    for fname in os.listdir(target_dir):
        if not fname.endswith('.mp4'):
            continue
        fpath = os.path.join(target_dir, fname)
        try:
            size = os.path.getsize(fpath)
            if size < min_size:
                os.remove(fpath)
                print(f"🗑️  [CLEANUP] Usunięto zbyt małe tło ({size/1024/1024:.1f} MB): {fname}")
                removed += 1
        except Exception as e:
            print(f"⚠️  [CLEANUP] Nie można sprawdzić {fname}: {e}")
    if removed:
        print(f"🧹 [CLEANUP] Usunięto {removed} plików <4MB z katalogu '{target_dir}'.")
    return removed


def fetch_background_video(profile_name="brainrot", target_dir=BACKGROUNDS_DIR, min_files=10,
                           search_query_override=None, force_refresh=False):
    """
    Pobiera bezpieczne pod kątem praw autorskich nagrania HD.
    - Automatycznie usuwa pliki <4MB (ultra low quality) przed sprawdzeniem puli.
    - min_files=10: pipeline potrzebuje co najmniej 10 HD teł (poprzednio 5 — było niewystarczające).
    - search_query_override: jeśli podane (przez Synapsę Master Director), pobiera właśnie to
      zamiast losować z wbudowanej puli.
    - force_refresh=True: ignoruje istniejące pliki i pobiera nowe HD materiały.
    """
    target_dir = os.path.join(BACKGROUNDS_DIR, profile_name)
    os.makedirs(target_dir, exist_ok=True)

    # ── KROK 1: Wyczyść śmieci (<4MB = ultra low quality) ────────────────────
    _cleanup_tiny_backgrounds(target_dir)

    existing_files = [f for f in os.listdir(target_dir) if f.endswith('.mp4')]

    if not force_refresh and len(existing_files) >= min_files and not search_query_override:
        print(f"✅ Znaleziono wystarczającą bazę HD teł dla {profile_name} ({len(existing_files)} plików ≥4MB). Pomijam pobieranie.")
        return True

    print(f"📥 Pobieranie darmowego tła dla nastroju konta [{profile_name}]...")
    
    if search_query_override:
        # Dyrektywa z Synapsy - pobieramy dokladnie to co AI chce
        query = search_query_override if search_query_override.startswith("ytsearch") else f"ytsearch1:{search_query_override}"
        print(f"🧠 [Synapsa Override] Zapytanie wideo: '{query}'")
    else:
        # Pula nowoczesnych teł 2025/2026 — dark psychology cinematic aesthetic
        # Sigma edity z 2022 === przestarzałe. Teraz: abstrakcja, mgła, świetlna atmosfera.
        mood_queries = {
            "dark_mindset": [
                "ytsearch1:dark particle abstract background vertical 4k loop no copyright",
                "ytsearch1:dark smoke cinematic atmosphere slow motion vertical 4k free",
                "ytsearch1:neural brain network visualization dark background 4k vertical",
                "ytsearch1:rainy night city cinematic dark aesthetic vertical 4k free use",
                "ytsearch1:dark luxury cinematic background vertical 4k no copyright",
                "ytsearch1:dark fog forest mystery cinematic vertical 4k no copyright",
                "ytsearch1:abstract dark gradient flow loop vertical 4k free background",
                "ytsearch1:silhouette dark room dramatic light cinematic vertical shorts",
                "ytsearch1:neon dark aesthetic vertical background 4k no copyright loop",
                "ytsearch1:dark ocean waves cinematic mood vertical 4k free use",
                "ytsearch1:dark psychological horror aesthetic atmosphere vertical 4k",
                "ytsearch1:cinematic dark background bokeh light vertical shorts free",
            ],
            "brainrot": [
                "ytsearch1:subway surfers gameplay no copyright",
                "ytsearch1:minecraft parkour gameplay no copyright satisfying",
                "ytsearch1:roblox obby funny fails no copyright gameplay",
                "ytsearch1:family guy brain rot compilation no copyright",
                "ytsearch1:satisfying slime asmr no copyright background"
            ]
        }
        search_queries = mood_queries.get(profile_name, mood_queries["brainrot"])

        # Jeśli mamy za mało plików, pobierz WSZYSTKIE zapytania z puli (batch mode)
        missing = max(0, min_files - len(existing_files))
        if missing >= 3 or force_refresh:
            print(f"📦 [BATCH MODE] Brakuje {missing} HD teł — uruchamiam pobieranie sekwencyjne ({len(search_queries)} zapytań)...")
            success_count = 0
            for _q in search_queries:
                print(f"🔍 [{success_count+1}/{len(search_queries)}] Wyszukuję: '{_q}'")
                _opts = {
                    'format': 'bestvideo[ext=mp4][height>=720]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height>=720]/best',
                    'outtmpl': os.path.join(target_dir, 'bg_%(id)s_no_copyright.%(ext)s'),
                    'noplaylist': True,
                    'quiet': True,
                    'merge_output_format': 'mp4',
                    'socket_timeout': 60,
                    'retries': 3,
                    'fragment_retries': 3,
                    'cookiefile': 'cookies.txt',  # PO Token via browser cookies
                }
                try:
                    with yt_dlp.YoutubeDL(_opts) as _ydl:
                        _ydl.download([_q])
                    success_count += 1
                except Exception as _e:
                    print(f"   ⚠️  Błąd pobierania '{_q}': {_e}")
            _cleanup_tiny_backgrounds(target_dir)  # Wyczyść nowe śmieci po batch
            final_count = len([f for f in os.listdir(target_dir) if f.endswith('.mp4')])
            print(f"🎉 [BATCH MODE] Zakończono. HD teł w katalogu: {final_count}")
            return success_count > 0

        query = random.choice(search_queries)
        print(f"🔍 Wyszukuję materiału dla frazy: '{query}'")
    ydl_opts = {
        # Priorytet: najlepsza jakość video (min 720p, preferowane 1080p/4K) + audio
        'format': 'bestvideo[ext=mp4][height>=720]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height>=720]/best',
        'outtmpl': os.path.join(target_dir, 'bg_%(id)s_no_copyright.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'merge_output_format': 'mp4',
        'socket_timeout': 60,       # timeout 60s na połączenie
        'retries': 3,               # 3 próby pobrania
        'fragment_retries': 3,      # 3 próby fragmentów
        'cookiefile': 'cookies.txt',  # PO Token via browser cookies
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        print("🎉 Pobieranie darmowego tła do Shortsów zakończone sukcesem!")
        return True
    except Exception as e:
        print(f"❌ KRYTYCZNY BŁĄD podczas pobierania bezpiecznego tła: {e}")
        return False

def force_refetch_hd_backgrounds(profile_name: str = "dark_mindset"):
    """Wywołaj ręcznie aby wyczyścić niskiej jakości tła i pobrać 10+ HD.
    Użycie: python background_fetcher.py
    """
    print(f"\n🚀 [FORCE REFETCH] Uruchamiam pełny reset HD teł dla profilu: {profile_name}")
    _cleanup_tiny_backgrounds(os.path.join(BACKGROUNDS_DIR, profile_name))
    fetch_background_video(profile_name, force_refresh=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        force_refetch_hd_backgrounds("dark_mindset")
    else:
        fetch_background_video("dark_mindset")
        fetch_background_video("brainrot")
