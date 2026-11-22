"""
refresh_token_auto.py
=====================
Cichy skrypt odświeżający tokeny OAuth wszystkich kont.
Uruchamiany codziennie przez Task Scheduler (~10:00), na długo przed pipeline'm (19:00).

Rozwiązuje problem: Google Cloud "Testing" mode = refresh_token wygasa po 7 dniach
jeśli NIE jest używany. Ten skrypt używa tokenu codziennie → Google resetuje 7-dniowy zegar.
"""

import os
import sys
import pickle
import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Wymuś UTF-8 na Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from google.auth.transport.requests import Request

ACCOUNTS_DIR = str(ROOT_DIR / "accounts")
LOG_FILE = str(ROOT_DIR / "logs" / "token_refresh.log")


def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_active_yt_token_name() -> str:
    reg_path = os.path.join(ACCOUNTS_DIR, "profiles_registry.json")
    try:
        if os.path.exists(reg_path):
            import json
            data = json.loads(Path(reg_path).read_text(encoding="utf-8"))
            active_id = data.get("active_account_id")
            acc = (data.get("accounts") or {}).get(active_id or "") or {}
            return acc.get("yt_token_file") or "lol_token.pickle"
    except Exception:
        pass
    return "lol_token.pickle"


def refresh_all_tokens():
    log("=" * 55)
    log("AUTO-REFRESH TOKENOW OAUTH — startuję")
    log("=" * 55)

    if not os.path.isdir(ACCOUNTS_DIR):
        log(f"BLAD: Brak katalogu '{ACCOUNTS_DIR}'")
        return 1

    active_yt_file = _load_active_yt_token_name()
    token_files = [f for f in os.listdir(ACCOUNTS_DIR) if f.endswith("_token.pickle")]

    if not token_files:
        log("Brak plikow tokenow w accounts/")
        return 0

    success = 0
    failed = 0
    warned = 0

    for fname in token_files:
        profile = fname.replace("_token.pickle", "")
        fpath = os.path.join(ACCOUNTS_DIR, fname)
        is_active = (fname == active_yt_file)

        try:
            with open(fpath, "rb") as f:
                creds = pickle.load(f)

            if not creds or not creds.refresh_token:
                if is_active:
                    log(f"[{profile}] BLAD — brak refresh_token dla aktywnego profilu")
                    failed += 1
                else:
                    log(f"[{profile}] SKIP — brak refresh_token (nieaktywny profil)")
                    warned += 1
                continue

            if creds.expired or not creds.valid:
                log(f"[{profile}] Token wygasly — odswiezam...")
                creds.refresh(Request())
                with open(fpath, "wb") as f:
                    pickle.dump(creds, f)
                log(f"[{profile}] OK — odswiezono, wygasa: {creds.expiry}")
            else:
                # Token wciaz wazny — odswiezamy go ANYWAY zeby zresetowac 7-dniowy zegar
                log(f"[{profile}] Token wazny do {creds.expiry} — odswiezam prewencyjnie...")
                creds.refresh(Request())
                with open(fpath, "wb") as f:
                    pickle.dump(creds, f)
                log(f"[{profile}] OK — prewencyjnie odswiezony, nowe wygasniecie: {creds.expiry}")

            success += 1

        except Exception as e:
            if is_active:
                log(f"[{profile}] BLAD (aktywny profil): {e}")
                failed += 1
            else:
                log(f"[{profile}] WARN (nieaktywny profil pominięty): {e}")
                warned += 1

    # --- TIKTOK AUTO-REFRESH ---
    tiktok_token_path = os.path.join(ACCOUNTS_DIR, "tiktok_token.json")
    if os.path.exists(tiktok_token_path):
        try:
            from lol_agent.tiktok_publisher import load_tiktok_token
            tt = load_tiktok_token()
            if tt:
                log("[tiktok] OK — token sprawdzony/odswiezony")
                success += 1
            else:
                log("[tiktok] SKIP — brak waznego tokenu lub refresh_token")
        except Exception as tt_err:
            log(f"[tiktok] BLAD: {tt_err}")

    # --- INSTAGRAM HEALTH-CHECK ---
    instagram_token_path = os.path.join(ACCOUNTS_DIR, "instagram_token.json")
    if os.path.exists(instagram_token_path):
        try:
            from lol_agent.instagram_publisher import get_instagram_token_status
            ig_stat = get_instagram_token_status()
            if ig_stat.get("valid"):
                log(f"[instagram] OK — token aktywny (@{ig_stat.get('username')})")
                success += 1
            else:
                log(f"[instagram] BLAD: {ig_stat.get('message')}")
                failed += 1
        except Exception as ig_err:
            log(f"[instagram] BLAD: {ig_err}")
            failed += 1

    # --- FACEBOOK PAGE HEALTH-CHECK ---
    facebook_token_path = os.path.join(ACCOUNTS_DIR, "facebook_token.json")
    if os.path.exists(facebook_token_path):
        try:
            from lol_agent.facebook_publisher import get_facebook_token_status
            fb_stat = get_facebook_token_status()
            if fb_stat.get("valid"):
                log(f"[facebook] OK - token aktywny ({fb_stat.get('page_name')}, can_publish={fb_stat.get('can_publish')})")
                success += 1
            else:
                log(f"[facebook] BLAD: {fb_stat.get('message')}")
                failed += 1
        except Exception as fb_err:
            log(f"[facebook] BLAD: {fb_err}")
            failed += 1

    # --- AUTOMATED FEEDBACK LOOP (METRIC INGESTION) ---
    try:
        from lol_agent.platform_feedback_collector import collect_all_platform_metrics
        log("\n[feedback_loop] Zbieranie metryk z opublikowanych filmow...")
        report = collect_all_platform_metrics(max_videos=10)
        log(f"[feedback_loop] Zaktualizowano bazy learning_states: YT={report.get('youtube_updated')}, IG={report.get('instagram_updated')}, FB={report.get('facebook_updated')}")
    except Exception as fl_err:
        log(f"[feedback_loop] Ostrzezenie feedback loop: {fl_err}")

    log("-" * 55)
    log(f"WYNIK: {success} sukces, {failed} bledow")
    log("=" * 55)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(refresh_all_tokens())
