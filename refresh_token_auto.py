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

# Wymuś UTF-8 na Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from google.auth.transport.requests import Request

ACCOUNTS_DIR = "accounts"
LOG_FILE = os.path.join("logs", "token_refresh.log")


def log(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def refresh_all_tokens():
    log("=" * 55)
    log("AUTO-REFRESH TOKENOW OAUTH — startuję")
    log("=" * 55)

    if not os.path.isdir(ACCOUNTS_DIR):
        log(f"BLAD: Brak katalogu '{ACCOUNTS_DIR}'")
        return 1

    token_files = [f for f in os.listdir(ACCOUNTS_DIR) if f.endswith("_token.pickle")]

    if not token_files:
        log("Brak plikow tokenow w accounts/")
        return 0

    success = 0
    failed = 0

    for fname in token_files:
        profile = fname.replace("_token.pickle", "")
        fpath = os.path.join(ACCOUNTS_DIR, fname)

        try:
            with open(fpath, "rb") as f:
                creds = pickle.load(f)

            if not creds or not creds.refresh_token:
                log(f"[{profile}] SKIP — brak refresh_token (wymaga recznej autoryzacji)")
                failed += 1
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
            log(f"[{profile}] BLAD: {e}")
            failed += 1

    log("-" * 55)
    log(f"WYNIK: {success} sukces, {failed} bledow")
    log("=" * 55)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(refresh_all_tokens())
