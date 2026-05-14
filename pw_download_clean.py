"""
pw_download_clean.py
====================
Pobiera filmy TikTok BEZ znaku wodnego przez yt-dlp z ciasteczkami przeglądarki.
TikTok daje właścicielom kont dostęp do czystej wersji (bez watermark).

Użycie:
  python pw_download_clean.py          # pobierz wszystkie z Excel
  python pw_download_clean.py --test   # test na 1 filmie
"""
import os, sys, subprocess, json, openpyxl, re, shutil
sys.stdout.reconfigure(encoding="utf-8")

EXCEL_FILE     = r"C:\Users\mz100\.gemini\antigravity\scratch\Content.xlsx"
OUTPUT_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\gotowe"
TEMP_DIR       = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\pw_temp"
PYTHON         = sys.executable
LIMIT          = 2  # ile filmów pobrać

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


def load_urls_from_excel() -> list:
    """Wczytuje TikTok URLs + metadane z Content.xlsx, sortuje po views malejąco."""
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        url = str(row[2]).strip() if row[2] else ""
        if "tiktok.com" not in url:
            continue
        rows.append({
            "url":      url,
            "desc":     str(row[1])[:80] if row[1] else "",
            "views":    int(row[7] or 0),
            "likes":    int(row[4] or 0),
        })
    rows.sort(key=lambda x: x["views"], reverse=True)
    return rows


def slug(text: str, n: int = 40) -> str:
    return re.sub(r'[^\w]+', '_', text)[:n].strip('_') or "video"


def try_download(url: str, out_path: str, method: str) -> bool:
    """Próbuje pobrać TikTok bez watermark — kilka metod."""

    base_cmd = [PYTHON, "-m", "yt_dlp", "--no-warnings", "-o", out_path, "--no-playlist"]

    if method == "opera_cookies":
        # Metoda 1: ciasteczka z Opery (zalogowany użytkownik = czysta wersja)
        cmd = base_cmd + [
            "--cookies-from-browser", "opera",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            url
        ]
    elif method == "chrome_cookies":
        # Metoda 2: ciasteczka z Chrome
        cmd = base_cmd + [
            "--cookies-from-browser", "chrome",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            url
        ]
    elif method == "musical_ly_api":
        # Metoda 3: alternatywny API host TikTok
        cmd = base_cmd + [
            "--extractor-args", "tiktok:app_name=musical_ly,app_version=26.1.3",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            url
        ]
    elif method == "trill_api":
        # Metoda 4: Trill API (często daje no-watermark)
        cmd = base_cmd + [
            "--extractor-args", "tiktok:app_name=trill,app_version=23.5.3",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            url
        ]
    else:
        return False

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        # Szukaj pobranego pliku (yt-dlp zmienia nazwy)
        temp_base = out_path.replace(".mp4", "")
        for ext in [".mp4", ".webm", ".mkv"]:
            if os.path.exists(out_path.replace(".mp4", ext)):
                return True
        # Sprawdź czy istnieje dokładnie
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000:
            return True
        return False
    except Exception as e:
        print(f"         ⚠️  {method}: {e}")
        return False


def apply_beauty_grading(src: str, out: str):
    """Aplikuje warm beauty grading + audio normalizację (bez watermark removal)."""
    w_r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
        capture_output=True, text=True, timeout=15
    )
    parts = w_r.stdout.strip().split(",")
    try:
        w, h = int(parts[0]), int(parts[1])
    except Exception:
        w, h = 1080, 1920

    vf = (
        "scale=1080:1920:flags=lanczos,"
        "setsar=1:1,"
        "curves=r='0/0 0.25/0.28 0.75/0.80 1/1':"
               "g='0/0 0.25/0.25 0.75/0.76 1/0.97':"
               "b='0/0 0.25/0.22 0.75/0.70 1/0.88',"
        "hue=s=1.08,"
        "eq=contrast=1.06:brightness=0.015,"
        "unsharp=3:3:0.6:3:3:0.0"
    )
    cmd = [
        "ffmpeg", "-y", "-nostdin", "-i", src,
        "-vf", vf,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", "-r", "30",
        out
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    return r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 50_000


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  🌸 PRETTYWOMAN — Pobieranie bez watermark (TikTok API)")
    print("=" * 60)

    entries = load_urls_from_excel()
    print(f"📊 Znaleziono {len(entries)} filmów w Content.xlsx")

    limit = 1 if args.test else LIMIT
    entries = entries[:limit]

    methods = ["opera_cookies", "chrome_cookies", "musical_ly_api", "trill_api"]

    for i, e in enumerate(entries, 1):
        print(f"\n[{i}/{len(entries)}] 📥 {e['desc'][:60]}")
        print(f"  URL: {e['url']}")
        print(f"  Views: {e['views']:,} | Likes: {e['likes']:,}")

        name_slug = slug(e['desc'], 40)
        tmp_dl    = os.path.join(TEMP_DIR, f"dl_{i:02d}_{name_slug}.mp4")
        final_out = os.path.join(OUTPUT_FOLDER, f"pw_clean_{i:02d}_{name_slug}.mp4")

        if os.path.exists(final_out) and os.path.getsize(final_out) > 50_000:
            print(f"  ⏭️  Już istnieje: {os.path.basename(final_out)}")
            continue

        # Usuń stary temp jeśli istnieje
        if os.path.exists(tmp_dl):
            os.remove(tmp_dl)

        downloaded = False
        for method in methods:
            print(f"  🔄 Próba: {method}...", end=" ", flush=True)
            ok = try_download(e['url'], tmp_dl, method)
            if ok:
                print("✅")
                downloaded = True
                break
            else:
                print("❌")

        if not downloaded:
            print(f"  ❌ Nie można pobrać przez żadną metodę")
            print(f"  💡 ROZWIĄZANIE: Zapisz oryginalny film z CapCut (przed uploadem TikTok)")
            continue

        # Sprawdź czy pobrany plik ma watermark
        size_mb = os.path.getsize(tmp_dl) / 1024 / 1024
        print(f"  📦 Pobrano: {size_mb:.1f}MB")

        # Aplikuj beauty grading
        print(f"  🎨 Beauty grading + audio normalizacja...")
        ok_grade = apply_beauty_grading(tmp_dl, final_out)
        if ok_grade:
            out_mb = os.path.getsize(final_out) / 1024 / 1024
            print(f"  ✅ GOTOWE: {os.path.basename(final_out)} ({out_mb:.1f}MB)")
        else:
            shutil.copy(tmp_dl, final_out)
            print(f"  ⚠️  Grading nie powiódł się — kopiuję bez filtrów")

        # Cleanup
        if os.path.exists(tmp_dl):
            os.remove(tmp_dl)

    print(f"\n{'='*60}")
    print(f"✅ Pliki w: {OUTPUT_FOLDER}")
    print()
    print("WAŻNE — jeśli watermark nadal widoczny:")
    print("  1. Zaloguj się do TikTok w Operze")
    print("  2. Uruchom ponownie — ciasteczka dadzą dostęp do czystej wersji")
    print("  3. LUB: Wyślij oryginały z CapCut (przed uploadem TikTok)")


if __name__ == "__main__":
    main()
