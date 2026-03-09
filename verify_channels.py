import sys
import pickle
from googleapiclient.discovery import build

def verify_token(profile):
    token_file = f"accounts/{profile}_token.pickle"
    try:
        with open(token_file, 'rb') as f:
            credentials = pickle.load(f)
            
        youtube = build('youtube', 'v3', credentials=credentials)
        response = youtube.channels().list(part='snippet', mine=True).execute()
        
        if not response.get('items'):
            print(f"❌ Profil '{profile}': Token działa, ale nie znaleziono ŻADNEGO KANAŁU YOUTUBE na tym koncie Google!")
            return
            
        channel = response['items'][0]['snippet']
        title = channel.get('title', 'Brak Nazwy')
        custom_url = channel.get('customUrl', 'Brak Handle')
        print(f"✅ Profil '{profile}' połączony prawidłowo z kanałem:")
        print(f"   Nazwa: {title}")
        print(f"   Handle: {custom_url}\n")
        
    except FileNotFoundError:
        print(f"❌ Profil '{profile}': Brak pliku tokenu ({token_file})")
    except Exception as e:
        print(f"❌ Profil '{profile}': Wystąpił błąd autoryzacji: {e}")

if __name__ == "__main__":
    print("\n--- WERYFIKACJA PODŁĄCZONYCH KONT YOUTUBE ---")
    verify_token("brainrot")
    verify_token("dark_mindset")
    print("---------------------------------------------")
