import os
import argparse
import shutil
import joblib  # POPRAWKA: Dodano brakujący import
from dotenv import load_dotenv

# --- KROK 1: Importujemy specjalistów z Twoich istniejących plików ---
# POPRAWKA: Dostosowano nazwy plików i funkcji do Twojego projektu
from outplayed_integration import find_best_clip
from video_audio_tools import normalize_audio, generate_and_burn_subtitles
from generate_thumbnail import create_thumbnail
from upload_youtube import get_authenticated_service, upload_video
from analyze_video_features import zmontuj_shorta_z_ai
from data_collector import generuj_metadane

# --- USTAWIENIA ---
# POPRAWKA: Używamy Twojej nazwy pliku z modelem
MODEL_PATH = "model_stylu.pkl"
TEMP_DIR = "temp_videos"


def run_automatic_pipeline(topic: str):
    """
    Uruchamia pełny, zautomatyzowany proces tworzenia i publikacji shorta na podstawie podanego tematu.
    """
    print("🚀🚀🚀 STARTUJĘ PEŁNY AUTOMATYCZNY PIPELINE 🚀🚀🚀")

    # Bezpieczne wczytanie klucza API
    load_dotenv()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        print("❌ BŁĄD KRYTYCZNY: Klucz GEMINI_API_KEY nie został znaleziony w pliku .env.")
        return

    try:
        # === ETAP 1: ZNAJDŹ NAJLEPSZY KLIP ===
        print("\n--- ETAP 1: Wyszukiwanie klipu do przetworzenia ---")
        # POPRAWKA: Używamy Twojej funkcji 'find_best_clip'
        source_video_path = find_best_clip()

        if not source_video_path:
            print("✅ Zakończono pracę. Brak nowych klipów do przetworzenia.")
            return

        print(f"✅ Znaleziono i zarchiwizowano klip: {os.path.basename(source_video_path)}")

        if not os.path.exists(TEMP_DIR):
            os.makedirs(TEMP_DIR)

        ai_clip_path = os.path.join(TEMP_DIR, "ai_selected_clip.mp4")
        normalized_audio_path = os.path.join(TEMP_DIR, "normalized_audio.mp4")
        final_clip_path = os.path.join(TEMP_DIR, "final_short_with_subs.mp4")
        thumbnail_path = os.path.join(TEMP_DIR, "final_thumbnail.jpg")

        # === ETAP 2: MONTAŻ Z UŻYCIEM PERSONALIZOWANEJ AI ===
        print("\n--- ETAP 2: Analiza i montaż z użyciem Twojego modelu AI ---")
        if not os.path.exists(MODEL_PATH):
            print(f"❌ BŁĄD KRYTYCZNY: Nie znaleziono pliku modelu '{MODEL_PATH}'.")
            print("   > Uruchom 'model_trainer.py' aby go stworzyć.")
            return

        model = joblib.load(MODEL_PATH)
        print("🧠 Spersonalizowany model AI załadowany.")
        zmontuj_shorta_z_ai(source_video_path, model, ai_clip_path)

        # === ETAP 3: ULEPSZANIE JAKOŚCI WIDEO I AUDIO ===
        print("\n--- ETAP 3: Ulepszanie jakości dźwięku i dodawanie napisów ---")
        normalize_audio(ai_clip_path, normalized_audio_path)
        generate_and_burn_subtitles(normalized_audio_path, final_clip_path)

        # === ETAP 4: TWORZENIE MATERIAŁÓW MARKETINGOWYCH ===
        print("\n--- ETAP 4: Generowanie tytułu, opisu i miniaturki przez AI ---")
        tytul, opis, tagi = generuj_metadane(topic, gemini_api_key)
        print(f"   - Wygenerowany tytuł: {tytul}")

        # Tworzymy miniaturkę, przekazując pełną ścieżkę zapisu
        create_thumbnail(final_clip_path, tytul.upper(), thumbnail_path)

        # === ETAP 5: PUBLIKACJA NA YOUTUBE ===
        print("\n--- ETAP 5: Wysyłanie gotowego shorta na YouTube ---")
        youtube_service = get_authenticated_service()
        upload_video(
            youtube=youtube_service,
            file_path=final_clip_path,
            title=tytul,
            description=opis,
            tags=tagi,
            category_id="27",  # POPRAWKA: Kategoria 27 = Edukacja (Cash Cow / Poradniki / Wiedza)
            privacy_status="private",
            thumbnail_path=thumbnail_path
        )

        print("\n🎉🎉🎉 PIPELINE ZAKOŃCZONY SUKCESEM! 🎉🎉🎉")

    except Exception as e:
        print(f"\n❌❌❌ WYSTĄPIŁ KRYTYCZNY BŁĄD W PIPELINE: {e} ❌❌❌")

    finally:
        # Automatyczne sprzątanie plików tymczasowych
        if os.path.exists(TEMP_DIR):
            print(f"\n🧹 Sprzątam pliki tymczasowe z folderu '{TEMP_DIR}'...")
            shutil.rmtree(TEMP_DIR)
            print("✅ Sprzątanie zakończone.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Shortsyt - Automatyczny system do tworzenia i publikacji shortów.")
    parser.add_argument(
        '--topic',
        type=str,
        required=True,
        help='Główny temat filmu, potrzebny do wygenerowania tytułu i opisu, np. "Niesamowity clutch w Valorant".'
    )
    args = parser.parse_args()

    run_automatic_pipeline(args.topic)