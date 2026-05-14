import os, re

site_dir = r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt"
files = [f for f in os.listdir(site_dir) if f.endswith('.html')]

for fname in files:
    path = os.path.join(site_dir, fname)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix canonical/og URLs — stara domena -> realna domena
    content = content.replace('https://shortsyt.pl', 'https://shortsyt.salon-prettywoman.pl')

    # 2. Fix Agency FAQ inconsistency (3-miesięczna umowa -> bez umowy)
    content = content.replace(
        'Pakiet Agency wymaga umowy na 3 miesi\u0105ce.',
        'Wszystkie pakiety dzia\u0142aj\u0105 bez umowy — mo\u017cesz zako\u0144czy\u0107 wsp\u00f3\u0142prac\u0119 z miesi\u0119cznym uprzedzeniem.'
    )

    # 3. Fix footer copyright year
    content = content.replace('\u00a9 2025 ShortsYT Agency', '\u00a9 2026 ShortsYT Agency')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed: {fname}")

# Weryfikacja
index_path = os.path.join(site_dir, 'index.html')
with open(index_path, 'r', encoding='utf-8') as f:
    c = f.read()

print()
print("=== WERYFIKACJA ===")
canon_ok = 'canonical.*shortsyt.salon-prettywoman.pl' in c or 'canonicalhref="https://shortsyt.salon-prettywoman.pl' in c
# Simple check
if 'shortsyt.salon-prettywoman.pl' in c and 'canonical' in c:
    print("[OK] Canonical URL: https://shortsyt.salon-prettywoman.pl")
else:
    print("[ERR] Canonical URL nadal bledny")

if 'mz10062001@gmail.com' in c:
    print("[OK] Email: mz10062001@gmail.com")

if '2026 ShortsYT' in c:
    print("[OK] Copyright: 2026")

# Check no old domain left
remaining = c.count('https://shortsyt.pl/')
print(f"[{'OK' if remaining == 0 else 'ERR'}] Stara domena shortsyt.pl: {remaining} pozostalych wystapien")
