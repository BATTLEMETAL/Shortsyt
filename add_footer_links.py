import os, re

site_dir = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt"
files = [f for f in os.listdir(site_dir) if f.endswith('.html') and f not in ['polityka-prywatnosci.html', '404.html']]

for fname in files:
    path = os.path.join(site_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Dodaj link do polityki prywatnosci w footer jesli nie ma
    if 'polityka-prywatnosci.html' not in content:
        content = content.replace(
            '<span>\u00a9 2026 ShortsYT Agency. Wszelkie prawa zastrze\u017cone.</span>',
            '<span>\u00a9 2026 ShortsYT Agency. Wszelkie prawa zastrze\u017cone. \u00b7 <a href="polityka-prywatnosci.html" style="color:var(--text-muted);text-decoration:none;">Polityka Prywatno\u015bci</a></span>'
        )

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated footer: {fname}")

print("\nDone!")
