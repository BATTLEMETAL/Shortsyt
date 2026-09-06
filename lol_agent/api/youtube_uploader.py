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


# ── Harmonogram Publikacji: 2 Shortsy dziennie (Morning Peak 08:30 + Evening Peak 18:30 CET) ──
DAILY_PEAK_SLOTS_CET = ["08:30", "18:30"]


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


_PERF_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": None}


def get_channel_videos_and_performance(max_results: int = 50, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Pobiera z YouTube API:
    1. Zaplanowane filmy (do obsadzenia w przyszłych slotach ze statusem 'scheduled')
    2. Opublikowane filmy z historycznymi statystykami (wyświetlenia, polubienia, komentarze)
    3. Wskaźnik skuteczności (Performance Score) każdego opublikowanego Shorta w relacji do średniej kanału.
    Zoptymalizowane: 60s TTL cache chroni limit quota i gwarantuje czas odpowiedzi < 1ms.
    """
    global _PERF_CACHE
    now_ts = time.time()
    if not force_refresh and _PERF_CACHE["data"] is not None and (now_ts - _PERF_CACHE["timestamp"] < 60.0):
        return _PERF_CACHE["data"]

    try:
        from zoneinfo import ZoneInfo

        tz_cet = ZoneInfo("Europe/Warsaw")
    except Exception:
        tz_cet = timezone(timedelta(hours=2))

    scheduled: Dict[str, Dict[str, Any]] = {}
    published: List[Dict[str, Any]] = []
    views_list: List[int] = []

    try:
        creds = _load_credentials()
        if creds:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    _save_credentials(creds)
                except Exception:
                    pass
            youtube = build("youtube", "v3", credentials=creds)
            ch = youtube.channels().list(part="contentDetails", mine=True).execute()
            uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            pl = youtube.playlistItems().list(part="snippet,status", playlistId=uploads_id, maxResults=max_results).execute()
            vids = [item["snippet"]["resourceId"]["videoId"] for item in pl.get("items", [])]
            if vids:
                v_res = youtube.videos().list(part="snippet,status,statistics,contentDetails", id=",".join(vids)).execute()
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

                for v in v_res.get("items", []):
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
                            raw_published.append({
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
                            })

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



def get_occupied_publish_slots() -> Dict[str, Dict[str, Any]]:
    """
    Sprawdza, które sloty publikacji (format 'YYYY-MM-DD HH:MM' CET) są już zajęte.
    """
    sync = get_channel_videos_and_performance(max_results=35)
    return sync["scheduled"]


def get_next_optimal_publish_time() -> Dict[str, Any]:
    """
    Inteligentny dyspozytor harmonogramu (2 Shortsy dziennie: 08:30 i 18:30 CET).
    Pobiera listę zajętych slotów (z YouTube i lokalnie) i wybiera NAJBLIŻSZY WOLNY SLOT.
    Jeśli dzisiejsze sloty minęły lub są już zajęte, automatycznie przeskakuje na:
      - Jutro o 08:30 CET (Morning Peak 🌅)
      - Jutro o 18:30 CET (Evening Peak ⚡)
      - Kolejne wolne dni w przód (Pojutrze itd.)
    Gwarantuje brak nakładania się filmów na ten sam slot.
    """
    try:
        from zoneinfo import ZoneInfo
        tz_cet = ZoneInfo("Europe/Warsaw")
    except Exception:
        tz_cet = timezone(timedelta(hours=2))

    now_cet = datetime.now(tz_cet)
    # Bufor bezpieczeństwa: slot musi być co najmniej 30 minut w przyszłości
    min_lead_time = timedelta(minutes=30)
    cutoff = now_cet + min_lead_time

    # Pobierz aktualne zajęte sloty
    occupied = get_occupied_publish_slots()

    # Szukaj najbliższego wolnego slotu przez kolejne 14 dni
    for day_offset in range(14):
        check_date = (now_cet + timedelta(days=day_offset)).date()
        for slot in DAILY_PEAK_SLOTS_CET:
            h, m = map(int, slot.split(":"))
            slot_dt_cet = datetime(check_date.year, check_date.month, check_date.day, h, m, 0, tzinfo=tz_cet)

            # Czy slot jest wystarczająco w przyszłości?
            if slot_dt_cet <= cutoff:
                continue

            slot_key = slot_dt_cet.strftime("%Y-%m-%d %H:%M")
            # Czy slot jest już zajęty przez inny film?
            if slot_key in occupied:
                continue

            # Znaleziono pierwszy wolny slot!
            slot_utc = slot_dt_cet.astimezone(timezone.utc)
            iso_utc = slot_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            slot_type = "Morning Peak 🌅" if h < 12 else "Evening Peak ⚡"
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

            print(f"[Scheduling] 🎯 Najbliższy wolny slot (2x/dzień): {label} ({slot_key} CET) | Zajętych slotów: {len(occupied)}")

            return {
                "publish_at": iso_utc,
                "label": label,
                "local_time": slot_key,
                "peak_slots": DAILY_PEAK_SLOTS_CET,
                "occupied_count": len(occupied),
            }

    # Fallback awaryjny
    fallback_dt = (now_cet + timedelta(days=1)).replace(hour=8, minute=30, second=0)
    return {
        "publish_at": fallback_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label": "Jutro o 08:30 CET (Morning Peak 🌅)",
        "local_time": fallback_dt.strftime("%Y-%m-%d %H:%M"),
        "peak_slots": DAILY_PEAK_SLOTS_CET,
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

    # Dodaj hashtag #Shorts jeśli go brakuje (algorytm YouTube Shorts tego wymaga)
    if "#shorts" not in title.lower():
        if len(title) + 8 <= 100:
            title = f"{title} #Shorts"

    # Gwarancja obecności bogatych hashtagów w opisie YouTube Shorts
    if "#leagueoflegends" not in description.lower() or description.count("#") < 3:
        try:
            from lol_agent.lol_metadata_generator import _build_hashtags
            extra_tags = _build_hashtags()
        except Exception:
            extra_tags = "#Shorts #LeagueOfLegends #LoL #Gaming #LoLHighlights #LoLShorts"
        description = f"{description.strip()}\n\n{extra_tags}"

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
    while response is None:
        status, response = request.next_chunk()

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

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/shorts/{video_id}",
        "title": response["snippet"]["title"],
        "status": response["status"]["privacyStatus"],
        "publish_at": response["status"].get("publishAt"),
        "comment_id": comment_id,
        "comment_pending": comment_pending,
    }


def _safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass


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


def _save_pending_comment(video_id: str, text: str) -> None:
    """Zapisuje komentarz do pliku kolejki JSON (do późniejszego wysłania po upublicznieniu)."""
    import json as _json
    queue_path = ACCOUNTS_DIR / "pending_comments.json"
    queue: list = []
    if queue_path.exists():
        try:
            queue = _json.loads(queue_path.read_text(encoding="utf-8"))
        except Exception:
            queue = []
    queue.append({"video_id": video_id, "text": text, "created_at": datetime.now(timezone.utc).isoformat()})
    queue_path.write_text(_json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def post_pinned_comment(video_id: str, text: str) -> Dict[str, Any]:
    """
    Dodaj (lub ponów) przypięty komentarz do istniejącego publicznego filmu YouTube.
    Używane po upublicznieniu zaplanowanego Shorta.
    """
    creds = _load_credentials()
    if creds is None:
        raise ValueError("Brak tokenu YouTube — wymagana autoryzacja")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    youtube = build("youtube", "v3", credentials=creds)
    comment_id = _post_comment_with_retry(youtube, video_id, text, retries=3)
    return {"video_id": video_id, "comment_id": comment_id, "ok": comment_id is not None}


def flush_pending_comments() -> Dict[str, Any]:
    """
    Sprawdza kolejkę oczekujących komentarzy i próbuje je dodać do już publicznych filmów.
    Wywołaj ręcznie lub automatycznie po upublicznieniu zaplanowanego Shorta.
    Zwraca: {"sent": [...], "still_pending": [...]}
    """
    import json as _json
    queue_path = ACCOUNTS_DIR / "pending_comments.json"
    if not queue_path.exists():
        return {"sent": [], "still_pending": []}

    queue: list = _json.loads(queue_path.read_text(encoding="utf-8"))
    if not queue:
        return {"sent": [], "still_pending": []}

    creds = _load_credentials()
    if creds is None:
        return {"sent": [], "still_pending": queue, "error": "Brak tokenu"}
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    youtube = build("youtube", "v3", credentials=creds)

    sent = []
    still_pending = []
    for item in queue:
        vid = item["video_id"]
        txt = item["text"]
        # Sprawdź czy film jest już publiczny
        try:
            res = youtube.videos().list(part="status", id=vid).execute()
            status = res["items"][0]["status"]["privacyStatus"] if res.get("items") else "unknown"
        except Exception:
            status = "unknown"

        if status == "public":
            cid = _post_comment_with_retry(youtube, vid, txt, retries=2)
            if cid:
                sent.append({"video_id": vid, "comment_id": cid})
            else:
                still_pending.append(item)
        else:
            still_pending.append(item)

    # Zapisz tylko te które nadal czekają
    queue_path.write_text(_json.dumps(still_pending, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"sent": sent, "still_pending": still_pending}

