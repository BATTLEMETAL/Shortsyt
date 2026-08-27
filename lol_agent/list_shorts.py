"""Pobiera listę top shortów z kanału i wyświetla metadane."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import subprocess

result = subprocess.run([
    "python", "-m", "yt_dlp",
    "--flat-playlist",
    "--print", "%(title)s|||%(url)s|||%(duration)s",
    "--playlist-items", "1-6",
    "https://www.youtube.com/@Dwannellenga/shorts"
], capture_output=True, text=True, encoding='utf-8', errors='replace')

print("=== TOP SHORTY DWANNELLENGA ===")
for line in result.stdout.strip().split('\n'):
    if '|||' in line:
        parts = line.split('|||')
        title = parts[0].strip()
        url = parts[1].strip() if len(parts) > 1 else ''
        dur = parts[2].strip() if len(parts) > 2 else '?'
        print(f"  [{dur}s] {title}")
        print(f"         {url}")
    elif line.strip():
        print(f"  {line}")

if result.stderr:
    print("\nSTDERR:", result.stderr[:500])
