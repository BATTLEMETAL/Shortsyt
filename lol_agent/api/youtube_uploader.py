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

    # Odśwież jeśli wygasł access token (1h)
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

    # creds.expiry to czas wygaśnięcia krótkotrwałego access tokenu (1 godzina).
    # Dopóki creds.refresh_token istnieje, token odnawia się automatycznie w nieskończoność
    # (w trybie Testing Google Cloud token wygasa po 7 dniach od autoryzacji).
    days_remaining = 7
    expires_at = None
    if YT_TOKEN_PATH.exists() and creds.refresh_token:
        mtime = YT_TOKEN_PATH.stat().st_mtime
        days_since_auth = (time.time() - mtime) / 86400.0
        days_remaining = max(1, min(7, int(7 - days_since_auth) + (1 if (7 - days_since_auth) % 1 > 0.05 else 0)))
        expires_at = datetime.fromtimestamp(mtime + 7 * 86400, timezone.utc).isoformat()
    elif creds.expiry:
        expires_at = creds.expiry.isoformat()

    return {
        "has_token": True,
        "is_valid": creds.valid or bool(creds.refresh_token),
        "can_refresh": bool(creds.refresh_token),
        "expires_at": expires_at,
        "days_remaining": days_remaining,
        "message": f"Token aktywny (Autoodnawialny, {days_remaining} dni)" if (creds.valid or creds.refresh_token) else "Token wygasł",
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


PEAK_SLOTS_CET = ["08:30", "12:00", "18:30", "20:30"]


def get_next_optimal_publish_time() -> Dict[str, Any]:
    """
    Oblicza najbliższy wolny slot godzinowy najwyższego ruchu (Peak Hours) dla YouTube Shorts.
    Zwraca ISO UTC timestamp, czytelny label (np. 'Dziś, 18:30 CET') oraz godzinę.
    """
    try:
        from zoneinfo import ZoneInfo
        tz_cet = ZoneInfo("Europe/Warsaw")
    except Exception:
        tz_cet = timezone(timedelta(hours=2))

    now = datetime.now(tz_cet)
    
    # Przejrzyj dzisiejsze sloty
    target_dt = None
    for slot in PEAK_SLOTS_CET:
        h, m = map(int, slot.split(":"))
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # Musi być co najmniej 15 minut w przyszłości
        if candidate > now + timedelta(minutes=15):
            target_dt = candidate
            label = f"Dzisiaj o {slot} CET (Peak Slot ⚡)"
            break

    # Jeśli wszystkie dzisiejsze sloty minęły, wybierz jutro 08:30
    if target_dt is None:
        tomorrow = now + timedelta(days=1)
        target_dt = tomorrow.replace(hour=8, minute=30, second=0, microsecond=0)
        label = "Jutro o 08:30 CET (Morning Peak 🌅)"

    utc_dt = target_dt.astimezone(timezone.utc)
    publish_at_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "publish_at": publish_at_iso,
        "label": label,
        "local_time": target_dt.strftime("%Y-%m-%d %H:%M"),
        "peak_slots": PEAK_SLOTS_CET,
    }


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy: str = "private",
    category_id: str = "20",
    pinned_comment: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    publish_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload wideo na YouTube z automatycznym komentarzem, miniaturką oraz opcjonalnym planowaniem (Peak Hours)."""
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

    # Konfiguracja statusu (publiczny / prywatny / zaplanowany publishAt)
    status_body: Dict[str, Any] = {
        "selfDeclaredMadeForKids": False,
    }

    if publish_at and publish_at.strip():
        # Zgodnie ze specyfikacją YouTube API: zaplanowane filmy MUSZĄ mieć privacyStatus='private' i publishAt w RFC 3339 (UTC)
        status_body["privacyStatus"] = "private"
        # Upewnij się, że format to UTC ISO np. 2026-09-02T16:30:00Z
        clean_pub = publish_at.strip()
        try:
            dt = datetime.fromisoformat(clean_pub.replace("Z", "+00:00"))
            status_body["publishAt"] = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            status_body["publishAt"] = clean_pub
        print(f"[YouTube] ⏰ Zaplanowano publikację na slot: {status_body['publishAt']}")
    else:
        status_body["privacyStatus"] = privacy

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": status_body,
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

    video_id = response["id"]
    print(f"[YouTube] ✅ Wideo wgrane pomyślnie! ID: {video_id}")

    # 1. Automatyczne wgrywanie miniaturki (jeśli podana lub istnieje plik _thumb.jpg)
    thumb_target = thumbnail_path or str(video_path).replace(".mp4", "_thumb.jpg")
    if Path(thumb_target).exists():
        try:
            thumb_media = MediaFileUpload(str(thumb_target), mimetype="image/jpeg")
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=thumb_media,
            ).execute()
            print(f"[YouTube] ✅ Miniaturka 9:16 została wgrana na YouTube: {thumb_target}")
        except Exception as te:
            print(f"[YouTube] ⚠️ Ostrzeżenie przy wgrywaniu miniaturki: {te}")

    # 2. Automatyczne dodawanie przypiętego komentarza pod Shortem
    comment_id = None
    if pinned_comment and pinned_comment.strip():
        try:
            comment_body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": pinned_comment.strip()
                        }
                    }
                }
            }
            comment_res = youtube.commentThreads().insert(
                part="snippet",
                body=comment_body
            ).execute()
            comment_id = comment_res.get("id")
            print(f"[YouTube] ✅ Przypięty komentarz dodany pod filmem: '{pinned_comment[:50]}' (ID: {comment_id})")
        except Exception as ce:
            print(f"[YouTube] ⚠️ Ostrzeżenie przy publikacji komentarza: {ce}")

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "title": response["snippet"]["title"],
        "status": response["status"]["privacyStatus"],
        "publish_at": response["status"].get("publishAt"),
        "comment_id": comment_id,
    }
