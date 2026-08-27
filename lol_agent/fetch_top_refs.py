"""Pobiera top shorty przez YouTube Data API (mamy token OAuth) i je ściąga."""
import sys, os, pickle, subprocess
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

TOKEN_PATH = os.path.join(os.path.dirname(__file__), '..', 'accounts', 'lol_token.pickle')
OUT_DIR    = r'C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\ref_downloads'
os.makedirs(OUT_DIR, exist_ok=True)

# Załaduj token
with open(TOKEN_PATH, 'rb') as f:
    token = pickle.load(f)

# Jeśli token to google.oauth2.credentials.Credentials
if hasattr(token, 'token'):
    creds = token
else:
    creds = token  # google-auth-oauthlib credentials

yt = build('youtube', 'v3', credentials=creds)

# Pobierz channel ID aktualnie zalogowanego użytkownika
ch = yt.channels().list(part='id,snippet', mine=True).execute()
channel_id = ch['items'][0]['id']
channel_name = ch['items'][0]['snippet']['title']
print(f"✅ Kanał: {channel_name} (ID: {channel_id})")

# Pobierz listę filmów (shorty = duration < 90s) — sortuj po viewCount
search_r = yt.search().list(
    part='id,snippet',
    channelId=channel_id,
    maxResults=10,
    order='viewCount',
    type='video'
).execute()

videos = []
for item in search_r['items']:
    vid_id = item['id']['videoId']
    title  = item['snippet']['title']
    videos.append({'id': vid_id, 'title': title})
    print(f"  📹 {title} → https://youtu.be/{vid_id}")

# Pobierz top 2 za pomocą yt-dlp
print(f"\n⬇️  Pobieranie top 2 shortów...")
for i, vid in enumerate(videos[:2]):
    url = f"https://www.youtube.com/watch?v={vid['id']}"
    out = os.path.join(OUT_DIR, f"ref_{i+1}.mp4")
    print(f"\n  [{i+1}] {vid['title']}")
    r = subprocess.run([
        "python", "-m", "yt_dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", out, url
    ], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode == 0 and os.path.exists(out):
        size = os.path.getsize(out) // 1024
        print(f"  ✅ Zapisano: {out} ({size} KB)")
    else:
        print(f"  ❌ Błąd: {r.stderr[:300]}")

print("\n✅ Gotowe!")
