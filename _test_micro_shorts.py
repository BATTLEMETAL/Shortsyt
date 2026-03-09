import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["PYTHONIOENCODING"] = "utf-8"

from agent_dark_psychology import generate_viral_script, get_forbidden_topics, PROFILE_NAME, NICHE_BASE, CHANNELS_NICHES

print("--- TEST MICRO SHORTS (15s GENERATION) ---")

forbidden = get_forbidden_topics(PROFILE_NAME)
niche_rule = CHANNELS_NICHES.get(PROFILE_NAME, {}).get('prompt', 
"""STRUKTURA VIRALOWA MICRO-SHORT (Hook-Trick-Warning):
1. HOOK (0-2s): Jedno uderzające zdanie. SZOK/PYTANIE. Wzorzec: 'They don't want you to know this...'
2. TRICK (1-2 zdania): Konkret, sedno techniki. BARDZO ZWIĘŹLE. BEZ MIESZANIA KILKU FAKTÓW.
3. WARNING (1 zdanie): Mroczne, urwane ostrzeżenie.
4. LOOP: Koniec i początek muszą tworzyć pętlę.
Celuj w MAX 10-15 sekund czytania (TYLKO 20-35 słów). Angielski. Zimny, analityczny ton. Skrypt POWYŻEJ 35 słów to błąd!""")

print(f"Forbidden topics count: {len(forbidden) if forbidden else 0}")
print("Generating script...")

director_json = generate_viral_script([], NICHE_BASE, niche_rule, forbidden)

if director_json and "error" in director_json:
    print(f"API ERROR: {director_json['error']}")
else:
    script = director_json.get('script_text', '')
    words = len(script.split())
    print("\n--- GENERATED SCRIPT ---")
    print(script)
    print(f"\nWord count: {words}")
    if 10 <= words <= 40:
        print("✅ LENGTH OK (Under 15s)")
    else:
        print("❌ LENGTH FAILED")
