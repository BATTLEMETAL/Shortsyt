"""
Shortsyt — Jednorazowa autoryzacja TikTok OAuth 2.0 z obsługą PKCE (Hex SHA256 specyficzny dla TikToka).
"""
import os
import sys
import time
import json
import hashlib
import secrets
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()

ACCOUNTS_DIR = ROOT_DIR / "accounts"
TIKTOK_TOKEN_PATH = ACCOUNTS_DIR / "tiktok_token.json"
AUTH_URL_FILE = ACCOUNTS_DIR / "_current_tiktok_auth_url.txt"

REDIRECT_URI = "http://localhost:8180/callback"
LOCAL_PORT = 8180

auth_code_received = None
current_code_verifier = None


def generate_pkce_pair():
    """
    Generuje parę PKCE dla TikToka:
    code_verifier: 64-znakowy losowy ciąg z [A-Za-z0-9-._~]
    code_challenge: Hexadecymalny SHA-256 (hexdigest), wymagany specyficznie przez TikTok Desktop OAuth!
    """
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    verifier = "".join(secrets.choice(chars) for _ in range(64))
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    return verifier, challenge


class CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        global auth_code_received
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code_received = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><title>TikTok Autoryzacja — Sukces</title></head>
            <body style="background:#0F121C;color:#E4D6B5;font-family:sans-serif;text-align:center;padding:50px;">
                <h1 style="color:#55E88D;">✅ Autoryzacja TikTok zakończona sukcesem!</h1>
                <p>Kod został odebrany. Trwa zapisywanie tokenu w Shortsyt Studio...</p>
                <p style="color:#8B8FA8;">Możesz zamknąć tę kartę i wrócić do aplikacji.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        elif "error" in params:
            err = params.get("error_description", params.get("error", ["Nieznany błąd"]))[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><title>Błąd autoryzacji</title></head>
            <body style="background:#0F121C;color:#FF6060;font-family:sans-serif;text-align:center;padding:50px;">
                <h1>❌ Błąd autoryzacji TikTok</h1>
                <p>{err}</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def exchange_code_for_token(code: str, code_verifier: str) -> dict:
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier
    }

    resp = requests.post(url, headers=headers, data=data, timeout=30)
    res_data = resp.json()

    if "access_token" in res_data:
        expires_in = res_data.get("expires_in", 86400)
        refresh_expires_in = res_data.get("refresh_expires_in", 31536000)
        now = int(time.time())

        token_record = {
            "access_token": res_data["access_token"],
            "refresh_token": res_data.get("refresh_token"),
            "open_id": res_data.get("open_id"),
            "scope": res_data.get("scope", ""),
            "token_type": res_data.get("token_type", "Bearer"),
            "expires_at": now + expires_in,
            "refresh_expires_at": now + refresh_expires_in,
            "created_at": now
        }

        ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
        TIKTOK_TOKEN_PATH.write_text(json.dumps(token_record, indent=2), encoding="utf-8")
        return token_record
    else:
        raise RuntimeError(f"Błąd wymiany kodu TikTok: {res_data}")


def main():
    global current_code_verifier
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        print("❌ Błąd: Brak TIKTOK_CLIENT_KEY lub TIKTOK_CLIENT_SECRET w pliku .env", flush=True)
        sys.exit(1)

    print("🚀 Inicjalizacja autoryzacji TikTok OAuth 2.0 (PKCE Hex)...", flush=True)
    scope = "user.info.basic,video.publish,video.upload"
    csrf_state = f"shortsyt_{int(time.time())}"

    current_code_verifier, code_challenge = generate_pkce_pair()

    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={TIKTOK_CLIENT_KEY}"
        f"&scope={scope}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&state={csrf_state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )

    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_URL_FILE.write_text(auth_url, encoding="utf-8")

    server = HTTPServer(("localhost", LOCAL_PORT), CallbackHandler)
    server.timeout = 2.0

    print(f"\n🌐 Otwieram przeglądarkę do autoryzacji TikTok...", flush=True)
    print(f"AUTH_URL_START\n{auth_url}\nAUTH_URL_END", flush=True)

    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("⏳ Oczekiwanie na autoryzację w przeglądarce (max 300s)...", flush=True)
    start_t = time.time()
    while not auth_code_received:
        server.handle_request()
        if time.time() - start_t > 300:
            print("❌ Timeout: nie odebrano autoryzacji w ciągu 300 sekund.", flush=True)
            sys.exit(1)

    print(f"✅ Odebrano kod autoryzacyjny! Wymieniam na token z użyciem PKCE verifier...", flush=True)
    try:
        tokens = exchange_code_for_token(auth_code_received, current_code_verifier)
        print(f"\n🎉🎉🎉 SUKCES! Konto TikTok połączone pomyślnie!", flush=True)
        print(f"   Token zapisany w: {TIKTOK_TOKEN_PATH}", flush=True)
        print(f"   OpenID: {tokens.get('open_id')}", flush=True)
        print(f"   Zakres uprawnień: {tokens.get('scope')}", flush=True)
        try:
            if AUTH_URL_FILE.exists():
                AUTH_URL_FILE.unlink()
        except Exception:
            pass
    except Exception as e:
        print(f"❌ Błąd zapisu tokenu: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
