import sys, ast
sys.stdout.reconfigure(encoding="utf-8")

files = [
    "smart_video_analyzer.py",
    "agent_dark_psychology.py",
    "cashcow_generator.py",
]

all_ok = True
for f in files:
    try:
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        ast.parse(src)
        print(f"  OK  {f} ({len(src)//1024}KB)")
    except SyntaxError as e:
        print(f"  ERR {f}: {e}")
        all_ok = False

print()
print("=== WERYFIKACJA KONFIGURACJI ===")

with open("agent_dark_psychology.py", encoding="utf-8") as f:
    ag = f.read()
print("  Category 27 (Education):   ", "OK" if 'category_id="27"' in ag else "BRAK")
print("  Body language focus pool:  ", "OK" if "body language command respect" in ag else "BRAK")
print("  Sigma/narcissist removed:  ", "OK" if "narcissist manipulation" not in ag else "POZOSTAJE")

with open("cashcow_generator.py", encoding="utf-8") as f:
    cg = f.read()
print("  Audio -ar 44100:           ", "OK" if "'-ar', '44100'" in cg else "BRAK")
print("  aresample=44100:           ", "OK" if "aresample=44100" in cg else "BRAK")
print("  -r 30 fps:                 ", "OK" if "'-r', '30'" in cg else "BRAK")
print("  faststart:                 ", "OK" if "faststart" in cg else "BRAK")

with open("smart_video_analyzer.py", encoding="utf-8") as f:
    sv = f.read()
print("  classify_video_performance:", "OK" if "classify_video_performance" in sv else "BRAK")
print("  SUPPRESSED state:          ", "OK" if "SUPPRESSED" in sv else "BRAK")
print("  MISS state:                ", "OK" if "MISS" in sv else "BRAK")
print("  TOO_YOUNG state:           ", "OK" if "TOO_YOUNG" in sv else "BRAK")
print("  Gap detection 48h:         ", "OK" if "gap_h > 48" in sv else "BRAK")
print("  Timezone CEST fix:         ", "OK" if "CEST" in sv else "BRAK")

print()
print("=== SYNTAX OK ==" if all_ok else "=== BLEDY SKLADNI ===")
