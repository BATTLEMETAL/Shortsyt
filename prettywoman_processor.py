"""
prettywoman_processor.py
=========================
Przetwarza filmy TikTok z folderu — usuwa watermark i przygotowuje na YT.

Użycie:
  python prettywoman_processor.py                    # przetworz wszystkie
  python prettywoman_processor.py --folder "ścieżka" # własny folder
  python prettywoman_processor.py --test             # tylko watermark test na 1 pliku
"""
import os, sys, json, re, shutil, subprocess, glob, argparse
import openpyxl
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

# ── Konfiguracja ────────────────────────────────────────────────────────────
TIKTOK_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman"
EXCEL_FILE     = r"C:\Users\mz100\.gemini\antigravity\scratch\Content.xlsx"
OUTPUT_FOLDER  = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\prettywoman_yt"
MUSIC_DIR      = r"C:\Users\mz100\PycharmProjects\shortsyt\music\pretty_woman"
PYTHON         = sys.executable
FFMPEG         = "ffmpeg"
FFPROBE        = "ffprobe"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)


# ── 1. Wczytaj Content.xlsx ─────────────────────────────────────────────────
def load_excel_data() -> list:
    """Parsuje Content.xlsx → lista wpisów z metadanymi."""
    if not os.path.exists(EXCEL_FILE):
        print(f"⚠️  Brak {EXCEL_FILE} — uruchamiam bez danych Excel")
        return []
    wb = openpyxl.load_workbook(EXCEL_FILE)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        # Kolumny: data_pub, opis, tiktok_url, data_tiktok, likes, komentarze, udostepnienia, views
        try:
            entry = {
                "publish_date": str(row[0]).strip() if row[0] else "",
                "description":  str(row[1]).strip() if row[1] else "",
                "tiktok_url":   str(row[2]).strip() if row[2] else "",
                "tiktok_date":  str(row[3]).strip() if row[3] else "",
                "likes":        int(row[4] or 0),
                "comments":     int(row[5] or 0),
                "shares":       int(row[6] or 0),
                "views":        int(row[7] or 0),
            }
            rows.append(entry)
        except Exception:
            pass
    # Sortuj malejąco po views
    rows.sort(key=lambda x: x["views"], reverse=True)
    print(f"✅ Wczytano {len(rows)} wpisów z Content.xlsx")
    return rows


# ── 2. Skanuj folder z filmami ──────────────────────────────────────────────
def scan_video_folder(folder: str) -> list:
    """Zbiera wszystkie .mp4 z folderu — obsługuje emoji i spacje w nazwach."""
    videos = []
    if not os.path.exists(folder):
        print(f"⚠️  Folder nie istnieje: {folder}")
        return videos
    for entry in os.scandir(folder):
        if entry.is_file() and entry.name.lower().endswith(".mp4"):
            try:
                size_mb = entry.stat().st_size / 1024 / 1024
                videos.append({
                    "path": entry.path,
                    "name": entry.name,
                    "size_mb": round(size_mb, 1),
                })
            except Exception as e:
                print(f"  ⚠️  Błąd odczytu {entry.name[:40]}: {e}")
        elif entry.is_dir():
            # Rekurencja w podfolderach
            sub = scan_video_folder(entry.path)
            videos.extend(sub)
    return videos


# ── 3. Utwórz bezpieczną nazwę pliku ───────────────────────────────────────
def safe_slug(text: str, max_len: int = 50) -> str:
    """Czyści tekst do bezpiecznej nazwy pliku ASCII."""
    # Usuń emoji i znaki specjalne
    text = re.sub(r'[^\w\s\-]', '', text, flags=re.UNICODE)
    text = re.sub(r'\s+', '_', text.strip())
    text = re.sub(r'[^\w\-]', '', text)
    return text[:max_len] or "video"


# ── 4. Pobierz wymiary video ────────────────────────────────────────────────
def get_video_dims(path: str):
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15
        )
        parts = r.stdout.strip().split(",")
        w = int(parts[0]) if len(parts) > 0 else 1080
        h = int(parts[1]) if len(parts) > 1 else 1920
        d = float(parts[2]) if len(parts) > 2 else 30.0
        return w, h, d
    except Exception:
        return 1080, 1920, 30.0


# ── 5. Usuń watermark TikTok ────────────────────────────────────────────────
def remove_tiktok_watermark(input_path: str, output_path: str, style: str = "crop") -> bool:
    """
    Strategie usuwania watermark TikTok:
    - 'crop': lekkie przycinanie góry i dołu (5%+8%) — najszybsze, brak pixelacji
    - 'blur': blur strip na dole (bardziej agresywne, ale nie tnie kadru)
    - 'both': crop + blur (najlepsza jakość)
    """
    print(f"  ✂️  Usuwam watermark [{style}]: {os.path.basename(input_path)[:50]}")
    w, h, dur = get_video_dims(input_path)

    if style == "crop":
        # Przytnij 5% góra, 9% dół (gdzie jest logo TikTok + @handle)
        crop_top    = int(h * 0.05)
        crop_bottom = int(h * 0.09)
        new_h = h - crop_top - crop_bottom
        vf = (
            f"crop={w}:{new_h}:0:{crop_top},"
            f"scale={w}:{h}:flags=lanczos,"
            # Warm beauty grading po przycięciu
            "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/0.97':b='0/0 0.5/0.45 1/0.90',"
            "hue=s=1.05"
        )
    elif style == "blur":
        # Blur tylko dolnego paska gdzie watermark (bez cięcia)
        blur_h = int(h * 0.10)
        vf = (
            f"split[a][b];"
            f"[b]crop={w}:{blur_h}:0:{h - blur_h},boxblur=20:20[blurred];"
            f"[a][blurred]overlay=0:{h - blur_h},"
            "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/0.97':b='0/0 0.5/0.45 1/0.90',"
            "hue=s=1.05"
        )
    else:  # both — crop + warm grading
        crop_top = int(h * 0.04)
        crop_bottom = int(h * 0.07)
        new_h = h - crop_top - crop_bottom
        blur_strip = int(new_h * 0.06)
        vf = (
            f"crop={w}:{new_h}:0:{crop_top},"
            f"scale={w}:{h}:flags=lanczos,"
            "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/0.97':b='0/0 0.5/0.45 1/0.90',"
            "hue=s=1.05"
        )

    cmd = [
        FFMPEG, "-y", "-nostdin",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  ✅ OK: {os.path.basename(output_path)} ({size_mb:.1f}MB)")
        return True
    err = r.stderr.decode("utf-8", errors="ignore")[-300:] if r.stderr else ""
    print(f"  ❌ ffmpeg error: {err}")
    return False


# ── 6. Dobierz muzykę beauty ─────────────────────────────────────────────────
def ensure_music() -> list:
    mp3s = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    if mp3s:
        return mp3s
    print(f"🎵 Pobieram muzykę beauty...")
    queries = [
        "ytsearch1:elegant soft salon background music no copyright 2024",
        "ytsearch1:beauty spa piano background music no copyright",
    ]
    for q in queries:
        cmd = [PYTHON, "-m", "yt_dlp", "-x", "--audio-format", "mp3",
               "--audio-quality", "192K",
               "-o", os.path.join(MUSIC_DIR, "bg_%(id)s.%(ext)s"), q]
        subprocess.run(cmd, capture_output=True, timeout=90)
    return glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))


# ── 7. Dodaj muzykę do wideo ─────────────────────────────────────────────────
def add_background_music(video_path: str, output_path: str, music_files: list) -> bool:
    if not music_files:
        shutil.copy(video_path, output_path)
        return True
    import random
    music = random.choice(music_files)
    _, _, dur = get_video_dims(video_path)
    cmd = [
        FFMPEG, "-y", "-nostdin",
        "-i", video_path,
        "-i", music,
        "-filter_complex",
        (f"[0:a]volume=1.0[main];"
         f"[1:a]atrim=0:{dur:.1f},asetpts=PTS-STARTPTS,volume=0.12[bg];"
         f"[main][bg]amix=inputs=2:duration=first[aout]"),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=180)
    return r.returncode == 0 and os.path.exists(output_path)


# ── 8. Buduj metadane YT ─────────────────────────────────────────────────────
def build_yt_metadata(excel_entry: dict | None, video_name: str) -> dict:
    """Buduje optymalny tytuł/opis/tagi dla YT Shorts."""
    if excel_entry:
        desc_raw = excel_entry.get("description", "")
        views    = excel_entry.get("views", 0)

        # Wyciągnij pierwsze zdanie jako hook
        first_sentence = re.split(r'[.!?]', desc_raw.replace('\n', ' '))[0].strip()
        first_sentence = re.sub(r'[\U0001F000-\U0001FFFF]', '', first_sentence).strip()[:80]

        # Dobierz tytuł na podstawie treści
        if any(k in desc_raw.lower() for k in ["afroloki", "afrolo"]):
            yt_hook = "Afroloki Świdnica — piękna metamorfoza w kilka godzin"
        elif any(k in desc_raw.lower() for k in ["kucyk", "kucyki"]):
            yt_hook = "Kucyki na ściągaczu — szybka metamorfoza w 1 minutę!"
        elif any(k in desc_raw.lower() for k in ["warkocz", "braids", "fulani"]):
            yt_hook = "Warkoczyki, które zachwycają — efekt w naszym salonie"
        elif any(k in desc_raw.lower() for k in ["peruk"]):
            yt_hook = "Peruka na opaskę — game changer dla Twojego looku"
        elif any(k in desc_raw.lower() for k in ["toper", "topor"]):
            yt_hook = "AfroToper — metamorfoza w 1 minutę bez zobowiązań"
        else:
            yt_hook = f"Salon Pretty Woman Świdnica — {first_sentence[:60]}"

        description = (
            f"{yt_hook}\n\n"
            f"💇‍♀️ Specjalizujemy się w: Afrolokach, warkoczykach, kucykach i perukach na zamówienie.\n"
            f"📍 Salon Kosmetyczny Pretty Woman\n"
            f"📫 ul. Ofiar Oświęcimskich 28, Świdnica\n"
            f"📞 788-945-643\n"
            f"🛍️ Sklep online: https://sklep.salon-prettywoman.pl\n"
            f"🎓 Szkolimy z fryzur alternatywnych!\n\n"
            f"👇 Zarezerwuj wizytę przez sklep lub Messenger\n\n"
            f"#afroloki #warkoczyki #fryzjerświdnica #metamorfoza #shorts "
            f"#kucykidoczepiania #peruki #hairgoals #salonpiękności"
        )
        tags = [
            "afroloki", "warkoczyki", "kucyki doczepianie", "fryzjer Świdnica",
            "salon pretty woman", "metamorfoza włosów", "shorts", "afroloki Polska",
            "warkoczyki na lato", "peruka na opaskę", "braids Poland",
            "hair transformation", "fryzury alternatywne", "Świdnica",
        ]
    else:
        slug = re.sub(r'[^\w\s]', '', video_name)[:50]
        yt_hook = f"Piękna metamorfoza — Salon Pretty Woman Świdnica"
        description = (
            f"{yt_hook}\n\n"
            f"📍 Salon Kosmetyczny Pretty Woman, Świdnica\n"
            f"🛍️ https://sklep.salon-prettywoman.pl\n\n"
            f"#afroloki #warkoczyki #shorts #fryzjerświdnica"
        )
        tags = ["afroloki", "warkoczyki", "shorts", "fryzjer Świdnica", "metamorfoza"]
        views = 0

    return {
        "title":       yt_hook[:100],
        "description": description[:4990],
        "tags":        tags[:15],
        "tiktok_views": views,
    }


# ── 9. Matchuj video do Excel ─────────────────────────────────────────────────
def match_video_to_excel(video_name: str, excel_data: list) -> dict | None:
    """Próbuje dopasować plik wideo do wpisu Excel po słowach kluczowych."""
    name_clean = re.sub(r'[^\w\s]', ' ', video_name.lower())
    name_words = set(name_clean.split())

    best_match = None
    best_score = 0

    for entry in excel_data:
        desc_words = set(re.sub(r'[^\w\s]', ' ', entry["description"].lower()).split())
        common = name_words & desc_words
        # Minimum 3 wspólne słowa
        if len(common) >= 3 and len(common) > best_score:
            best_score = len(common)
            best_match = entry

    return best_match


# ── MAIN ───────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Prettywoman Processor — Beauty re-edit dla YT Shorts")
    parser.add_argument("--folder",         default=TIKTOK_FOLDER, help="Folder z filmami TikTok")
    parser.add_argument("--test",           action="store_true",   help="Test na 1 pliku")
    parser.add_argument("--no-music",       action="store_true",   help="Pomijaj dodawanie muzyki")
    parser.add_argument("--style",          default="crop",        choices=["crop","blur","both"],
                        help="Styl usuwania watermark (użyj TYLKO gdy plik ma watermark)")
    parser.add_argument("--already-clean",  action="store_true",   default=True,
                        help="[Default] Pliki ze snaptik.app — bez watermarku. Pomija FFmpeg crop.")
    parser.add_argument("--force-crop",     action="store_true",
                        help="Wymuś usuwanie watermarku przez crop (gdy plik ma watermark)")
    args = parser.parse_args()

    # Logika: --force-crop nadpisuje --already-clean
    already_clean = (not args.force_crop)

    print("=" * 60)
    print("  🌸 PRETTYWOMAN PROCESSOR — Beauty re-edit dla YT Shorts")
    print(f"  Folder: {args.folder}")
    print(f"  Output: {OUTPUT_FOLDER}")
    if already_clean:
        print("  ✅ Tryb: Pliki JUŻ BEZ watermarku (snaptik/download_addr) — pomijam crop")
    else:
        print(f"  ✂️  Tryb: Usuwanie watermarku FFmpeg [{args.style}] — może obniżyć jakość")
    print("=" * 60)

    # Wczytaj dane
    excel_data = load_excel_data()
    videos     = scan_video_folder(args.folder)
    music_files = [] if args.no_music else ensure_music()

    if not videos:
        print(f"❌ Brak filmów .mp4 w folderze: {args.folder}")
        print("   Wgraj filmy z TikToka do folderu i uruchom ponownie.")
        return

    print(f"\n📁 Znaleziono {len(videos)} filmów do przetworzenia")
    if args.test:
        videos = videos[:1]
        print("  [TEST MODE] Przetwarzam tylko 1 film")

    results = []
    for i, v in enumerate(videos, 1):
        print(f"\n{'─'*55}")
        print(f"[{i}/{len(videos)}] {v['name'][:60]} ({v['size_mb']}MB)")

        # Nazwa wyjściowa
        slug = safe_slug(v['name'], 40)
        nowm_path  = os.path.join(OUTPUT_FOLDER, f"pw_{i:02d}_{slug}_nowm.mp4")
        final_path = os.path.join(OUTPUT_FOLDER, f"pw_{i:02d}_{slug}_YT.mp4")
        meta_path  = os.path.join(OUTPUT_FOLDER, f"pw_{i:02d}_{slug}_meta.json")

        # Skip jeśli już przetworzone
        if os.path.exists(final_path) and os.path.getsize(final_path) > 50000:
            print(f"  ⏭️  Już przetworzone — pomijam")
            results.append({"input": v['name'], "output": final_path, "status": "skipped"})
            continue

        # KROK 1: Watermark handling
        if already_clean:
            # Plik ze snaptik.app lub download_addr — JUŻ czysty.
            # Zamiast niszczyć jakość przez crop, tylko aplikujemy warm beauty grading przez FFmpeg.
            print(f"  🌸 Aplikuję beauty grading (bez cropu)...")
            vf_beauty = (
                "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/0.97':b='0/0 0.5/0.45 1/0.90',"
                "hue=s=1.05"
            )
            cmd_beauty = [
                FFMPEG, "-y", "-nostdin",
                "-i", v['path'],
                "-vf", vf_beauty,
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-c:a", "copy",          # audio KOPIA — zero utraty
                "-movflags", "+faststart",
                nowm_path
            ]
            r = subprocess.run(cmd_beauty, capture_output=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(nowm_path):
                # Fallback: skopiuj bez zmian
                shutil.copy(v['path'], nowm_path)
                print(f"  ⚠️  Beauty grading nie powiódł się — używam oryginału")
            else:
                size_mb = os.path.getsize(nowm_path) / 1024 / 1024
                print(f"  ✅ Beauty grading OK ({size_mb:.1f}MB) — audio bez zmian")
        else:
            # --force-crop: plik MA watermark — użyj FFmpeg crop (utrata jakości)
            ok_wm = remove_tiktok_watermark(v['path'], nowm_path, style=args.style)
            if not ok_wm:
                print(f"  ❌ Watermark removal failed")
                results.append({"input": v['name'], "output": "", "status": "failed"})
                continue

        # KROK 2: Dodaj muzykę
        if music_files and not args.no_music:
            print(f"  🎵 Dodaję muzykę beauty w tle...")
            ok_music = add_background_music(nowm_path, final_path, music_files)
            if not ok_music:
                shutil.copy(nowm_path, final_path)
        else:
            shutil.copy(nowm_path, final_path)

        # KROK 3: Dopasuj do Excel i zbuduj metadane
        excel_match = match_video_to_excel(v['name'], excel_data)
        if excel_match:
            print(f"  📊 Excel match: {excel_match['views']} views TikTok")
        meta = build_yt_metadata(excel_match, v['name'])

        # Zapisz metadane
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"  📋 YT Title: {meta['title'][:70]}")
        print(f"  💾 Zapisano: {os.path.basename(final_path)}")

        results.append({
            "input":       v['name'][:60],
            "output":      final_path,
            "meta":        meta_path,
            "yt_title":    meta['title'],
            "tiktok_views": meta.get('tiktok_views', 0),
            "status":      "done",
        })

        # Cleanup temp no-watermark
        if os.path.exists(nowm_path):
            os.remove(nowm_path)

    # Podsumowanie
    done  = [r for r in results if r['status'] == 'done']
    skip  = [r for r in results if r['status'] == 'skipped']
    fails = [r for r in results if r['status'] == 'failed']

    print(f"\n{'='*60}")
    print(f"✅ GOTOWE: {len(done)} filmów | Pominięte: {len(skip)} | Błędy: {len(fails)}")
    print(f"\n📁 Pliki gotowe do YT: {OUTPUT_FOLDER}")
    for r in done:
        print(f"   → {os.path.basename(r['output'])}")
        print(f"     YT: {r.get('yt_title','')[:60]}")

    # Zapisz raport
    report_path = os.path.join(OUTPUT_FOLDER, "processing_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now().isoformat(), "results": results}, f,
                  ensure_ascii=False, indent=2)
    print(f"\n📋 Raport zapisany: {report_path}")
    print("\n📌 NASTĘPNY KROK:")
    print("   python prettywoman_agent.py --upload-only")
    print("   (przesyła przetworzone filmy na YT przez smart_uploader.py)")


if __name__ == "__main__":
    main()
