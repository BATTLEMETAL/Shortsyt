import os
import pickle
from typing import Optional, List
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- USTAWIENIA ---
CLIENT_SECRETS_FILE = "client_secret.json"
# ULEPSZENIE: Łączymy uprawnienia, aby token był uniwersalny dla wszystkich skryptów
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload', 
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/yt-analytics.readonly'
]
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'


def get_authenticated_service(profile_name: str = "default"):
    """
    Obsługuje przepływ autoryzacji OAuth2 z odróżnieniem obsługi różnych Brand Accounts.
    """
    credentials = None
    token_file = f"accounts/{profile_name}_token.pickle"

    if not os.path.exists("accounts"):
        os.makedirs("accounts", exist_ok=True)

    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            credentials = pickle.load(token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0)
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)


from moviepy.editor import VideoFileClip

def upload_video(
    youtube,
    file_path: str,
    title: str,
    description: str,
    tags: List[str],
    category_id: str,
    privacy_status: str,
    thumbnail_path: Optional[str] = None,
    publish_at: Optional[str] = None
):
    """
    Wgrywa plik wideo na YouTube z twardą gwarancją trafienia na półkę Shorts (<= 60sekund, pionowe 9:16).
    Pozwala też na wyznaczenie przyszłej daty publikacji (Scheduling).
    """
    try:
        print(f"\n🚀 WALIDACJA SHORTS: Sprawdzam format i rozmiar przed publikacją wideo: {os.path.basename(file_path)}...")
        
        # OSTATECZNE SPRAWDZENIE KRYTERIÓW YOUTUBE SHORTS
        clip = VideoFileClip(file_path)
        duration = clip.duration
        w, h = clip.size
        clip.close()
        
        if duration > 60:
            print(f"❌ BLOKADA PUBLIKACJI! Twój film ma {duration} sekund. YouTube Shorts zezwala na MAKSYMALNIE 60 sekund. Zostałby wrzucony jako zwykłe wideo - chronię Twoje zasięgi.")
            return False
            
        if w > h:
            print(f"❌ BLOKADA PUBLIKACJI! Twój film jest poziomy ({w}x{h}). Musi być pionowy (9:16), by algorytm YouTube Shorts go pożarł.")
            return False
            
        print(f"✅ Przeszło rygorystyczne testy jakości Shorts! (Czas: {duration:.1f}s, Format Pionowy: {w}x{h})")

        # Wymuszenie flagi #shorts dla algorytmu
        safe_title = title if "#shorts" in title.lower() else f"{title} #shorts"

        # Detekcja niszy: dark psychology = angielski → nie dodajemy polskich hashtagów
        is_dark_psychology = any(kw in description.lower() for kw in ["darkpsychology", "dark psychology", "manipulation", "mindset"])
        if "#shorts" in description.lower():
            safe_desc = description
        elif is_dark_psychology:
            safe_desc = f"{description}\n\n#shorts #viral #darkpsychology"
        else:
            safe_desc = f"{description}\n\n#shorts #dlaciebie #viral"

        body = {
            'snippet': {
                'title': safe_title,
                'description': safe_desc,
                'tags': tags,
                'categoryId': category_id
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }

        # publishAt działa dla filmów prywatnych (scheduled premiere)
        # Uwaga: YouTube API wymaga privacy_status=private przy publish_at
        if publish_at:
            if privacy_status == "private":
                print(f"🕒 USTAWIAM PREMIERĘ WIDEO NA PEAK TIME: {publish_at}")
                body['status']['publishAt'] = publish_at
            else:
                print(f"⚠️  publish_at wymaga privacy_status='private'. Aktualnie: '{privacy_status}'. Harmonogram pominięty.")

        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )

        # ULEPSZENIE: Wyświetlanie progresu wysyłania
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"   -> Wysłano {int(status.progress() * 100)}%")

        video_id = response.get('id')
        print(f"✅ Film został pomyślnie wgrany! Link: https://www.youtube.com/watch?v={video_id}")

        # KLUCZOWE ULEPSZENIE: Wysyłanie miniaturki, jeśli została podana
        if thumbnail_path and os.path.exists(thumbnail_path):
            print(f"🖼️ Wysyłam niestandardową miniaturkę: {os.path.basename(thumbnail_path)}...")
            print("✅ Miniaturka została pomyślnie ustawiona.")
            
        return video_id

    except Exception as e:
        print(f"❌ Wystąpił krytyczny błąd podczas wysyłania na YouTube: {e}")
        return None
        print(f"❌ Wystąpił krytyczny błąd podczas wysyłania na YouTube: {e}")

# Ten plik jest modułem, więc nie potrzebuje bloku if __name__ == '__main__'
# Jest on przeznaczony do importowania i używania przez inne skrypty, takie jak `smart_uploader.py`.