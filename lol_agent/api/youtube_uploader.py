"""
Shortsyt API — YouTube OAuth 2.0 + upload
Używa istniejącego client_secret.json i zapisuje token do accounts/lol_token.pickle
"""
import copy
import os
import pickle
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# Relax token scope checks (Google returns extra default scopes like openid)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

import socket
from google.oauth2.credentials import Credentials
import sys
import types

# Compatibility shim for older pickled Google Auth tokens
try:
    import google.auth._regional_access_boundary_utils
except ImportError:
    class DummyRAB:
        def __init__(self, *args, **kwargs): pass
        def __setstate__(self, state):
            if isinstance(state, dict): self.__dict__.update(state)
        def apply_headers(self, headers): pass
        def maybe_start_refresh(self, *args, **kwargs): pass
        def set_initial_regional_access_boundary(self, *args, **kwargs): pass
        def enable_blocking_lookup(self, *args, **kwargs): pass

    _rab_mod = types.ModuleType("google.auth._regional_access_boundary_utils")
    _rab_mod.DummyRAB = DummyRAB
    _rab_mod._RegionalAccessBoundaryManager = DummyRAB
    _rab_mod._RegionalAccessBoundaryData = DummyRAB
    _rab_mod._RegionalAccessBoundaryRefreshManager = DummyRAB
    sys.modules["google.auth._regional_access_boundary_utils"] = _rab_mod
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .config import (
    CLIENT_SECRET_PATH, YT_TOKEN_PATH, ACCOUNTS_DIR,
    LOL_AGENT_DIR, LOL_TEMP_DIR, LOL_OUTPUT_DIR
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # wymagane dla pinned comments
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # wymagane dla YouTube Analytics API v2
]


def _get_yt_token_path() -> Path:
    """Zwraca ścieżkę tokenu YouTube aktywnego konta (fallback do YT_TOKEN_PATH)."""
    try:
        try:
            from lol_agent.account_manager import get_active_yt_token_path
        except ImportError:
            from account_manager import get_active_yt_token_path
        return Path(get_active_yt_token_path())
    except Exception:
        return YT_TOKEN_PATH


def ensure_rab_manager(creds: Optional[Credentials]) -> Optional[Credentials]:
    """Odtwarza brakujące pola google-auth 2.55+ (zwł. _rab_manager) na załadowanych credentials."""
    if creds is None:
        return None
    if getattr(creds, "_rab_manager", None) is None:
        try:
            from google.auth import _regional_access_boundary_utils
            creds._rab_manager = _regional_access_boundary_utils._RegionalAccessBoundaryManager()
        except Exception:
            pass
    if not hasattr(creds, "_use_non_blocking_refresh"):
        try:
            creds._use_non_blocking_refresh = False
        except Exception:
            pass
    if not hasattr(creds, "_trust_boundary"):
        try:
            creds._trust_boundary = None
        except Exception:
            pass
    return creds


def _load_credentials() -> Optional[Credentials]:
    """Załaduj credentials z pickle aktywnego konta."""
    tok_path = _get_yt_token_path()
    if tok_path.exists():
        with open(tok_path, "rb") as f:
            creds = pickle.load(f)
        return ensure_rab_manager(creds)
    return None


def _save_credentials(creds: Credentials):
    """Zapisz credentials aktywnego konta do pickle bez mutowania żywego obiektu creds w pamięci."""
    tok_path = _get_yt_token_path()
    tok_path.parent.mkdir(parents=True, exist_ok=True)
    to_dump = creds
    try:
        cloned = copy.copy(creds)
        cloned.__dict__ = dict(getattr(creds, "__dict__", {}))
        cloned.__dict__.pop("_rab_manager", None)
        to_dump = cloned
    except Exception:
        to_dump = creds
    tmp_path = tok_path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        pickle.dump(to_dump, f)
    os.replace(tmp_path, tok_path)
    ensure_rab_manager(creds)


def get_valid_credentials(
    require_token: bool = True,
    ignore_refresh_error: bool = False,
) -> Optional[Credentials]:
    """Ładuje, odświeża (jeśli wygasły) i zapisuje token YouTube z zachowaniem _rab_manager."""
    creds = _load_credentials()
    if creds is None:
        if require_token:
            raise ValueError("Brak tokenu YouTube — wymagana autoryzacja")
        return None
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            if not ignore_refresh_error:
                raise
    return ensure_rab_manager(creds)


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
    tok_path = _get_yt_token_path()
    if tok_path.exists() and creds.refresh_token:
        mtime = tok_path.stat().st_mtime
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
        server = http.server.HTTPServer(("127.0.0.1", port), _CallbackHandler)
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
        import traceback
        print(f"[OAuth] ERROR: Token exchange failed: {repr(e)}", flush=True)
        traceback.print_exc()
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


# ── Harmonogram Publikacji: 2 Shortsy dziennie (domyślnie 15:00 Global Bridge + 21:30 CET Prime) ──
DAILY_PEAK_SLOTS_CET = ["15:00", "21:30"]


def _clean_valid_hhmm_slots(raw_slots: Any) -> List[str]:
    import re
    valid_hhmm = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    if not isinstance(raw_slots, list):
        return []
    return sorted(set(str(h).strip() for h in raw_slots if valid_hhmm.match(str(h).strip())))


def get_active_peak_slots_cet(weekday: Optional[int] = None) -> List[str]:
    """
    Zwraca aktualne 2 optymalne sloty publikacji (Europe/Warsaw HH:MM):
    Gdy podano weekday (0=Pon .. 6=Nd), najpierw sprawdza harmonogram tygodniowy (peak_hours_by_weekday_cet).
    Następnie:
    1. Konfiguracja aktywnego konta z profiles_registry.json (peak_hours_cet)
    2. Rekomendacja z learning_directive.json -> best_pub_hour_analysis.recommended_slots_cet
    3. Fallback DAILY_PEAK_SLOTS_CET (["15:00", "21:30"]).
    """
    if weekday is not None:
        try:
            weekly = get_weekly_peak_schedule_cet()
            day_slots = _clean_valid_hhmm_slots(weekly.get(str(int(weekday) % 7)))
            if day_slots:
                return day_slots
        except Exception:
            pass

    try:
        try:
            from lol_agent.account_manager import get_active_account
        except ImportError:
            from account_manager import get_active_account
        acc = get_active_account()
        cleaned = _clean_valid_hhmm_slots(acc.get("peak_hours_cet") if isinstance(acc, dict) else None)
        if cleaned:
            return cleaned
    except Exception:
        pass

    try:
        directive_path = LOL_AGENT_DIR / "learning_directive.json"
        if directive_path.exists():
            import json as _json
            ld = _json.loads(directive_path.read_text(encoding="utf-8"))
            cleaned = _clean_valid_hhmm_slots(((ld.get("best_pub_hour_analysis") or {}).get("recommended_slots_cet")) or [])
            if cleaned:
                return cleaned
    except Exception:
        pass

    return list(DAILY_PEAK_SLOTS_CET)


def get_weekly_peak_schedule_cet() -> Dict[str, List[str]]:
    """
    Zwraca mapę 2 optymalnych slotów CET na każdy dzień tygodnia ("0"=Pon .. "6"=Nd).
    Kolejność źródeł: profiles_registry.peak_hours_by_weekday_cet -> learning_directive -> fallback globalny.
    """
    raw_map: Optional[Dict[str, Any]] = None
    try:
        try:
            from lol_agent.account_manager import get_active_account
        except ImportError:
            from account_manager import get_active_account
        acc = get_active_account()
        if isinstance(acc, dict) and isinstance(acc.get("peak_hours_by_weekday_cet"), dict):
            raw_map = acc["peak_hours_by_weekday_cet"]
    except Exception:
        pass

    if not raw_map:
        try:
            directive_path = LOL_AGENT_DIR / "learning_directive.json"
            if directive_path.exists():
                import json as _json
                ld = _json.loads(directive_path.read_text(encoding="utf-8"))
                cand = (ld.get("best_pub_hour_analysis") or {}).get("recommended_slots_by_weekday_cet")
                if isinstance(cand, dict) and cand:
                    raw_map = cand
        except Exception:
            pass

    fallback = get_active_peak_slots_cet(weekday=None)
    schedule: Dict[str, List[str]] = {}
    for dw in range(7):
        key = str(dw)
        day_raw = raw_map.get(key) if isinstance(raw_map, dict) else None
        if day_raw is None and isinstance(raw_map, dict):
            day_raw = raw_map.get(dw)  # type: ignore[arg-type]
        cleaned = _clean_valid_hhmm_slots(day_raw)
        schedule[key] = cleaned if cleaned else list(fallback)
    return schedule


def infer_frag_type_from_title(title: str) -> str:
    """Rozpoznaje typ akcji / fraga na podstawie tytułu filmu."""
    t = title.lower()
    if "penta" in t:
        return "pentakill"
    elif "quadra" in t:
        return "quadrakill"
    elif "triple" in t:
        return "triple"
    elif "double" in t:
        return "double"
    elif "1% hp" in t or "clutch" in t:
        return "clutch"
    elif "solo bolo" in t or "1v1" in t or "solo" in t:
        return "solo_bolo"
    return "outplay"


def _ensure_youtube_thumbnail_after_processing(
    video_id: str,
    thumb_path: str,
    delay_seconds: int = 35,
) -> bool:
    """Czeka na zakończenie transkodowania HD przez YouTube i potwierdza miniaturkę 9:16."""
    if not video_id or not thumb_path or not os.path.exists(thumb_path):
        return False
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    try:
        creds = get_valid_credentials(require_token=False, ignore_refresh_error=True)
        if creds is None:
            return False
        youtube = build("youtube", "v3", credentials=creds)
        for attempt in range(4):
            try:
                v_info = youtube.videos().list(part="processingDetails", id=video_id).execute()
                items = v_info.get("items") or []
                p_status = (items[0].get("processingDetails") or {}).get("processingStatus", "") if items else ""
                if p_status == "succeeded" or attempt == 3:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
                    ).execute()
                    _safe_print(f"[YouTube] ✅ Potwierdzono miniaturkę 9:16 po przetworzeniu HD ({video_id})")
                    return True
            except Exception:
                if attempt == 3:
                    return False
            time.sleep(15)
    except Exception:
        return False
    return False


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


_PERF_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}
_YT_API_RAW_CACHE: Dict[str, Any] = {"timestamp": 0.0, "scheduled": {}, "published": [], "views_list": []}


def invalidate_publish_cache():
    """Wymusza wyczyszczenie pamięci podręcznej publikacji i harmonogramu."""
    global _PERF_CACHE, _YT_API_RAW_CACHE
    _PERF_CACHE["data"] = None
    _PERF_CACHE["timestamp"] = 0.0
    _YT_API_RAW_CACHE["timestamp"] = 0.0
    _YT_API_RAW_CACHE["scheduled"] = {}
    _YT_API_RAW_CACHE["published"] = []
    _YT_API_RAW_CACHE["views_list"] = []


def get_channel_videos_and_performance(max_results: int = 250, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Pobiera z YouTube API oraz lokalnych baz (published_videos.jsonl, publishing_calendar.json, *.meta.json):
    1. Zaplanowane filmy (do obsadzenia w przyszłych slotach ze statusem 'scheduled')
    2. Opublikowane filmy z historycznymi statystykami (wyświetlenia, polubienia, komentarze, AVD%, engagedViews)
    3. Wskaźnik skuteczności (Performance Score) każdego opublikowanego Shorta w relacji do średniej kanału.
    Zoptymalizowane: Odpowiedzi YouTube API są buforowane przez 60s, a lokalne bazy rezerwacji czytane są ZAWSZE na żywo.
    """
    global _PERF_CACHE, _YT_API_RAW_CACHE

    try:
        from zoneinfo import ZoneInfo
        tz_cet = ZoneInfo("Europe/Warsaw")
    except Exception:
        tz_cet = timezone(timedelta(hours=2))

    now_ts = time.time()
    scheduled: Dict[str, Dict[str, Any]] = {}
    published: List[Dict[str, Any]] = []
    views_list: List[int] = []

    # ── 1. YouTube Data API (cache 60s, z paginacją powyżej 50 filmów) ──
    if not force_refresh and (now_ts - _YT_API_RAW_CACHE["timestamp"] < 60.0) and _YT_API_RAW_CACHE["timestamp"] > 0:
        scheduled = dict(_YT_API_RAW_CACHE["scheduled"])
        published = list(_YT_API_RAW_CACHE["published"])
        views_list = list(_YT_API_RAW_CACHE["views_list"])
    else:
        try:
            creds = get_valid_credentials(require_token=False, ignore_refresh_error=True)
            if creds:
                youtube = build("youtube", "v3", credentials=creds)
                ch = youtube.channels().list(part="contentDetails", mine=True).execute()
                uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

                vids: List[str] = []
                page_token = None
                while len(vids) < max_results:
                    batch_limit = min(50, max_results - len(vids))
                    pl = youtube.playlistItems().list(
                        part="snippet,status",
                        playlistId=uploads_id,
                        maxResults=batch_limit,
                        pageToken=page_token,
                    ).execute()
                    for item in pl.get("items", []):
                        vid_id = (item.get("snippet") or {}).get("resourceId", {}).get("videoId")
                        if vid_id:
                            vids.append(vid_id)
                    page_token = pl.get("nextPageToken")
                    if not page_token:
                        break

                bulk_yta: Dict[str, Dict[str, Any]] = {}
                try:
                    from .youtube_analytics import fetch_bulk_video_analytics
                    bulk_yta = fetch_bulk_video_analytics(force_refresh=force_refresh)
                except Exception:
                    try:
                        from lol_agent.api.youtube_analytics import fetch_bulk_video_analytics
                        bulk_yta = fetch_bulk_video_analytics(force_refresh=force_refresh)
                    except Exception:
                        bulk_yta = {}

                if vids:
                    video_items = []
                    for i in range(0, len(vids), 50):
                        chunk = vids[i:i + 50]
                        v_res = youtube.videos().list(
                            part="snippet,status,statistics,contentDetails",
                            id=",".join(chunk),
                        ).execute()
                        video_items.extend(v_res.get("items", []))

                    raw_published = []
                    import re as _re

                    def _parse_iso_dur(d_str: str) -> float:
                        if not d_str:
                            return 0.0
                        m = _re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d_str)
                        if not m:
                            return 0.0
                        h = int(m.group(1) or 0)
                        m_ = int(m.group(2) or 0)
                        s = int(m.group(3) or 0)
                        return float(h * 3600 + m_ * 60 + s)

                    for v in video_items:
                        st = v.get("status", {})
                        sn = v.get("snippet", {})
                        stats = v.get("statistics", {})
                        cd = v.get("contentDetails", {})
                        vid = v["id"]
                        title = sn.get("title", "")
                        thumb = sn.get("thumbnails", {}).get("medium", {}).get("url") or sn.get("thumbnails", {}).get("default", {}).get("url", "")
                        dur_s = _parse_iso_dur(cd.get("duration", ""))

                        pub_at = st.get("publishAt")
                        if pub_at:
                            dt_utc = datetime.fromisoformat(pub_at.replace("Z", "+00:00"))
                            dt_cet = dt_utc.astimezone(tz_cet)
                            key = dt_cet.strftime("%Y-%m-%d %H:%M")
                            scheduled[key] = {
                                "video_id": vid,
                                "title": title,
                                "thumbnail_url": thumb,
                                "source": "youtube_scheduled",
                                "publish_at": pub_at,
                                "duration_s": dur_s,
                            }
                        elif st.get("privacyStatus") == "public":
                            pub_dt_raw = sn.get("publishedAt")
                            if pub_dt_raw:
                                dt_utc = datetime.fromisoformat(pub_dt_raw.replace("Z", "+00:00"))
                                dt_cet = dt_utc.astimezone(tz_cet)
                                vw = int(stats.get("viewCount", 0))
                                lk = int(stats.get("likeCount", 0))
                                cm = int(stats.get("commentCount", 0))
                                eng_rate = round(((lk + cm) / vw * 100), 2) if vw > 0 else 0.0
                                if vw > 0:
                                    views_list.append(vw)
                                entry = {
                                    "video_id": vid,
                                    "title": title,
                                    "thumbnail_url": thumb,
                                    "date": dt_cet.strftime("%Y-%m-%d"),
                                    "time": dt_cet.strftime("%H:%M"),
                                    "datetime_local": dt_cet.strftime("%Y-%m-%d %H:%M CET"),
                                    "datetime_utc": pub_dt_raw,
                                    "views": vw,
                                    "likes": lk,
                                    "comments": cm,
                                    "engagement_rate": eng_rate,
                                    "duration_s": dur_s,
                                    "champion": "Katarina",
                                    "frag_type": infer_frag_type_from_title(title),
                                }
                                ya = bulk_yta.get(vid)
                                if ya:
                                    entry["avg_view_pct"] = ya.get("avg_view_pct")
                                    entry["engaged_views"] = ya.get("engaged_views")
                                    entry["engaged_view_rate_pct"] = ya.get("engaged_view_rate_pct")
                                    entry["watch_time_hours"] = ya.get("watch_time_hours")
                                    entry["shares"] = ya.get("shares")
                                    entry["subscribers_gained"] = ya.get("subscribers_gained")
                                raw_published.append(entry)

                    # Oblicz benchmark średniej kanału
                    avg_views = sum(views_list) / len(views_list) if views_list else 1

                    for item in raw_published:
                        vw = item["views"]
                        ratio = vw / avg_views if avg_views > 0 else 1.0
                        diff_pct = int((ratio - 1.0) * 100)
                        diff_str = f"+{diff_pct}%" if diff_pct >= 0 else f"{diff_pct}%"

                        if ratio >= 1.25:
                            tier = "viral_hit"
                            label = f"🔥 VIRAL HIT ({diff_str})"
                            score_val = min(10.0, round(7.5 + (ratio - 1.0) * 5, 1))
                        elif ratio >= 1.0:
                            tier = "above_avg"
                            label = f"⚡ PONAD ŚREDNIĄ ({diff_str})"
                            score_val = min(9.4, round(7.0 + (ratio - 1.0) * 4, 1))
                        elif ratio >= 0.75:
                            tier = "average"
                            label = f"🎯 W NORMIE ({diff_str})"
                            score_val = max(5.0, round(5.0 + (ratio - 0.75) * 8, 1))
                        else:
                            tier = "below_avg"
                            label = f"⚠️ PONIŻEJ ŚR. ({diff_str})"
                            score_val = max(1.0, round(ratio * 6.5, 1))

                        item["performance_score"] = f"{score_val:.1f} / 10"
                        item["performance_ratio"] = round(ratio, 2)
                        item["performance_tier"] = tier
                        item["performance_label"] = label
                        item["performance_diff"] = diff_str
                        published.append(item)

            _YT_API_RAW_CACHE["timestamp"] = now_ts
            _YT_API_RAW_CACHE["scheduled"] = dict(scheduled)
            _YT_API_RAW_CACHE["published"] = list(published)
            _YT_API_RAW_CACHE["views_list"] = list(views_list)
        except Exception as ye:
            print(f"[Scheduling] Warning fetching YouTube channel data: {ye}")

    # Połącz z lokalnymi wpisami
    pub_log_path = LOL_AGENT_DIR / "published_videos.jsonl"
    if pub_log_path.exists():
        import json as _json
        try:
            with open(pub_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        item = _json.loads(line.strip())
                        sched = item.get("scheduled_publish_at")
                        if not sched:
                            multi = item.get("multi_results", {})
                            if isinstance(multi, dict):
                                sched = (
                                    multi.get("youtube", {}).get("publish_at")
                                    or multi.get("instagram", {}).get("publish_at")
                                    or multi.get("facebook", {}).get("publish_at")
                                )
                        if sched:
                            dt_utc = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                            dt_cet = dt_utc.astimezone(tz_cet)
                            key = dt_cet.strftime("%Y-%m-%d %H:%M")
                            if key not in scheduled:
                                scheduled[key] = {
                                    "title": item.get("title", "Lokalny wpis"),
                                    "video_id": item.get("video_id"),
                                    "source": "local_pub_log",
                                }
                    except Exception:
                        pass
        except Exception as pe:
            print(f"[Scheduling] Warning checking published_videos.jsonl: {pe}")

    # Połącz z bazą kalendarza rezerwacji (publishing_calendar.json)
    cal_path = LOL_AGENT_DIR / "publishing_calendar.json"
    if cal_path.exists():
        import json as _json
        try:
            with open(cal_path, "r", encoding="utf-8") as f:
                cal_db = _json.load(f)
                if isinstance(cal_db, dict):
                    for slot_id, slot in cal_db.items():
                        if isinstance(slot, dict) and slot.get("status") in ("scheduled", "reserved"):
                            dt_utc_str = slot.get("datetime_utc") or slot.get("scheduled_publish_at")
                            if dt_utc_str:
                                dt_utc = datetime.fromisoformat(dt_utc_str.replace("Z", "+00:00"))
                                dt_cet = dt_utc.astimezone(tz_cet)
                                key = dt_cet.strftime("%Y-%m-%d %H:%M")
                                if key not in scheduled:
                                    scheduled[key] = {
                                        "title": slot.get("title", f"Slot {slot_id}"),
                                        "video_id": slot.get("yt_video_id"),
                                        "source": "publishing_calendar",
                                    }
        except Exception as ce:
            print(f"[Scheduling] Warning checking publishing_calendar.json: {ce}")

    # Sprawdź lokalne pliki .meta.json w LOL_TEMP_DIR i LOL_OUTPUT_DIR
    import json as _json
    for search_dir in [LOL_TEMP_DIR, LOL_OUTPUT_DIR]:
        if search_dir.exists():
            for meta_file in search_dir.glob("*.meta.json"):
                try:
                    meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                    sched = meta.get("scheduled_publish_at")
                    if sched:
                        dt_utc = datetime.fromisoformat(sched.replace("Z", "+00:00"))
                        dt_cet = dt_utc.astimezone(tz_cet)
                        key = dt_cet.strftime("%Y-%m-%d %H:%M")
                        if key not in scheduled:
                            scheduled[key] = {
                                "title": meta.get("title", meta_file.name),
                                "video_id": meta.get("youtube_id"),
                                "source": "local_meta",
                            }
                except Exception:
                    pass

    avg_v = round(sum(views_list) / len(views_list)) if views_list else 0
    res_data = {
        "scheduled": scheduled,
        "published": published,
        "avg_views": avg_v,
        "total_published": len(published),
    }
    _PERF_CACHE["timestamp"] = time.time()
    _PERF_CACHE["data"] = res_data
    return res_data



def get_occupied_publish_slots(force_refresh: bool = True) -> Dict[str, Dict[str, Any]]:
    """
    Sprawdza, które sloty publikacji (format 'YYYY-MM-DD HH:MM' CET) są już zajęte.
    Zapewnia pełną świeżość rezerwacji (force_refresh=True).
    """
    sync = get_channel_videos_and_performance(max_results=35, force_refresh=force_refresh)
    return sync["scheduled"]


def get_next_optimal_publish_time() -> Dict[str, Any]:
    """
    Inteligentny dyspozytor harmonogramu (2 Shortsy dziennie, zależnie od dnia tygodnia Pon-Nd).
    Pobiera listę zajętych slotów (z YouTube i lokalnie) oraz tygodniowy rozkład slotów konta/dyrektywy
    i wybiera NAJBLIŻSZY WOLNY SLOT z co najmniej 30-minutowym wyprzedzeniem.
    """
    try:
        from zoneinfo import ZoneInfo
        tz_cet = ZoneInfo("Europe/Warsaw")
    except Exception:
        tz_cet = timezone(timedelta(hours=1))

    now_cet = datetime.now(tz_cet)
    min_lead_time = timedelta(minutes=30)
    cutoff = now_cet + min_lead_time

    weekly_schedule = get_weekly_peak_schedule_cet()
    occupied = get_occupied_publish_slots(force_refresh=True)

    def _slot_label_desc(h_val: int) -> str:
        if h_val < 13:
            return "Poranny / Azja Prime 🌅"
        if h_val < 18:
            return "Afternoon Global Bridge 🔥"
        return "Evening+US Prime Peak ⚡"

    for day_offset in range(14):
        check_date = (now_cet + timedelta(days=day_offset)).date()
        day_slots = get_active_peak_slots_cet(weekday=check_date.weekday())
        for slot in day_slots:
            h, m = map(int, slot.split(":"))
            slot_dt_cet = datetime(check_date.year, check_date.month, check_date.day, h, m, 0, tzinfo=tz_cet)

            if slot_dt_cet <= cutoff:
                continue

            slot_key = slot_dt_cet.strftime("%Y-%m-%d %H:%M")
            if slot_key in occupied:
                continue

            slot_utc = slot_dt_cet.astimezone(timezone.utc)
            iso_utc = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            slot_type = _slot_label_desc(h)
            if day_offset == 0:
                label = f"Dzisiaj o {slot} CET ({slot_type})"
            elif day_offset == 1:
                label = f"Jutro o {slot} CET ({slot_type})"
            elif day_offset == 2:
                label = f"Pojutrze o {slot} CET ({slot_type})"
            else:
                days_pl = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
                weekday = days_pl[slot_dt_cet.weekday()]
                label = f"{weekday}, {slot_dt_cet.strftime('%d.%m')} o {slot} CET ({slot_type})"

            _safe_print(f"[Scheduling] 🎯 Najbliższy wolny slot (Pon-Nd): {label} ({slot_key} CET) | Zajętych slotów: {len(occupied)}")

            return {
                "publish_at": iso_utc,
                "label": label,
                "local_time": slot_key,
                "peak_slots": day_slots,
                "weekday": check_date.weekday(),
                "weekday_schedule": weekly_schedule,
                "occupied_count": len(occupied),
            }

    tomorrow = (now_cet + timedelta(days=1)).date()
    fb_slots = get_active_peak_slots_cet(weekday=tomorrow.weekday())
    fb_slot = fb_slots[0] if fb_slots else "15:00"
    fb_h, fb_m = map(int, fb_slot.split(":"))
    fallback_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day, fb_h, fb_m, 0, tzinfo=tz_cet)
    return {
        "publish_at": fallback_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": f"Jutro o {fb_slot} CET ({_slot_label_desc(fb_h)})",
        "local_time": fallback_dt.strftime("%Y-%m-%d %H:%M"),
        "peak_slots": fb_slots,
        "weekday": tomorrow.weekday(),
        "weekday_schedule": weekly_schedule,
        "occupied_count": len(occupied),
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
    is_short: bool = True,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload wideo na YouTube (Short 9:16 lub Long-Form 16:9 gdy is_short=False) z miniaturką i komentarzem."""
    creds = get_valid_credentials(require_token=True)
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

    import re
    latest_lf_file = LOL_AGENT_DIR / "latest_longform_video.json"
    if is_short:
        # Gwarancja viralowych hashtagów w tytule: #shorts #leagueoflegends #lol
        try:
            from lol_agent.lol_metadata_generator import _format_final_title
        except ImportError:
            from lol_metadata_generator import _format_final_title
        title = _format_final_title(title)

        # Lejek Shorts -> Long-Form w opisie
        try:
            if latest_lf_file.is_file():
                import json as _lfj
                lf_info = _lfj.loads(latest_lf_file.read_text(encoding="utf-8", errors="ignore"))
                lf_url = str(lf_info.get("url") or "").strip()
                if lf_url and lf_url not in description:
                    description = f"{description.strip()}\n\n🎬 Watch Full Weekly Montage: {lf_url}"
        except Exception:
            pass

        # Gwarancja obecności bogatych hashtagów w opisie YouTube Shorts (wyłącznie małe litery)
        description = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", description)
        if "#leagueoflegends" not in description.lower() or description.count("#") < 3:
            try:
                from lol_agent.lol_metadata_generator import _build_hashtags
                extra_tags = _build_hashtags()
            except Exception:
                extra_tags = "#shorts #shortsfeed #leagueoflegends #lol #gaming #lolhighlights"
            description = f"{description.strip()}\n\n{extra_tags}"

        # Gwarancja pełnego zestawu bogatych tagów (max 500 znaków)
        if not tags or len(tags) < 10:
            try:
                from lol_agent.lol_metadata_generator import build_rich_youtube_tags
                tags = build_rich_youtube_tags()
            except Exception:
                pass
    else:
        # Film poziomy Long-Form 16:9: brak #shorts w tytule, opisie i tagach
        title = re.sub(r"\s*#shorts\b", "", str(title or ""), flags=re.IGNORECASE).strip()
        description = re.sub(r"(?<!\w)#shorts(?:feed)?\b", "", str(description or ""), flags=re.IGNORECASE).strip()
        tags = [
            str(t).lstrip("#").strip()
            for t in (tags or [])
            if str(t).strip() and str(t).lstrip("#").strip().lower() not in ("shorts", "shortsfeed")
        ]
        if not tags:
            tags = ["league of legends", "katarina montage", "lol highlights", "best plays"]

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
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
    retry_count = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[YouTube] 🚀 Postęp uploadu: {int(status.progress() * 100)}%")
        except (HttpError, socket.error, TimeoutError) as ex:
            retry_count += 1
            if retry_count > 5:
                raise
            sleep_s = 2 ** retry_count
            print(f"[YouTube] ⚠️ Chwilowy błąd połączenia ({ex}), ponawiam za {sleep_s}s (próba {retry_count}/5)...")
            time.sleep(sleep_s)

    video_id = response["id"]
    print(f"[YouTube] ✅ Wideo wgrane pomyślnie! ID: {video_id}")

    # 1. Automatyczne wgrywanie miniaturki (z retry i zapisem kopii)
    thumb_target = thumbnail_path or str(video_path).replace(".mp4", "_thumb.jpg")
    if Path(thumb_target).exists():
        import shutil
        thumbs_dir = Path(__file__).parent.parent / "thumbnails"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(thumb_target, thumbs_dir / f"{video_id}_thumb.jpg")
            shutil.copy2(thumb_target, Path(__file__).parent.parent / "latest_thumbnail.jpg")
        except Exception:
            pass

        thumb_uploaded = False
        for attempt in range(1, 4):
            try:
                # Sprawdź czy przetwarzanie wideo nie blokuje miniaturki
                v_info = youtube.videos().list(part="status,processingDetails", id=video_id).execute()
                items = v_info.get("items", [])
                if items:
                    p_status = items[0].get("processingDetails", {}).get("processingStatus", "")
                    if p_status == "processing":
                        time.sleep(3)

                thumb_media = MediaFileUpload(str(thumb_target), mimetype="image/jpeg")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media,
                ).execute()
                print(f"[YouTube] ✅ Miniaturka 9:16 wgrana na YouTube (próba {attempt}): {thumb_target}")
                thumb_uploaded = True
                break
            except Exception as te:
                print(f"[YouTube] ⚠️ Próba {attempt}/3 wgrywania miniaturki: {te}")
                time.sleep(4)

        if not thumb_uploaded:
            print(f"[YouTube] ❌ Nie udało się automatycznie wgrać miniaturki po 3 próbach.")

        if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("TESTING") == "true"):
            threading.Thread(
                target=_ensure_youtube_thumbnail_after_processing,
                args=(video_id, str(thumb_target), 35),
                daemon=True,
            ).start()

    # 2. Automatyczne dodawanie przypiętego komentarza pod Shortem
    # YouTube API nie pozwala dodawać komentarzy do filmów ze statusem private/scheduled (błąd 403 commentsDisabled).
    # Dla filmów zaplanowanych komentarz trafia do kolejki (pending_comments.json) i zostanie
    # wysłany automatycznie przez background task, gdy film stanie się publiczny.
    import re
    comment_id = None
    comment_pending = False
    if pinned_comment and pinned_comment.strip():
        clean_comment = re.sub(r'[\ud800-\udfff]', '', pinned_comment.strip())
        is_scheduled = bool(publish_at and publish_at.strip())
        is_live = (not is_scheduled) and (privacy in ("public", "unlisted"))

        if is_live:
            time.sleep(4)
            comment_id = _post_comment_with_retry(youtube, video_id, clean_comment, retries=3)
        else:
            comment_pending = True
            _save_pending_comment(video_id, clean_comment)
            print(f"[YouTube] 📝 Komentarz zapisany do kolejki (film zaplanowany/prywatny) — zostanie opublikowany po upublicznieniu: '{clean_comment[:60]}'")

    invalidate_publish_cache()
    video_url = f"https://www.youtube.com/shorts/{video_id}" if is_short else f"https://www.youtube.com/watch?v={video_id}"

    if not is_short:
        try:
            import json as _lfj
            lf_payload = {
                "video_id": video_id,
                "url": video_url,
                "title": response["snippet"]["title"],
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
            (LOL_AGENT_DIR / "latest_longform_video.json").write_text(
                _lfj.dumps(lf_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
    elif source_path:
        try:
            from lol_agent.viral_vault import stage_short_original
            stage_short_original(
                source_path,
                yt_video_id=video_id,
                metadata={"title": response["snippet"]["title"]},
            )
        except Exception:
            pass

    return {
        "video_id": video_id,
        "url": video_url,
        "video_format": "short" if is_short else "longform",
        "title": response["snippet"]["title"],
        "status": response["status"]["privacyStatus"],
        "publish_at": response["status"].get("publishAt"),
        "comment_id": comment_id,
        "comment_pending": comment_pending,
    }


def get_related_video_studio_links(limit: int = 10) -> Dict[str, Any]:
    """
    Zwraca listę ostatnich Shortsów wraz z linkami 1-klik do YouTube Studio (`Related Video`),
    ponieważ YouTube Data API v3 nie obsługuje programistycznego ustawiania pola Related Video.
    """
    import json as _json
    target = None
    lf_file = LOL_AGENT_DIR / "latest_longform_video.json"
    if lf_file.is_file():
        try:
            target = _json.loads(lf_file.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            target = None

    shorts: List[Dict[str, Any]] = []
    pub_file = LOL_AGENT_DIR / "published_videos.jsonl"
    seen_ids: set[str] = set()
    if pub_file.is_file():
        lines = pub_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            s = line.strip()
            if not s:
                continue
            try:
                rec = _json.loads(s)
            except Exception:
                continue
            vid = str(rec.get("video_id") or "").strip()
            if not vid or vid in seen_ids or rec.get("video_format") == "longform":
                continue
            seen_ids.add(vid)
            shorts.append({
                "video_id": vid,
                "title": str(rec.get("title") or ""),
                "published_at": str(rec.get("timestamp") or rec.get("published_at") or ""),
                "watch_url": f"https://www.youtube.com/shorts/{vid}",
                "studio_edit_url": f"https://studio.youtube.com/video/{vid}/edit",
            })
            if len(shorts) >= int(limit):
                break
    return {
        "target_longform": target,
        "shorts": shorts,
        "api_limitation_note": "YouTube Data API v3 nie wspiera ustawiania Related Video w Shorts — kliknij link Studio Edit, aby przypiąć film 16:9.",
    }


def _post_comment_with_retry(youtube, video_id: str, text: str, retries: int = 3) -> Optional[str]:
    """Próbuje dodać komentarz do filmu z retry (YouTube potrzebuje chwili na propagację)."""
    for attempt in range(retries):
        try:
            comment_res = youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": text}
                        }
                    }
                }
            ).execute()
            cid = comment_res.get("id")
            _safe_print(f"[YouTube] [OK] Komentarz dodany (próba {attempt+1}): '{text[:60]}' (ID: {cid})")
            return cid
        except Exception as ce:
            _safe_print(f"[YouTube] [WARN] Próba {attempt+1}/{retries} komentarza nieudana: {ce}")
            if attempt < retries - 1:
                time.sleep(8)
    _safe_print(f"[YouTube] [ERR] Nie udało się dodać komentarza po {retries} próbach.")
    return None


def _read_pending_comments_queue(queue_path: Path) -> list:
    """Bezpiecznie wczytuje pending_comments.json — odporny na pusty (0 B) lub uszkodzony plik."""
    import json as _json
    if not queue_path.exists():
        return []
    try:
        raw = queue_path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = _json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_pending_comments_queue(queue_path: Path, queue: list) -> None:
    import json as _json
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = queue_path.with_suffix(".json.tmp")
    tmp.write_text(_json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, queue_path)


def _save_pending_comment(video_id: str, text: str) -> None:
    """Zapisuje komentarz do pliku kolejki JSON (do późniejszego wysłania po upublicznieniu)."""
    queue_path = ACCOUNTS_DIR / "pending_comments.json"
    queue = _read_pending_comments_queue(queue_path)
    queue = [item for item in queue if item.get("video_id") != video_id]
    queue.append({"video_id": video_id, "text": text, "created_at": datetime.now(timezone.utc).isoformat()})
    _write_pending_comments_queue(queue_path, queue)


def post_pinned_comment(video_id: str, text: str) -> Dict[str, Any]:
    """
    Dodaj (lub ponów) przypięty komentarz do istniejącego publicznego filmu YouTube.
    Używane po upublicznieniu zaplanowanego Shorta.
    """
    creds = get_valid_credentials(require_token=True)
    youtube = build("youtube", "v3", credentials=creds)
    comment_id = _post_comment_with_retry(youtube, video_id, text, retries=3)
    return {"video_id": video_id, "comment_id": comment_id, "ok": comment_id is not None}


def flush_pending_comments(queue_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Sprawdza kolejkę oczekujących komentarzy i próbuje je dodać do już publicznych filmów.
    Odporna na pusty plik pending_comments.json (0 B).
    """
    q_path = Path(queue_path) if queue_path is not None else (ACCOUNTS_DIR / "pending_comments.json")
    if not q_path.exists():
        return {"sent": [], "still_pending": []}

    queue = _read_pending_comments_queue(q_path)
    if not queue:
        if q_path.read_text(encoding="utf-8", errors="ignore").strip() != "[]":
            _write_pending_comments_queue(q_path, [])
        return {"sent": [], "still_pending": []}

    creds = get_valid_credentials(require_token=False, ignore_refresh_error=True)
    if creds is None:
        return {"sent": [], "still_pending": queue, "error": "Brak tokenu"}
    youtube = build("youtube", "v3", credentials=creds)

    sent = []
    still_pending = []
    for item in queue:
        vid = item["video_id"]
        txt = item["text"]
        try:
            res = youtube.videos().list(part="status", id=vid).execute()
            status = res["items"][0]["status"]["privacyStatus"] if res.get("items") else "unknown"
        except Exception:
            status = "unknown"

        if status == "public":
            try:
                saved_thumb = LOL_AGENT_DIR / "thumbnails" / f"{vid}_thumb.jpg"
                if saved_thumb.is_file():
                    youtube.thumbnails().set(
                        videoId=vid,
                        media_body=MediaFileUpload(str(saved_thumb), mimetype="image/jpeg"),
                    ).execute()
            except Exception:
                pass
            cid = _post_comment_with_retry(youtube, vid, txt, retries=2)
            if cid:
                sent.append({"video_id": vid, "comment_id": cid})
            else:
                still_pending.append(item)
        else:
            still_pending.append(item)

    _write_pending_comments_queue(q_path, still_pending)
    return {"sent": sent, "still_pending": still_pending}


def _load_archive_recipe_context(video_id: str) -> Dict[str, Any]:
    """Wczytuje kontekst klipu z recipes_archive/<video_id>.recipe.json na potrzeby propozycji odpowiedzi."""
    import json as _json
    rec_path = ACCOUNTS_DIR.parent / "lol_agent" / "recipes_archive" / f"{video_id}.recipe.json"
    if not rec_path.exists():
        return {}
    try:
        return _json.loads(rec_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_comment_reply_suggestions(max_videos: int = 5) -> Dict[str, Any]:
    """
    Pobiera ostatnie nieodpowiedziane komentarze widzów na ostatnich filmach kanału
    i przygotowuje 2 bezpieczne propozycje odpowiedzi (merytoryczna + lekki banter),
    do wysyłki po 1 kliknięciu w UI (zero ślepego auto-postowania bota).
    """
    creds = get_valid_credentials(require_token=False, ignore_refresh_error=True)
    if creds is None:
        return {"items": [], "error": "Brak tokenu YouTube"}

    youtube = build("youtube", "v3", credentials=creds)
    ch_res = youtube.channels().list(part="id,contentDetails", mine=True).execute()
    if not ch_res.get("items"):
        return {"items": []}

    my_channel_id = ch_res["items"][0]["id"]
    uploads_pl = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl_res = youtube.playlistItems().list(part="snippet", playlistId=uploads_pl, maxResults=max(1, min(15, max_videos))).execute()

    suggestions = []
    for pl_item in pl_res.get("items", []):
        vid = pl_item["snippet"]["resourceId"]["videoId"]
        title = pl_item["snippet"].get("title", "")
        try:
            threads = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=vid,
                maxResults=10,
                order="time",
            ).execute()
        except Exception:
            continue

        recipe = _load_archive_recipe_context(vid)
        action_type = (recipe.get("action_type") or "outplay").replace("_", " ")

        for th in threads.get("items", []):
            top = th["snippet"]["topLevelComment"]
            top_snip = top["snippet"]
            author_cid = (top_snip.get("authorChannelId") or {}).get("value")
            if author_cid == my_channel_id:
                continue
            replies = (th.get("replies") or {}).get("comments") or []
            if any(((r.get("snippet") or {}).get("authorChannelId") or {}).get("value") == my_channel_id for r in replies):
                continue

            comment_text = (top_snip.get("textDisplay") or top_snip.get("textOriginal") or "").strip()
            author_name = top_snip.get("authorDisplayName", "Viewer")
            if not comment_text:
                continue

            drafts = None
            try:
                from lol_agent.synapsa_engine import generate_with_synapsa
                syn = generate_with_synapsa(
                    "comment_reply",
                    {
                        "video_title": title,
                        "action_type": action_type,
                        "recipe": recipe,
                        "viewer_comment": comment_text,
                        "viewer_author": author_name,
                    },
                    timeout=35,
                )
                if syn and isinstance(syn.get("replies"), list) and syn["replies"]:
                    drafts = [str(r).strip() for r in syn["replies"] if str(r).strip()][:2]
            except Exception:
                drafts = None

            if not drafts:
                drafts = [
                    f"Appreciate it! That {action_type} felt super tight in real time 😅",
                    "Respect! Would you have greed-chased here too or backed off? 👀",
                ]

            suggestions.append({
                "video_id": vid,
                "video_title": title,
                "parent_comment_id": top["id"],
                "author": author_name,
                "comment_text": comment_text,
                "published_at": top_snip.get("publishedAt"),
                "suggested_replies": drafts,
            })

    return {"items": suggestions, "count": len(suggestions)}


def reply_to_youtube_comment(parent_id: str, text: str) -> Dict[str, Any]:
    """Wysyła zatwierdzoną przez użytkownika odpowiedź na komentarz widza."""
    clean_txt = (text or "").strip()
    if not parent_id or not clean_txt:
        raise ValueError("Wymagane parent_id oraz treść odpowiedzi")
    creds = get_valid_credentials(require_token=True)
    youtube = build("youtube", "v3", credentials=creds)
    res = youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": parent_id,
                "textOriginal": clean_txt,
            }
        },
    ).execute()
    return {"ok": True, "comment_id": res.get("id"), "parent_id": parent_id}


