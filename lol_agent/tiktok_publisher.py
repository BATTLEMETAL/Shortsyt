"""
Shortsyt — Moduł publikacji na TikTok za pomocą Content Posting API v2.
Obsługuje bezpośredni upload pliku wideo (Direct Post / FILE_UPLOAD),
chunking, odświeżanie tokenów OAuth oraz monitorowanie statusu publikacji.
"""
import os
import sys
import time
import json
import math
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
TIKTOK_TOKEN_PATH = ACCOUNTS_DIR / "tiktok_token.json"

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
TIKTOK_INIT_URL = f"{TIKTOK_API_BASE}/post/publish/video/init/"
TIKTOK_INBOX_URL = f"{TIKTOK_API_BASE}/post/publish/inbox/video/init/"
TIKTOK_STATUS_URL = f"{TIKTOK_API_BASE}/post/publish/status/fetch/"
TIKTOK_TOKEN_URL = f"{TIKTOK_API_BASE}/oauth/token/"

CHUNK_SIZE = 10 * 1024 * 1024  # 10MB chunk


def load_tiktok_token() -> Optional[Dict[str, Any]]:
    """Wczytuje token TikToka z pliku. Jeśli zbliża się wygaśnięcie (< 1h), odświeża go."""
    if not TIKTOK_TOKEN_PATH.exists():
        return None

    try:
        data = json.loads(TIKTOK_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Błąd odczytu {TIKTOK_TOKEN_PATH}: {e}")
        return None

    now = int(time.time())
    expires_at = data.get("expires_at", 0)

    # Odśwież, jeśli pozostała mniej niż godzina do wygaśnięcia access_tokena
    if expires_at - now < 3600 and data.get("refresh_token"):
        print("🔄 Odświeżam token dostępu TikTok...")
        refreshed = refresh_tiktok_token(data)
        if refreshed:
            return refreshed

    return data


def refresh_tiktok_token(token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Odświeża access_token TikToka za pomocą refresh_tokena."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print("❌ Brak refresh_token dla TikToka")
        return None

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    data = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    try:
        resp = requests.post(TIKTOK_TOKEN_URL, headers=headers, data=data, timeout=30)
        res_json = resp.json()
        if "access_token" in res_json:
            now = int(time.time())
            token_data["access_token"] = res_json["access_token"]
            token_data["refresh_token"] = res_json.get("refresh_token", refresh_token)
            token_data["expires_at"] = now + res_json.get("expires_in", 86400)
            token_data["refresh_expires_at"] = now + res_json.get("refresh_expires_in", 31536000)

            ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
            TIKTOK_TOKEN_PATH.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
            print("✅ Token TikTok został pomyślnie odświeżony!")
            return token_data
        else:
            print(f"⚠️ Nie udało się odświeżyć tokenu TikTok: {res_json}")
            return None
    except Exception as e:
        print(f"❌ Błąd sieci podczas odświeżania tokenu TikTok: {e}")
        return None


def get_tiktok_token_status() -> Dict[str, Any]:
    """Zwraca czytelny status połączenia konta TikTok."""
    token = load_tiktok_token()
    if not token or not token.get("access_token"):
        return {
            "connected": False,
            "valid": False,
            "message": "Brak połączonego konta TikTok. Wymagana autoryzacja."
        }

    now = int(time.time())
    expires_at = token.get("expires_at", 0)
    refresh_expires_at = token.get("refresh_expires_at", 0)
    is_valid = expires_at > now or refresh_expires_at > now

    days_left = max(0, int((refresh_expires_at - now) / 86400))

    return {
        "connected": True,
        "valid": is_valid,
        "open_id": token.get("open_id"),
        "scope": token.get("scope"),
        "expires_in_hours": max(0, int((expires_at - now) / 3600)),
        "refresh_expires_in_days": days_left,
        "message": f"Konto TikTok połączone (ważność tokenu odświeżania: {days_left} dni)"
    }


def upload_tiktok_short(
    video_path: str,
    title: str,
    hashtags: Optional[List[str]] = None,
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    disable_duet: bool = False,
    disable_comment: bool = False,
    disable_stitch: bool = False,
    video_cover_timestamp_ms: int = 1000,
    publish_at: Optional[str] = None,
    thumbnail_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Publikuje plik wideo na TikTok przez Content Posting API v2.
    video_path: ścieżka do lokalnego pliku MP4
    title: tytuł / opis filmu (max 2200 znaków)
    """
    vp = Path(video_path)
    if not vp.exists():
        return {"success": False, "error": f"Plik wideo nie istnieje: {video_path}"}

    # Obsługa planowania publikacji w przyszłości
    if publish_at:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            scheduled_ts = int(dt.timestamp())
            if scheduled_ts > int(time.time()) + 600:
                try:
                    from lol_agent.scheduled_queue import queue_scheduled_post
                    queue_scheduled_post(
                        platform="tiktok",
                        video_path=str(vp),
                        caption=title,
                        publish_at=publish_at,
                        thumbnail_path=thumbnail_path,
                        extra={
                            "hashtags": hashtags,
                            "privacy_level": privacy_level,
                            "video_cover_timestamp_ms": video_cover_timestamp_ms
                        }
                    )
                    print(f"⏰ TikTok Short dodany do kolejki planowania na: {dt.isoformat()}")
                    return {
                        "success": True,
                        "platform": "tiktok",
                        "is_scheduled": True,
                        "publish_at": publish_at,
                        "message": f"Zaplanowano w kolejce publikacji na {dt.strftime('%Y-%m-%d %H:%M')}"
                    }
                except Exception as _qe:
                    print(f"⚠️ Kolejka planowania TikTok: {_qe}. Kontynuuję natychmiastową publikację.")
        except Exception as _dt_err:
            print(f"⚠️ Błąd parsowania publish_at ({publish_at}): {_dt_err}")

    token_data = load_tiktok_token()
    if not token_data or not token_data.get("access_token"):
        return {
            "success": False,
            "error": "Brak ważnego tokenu TikTok. Uruchom scripts/authorize_tiktok.py."
        }

    access_token = token_data["access_token"]
    file_size = vp.stat().st_size

    # Łączenie tytułu z hashtagami
    full_title = title.strip()
    if hashtags:
        tags_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t)
        if tags_str:
            full_title = f"{full_title} {tags_str}".strip()

    # TikTok ogranicza tytuł do 2200 znaków
    full_title = full_title[:2200]

    # TikTok API v2 Direct Post chunk calculations:
    # 1. If file_size <= 64MB: single chunk upload where chunk_size == file_size and total_chunks == 1
    # 2. If file_size > 64MB: chunk_size between 5MB and 64MB; total_chunks MUST be math.floor(file_size / chunk_size),
    #    and the final chunk absorbs any trailing bytes.
    max_single_chunk = 64 * 1024 * 1024
    if file_size <= max_single_chunk:
        chunk_size = file_size
        total_chunks = 1
    else:
        chunk_size = CHUNK_SIZE
        total_chunks = max(1, math.floor(file_size / chunk_size))

    print(f"\n🚀 Inicjalizacja uploadu na TikTok...")
    print(f"   📹 Plik: {vp.name} ({file_size / (1024*1024):.1f} MB, {total_chunks} chunków)")
    print(f"   📌 Tytuł: {full_title[:60]}...")

    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }

    init_payload = {
        "post_info": {
            "title": full_title,
            "privacy_level": privacy_level,
            "disable_duet": disable_duet,
            "disable_comment": disable_comment,
            "disable_stitch": disable_stitch,
            "video_cover_timestamp_ms": video_cover_timestamp_ms
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks
        }
    }

    try:
        init_res = requests.post(TIKTOK_INIT_URL, headers=init_headers, json=init_payload, timeout=30)
        init_data = init_res.json()
    except Exception as e:
        return {"success": False, "error": f"Błąd połączenia z TikTok API: {e}"}

    data_block = init_data.get("data", {})
    publish_id = data_block.get("publish_id")
    upload_url = data_block.get("upload_url")

    # Obsługa trybu Sandbox / niezatwierdzonej aplikacji:
    # TikTok w Sandboxie nie pozwala na PUBLIC_TO_EVERYONE i wymaga SELF_ONLY (film prywatny na Twoim profilu)
    if (not upload_url or not publish_id) and init_payload["post_info"]["privacy_level"] != "SELF_ONLY":
        err_code = init_data.get("error", {}).get("code", "")
        err_msg = str(init_data.get("error", {}).get("message", "")).lower()
        if "unaudited" in err_msg or "private" in err_msg or "privacy" in err_msg or "scope" in err_msg:
            print("   ℹ️ [Sandbox] Wykryto ograniczenie widoczności TikToka — ponawiam jako SELF_ONLY...")
            init_payload["post_info"]["privacy_level"] = "SELF_ONLY"
            try:
                init_res = requests.post(TIKTOK_INIT_URL, headers=init_headers, json=init_payload, timeout=30)
                init_data = init_res.json()
                data_block = init_data.get("data", {})
                publish_id = data_block.get("publish_id")
                upload_url = data_block.get("upload_url")
            except Exception as e:
                return {"success": False, "error": f"Błąd ponownego połączenia z TikTok API: {e}"}

    is_inbox_mode = False
    if not upload_url or not publish_id:
        print("   ℹ️ [TikTok] Direct Post wymaga audytu profilu publicznego — przełączam na Share to TikTok (Inbox/Drafts)...", flush=True)
        inbox_payload = {
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks
            }
        }
        try:
            inbox_res = requests.post(TIKTOK_INBOX_URL, headers=init_headers, json=inbox_payload, timeout=30)
            inbox_data = inbox_res.json()
            data_block = inbox_data.get("data", {})
            publish_id = data_block.get("publish_id")
            upload_url = data_block.get("upload_url")
            is_inbox_mode = True
        except Exception as e:
            return {"success": False, "error": f"Błąd połączenia z TikTok Inbox API: {e}"}

    if not upload_url or not publish_id:
        error_msg = init_data.get("error", {}).get("message") or str(init_data)
        return {"success": False, "error": f"TikTok API odmówił uploadu: {error_msg}"}

    print(f"   🔑 Publish ID: {publish_id}")
    print(f"   ⏳ Wysyłanie chunków do TikTok...", flush=True)

    # Wysyłanie chunków pliku wideo
    with open(vp, "rb") as f:
        for chunk_idx in range(total_chunks):
            if chunk_idx == total_chunks - 1:
                chunk_data = f.read()  # Absorbuje wszystkie pozostałe bajty do końca pliku
            else:
                chunk_data = f.read(chunk_size)
            chunk_len = len(chunk_data)
            start_byte = chunk_idx * chunk_size
            end_byte = start_byte + chunk_len - 1

            chunk_headers = {
                "Content-Type": "video/mp4",
                "Content-Length": str(chunk_len),
                "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}"
            }

            for attempt in range(1, 4):
                try:
                    put_res = requests.put(upload_url, headers=chunk_headers, data=chunk_data, timeout=60)
                    if put_res.status_code in (200, 201, 206):
                        pct = int((end_byte + 1) / file_size * 100)
                        print(f"\r   ⏳ Wysyłanie TikTok: {pct}% (chunk {chunk_idx + 1}/{total_chunks})", end="", flush=True)
                        break
                    else:
                        print(f"\n   ⚠️ Błąd wysyłania chunka ({put_res.status_code}), próba {attempt}/3...")
                        time.sleep(2 * attempt)
                except Exception as ex:
                    print(f"\n   ⚠️ Wyjątek sieciowy podczas wysyłania chunka: {ex}, próba {attempt}/3...")
                    time.sleep(2 * attempt)
            else:
                return {"success": False, "error": f"Nie udało się wysłać chunka {chunk_idx} po 3 próbach."}

    print(f"\n   ✅ Wszystkie chunki wysłane! Oczekiwanie na przetworzenie przez TikTok...")

    # Sprawdzanie statusu przetwarzania (polling)
    status_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    status_payload = {"publish_id": publish_id}

    for poll_idx in range(15):
        time.sleep(4)
        try:
            st_res = requests.post(TIKTOK_STATUS_URL, headers=status_headers, json=status_payload, timeout=20)
            st_data = st_res.json()
            st_info = st_data.get("data", {})
            status_code = st_info.get("status")

            if status_code in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                msg = "Film opublikowany na profilu!" if status_code == "PUBLISH_COMPLETE" else "Wysłano do aplikacji TikTok (Inbox/Drafts — gotowe do publikacji na telefonie!)"
                print(f"🎉 SUKCES! {msg} (Publish ID: {publish_id})")
                return {
                    "success": True,
                    "platform": "tiktok",
                    "publish_id": publish_id,
                    "title": full_title,
                    "status": status_code,
                    "inbox": (status_code == "SEND_TO_USER_INBOX")
                }
            elif status_code == "FAILED":
                fail_reason = st_info.get("fail_reason", "Nieznany błąd TikToka")
                return {"success": False, "error": f"Przetwarzanie TikTok zakończone błędem: {fail_reason}"}
            else:
                print(f"   ⏳ Status wideo: {status_code}... ({poll_idx + 1}/15)")
        except Exception as e:
            print(f"   ⚠️ Błąd podczas sprawdzania statusu: {e}")

    # Jeśli timeout, ale chunki weszły — wideo zwykle publikuje się chwilę później w tle
    return {
        "success": True,
        "platform": "tiktok",
        "publish_id": publish_id,
        "status": "PROCESSING",
        "message": "Wideo przesłane do TikTok i przetwarzane w tle."
    }
