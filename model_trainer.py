import os
import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

# --- USTAWIENIA ---
DATABASE_FILE = 'video_features.csv'
MODEL_OUTPUT_FILE = 'video_success_model.pkl'  # Ujednolicona nazwa z main.py


def train_model():
    """Główna funkcja do wczytywania danych, trenowania i zapisywania modelu."""

    # 1. Sprawdź, czy plik z danymi istnieje
    if not os.path.exists(DATABASE_FILE):
        print(f"❌ BŁĄD: Plik '{DATABASE_FILE}' nie został znaleziony.")
        print("   > Uruchom najpierw skrypt 'data_collector.py', aby go wygenerować.")
        return

    # 2. Wczytaj dane
    print(f"✅ Wczytuję dane z pliku '{DATABASE_FILE}'...")
    data = pd.read_csv(DATABASE_FILE)

    # Sprawdź, czy mamy wystarczająco dużo danych
    if len(data) < 20:  # Zwiększono próg dla bardziej wiarygodnego modelu
        print(f"⚠️ Ostrzeżenie: Masz tylko {len(data)} filmów. Model może nie być dokładny.")
        print("   > Zbierz więcej danych (rekomendowane 50+), aby uzyskać lepsze wyniki.")

    # 3. Przygotuj dane do treningu
    features = [
        'avg_motion',
        'avg_color_r',
        'avg_color_g',
        'avg_color_b',
        'avg_volume'
    ]

    X = data[features]
    y = data['sukces']

    # Sprawdź, czy mamy przykłady obu klas
    if len(y.unique()) < 2:
        print("❌ BŁĄD: W Twoich danych wszystkie filmy są oznaczone tak samo (wszystkie jako 'sukces' lub 'porażka').")
        print("   > Model nie może się niczego nauczyć. Potrzebujesz bardziej zróżnicowanych danych.")
        return

    # 4. Podziel dane na zbiór treningowy i testowy
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y  # stratify zapewnia podobny rozkład klas
    )

    # 5. Stwórz i wytrenuj model
    print("🧠 Rozpoczynam trenowanie modelu AI (Random Forest)...")
    model = RandomForestClassifier(n_estimators=150, random_state=42, class_weight='balanced', min_samples_leaf=3)
    model.fit(X_train, y_train)
    print("✅ Trenowanie zakończone.")

    # 6. Oceń wydajność modelu
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)
    print("\n--- 📊 Ocena Wydajności Modelu ---")
    print(f"Dokładność (Accuracy): {accuracy * 100:.2f}%")
    print("\nSzczegółowy Raport Klasyfikacji:")
    print(classification_report(y_test, predictions, target_names=['Porażka (0)', 'Sukces (1)']))

    # ULEPSZENIE: Wyświetl, które cechy są najważniejsze dla modelu
    print("\n--- ⭐ Najważniejsze Cechy dla Modelu ---")
    feature_importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
    print(feature_importances)
    print("----------------------------------------")

    # 7. Zapisz wytrenowany model do pliku
    joblib.dump(model, MODEL_OUTPUT_FILE)

    print(f"\n🎉 Model został pomyślnie wytrenowany i zapisany w pliku '{MODEL_OUTPUT_FILE}'.")
    print("   > Możesz teraz używać go w skrypcie 'main.py' do tworzenia inteligentnych shortów!")


if __name__ == '__main__':
    train_model()