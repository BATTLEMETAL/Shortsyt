import os
import json
import glob
from collections import defaultdict
from datetime import datetime
from data_collector import get_authenticated_service, get_channel_videos
# FIX AUDYT: Usunięto przestarzały import google.generativeai (gemini-pro wycofany)
# Optymalizacja promptów teraz przez lokalną Synapsę (offline, bez API key)
from synapsa_bridge import generate_viral_script_with_synapsa

PROMPTS_FILE = "accounts/niche_prompts.json"
PEAK_TIMES_FILE = "accounts/peak_times.json"

DEFAULT_PROMPTS = {
    "kanal_1": {"nazwa": "brainrot", "prompt": "Napisz mi ultra krótki, 30-sekundowy skrypt o absurdalnej i wymyślonej sytuacji w szkole, używając skrajnego internetowego slangu (np. skibidi, sigma, rizz, gyatt, minus aura, ohio). Tekst musi szokować od pierwszej sekundy, bo to dla dzieci. Ostatnie zdanie musi w połowie urwać się tak, by idealnie pasowało do pierwszego zdania (stworzenie pętli/Loopa). Pisz ciągiem."},
    "kanal_2": {"nazwa": "psychologia", "prompt": "Napisz mi 3 mroczne triki psychologiczne. Hook musi być agresywny (np. 'Uważaj! Ktoś w tym momencie może cię manipulować...'). Czas 40 sekund."},
    "kanal_3": {"nazwa": "finanse", "prompt": "Napisz mi 1 brutalną prawdę o finansach. Styl agresywny, w stylu Andrew Tate'a. Zaczynamy od błędu, który widz właśnie teraz popełnia. Czas 40 sekund."},
    "kanal_4": {"nazwa": "reddit_stories", "prompt": "Wciągający Reddit z perspektywy pierwszej osoby. Temat: sekrety sąsiadów. Plot twist na końcu, suspens w pierwszych 5 sekundach."},
    "kanal_5": {"nazwa": "quizy", "prompt": "Trudny quiz. 3 pytania, bardzo szybko. Odliczanie na odpowiedź zmniejszone, żeby podbić frustrację i komentarze."}
}

def analyze_profile_peak_time(vid_response):
    """Oblicza godzinę (UTC) o najwyższym współczynniku odsłon"""
    hour_stats = defaultdict(lambda: {"views": 0, "count": 0})
    
    for item in vid_response.get("items", []):
        published_at = item["snippet"].get("publishedAt")
        views = int(item["statistics"].get("viewCount", 0))
        if published_at:
            # Format "2026-02-21T18:00:00Z"
            dt = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
            hour = dt.strftime("%H:00")
            hour_stats[hour]["views"] += views
            hour_stats[hour]["count"] += 1
            
    best_hour = "18:00" # domyślna godzina (wieczór)
    best_avg_views = -1
    for h, data in hour_stats.items():
        avg = data["views"] / data["count"]
        if avg > best_avg_views:
            best_avg_views = avg
            best_hour = h
            
    return best_hour, best_avg_views

def analyze_and_optimize():
    print("🧠 Inicjowanie Inteligentnej Pętli Optymalizacyjnej (Wielokonta + Peak Time)...")
    os.makedirs("accounts", exist_ok=True)
    
    # 1. Załadowanie bazy
    prompts_db = DEFAULT_PROMPTS
    if os.path.exists(PROMPTS_FILE):
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            prompts_db = json.load(f)
            
    peak_times_db = {}
    if os.path.exists(PEAK_TIMES_FILE):
        with open(PEAK_TIMES_FILE, "r", encoding="utf-8") as f:
            peak_times_db = json.load(f)

    # FIX AUDYT: Usunięto zależność od gemini API key - Synapsa działa offline
    # Znajdprompts_db wszystkie autoryzowane konta (kanal_1_token.pickle, kanal_2_token.pickle)
    token_files = glob.glob("accounts/*_token.pickle")
    if not token_files:
        print("Brak podłączonych kanałów w folderze accounts! Uruchom authorize_channel.py.")
        profiles_to_check = ["kanal_1"]
    else:
        profiles_to_check = [os.path.basename(t).replace("_token.pickle", "") for t in token_files]

    for profile in profiles_to_check:
        print(f"\n=============================================")
        print(f"📊 ANALIZA I OPTYMALIZACJA PROFILU: {profile.upper()}")
        print(f"=============================================")
        
        service = get_authenticated_service(profile)
        if not service:
            print(f"⚠️ {profile} odrzucił autoryzację. Pomiń.")
            continue
            
        print("-> Skanowanie filmów i uczenie się skuteczności z YouTube Analytics...")
        video_ids = get_channel_videos(service, channel_id=None)
        recent_ids = video_ids[:40]
        
        if not recent_ids:
            print(f"Brak filmów na kanale {profile}. Wymagam materiału do uczenia. Ustawiam godzinę publikacji na 18:00 (Prime Time).")
            peak_times_db[profile] = "18:00:00"
            continue
            
        vid_request = service.videos().list(part="statistics,snippet", id=",".join(recent_ids))
        vid_response = vid_request.execute()
        
        # OBLICZENIE PEAK TIME
        best_hour, max_avg = analyze_profile_peak_time(vid_response)
        print(f"⏱️ OBLICZONY PEAK TIME dla {profile}: {best_hour} (Spodziewane wyższe AVD)")
        peak_times_db[profile] = f"{best_hour}:00"
        
        # KOMUNIKACJA LLM (Co działa a co nie?)
        stats_list = []
        for item in vid_response.get("items", []):
            title = item["snippet"]["title"]
            views = int(item["statistics"].get("viewCount", 0))
            likes = int(item["statistics"].get("likeCount", 0))
            stats_list.append(f"- '{title[:40]}...' | Wyś: {views} | Lajki: {likes}")
            
        yt_summary = "\n".join(stats_list)
        
        # Budujemy kontekst dla Synapsy (lokalna analiza tytułów + wyniki)
        context_lines = stats_list[:5]  # top 5 filmów jako kontekst
        niche_channel = profile.replace("_", " ")
        
        optimization_rule = (
            f"[ANALIZA OPTYMALIZACYJNA dla kanału '{profile}']\n"
            f"Na podstawie poniższych wyników (tytuł | wyświetlenia | lajki), "
            f"wygeneruj lepszą zasadę tworzenia skryptów. "
            f"Zwróć uwagę co miało dużo wyświetleń, a co nie.\n"
            f"Aktualna reguła: {json.dumps(prompts_db.get(profile, {}), ensure_ascii=False)[:200]}"
        )
        
        try:
            # Synapsa jako optimizer - zamiast zewnętrznego Gemini
            result = generate_viral_script_with_synapsa(
                viral_context=context_lines,
                niche_topic=niche_channel,
                channel_rule=optimization_rule,
                forbidden_topics=[]
            )
            if result and "script_text" in result:
                # Zaktualizuj prompt o wskazówki Synapsy
                new_tip = result.get("viral_reasoning", "")
                if new_tip and profile in prompts_db:
                    old_prompt = prompts_db[profile].get("prompt", "")
                    prompts_db[profile]["prompt"] = f"{old_prompt} [Optymalizacja AI {datetime.now().strftime('%Y-%m-%d')}: {new_tip[:200]}]"
                    print(f"🤖 [Synapsa] Zoptymalizowano reguły kanału {profile}: {new_tip[:80]}...")
                else:
                    print("⚠️ Synapsa nie zwróciła wskazówek optymalizacyjnych.")
            else:
                print("⚠️ Synapsa nie odpowiedziała na żądanie optymalizacji.")
        except Exception as e:
            print(f"❌ Błąd optymalizacji przez Synapsę: {e}")

    # Zapisz z powrotem do bazy globalnej
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(prompts_db, f, indent=4, ensure_ascii=False)
        
    with open(PEAK_TIMES_FILE, "w", encoding="utf-8") as f:
        json.dump(peak_times_db, f, indent=4, ensure_ascii=False)
        
    print("\n✅ GLOBALNA PĘTLA ZAMKNIĘTA. Wszystkie konta zoptymalizowane pod publikacje i udoskonalone formatowo.")

if __name__ == "__main__":
    analyze_and_optimize()
