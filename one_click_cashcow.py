import argparse
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from data_collector import get_authenticated_service
from cashcow_generator import generate_cashcow_from_text, CHANNELS_NICHES
from synapsa_bridge import generate_viral_script_with_synapsa

def search_viral_shorts(youtube, query: str, count: int = 5):
    """Przeszukuje YouTube by znaleźć najpopularniejsze na świecie Shortsy (ViewCount sort) o danym temacie z ostatnich 7 dni i mierzy wolumen"""
    print(f"\n🌍 SKANOWANIE NAJNOWSZYCH TRENDÓW NA ŚWIECIE (Ostatnie 7 Dni) (Topic: {query})...")
    try:
        # YouTube Data API wymaga często by query do Shorts miało explicit '#shorts'
        search_query = f"{query} #shorts"
        
        # Ograniczenie czasu publikacji do ostatnich 7 dni = łapanie fali trendu
        # API YouTube wymaga formatu zgodnego z RFC 3339 (np. "1970-01-01T00:00:00Z")
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
        total_views = 0
        for item in search_response.get("items", []):
            try:
                # Wymaga part=statistics, dodajmy to przez kolejne żądanie do videoId by sprawdzić siłę trendu
                vid_id = item["id"]["videoId"]
                stat_response = youtube.videos().list(part="statistics", id=vid_id).execute()
                views = int(stat_response['items'][0]['statistics']['viewCount'])
                total_views += views
            except:
                pass
                
            title = item["snippet"]["title"]
            desc = item["snippet"]["description"]
            viral_data.append(f"TYTUŁ: {title} | OPIS: {desc[:100]}...")
            
        print(f"✅ Znaleziono {len(viral_data)} hitów nakręcających wyświetlenia w przeciągu ostatnich 7 dni.")
        
        # Jeśli suma wyświetleń z TOP 5 filmów (z tego tygodnia) przekracza 5 milionów, wiemy o OGROMNYM RUCHU.
        if total_views > 5000000:
            print(f"🔥 WYKRYTO MEGA-TREND: Branża '{query}' ma aktualnie w sieci ponad {total_views} wyświetleń w ten tydzień! Synapsa włącza tryb agresywny.")
            viral_data.append("UWAGA SYSTEMOWA: Twoja nisza to absolutny MEGA-TREND. Zwiększ klikalność skryptu, użyj kontrowersyjnego, szokującego Języka! Algorytmy szaleją.")
        else:
            print(f"📉 Trend Stabilny (Wolumen 7-dniowy: {total_views}). Konstruowanie trwałego skryptu Cash Cow.")
            
        return viral_data
    except Exception as e:
        print(f"❌ Błąd skanowania API YouTube: {e}")
        return ["Błąd połączenia, przejdź do improwizacji eksperckiej."]

def generate_viral_script(viral_context, niche_topic, channel_rule, forbidden_topics=None):
    """Przekierowanie zapytania o scenariusz wideo bezpośrednio do lokalnego modelu Qwen2.5 z użyciem Synapsa Bridge."""
    return generate_viral_script_with_synapsa(viral_context, niche_topic, channel_rule, forbidden_topics)

TOPIC_HISTORY_FILE = "accounts/topic_history.json"

def get_forbidden_topics(profile_name: str, limit: int = 15) -> list:
    if not os.path.exists(TOPIC_HISTORY_FILE):
        return []
    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile_history = data.get(profile_name, [])
        return [item["title"] for item in profile_history][-limit:]
    except:
        return []

def add_to_history(profile_name: str, title: str):
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
        "title": title
    })
    
    data[profile_name] = data[profile_name][-50:]
    
    with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def run_one_click_agent(niche: str, profile_name: str):
    print("===============================================================")
    print(f"🚀 ONE-CLICK CASH COW AGENT: ROZPOCZYNAM AUTOMATYZACJĘ ({niche})")
    print("===============================================================")
    
    # 1. Połączenie z YouTube
    youtube = get_authenticated_service(profile_name)
    if not youtube:
        print("Ostrzeżenie: Agent nie uzyskał dostępu. Proces opiera się na domysłach AI.")
        viral_context = ["Brak internetu - model pracuje na danych bazowych."]
    else:
        # 2. Inteligentne skanowanie światowe z dzisiaj
        search_topic = f"{niche} facts"
        viral_context = search_viral_shorts(youtube, search_topic, count=5)
        
        # 2B. Wstrzykiwanie "The Master Memory" (Złote Wzorce wyuczone z analityki agenta)
        live_ctx_file = f"accounts/live_viral_context_{profile_name}.json"
        if os.path.exists(live_ctx_file):
            try:
                with open(live_ctx_file, "r", encoding="utf-8") as f:
                    saved_ctx = json.load(f)
                if saved_ctx.get("analyzed_shorts"):
                    print(f"🧠 Ładuję potężną the Pamięć TRENDÓW (Live Context) dla '{profile_name}'...")
                    for item in saved_ctx.get("analyzed_shorts", [])[:5]:
                        t_title = item.get("title", "")
                        hook = item.get("ai_analysis", {}).get("hook_pattern", item.get("ai_analysis", {}).get("hook_strategy", ""))
                        if t_title:
                            viral_context.append(f"ZŁOTY WZÓR: '{t_title}' | Uderzenie (Hook): {hook}")
            except Exception as e:
                pass
        
    # Pobranie wytycznych dla nastroju i konta
    niche_rule = "Bądź kontrowersyjny i stanowczy."
    if profile_name in CHANNELS_NICHES:
        niche_rule = CHANNELS_NICHES[profile_name].get('prompt', niche_rule)
        
    # Moduł Deduplikacji (Pamięć AI)
    forbidden_topics = get_forbidden_topics(profile_name)
    if forbidden_topics:
        print(f"🧠 [PAMIĘĆ DEDUPLIKACJI] Zabezpieczono {len(forbidden_topics)} starych tematów przed powtórzeniem.")
        for top_title in forbidden_topics[-3:]:
             print(f"   ✖ Zablokowano dawny temat: {top_title[:50]}...")
        
    # 3. Synapsa MASTER DIRECTOR - generuje JSON z dyrektywami dla całego wideo
    # The Anti-Short-Script Loop: Model czasem ucina odpowiedź. Wymuszamy porządny skrypt dając mu 3 próby.
    director_json = {}
    for probe in range(3):
        print(f"🎬 Synapsa Próba #{probe+1}/3: Incepcja Reżysera...")
        director_json = generate_viral_script(viral_context, niche, niche_rule, forbidden_topics)
        if "error" in director_json:
            print(f"🔴 BŁĄD PODSYSTEMU SYNAPSA: {director_json['error']}")
        script_len = len(director_json.get('script_text', '').split())
        if script_len >= 45: 
            print(f"✅ Skrypt wystarczająco gęsty ({script_len} słów).")
            break
        print(f"⚠️  Skrypt za krótki ({script_len} słów). Regeneracja! (Synapsa zgubiła wenę)")

    # Odczyt dyrektyw z JSONa Reżysera (z fallback'ami)
    script_text       = director_json.get('script_text', '')
    if not script_text.strip():
        script_text = f'Krótka historia o {niche}.'
        
    background_vibe   = director_json.get('background_vibe', f'{niche} no copyright gameplay')
    music_folder_name = director_json.get('music_folder', profile_name)
    tytul             = director_json.get('title', f'{niche} #shorts')
    opis              = director_json.get('description', f'Sprawdź {niche}! #shorts #viral')
    raw_tagi          = director_json.get('seo_tags', [niche, 'shorts', 'viral'])
    if isinstance(raw_tagi, str):
        raw_tagi = [raw_tagi]
        
    tagi = []
    for raw_t in raw_tagi:
        for t in str(raw_t).split(','):
            cl_t = t.strip().replace('<', '').replace('>', '').replace('"', '')
            if cl_t and cl_t not in tagi:
                tagi.append(cl_t)
    tagi = tagi[:35]
    viral_reasoning   = director_json.get('viral_reasoning', '')
    
    viral_score     = director_json.get('viral_score', '?')
    vs_top_shorts   = director_json.get('vs_top_shorts', '')
    
    print("\n╔══════════════════════════════════════════════════╗")
    print("║     🧠 SYNAPSA MASTER DIRECTOR — RAPORT          ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  🎯 Ocena Viral Score:  {viral_score}/10")
    print(f"║  📊 VS Top Shorts:      {vs_top_shorts[:120]}")
    print(f"║  💡 Reasoning:          {viral_reasoning[:100]}")
    print(f"║  📝 Skrypt (początek):  {script_text[:90]}...")
    print(f"║  🎬 Tło wideo:          {background_vibe}")
    print(f"║  🎵 Muzyka:             {music_folder_name}")
    print(f"║  📌 Tytuł YT:           {tytul}")
    print(f"║  🔖 Tagi:               {', '.join(tagi[:5])}")
    print("╚══════════════════════════════════════════════════╝")
    
    # 4. Fabryka renderowania - egzekutor dyrektyw Synapsy
    output_video = generate_cashcow_from_text(
        script_text, profile_name,
        background_vibe=background_vibe,
        music_folder=music_folder_name
    )
    
    # 5. Automatyczna Publikacja The-Real-One-Click
    print("\n--- ETAP 5: Autopublikacja na kanale YouTube (1-Click) ---")
    if youtube and output_video:
        from upload_youtube import upload_video
        
        # --- OBLICZANIE PEAK TIME / KALENDARZA ---
        publish_at_iso = None
        peak_times_file = "accounts/peak_times.json"
        privacy_to_use = "private" 
        
        if os.path.exists(peak_times_file):
            with open(peak_times_file, "r", encoding="utf-8") as f:
                peak_times = json.load(f)
            if profile_name in peak_times:
                time_str = peak_times[profile_name] 
                parts = time_str.split(":")
                t_hour, t_min = int(parts[0]), int(parts[1]) if len(parts)>1 else 0
                
                now = datetime.now(timezone.utc)
                target_dt = now.replace(hour=t_hour, minute=t_min, second=0, microsecond=0)
                if target_dt <= now:
                    target_dt += timedelta(days=1)
                
                publish_at_iso = target_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                print(f"🕒 AUTOMATYZACJA CZASU: Kanał osiąga szczyty o {time_str}. Zaplanowano premierę na {publish_at_iso}.")

        try:
            upload_video(
                youtube=youtube,
                file_path=output_video,
                title=tytul,       # <-- z Synapsy
                description=opis,  # <-- z Synapsy
                tags=tagi,
                category_id="24", # Entertainment/Rozrywka
                privacy_status=privacy_to_use, 
                publish_at=publish_at_iso
            )
            # Rejestracja w Pamięci Deduplikacyjnej (Sukces Publikacji)
            add_to_history(profile_name, tytul)
        except Exception as e:
            print(f"❌ Błąd w trakcie walidacji i wgrywania: {e}")
    
    print("\n🎉 MISJA ZAKOŃCZONA! AGENT ONE-CLICK PRZYSZŁOŚCI WYKONAŁ PRACĘ.")
    print(f"Plik wyjściowy znajduje się również na dysku: {output_video}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="One-Click Skrypt dla 5 nisz badający światowy YT")
    parser.add_argument("--konto", type=str, default="kanal_1", help="Profil (np. kanal_1)")
    parser.add_argument("--nisza", type=str, default="roblox brainrot stories", help="Tematyka światowa do przebadania (domyślnie najmocniejsze dopaminowe treści)")
    args = parser.parse_args()
    
    run_one_click_agent(args.nisza, args.konto)
