"""Pobiera top 3 shorty z Dwannellenga i zapisuje do ref_downloads/"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import subprocess, os

out_dir = r'C:\Users\mz100\PycharmProjects\shortsyt\temp_videos\ref_downloads'
os.makedirs(out_dir, exist_ok=True)

# Próbuj różnych URL-i kanału
urls_to_try = [
    "https://www.youtube.com/@Dwannellenga",
    "https://www.youtube.com/c/Dwannellenga",
]

for url in urls_to_try:
    print(f"\n🔍 Próbuję: {url}")
    r = subprocess.run([
        "python", "-m", "yt_dlp",
        "--flat-playlist",
        "--print", "%(title)s|||%(webpage_url)s|||%(duration)s",
        "--playlist-items", "1-5",
        "--match-filter", "duration < 90",
        url
    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

    lines = [l for l in r.stdout.strip().split('\n') if '|||' in l]
    if lines:
        print(f"✅ Znaleziono {len(lines)} filmów:")
        for line in lines:
            parts = line.split('|||')
            print(f"  [{parts[2].strip() if len(parts)>2 else '?'}s] {parts[0].strip()}")
            print(f"       {parts[1].strip() if len(parts)>1 else ''}")
        
        # Pobierz top 2
        top_urls = [l.split('|||')[1].strip() for l in lines[:2] if len(l.split('|||')) > 1]
        for i, vurl in enumerate(top_urls):
            print(f"\n⬇️  Pobieram short #{i+1}: {vurl}")
            dl = subprocess.run([
                "python", "-m", "yt_dlp",
                "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
                "-o", os.path.join(out_dir, f"ref_{i+1}.%(ext)s"),
                "--merge-output-format", "mp4",
                vurl
            ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            if dl.returncode == 0:
                print(f"  ✅ Pobrano ref_{i+1}.mp4")
            else:
                print(f"  ❌ Błąd: {dl.stderr[:200]}")
        break
    else:
        print(f"  ❌ Brak wyników, stderr: {r.stderr[:200]}")
