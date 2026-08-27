"""
Shortsyt API — YouTube OAuth 2.0 + upload
Używa istniejącego client_secret.json i zapisuje token do accounts/lol_token.pickle
"""
import os
import pickle
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

# Relax token scope checks (Google returns extra default scopes like openid)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import CLIENT_SECRET_PATH, YT_TOKEN_PATH, ACCOUNTS_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # wymagane dla pinned comments
]


def _load_credentials() -> Optional[Credentials]:
    """Załaduj credentials z pickle."""
    if YT_TOKEN_PATH.exists():
        with open(YT_TOKEN_PATH, "rb") as f:
            return pickle.load(f)
    return None


def _save_credentials(creds: Credentials):
    """Zapisz credentials do pickle."""
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(YT_TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)


def get_token_status() -> Dict[str, Any]:
    """Sprawdź status tokenu YouTube."""
    creds = _load_credentials()

    if creds is None:
        return {
            "has_token": False,
            "is_valid": False,
            "can_refresh": False,
            "expires_at": None,
            "days_remaining": None,
            "message": "Brak tokenu — wymagana autoryzacja",
        }

    # Odśwież jeśli wygasł
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception as e:
            return {
                "has_token": True,
                "is_valid": False,
                "can_refresh": False,
                "expires_at": None,
                "days_remaining": 0,
                "message": f"Token nieważny, odświeżenie nie udało się: {e}",
            }

    days_remaining = None
    expires_at = None
    if creds.expiry:
        # expiry jest naive UTC
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        delta = creds.expiry - now_utc
        days_remaining = max(0, int(delta.total_seconds() / 86400))
        expires_at = creds.expiry.isoformat()

    return {
        "has_token": True,
        "is_valid": creds.valid,
        "can_refresh": bool(creds.refresh_token),
        "expires_at": expires_at,
        "days_remaining": days_remaining,
        "message": "Token aktywny" if creds.valid else "Token wygasł",
    }


_ACTIVE_FLOWS: Dict[int, Any] = {}


def get_auth_url() -> str:
    """
    Zwróć URL do autoryzacji YouTube OAuth.
    Używa localhost redirect — backend sam odbierze kod po zalogowaniu w przeglądarce.
    Google automatycznie przekieruje na http://localhost:PORT po autoryzacji.
    """
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(f"Brak client_secret.json: {CLIENT_SECRET_PATH}")

    import socket
    import json as _json

    # Znajdź wolny port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    redirect_uri = f"http://localhost:{port}"

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    _ACTIVE_FLOWS[port] = flow

    # Zapisz konfigurację do pliku (wraz z code_verifier dla PKCE)
    flow_path = YT_TOKEN_PATH.parent / "_pending_flow.json"
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    _json.dump({
        "client_config_file": str(CLIENT_SECRET_PATH),
        "scopes": SCOPES,
        "redirect_uri": redirect_uri,
        "port": port,
        "code_verifier": getattr(flow, "code_verifier", None),
    }, open(flow_path, "w", encoding="utf-8"))

    # Uruchom callback server w tle — czeka na redirect od Google
    import threading
    threading.Thread(target=_run_callback_server, args=(port, str(flow_path)), daemon=True).start()

    return auth_url


def _run_callback_server(port: int, flow_path_str: str) -> None:
    """
    Minimalny HTTP server który odbiera callback od Google OAuth i wymienia kod na token.
    Działa w tle jako daemon thread — kończy się automatycznie po odebraniu kodu.
    """
    import http.server
    import urllib.parse
    import time
    import threading

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if "code" not in params:
                error = params.get("error", ["unknown"])[0]
                body = f"""<!DOCTYPE html>
                <html><head><meta charset="utf-8"><title>Błąd</title></head>
                <body style="background:#0A0E1A;color:#FF6060;font-family:sans-serif;text-align:center;padding:60px">
                <h2>❌ Błąd autoryzacji: {error}</h2>
                <p style="color:#8B8FA8">Wróć do aplikacji i spróbuj ponownie.</p>
                </body></html>""".encode("utf-8")

                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
                return

            code = params["code"][0]

            # Najpierw wymień token
            success = _exchange_code_direct(code, flow_path_str, port)

            if success:
                body = """<!DOCTYPE html>
                <html><head><meta charset="utf-8"><title>Sukces!</title></head>
                <body style="background:#0A0E1A;color:#55E88D;font-family:sans-serif;text-align:center;padding:60px">
                <h1 style="font-size:32px">✅ Autoryzacja zakończona sukcesem!</h1>
                <p style="color:#E4D6B5;font-size:16px;margin-top:16px">Token YouTube z uprawnieniami został zapisany.</p>
                <p style="color:#8B8FA8;font-size:13px;margin-top:8px">Możesz zamknąć tę kartę i wrócić do aplikacji Shortsyt Studio.</p>
                <script>setTimeout(()=>window.close(), 3500)</script>
                </body></html>""".encode("utf-8")
                self.send_response(200)
            else:
                body = """<!DOCTYPE html>
                <html><head><meta charset="utf-8"><title>Błąd zapisu</title></head>
                <body style="background:#0A0E1A;color:#FF6060;font-family:sans-serif;text-align:center;padding:60px">
                <h2>⚠️ Błąd wymiany kodu</h2>
                <p style="color:#8B8FA8">Nie udało się zapisać tokenu. Spróbuj ponownie w aplikacji.</p>
                </body></html>""".encode("utf-8")
                self.send_response(500)

            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

            # Zaplanuj zamknięcie serwera za 2 sekundy, żeby przeglądarka zdążyła odebrać stronę
            def _delayed_shutdown(srv):
                time.sleep(2.0)
                try:
                    srv.shutdown()
                except Exception:
                    pass

            threading.Thread(target=_delayed_shutdown, args=(self.server,), daemon=True).start()

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

    try:
        server = http.server.HTTPServer(("0.0.0.0", port), _CallbackHandler)
        server.timeout = 300
        server.serve_forever()
    except Exception as e:
        print(f"[OAuth callback server error]: {e}")


def _exchange_code_direct(code: str, flow_path_str: str, port: int) -> bool:
    """Wymień kod OAuth na token, uwzględniając PKCE code_verifier."""
    import json as _json
    try:
        flow = _ACTIVE_FLOWS.pop(port, None)
        if flow is None:
            flow_path = Path(str(flow_path_str))
            if not flow_path.exists():
                print("[OAuth] ❌ Brak pliku flow", flush=True)
                return False
            cfg = _json.load(open(flow_path, encoding="utf-8"))
            flow = InstalledAppFlow.from_client_secrets_file(
                cfg["client_config_file"],
                scopes=cfg["scopes"],
                redirect_uri=cfg["redirect_uri"],
            )
            if cfg.get("code_verifier"):
                flow.code_verifier = cfg["code_verifier"]

        flow.fetch_token(code=code)
        creds = flow.credentials
        _save_credentials(creds)
        Path(str(flow_path_str)).unlink(missing_ok=True)
        print("[OAuth] SUCCESS: YouTube token saved successfully!", flush=True)
        return True
    except Exception as e:
        print(f"[OAuth] ERROR: Token exchange failed: {repr(e)}", flush=True)
        return False


def exchange_auth_code(code: str) -> Dict[str, Any]:
    """Ręczna wymiana kodu autoryzacji na token (fallback)."""
    import json as _json
    flow_path = YT_TOKEN_PATH.parent / "_pending_flow.json"
    if not flow_path.exists():
        raise ValueError("Brak pending flow — najpierw wywołaj get_auth_url()")

    cfg = _json.load(open(flow_path, encoding="utf-8"))
    port = cfg.get("port", 0)
    flow = _ACTIVE_FLOWS.pop(port, None)
    if flow is None:
        flow = InstalledAppFlow.from_client_secrets_file(
            cfg["client_config_file"],
            scopes=cfg["scopes"],
            redirect_uri=cfg["redirect_uri"],
        )
        if cfg.get("code_verifier"):
            flow.code_verifier = cfg["code_verifier"]

    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_credentials(creds)
    flow_path.unlink(missing_ok=True)

    return get_token_status()


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy: str = "private",
    category_id: str = "20",
) -> Dict[str, Any]:
    """Upload wideo na YouTube."""
    creds = _load_credentials()
    if creds is None:
        raise ValueError("Brak tokenu YouTube — wymagana autoryzacja")

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)

    youtube = build("youtube", "v3", credentials=creds)

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Plik nie istnieje: {video_path}")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,  # 5MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    return {
        "video_id": response["id"],
        "url": f"https://www.youtube.com/shorts/{response['id']}",
        "title": response["snippet"]["title"],
        "status": response["status"]["privacyStatus"],
    }
