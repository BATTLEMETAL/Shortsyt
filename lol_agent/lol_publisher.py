"""
LOL Agent — Publisher YouTube
Publikuje gotowego Shorta na kanał Dwannellenga (LoL)
"""
import os
import sys
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# Dodaj ścieżkę do folderu głównego projektu (żeby znaleźć client_secret.json)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from lol_config import (
    CLIENT_SECRET_PATH, TOKEN_PATH, ACCOUNTS_DIR,
    CHANNEL_PROFILE, YT_CATEGORY_ID, YT_PRIVACY
)

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube',
]


def get_lol_youtube_service():
    """
    Autoryzuje i zwraca serwis YouTube API dla kanału LoL (Dwannellenga).
    Jeśli token nie istnieje — otwiera przeglądarkę do logowania.
    """
    credentials = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as f:
            credentials = pickle.load(f)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("🔄 Odświeżam token LoL...")
            credentials.refresh(Request())
        else:
            print(f"🌐 Otwieram przeglądarkę — zaloguj się na KONTO LoL (Dwannellenga)...")
            if not os.path.exists(CLIENT_SECRET_PATH):
                raise FileNotFoundError(
                    f"Brak pliku client_secret.json: {CLIENT_SECRET_PATH}\n"
                    "Pobierz go z Google Cloud Console."
                )
            os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            credentials = flow.run_local_server(port=0, prompt='consent select_account')

        os.makedirs(ACCOUNTS_DIR, exist_ok=True)
        with open(TOKEN_PATH, 'wb') as f:
            pickle.dump(credentials, f)
        print(f"✅ Token LoL zapisany: {TOKEN_PATH}")

    return build('youtube', 'v3', credentials=credentials)


def upload_lol_short(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy: str = YT_PRIVACY,
    thumbnail_path: str = None,
    category_id: str = YT_CATEGORY_ID,
) -> dict:
    """
    Uploaduje Shorta LoL na YouTube.
    Zwraca dict z video_id i url.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Brak pliku wideo: {video_path}")

    print(f"\n🚀 Uploading na YouTube...")
    print(f"   📹 Plik: {os.path.basename(video_path)}")
    print(f"   📌 Tytuł: {title[:60]}...")
    print(f"   🔒 Privacy: {privacy}")

    youtube = get_lol_youtube_service()

    # Dodaj #Shorts do tytułu jeśli nie ma
    if "#Shorts" not in title and "#shorts" not in title:
        if len(title) < 90:
            title = title + " #Shorts"

    body = {
        "snippet": {
            "title": title[:100],  # Max 100 znaków
            "description": description[:5000],  # Max 5000
            "tags": tags[:30],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(
        video_path,
        chunksize=4 * 1024 * 1024,  # 4MB chunks
        resumable=True,
        mimetype="video/mp4"
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    print("   ⏳ Uploading", end="", flush=True)

    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"\r   ⏳ Uploading: {pct}%", end="", flush=True)

    print()
    video_id = response.get("id", "")
    video_url = f"https://www.youtube.com/shorts/{video_id}"

    print(f"\n✅ SHORT OPUBLIKOWANY!")
    print(f"   🎮 Video ID: {video_id}")
    print(f"   🔗 URL: {video_url}")

    # Thumbnail
    if thumbnail_path and os.path.exists(thumbnail_path):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            print(f"   🖼️  Thumbnail ustawiony!")
        except Exception as e:
            print(f"   ⚠️  Thumbnail error: {e}")

    return {
        "video_id": video_id,
        "url": video_url,
        "title": title,
    }


if __name__ == "__main__":
    # Test autoryzacji
    print("🔐 Test autoryzacji kanału LoL (Dwannellenga)...")
    try:
        service = get_lol_youtube_service()
        channels = service.channels().list(part="snippet", mine=True).execute()
        for ch in channels.get("items", []):
            print(f"✅ Połączono z kanałem: {ch['snippet']['title']}")
    except Exception as e:
        print(f"❌ Błąd: {e}")
