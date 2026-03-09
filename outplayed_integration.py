import os
import shutil
import glob
from typing import Optional, List

# --- USTAWIENIA ---
USER_HOME_DIR = os.path.expanduser("~")
PROCESSING_DIR = os.path.join(USER_HOME_DIR, "Wideo", "do_montazu")
ARCHIVE_DIR = os.path.join(PROCESSING_DIR, "archiwum")
SUPPORTED_FORMATS = ('*.mp4', '*.mov', '*.mkv')


# --- POPRAWKA ---
# Zmieniamy nazwę funkcji z powrotem na 'find_best_clip',
# aby pasowała do importu w pliku 'smart_uploader.py'.
def find_best_clip() -> Optional[str]:
# --- KONIEC POPRAWKI ---
    """
    Przeszukuje folder 'do_montazu' w poszukiwaniu najnowszego pliku wideo,
    przenosi go do podfolderu 'archiwum', a następnie zwraca nową ścieżkę do tego pliku.
    """
    print(f"📂 Przeszukuję folder: {PROCESSING_DIR}")

    if not os.path.exists(PROCESSING_DIR):
        print(f"🟡 Folder '{PROCESSING_DIR}' nie istniał. Tworzę go teraz.")
        os.makedirs(PROCESSING_DIR)

    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
        print(f"   -> Utworzono podfolder archiwum: {ARCHIVE_DIR}")

    video_files: List[str] = []
    for fmt in SUPPORTED_FORMATS:
        video_files.extend(glob.glob(os.path.join(PROCESSING_DIR, fmt)))

    if not video_files:
        print("✅ Nie znaleziono żadnych nowych klipów do przetworzenia.")
        return None

    try:
        latest_file = max(video_files, key=os.path.getmtime)
    except FileNotFoundError:
        print("🟡 Wygląda na to, że klip zniknął podczas skanowania. Spróbuj ponownie.")
        return None

    file_name = os.path.basename(latest_file)
    archive_path = os.path.join(ARCHIVE_DIR, file_name)

    print(f"✅ Znaleziono najnowszy klip: '{file_name}'.")
    print(f"   -> Przenoszę do archiwum...")
    try:
        shutil.move(latest_file, archive_path)
    except Exception as e:
        print(f"❌ Błąd podczas przenoszenia pliku: {e}")
        return None

    print(f"   -> Gotowy do przetworzenia z lokalizacji: {archive_path}")
    return archive_path


if __name__ == '__main__':
    print("--- 🚀 Uruchamiam test modułu wyszukiwania klipów ---")

    if not os.path.exists(PROCESSING_DIR):
        os.makedirs(PROCESSING_DIR)

    test_file_path = os.path.join(PROCESSING_DIR, "test_clip_123.mp4")
    with open(test_file_path, "w") as f:
        f.write("to jest plik testowy")
    print(f"\nStworzono fałszywy plik do testu: {test_file_path}")

    # Używamy nowej nazwy funkcji w teście
    processed_file = find_best_clip()

    if processed_file:
        print(f"\n✅ Test zakończony sukcesem. Funkcja zwróciła ścieżkę: {processed_file}")
        if os.path.exists(processed_file):
            print("   -> Plik został poprawnie przeniesiony do archiwum.")
        else:
            print("   -> BŁĄD: Plik nie istnieje w docelowej lokalizacji!")
    else:
        print("\n🟡 Test zakończony. Funkcja nie znalazła żadnych plików do przetworzenia.")