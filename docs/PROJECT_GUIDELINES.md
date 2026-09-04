# Shortsyt — Podstawowe Wytyczne Operacyjne i Standardy Architektury (GUIDELINES)

> **Zasada nadrzędna**: Ten dokument zawiera fundamenty techniczne, parametry oraz reguły biznesowe wypracowane w procesie testów produkcyjnych. Wszelkie przyszłe modyfikacje agentów, skryptów i pipeline'u MUSZĄ być zgodne z poniższymi wytycznymi, aby uniknąć regresji.

---

## 1. SMART CAMERA — Kinematyka i Śledzenie Postaci (`lol_agent/smart_camera.py`)

Kamera w Shortsyt odpowiada za dynamiczny, stabilny crop 9:16 z materiału źródłowego 16:9 (1920x1080 -> 608x1080).

### A. Dual-Mode Detekcja Paska Zdrowia Gracza
W League of Legends kolor paska zdrowia gracza zależy od ustawień gry:
- **Standard Mode (Tryb domyślny)**:
  - Pasek gracza nad postacią jest **zielony** (`#42bb27`).
  - Sojusznicy mają paski **niebieskie/cyjanowe**.
  - Wrogowie mają paski **czerwone**.
  - Maska koloru: `((g > 115) & (r < 110) & (b < 100) & ((g - r) > 35) & ((g - b) > 35))`
- **Colorblind Mode (Tryb dla daltonistów)**:
  - Pasek gracza nad postacią jest **złoty** (`#ffd700`).
  - Maska koloru: `((r > 175) & (g > 140) & (b < 95) & ((r - b) > 80) & ((g - b) > 50))`

**Reguła Pre-skanu**:
Przed generowaniem trajektorii moduł próbuje próbkę klatek (co 16 klatkę). Jeśli liczba trafień zielonych przewyższa złote, aktywowany jest tryb `Standard (Green)`.
> **Uwaga**: W trybie Standardowym kolor złoty jest **całkowicie wyłączony z detekcji gracza**. Chroni to kamerę przed ucieczką na złote efekty umiejętności (np. ult Swaina, skrzydła, tarcze), złote wieże i overlaye statystyk.

### B. Maska Wykluczeń (HUD & In-Game Overlays)
Elementy statyczne na ekranie nie mogą wpływać na pozycję gracza:
- Górny scoreboard / KDA: `y < 140`
- Dolny pasek umiejętności: `y > 864`
- Minimapa i sklep: `y > 626 oraz x > 1459`
- Portret i czat: `y > 670 oraz x < 345`
- Lewy margines ekranu: `x < 140`
- **Prawy overlay ze statystykami (Porofessor / Blitz / Mobalytics / Outplayed)**: `x > 1550`

### C. Scalanie Segmentów 1000 HP (Notch Merging)
W LoL paski zdrowia dzielone są pionowymi czarnymi kreskami co 1000 HP. Pasek gracza na klatce składa się z 2 lub więcej prostokątów:
- Warunek scalenia: `abs(cy1 - cy2) <= 4` oraz odległość pozioma krawędzi `<= 15px`.
- Wynik scalenia: `center_x = (cx1 + cx2) / 2`, `area = area1 + area2`.
- Geometria paska: `20 <= cw <= 130`, `4 <= ch <= 16`, `2.2 <= asp <= 20.0`, `area >= 50`.

### D. Kinowa Stabilizacja Kamery (Parametry Płynności)
Aby wyeliminować drgania i niepotrzebne ruchy lewo-prawo:
- **`DEADBAND_PX = 35.0`**: Martwa strefa. Jeśli zmiana pozycji gracza jest mniejsza niż 35px, kamera w ogóle się nie rusza (stabilność statywu).
- **`LERP_ALPHA = 0.20`**: Spokojne, kinowe doganianie gracza.
- **`MAX_PAN_PX = 25`**: Maksymalny dozwolony przesuw kadru na pojedynczą klatkę próbkowania (blokada gwałtownych szarpnięć).
- **`SNAP_DELTA = 280`**: Próg natychmiastowego doskoku (dla Flash, Shunpo Katariny, teleportu).
- **`SMOOTH_WIN = 7`**: Średnia krocząca trajektorii. Zapewnia brak opóźnień (lagu) za akcją.
- **`end_freeze_sec = 0.6`**: Zamrożenie pozycji w outro klipu (ostatnie 0.6s). Nigdy nie ustawiać więcej niż 0.8s, aby nie zamrozić kadru przed zadaniem fraga!

---

## 2. DETEKCJA AKCJI I KADROWANIE CZASOWE (`lol_agent/lol_frag_detector.py`)

### A. Tryb Solo Bolo (1v1)
- Jeśli zabójstwo następuje w pierwszych 14.5s nagrania:
  - Klip rozpoczyna się od **dokładnie 0.0s** i trwa **15.0s** (`start = 0.0, end = 15.0`).
  - **Zero jump-cutów** — cała wymiana ciosów i setup widoczne bez cięć.
- Kolor badge'a miniatury: Crimson Red (`#DC2626`).

### B. Multi-kille (Double, Triple, Quadra, Penta)
- **Bufor wejścia w walkę (Lead-in)**:
  - Widz musi widzieć początek starcia, inicjację i wymianę skilli.
  - Minimalny bufor przed pierwszym killem: **`min 4.5s – 5.5s`** (`lead_in = max(4.5, buildup * 4.0)`).
  - Zakaz ucinania setupu walki do 1-2 sekund przed fragiem.
- **Bufor wyjścia (Outro)**:
  - Minimum 1.5s – 2.0s po ostatnim fragu.
- **Action Hook Guard (`lol_quality_validator.py`)**:
  - Sprawdza, czy klip nie został przycięty zbyt blisko fraga. Jeśli start jest za późny, cofa start do początku walki.

### C. Slow-Motion i Efekty
- Współczynnik slowmo: **`0.7x`** w kluczowym uderzeniu fraga.
- Czas trwania: krótki, dynamiczny akcent. Niedozwolone są długie, 4-sekundowe przestoje obrazu po fragu.

---

## 3. MULTI-GAME PROFILE ARCHITECTURE

System wspiera wiele profili gier z niezależnymi ROI, OCR i generatorem metadanych:
- `lol`: League of Legends (OCR kill-banner + paski HP)
- `valorant`: Valorant (kill banner center + clutch detection)
- `fortnite`: Fortnite (elim feed top right)
- `cs2`: Counter Strike 2 (top right feed)
- `generic`: Inne gry (detekcja peaków przez różnicę energii ruchu / Motion Energy)
- `product_ad`: Reklamy i recenzje (Dark Psychology CTR hooks, Motion Energy, Face detection)

Lokalizacja profili: `lol_agent/game_profiles/{game_id}.json`  
Router metadanych: `lol_agent/metadata_profiles/`

---

## 4. STANDARDY BEZPIECZEŃSTWA (Security & Secrets)

Repozytorium `BATTLEMETAL/Shortsyt` jest publiczne. Obowiązują rygorystyczne zasady:
1. **Nigdy nie commitować sekretów**:
   - Klucze API (Gemini, OpenAI, YouTube OAuth, Webhooki) mogą znajdować się **wyłącznie w lokalnym pliku `.env`**.
   - Plik `.env` musi być zawsze obecny w `.gitignore`.
2. **Zakaz umieszczania kluczy w plikach `.md` i `.json`**:
   - Nigdy nie wklejać rzeczywistych tokenów ani kluczy w promptach, plikach konfiguracyjnych repozytorium ani dokumentacji.
3. **Weryfikacja przed pushem**:
   - Zawsze uruchamiaj audyt bezpieczeństwa: `python scratch/audit_repo_secrets.py`.
4. **Procedura w razie wycieku**:
   - Natychmiast unieważnić (Revoke / Delete) klucz w panelu dostawcy (Google Cloud / AI Studio).
   - Oznaczyć alert w GitGuardian jako *Revoked*.

---

## 5. ZARZĄDZANIE PROCESAMI I DESKTOP STUDIO

- **Backend API**: FastAPI na porcie `8765` (`lol_agent.api.main:app`).
- **Desktop Frontend**: Electron + Vite React w `shortsyt-desktop/`.
- **Wdrażanie zmian frontendowych**:
  - Po modyfikacji kodu TypeScript w `shortsyt-desktop/src/`:
  - `npm run build` w `shortsyt-desktop/`
  - W razie potrzeby zaktualizować bundle Electrona / asar.
- **Restart backendu**:
  - Zabić proces uvicorn na porcie 8765 i uruchomić ponownie w tle:
  - `.\venv313\Scripts\python.exe -m uvicorn lol_agent.api.main:app --host 127.0.0.1 --port 8765`
