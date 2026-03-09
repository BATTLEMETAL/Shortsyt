import os
import subprocess
import time
from datetime import datetime
import json

# Wypisywanie znaków emoji bezpieczne dla Windows Powershell.
os.environ["PYTHONIOENCODING"] = "utf-8"

def run_daily_campaign():
    print("===================================================================")
    print("🚀 KAMPAŃIA 'DAILY SHORTS' ROZPOCZĘTA (BEZPIECZEŃSTWO ALGORYTMU)")
    print("===================================================================")
    
    # Lista zadań profilowanych na każdy dzień
    tasks = [
        {"konto": "brainrot", "nisza": "roblox brainrot stories"},
        {"konto": "dark_mindset", "nisza": "dark psychology secrets"}
    ]
    
    print(f"Zaplanowano generacji: {len(tasks)}")
    print("System będzie budował produkcje po kolei, by nie przeciążać pamięci oraz bezpiecznie wysyłał je jedną po drugiej do kalendarza na YouTube (Prywatne & Zaplanowane).")
    
    for i, t in enumerate(tasks):
        print(f"\n--- [ {i+1} / {len(tasks)} ] Uruchamiam proces dystrybucji dla: {t['konto']} ---")
        
        # Wywołujemy bezpiecznie w izolowanym procesie, po kolei
        cmd = [
            ".\\venv313\\Scripts\\python.exe",
            "one_click_cashcow.py",
            "--konto", t["konto"],
            "--nisza", t["nisza"]
        ]
        
        # FIX AUDYT: Dodano timeout=3600s (1h max) i encoding jawny
        result = subprocess.run(cmd, capture_output=True, timeout=3600)
        
        stdout_text = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
        stderr_text = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
        
        if result.returncode == 0:
            print(f"✅ Maszyna One-Click Cash Cow pomyślnie złożyła film i wysłała na serwery YouTube dla kanału {t['konto']}.")
            print("Fragment logów uploadera:")
            # Wypiszmy czysty log ze statsami z końcówki:
            lines = stdout_text.split("\n")
            for line in lines[-15:]:
                if "WALIDACJA" in line or "✅" in line or "Przeszło" in line or "USTAWIAM" in line or "Wysłano" in line or "Link:" in line:
                    print(f"   {line.strip()}")
        else:
            print(f"❌ Wystąpił błąd w generacji profilu {t['konto']}:")
            print(stderr_text[-500:]) # Wyświetl ostatnie błędy
            
        # Zabezpieczenie anty-ban (Timeout pomiędzy prośbami do YouTube API)
        if i < len(tasks) - 1:
            wait_time = 15
            print(f"\n⏳ Zarządzam {wait_time} sekund ochrony przed spamem YouTube API zanim przejdę do drugiego kanału...")
            time.sleep(wait_time)
            
    print("\n===================================================================")
    print("🎉 KAMPAŃIA DAILY ZAKOŃCZONA! Filmy wygenerowane, zmontowane i bezpiecznie przekazane kalendarzom YouTube'a.")

if __name__ == "__main__":
    run_daily_campaign()
