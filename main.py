import os
import joblib
import argparse
from dotenv import load_dotenv

# Importowanie funkcji z Twoich pozostałych modułów
from analyze_video_features import zmontuj_shorta_z_ai
from generate_thumbnail import create_thumbnail
from data_collector import generuj_metadane  # Załóżmy, że ta funkcja jest tutaj

# --- USTAWIENIA ---
MODEL_PATH = "video_success_model.pkl"  # Ścieżka do zapisanego, wytrenowanego modelu
INPUT_VIDEO_DIR = "videos"  # Folder z długimi filmami do cięcia
OUTPUT_DIR = "temp_videos"  # Folder na wyjściowe shorty i miniaturki


def main():
    """Główna funkcja orkiestrująca cały proces."""

    # Wczytanie klucza API z pliku .env dla bezpieczeństwa
    load_dotenv()
    gemini_api_key = os.getenv("haslo")
    if not gemini_api_key:
        print("❌ Błąd: Klucz GEMINI_API_KEY nie został znaleziony. Upewnij się, że masz plik .env.")
        return

    # 1. Konfiguracja argumentów linii poleceń
    parser = argparse.ArgumentParser(description="Automatyczny kreator YouTube Shorts z długich filmów.")
    parser.add_argument("--video", required=True, help="Nazwa pliku wideo w folderze 'videos' (np. 'moj_film.mp4').")
    parser.add_argument("--topic", required=True, help="Główny temat filmu, np. 'Niesamowity zwrot akcji w Valorant'.")
    args = parser.parse_args()

    input_video_path = os.path.join(INPUT_VIDEO_DIR, args.video)

    # Sprawdzenie, czy pliki istnieją
    if not os.path.exists(input_video_path):
        print(f"❌ Błąd: Nie znaleziono pliku wideo: {input_video_path}")
        return

    if not os.path.exists(MODEL_PATH):
        print(f"❌ Błąd: Nie znaleziono wytrenowanego modelu: {MODEL_PATH}")
        print("   > Uruchom najpierw skrypt 'train_model.py', aby go stworzyć.")
        return

    # 2. Wczytanie wytrenowanego modelu AI
    print(f"🧠 Wczytuję model predykcyjny z pliku: {MODEL_PATH}...")
    try:
        model = joblib.load(MODEL_PATH)
    except Exception as e:
        print(f"❌ Nie udało się wczytać modelu: {e}")
        return

    # 3. Uruchomienie inteligentnego montażu
    output_short_path = os.path.join(OUTPUT_DIR, f"short_{os.path.basename(input_video_path)}")
    zmontuj_shorta_z_ai(input_video_path, model, output_short_path)

    if not os.path.exists(output_short_path):
        print("🔴 Montaż nie powiódł się. Prerywam działanie.")
        return

    # 4. Generowanie metadanych (tytuł, opis, tagi)
    tytul, opis, tagi = generuj_metadane(args.topic, gemini_api_key)
    print("\n--- Wygenerowane Metadane ---")
    print(f"Tytuł: {tytul}")
    print(f"Opis: {opis}")
    print(f"Tagi: {', '.join(tagi)}")
    print("-----------------------------\n")

    # 5. Tworzenie miniaturki
    create_thumbnail(output_short_path, tytul)

    print("\n🎉🎉🎉 Proces zakończony sukcesem! 🎉🎉🎉")
    print(f"Gotowy Short: {output_short_path}")
    print(f"Gotowa Miniaturka: {os.path.join(OUTPUT_DIR, 'thumbnail.jpg')}")
    print("\nTeraz możesz uruchomić 'smart_uploader.py', aby wysłać klip na YouTube.")


if __name__ == '__main__':
    main()