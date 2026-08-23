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

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import CLIENT_SECRET_PATH, YT_TOKEN_PATH, ACCOUNTS_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
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


def get_auth_url() -> str:
    """
    Zwróć URL do autoryzacji YouTube OAuth.
    Użytkownik otwiera URL, autoryzuje i wkleja kod.
    """
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError(f"Brak client_secret.json: {CLIENT_SECRET_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    # Zapisz client_config + auth_url (flow ma niepicklowalną lambdę)
    import json as _json
    flow_path = YT_TOKEN_PATH.parent / "_pending_flow.json"
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    _json.dump({
        "client_config_file": str(CLIENT_SECRET_PATH),
        "scopes": SCOPES,
        "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
    }, open(flow_path, "w"))

    return auth_url


def exchange_auth_code(code: str) -> Dict[str, Any]:
    """Wymień kod autoryzacji na token i zapisz."""
    import json as _json
    flow_path = YT_TOKEN_PATH.parent / "_pending_flow.json"
    if not flow_path.exists():
        raise ValueError("Brak pending flow — najpierw wywołaj get_auth_url()")

    cfg = _json.load(open(flow_path))
    flow = InstalledAppFlow.from_client_secrets_file(
        cfg["client_config_file"],
        scopes=cfg["scopes"],
        redirect_uri=cfg["redirect_uri"],
    )

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
