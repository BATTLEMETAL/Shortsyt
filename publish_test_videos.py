import os
from data_collector import get_authenticated_service

VIDEOS_TO_PUBLISH = {
    "brainrot": "IUxtxeh2tSE",
    "dark_mindset": "2p1l-MzgcI8"
}

def make_videos_public():
    print("==================================================")
    print("🌍 WYMUSZENIE PUBLIKACJI TESTOWYCH WIDEO")
    print("==================================================")
    
    for profile, vid_id in VIDEOS_TO_PUBLISH.items():
        print(f"\n-> Nawiązywanie połączenia z {profile.upper()} dla ID: {vid_id}...")
        try:
            youtube = get_authenticated_service(profile)
            if not youtube:
                print(f"❌ Brak autoryzacji dla kanału {profile}.")
                continue
                
            request = youtube.videos().list(part="snippet,status", id=vid_id)
            response = request.execute()
            
            if response.get("items"):
                video = response["items"][0]
                old_status = video["status"].get("privacyStatus")
                
                # Ustawiamy widoczność na w pełni publiczną
                video["status"]["privacyStatus"] = "public"
                
                # Jeżeli wideo było zaplanowane w Harmonogramie, anulujemy kalendarz wypychając je NOW!
                if "publishAt" in video["status"]:
                    del video["status"]["publishAt"]
                    
                youtube.videos().update(part="snippet,status", body=video).execute()
                print(f"✅ Sukces: Wideo '{video['snippet']['title']}' zostało UPUBLICZNIONE!")
                print(f"👉 Link do Shorts: https://www.youtube.com/shorts/{vid_id}")
            else:
                print(f"❌ Nie znaleziono wideo {vid_id} w bazie API.")
        except Exception as e:
            print(f"❌ Wystąpił błąd komunikacji API dla {profile}: {e}")

if __name__ == "__main__":
    make_videos_public()
