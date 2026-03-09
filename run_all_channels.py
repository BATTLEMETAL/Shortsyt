import subprocess
import concurrent.futures
import time
import os
import time

# Zdefiniowane kanały i ich odpowiadające nisze docelowe (Złote Wzorce)
CHANNELS = [
    {"konto": "brainrot", "nisza": "roblox brainrot stories polska"},
    {"konto": "dark_mindset", "nisza": "dark psychology manipulation secrets"}
]

def run_agent_for_channel(channel_config):
    konto = channel_config["konto"]
    nisza = channel_config["nisza"]
    print(f"🚀 [START] Inicjalizacja wątku YouTube bota dla: {konto.upper()}...")
    
    cmd = [
        ".\\venv313\\Scripts\\python.exe", 
        "one_click_cashcow.py", 
        "--konto", konto, 
        "--nisza", nisza
    ]
    
    # Wymuszamy kodowanie utf-8 w podprocesie
    my_env = os.environ.copy()
    my_env["PYTHONIOENCODING"] = "utf-8"
    my_env["PYTHONUTF8"] = "1"
    
    # Tworzymy proces
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=my_env
    )
    
    # Zastępujemy logowanie ciągłym streamem outputu
    print_prefix = f"📺 [{konto.upper()}]: "
    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if line:
            print(f"{print_prefix}{line}")
    
    process.stdout.close()
    return_code = process.wait()
    
    if return_code == 0:
        print(f"✅ [SUKCES] Konto {konto.upper()} zakończyło publikację wideo pomyślnie.")
    else:
        print(f"❌ [BŁĄD] Konto {konto.upper()} zakończyło proces z kodem błędu: {return_code}.")

def main():
    print("=====================================================================")
    print("🔥 GLOBALNY ONE-CLICK CASH COW - PARALLEL MODE (Wrzucanie na Wszystkie Konta)")
    print("=====================================================================")
    
    # KROK 1: BEZPIECZNA WERYFIKACJA LOGOWANIA (SEKWENCYJNA)
    print("🔐 Weryfikacja sesji YouTube. Jeżeli brakuje tokenów, otworzy się przeglądarka.")
    import os
    from upload_youtube import get_authenticated_service
    for ch in CHANNELS:
        konto = ch["konto"]
        print(f"Logowanie / Weryfikacja autoryzacji dla kanału: {konto.upper()}...")
        try:
            get_authenticated_service(konto)
            print(f"✅ Token konta {konto.upper()} jest gotowy.")
        except Exception as e:
            print(f"❌ Problem z logowaniem {konto}: {e}. Operacja może się nie powieść.")
            
    print("\n🚀 Autoryzacja zweryfikowana. Przechodzę do pełnej automatyzacji w tle...")
    print(f"Ilość skonfigurowanych kont do potężnych zasiegów: {len(CHANNELS)}")
    start_time = time.time()
    
    # Uruchomienie asynchronicznych operacji generowania i wgrywania
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(CHANNELS)) as executor:
        futures = [executor.submit(run_agent_for_channel, ch) for ch in CHANNELS]
        concurrent.futures.wait(futures)
        
    duration = time.time() - start_time
    print("=====================================================================")
    print(f"🎉 Zakończono automatyzację YouTube dla WSZYSTKICH KONT jednocześnie! "
          f"(Czas trwania procesu the masowego The: {duration:.1f} sekund)")

if __name__ == "__main__":
    main()
