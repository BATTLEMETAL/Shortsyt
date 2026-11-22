"""
Globalna izolacja sieci i kont produkcyjnych dla root pakietu `tests/`.
Blokuje niezamierzone odczyty prawdziwych tokenów (Meta/TikTok/YT) oraz wyjścia HTTP w testach offline.
"""
from unittest.mock import MagicMock
import pytest
import requests

_BLOCKED_HOSTS = (
    "graph.facebook.com",
    "graph-video.facebook.com",
    "rupload.facebook.com",
    "open.tiktokapis.com",
    "googleapis.com",
    "accounts.google.com",
)


@pytest.fixture(autouse=True)
def _isolate_live_social_apis(monkeypatch, tmp_path):
    # Wyczyść zmienne środowiskowe z prawdziwymi tokenami Meta
    for env_key in (
        "FACEBOOK_ACCESS_TOKEN",
        "FACEBOOK_PAGE_ID",
        "INSTAGRAM_ACCESS_TOKEN",
        "INSTAGRAM_ACCOUNT_ID",
    ):
        monkeypatch.delenv(env_key, raising=False)

    # Przekieruj _token_path() w FB/IG/TikTok oraz TOKEN_PATH w lol_publisher
    try:
        import lol_agent.facebook_publisher as fb_pub
        monkeypatch.setattr(fb_pub, "FACEBOOK_TOKEN_PATH", tmp_path / "missing_fb_token.json")
        monkeypatch.setattr(fb_pub, "_token_path", lambda: fb_pub.FACEBOOK_TOKEN_PATH)
    except Exception:
        pass

    try:
        import lol_agent.instagram_publisher as ig_pub
        monkeypatch.setattr(ig_pub, "INSTAGRAM_TOKEN_PATH", tmp_path / "missing_ig_token.json")
        monkeypatch.setattr(ig_pub, "_token_path", lambda: ig_pub.INSTAGRAM_TOKEN_PATH)
    except Exception:
        pass

    try:
        import lol_agent.tiktok_publisher as tt_pub
        monkeypatch.setattr(tt_pub, "TIKTOK_TOKEN_PATH", tmp_path / "missing_tt_token.json")
        monkeypatch.setattr(tt_pub, "_token_path", lambda: tt_pub.TIKTOK_TOKEN_PATH)
    except Exception:
        pass

    try:
        import lol_agent.api.youtube_uploader as yt_up
        monkeypatch.setattr(
            yt_up,
            "upload_video",
            MagicMock(side_effect=AssertionError("Blocked real YouTube upload in pytest")),
        )
    except Exception:
        pass

    try:
        import lol_agent.lol_publisher as lol_pub
        monkeypatch.setattr(lol_pub, "TOKEN_PATH", str(tmp_path / "missing_yt_token.pickle"))
    except Exception:
        pass

    # Twarda blokada nie-zamockowanych zapytań sieciowych na domeny produkcyjne
    orig_session_req = requests.Session.request

    def _guarded_session_request(self, method, url, *args, **kwargs):
        url_low = str(url or "").lower()
        if any(host in url_low for host in _BLOCKED_HOSTS):
            raise RuntimeError(f"Blocked live outbound request in pytest: {method} {url}")
        return orig_session_req(self, method, url, *args, **kwargs)

    monkeypatch.setattr(requests.Session, "request", _guarded_session_request)
