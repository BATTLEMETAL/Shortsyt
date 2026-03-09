import os
import sys
import json
from data_collector import get_authenticated_service
from agent_dark_psychology import generate_viral_script, get_forbidden_topics, add_to_history, NICHE_BASE, PROFILE_NAME, TOPIC_HISTORY_FILE

def run_stress_test():
    print("🧠 --- STRESS TEST DEDUPLIKACJI (5 FILMÓW Z RZĘDU) --- 🧠\n")
    
    # Kopia zapasowa historii
    backup_history = None
    if os.path.exists(TOPIC_HISTORY_FILE):
        with open(TOPIC_HISTORY_FILE, 'r', encoding='utf-8') as f:
            backup_history = f.read()

    try:
        niche_rule = """STRUCTURE: Viral Micro-Hook-Trick-Warning (DARK PSYCHOLOGY / 10-15 SECONDS).
FORMAT OF EACH SHORT (CHOOSE ONE RANDOMLY AND NEVER REPEAT):
- FORMAT A (Single Trick): HOOK (one shocking behavioral fact) -> TRICK (what the technique does to the brain) -> CTA ("Try this tonight. Notice what changes.")
- FORMAT B (List): "3 signs they're manipulating you right now. 1... 2... 3. Protect yourself."
- FORMAT C (Warning): "Stop doing this. It instantly reveals your weakness. Here is why."
RULES:
1. HOOK must promise a dark secret or reveal danger in the first 1.5 seconds.
2. NEVER use the word 'forehead'. Choose a fresh, DIFFERENT behavioral or psychological concept each time.
3. The script LOOP: last sentence ends with an open question or connects back to the first.
4. English. Cold, analytical tone. MAX 25-30 words. Longer = failure.
5. Always end with ONE CTA question: 'Would you use this?' OR 'Want part 2?'"""

        for i in range(1, 6):
            print(f"\n🎬 === GENERACJA {i}/5 ===")
            forbidden = get_forbidden_topics(PROFILE_NAME, limit=15)
            print(f"🚫 Zabronionych słów kluczowych/tematów w pamięci: {len(forbidden)}")
            
            # Wymuś mniejszy kontekst żeby skupić się na prompcie
            viral_context = ["TYTUŁ: Psychology Tricks | OPIS: Manipulate anyone."]

            director_json = generate_viral_script(viral_context, NICHE_BASE, niche_rule, forbidden)
            if not director_json or "error" in director_json:
                print(f"Błąd wejścia Synapsy: {director_json.get('error', 'Unknown')}")
                continue

            script_text = director_json.get('script_text', '')
            title = director_json.get('title', 'Test Title')
            
            print(f"✅ Tytuł: {title}")
            print(f"📝 Skrypt: {script_text}")
            
            # Zapisz do historii, co od razu powiększy listę 'forbidden' dla kolejnej iteracji
            add_to_history(PROFILE_NAME, title, script_text=script_text)
            
    finally:
        # Przywróć oryginalną historię żeby nie śmiecić głównych logów po teście
        if backup_history is not None:
            with open(TOPIC_HISTORY_FILE, 'w', encoding='utf-8') as f:
                f.write(backup_history)
        print("\n🧹 Skasowano logi testowe. Oryginalna historia przywrócona.")

if __name__ == "__main__":
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    run_stress_test()
