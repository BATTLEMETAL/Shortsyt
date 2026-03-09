import os
import pickle
import json
import cv2
import numpy as np
import pandas as pd
import yt_dlp
from tqdm import tqdm
from moviepy.editor import VideoFileClip
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from multiprocessing import Process, Queue

# --- PATCH dla Python 3.9 ---
import importlib.metadata

if not hasattr(importlib.metadata, "packages_distributions"):
    def _fake_packages_distributions(): return {}


    importlib.metadata.packages_distributions = _fake_packages_distributions
# --- KONIEC PATCHA ---

# --- USTAWIENIA ---
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
ANALYSIS_TIMEOUT = 1200  # Maksymalny czas analizy jednego filmu w sekundach (20 minut)


# ==============================================================================
# === FUNKCJE POMOCNICZE (BEZ ZMIAN) ===
# ==============================================================================
def get_authenticated_service(profile_name="kanal_1"):
    credentials = None
    # Autoryzowanie pod profil konkretnego kanału (Multikonta bez wpisywania haseł)
    token_file = os.path.join("accounts", f"{profile_name}_token.pickle")
    if not os.path.exists(token_file):
        print(f"❌ BLOKADA: Nie znaleziono tokenu dla '{profile_name}'. Użyj wpierw: 'python authorize_channel.py --konto {profile_name}'")
        return None
        
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token: credentials = pickle.load(token)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0, prompt='consent select_account')
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)


def get_channel_videos(youtube, channel_id: str = None) -> list[str]:
    """Pobiera ID filmów z podanego kanału. Jeśli brak ID, pobierze dla zalogowanego."""
    video_ids = []
    try:
        if channel_id:
            channels_response = youtube.channels().list(part='contentDetails', id=channel_id).execute()
        else:
            channels_response = youtube.channels().list(part='contentDetails', mine=True).execute()

        if not channels_response.get('items'):
            print(f"❌ Nie znaleziono kanału dla dostarczonego ID/tokenu.")
            return []

        uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        next_page_token = None
        while True:
            playlist_request = youtube.playlistItems().list(part='contentDetails', playlistId=uploads_playlist_id,
                                                            maxResults=50, pageToken=next_page_token)
            playlist_response = playlist_request.execute()
            for item in playlist_response.get('items', []): video_ids.append(item['contentDetails']['videoId'])
            next_page_token = playlist_response.get('nextPageToken')
            if not next_page_token: break
            
        # Ograniczmy sztucznie zaciąganie do max 50 najnowszych/najstarszych filmów per kanał referencyjny na potrzeby testów
        video_ids = video_ids[:50] 
        print(f"✅ Znaleziono {len(video_ids)} filmów dla kanału (ID: {channel_id or 'Twój kanał'}).")
        return video_ids
    except Exception as e:
        print(f"❌ Błąd przy pobieraniu listy filmów dla {channel_id}: {e}")
        return []


def get_video_stats(youtube, video_id: str) -> dict:
    try:
        request = youtube.videos().list(part="statistics,contentDetails", id=video_id)
        response = request.execute()
        if not response.get("items"): return {}
        stats = response["items"][0]["statistics"]
        details = response["items"][0]["contentDetails"]
        return {'views': int(stats.get('viewCount', 0)), 'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)), 'duration': details.get('duration', 'PT0S')}
    except Exception as e:
        print(f"❌ Nie udało się pobrać statystyk dla filmu {video_id}: {e}")
        return {}


def generuj_metadane(topic: str, api_key: str = None) -> (str, str, list):
    from synapsa_bridge import generate_metadata_with_synapsa
    # Argument api_key pozostawiony dla zgodności starego wywołania, ale Synapsa działa w pełni lokalnie bez API.
    return generate_metadata_with_synapsa(topic)


# ==============================================================================
# === BEZPIECZNA FUNKCJA ANALIZY W OSOBNYM PROCESIE ===
# ==============================================================================
def analyze_video_features_worker(file_path: str, result_queue: Queue):
    try:
        features = {}
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened(): raise IOError("OpenCV nie mogło otworzyć pliku.")

        scores, prev_frame = [], None
        while True:
            ret, frame = cap.read()
            if not ret: break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_frame is not None and prev_frame.shape == gray.shape:
                flow = cv2.calcOpticalFlowFarneback(prev_frame, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                scores.append(np.mean(np.abs(flow)))
            prev_frame = gray
        features['avg_motion'] = np.mean(scores) if scores else 0

        clip = VideoFileClip(file_path)
        if clip.duration and clip.duration > 0:
            avg_color_frame = clip.get_frame(clip.duration / 2)
            features.update({'avg_color_r': float(np.mean(avg_color_frame[:, :, 0])),
                             'avg_color_g': float(np.mean(avg_color_frame[:, :, 1])),
                             'avg_color_b': float(np.mean(avg_color_frame[:, :, 2]))})
            avg_volume = 0.0
            if clip.audio:
                try:
                    audio_samples = clip.audio.to_soundarray()
                    if audio_samples.size > 0: avg_volume = float(np.sqrt(np.mean(audio_samples ** 2)))
                except Exception:
                    pass
            features['avg_volume'] = avg_volume
        else:
            features.update({'avg_color_r': 0, 'avg_color_g': 0, 'avg_color_b': 0, 'avg_volume': 0})

        result_queue.put(features)
    except Exception as e:
        print(f"❌ Błąd w procesie analizy: {e}")
        result_queue.put({})
    finally:
        if 'cap' in locals() and cap.isOpened(): cap.release()
        if 'clip' in locals() and clip: clip.close()



def search_viral_shorts(youtube, query: str, max_results: int = 5) -> list:
    """
    Wyszukuje najbardziej viralowe Shorts na YouTube na podstawie zapytania.
    Zwraca listę stringów (tytuł + opis) do użycia jako kontekst dla Synapsy.
    """
    results = []
    try:
        response = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            videoDuration="short",            # tylko shortsy
            order="viewCount",                 # sortuj po wyświetleniach
            maxResults=max_results,
            relevanceLanguage="pl"
        ).execute()

        for item in response.get('items', []):
            s = item['snippet']
            title = s.get('title', '')
            desc  = s.get('description', '')[:120]
            ch    = s.get('channelTitle', '')
            results.append(f"[TREND] {title} | Kanał: {ch} | {desc}")

        print(f"  🔍 Znaleziono {len(results)} trendów dla: '{query}'")
    except Exception as e:
        # Fallback — brak autoryzacji lub quota exceeded
        print(f"  ⚠️  search_viral_shorts error (używam fallback): {e}")
        results = [f"Trending: {query} — viral shorts 2025"]

    return results


# ==============================================================================
# === GŁÓWNA LOGIKA SKRYPTU Z MECHANIZMEM WZNAWIANIA ===
# ==============================================================================
if __name__ == '__main__':
    plik_csv = 'video_features.csv'

    try:
        # Sprawdzamy, czy plik istnieje i nie jest pusty
        if os.path.exists(plik_csv) and os.path.getsize(plik_csv) > 0:
            df_istniejace = pd.read_csv(plik_csv)
            if 'video_id' in df_istniejace.columns:
                przetworzone_juz_idy = set(df_istniejace['video_id'])
                print(f"📂 Znaleziono istniejący plik CSV z {len(przetworzone_juz_idy)} przetworzonymi filmami.")
            else:
                przetworzone_juz_idy = set()
                print("⚠️ Znaleziono plik CSV, ale brakuje w nim kolumny 'video_id'. Zaczynam od nowa.")
        else:
            df_istniejace = pd.DataFrame()
            przetworzone_juz_idy = set()
            print("ℹ️ Nie znaleziono pliku CSV lub jest pusty. Tworzę nową bazę danych.")
    except Exception as e:
        df_istniejace = pd.DataFrame()
        przetworzone_juz_idy = set()
        print(f"⚠️ Wystąpił błąd przy wczytywaniu pliku CSV: {e}. Zaczynam od nowa.")

    youtube_service = get_authenticated_service()
    
    # KONFIGURACJA ŹRÓDEŁ WIEDZY DLA MODELU
    # Możesz dodać do tej listy ID kanałów reprezentujących viralowy "cash cow" w danej niszy
    # By uzyskać ID kanału spójrz w źródło strony tego kanału lub na tool online (YouTube Channel ID checker)
    TOP_COMPETITOR_CHANNELS = [
        # Wpisz tu listę stringów z ID kanałów od których model ma się uczyć np:
        # "UCLH2gUak0h2t32Wl3v9kI6w", 
        # "UC..."
    ]
    
    wszystkie_idy_z_sieci = set()
    
    if TOP_COMPETITOR_CHANNELS:
        print("\n🔎 Krok 1: Skanowanie kanałów konkurencji z branży Cash Cow...")
        for channel in TOP_COMPETITOR_CHANNELS:
            idy = get_channel_videos(youtube_service, channel_id=channel)
            wszystkie_idy_z_sieci.update(idy)
    else:
        print("\n🔎 OSTRZEŻENIE: Używam tylko Twoich filmów. By w pełni zbudować 'maszynkę', podaj ID kanałów Cash Cow w kodzie.")
        # Opcja analizy własnego kanału (przydatne przy farmach uczących)
        wszystkie_idy_z_sieci.update(get_channel_videos(youtube_service))

    idy_do_przetworzenia = [vid for vid in wszystkie_idy_z_sieci if vid not in przetworzone_juz_idy]

    if not idy_do_przetworzenia:
        print("\n🎉 Baza danych jest aktualna! Nie znaleziono nowych filmów do przetworzenia.")
    else:
        print(f"\n🔥 Znaleziono {len(idy_do_przetworzenia)} nowych filmów do analizy.")

        # Inicjalizujemy listę na nowe dane
        nowe_dane_wideo = []

        # ==========================================================
        # ===                KLUCZOWA POPRAWKA                   ===
        # ==========================================================
        with tqdm(total=len(idy_do_przetworzenia), desc="📊 Przetwarzanie NOWYCH filmów", unit="film") as pbar:
            for video_id in idy_do_przetworzenia:
                pbar.set_postfix_str(f"ID: {video_id}")
                print(f"\n--- 🎬 Przetwarzam film: {video_id} ---")

                stats = get_video_stats(youtube_service, video_id)
                if not stats:
                    pbar.update(1)
                    continue

                download_path = None
                try:
                    ydl_opts = {'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                                'outtmpl': f'{video_id}.%(ext)s', 'quiet': True, 'no_warnings': True,
                                'cookiefile': 'cookies.txt',
                                'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
                        download_path = ydl.prepare_filename(info_dict)
                except Exception as e:
                    print(f"❌ Błąd podczas pobierania: {e}")
                    pbar.update(1)
                    continue

                if not (download_path and os.path.exists(download_path)):
                    pbar.update(1)
                    continue

                result_queue = Queue()
                analyzer_process = Process(target=analyze_video_features_worker, args=(download_path, result_queue))
                analyzer_process.start()
                pbar.set_postfix_str(f"Analiza {os.path.basename(download_path)} (limit: {ANALYSIS_TIMEOUT // 60} min)")
                analyzer_process.join(timeout=ANALYSIS_TIMEOUT)

                features = {}
                if analyzer_process.is_alive():
                    print(f"⏰ PRZEKROCZONO LIMIT CZASU! Przerywam analizę pliku {os.path.basename(download_path)}.")
                    analyzer_process.terminate();
                    analyzer_process.join()
                else:
                    if not result_queue.empty():
                        features = result_queue.get();
                        print("✅ Analiza zakończona.")
                    else:
                        print("🤷 Proces analizy zakończył się bez wyników.")

                if os.path.exists(download_path):
                    try:
                        os.remove(download_path); print(f"🗑️ Usunięto plik tymczasowy.")
                    except OSError as e:
                        print(f"⚠️ Nie można usunąć pliku: {e}")

                if not features:
                    pbar.update(1)
                    continue

                video_data = {'video_id': video_id, **stats, **features}

                # Zapisujemy postęp po każdej iteracji
                try:
                    df_nowy_wiersz = pd.DataFrame([video_data])
                    plik_istnieje_i_nie_jest_pusty = os.path.exists(plik_csv) and os.path.getsize(plik_csv) > 0
                    df_nowy_wiersz.to_csv(plik_csv, mode='a', header=not plik_istnieje_i_nie_jest_pusty, index=False)
                    pbar.set_postfix_str(f"Zapisano postęp po {video_id}")
                except OSError as e:
                    print(f"❌ KRYTYCZNY BŁĄD ZAPISU: {e}. Przerywam. Zwolnij miejsce na dysku!")
                    break

                pbar.update(1)

        # Ostateczne przetworzenie pliku CSV po zakończeniu pętli
        print("\n🔄 Końcowe przetwarzanie danych (obliczanie wskaźników)...")
        try:
            df_finalny = pd.read_csv(plik_csv)
            df_finalny['views'] = pd.to_numeric(df_finalny['views'], errors='coerce').fillna(0)
            df_finalny['likes'] = pd.to_numeric(df_finalny['likes'], errors='coerce').fillna(0)
            df_finalny['engagement_rate'] = np.where(df_finalny['views'] > 0, df_finalny['likes'] / df_finalny['views'],
                                                     0)
            median_engagement = df_finalny[df_finalny['engagement_rate'] > 0]['engagement_rate'].median()
            if pd.isna(median_engagement): median_engagement = 0
            df_finalny['sukces'] = (df_finalny['engagement_rate'] > median_engagement).astype(int)

            df_finalny.drop_duplicates(subset='video_id', keep='last', inplace=True)

            df_finalny.to_csv(plik_csv, index=False)
            print(f"\n✅ Zakończono. Baza danych '{plik_csv}' jest w pełni aktualna.")
        except FileNotFoundError:
            print(
                "🤷 Nie znaleziono pliku CSV do finalnego przetworzenia. Prawdopodobnie żaden film nie został pomyślnie przeanalizowany.")
        except Exception as e:
            print(f"❌ Wystąpił błąd podczas finalnego przetwarzania pliku CSV: {e}")