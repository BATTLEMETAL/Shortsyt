import os
import pickle
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/youtube.upload']

def authorize_channel(profile_name: str):
    """Przeprowadza autoryzację dla wybranego profilu kanału w okienku przeglądarki i zapisuje token."""
    print(f"\n==============================================")
    print(f"🔐 ROZPOCZĘCIE AUTORYZACJI DLA KANAŁU: {profile_name.upper()}")
    print(f"==============================================")
    
    accounts_dir = "accounts"
    os.makedirs(accounts_dir, exist_ok=True)
    
    token_file = os.path.join(accounts_dir, f"{profile_name}_token.pickle")
    credentials = None
    
    if os.path.exists(token_file):
        print(f"✅ Token dla {profile_name} już istnieje. Weryfikacja...")
        with open(token_file, 'rb') as token:
            credentials = pickle.load(token)
            
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print(f"🔄 Odświeżanie wygasłego tokenu dla {profile_name}...")
            credentials.refresh(Request())
        else:
            print(f"🌐 Otwieram przeglądarkę. Zaloguj się na konto Google przygotowane pod kanał {profile_name}...")
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"❌ KRYTYCZNY BŁĄD: Nie znaleziono pliku {CLIENT_SECRETS_FILE}! Musisz go pobrać z Google Cloud Console.")
                return
                
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0, prompt='consent select_account')
            
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
        print(f"🎉 SUKCES! Zapisano autoryzację kanału do pliku: {token_file}")
    else:
        print(f"👍 To konto jest już połączone i gotowe do pracy!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zaloguj nowe konto do automatu Cash Cow bez wpisywania haseł (OAuth).")
    parser.add_argument("--konto", type=str, default="kanal_1", help="Podaj nazwę profilu (np. kanal_1, kanal_2, kanal_5)")
    args = parser.parse_args()
    
    authorize_channel(args.konto)
