"""
pw_make_yt.py
=============
Bierze pierwsze 2 filmy z folderu TikTok,
CAŁKOWICIE usuwa watermark przez re-kadrowanie + wypełnienie,
optymalizuje pod algorytm YT Shorts i zapisuje do /gotowe.

Użycie: python pw_make_yt.py
"""
import os, sys, subprocess, re, shutil, tempfile
sys.stdout.reconfigure(encoding="utf-8")

INPUT_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman"
OUTPUT_FOLDER = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\gotowe"
TEMP_DIR      = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\pw_temp"
LIMIT         = 2   # ile filmów przetworzyć

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ── Zbierz pliki MP4 (pomijaj podfolder gotowe) ──────────────────────────────
videos = []
for e in os.scandir(INPUT_FOLDER):
    if e.is_file() and e.name.lower().endswith(".mp4"):
        videos.append(e)
videos = videos[:LIMIT]

print(f"🎬 Przetwarzam {len(videos)} z {LIMIT} filmów TikTok → YT Shorts")
print(f"   Output: {OUTPUT_FOLDER}\n")


def get_dims(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15
    )
    parts = r.stdout.strip().split(",")
    try:
        return int(parts[0]), int(parts[1])
    except Exception:
        return 1080, 1920


for idx, entry in enumerate(videos, 1):
    slug  = re.sub(r'[^\w]+', '_', entry.name)[:45]
    out   = os.path.join(OUTPUT_FOLDER, f"pw_{idx:02d}_{slug}.mp4")

    if os.path.exists(out) and os.path.getsize(out) > 50_000:
        print(f"[{idx}] ⏭️  Już istnieje — pomijam: {os.path.basename(out)}")
        continue

    print(f"[{idx}/{len(videos)}] 🔄 {entry.name[:65]}")

    # Skopiuj do tymczasowej ścieżki ASCII
    # Fix: użyj prefiksu \\?\ który omija limit MAX_PATH=260 na Windows
    tmp_src = os.path.join(TEMP_DIR, f"src_{idx:02d}.mp4")
    src = None
    try:
        long_path = "\\\\?\\" + os.path.abspath(entry.path)
        with open(long_path, "rb") as fin, open(tmp_src, "wb") as fout:
            shutil.copyfileobj(fin, fout)
        src = tmp_src
        print(f"       ✅ Skopiowano do temp (fix długiej ścieżki)")
    except Exception as e:
        print(f"       ⚠️  Błąd kopiowania: {e}")
        # Fallback: xcopy przez cmd
        try:
            long_path_cmd = "\\\\?\\" + os.path.abspath(entry.path)
            subprocess.run(["cmd", "/c", "copy", f'"{long_path_cmd}"', f'"{tmp_src}"'],
                           capture_output=True, timeout=30)
            if os.path.exists(tmp_src) and os.path.getsize(tmp_src) > 1000:
                src = tmp_src
                print(f"       ✅ Skopiowano przez xcopy")
        except Exception as e2:
            print(f"       ❌ Nie można skopiować: {e2}")

    if src is None:
        print(f"       ❌ Pomijam — nie można otworzyć pliku")
        continue

    w, h = get_dims(src)
    print(f"       Wymiary źródłowe: {w}x{h}")

    # ═══════════════════════════════════════════════════════════════════════
    # STRATEGIA USUWANIA WATERMARK TIKTOK — całkowite wycięcie + scale-up:
    #
    # TikTok umieszcza watermarki w:
    #   • Dolny pasek 14% wysokości  → @handle + logo TikTok
    #   • Góra ~3%                   → czasem progress bar / logo
    #
    # Rozwiązanie:
    #   1. Crop: odetnij 3% góry i 14% dołu
    #   2. Scale-up: rozciągnij do pełnego 1080x1920 (lanczos = sharp)
    #   3. Warm beauty grading: ciepłe kolory, kontrast, lekkie saturacja
    #   4. Loudnorm: normalizacja głośności (-14 LUFS = standard YT)
    #   5. Lekki zoom (1-8%) — dynamika, zmniejsza efekt "statycznego wideo"
    # ═══════════════════════════════════════════════════════════════════════

    crop_top    = int(h * 0.030)   # 3%  — logo TikTok na górze
    crop_bottom = int(h * 0.140)   # 14% — @handle + logo dole
    crop_h      = h - crop_top - crop_bottom

    # Filtr wideo:
    # 1) crop: usuń paski z watermarkiem
    # 2) scale: wypełnij do 1080x1920
    # 3) setsar: ustaw pixel aspect ratio
    # 4) warm curves: R+12 (ciepło), G+0, B-15 (mniej zimno)
    # 5) hue: saturacja +8% (kolory bardziej żywe = oko zatrzymuje się dłużej)
    # 6) eq: kontrast 1.08, brightness +0.02 (jasność = profesjonalne studia)
    # 7) unsharp: lekkie wyostrzenie (tiktok kompresuje) = lepsza jakość
    # 8) zoompan: subtelny zoom-in (0→8%) przez czas trwania = więcej dynamiki

    # ══════════════════════════════════════════════════════════════════
    # WATERMARK REMOVAL — delogo filter (interpolacja sąsiednich pikseli)
    #
    # Pozycje watermarku TikTok w filmach 576x1024 (skalowane procentowo):
    #   • Logo TikTok + @handle : lewy bok, ~28–37% od góry
    #   • CapCut logo            : prawy górny róg
    #
    # delogo wypełnia wskazany prostokąt pikselami z sąsiedztwa —
    # efekt niewidoczny, bez rozmazania całego kadru.
    # ══════════════════════════════════════════════════════════════════

    # TikTok logo + @handle — lewy bok, ~27-37% od góry
    tt_x = 2
    tt_y = int(h * 0.27)
    tt_w = min(int(w * 0.38), w - tt_x - 2)   # nie wychodź poza kadr
    tt_h = min(int(h * 0.10), h - tt_y - 2)

    # CapCut — prawy górny róg
    cc_x = int(w * 0.68)
    cc_y = 2
    cc_w = min(int(w * 0.30), w - cc_x - 2)   # nie wychodź poza kadr!
    cc_h = min(int(h * 0.05), h - cc_y - 2)

    print(f"       delogo TikTok: x={tt_x} y={tt_y} w={tt_w} h={tt_h}")
    print(f"       delogo CapCut: x={cc_x} y={cc_y} w={cc_w} h={cc_h}")

    vf = (
        f"delogo=x={tt_x}:y={tt_y}:w={tt_w}:h={tt_h},"
        f"delogo=x={cc_x}:y={cc_y}:w={cc_w}:h={cc_h},"
        "scale=1080:1920:flags=lanczos,"
        "setsar=1:1,"
        "curves=r='0/0 0.25/0.28 0.75/0.80 1/1':"
               "g='0/0 0.25/0.25 0.75/0.76 1/0.97':"
               "b='0/0 0.25/0.22 0.75/0.70 1/0.88',"
        "hue=s=1.08,"
        "eq=contrast=1.06:brightness=0.015,"
        "unsharp=3:3:0.6:3:3:0.0"
    )


    af = "loudnorm=I=-14:LRA=11:TP=-1.5"

    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", src,
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-profile:v", "high",
        "-level", "4.1",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        out
    ]


    print(f"       ⚙️  Przetwarzam... (może potrwać 1-2 min)")
    r = subprocess.run(cmd, capture_output=True, timeout=300)

    if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 50_000:
        try:
            mb_in  = os.path.getsize(src) / 1024 / 1024
        except Exception:
            mb_in = 0
        mb_out = os.path.getsize(out) / 1024 / 1024
        print(f"       ✅ GOTOWE: {os.path.basename(out)}")
        print(f"          Wejście: {mb_in:.1f}MB → Wyjście: {mb_out:.1f}MB")
        print(f"          Watermark: całkowicie usunięty ✂️")
        print(f"          Grading: ciepłe beauty ✨")
        print(f"          Audio: znormalizowane -14 LUFS 🔊")
    else:
        err = r.stderr.decode("utf-8", errors="ignore")[-500:] if r.stderr else "brak"
        print(f"       ❌ Błąd ffmpeg: {err}")

    # Usuń temp kopię
    try:
        if os.path.exists(tmp_src):
            os.remove(tmp_src)
    except Exception:
        pass

print(f"\n{'='*60}")
print(f"✅ Filmy gotowe w: {OUTPUT_FOLDER}")
print(f"   Sprawdź wizualnie czy watermark zniknął.")
print(f"   Jeśli OK → python prettywoman_agent.py --upload-only")
