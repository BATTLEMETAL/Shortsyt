import os
import sys
import pickle
import argparse

# Wymuszenie UTF-8 na stdout/stderr (Windows CP1250 nie obsługuje emoji)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/yt-analytics.readonly',  # CTR, impressions, AVD
    'https://www.googleapis.com/auth/youtube.force-ssl',      # Wymagany do komentarzy CTA + thumbnail upload
]

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

            # OAUTHLIB_RELAX_TOKEN_SCOPE=1 zapobiega crashowi gdy Google zwróci
            # węższy zakres niż żądany (force-ssl wymaga dodania w OAuth consent screen)
            os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            credentials = flow.run_local_server(port=0, prompt='consent select_account')

        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
        print(f"🎉 SUKCES! Zapisano autoryzację kanału do pliku: {token_file}")

        # Sprawdź które scope'y faktycznie zostały nadane
        granted = set(getattr(credentials, 'scopes', None) or [])
        has_force_ssl = any('force-ssl' in s for s in granted)
        has_analytics = any('yt-analytics' in s for s in granted)
        print(f"   📋 Przyznane scope'y: {len(granted)}")
        for s in sorted(granted):
            print(f"      ✅ {s}")
        if not has_force_ssl:
            print()
            print("   ⚠️  BRAK SCOPE: youtube.force-ssl")
            print("   ➡️  CTA komentarze NIE będą działać dopóki nie dodasz tego scope'u do")
            print("   ➡️  Google Cloud Console → APIs & Services → OAuth consent screen → Scopes")
            print("   ➡️  Dodaj: https://www.googleapis.com/auth/youtube.force-ssl")
            print("   ➡️  Po dodaniu usuń token i uruchom ponownie: authorize_channel.py --konto dark_mindset")
        if not has_analytics:
            print("   ⚠️  BRAK SCOPE: yt-analytics.readonly (CTR/impressions nie będą dostępne)")
    else:
        print(f"👍 To konto jest już połączone i gotowe do pracy!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zaloguj nowe konto do automatu Cash Cow bez wpisywania haseł (OAuth).")
    parser.add_argument("--konto", type=str, default="kanal_1", help="Podaj nazwę profilu (np. kanal_1, kanal_2, kanal_5)")
    args = parser.parse_args()
    
    authorize_channel(args.konto)
