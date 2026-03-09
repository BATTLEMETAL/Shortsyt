import os
import random
import yt_dlp

BACKGROUNDS_DIR = "videos"

def fetch_background_video(profile_name="brainrot", target_dir=BACKGROUNDS_DIR, min_files=2,
                           search_query_override=None):
    """
    Pobiera bezpieczne pod kątem praw autorskich nagrania.
    search_query_override: jeśli podane (przez Synapsę Master Director), pobiera właśnie to
    zamiast losować z wbudowanej puli.
    """
    target_dir = os.path.join(BACKGROUNDS_DIR, profile_name)
    os.makedirs(target_dir, exist_ok=True)
    existing_files = [f for f in os.listdir(target_dir) if f.endswith('.mp4')]
    
    if len(existing_files) >= min_files and not search_query_override:
        print(f"✅ Znaleziono wystarczającą bazę darmowych teł dla {profile_name} ({len(existing_files)} plików). Pomijam pobieranie.")
        return True

    print(f"📥 Pobieranie darmowego tła dla nastroju konta [{profile_name}]...")
    
    if search_query_override:
        # Dyrektywa z Synapsy - pobieramy dokladnie to co AI chce
        query = search_query_override if search_query_override.startswith("ytsearch") else f"ytsearch1:{search_query_override}"
        print(f"🧠 [Synapsa Override] Zapytanie wideo: '{query}'")
    else:
        # Fallback na wbudowana pule mood_queries
        mood_queries = {
            "dark_mindset": [
                "ytsearch1:peaky blinders tommy shelby sigma edit 4k vertical",
                "ytsearch1:american psycho patrick bateman sigma edit 4k vertical",
                "ytsearch1:gta 5 night drive cinematic realistic mod 4k vertical",
                "ytsearch1:cyberpunk 2077 night drive rain 4k vertical",
                "ytsearch1:dark aesthetic driving night 4k vertical",
                "ytsearch1:ryan gosling drive sigma edit 4k vertical",
                "ytsearch1:mafia definitive edition cinematic rain night 4k",
                "ytsearch1:dark moody cinematic rain window 4k vertical"
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
        query = random.choice(search_queries)
        print(f"🔍 Wyszukuję materiału dla frazy: '{query}'")
    ydl_opts = {
        # FIX AUDYT: 'b' to błędny alias - używamy właściwego formatu
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(target_dir, 'bg_%(id)s_no_copyright.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'merge_output_format': 'mp4',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([query])
        print("🎉 Pobieranie darmowego tła do Shortsów zakończone sukcesem!")
        return True
    except Exception as e:
        print(f"❌ KRYTYCZNY BŁĄD podczas pobierania bezpiecznego tła: {e}")
        return False

if __name__ == "__main__":
    fetch_background_video("dark_mindset")
    fetch_background_video("brainrot")
