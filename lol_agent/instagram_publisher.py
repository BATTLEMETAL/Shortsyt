"""
Shortsyt — Moduł publikacji na Instagram Reels za pomocą Instagram Graph API.
Obsługuje bezpośredni upload pliku wideo (Resumable Upload na rupload.facebook.com),
status polling kontenera oraz publikację Reels z pełnym error-handlingiem.
"""
import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
INSTAGRAM_TOKEN_PATH = ACCOUNTS_DIR / "instagram_token.json"

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def load_instagram_token() -> Optional[Dict[str, Any]]:
    """Wczytuje token i dane konta Instagram z pliku lub zmiennych środowiskowych."""
    data = {}
    if INSTAGRAM_TOKEN_PATH.exists():
        try:
            data = json.loads(INSTAGRAM_TOKEN_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ Błąd odczytu {INSTAGRAM_TOKEN_PATH}: {e}")

    # Fallback / override ze zmiennych środowiskowych
    access_token = data.get("access_token") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    instagram_account_id = data.get("instagram_account_id") or os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
    page_id = data.get("page_id") or os.getenv("FACEBOOK_PAGE_ID", "").strip()
    username = data.get("username", "")

    if not access_token or not instagram_account_id:
        return None

    return {
        "access_token": access_token,
        "instagram_account_id": instagram_account_id,
        "page_id": page_id,
        "username": username,
        "expires_at": data.get("expires_at", 0)
    }


def get_instagram_token_status() -> Dict[str, Any]:
    """Zwraca czytelny status połączenia konta Instagram."""
    token_data = load_instagram_token()
    if not token_data:
        return {
            "connected": False,
            "valid": False,
            "message": "Brak skonfigurowanego konta Instagram. Wymagana autoryzacja."
        }

    access_token = token_data["access_token"]
    ig_id = token_data["instagram_account_id"]

    try:
        url = f"{GRAPH_API_BASE}/{ig_id}"
        resp = requests.get(
            url,
            params={"fields": "username,name", "access_token": access_token},
            timeout=10
        )
        if resp.status_code == 200:
            res_json = resp.json()
            username = res_json.get("username", token_data.get("username", "nieznany"))
            return {
                "connected": True,
                "valid": True,
                "username": username,
                "instagram_account_id": ig_id,
                "page_id": token_data.get("page_id"),
                "message": f"Konto Instagram połączone (@{username}, ID: {ig_id})"
            }
        else:
            return {
                "connected": True,
                "valid": False,
                "error": resp.text,
                "message": f"Token Instagram nieprawidłowy lub utracił uprawnienia (kod {resp.status_code})"
            }
    except Exception as e:
        return {
            "connected": True,
            "valid": False,
            "error": str(e),
            "message": f"Błąd weryfikacji tokenu Instagram: {e}"
        }


def upload_instagram_reel(
    video_path: str,
    caption: str,
    share_to_feed: bool = True,
    cover_url: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    thumb_offset: Optional[int] = None,
    peak_moment: Optional[float] = None,
    publish_at: Optional[str] = None,
    timeout: int = 300
) -> Dict[str, Any]:
    """
    Publikuje lub planuje plik wideo jako Instagram Reel za pomocą Meta Resumable Upload.
    
    1. Sprawdza planowanie (jeśli publish_at w przyszłości, kolejkuje wpis).
    2. Tworzy kontener medialny (POST /{ig_user_id}/media z upload_type=resumable i thumb_offset).
    3. Wysyła strumień binarny wideo bezpośrednio do rupload.facebook.com.
    4. Monitoruje status przetwarzania wideo (status_code == 'FINISHED').
    5. Publikuje Reel (POST /{ig_user_id}/media_publish).
    6. Pobiera i zwraca permalink opublikowanego Reels.
    """
    vp = Path(video_path)
    if not vp.exists():
        return {"success": False, "error": f"Plik wideo nie istnieje: {video_path}", "platform": "instagram"}

    file_size = vp.stat().st_size
    if file_size == 0:
        return {"success": False, "error": f"Plik wideo jest pusty: {video_path}", "platform": "instagram"}

    # Sprawdzenie planowania w przyszłości
    if publish_at:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            scheduled_ts = int(dt.timestamp())
            if scheduled_ts > int(time.time()) + 600:
                try:
                    from lol_agent.scheduled_queue import queue_scheduled_post
                    queue_scheduled_post(
                        platform="instagram",
                        video_path=str(vp),
                        caption=caption,
                        publish_at=publish_at,
                        thumbnail_path=thumbnail_path,
                        peak_moment=peak_moment
                    )
                    print(f"⏰ Instagram Reel dodany do kolejki planowania na: {dt.isoformat()}")
                    return {
                        "success": True,
                        "platform": "instagram",
                        "is_scheduled": True,
                        "publish_at": publish_at,
                        "message": f"Zaplanowano w kolejce publikacji na {dt.strftime('%Y-%m-%d %H:%M')}"
                    }
                except Exception as _qe:
                    print(f"⚠️ Kolejka planowania Instagram: {_qe}. Kontynuuję natychmiastową publikację.")
        except Exception as _dt_err:
            print(f"⚠️ Błąd parsowania publish_at ({publish_at}): {_dt_err}")

    token_data = load_instagram_token()
    if not token_data:
        return {
            "success": False,
            "error": "Brak konfiguracji konta Instagram w accounts/instagram_token.json lub .env",
            "platform": "instagram"
        }

    access_token = token_data["access_token"]
    ig_id = token_data["instagram_account_id"]

    print(f"📸 Rozpoczynam publikację Reel na Instagram (@{token_data.get('username') or ig_id})...")
    print(f"📦 Rozmiar pliku: {file_size / (1024 * 1024):.2f} MB | {vp.name}")

    # Krok 1: Utworzenie kontenera mediów z automatyczną miniaturą (thumb_offset)
    container_url = f"{GRAPH_API_BASE}/{ig_id}/media"
    container_params: Dict[str, Any] = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "share_to_feed": "true" if share_to_feed else "false",
        "access_token": access_token
    }

    if cover_url:
        container_params["cover_url"] = cover_url
    elif thumb_offset is not None:
        container_params["thumb_offset"] = str(int(thumb_offset))
    elif peak_moment is not None and peak_moment > 0:
        container_params["thumb_offset"] = str(int(peak_moment * 1000))
        print(f"🎯 Automatyczna miniatura IG: ustawiono thumb_offset na moment szczytowy ({int(peak_moment*1000)}ms)")
    else:
        # Domyślny offset 2500ms, aby uniknąć czarnej pierwszej klatki
        container_params["thumb_offset"] = "2500"

    try:
        resp = requests.post(container_url, data=container_params, timeout=30)
        res_json = resp.json()
        if resp.status_code != 200 or "id" not in res_json:
            err = res_json.get("error", {}).get("message", resp.text)
            print(f"❌ Błąd tworzenia kontenera Reel: {err}")
            return {"success": False, "error": f"Błąd tworzenia kontenera: {err}"}

        container_id = res_json["id"]
        upload_uri = res_json.get("uri")
        print(f"✅ Kontener Reel utworzony! ID: {container_id}")
    except Exception as e:
        print(f"❌ Wyjątek podczas tworzenia kontenera Reel: {e}")
        return {"success": False, "error": str(e)}

    # Krok 2: Bezpośredni upload binarny na rupload.facebook.com
    if not upload_uri:
        upload_uri = f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}/{container_id}"

    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }

    print("🚀 Wysyłam dane wideo do rupload.facebook.com...")
    try:
        with open(vp, "rb") as video_file:
            up_resp = requests.post(
                upload_uri,
                headers=upload_headers,
                data=video_file,
                timeout=180
            )

        if up_resp.status_code not in (200, 201):
            print(f"❌ Błąd uploadu binarki do rupload: {up_resp.status_code} {up_resp.text}")
            return {"success": False, "error": f"Błąd uploadu: {up_resp.text}"}

        print("✅ Plik wideo przesłany pomyślnie. Oczekiwanie na przetworzenie przez Instagram...")
    except Exception as e:
        print(f"❌ Wyjątek podczas uploadu pliku: {e}")
        return {"success": False, "error": str(e)}

    # Krok 3: Monitorowanie statusu kontenera
    status_url = f"{GRAPH_API_BASE}/{container_id}"
    start_time = time.time()
    poll_interval = 5

    while time.time() - start_time < timeout:
        try:
            st_resp = requests.get(
                status_url,
                params={"fields": "status_code,status", "access_token": access_token},
                timeout=15
            )
            st_data = st_resp.json()
            status_code = st_data.get("status_code", "").upper()

            if status_code == "FINISHED":
                print("✨ Wideo przetworzone przez Instagram! Gotowe do publikacji.")
                break
            elif status_code in ("ERROR", "EXPIRED"):
                err_msg = st_data.get("status", status_code)
                print(f"❌ Przetwarzanie wideo nie powiodło się: {err_msg}")
                return {"success": False, "error": f"Przetwarzanie kontenera: {err_msg}"}
            elif status_code == "IN_PROGRESS":
                elapsed = int(time.time() - start_time)
                print(f"⏳ Przetwarzanie Reels w toku... ({elapsed}s)")
            else:
                print(f"ℹ️ Status kontenera: {status_code}")
        except Exception as e:
            print(f"⚠️ Ostrzeżenie przy sprawdzaniu statusu: {e}")

        time.sleep(poll_interval)
    else:
        return {"success": False, "error": f"Timeout oczekiwania na przetworzenie wideo ({timeout}s)"}

    # Krok 4: Publikacja kontenera
    publish_url = f"{GRAPH_API_BASE}/{ig_id}/media_publish"
    publish_params = {
        "creation_id": container_id,
        "access_token": access_token
    }

    try:
        pub_resp = requests.post(publish_url, data=publish_params, timeout=30)
        pub_json = pub_resp.json()
        if pub_resp.status_code != 200 or "id" not in pub_json:
            err = pub_json.get("error", {}).get("message", pub_resp.text)
            print(f"❌ Błąd publikacji Reel: {err}")
            return {"success": False, "error": f"Błąd publikacji: {err}"}

        media_id = pub_json["id"]
        print(f"🎉 Instagram Reel opublikowany sukcesem! Media ID: {media_id}")
    except Exception as e:
        print(f"❌ Wyjątek podczas publikacji Reel: {e}")
        return {"success": False, "error": str(e)}

    # Krok 5: Pobranie permalinka
    permalink = None
    try:
        media_url = f"{GRAPH_API_BASE}/{media_id}"
        m_resp = requests.get(
            media_url,
            params={"fields": "permalink", "access_token": access_token},
            timeout=10
        )
        if m_resp.status_code == 200:
            permalink = m_resp.json().get("permalink")
    except Exception:
        pass

    reel_url = permalink or f"https://www.instagram.com/p/{media_id}/"
    print(f"🔗 Link do opublikowanego Reel: {reel_url}")

    return {
        "success": True,
        "media_id": media_id,
        "container_id": container_id,
        "url": reel_url,
        "permalink": reel_url,
        "caption": caption
    }
