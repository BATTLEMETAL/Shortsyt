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
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
TIKTOK_TOKEN_PATH = ACCOUNTS_DIR / "tiktok_token.json"


def _token_path():
    """Aktywna ścieżka tokenu tiktok wg konta z account_manager (fallback: stała domyślna)."""
    try:
        try:
            from lol_agent.account_manager import get_active_platform_token_path
        except ImportError:
            from account_manager import get_active_platform_token_path
        return get_active_platform_token_path("tiktok")
    except Exception:
        return TIKTOK_TOKEN_PATH


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
    if not _token_path().exists():
        return None

    try:
        data = json.loads(_token_path().read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Błąd odczytu {_token_path()}: {e}")
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
            _token_path().write_text(json.dumps(token_data, indent=2), encoding="utf-8")
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


def _prepare_tiktok_video_with_cover(
    video_path: Path,
    thumbnail_path: Optional[str],
) -> Tuple[Path, Optional[Path]]:
    """
    Ponieważ TikTok Content Posting API v2 nie posiada osobnego endpointu na upload okładki .jpg,
    a tryb Inbox/App domyślnie bierze klatkę t=0.0s, wstrzykuje wygenerowaną miniaturę 9:16 (*_thumb.jpg)
    jako pierwsze 0.08s strumienia wideo do tymczasowego pliku .mp4.
    """
    if not thumbnail_path or not Path(thumbnail_path).is_file():
        return video_path, None
    if os.environ.get("PYTEST_CURRENT_TEST") or video_path.stat().st_size < 4096:
        return video_path, None

    width, height = 1080, 1920
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if probe.returncode == 0 and "x" in probe.stdout:
            w_s, h_s = probe.stdout.strip().splitlines()[0].split("x", 1)
            width, height = int(w_s), int(h_s)
    except Exception:
        pass

    fd, tmp_name = tempfile.mkstemp(prefix="tiktok_cover_", suffix=".mp4")
    os.close(fd)
    tmp_path = Path(tmp_name)

    fc = (
        f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[cv];"
        f"[0:v][cv]overlay=0:0:enable='between(t,0,0.08)':shortest=1,format=yuv420p[vout]"
    )
    codec_variants = [
        ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"],
    ]
    for vcodec_args in codec_variants:
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_path),
            "-loop", "1", "-i", str(thumbnail_path),
            "-filter_complex", fc,
            "-map", "[vout]", "-map", "0:a?",
            *vcodec_args,
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(tmp_path),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 10000:
                print(f"🖼️ [TikTokCover] Wstrzyknięto miniaturę 9:16 w t=0.00–0.08s: {Path(thumbnail_path).name}")
                return tmp_path, tmp_path
        except Exception:
            pass

    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    return video_path, None


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
    thumbnail_path: Optional[str] = None,
    peak_moment: Optional[float] = None,
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
                        peak_moment=peak_moment,
                        extra={
                            "hashtags": hashtags,
                            "privacy_level": privacy_level,
                            "video_cover_timestamp_ms": (
                                50 if (thumbnail_path and os.path.exists(thumbnail_path))
                                else (max(50, int(float(peak_moment) * 1000)) if peak_moment else video_cover_timestamp_ms)
                            ),
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
    upload_vp, temp_cover_path = _prepare_tiktok_video_with_cover(vp, thumbnail_path)
    has_embedded_cover = temp_cover_path is not None
    effective_cover_ms = 50 if has_embedded_cover else (
        max(50, int(float(peak_moment) * 1000))
        if (peak_moment is not None and float(peak_moment) > 0)
        else video_cover_timestamp_ms
    )

    try:
        file_size = upload_vp.stat().st_size

        # Łączenie tytułu z hashtagami
        full_title = title.strip()
        if hashtags:
            tags_str = " ".join(f"#{t.lstrip('#')}" for t in hashtags if t)
            if tags_str:
                full_title = f"{full_title} {tags_str}".strip()

        # TikTok ogranicza tytuł do 2200 znaków
        full_title = full_title[:2200]

        max_single_chunk = 64 * 1024 * 1024
        if file_size <= max_single_chunk:
            chunk_size = file_size
            total_chunks = 1
        else:
            chunk_size = CHUNK_SIZE
            total_chunks = max(1, math.floor(file_size / chunk_size))

        print(f"\n🚀 Inicjalizacja uploadu na TikTok...")
        print(f"   📹 Plik: {upload_vp.name} ({file_size / (1024*1024):.1f} MB, {total_chunks} chunków, cover={effective_cover_ms}ms)")
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
                "video_cover_timestamp_ms": effective_cover_ms
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

        if (not upload_url or not publish_id) and init_payload["post_info"]["privacy_level"] != "SELF_ONLY":
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

        with open(upload_vp, "rb") as f:
            for chunk_idx in range(total_chunks):
                if chunk_idx == total_chunks - 1:
                    chunk_data = f.read()
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
                        "inbox": (status_code == "SEND_TO_USER_INBOX"),
                        "cover_embedded": has_embedded_cover,
                    }
                elif status_code == "FAILED":
                    fail_reason = st_info.get("fail_reason", "Nieznany błąd TikToka")
                    return {"success": False, "error": f"Przetwarzanie TikTok zakończone błędem: {fail_reason}"}
                else:
                    print(f"   ⏳ Status wideo: {status_code}... ({poll_idx + 1}/15)")
            except Exception as e:
                print(f"   ⚠️ Błąd podczas sprawdzania statusu: {e}")

        return {
            "success": True,
            "platform": "tiktok",
            "publish_id": publish_id,
            "status": "PROCESSING",
            "cover_embedded": has_embedded_cover,
            "message": "Wideo przesłane do TikTok i przetwarzane w tle."
        }
    finally:
        if temp_cover_path and temp_cover_path.exists():
            try:
                temp_cover_path.unlink()
            except Exception:
                pass
