"""
Shortsyt — Moduł publikacji na Instagram Reels za pomocą Instagram Graph API.
Obsługuje bezpośredni upload pliku wideo (Resumable Upload na rupload.facebook.com),
status polling kontenera oraz publikację Reels z pełnym error-handlingiem.
"""
import os
import sys
import time
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

ACCOUNTS_DIR = ROOT_DIR / "accounts"
INSTAGRAM_TOKEN_PATH = ACCOUNTS_DIR / "instagram_token.json"


def _token_path():
    """Aktywna ścieżka tokenu instagram wg konta z account_manager (fallback: stała domyślna)."""
    try:
        try:
            from lol_agent.account_manager import get_active_platform_token_path
        except ImportError:
            from account_manager import get_active_platform_token_path
        return get_active_platform_token_path("instagram")
    except Exception:
        return INSTAGRAM_TOKEN_PATH


GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

IG_MAX_VIDEO_BITRATE = 20_000_000
IG_MAX_FILE_BYTES = 80 * 1024 * 1024
IG_MAX_AUDIO_BITRATE = 136_000


def _parse_fps_ratio(val: Any) -> float:
    """Parsuje zapis klatkażu z ffprobe (np. '60/1' lub '82260/1421') do float."""
    s = str(val or "").strip()
    if not s:
        return 0.0
    if "/" in s:
        num, den = s.split("/", 1)
        try:
            d = float(den)
            return float(num) / d if d > 0 else 0.0
        except Exception:
            return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _probe_video_for_ig(vp: Path) -> Dict[str, Any]:
    """Odczytuje parametry strumieni wideo/audio przez ffprobe do oceny zgodności z IG Reels."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(vp)],
            capture_output=True, text=True, check=False, timeout=20,
        )
        if r.returncode != 0 or not (r.stdout or "").strip():
            return {}
        data = json.loads(r.stdout)
    except Exception:
        return {}

    fmt = data.get("format") or {}
    v_stream: Dict[str, Any] = {}
    a_stream: Dict[str, Any] = {}
    for st in data.get("streams") or []:
        if st.get("codec_type") == "video" and not v_stream:
            v_stream = st
        elif st.get("codec_type") == "audio" and not a_stream:
            a_stream = st

    try:
        dur_s = float(fmt.get("duration") or v_stream.get("duration") or 0.0)
    except Exception:
        dur_s = 0.0

    def _safe_int(x: Any) -> int:
        try:
            return int(float(x))
        except Exception:
            return 0

    return {
        "duration_s": dur_s,
        "size": _safe_int(fmt.get("size")),
        "video_bitrate": _safe_int(v_stream.get("bit_rate") or fmt.get("bit_rate")),
        "audio_bitrate": _safe_int(a_stream.get("bit_rate")),
        "audio_sample_rate": _safe_int(a_stream.get("sample_rate")),
        "codec_name": str(v_stream.get("codec_name") or "").lower(),
        "pix_fmt": str(v_stream.get("pix_fmt") or "").lower(),
        "r_fps": _parse_fps_ratio(v_stream.get("r_frame_rate")),
        "avg_fps": _parse_fps_ratio(v_stream.get("avg_frame_rate")),
    }


def _needs_ig_transcode(probe: Dict[str, Any], file_size: int) -> Tuple[bool, List[str]]:
    """Sprawdza, czy plik przekracza twarde limity Instagram Reels (bitrate, VFR, AAC, faststart)."""
    reasons: List[str] = []
    if file_size > IG_MAX_FILE_BYTES:
        reasons.append(f"size={file_size}>{IG_MAX_FILE_BYTES}")
    if not probe:
        return bool(reasons), reasons

    vb = int(probe.get("video_bitrate") or 0)
    ab = int(probe.get("audio_bitrate") or 0)
    codec = str(probe.get("codec_name") or "").lower()
    pix = str(probe.get("pix_fmt") or "").lower()
    r_fps = float(probe.get("r_fps") or 0.0)
    avg_fps = float(probe.get("avg_fps") or 0.0)

    if vb > IG_MAX_VIDEO_BITRATE:
        reasons.append(f"video_bitrate={vb}>{IG_MAX_VIDEO_BITRATE}")
    if ab > IG_MAX_AUDIO_BITRATE:
        reasons.append(f"audio_bitrate={ab}>{IG_MAX_AUDIO_BITRATE}")
    if codec and codec != "h264":
        reasons.append(f"codec={codec}")
    if pix and pix != "yuv420p":
        reasons.append(f"pix_fmt={pix}")
    if r_fps > 0.0 and avg_fps > 0.0 and (abs(r_fps - avg_fps) / max(r_fps, 1.0)) > 0.02:
        reasons.append(f"vfr(r={r_fps:.2f},avg={avg_fps:.2f})")

    return bool(reasons), reasons


def _prepare_ig_compliant_video(
    vp: Path,
    force_transcode: bool = False,
    force_check: bool = False,
) -> Tuple[Path, bool, Optional[float]]:
    """Zwraca (ścieżka_do_wysyłki, czy_plik_tymczasowy, czas_trwania_s). Konwertuje ciężkie/VFR MP4 pod IG Reels."""
    if not force_check and (vp.stat().st_size < 4096 or os.environ.get("PYTEST_CURRENT_TEST")):
        return vp, False, None

    probe = _probe_video_for_ig(vp)
    dur_s = float(probe["duration_s"]) if probe.get("duration_s") else None
    need_tx, reasons = _needs_ig_transcode(probe, vp.stat().st_size)
    if not force_transcode and not need_tx:
        return vp, False, dur_s

    target_fps = min(60, max(30, round(float(probe.get("r_fps") or 30))))
    tmp_name = f"ig_compliant_{vp.stem[:40]}_{int(time.time())}.mp4"
    tmp_path = Path(tempfile.gettempdir()) / tmp_name
    print(f"🎛️ [IG Compliance] Transkoduję do profilu Reels ({', '.join(reasons) or 'force'}) -> {tmp_path.name}...")

    cmd = [
        "ffmpeg", "-y", "-i", str(vp),
        "-c:v", "libx264", "-preset", "fast", "-profile:v", "high", "-level", "4.2",
        "-pix_fmt", "yuv420p", "-crf", "20", "-maxrate", "14M", "-bufsize", "28M",
        "-fps_mode", "cfr", "-r", str(target_fps),
        "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(tmp_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180)
        if res.returncode == 0 and tmp_path.is_file() and tmp_path.stat().st_size > 0:
            return tmp_path, True, dur_s
        print(f"⚠️ [IG Compliance] FFmpeg kod={res.returncode}: {(res.stderr or '')[:240]}")
    except Exception as e:
        print(f"⚠️ [IG Compliance] Błąd transkodera: {e}")

    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass
    return vp, False, dur_s


def _clamp_thumb_offset_ms(offset_ms: int, duration_s: Optional[float]) -> int:
    """Ogranicza thumb_offset do zakresu [0, (duration - 0.5s)] aby Meta nie odrzuciła offsetu po końcu klipu."""
    val = max(0, int(offset_ms))
    if duration_s is not None and duration_s > 0.6:
        max_ms = max(0, int((float(duration_s) - 0.5) * 1000))
        val = min(val, max_ms)
    return val


def _post_ig_rupload(upload_uri: str, vp_send: Path, file_size: int, access_token: str):
    """Wysyła strumień binarny na rupload.facebook.com z 1 automatyczną próbą przy błędzie tymczasowym."""
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    }
    up_resp = None
    for attempt in range(2):
        with open(vp_send, "rb") as video_file:
            up_resp = requests.post(upload_uri, headers=upload_headers, data=video_file, timeout=180)
        if up_resp.status_code in (200, 201):
            return up_resp
        body_low = (up_resp.text or "").lower()
        is_transient = (500 <= up_resp.status_code < 600) or ('"retriable":true' in body_low)
        if attempt == 0 and is_transient:
            print(f"⚠️ Tymczasowy błąd rupload ({up_resp.status_code}) — ponawiam za 3s...")
            time.sleep(3)
            continue
        break
    return up_resp


def load_instagram_token() -> Optional[Dict[str, Any]]:
    """Wczytuje token i dane konta Instagram z pliku lub zmiennych środowiskowych."""
    data = {}
    if _token_path().exists():
        try:
            data = json.loads(_token_path().read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ Błąd odczytu {_token_path()}: {e}")

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
    cleanup_paths: List[Path] = []
    try:
        vp_send, is_tmp, dur_s = _prepare_ig_compliant_video(vp)
        if is_tmp:
            cleanup_paths.append(vp_send)
        send_size = vp_send.stat().st_size
        print(f"📦 Rozmiar pliku: {send_size / (1024 * 1024):.2f} MB | {vp_send.name}")

        # Krok 1: Parametry kontenera mediów z automatyczną miniaturą (thumb_offset)
        container_url = f"{GRAPH_API_BASE}/{ig_id}/media"
        container_params: Dict[str, Any] = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": access_token,
        }

        if cover_url:
            container_params["cover_url"] = cover_url
        elif thumb_offset is not None:
            container_params["thumb_offset"] = str(_clamp_thumb_offset_ms(int(thumb_offset), dur_s))
        elif peak_moment is not None and peak_moment > 0:
            clamped_ms = _clamp_thumb_offset_ms(int(peak_moment * 1000), dur_s)
            container_params["thumb_offset"] = str(clamped_ms)
            print(f"🎯 Automatyczna miniatura IG: ustawiono thumb_offset na moment szczytowy ({clamped_ms}ms)")
        else:
            # Domyślny offset 2500ms (ograniczony długością klipu)
            container_params["thumb_offset"] = str(_clamp_thumb_offset_ms(2500, dur_s))

        container_id = None
        for tx_attempt in range(2):
            try:
                resp = requests.post(container_url, data=container_params, timeout=30)
                res_json = resp.json()
                if resp.status_code != 200 or "id" not in res_json:
                    err = res_json.get("error", {}).get("message", resp.text)
                    print(f"❌ Błąd tworzenia kontenera Reel: {err}")
                    return {"success": False, "error": f"Błąd tworzenia kontenera: {err}"}

                container_id = res_json["id"]
                upload_uri = res_json.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}/{container_id}"
                print(f"✅ Kontener Reel utworzony! ID: {container_id}")
            except Exception as e:
                print(f"❌ Wyjątek podczas tworzenia kontenera Reel: {e}")
                return {"success": False, "error": str(e)}

            # Krok 2: Bezpośredni upload binarny na rupload.facebook.com
            print("🚀 Wysyłam dane wideo do rupload.facebook.com...")
            try:
                up_resp = _post_ig_rupload(upload_uri, vp_send, send_size, access_token)
                if up_resp is not None and up_resp.status_code in (200, 201):
                    print("✅ Plik wideo przesłany pomyślnie. Oczekiwanie na przetworzenie przez Instagram...")
                    break

                err_txt = up_resp.text if up_resp is not None else "empty response"
                if (
                    tx_attempt == 0
                    and not is_tmp
                    and not os.environ.get("PYTEST_CURRENT_TEST")
                    and "ProcessingFailedError" in err_txt
                ):
                    print("🔄 [IG Recovery] rupload zgłosił ProcessingFailedError — transkoduję do profilu Reels i ponawiam...")
                    vp_retry, retry_tmp, dur_retry = _prepare_ig_compliant_video(vp, force_transcode=True, force_check=True)
                    if retry_tmp:
                        cleanup_paths.append(vp_retry)
                        vp_send = vp_retry
                        is_tmp = True
                        send_size = vp_send.stat().st_size
                        if "thumb_offset" in container_params:
                            container_params["thumb_offset"] = str(_clamp_thumb_offset_ms(int(container_params["thumb_offset"]), dur_retry))
                        continue

                st_code = up_resp.status_code if up_resp is not None else "ERR"
                print(f"❌ Błąd uploadu binarki do rupload: {st_code} {err_txt}")
                return {"success": False, "error": f"Błąd uploadu: {err_txt}"}
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
    finally:
        for cp in cleanup_paths:
            try:
                if cp.exists():
                    cp.unlink()
            except Exception:
                pass
