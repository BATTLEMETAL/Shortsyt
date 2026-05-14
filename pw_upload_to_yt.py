"""
pw_upload_to_yt.py — Batch uploader dla Salon Pretty Woman YT
==============================================================
Wczytuje gotowe filmy (bez watermarku TikTok) z folderu gotowe/
i uploaduje je na kanał YouTube z profesjonalnymi metadanymi PL.

Użycie:
    python pw_upload_to_yt.py            # upload wszystkich filmów
    python pw_upload_to_yt.py --dry-run  # podgląd bez uploadu
    python pw_upload_to_yt.py --limit 1  # tylko 1 film (test)
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

# ── Konfiguracja ─────────────────────────────────────────────────────────────
PROFILE_NAME   = "prettywoman"
GOTOWE_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\gotowe"
REPORT_FILE    = "pw_publish_report.json"

# ── Tagi (research 06.05.2026) ──────────────────────────────────────────────────
# Reguła: max 15 tagów w polu tags, ale tylko 3-5 hashtagów w tytule/opisie
# Algorytm ignoruje spam tagów — jakość > ilość
BASE_TAGS = [
    "afroloki",
    "afrolokiświdnica",
    "warkoczyki",
    "warkoczzykiafrykańskie",
    "metamorfoza",
    "hairtransformation",
    "protectivestyles",
    "naturalhair",
    "fryzjer",
    "swidnica",
    "szkoleniafryzerskie",
    "braidstyles",
    "salonprettywoman",
    "przedłużaniewłosów",
    "shorts",
]

# Zestawy hashtagów do opisu (rotacja wg typu filmu)
HASHTAG_SETS = {
    "transformacja": "#afroloki #metamorfoza #hairtransformation #protectivestyles #shorts",
    "warkoczyki":    "#warkoczyki #braidstyles #naturalhair #fryzura2026 #shorts",
    "lokalne":       "#afrolokiświdnica #fryzjerswidnica #szkolenieonline #braider #shorts",
    "edukacja":      "#afroloki #warkoczyki #fryzjerskieporady #naturalhair #shorts",
}

# Szablony tytułów (research: max 55 znaków, keyword z przodu, emoji)
TITLE_MAP = {
    "kucyki":       "Kucyki które trzymają MIESIĄCAMI 🫶 Nie klamerki! #shorts",
    "sylwia":       "Pani Sylwia — jej 3. Afroloki 🥹 Historia klientki #shorts",
    "metamorfoza":  "Nie uwierzysz jak wyglądała PRZED 😱 Afroloki Świdnica",
    "boho":         "Warkoczyki BOHO vs Afroloki — którą byś wybrała? 🔥 #shorts",
}

# Opis bazowy
BASE_DESCRIPTION = """Salon Pretty Woman — Świdnica 🌸

✂️ Specjalizujemy się w:
• Afroloki i warkoloki
• Warkoczyki afrykańskie + BOHO
• Przedłużanie włosów metodą szydełkową
• Szkolenia dla fryzjerek 💡

📍 Świdnica, ul. Ofiar Oświęcimskich 28
📞 Umów wizytę: sklep.salon-prettywoman.pl
📸 TikTok: @salonprettywoman

#afroloki #afrolokiświdnica #warkoczykiafrykańskie #metamorfoza #shorts"""


# ── Wybór tytułu wg nazwy pliku ───────────────────────────────────────────────
def pick_title(filename: str) -> str:
    fn_lower = filename.lower()
    if "kucyki" in fn_lower or "kucyk" in fn_lower:
        return TITLE_MAP["kucyki"]
    if "sylwia" in fn_lower:
        return TITLE_MAP["sylwia"]
    if "metamorfoza" in fn_lower or "moja" in fn_lower:
        return TITLE_MAP["metamorfoza"]
    if "boho" in fn_lower or "warkoczyki" in fn_lower:
        return TITLE_MAP["boho"]
    # Fallback — wygeneruj z nazwy pliku
    clean = re.sub(r"[_\-]+", " ", re.sub(r"YT_\d+_?", "", filename))
    clean = re.sub(r"\.mp4$", "", clean).strip()[:80]
    return f"{clean} 🌸 #shorts"


# ── Załaduj/Zapisz raport ─────────────────────────────────────────────────────
def load_report() -> list:
    if not os.path.exists(REPORT_FILE):
        return []
    try:
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_report(entries: list):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


# ── Główna logika ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pretty Woman YT Uploader")
    parser.add_argument("--dry-run", action="store_true", help="Podgląd bez uploadu")
    parser.add_argument("--limit",   type=int, default=99, help="Max. liczba filmów")
    args = parser.parse_args()

    # Importy YT API
    from upload_youtube import get_authenticated_service, upload_video

    print("=" * 60)
    print("  🌸 SALON PRETTY WOMAN — YouTube Uploader")
    print("=" * 60)

    # Autoryzacja
    print(f"\n🔑 Autoryzacja konta: {PROFILE_NAME}...")
    youtube = get_authenticated_service(PROFILE_NAME)
    if not youtube:
        print("❌ Brak tokenu! Uruchom: python authorize_channel.py --konto prettywoman")
        return

    # Znajdź filmy — preferuj YT_0X_ wersje (wyższa jakość procesowania)
    all_files = [
        f for f in os.listdir(GOTOWE_FOLDER)
        if f.lower().endswith(".mp4") and f.startswith("YT_")
    ]
    # Deduplikacja: dla każdego numeru (YT_01, YT_02...) wybierz NAJWIĘKSZY plik
    best_per_num: dict[str, tuple] = {}
    for fname in all_files:
        m = re.match(r"YT_(\d+)_", fname)
        if not m:
            continue
        num = m.group(1)
        fpath = os.path.join(GOTOWE_FOLDER, fname)
        fsize = os.path.getsize(fpath)
        if num not in best_per_num or fsize > best_per_num[num][1]:
            best_per_num[num] = (fname, fsize, fpath)

    to_upload = sorted(best_per_num.items())[:args.limit]  # posortuj wg numeru

    print(f"\n📂 Folder: {GOTOWE_FOLDER}")
    print(f"🎬 Filmów do uploadu: {len(to_upload)}")

    report = load_report()
    already_uploaded = {e.get("filename") for e in report}

    for num, (fname, fsize, fpath) in to_upload:
        print(f"\n{'─'*55}")
        print(f"[{num}] {fname}")
        print(f"    Rozmiar: {fsize/1024/1024:.1f} MB")

        if fname in already_uploaded:
            print(f"    ⏭️  Już uploadowany — pomijam.")
            continue

        title = pick_title(fname)
        description = BASE_DESCRIPTION
        print(f"    📌 Tytuł: {title}")

        if args.dry_run:
            print(f"    [DRY-RUN] Pominięto upload.")
            continue

        video_id = upload_video(
            youtube=youtube,
            file_path=fpath,
            title=title,
            description=description,
            tags=BASE_TAGS,
            category_id="26",        # Howto & Style (beauty/fryzjerstwo)
            privacy_status="public",
        )

        if video_id:
            entry = {
                "filename":   fname,
                "video_id":   video_id,
                "title":      title,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "url":        f"https://www.youtube.com/shorts/{video_id}",
            }
            report.append(entry)
            save_report(report)
            print(f"    ✅ https://www.youtube.com/shorts/{video_id}")
        else:
            print(f"    ❌ Upload nieudany.")

    print(f"\n{'='*60}")
    print(f"✅ Gotowe! Raport: {REPORT_FILE}")
    if not args.dry_run:
        print(f"📺 Sprawdź: https://studio.youtube.com")


if __name__ == "__main__":
    main()
