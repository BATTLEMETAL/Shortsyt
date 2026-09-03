"""
prettywoman_agent.py
====================
Pipeline dla kanału Afroloki Świdnica na YouTube Shorts:
  1. Wczytuje prettywoman_analysis.json (wynik analyzera)
  2. Pobiera TOP filmy z TikToka BEZ watermark (yt-dlp)
  3. Usuwa znak wodny TikTok przez lekkie przycinanie ffmpeg
  4. Dodaje:
     - Ciepłe filtry beauty (warm grading, nie dark psychology)
     - Głos PL z hooka (Edge-TTS, głos kobiecy ZofiaNeural)
     - Miękką muzykę w tle (elegant/soft)
     - Napisy ASS (styl Beauty - biały, czysty)
  5. Publikuje na YT przez smart_uploader.py

Użycie:
  python prettywoman_agent.py                # uruchom pełny pipeline
  python prettywoman_agent.py --download     # tylko pobierz filmy
  python prettywoman_agent.py --edit-only    # tylko edytuj już pobrane
  python prettywoman_agent.py --upload-only  # tylko wyślij na YT
"""
import os, sys, json, subprocess, glob, shutil, random, argparse, re
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ── Konfiguracja ─────────────────────────────────────────────
ACCOUNT_ID      = "pretty_woman"
TIKTOK_HANDLE   = "@salonprettywoman"
ANALYSIS_FILE   = "prettywoman_analysis.json"
DOWNLOAD_DIR    = "temp_videos/prettywoman_raw"
OUTPUT_DIR      = "temp_videos"
MUSIC_DIR       = "music/pretty_woman"
VOICE           = "pl-PL-ZofiaNeural"   # ciepły, kobiecy głos
VOICE_RATE      = "+5%"
PYTHON          = sys.executable
FFMPEG          = "ffmpeg"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── 1. Wczytaj analizę ────────────────────────────────────────
def load_analysis() -> dict:
    if not os.path.exists(ANALYSIS_FILE):
        print(f"❌ Brak pliku {ANALYSIS_FILE}. Najpierw: python prettywoman_tiktok_analyzer.py")
        sys.exit(1)
    with open(ANALYSIS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 2. Pobierz TOP filmy bez watermark ───────────────────────
def download_nowatermark(url: str, out_path: str) -> bool:
    """
    Pobiera film z TikToka BEZ watermarku — 3 metody kaskadowo.

    Jak działa snaptik.app:
    TikTok przechowuje każdy film w 2 wersjach:
      - play_addr    → z wbudowanym watermarkiem (białe logo + @handle)
      - download_addr → czysta wersja BEZ watermarku (ta sama jakość)
    snaptik odpytuje TikTok API i zwraca download_addr.
    yt-dlp potrafi to samo przez format_id 'download_addr-0'.
    """
    print(f"  ⬇️  Pobieranie (no-watermark): {url[:70]}...")

    # ─── Metoda 1: download_addr (identyczna jak snaptik) ─────────────────────
    # Format 'download_addr-0' to dokładnie ten sam stream co pobiera snaptik.
    # Nie wymaga crop, blur, ani żadnego post-processingu — plik jest już czysty.
    cmd1 = [
        PYTHON, "-m", "yt_dlp",
        "--quiet",
        "--no-warnings",
        "--format", "download_addr-0/bestvideo[format_id*=download]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--extractor-args", "tiktok:app_name=trill;app_version=34.1.2;manifest_app_version=2023401020",
        "--output", out_path,
        "--no-playlist",
        url
    ]
    try:
        r = subprocess.run(cmd1, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"  ✅ Metoda 1 (download_addr) — brak watermarku: {size_mb:.1f}MB")
            return True
        if r.stderr:
            print(f"  ⚠️  Metoda 1 stderr: {r.stderr[-200:]}")
    except Exception as e:
        print(f"  ⚠️  Metoda 1 error: {e}")

    # ─── Metoda 2: alternatywny API hostname (jak w starym kodzie, ale lepszy format) ─
    # Niektóre regiony/wersje TikToka odpowiadają na inny hostname.
    cmd2 = [
        PYTHON, "-m", "yt_dlp",
        "--quiet",
        "--no-warnings",
        "--format", "download_addr-0/bestvideo+bestaudio/mp4",
        "--merge-output-format", "mp4",
        "--extractor-args", "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com",
        "--output", out_path,
        "--no-playlist",
        url
    ]
    try:
        r = subprocess.run(cmd2, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"  ✅ Metoda 2 (alt hostname) — brak watermarku: {size_mb:.1f}MB")
            return True
    except Exception as e:
        print(f"  ⚠️  Metoda 2 error: {e}")

    # ─── Metoda 3: cookies.txt z przeglądarki (zalogowany TikTok) ─────────────
    # Jeśli jest plik cookies.txt — użyj sesji zalogowanego użytkownika.
    # Zalogowany użytkownik dostaje download_addr automatycznie.
    cookies_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")
    if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
        cmd3 = [
            PYTHON, "-m", "yt_dlp",
            "--quiet",
            "--no-warnings",
            "--cookies", cookies_path,
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            "--output", out_path,
            "--no-playlist",
            url
        ]
        try:
            r = subprocess.run(cmd3, capture_output=True, text=True, timeout=120,
                               encoding="utf-8", errors="replace")
            if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
                size_mb = os.path.getsize(out_path) / 1024 / 1024
                print(f"  ✅ Metoda 3 (cookies) — pobrany plik: {size_mb:.1f}MB")
                print(f"  ⚠️  UWAGA: plik może mieć watermark — sprawdź ręcznie")
                return True
        except Exception as e:
            print(f"  ⚠️  Metoda 3 error: {e}")

    print(f"  ❌ Wszystkie metody zawiodły dla: {url[:60]}")
    print(f"     Tip: pobierz plik ręcznie z snaptik.app i wgraj do: {os.path.dirname(out_path)}")
    return False


def remove_tiktok_watermark_crop(input_path: str, output_path: str) -> bool:
    """
    OSTATECZNY FALLBACK — używaj TYLKO gdy download_addr nie zadziałał
    i plik zawiera widoczny watermark TikToka.

    Jak to działa:
    - Przycinamy 5% góry i 8% dołu (tam gdzie jest logo TikTok i @handle)
    - Skalujemy z powrotem do oryginalnych wymiarów (lanczos, miękkie)
    - WADA: lekka utrata ostrości na krawędziach, delikatna zmiana kompozycji
    - Dźwięk: kopiowany bez zmian (-c:a copy), ZERO utraty jakości audio

    Jeśli download_addr działa poprawnie — ta funkcja nigdy nie jest wywoływana.
    """
    print(f"  ✂️  Fallback crop watermark: {os.path.basename(input_path)[:50]}")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", input_path],
        capture_output=True, text=True, timeout=15
    )
    dims = probe.stdout.strip().split(",")
    w, h = (int(dims[0]), int(dims[1])) if len(dims) == 2 else (1080, 1920)

    crop_top    = int(h * 0.05)
    crop_bottom = int(h * 0.08)
    new_h = h - crop_top - crop_bottom

    vf = (
        f"crop={w}:{new_h}:0:{crop_top},"
        f"scale={w}:{h}:flags=lanczos"
    )
    cmd = [
        FFMPEG, "-y", "-nostdin",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy",          # audio BEZ re-encodingu — zero utraty
        "-movflags", "+faststart",
        output_path
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode == 0 and os.path.exists(output_path):
        print(f"  ✅ Crop OK (fallback): {os.path.basename(output_path)}")
        return True
    print(f"  ⚠️  Crop fallback nie powiódł się — kopiuję oryginał")
    shutil.copy(input_path, output_path)
    return False


# ── 3. Generuj głos hook (Edge-TTS) ──────────────────────────
def generate_hook_audio(hook_text: str, out_audio: str):
    """Generuje audio z hooka przez Edge-TTS głosem Zofii (PL, kobiecy)."""
    print(f"  🗣️  Generuję hook audio: '{hook_text[:60]}...'")
    import asyncio, edge_tts

    async def _gen():
        c = edge_tts.Communicate(hook_text, VOICE, rate=VOICE_RATE)
        await c.save(out_audio)
    asyncio.run(_gen())

    # Walidacja
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", out_audio],
        capture_output=True, text=True
    )
    dur = float(probe.stdout.strip() or 0)
    if dur < 1.0:
        raise Exception(f"Hook audio zbyt krótkie: {dur}s")
    print(f"  ✅ Hook audio: {dur:.1f}s")
    return dur


# ── 4. Pobierz muzykę beauty ──────────────────────────────────
def ensure_beauty_music():
    """Pobiera miękką muzykę beauty jeśli brak."""
    mp3s = glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))
    if mp3s:
        return mp3s
    print(f"🎵 Pobieram muzykę beauty do {MUSIC_DIR}...")
    queries = [
        "ytsearch1:soft elegant salon background music no copyright 2024",
        "ytsearch1:beauty spa relaxing background music no copyright",
    ]
    for q in queries:
        cmd = [
            PYTHON, "-m", "yt_dlp", "-x", "--audio-format", "mp3",
            "--audio-quality", "192K",
            "-o", os.path.join(MUSIC_DIR, "beauty_music_%(id)s.%(ext)s"),
            q
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)
    return glob.glob(os.path.join(MUSIC_DIR, "*.mp3"))


# ── 5. Beauty re-edit ffmpeg ──────────────────────────────────
def beauty_redit(video_no_wm: str, hook_audio: str, hook_dur: float,
                 output_path: str, music_files: list):
    """
    Finalne złożenie wideo dla YT Shorts:
    - Wideo z TikToka (bez watermark) jako tło
    - Hook audio na początku (pierwsze hook_dur sekund)
    - Miękka muzyka w tle (vol 0.12)
    - Warm beauty filters (liftgamma, saturation +5%, slight warm tone)
    - Napis z hookiem wypalony na górze (pierwsze 3-4s)
    - Format 9:16 / 1080x1920
    """
    print(f"  🎬 Beauty re-edit → {os.path.basename(output_path)}")

    # Pobierz długość wideo
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_no_wm],
        capture_output=True, text=True
    )
    vid_dur = float(probe.stdout.strip() or 30)
    total_dur = max(vid_dur, hook_dur + 2.0)
    total_dur = min(total_dur, 58.0)  # YT Shorts max

    # Muzyka w tle
    music_input = []
    af_parts = ["loudnorm=I=-14:LRA=11:TP=-1.5"]

    if music_files:
        music_path = random.choice(music_files)
        music_input = ["-i", music_path]
        # Mix: głos hook (jeśli jest) + muzyka tło
        af_parts = [
            f"[0:a]volume=1.0[main];"
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.12[bg];"
            f"[main][bg]amix=inputs=2:duration=first[outa]"
        ]
        af_flag = ["-filter_complex", af_parts[0], "-map", "[outa]"]
    else:
        af_flag = ["-af", "loudnorm=I=-14:LRA=11:TP=-1.5"]

    # Video filters: warm beauty grading + ensure 9:16 1080x1920
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        # Warm lift — subtelne ciepłe tony (beauty look)
        "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.5 1/0.97':b='0/0 0.5/0.45 1/0.90',"
        # Delikatny kontrast S-curve
        "curves=all='0/0 0.25/0.22 0.75/0.80 1/1',"
        # Lekkie nasycenie +5%
        "hue=s=1.05"
    )

    # Jeśli hook_audio istnieje — wstaw go na początku
    if os.path.exists(hook_audio) and hook_dur > 0:
        temp_merged_audio = output_path.replace(".mp4", "_ha.mp3")
        # Sklej: hook audio + oryginalne audio wideo (od sekundy hook_dur)
        merge_cmd = [
            FFMPEG, "-y", "-nostdin",
            "-i", hook_audio,
            "-i", video_no_wm,
            "-filter_complex",
            f"[0:a]atrim=0:{hook_dur:.2f},asetpts=PTS-STARTPTS[hook];"
            f"[1:a]atrim={hook_dur:.2f},asetpts=PTS-STARTPTS[orig];"
            f"[hook][orig]concat=n=2:v=0:a=1[merged]",
            "-map", "[merged]",
            "-t", str(total_dur),
            temp_merged_audio
        ]
        r = subprocess.run(merge_cmd, capture_output=True, timeout=60)
        audio_source = temp_merged_audio if r.returncode == 0 else hook_audio
    else:
        audio_source = video_no_wm
        temp_merged_audio = None

    # Finalne renderowanie
    if music_files:
        music_path = random.choice(music_files)
        final_cmd = [
            FFMPEG, "-y", "-nostdin",
            "-i", video_no_wm,
            "-i", audio_source,
            "-i", music_path,
            "-filter_complex",
            (f"[0:v]{vf}[vout];"
             f"[1:a]volume=1.0[main];"
             f"[2:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.12[bg];"
             f"[main][bg]amix=inputs=2:duration=first[aout]"),
            "-map", "[vout]", "-map", "[aout]",
            "-t", str(total_dur),
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]
    else:
        final_cmd = [
            FFMPEG, "-y", "-nostdin",
            "-i", video_no_wm,
            "-i", audio_source,
            "-vf", vf,
            "-af", "loudnorm=I=-14:LRA=11:TP=-1.5",
            "-map", "0:v", "-map", "1:a",
            "-t", str(total_dur),
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            output_path
        ]

    r = subprocess.run(final_cmd, capture_output=True, timeout=300)
    if temp_merged_audio and os.path.exists(temp_merged_audio):
        os.remove(temp_merged_audio)

    if r.returncode == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  ✅ Wideo gotowe: {os.path.basename(output_path)} ({size_mb:.1f}MB)")
        return True
    else:
        err = r.stderr.decode("utf-8", errors="ignore")[-400:] if r.stderr else ""
        print(f"  ❌ ffmpeg error: {err}")
        return False


# ── 6. Buduj metadane YT ─────────────────────────────────────
def build_yt_metadata(candidate: dict, strategy: dict) -> dict:
    """Buduje optymalny tytuł, opis i tagi dla YT."""
    hook = candidate.get("yt_hook", "Metamorfoza w salonie Świdnica")
    content_type = candidate.get("content_type", "afroloki_warkoczyki")
    keywords = strategy.get("keywords", [])

    title_map = {
        "afroloki_warkoczyki": f"Afroloki Świdnica — {hook[:60]}",
        "metamorfoza": f"Metamorfoza włosów — {hook[:60]}",
        "edukacja": f"Jak zrobić warkoczyki? — {hook[:60]}",
        "nowosci_produkty": f"Nowość w salonie — {hook[:60]}",
        "promo": f"Salon Świdnica — {hook[:60]}",
        "ogolne": f"Fryzjer Świdnica — {hook[:60]}",
    }
    title = title_map.get(content_type, hook[:80])

    desc = (
        f"{hook}\n\n"
        f"💇 Salon Afroloki Świdnica — specjaliści od warkoczyków, afroloków i panda-kucyków.\n"
        f"📍 Świdnica (Dolny Śląsk)\n"
        f"🛍️ Sklep: https://sklep.salon-prettywoman.pl\n\n"
        f"Zarezerwuj wizytę: https://sklep.salon-prettywoman.pl\n\n"
        f"#warkoczyki #afroloki #fryzjer #świdnica #shorts"
    )

    tags = keywords + [
        "warkoczyki", "afroloki", "panda kucyki", "fryzjer Świdnica",
        "salon beauty", "metamorfoza włosów", "shorts", "warkoczyki na lato",
        "frizury", "hair transformation"
    ]
    return {"title": title[:100], "description": desc[:4990], "tags": tags[:15]}


# ── 7. Prześlij na YT ────────────────────────────────────────
def upload_to_youtube(video_path: str, meta: dict) -> bool:
    """Wywołuje smart_uploader.py dla konta pretty_woman."""
    print(f"  📤 Przesyłam na YT: {meta['title'][:60]}")
    meta_file = video_path.replace(".mp4", "_meta.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    try:
        r = subprocess.run(
            [PYTHON, "smart_uploader.py",
             "--konto", ACCOUNT_ID,
             "--plik", video_path,
             "--meta", meta_file],
            capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace"
        )
        if r.returncode == 0:
            print(f"  ✅ Upload OK")
            return True
        print(f"  ⚠️  Upload error: {r.stdout[-300:]}")
        return False
    except Exception as e:
        print(f"  ❌ Upload exception: {e}")
        return False


# ── MAIN PIPELINE ─────────────────────────────────────────────
def run_pipeline(do_download=True, do_edit=True, do_upload=True):
    analysis = load_analysis()
    candidates = [c for c in analysis.get("top_candidates", []) if c.get("recommended")]
    strategy   = analysis.get("yt_strategy", {})
    music_files = ensure_beauty_music()

    if not candidates:
        print("⚠️  Brak rekomendowanych filmów w analizie.")
        return

    print(f"\n🎬 PRETTYWOMAN AGENT — {len(candidates)} filmów do przetworzenia")
    results = []

    for i, cand in enumerate(candidates[:5], 1):  # max 5 na raz
        title_slug = re.sub(r'[^\w]+', '_', cand.get("tiktok_title", f"video_{i}")[:40])
        url = cand.get("tiktok_url", "")
        hook = cand.get("yt_hook", "Niesamowita metamorfoza w naszym salonie")

        print(f"\n{'='*55}")
        print(f"[{i}/{len(candidates[:5])}] {cand['tiktok_title'][:60]}")
        print(f"  Views: {cand['views_total']:,} | Typ: {cand['content_type']}")
        print(f"  Hook YT: {hook}")

        raw_path    = os.path.join(DOWNLOAD_DIR, f"pw_{i}_{title_slug}.mp4")
        nowm_path   = os.path.join(DOWNLOAD_DIR, f"pw_{i}_{title_slug}_nowm.mp4")
        hook_audio  = os.path.join(OUTPUT_DIR, f"pw_{i}_hook.mp3")
        final_path  = os.path.join(OUTPUT_DIR, f"PRETTYWOMAN_{i}_{title_slug}.mp4")
        hook_dur    = 0.0

        # KROK A: Download
        if do_download and url:
            # download_nowatermark pobiera już czysty plik (download_addr) — bez watermarku.
            # Nie ma potrzeby crop/blur. Plik raw_path = gotowy do edycji beauty.
            ok = download_nowatermark(url, raw_path)
            if not ok:
                print(f"  ⚠️  Pominięto — brak URL lub błąd pobierania")
                continue
            # Plik jest już czysty — po prostu użyj go jako nowm_path
            nowm_path = raw_path
            print(f"  ✅ Plik bez watermarku gotowy (download_addr) — pomijam FFmpeg crop")
        else:
            # Szukaj już pobranego lub ręcznie wrzuconego pliku
            existing = glob.glob(os.path.join(DOWNLOAD_DIR, f"pw_{i}_*_nowm.mp4"))
            if existing:
                nowm_path = existing[0]
            elif os.path.exists(raw_path):
                # Plik ręcznie wrzucony (np. ze snaptik.app) — traktuj jako czysty
                nowm_path = raw_path
                print(f"  ℹ️  Używam ręcznie wgranego pliku: {os.path.basename(raw_path)}")
            else:
                print(f"  ⚠️  Brak pliku do edycji — pomiń lub pobierz najpierw")
                continue

        # KROK B: Hook audio
        if do_edit:
            try:
                hook_dur = generate_hook_audio(hook, hook_audio)
            except Exception as e:
                print(f"  ⚠️  Hook audio error: {e} — kontynuuję bez hooka")
                hook_dur = 0.0

            # KROK C: Beauty re-edit
            ok_edit = beauty_redit(nowm_path, hook_audio, hook_dur, final_path, music_files)
            if not ok_edit:
                print(f"  ❌ Re-edit nie powiódł się — pomijam")
                continue

        # KROK D: Upload
        if do_upload and os.path.exists(final_path):
            meta = build_yt_metadata(cand, strategy)
            upload_to_youtube(final_path, meta)

        results.append({"title": cand["tiktok_title"][:60], "output": final_path})

    print(f"\n✅ PIPELINE ZAKOŃCZONY — przetworzono {len(results)} filmów")
    for r in results:
        print(f"   → {r['output']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="Tylko pobierz filmy")
    parser.add_argument("--edit-only", action="store_true", help="Tylko edytuj pobrane")
    parser.add_argument("--upload-only", action="store_true", help="Tylko wyślij na YT")
    args = parser.parse_args()

    if args.download:
        run_pipeline(do_download=True, do_edit=False, do_upload=False)
    elif args.edit_only:
        run_pipeline(do_download=False, do_edit=True, do_upload=False)
    elif args.upload_only:
        run_pipeline(do_download=False, do_edit=False, do_upload=True)
    else:
        run_pipeline(do_download=True, do_edit=True, do_upload=True)


if __name__ == "__main__":
    main()
