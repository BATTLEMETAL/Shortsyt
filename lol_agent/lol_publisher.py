"""
LOL Agent — Publisher YouTube
Publikuje gotowego Shorta na kanał Dwannellenga (LoL)
"""
import os
import sys
import time
import pickle

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import types

# Compatibility shim for older pickled Google Auth tokens
try:
    import google.auth._regional_access_boundary_utils
except ImportError:
    class _DynamicDummyModule(types.ModuleType):
        def __getattr__(self, name):
            class Dummy:
                def __init__(self, *args, **kwargs): pass
                def __setstate__(self, state):
                    if isinstance(state, dict): self.__dict__.update(state)
                def apply_headers(self, headers): pass
                def __getattr__(self, name): return lambda *a, **k: None
            Dummy.__name__ = name
            setattr(self, name, Dummy)
            return Dummy
    sys.modules['google.auth._regional_access_boundary_utils'] = _DynamicDummyModule('google.auth._regional_access_boundary_utils')

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# Dodaj ścieżkę do folderu głównego projektu (żeby znaleźć client_secret.json)
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

try:
    from lol_agent.lol_config import (
        CLIENT_SECRET_PATH, TOKEN_PATH, ACCOUNTS_DIR,
        CHANNEL_PROFILE, YT_CATEGORY_ID, YT_PRIVACY
    )
except ImportError:
    from lol_config import (
        CLIENT_SECRET_PATH, TOKEN_PATH, ACCOUNTS_DIR,
        CHANNEL_PROFILE, YT_CATEGORY_ID, YT_PRIVACY
    )

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
]


def _limit_tags(tags: list) -> list:
    """
    Enforce YouTube's 500-character combined tag limit.
    Also caps at 30 tags. Strips empty tags.
    """
    result = []
    total_chars = 0
    for tag in tags:
        tag = tag.strip()
        if not tag:
            continue
        # Each tag adds its length + 1 (comma separator)
        if total_chars + len(tag) + 1 > 500:
            break
        result.append(tag)
        total_chars += len(tag) + 1
        if len(result) >= 30:
            break
    return result


_LAST_AUTH_PROMPT_TIME = 0.0
_AUTH_PROMPT_COOLDOWN_SEC = 60.0  # Max 1 próba autoryzacji / otwarcie przeglądarki na 60s per proces


def get_lol_youtube_service(allow_interactive: bool = True):
    """
    Autoryzuje i zwraca serwis YouTube API dla kanału LoL (Dwannellenga).
    - allow_interactive=False: tryb cichy (background worker, tracker, watcher) —
      jeśli brak tokenu, natychmiast zwraca None bez otwierania przeglądarki.
    - allow_interactive=True: w interaktywnej konsoli z TTY odpala lokalny serwer OAuth
      (maksymalnie 1 próba na 60s).
    """
    global _LAST_AUTH_PROMPT_TIME
    credentials = None

    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, 'rb') as f:
                credentials = pickle.load(f)
        except Exception as load_err:
            print(f"⚠️  Błąd odczytu tokenu LoL ({load_err}) — usuwam uszkodzony plik...")
            if os.path.exists(TOKEN_PATH):
                try:
                    os.remove(TOKEN_PATH)
                except OSError:
                    pass
            credentials = None

    if credentials and not credentials.valid:
        if credentials.expired and credentials.refresh_token:
            print("🔄 Odświeżam token LoL...")
            try:
                credentials.refresh(Request())
                os.makedirs(ACCOUNTS_DIR, exist_ok=True)
                with open(TOKEN_PATH, 'wb') as f:
                    pickle.dump(credentials, f)
                print(f"✅ Token LoL odświeżony pomyślnie: {TOKEN_PATH}", flush=True)
            except Exception as refresh_err:
                print(f"⚠️  Token nieważny ({refresh_err}) — wymagana nowa autoryzacja.")
                if os.path.exists(TOKEN_PATH):
                    try:
                        os.remove(TOKEN_PATH)
                    except OSError:
                        pass
                credentials = None
        else:
            credentials = None

    if not credentials or not credentials.valid:
        # 1. Guard trybu nieinteraktywnego (background tracker, scheduler, watcher, API loop)
        if not allow_interactive:
            return None

        # 2. Guard środowiska tty (nie można autoryzować interaktywnie w procesach w tle / GUI)
        import sys
        if not (sys.stdin and sys.stdin.isatty()):
            print("⚠️  [OAuth] Wymagana autoryzacja YouTube, ale proces działa w trybie nieinteraktywnym (brak TTY).", flush=True)
            print("    Uruchom w terminalu: python run_lol_agent.py --authorize lub autoryzuj w Shortsyt Studio Desktop.", flush=True)
            return None

        # 3. Guard częstotliwości (Antispam: max 1 otwarcie przeglądarki na 60 sekund w całym procesie)
        now = time.time()
        if (now - _LAST_AUTH_PROMPT_TIME) < _AUTH_PROMPT_COOLDOWN_SEC:
            print(f"⚠️  [OAuth] Przeglądarka została już otwarta w ciągu ostatnich {_AUTH_PROMPT_COOLDOWN_SEC:.0f}s. Pomijam ponowne otwieranie.", flush=True)
            return None

        _LAST_AUTH_PROMPT_TIME = now

        print(f"🌐 Inicjalizuję autoryzację YouTube OAuth...", flush=True)
        if not os.path.exists(CLIENT_SECRET_PATH):
            raise FileNotFoundError(
                f"Brak pliku client_secret.json: {CLIENT_SECRET_PATH}\n"
                "Pobierz go z Google Cloud Console."
            )

        os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_PATH, SCOPES
            )
            print("🌐 Otwieram przeglądarkę do logowania OAuth (port localhost)...", flush=True)
            credentials = flow.run_local_server(port=0, prompt='consent select_account')
        except Exception as flow_err:
            print(f"❌ [OAuth] Błąd autoryzacji: {flow_err}", flush=True)
            return None

        if credentials:
            os.makedirs(ACCOUNTS_DIR, exist_ok=True)
            with open(TOKEN_PATH, 'wb') as f:
                pickle.dump(credentials, f)
            print(f"✅ Token LoL zapisany: {TOKEN_PATH}", flush=True)

    if not credentials or not credentials.valid:
        return None

    return build('youtube', 'v3', credentials=credentials)


from datetime import datetime, timezone, timedelta
from typing import Optional, Union, Dict, List, Tuple


def parse_schedule_time(schedule_str: str) -> Tuple[str, str]:
    """
    Parsuje czas publikacji do formatu RFC3339 UTC dla YouTube API.
    Obsługuje:
      - 'morning' / 'rano' -> 08:30 (najbliższe)
      - 'evening' / 'wieczor' / 'wieczór' -> 18:00 (najbliższe)
      - 'HH:MM' (np. '18:00', '08:30') -> najbliższe wystąpienie tej godziny
      - 'YYYY-MM-DDTHH:MM:SS' -> dokładny czas ISO
    Zwraca: (rfc3339_utc_str, human_readable_local_str)
    """
    now = datetime.now()
    schedule_lower = schedule_str.strip().lower()

    target_hour = None
    target_minute = 0
    target_date = now.date()

    if schedule_lower in ("morning", "rano", "poranek"):
        target_hour = 8
        target_minute = 30
    elif schedule_lower in ("evening", "wieczor", "wieczór"):
        target_hour = 18
        target_minute = 0
    elif ":" in schedule_lower and len(schedule_lower.split(":")) == 2:
        parts = schedule_lower.split(":")
        target_hour = int(parts[0])
        target_minute = int(parts[1])
    else:
        try:
            dt = datetime.fromisoformat(schedule_str)
            if dt.tzinfo is None:
                dt = dt.astimezone()
            utc_dt = dt.astimezone(timezone.utc)
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            raise ValueError(f"Nieznany format planowania czasu: '{schedule_str}'. Użyj np. '18:00', 'morning', 'evening' lub '2026-08-24T18:00:00'")

    target_dt = datetime(target_date.year, target_date.month, target_date.day, target_hour, target_minute)
    # Jeśli czas już minął dzisiaj (z marginesem 10 minut), przenieś na jutro
    if target_dt <= now + timedelta(minutes=10):
        target_dt += timedelta(days=1)

    local_dt = target_dt.astimezone()
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), local_dt.strftime("%Y-%m-%d %H:%M")


def upload_lol_short(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy: str = YT_PRIVACY,
    thumbnail_path: str = None,
    category_id: str = YT_CATEGORY_ID,
    publish_at: Optional[str] = None,
    pinned_comment: Optional[str] = None,
) -> dict:
    """
    Uploaduje Shorta LoL na YouTube.
    Zwraca dict z video_id i url.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Brak pliku wideo: {video_path}")

    print(f"\n🚀 Uploading na YouTube...")
    print(f"   📹 Plik: {os.path.basename(video_path)}")
    print(f"   📌 Tytuł: {title[:60]}...")

    youtube = get_lol_youtube_service()

    # Gwarantuj pełny zestaw viralowych tagów w tytule przed wysłaniem do YouTube API (wyłącznie małe litery)
    try:
        from lol_agent.lol_metadata_generator import _format_final_title
    except ImportError:
        from lol_metadata_generator import _format_final_title
    title = _format_final_title(title)

    # Normalizuj wszystkie hasztagi w opisie do małych liter
    import re
    description = re.sub(r'#([a-zA-Z0-9_]+)', lambda m: f"#{m.group(1).lower()}", description)

    # Gwarantuj bogate tagi (max 500 znaków) jeśli lista jest zbyt krótka
    if not tags or len(tags) < 10:
        try:
            from lol_agent.lol_metadata_generator import build_rich_youtube_tags
            tags = build_rich_youtube_tags()
        except Exception:
            pass

    status_dict = {
        "selfDeclaredMadeForKids": False,
    }

    if publish_at:
        rfc_time, human_time = parse_schedule_time(publish_at)
        status_dict["privacyStatus"] = "private"
        status_dict["publishAt"] = rfc_time
        print(f"   📅 Zaplanowano publikację na: {human_time} (UTC: {rfc_time})")
    else:
        status_dict["privacyStatus"] = privacy
        print(f"   🔒 Privacy: {privacy}")

    body = {
        "snippet": {
            "title": title[:100],  # Max 100 znaków
            "description": description[:5000],  # Max 5000
            "tags": _limit_tags(tags),  # Max 500 chars combined
            "categoryId": category_id,
        },
        "status": status_dict
    }

    media = MediaFileUpload(
        video_path,
        chunksize=4 * 1024 * 1024,  # 4MB chunks
        resumable=True,
        mimetype="video/mp4"
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    print("   ⏳ Uploading", end="", flush=True)

    retry_count = 0
    max_retries = 3
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"\r   ⏳ Uploading: {pct}%", end="", flush=True)
            retry_count = 0
        except Exception as exc:
            http_code = getattr(exc, "resp", None)
            code = getattr(http_code, "status", None) if http_code is not None else None
            # Retry on 5xx or connection error
            if (code is None or str(code) in ("500", "502", "503", "504")) and retry_count < max_retries:
                retry_count += 1
                wait_sec = 2 ** retry_count
                print(f"\n   ⚠️ Błąd przejściowy uploadu ({code or exc}), ponawiam za {wait_sec}s (próba {retry_count}/{max_retries})...")
                time.sleep(wait_sec)
                continue

            if str(code) == "409":
                raise RuntimeError(
                    "YouTube odrzucił upload (409 alreadyExists) — "
                    "ten klip był już uploadowany zbyt wiele razy z tego samego pliku. "
                    "Użyj nowego klipu lub odczekaj 24h."
                ) from exc
            elif str(code) == "403":
                raise RuntimeError(
                    f"YouTube odrzucił upload (403 Forbidden) — "
                    f"sprawdź uprawnienia konta / OAuth scope. Szczegóły: {exc}"
                ) from exc
            else:
                raise RuntimeError(f"Upload error ({code}): {exc}") from exc

    print()
    video_id = response.get("id", "")
    video_url = f"https://www.youtube.com/shorts/{video_id}"

    print(f"\n✅ SHORT OPUBLIKOWANY!")
    print(f"   🎮 Video ID: {video_id}")
    print(f"   🔗 URL: {video_url}")

    # Thumbnail — Robust Upload & Verification
    if thumbnail_path and os.path.exists(thumbnail_path):
        import shutil
        import time

        # Zapisz kopię w katalogu thumbnails/ oraz latest_thumbnail.jpg
        thumbs_dir = os.path.join(os.path.dirname(_HERE), "thumbnails")
        os.makedirs(thumbs_dir, exist_ok=True)
        dest_thumb = os.path.join(thumbs_dir, f"{video_id}_thumb.jpg")
        try:
            shutil.copy2(thumbnail_path, dest_thumb)
            shutil.copy2(thumbnail_path, os.path.join(os.path.dirname(_HERE), "latest_thumbnail.jpg"))
        except Exception:
            pass

        # Odczekaj na zaindeksowanie wideo przez YouTube, aby procesor Google nie nadpisał miniaturki domyślną klatką
        print(f"   🖼️  Wgrywam miniaturkę do YouTube (weryfikacja gotowości wideo)...")
        thumb_uploaded = False
        for attempt in range(1, 4):
            try:
                # Sprawdź stan przetwarzania wideo
                v_info = youtube.videos().list(part="status,processingDetails", id=video_id).execute()
                items = v_info.get("items", [])
                if items:
                    p_details = items[0].get("processingDetails", {})
                    p_status = p_details.get("processingStatus", "")
                    if p_status == "processing":
                        time.sleep(3)

                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                ).execute()
                print(f"   ✅ Miniaturka 9:16 pomyślnie wgrana i ustawiona na YouTube (próba {attempt})!")
                thumb_uploaded = True
                break
            except Exception as e:
                print(f"   ⚠️  Próba {attempt}/3 wgrywania miniaturki: {e}")
                time.sleep(4)

        if not thumb_uploaded:
            print(f"   ❌ Nie udało się automatycznie wgrać miniaturki po 3 próbach. Plik lokalny: {dest_thumb}")

    if pinned_comment and video_id:
        try:
            print(f"   💬 Dodawanie i przypinanie komentarza na YouTube...")
            post_pinned_comment(youtube, video_id, pinned_comment)
        except Exception as comment_err:
            print(f"   ⚠️ Nie udało się dodać przypiętego komentarza: {comment_err}")

    return {
        "video_id": video_id,
        "url": video_url,
        "title": title,
    }


def post_pinned_comment(youtube, video_id: str, comment_text: str) -> bool:
    """
    Dodaje i przypina komentarz pod filmem.
    Musi byc wywolane krotko po uploadzie (token musi miec scope youtube.force-ssl).
    """
    import re
    try:
        # Usuń niedozwolone znaki surrogate
        comment_text = re.sub(r'[\ud800-\udfff]', '', comment_text)
        # Stworz watek komentarza
        thread = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
        ).execute()

        comment_id = thread["snippet"]["topLevelComment"]["id"]

        # Przypin komentarz (wymaga wlasciciela kanalu)
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus="published",
        ).execute()

        print(f"   📌 Przypiety komentarz: '{comment_text[:60]}...'")
        return True

    except Exception as e:
        print(f"   ⚠️  Pinned comment error: {e}")
        return False


if __name__ == "__main__":
    # Test autoryzacji
    print("\ud83d\udd10 Test autoryzacji kanalu LoL (Dwannellenga)...")
    try:
        service = get_lol_youtube_service()
        channels = service.channels().list(part="snippet", mine=True).execute()
        for ch in channels.get("items", []):
            print(f"\u2705 Polaczono z kanalem: {ch['snippet']['title']}")
    except Exception as e:
        print(f"\u274c Blad: {e}")

