"""
Shortsyt — Skrypt autoryzacji i odświeżania wiecznego tokenu Meta Graph API dla Instagram Reels.
"""
import os
import sys
import time
import json
import argparse
from pathlib import Path
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID", "").strip()
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "").strip()
FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()

ACCOUNTS_DIR = ROOT_DIR / "accounts"
INSTAGRAM_TOKEN_PATH = ACCOUNTS_DIR / "instagram_token.json"

GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def setup_instagram_token(user_access_token: str) -> dict:
    """
    Wymienia User Access Token na Long-Lived Token, pobiera wieczny Page Access Token
    oraz identyfikuje połączone konto Instagram Professional / Creator.
    """
    if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
        raise ValueError("Brak INSTAGRAM_APP_ID lub INSTAGRAM_APP_SECRET w .env!")

    print("🔄 Krok 1: Wymiana User Token na Long-Lived Token (60 dni)...")
    exchange_url = f"{GRAPH_API_BASE}/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": INSTAGRAM_APP_ID,
        "client_secret": INSTAGRAM_APP_SECRET,
        "fb_exchange_token": user_access_token
    }
    resp = requests.get(exchange_url, params=params, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Błąd wymiany tokenu: {resp.text}")

    ll_token_data = resp.json()
    ll_user_token = ll_token_data.get("access_token", user_access_token)
    print("✅ Long-Lived User Token uzyskany!")

    print("🔄 Krok 2: Pobieranie stron Facebook i wiecznego tokenu strony...")
    accounts_url = f"{GRAPH_API_BASE}/me/accounts"
    resp = requests.get(accounts_url, params={"access_token": ll_user_token}, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Błąd pobierania stron: {resp.text}")

    acc_data = resp.json()
    pages = acc_data.get("data", [])
    if not pages:
        raise RuntimeError("Brak powiązanych stron Facebook dla tego konta.")

    target_page = None
    if FACEBOOK_PAGE_ID:
        for p in pages:
            if p.get("id") == FACEBOOK_PAGE_ID:
                target_page = p
                break
    if not target_page:
        target_page = pages[0]

    page_id = target_page["id"]
    page_name = target_page.get("name", "Unknown")
    page_token = target_page.get("access_token")
    print(f"✅ Znaleziono stronę: {page_name} (ID: {page_id})")

    print("🔄 Krok 3: Wyciąganie powiązanego konta Instagram...")
    page_info_url = f"{GRAPH_API_BASE}/{page_id}"
    resp = requests.get(
        page_info_url,
        params={"fields": "instagram_business_account,connected_instagram_account,name", "access_token": page_token},
        timeout=15
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Błąd odpytania strony o Instagram: {resp.text}")

    page_info = resp.json()
    ig_account = page_info.get("instagram_business_account") or page_info.get("connected_instagram_account")
    if not ig_account:
        raise RuntimeError(
            f"Strona {page_name} nie ma powiązanego konta Instagram Professional/Creator!\n"
            "Upewnij się, że połączyłeś konto Instagram z tą stroną na Facebooku."
        )

    ig_id = ig_account["id"]

    print("🔄 Krok 4: Pobieranie szczegółów profilu Instagram...")
    ig_resp = requests.get(
        f"{GRAPH_API_BASE}/{ig_id}",
        params={"fields": "username,name", "access_token": page_token},
        timeout=15
    )
    ig_info = ig_resp.json() if ig_resp.status_code == 200 else {}
    username = ig_info.get("username", "")

    # Krok 5: Sprawdzenie przyznanych uprawnień (debug_token)
    granted_scopes = []
    try:
        debug_url = f"https://graph.facebook.com/debug_token"
        debug_resp = requests.get(
            debug_url,
            params={"input_token": page_token, "access_token": f"{INSTAGRAM_APP_ID}|{INSTAGRAM_APP_SECRET}"},
            timeout=10
        )
        if debug_resp.status_code == 200:
            granted_scopes = debug_resp.json().get("data", {}).get("scopes", [])
    except Exception:
        pass

    has_ig_insights = "instagram_manage_insights" in granted_scopes
    has_fb_posts = "pages_manage_posts" in granted_scopes

    token_payload = {
        "access_token": page_token,
        "instagram_account_id": ig_id,
        "page_id": page_id,
        "username": username,
        "token_type": "Bearer",
        "expires_at": 0,
        "created_at": int(time.time()),
        "scopes": granted_scopes,
        "features": {
            "instagram_reels_publish": True,
            "instagram_insights": has_ig_insights,
            "facebook_posts_publish": has_fb_posts,
        }
    }

    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    INSTAGRAM_TOKEN_PATH.write_text(json.dumps(token_payload, indent=2), encoding="utf-8")

    # Zapisz również konfigurację Facebook Page
    fb_token_path = ACCOUNTS_DIR / "facebook_token.json"
    fb_payload = {
        "access_token": page_token,
        "page_id": page_id,
        "page_name": page_name,
        "token_type": "Bearer",
        "expires_at": 0,
        "created_at": int(time.time()),
        "scopes": granted_scopes,
        "can_publish_posts": has_fb_posts,
    }
    fb_token_path.write_text(json.dumps(fb_payload, indent=2), encoding="utf-8")

    print(f"\n🎉 SUKCES! Zapisano wieczny token Meta (Instagram + FB):")
    print(f"   Instagram: @{username} (ID: {ig_id})")
    print(f"   Facebook Page: {page_name} (ID: {page_id})")
    print(f"   Pliki: {INSTAGRAM_TOKEN_PATH} | {fb_token_path}")
    print("\n📋 Status uprawnień:")
    print(f"   • Instagram Reels Upload: ✅ Aktywne")
    print(f"   • Instagram Insights:     {'✅ Aktywne' if has_ig_insights else '⚠️ Brak instagram_manage_insights'}")
    print(f"   • Facebook Page Posting:  {'✅ Aktywne' if has_fb_posts else '⚠️ Brak pages_manage_posts'}")
    return token_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autoryzacja Instagram dla Shortsyt")
    parser.add_argument("--token", help="User Access Token z Graph API Explorer", default=None)
    args = parser.parse_args()

    token = args.token
    if not token:
        token = input("Wklej User Access Token z Graph API Explorer: ").strip()

    if not token:
        print("❌ Nie podano tokenu.")
        sys.exit(1)

    try:
        setup_instagram_token(token)
    except Exception as e:
        print(f"❌ Błąd autoryzacji Instagram: {e}")
        sys.exit(1)
