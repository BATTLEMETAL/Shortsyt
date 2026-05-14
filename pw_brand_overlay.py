"""
pw_brand_overlay.py
====================
Przykrywa floating watermark TikToka własnym brandem salonu.

Strategia:
  - TikTok watermark pojawia się naprzemiennie LEFT/RIGHT w środku kadru
  - Dodajemy DELIKATNY brand "💇 Pretty Woman | Świdnica" na dole kadru
  - Górę i dół trimujemy lekko (CapCut logo = góra, TikTok handle = zmieniana pozycja)
  - Nakładamy WHITE GRADIENT BAR na dole z nazwą salonu
  - Efekt: profesjonalne branded video bez obcego watermarku

Użycie: python pw_brand_overlay.py
"""
import os, sys, subprocess, re, shutil
sys.stdout.reconfigure(encoding="utf-8")

INPUT_FOLDER  = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman"
OUTPUT_FOLDER = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt\tiktokiprettywoman\gotowe"
TEMP_DIR      = r"C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\pw_temp"
FONT          = "C\\:/Windows/Fonts/arialbd.ttf"   # Arial Bold — zawsze na Windows
LIMIT         = 2

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)


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
        return 576, 1024


def process_video(src: str, final_out: str, idx: int) -> bool:
    w, h = get_dims(src)
    print(f"       Wymiary: {w}x{h}")

    # ffmpeg nie radzi sobie z polskimi znakami w ścieżce wyjściowej
    # → renderuj do ASCII temp, potem przenieś
    tmp_out = os.path.join(TEMP_DIR, f"out_{idx:02d}.mp4")
    if os.path.exists(tmp_out):
        os.remove(tmp_out)

    crop_top = int(h * 0.045)
    crop_bot = int(h * 0.04)
    new_h    = h - crop_top - crop_bot

    bar_h  = 120
    bar_y  = 1920 - bar_h

    brand_text = "SALON PRETTY WOMAN  |  SWIDNICA"
    font_size  = 34
    text_y     = bar_y + (bar_h - font_size) // 2 + 5

    vf_parts = [
        f"crop={w}:{new_h}:0:{crop_top}",
        "scale=1080:1920:flags=lanczos",
        "setsar=1:1",
        "curves=r='0/0 0.25/0.28 0.75/0.80 1/1':"
        "g='0/0 0.25/0.25 0.75/0.76 1/0.97':"
        "b='0/0 0.25/0.22 0.75/0.70 1/0.88'",
        "hue=s=1.08",
        "eq=contrast=1.06:brightness=0.015",
        "unsharp=3:3:0.6:3:3:0.0",
        # Brand bar
        f"drawbox=x=0:y={bar_y}:w=1080:h={bar_h}:color=0x1a1a2e@0.82:t=fill",
        f"drawbox=x=0:y={bar_y}:w=1080:h=3:color=0xFF69B4@0.95:t=fill",
        # Tekst — fontcolor z alpha wbudowanym (format RRGGBBAA)
        f"drawtext=text='{brand_text}'"
        f":fontfile='{FONT}'"
        f":fontsize={font_size}"
        f":fontcolor=white"
        f":x=(w-text_w)/2"
        f":y={text_y}"
        f":shadowcolor=black:shadowx=1:shadowy=1",
    ]
    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", src,
        "-vf", vf,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium",
        "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", "-r", "30",
        tmp_out
    ]

    r = subprocess.run(cmd, capture_output=True, timeout=300)
    if r.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 50_000:
        # Przenieś do docelowego folderu
        shutil.copy2(tmp_out, final_out)
        os.remove(tmp_out)
        mb = os.path.getsize(final_out) / 1024 / 1024
        print(f"       \u2705 OK: {os.path.basename(final_out)} ({mb:.1f}MB)")
        return True
    err = r.stderr.decode("utf-8", errors="ignore")[-400:] if r.stderr else ""
    print(f"       \u274c ffmpeg error: {err}")
    return False


# ── Skanuj folder ────────────────────────────────────────────
videos = []
for e in os.scandir(INPUT_FOLDER):
    if e.is_file() and e.name.lower().endswith(".mp4"):
        videos.append(e)
videos = videos[:LIMIT]

print("=" * 60)
print("  🌸 PRETTYWOMAN — Brand Overlay (zastąp TikTok watermark)")
print(f"  Przetwarzam: {len(videos)} filmów")
print("=" * 60)

for idx, entry in enumerate(videos, 1):
    slug = re.sub(r'[^\w]+', '_', entry.name)[:40]
    out  = os.path.join(OUTPUT_FOLDER, f"pw_{idx:02d}_{slug}.mp4")
    tmp  = os.path.join(TEMP_DIR, f"src_{idx:02d}.mp4")

    if os.path.exists(out) and os.path.getsize(out) > 50_000:
        print(f"\n[{idx}] ⏭️  Już istnieje")
        continue

    print(f"\n[{idx}/{len(videos)}] {entry.name[:60]}")

    # Kopiuj z long-path fix
    src = None
    try:
        lp = "\\\\?\\" + os.path.abspath(entry.path)
        with open(lp, "rb") as fi, open(tmp, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        src = tmp
        print(f"       ✅ Skopiowano")
    except Exception as e:
        print(f"       ⚠️  Błąd copy: {e}")

    if not src:
        continue

    process_video(src, out, idx)

    try:
        os.remove(tmp)
    except Exception:
        pass

print(f"\n{'='*60}")
print(f"✅ Gotowe: {OUTPUT_FOLDER}")
print()
print("UWAGA: Brand bar na dole przykrywa watermark TikTok.")
print("Sprawdź wizualnie — jeśli TikTok logo nadal widoczne w środku kadru,")
print("jedynym rozwiązaniem jest oryginalny plik z CapCut (przed uploadem).")
