# LOL AGENT — MASTER CONTEXT
> Ostatnia aktualizacja: 2026-08-26 (sesja 23: Beat-Sync librosa, CTA Description Template, Desktop OAuth, Context Clean)
> Wersja: v33 — PRODUKCYJNY PIPELINE + NATIVE DESKTOP STUDIO + BEAT-SYNC ENGINE + OAUTH 2.0
> CZYTAJ TEN PLIK NA POCZĄTKU KAŻDEJ SESJI — zastępuje analizę wszystkich plików

---

## ⚡ ZASADY OSZCZĘDZANIA TOKENÓW (dla AI — stosuj ZAWSZE, szczególnie Gemini Flash)
```
✅ Odpowiadaj KRÓTKO i na temat — zero sykofancji, zero wstępów
✅ Pokazuj tylko zmienione linie, nie cały plik
✅ Pytania zadawaj TYLKO gdy konieczne — nie pytaj o oczywiste rzeczy
✅ Jeśli błąd jest jasny — od razu napraw, nie opisuj co zrobisz
✅ Używaj view_file(StartLine, EndLine) — nie czytaj całych plików
✅ Maksymalnie 5 zdań w odpowiedzi do użytkownika jeśli to możliwe
✅ Zanim zaczniesz sesję: przeczytaj TYLKO sekcje 0, "CO TRZEBA ZROBIĆ" i odpowiedni moduł
❌ Nie powtarzaj tego co właśnie zrobiłeś
❌ Nie pisz "Świetnie!", "Oczywiście!", "Rozumiem" itp.
❌ Nie opisuj kroków przed ich wykonaniem — po prostu je wykonaj
❌ Nie czytaj całego CONTEXT.md — używaj sekcji na żądanie
```

---

## ⚠️ UWAGA DLA GEMINI FLASH (model z ograniczonymi tokenami)
```
Ten model ma MAŁY LIMIT TOKENÓW. Jeśli kontekst się kończy:
1. Zapisz postęp do CONTEXT.md (sekcja "CO ZROBIONO") PRZED wyczerpaniem tokenów
2. Napisz użytkownikowi: "Tokeny kończą się — zapisałem postęp. Kontynuuj w nowym czacie."
3. Nie próbuj kończyć na siłę dużego zadania — zrób częściowy commit i udokumentuj

PRIORYTETY przy ograniczonych tokenach:
- Najpierw: napraw błędy blokujące pipeline (importy, crashes)
- Potem: zmiany w jednym pliku na raz, testuj import po każdej
- Ostatnie: refaktory, optymalizacje, UI zmiany
```

---

## 0. SZYBKI START NOWEGO CZATU ← CZYTAJ TO NAJPIERW

> **Jesteś AI asystentem projektu LOL AGENT.**
> Projekt: automatyczne YouTube Shorts z klipów League of Legends. Kanał: Dwannellenga.
> Ścieżka: `C:\Users\mz100\PycharmProjects\shortsyt\` | Venv: `.\venv313\Scripts\python.exe`
> Desktop App: `C:\Users\mz100\PycharmProjects\shortsyt\shortsyt-desktop\` (Electron 32 + React 18 + Vite + TailwindCSS)

### ✅ Co jest ZWERYFIKOWANE (NIE ruszaj):
- ✅ **smart_camera.py v12 Rock-Solid**: `player_gold` priority (-600 bonus), `ally_green` non-combat penalty (+450), `MAX_STEP_PX = 50`, `end_freeze = 2.0s` — kamera nie ucieka po walce, idealny lock na graczu.
- ✅ **lol_editor.py v34**: Trade preservation — `chase_gaps` wyłączone przy jump-cut i podniesione do >9s przy single cut (trade'y 5-7s są w 100% zachowane w 1.0x!).
- ✅ **lol_momentum_analyzer.py**: `pre_roll = 2.5s` (pełny setup akcji/engage), `merge_gap = 3.5s` (ciągłe wymiany nie są cięte), Loop-Bait Climax (+1.0s do +1.2s po ostatnim killu).
- ✅ **Death & Quality Filter** (`autonomous.evaluator` + `lol_clip_ranker`): 0 killi + śmierć lub 1-for-1 trade = **REJECT (0 pkt)**. Dobre klipy to 2 kille (0 deaths) ~15s SNAP lub 3+ kille (triple/quadra/penta).
- ✅ **lol_smart_titles.py**: context-aware (kill_count, game_phase, solo/team) + TITLE ACCURACY RULES w Gemini prompcie
- ✅ **lol_metadata_generator.py**: `build_description()` — stały CTA template (Dwannellenga branding + 3x CTA + hashtagi)
- ✅ **Beat-sync muzyka**: `librosa 1.0.0` zainstalowane, `lol_beat_detector.py` aktywny, `BEAT_DETECTOR_OK=True`, drop cache dla 11 piosenek
- ✅ **FastAPI backend** `/health`, `/status`, `/clips`, `/outputs`, `/youtube` — działają
- ✅ **YouTube OAuth Desktop**: Zweryfikowany i aktywny (`accounts/lol_token.pickle`) ze scopem `youtube.force-ssl` (przypięte komentarze działają!)
- ✅ **4-Layer Deduplication** (check_duplicate_clip): MD5 + nazwa + stem + OCR fingerprint — testy PASS
- ✅ **Scheduler** (`--schedule morning/evening`): 08:30 i 18:30 CEST
- ✅ **ZAPLANOWANY SHORT (27.08)**:
  - ☀️ **Dzisiaj 08:00 CEST**: `https://www.youtube.com/shorts/Po_hjAMbO3Q` (Katarina PENTAKILL, "Entire Team Disappeared In Seconds 💀💥", 20.9s, Quality 89/100, Jump-Cut 18→30 + 39.5→46.5, kamera v12 max-step-clamp)

### ⏰ Strategia godzin publikacji Shorts (Gaming / LoL):
- ☀️ **Poranek (08:30 CEST / 06:30 UTC)**: Algorytm ma 2h na transkodowanie i wstępny test na małej próbie widzów.
- 🌙 **Wieczór (18:30 CEST / 16:30 UTC)**: Szczyt graczy PC w Europie (17:00–22:00) + lunch-time w USA.

### ❌ Co COFNIĘTE (nie działa / gorsze):
- **cap.set(POS_FRAMES)** frame jumping — WOLNIEJSZE na H.264. Przywrócono sekwencyjny read.


---

## 🚀 CO ZOSTAŁO ZROBIONE W SESJI 22 (2026-08-24):
1. **Analiza i naprawa pętli uczenia Dark Psychology (`auditor_feedback.py`, `agent_dark_psychology.py`)**:
   - Ujednolicono rozbieżne ścieżki plików feedbacku: teraz wszystko zapisuje się i czyta z root (`auditor_feedback.json` i `auditor_weights.json`), dodano automatyczną migrację `_migrate_legacy_files()`.
   - Obniżono nierealistyczny próg trafności `APPROVAL_VIEW_THRESHOLD` z 80 na **35 views** (adekwatny dla kanału z 23 subskrybentami).
   - Dodano funkcję `run_feedback_cycle(youtube)` wykonującą pełną aktualizację wyników z YouTube, obliczenie korelacji Pearsona dla 8 kategorii audytora i zapis wag.
   - Dodano `get_forbidden_titles()` w `agent_dark_psychology.py` zabezpieczające przed duplikatami tytułów.
   - Zintegrowano automatyczny `run_feedback_cycle()` po ostatnim filmie sesji publikacyjnej.

2. **Rozszerzenie FastAPI Backend (`lol_agent/api/main.py` na porcie 8765)**:
   - Połączono architekturę obu agentów (LoL + Dark Psychology) w jeden spójny serwer backendowy.
   - Zaimplementowano kompletny zestaw endpointów `/dark/*`:
     - `GET /dark/status`: status kanału, ostatnie 2 filmy, statystyki audytora, v/h.
     - `GET /dark/analytics`: top 5 filmów, analiza formatów (QUESTION vs STATEMENT), keywords, czas publikacji.
     - `GET /dark/calibration`: wagi Pearsona per kategoria audytora, trafność prognoz %, top/bottom performers.
     - `GET /dark/directive`: aktualna dyrektywa adaptacyjna dla AI (`adaptation_directive.json`).
     - `POST /dark/run`: asynchroniczne uruchomienie agenta dark psychology (`--dry-run`, `--videos`).
     - `POST /dark/recalibrate`: ręczne wywołanie rekalibracji wag audytora.
     - `GET /health/full`: healthcheck obu agentów jednocześnie.

3. **Aplikacja PC Studio (`shortsyt-desktop`)**:
   - `src/lib/api.ts`: dodano metody API (`apiGetDarkStatus`, `apiGetDarkAnalytics`, `apiGetDarkCalibration`, `apiGetDarkDirective`, `apiRunDarkAgent`, `apiRecalibrateDark`).
   - `src/screens/DarkAgent.tsx` [NEW]: pełny panel monitoringu z kafelkami metryk, podglądem filmów, interaktywnymi paskami wag Pearsona, top 5, analizą słów kluczowych i przyciskiem uruchomienia z opcją dry-run.
   - `src/components/Sidebar.tsx` & `src/App.tsx`: dodano zakładkę "Dark Psychology" (Brain icon, badge AI, route `/dark`).
   - Weryfikacja: TypeScript check (`npx tsc --noEmit`) zakończony sukcesem (0 błędów).

4. **Aplikacja Mobilna (`shortsyt-app` - Expo / React Native)**:
   - `lib/api.ts`: dodano wywołania API dla Dark Psychology.
   - `screens/DarkAgentScreen.tsx` [NEW]: dedykowany ekran mobilny (statystyki, przycisk run z przełącznikiem dry-run, kalibracja wag audytora, top filmy, formaty).
   - `screens/DashboardScreen.tsx`: dodano kafelek "Dark Agent" w siatce szybkich akcji.
   - `App.tsx`: zarejestrowano ekran `DarkAgent` w `Stack.Navigator`.

---

## 🧪 CO TRZEBA ZROBIĆ / PRZETESTOWAĆ W KOLEJNYM CZACIE:
```
[!] [KRYTYCZNE] Re-autoryzacja YouTube przez Desktop App:
    → Uruchom backend: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765
    → Uruchom Desktop: npm run electron:dev (w shortsyt-desktop/)
    → Settings → "Autoryzuj kanał YouTube" → przeglądarka otworzy się automatycznie
    → Zaloguj na Dwannellenga → token zapisany → ShieldCheck zielony

[ ] [LIVE CHECK] Desktop App — po autoryzacji:
    → Outputs → wybierz short → Upload → sprawdź pinned comment (force-ssl)

[ ] [LIVE CHECK] Sprawdź YT Studio stats (views/CTR/watch time) dla ostatnich shortów:
    Triple Kill jtTa72ENbd0 (zaplanowany 08:30 2026-08-26)
    Quadra Kill cInsKL3ge7c (opublikowany 18:30 2026-08-25)

[ ] [OPCJONALNIE] Usuń ręcznie z YouTube Studio: rojVNLW34Nw (Double Kill — słabej jakości)
```


---


## 📦 PLAN KOMERCJALIZACJI & JAK ŁATWIEJ SPRZEDAĆ PRODUKT:
```
1. 1-CLICK INSTALATOR (.EXE / INSTALLER):
   - Użycie Electron Builder do wygenerowania standalone .exe instalatora
   - Wbudowanie ffmpeg i tesseract w pakiet lub auto-downloader (zero instalacji ręcznej)

2. CLOSED FEEDBACK LOOP (SAMOUCZENIE AI):
   - Zapis preferencji użytkownika (tempo, zoom, zbanowana muzyka) do user_preferences.json
   - Dynamiczne wstrzykiwanie notatek użytkownika do promptów Gemini Vision

3. ROZSZERZENIE NA E-COMMERCE / UGC ADS:
   - Moduł detekcji twarzy (MediaPipe) dla wideo z ludźmi / produktami
   - Auto-napisy w stylu CapCut/MrBeast (Whisper word-by-word)
   - Integracja z ElevenLabs / EdgeTTS do czytania skryptu reklamowego z linku sklepu

4. LANDING PAGE & WIDEO DEMO:
   - Krótkie 45-sekundowe wideo porównawcze: "16:9 surowy klip" vs "Zautomatyzowany 9:16 viral short w 10 sekund"
```

---

## 🔮 ROADMAP & PRZYSZŁY ROZWÓJ (UNIWERSALNY SILNIK KONTENTU Z DOWOLNEGO WIDEO):
```
Architektura przekształcenia silnika z gamingu w uniwersalny kombajn wideo (podcasty, wywiady, vlogi, e-commerce):

1. PIPELINE AUDIO-FIRST (Transkrypcja & Detekcja Perełek):
   - Moduł: whisper_highlight_extractor.py
   - Narzędzie: Faster-Whisper z word-level timestamps (word_timestamps=True) + Silero VAD (wykrywanie energii głosu / pauz).
   - LLM Story Extraction: Gemini / Qwen analizuje tekst i wybiera 20-50s fragmenty (Hook -> Context -> Climax/Punchline) oceniając potencjał wiralowy (0-100).

2. UNIWERSALNE KADROWANIE 9:16 (MediaPipe Face & Speaker Tracking):
   - Moduł: mediapipe_face_camera.py (zamiennik smart_camera.py opartego o paski HP)
   - Działanie: Google MediaPipe Face Mesh / Active Speaker Detection wykrywa osobę mówiącą i płynnie centruje okno 9:16 (z opcją split-screen góra/dół dla wywiadów dwuosobowych).

3. KINETYCZNE NAPISY WORD-BY-WORD (Styl MrBeast / Hormozi / CapCut):
   - Generowanie dynamicznych napisów w rytm mowy (1-3 słowa na ekranie z podświetleniem aktywnego słowa na żółto/zielono).
   - Automatyczne wycinanie ciszy (Silence Removal > 0.6s) dla maksymalizacji tempa i retencji.

4. SYSTEM PRESETÓW TEMATYCZNYCH (Niche Archetypes):
   - Preset A [Podcast / Interview]: kadrowanie twarzy + split-screen + wycinanie ciszy + napisy centralne.
   - Preset B [Gaming]: obecny silnik (OCR, paski HP, zoom-punch, momentum curve, slow-mo 60FPS).
   - Preset C [E-commerce / UGC Ads]: detekcja obiektów/produktów (YOLO) + podkład lektora Edge-TTS + dynamiczne slajdy korzyści.
```

---

## 🐙 INSTRUKCJA GITHUB & SYNCHRONIZACJA REPO:
```powershell
# 1. Przygotuj .gitignore (upewnij się że node_modules, venv, .env, tokeny i surowe wideo są ignorowane)
# 2. Inicjalizacja i push do zdalnego repozytorium:
git init
git add .
git commit -m "feat: complete Shortsyt desktop studio v26 + lol agent pipeline"
git branch -M main
git remote add origin https://github.com/TWOJ_USER/shortsyt-studio.git
git push -u origin main
```

---

## 💼 POST NA LINKEDIN (SZABLON DO WYKORZYSTANIA):
```text
🚀 Zbudowałem autonomiczne studio montażu i publikacji wideo wertykalnego (YouTube Shorts / TikTok) oparte o AI, Computer Vision i Electron!

Jako pasjonat gamingu i AI zawsze irytowało mnie, jak dużo czasu zajmuje ręczny montaż klipów:
❌ Ręczne wycinanie formatu 9:16 i uciekająca akcja z kadru
❌ Ręczne dopasowywanie spowolnień i dynamicznych zoomów
❌ Wymyślanie viralowych tytułów i opisów

Zautomatyzowałem cały ten proces od A do Z:
🔹 Smart Camera v11 (Computer Vision) — w czasie rzeczywistym śledzi postać gracza i dynamicznie centruje kadr 9:16
🔹 OCR & Momentum Analyzer — precyzyjnie wykrywa kluczowe akcje (Pentakill/Outplay) i automatycznie aplikuje slow-mo 60 FPS oraz uderzenia zoom-punch
🔹 Gemini Multimodal AI — generuje angażujące hooki, narracyjne tytuły i optymalizuje hashtagi pod algorytm YouTube
🔹 Desktop Studio (Electron 32 + React 18 + TailwindCSS) połączone z asynchronicznym backendem FastAPI i aplikacją mobilną (React Native / Expo)

Efekt? 1 kliknięcie dzieli surowy mecz od gotowego, wyrenderowanego w 4K/60FPS Shorta opublikowanego na YouTube z gotową miniaturką!

Wkrótce rozszerzam silnik o generowanie reklam UGC i wideo e-commerce dla sklepów internetowych. 

Wideo demo w komentarzu! 👇

#AI #MachineLearning #ComputerVision #Python #FastAPI #Electron #React #YouTubeShorts #Automation #SaaS #Gaming
```
> Cel: natywna aplikacja Windows (Electron + React) do zarządzania całym pipeline bez terminala.
> Połączona z FastAPI backendem (lol_agent/api/) + sync z apką Android (shortsyt-app/).
> Docelowo: jedno miejsce do zarządzania klipami, renderem, publishem i analityką.

### STOS TECHNOLOGICZNY:
```
Frontend:  Electron 32 + React 18 + TailwindCSS + shadcn/ui
Backend:   istniejący FastAPI (lol_agent/api/main.py) — bez zmian
Bridge:    electron-is-dev + axios (ten sam API client co apka Android)
Katalog:   C:\Users\mz100\PycharmProjects\shortsyt\shortsyt-desktop\
```

### EKRANY / WIDOKI (6 widoków):

#### 1. DASHBOARD (główny)
- Status pipeline (IDLE/RUNNING/DONE/ERROR) z live logami
- Ostatni opublikowany short: miniaturka + views + CTR
- Quick stats: łączne views, najlepszy short tydzień
- Countdown tokenu YouTube (czerwony gdy <7 dni)
- Przyciski: [▶ Start Pipeline] [⏹ Stop] [🔄 Refresh YT Token]

#### 2. KLIPY (Clip Browser)
- Lista plików MP4 z LOL_INPUT_DIR + Outplayed auto-scan
- Pre-pipeline score z lol_pre_analysis.json (kolorowe badge: 🔥/✅/📋/SKIP)
- Sortowanie: score DESC, data DESC, rozmiar
- Filtrowanie: action type, min score, champion
- Klik na klip → ClipDetail

#### 3. CLIP DETAIL + LAUNCH
- Miniaturka klipu (frame z ffprobe)
- Parametry: champion, action_type, --dry-run toggle
- Pre-analysis insights: weighted avg views, best title ref
- Przycisk: [▶ Renderuj] → RenderScreen

#### 4. RENDER MONITOR (live)
- Pasek postępu 7 kroków (1/7 Wycinanie... → 7/7 CTA Overlay)
- Live logi scrollowane z /status API (polling co 1.5s)
- Po zakończeniu: podgląd wideo + thumbnail + QA score
- Przyciski: [✅ Publikuj] [👁 Podgląd] [🗑 Odrzuć]

#### 5. OUTPUTS (biblioteka gotowych shortów)
- Lista wyrenderowanych MP4 z datą, długością, QA score
- Wbudowany podgląd wideo (HTML5 video tag przez file:// URI)
- Status YT: prywatny/publiczny/niezaładowany
- Przycisk [📤 Upload na YT] obok każdego

#### 6. ANALYTICS (dashboard danych)
- Graf: views over time dla wszystkich opublikowanych shortów
- Tabela: action_type → avg_views, best_views, count (z yt_perf_cache.json)
- Porównanie: narracyjne tytuły vs stare "Rampage" (z published_videos.jsonl)
- Eksport CSV

### INTEGRACJA Z ISTNIEJĄCYM BACKENDEM:
```
Endpoint                  → Gdzie używany w desktop
GET  /health              → Dashboard: sprawdzenie połączenia
GET  /status              → RenderMonitor: live logi
POST /pipeline/start      → ClipDetail: uruchom render
POST /pipeline/stop       → RenderMonitor: zatrzymaj
GET  /clips               → ClipBrowser: lista plików
GET  /outputs/{filename}  → Outputs: stream wideo
POST /youtube/upload/{n}  → Outputs: publikuj
GET  /youtube/token-status→ Dashboard: countdown tokenu
```

### SYNCHRONIZACJA Z APKĄ ANDROID:
```
SharedAPI:
  - Ten sam backend FastAPI (lol_agent/api/)
  - Ten sam JWT token (30 dni)
  - Desktop = "admin view" (pełne logi, analytics)
  - Mobile  = "remote control" (start/stop + preview)

Sync state:
  - Pipeline status live przez /status polling
  - Desktop i mobile mogą równolegle obserwować ten sam render
  - Upload triggerable z obu
```

### PLIKI DO STWORZENIA:
```
shortsyt-desktop/
├── package.json           ← Electron + React + Vite
├── electron/
│   ├── main.js            ← Electron main process (okno, menu, IPC)
│   └── preload.js         ← kontekst przeglądarki (bezpieczny IPC bridge)
├── src/
│   ├── App.tsx            ← React root + router
│   ├── lib/
│   │   └── api.ts         ← axios client (portowany z apki Android)
│   ├── components/
│   │   ├── Sidebar.tsx    ← nawigacja lewa
│   │   ├── StatusBadge.tsx
│   │   ├── VideoPlayer.tsx
│   │   └── ScoreBadge.tsx
│   └── screens/
│       ├── Dashboard.tsx
│       ├── ClipBrowser.tsx
│       ├── ClipDetail.tsx
│       ├── RenderMonitor.tsx
│       ├── Outputs.tsx
│       └── Analytics.tsx
└── tailwind.config.js
```

### DESIGN:
```
Paleta: ciemna LoL gold/blue (taka sama jak apka Android — constants/theme.ts)
  bg: #0A0E1A (ciemny granat)
  accent: #C89B3C (LoL gold)
  text: #E4D6B5 (kremowy)
  danger: #C0392B
  success: #27AE60
Font: Inter (UI) + Impact (overlaye jak w grze)
Layout: sidebar 220px + content area fluid
```

### KOLEJNOŚĆ IMPLEMENTACJI:
```
FAZA 1 (sesja 18): Szkielet Electron + połączenie z backendem
  → package.json, electron/main.js, preload.js, App.tsx, api.ts
  → Dashboard z /health + /status + countdown tokenu
  → WERYFIKACJA: apka się odpala, łączy z backendem

FAZA 2 (sesja 19): ClipBrowser + ClipDetail + launch pipeline
  → ClipBrowser z listą z /clips + pre-analysis scores
  → ClipDetail z parametrami + [▶ Renderuj]
  → RenderMonitor z live logami + progress

FAZA 3 (sesja 20): Outputs + YouTube upload + Analytics
  → Outputs z podglądem video
  → YouTube upload z apki desktop
  → Analytics z wykresami (recharts)

FAZA 4 (sesja 21): Sync z apką Android + packaging
  → Testowanie że desktop i mobile obserwują ten sam stan
  → Electron Builder → .exe installer
```

### WAŻNE ZASADY DESKTOP APP:
```
❌ Nie używaj node-fetch — używaj axios (spójność z apką mobilną)
❌ Nie otwieraj plików wideo przez Electron IPC — stream przez /outputs/{n}?token=JWT
✅ Używaj contextBridge w preload.js — nie wystawiaj require() na renderer
✅ Hardcode API URL default: http://localhost:8765 (edytowalny w Settings)
✅ JWT przechowuj w electron-store (nie localStorage — nie persystuje między sesjami)
✅ Paleta kolorów: skopiuj z shortsyt-app/constants/theme.ts
```



## ⚠️ ZŁOTE ZASADY PRODUKCJI & MONTAŻU (Wdrożone i Zweryfikowane)

### 1. Kadrowanie & Smart Camera (v11 Stateful HD Tracker):
- **Rozdzielczość próbkowania**: 640x360 (precyzyjna detekcja geometrii pasków HP).
- **Priorytetyzacja**: Złoty pasek gracza (bonus `-350`), strefa walki wrogów (bonus `-300`).
- **Limiter prędkości**: `MAX_DELTA = 60px/step` (eliminuje teleportację przy Shunpo / Flash).
- **Zamrożenie kadru**: `FREEZE_STREAK = 8` (kamera trzyma ostatnią pozycję, nie ucieka po walce).
- **Banner Shift**: `BANNER_SHIFT = 160px` w lewo przy killu (bannery LoL 1200-1920 są w pełni widoczne).

### 2. Dynamika Walki, Jump-Cut & Climax:
- **Jump-Cut Engine v6**: Automatyczne wycinanie przerw >2.5s między killami (np. bieganie przez rzekę).
- **Płynne 60 FPS**: Ciągła walka w tempie 1.0x, wejście w slow-mo 0.45x-0.50x (1.5s) tylko na finałowy cios.
- **15s Snap Rule**: Klipy 15.5-17.5s są precyzyjnie snapowane do 15.0s (najwyższy priorytet algorytmu).
- **Tight Ending & Loop Hook**: Zakończenie max 1.0-1.5s po ostatnim killu + CTA overlay "LEAVE A LIKE & SUBSCRIBE FOR MORE!" (1.5s).

### 3. Dźwięk & Beat-Sync:
- **Beat-Sync**: `librosa 1.0.0` pre-caching dropów dla wszystkich utworów NCS. Szczyt wideo trafia dokładnie w drop basu.
- **Audio Ducking**: Wyciszenie muzyki podczas PENTAKILL, boost dźwięków gry announcera.

### 4. Metadane & Tytuły:
- **Opisy**: Stały szablon `build_description()` w `lol_metadata_generator.py` z brandingiem Dwannellenga + 3x CTA + hashtagi.
- **Tytuły**: Kontekstowe (kill sequence, timings, game phase) z perspektywy wroga ("Enemy Tried to...") lub narracyjne.

---

---

## 1. PROJEKT — CO TO JEST

Automatyczny pipeline do tworzenia YouTube Shorts z klipów League of Legends.
**Kanał:** Dwannellenga
**Ścieżka projektu:** `C:\Users\mz100\PycharmProjects\shortsyt\`
**Venv:** `.\venv313\Scripts\python.exe`
**Główna komenda:** `.\venv313\Scripts\python.exe lol_agent\run_lol_agent.py`

### Pipeline (kolejność):
```
run_lol_agent.py
  → lol_clip_analyzer.py   (OCR kill detection + Gemini Vision champion)
  → lol_editor.py          (FFmpeg: crop 9:16, slow-mo, overlays, muzyka)
  → lol_thumbnail.py       (miniaturka 1080x1920)
  → lol_smart_titles.py    (Gemini AI title/hook/tags)
  → lol_publisher.py       (YouTube Data API upload)
  → lol_performance_tracker.py (48h po uploadzie: wyniki)
```

---

## 2. KLUCZOWE KOMENDY CLI

```powershell
# Pre-pipeline analyzer (uruchom PRZED pipeline — ranking klipów)
.\venv313\Scripts\python.exe lol_agent\lol_pre_pipeline_analyzer.py
.\venv313\Scripts\python.exe lol_agent\lol_pre_pipeline_analyzer.py --no-ocr   # szybko bez OCR
.\venv313\Scripts\python.exe lol_agent\lol_pre_pipeline_analyzer.py --top 5    # top 5 klipów
# Wyniki: lol_agent/lol_pre_analysis.json

# Standard upload (private)
.\venv313\Scripts\python.exe lol_agent\run_lol_agent.py --file "SCIEZKA" --champion Katarina --action pentakill

# Force re-upload (bypass dedup)
... --force

# Dry-run (nie uploaduje, tylko renderuje)
... --dry-run

# Autoryzacja konta YouTube
.\venv313\Scripts\python.exe lol_agent\run_lol_agent.py --authorize

# Test pipeline (standalone)
.\venv313\Scripts\python.exe lol_agent\test_render_v17.py 2>&1

# Uruchom API serwer (dwa sposoby)
.\venv313\Scripts\python.exe -m uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765
# LUB kliknij dwukrotnie:
lol_agent\api\start_server.bat

# Test API (PowerShell)
Invoke-WebRequest -Uri "http://localhost:8765/health" -UseBasicParsing | Select-Object -ExpandProperty Content

# Test importu API (sprawdź czy nie ma błędów)
.\venv313\Scripts\python.exe -c "from lol_agent.api.main import app; print('OK')"

# Uruchom apkę Android
cd shortsyt-app
npm start
```

**Flags CLI pipeline:**
- `--file PATH`      : konkretny plik (omija scan folderu)
- `--champion NAME`  : override champion (Gemini Vision bywa błędna: Evelynn/Kassadin zamiast Katarina)
- `--action TYPE`    : pentakill/quadrakill/triple/double/outplay/clutch
- `--force`          : bypass dedup check
- `--dry-run`        : renderuj ale nie uploaduj
- `--authorize`      : OAuth flow

---

## 3. KONFIGURACJA

### lol_config.py — wartości globalne:
```python
LOL_INPUT_DIR       = r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends"  # zmienione s9
LOL_MUSIC_DIR       = lol_agent/lol_music/
LOL_ARCHIVE_DIR     = lol_agent/lol_archive/

OUTPUT_WIDTH        = 1080
OUTPUT_HEIGHT       = 1920
OUTPUT_FPS          = 60
SHORT_MAX_DURATION  = 50    # max 50s (YT Shorts limit = 60s)

MUSIC_VOLUME        = 0.85  # 85% muzyki w tle
GAME_AUDIO_VOLUME   = 0.6   # 60% oryginalny dźwięk gry

SLOWMO_FACTOR       = 0.5   # 50% prędkości na peak action
SLOWMO_DURATION     = 1.5   # sekundy slow-mo
SMOOTH_SLOWMO       = True  # FFmpeg minterpolate blend

OVERLAY_FONT        = "Impact"
YT_CATEGORY_ID      = "20"  # Gaming
YT_PRIVACY          = "public"
GEMINI_MODEL        = "gemini-2.5-flash"
```

### .env — plik w root projektu (`C:\Users\mz100\PycharmProjects\shortsyt\.env`):
```
GEMINI_API_KEY=your_gemini_api_key_here
API_PASSWORD=shortsyt2026         <- hasło do apki Android (domyślne)
JWT_SECRET=change_me_to_random_32char_secret_here
API_PORT=8765
LOL_INPUT_DIR=C:\Medal\Edits
LOL_OUTPUT_DIR=C:\Users\mz100\Videos\lol_shorts_output
```

---

## 4. KAMERA — STAN AKTUALNY (smart_camera.py)

### Algorytm (v4 — fight zone centroid):
1. Dla każdej klatki wywołuje `_detect_fight_center_x(frame)`
2. Wykrywa ŻÓŁTY HP bar (gracz): `R>160, G>130, B<110, (R-B)>90, (G-B)>60`
3. Wykrywa CZERWONE HP bary (wrogowie): `R>150, G<90, B<80, (R-G)>70, (R-B)>80`
4. Gdy walka (żółty + czerwone): centroid wszystkich barów = centrum walki
5. Gdy tylko żółty: śledzi gracza
6. Gdy nic: **ostatnia znana pozycja** (freeze po FREEZE_STREAK=8 klatekach braku barów)
7. Outlier filter: jeżeli skok > 200px bez wykrycia barów — ignoruj
8. Smoothing window: 15 (~3.5s okno — filmowy ruch)
9. Max jump: 12px/krok (był 30)
10. **Velocity limiter: MAX_DELTA=60px/step** — eliminuje teleportację przy Shunpo

### Wykluczenia w detekcji:
- Górny scoreboard: `top_cutoff = 8%` wysokości
- Outplayed stats panel: lewe 22% x górne 35%
- HUD/minimap: dolne 20% wysokości
- Boczne marginesy: 6px z każdej strony

### Wyniki testów (Katarina pentakill, 26.6s):
- Detekcja: 86/89 klatek z detekcją HP barów ✅
- Velocity limiter aktywny: +VelLimit=60px widoczny w logach ✅
- Zakres x: 216-430px (swing 214px) — stabilna kamera

### Kluczowe wartości (NIE zmieniaj):
```python
# smart_camera.py linia ~743
FREEZE_STREAK = 8      # klatek bez barów przed zamrożeniem kamery
                       # przy ~4 sampli/s = freeze po ~2s braku barów
                       # < 5 → kamera goni Katarynę po Shunpo
                       # > 12 → freeze zbyt długi, kamera nie wraca po walce

# smart_camera.py linia ~134 (find_action_path PRZEBIEG 4)
MAX_DELTA = 60         # max px przesunięcia per krok
                       # > 80 → teleportacja wraca
                       # < 30 → kamera za wolna, nie dogania walki
```

### Parametry crop:
- Source: 1920x1080
- Crop width: 608px (31.6%) → 1080x1920 output po skalowaniu
- Scale factor: 1920/384 = 5.0 (analiza na skalowanej 384x216)

---

## 5. EDITOR — STAN AKTUALNY (lol_editor.py)

### Kill Banner Shift:
```python
# lol_editor.py linia ~812
BANNER_SHIFT = 160     # px w lewo przy kill (crop_x -= 160)
BANNER_WINDOW = 2.0    # sekundy przed/po kill gdzie shift aktywny
# Bannery LoL pojawiają się @ x=1200-1920 oryginału
# Bez shiftu: crop 608px wycina prawą stronę
# 160px = prawa krawędź kadru trafia w x≈1760 = cały "PENTAKILL" widoczny
# < 120 → banner ucięty
# > 250 → champion ucięty z lewej
```

### Overlaye i napisy:
- Kill counter: `detect_kill_events_from_video()` — OCR-free, detekcja z barów HP
- Hook overlay: "PENTAKILL" pierwsze 2s — kolor `0xFFD700` (złoty LoL)
- CTA overlay: "SUBSCRIBE" ostatnie 2s — drawbox tło 50% alpha
- Kill caption drawbox: czarne semi-transparent tło pod każdą etykietą kill
- **UWAGA FFmpeg drawbox:** używaj `trunc()` nie `//`, używaj `iw`/`ih` nie `w`/`h`

### Speed ramp i zoom:
- Slow-mo: 0.45x przy peak_moment (minterpolate blend)
- Zoom-punch: 1.20x przy kill moment
- Minterpolate fix: `tpad=stop_mode=clone:stop_duration=0.5` przed minterpolate
  → eliminuje migotanie ostatniej ~1s (ghosting artefakt)

### Encode:
- CRF=22 (~50% mniejszy bitrate niż CRF=18, jakość wciąż OK)
- Color: `eq=contrast=1.08:saturation=1.35:brightness=0.03`
- Output: 1080x1920 / 60fps / H264 / AAC

---

## 6. ANDROID APP + FASTAPI BACKEND

### Architektura systemu:
```
[Telefon Android — Expo Go]
        |  LAN WiFi (http://192.168.X.X:8765)
        |  LUB HTTPS (Cloudflare Tunnel — darmowy)
        v
[FastAPI Server — lokalny PC port 8765]  <-->  [lol_agent pipeline]
        |
        v
[YouTube Data API v3]  <-->  [OAuth token]
```

### Backend FastAPI — pliki (`lol_agent/api/`):
```
api/
├── main.py              <- FastAPI — 15 endpointów (GŁÓWNY PLIK SERWERA)
├── config.py            <- ustawienia z .env (hasło, JWT, ścieżki)
├── auth.py              <- JWT login, 30 dni ważności tokenu
│                           verify_token()         — Bearer header (standardowy)
│                           verify_token_flexible() — Bearer LUB ?token= (expo-av!)
├── pipeline_runner.py   <- uruchamia render_short() w osobnym wątku
│                           stan: IDLE / RUNNING / DONE / ERROR
├── youtube_uploader.py  <- YouTube OAuth 2.0 flow + upload wideo
├── start_server.bat     <- uruchom FastAPI + Cloudflare Tunnel (2x klik)
├── requirements_api.txt <- dependencje Python
└── cloudflare/
    ├── README.md        <- instrukcja Cloudflare Tunnel (darmowy tunel)
    └── config.yml.example
```

### Apka Android — pliki (`shortsyt-app/`):
```
shortsyt-app/
├── App.tsx                      <- navigation root + auto-login check
├── screens/
│   ├── LoginScreen.tsx          <- hasło → JWT token (30 dni)
│   ├── DashboardScreen.tsx      <- status pipeline + countdown + 4 przyciski
│   ├── ClipsScreen.tsx          <- lista MP4 z LOL_INPUT_DIR
│   ├── ClipDetailScreen.tsx     <- parametry: timing, action type, champion, efekty
│   ├── RenderScreen.tsx         <- live logi polling co 2s + progress bar
│   ├── OutputsScreen.tsx        <- lista gotowych Shortów
│   ├── PreviewScreen.tsx        <- odtwarzacz video + upload YouTube (modal)
│   └── SettingsScreen.tsx       <- URL serwera + YouTube OAuth + push notif
├── lib/
│   ├── api.ts                   <- API client (axios + SecureStore dla JWT/URL)
│   └── notifications.ts         <- Expo Push Notifications
├── components/
│   ├── TokenCountdown.tsx       <- countdown YouTube tokenu (zielony→żółty→czerwony)
│   └── StatusBadge.tsx          <- badge statusu pipeline
└── constants/theme.ts           <- design tokens (dark LoL gold/blue palette)
```

### API Endpoints:
```
POST /auth/login              <- hasło → JWT token (30 dni)
GET  /auth/me                 <- sprawdź token
GET  /status                  <- status pipeline (idle/running/done/error + logi)
POST /pipeline/start          <- uruchom rendering (body: wszystkie parametry)
POST /pipeline/stop           <- zatrzymaj
GET  /clips                   <- lista MP4 z LOL_INPUT_DIR
GET  /outputs                 <- lista gotowych Shortów (lol_temp + output dir)
GET  /outputs/{filename}      <- stream video (verify_token_FLEXIBLE — expo-av!)
                                 URL: /outputs/file.mp4?token=<jwt>
GET  /youtube/token-status    <- ile dni do wygaśnięcia tokenu YT
GET  /youtube/auth-url        <- URL do Google OAuth
POST /youtube/auth-code       <- wymień kod na token, zapisz pickle
POST /youtube/upload/{name}   <- upload Shorta na YouTube
POST /push/register           <- rejestruj Expo push token
GET  /health                  <- healthcheck BEZ autoryzacji
GET  /                        <- root info
```

### Hasło i JWT:
- Domyślne hasło: `shortsyt2026` (ustawione w `.env` → `API_PASSWORD`)
- JWT ważny 30 dni — apka nie wymaga częstego logowania
- Docs API (Swagger): http://localhost:8765/docs

### Krytyczna uwaga — expo-av i JWT:
```
❌ PROBLEM: expo-av (odtwarzacz wideo) nie może wysłać nagłówka Authorization
   przy ładowaniu źródła wideo. Zwykły Depends(verify_token) zwróci 403.

✅ ROZWIĄZANIE: endpoint /outputs/{filename} używa verify_token_flexible
   który akceptuje token z query param: /outputs/file.mp4?token=<jwt>
   
   W apce (PreviewScreen.tsx / api.ts) URL video musi być:
   `${serverUrl}/outputs/${filename}?token=${jwtToken}`
```

---

## 7. STATUS AKTUALNY (Sesja 23 — 2026-08-26)

### DZIAŁA — Pipeline LOL & Video Studio ✅
- **Smart Camera v11**: 640x360 HD Trajectory Tracker, HP bar gold (-350 bonus) + combat priority (-300), MAX_DELTA=60px, FREEZE_STREAK=8
- **Combat Segment Detection & Jump-Cut Engine v6**: Dual-signal (OCR + momentum), auto jump-cut dla przerw >2.5s
- **Dynamic Speed Ramp & Climax**: 60fps 1.0x continuous fight, 0.45x-0.50x slow-mo tylko na finalny cios (1.5s), zoom-punch 1.20x
- **15s Snap Rule & Loop Ending**: raw window snap do 14.0s / post-render trim do 15.0s, after_k=1.5s, CTA overlay "LEAVE A LIKE & SUBSCRIBE FOR MORE!" (1.5s)
- **Metadata Generator**: `build_description()` ze stałym brandingiem kanału Dwannellenga, hookiem tytułowym i 3x CTA
- **Smart Titles**: Context-aware (kill sequence, timings, game phase, solo vs team signal), TITLE ACCURACY RULES w Gemini prompcie
- **Beat-Sync Engine**: librosa 1.0.0 auto beat drop detection + pre-cached drops dla wszystkich 11 utworów NCS
- **Multi-Layer Dedup Guard**: 4 warstwy ochrony (MD5 hash, nazwa, stem meczu, semantyczny OCR fingerprint)
- **Evaluator & QA**: detekcja śmierci gracza (HP mask @ last_kill+0.8s), OCR score, velocity check, cisza check

### DZIAŁA — Desktop Studio & Backend API ✅
- **FastAPI backend (port 8765)**: pipeline control, clips scan, live status polling, outputs stream z token_flexible
- **YouTube OAuth (Desktop Native)**: get_auth_url() -> background localhost callback server -> Electron openExternal -> auto code exchange & save token (z uprawnieniami upload + force-ssl)
- **Desktop App (Electron 32 + React 18 + Vite)**: Dashboard, ClipBrowser, RenderMonitor, Outputs (z upload modalem na YT), Settings (JWT + YT OAuth)
- **Mobile App (React Native Expo)**: architektura gotowa, API client zsynchronizowany z backendem

---

## 8. BACKLOG & NAJBLIŻSZE ULEPSZENIA PRODUKTOWE

### Priorytet WYSOKI:
- [ ] **Re-autoryzacja YouTube**: wykonać w Desktop App (Settings -> Autoryzuj kanał) w celu aktywacji uprawnień force-ssl (pinned comments)
- [ ] **Desktop Analytics Screen**: wizualizacja views, CTR, watch time na podstawie `published_videos.jsonl` i `yt_perf_cache.json`

### Priorytet ŚREDNI:
- [ ] **Scheduling z poziomu Desktop Outputs**: dodanie wyboru slotu publikacji (☀️ 08:30 / 🌙 18:30) w modalu uploadu na YouTube
- [ ] **Thumbnail A/B Preview**: możliwość wyboru wariantu klatki/kolorów w Outputs przed publikacją
- [ ] **Auto-retry YouTube upload**: obsługa do 3 prób z exponential backoff przy chwilowych błędach sieciowych

### Priorytet NISKI:
- [ ] **Standalone packaging**: przygotowanie instalatora .exe (Electron Builder) z wbudowanym ffmpeg i tesseract
- [ ] **Dark Psychology -> LoL Title feedback**: automatyczne uwzględnianie wag audytora w rankingu propozycji tytułów

---

## 10. BIBLIOTEKA MUZYKI (lol_agent/lol_music/)

| Plik | Energia | Drop |
|---|---|---|
| ncs_elektronomia_sky_high.mp3 | HIGH | 30s |
| ncs_lost_sky_dreams_pt2.mp3 | HIGH | 40s |
| ncs_robin_hustin_light_it_up.mp3 | HIGH | 35s |
| ncs_elektronomia_immortality.mp3 | HIGH | 32s |
| ncs_unknown_brain_superhero.mp3 | HIGH | 38s |
| ncs_egzod_royalty.mp3 | HIGH | 45s |
| ncs_jim_yosef_link.mp3 | LOW | 30s |
| ncs_cartoon_on_and_on.mp3 | MEDIUM | 38s |
| ncs_different_heaven_my_heart.mp3 | MEDIUM | 28s |
| ncs_alan_walker_fade.mp3 | MEDIUM | 42s |
| ncs_alex_skrindo_euphoria.mp3 | MEDIUM | 36s |

---

## 11. PLIKI KLUCZOWE (mapa projektu)

```
C:\Users\mz100\PycharmProjects\shortsyt\
├── .env                         <- GEMINI_API_KEY + API_PASSWORD + JWT_SECRET
├── client_secret.json           <- Google OAuth credentials (YouTube)
├── accounts/lol_token.pickle    <- YouTube OAuth token (wygasa ~co 6m)
├── shortsyt-app/                <- React Native Expo apka Android
└── lol_agent/
    ├── CONTEXT.md               <- TEN PLIK
    ├── run_lol_agent.py         <- MAIN: CLI + orchestration
    ├── lol_config.py            <- CONFIG: zmień tu globalne wartości
    ├── smart_camera.py          <- CAMERA: fight-zone centroid v4
    │   └── linia ~743: FREEZE_STREAK=8, linia ~134: MAX_DELTA=60
    ├── lol_clip_analyzer.py     <- OCR + Gemini Vision + trim_quiet_start
    ├── lol_editor.py            <- FFmpeg pipeline: cut/effects/music/overlays
    │   └── linia ~812: BANNER_SHIFT=160, linia ~813: BANNER_WINDOW=2.0
    ├── lol_publisher.py         <- YouTube Data API upload
    ├── lol_temp/                <- pliki tymczasowe renderingu (*.mp4)
    │   └── test_v23_katarina_kills.mp4  <- ostatni test render
    │   └── *_qa.json            <- raport QA po renderze
    ├── qa_after_render.py       <- [NOWY] QA skrypt po renderze (OCR+velocity+cisza)
    └── api/
        ├── main.py              <- FastAPI serwer (15 endpointów)
        ├── auth.py              <- verify_token + verify_token_flexible
        ├── config.py            <- settings z .env
        ├── pipeline_runner.py   <- runner wątku pipeline
        ├── youtube_uploader.py  <- YT OAuth + upload
        └── start_server.bat     <- uruchom serwer (2x klik)
```

---

## 12. AUTORYZACJA YOUTUBE

```
AUTORYZACJA GŁÓWNA (Zalecana — Desktop App):
1. Uruchom serwer API: python -m uvicorn lol_agent.api.main:app --port 8765
2. Otwórz Desktop App (shortsyt-desktop) → zakładka "Ustawienia" (Settings)
3. Sekcja YouTube OAuth → Kliknij "Autoryzuj kanał YouTube"
4. Electron automatycznie otwiera przeglądarkę domyślną (Google OAuth)
5. Backend uruchamia w tle callback server (localhost:PORT)
6. Po zalogowaniu na Dwannellenga, Google przekierowuje do callbacku
7. Token (z uprawnieniami upload + force-ssl dla pinned comments) zapisuje się automatycznie w accounts/lol_token.pickle
8. Desktop App odświeża stan do zielonego badge ShieldCheck ("Token aktywny")

FALLBACK CLI:
.\venv313\Scripts\python.exe lol_agent\lol_publisher.py --authorize
```

---

## 13. HISTORIA SESJI

| Data | Co zrobiono |
|---|---|
| 2026-06-05 | Pełny audit 15 bugów, wszystkie naprawione |
| 2026-07-21 | Camera v1-v3: yellow HP bar, outlier filter, window=15 |
| 2026-07-23 | Camera v4: fight zone centroid (59/59 = 100% detection) |
| 2026-07-23 | trim_quiet_start (2.5x baseline), 409 error handling |
| 2026-08-09 | FastAPI backend (lol_agent/api/) — 15 endpointów, JWT, YT OAuth |
| 2026-08-09 | React Native Expo apka — 8 ekranów, push notif, SecureStore |
| 2026-08-09 | google-auth-oauthlib upgrade 1.2→1.4 (kompatybilna z genai) |
| 2026-08-09 | Cloudflare Tunnel — darmowy dostęp zdalny |
| 2026-08-12 s1 | Velocity limiter MAX_DELTA=60px/step — skok kamery wyeliminowany (86/89 klatek) |
| 2026-08-12 s1 | Kill Counter OCR-free: overlay PENTAKILL @ 17.3s OK |
| 2026-08-12 s1 | Minterpolate artefakt fix: tpad=clone + trim — migotanie wyeliminowane |
| 2026-08-12 s1 | Pełna analiza shortsa: ocena 5/10, 6 problemów |
| 2026-08-12 s2 | P1 Kill Banner Shift: crop_x -120px @ kill±2s (lol_editor.py) |
| 2026-08-12 s2 | P2 Camera Freeze: no_bar_streak>5 → cam=last_known (smart_camera.py) |
| 2026-08-12 s2 | P3 PENTAKILL gold: red→0xFFD700 + drawbox tło pod labelem |
| 2026-08-12 s2 | P4 CTA drawbox: czarny pasek ih*0.10 pod SUBSCRIBE |
| 2026-08-12 s2 | P5 CRF 22: bitrate ~50% mniejszy w final encode |
| 2026-08-12 s2 | Drawbox bug fix 1: text_w→approx_box_w, w/h→iw/ih w drawbox filtrach |
| 2026-08-12 s2 | Drawbox bug fix 2: // (Python floor div) → trunc() dla FFmpeg drawbox expr |
| 2026-08-12 s2 | Ocena shortsa po naprawkach: 7/10 |
| 2026-08-13 s3 | BANNER_SHIFT: 120 → 160px (pewniejsza widoczność bannerów kill) |
| 2026-08-13 s3 | FREEZE_STREAK: 5 → 8 klatek (eliminacja pościgu po Shunpo) |
| 2026-08-13 s3 | JWT fix: verify_token_flexible w auth.py (Bearer header LUB ?token= dla expo-av) |
| 2026-08-13 s3 | CORS: już był OK w main.py — CORSMiddleware z allow_origins=ALLOWED_ORIGINS |
| 2026-08-13 s3 | CONTEXT.md v11: pełna dokumentacja + plan testów telefonu |
| 2026-08-13 s4 | Etap A OK: /health działa z telefonu WiFi 192.168.8.187:8765 |
| 2026-08-13 s4 | Firewall: open_port_8765.bat (uruchom jako admin) |
| 2026-08-13 s4 | Expo Go 57.0.3 APK sideload z github.com/expo/expo-go-releases |
| 2026-08-13 s4 | Fix: App.tsx — wszystkie '../' importy → './' (App.tsx jest w root, nie w subfolderze) |
| 2026-08-13 s4 | Fix: notifications.ts — try/catch guard (push notif usunięte z Expo Go SDK 53+) |
| 2026-08-13 s4 | Bundle OK: Android Bundled 11410ms index.ts (1125 modules) ✅ |
| 2026-08-13 s4 | Decyzja: migracja na expo run:android (Android Studio) zamiast Expo Go |
| 2026-08-13 s4 | CONTEXT.md v12: zasady oszczędzania tokenów + plan sesji 5 |
| 2026-08-15 s6 | #1 DONE: pytesseract kill timing — Tesseract 5.4.0, wykrywa QUADRAKILL/PENTAKILL |
| 2026-08-15 s6 | #2 DONE: qa_after_render.py — OCR kill check + smart_camera velocity + ffmpeg cisza |
| 2026-08-15 s6 | #3 DONE: velocity limiter potwierdzony — Peak=60px=MAX_DELTA, brak skoków |
| 2026-08-15 s7 | Dry-run fix: usunięto cleanup_temp() na dry-run (run_lol_agent.py L369) — plik zostaje do QA |
| 2026-08-15 s7 | End-to-end render: OCR QUADRAKILL@19.2s + PENTAKILL@27.2s, kamera 86/89 klatek |
| 2026-08-15 s7 | QA PASS: Kill OCR OK, Velocity Peak=60px OK, Cisza=0.0s OK |
| 2026-08-15 s7 | Ocena shortsa: 8/10 → YT_PRIVACY zmienione private→public (lol_config.py L91) |
| 2026-08-15 s7 | Token YT wygasł (invalid_grant) — upload wymaga --authorize w sesji 8 |
| 2026-08-17 s8 | OAuth fix: run_local_server → manual URL flow w lol_publisher.py |
| 2026-08-17 s8 | Upload: "Five Kills. One Katarina. 🔥" — QA 92/100, public, Pgn0M8RXRIA |
| 2026-08-17 s8 | Bug fix: surrogate chars w pinned comment (encode utf-16 surrogatepass) |
| 2026-08-18 s9 | LOL_INPUT_DIR: C:\Medal\Edits → C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends |
| 2026-08-18 s9 | smart_camera: kill-window freeze ±3s od killa (kamera nie ucieka po QUADRAKILL/PENTAKILL) |
| 2026-08-18 s9 | lol_editor: music dedup (.last_track wyklucza poprzedni track) |
| 2026-08-18 s9 | lol_metadata_generator: pełne hashtagi #Shorts #LeagueOfLegends #LoL |
| 2026-08-18 s9 | lol_smart_titles: wymuszenie hashtagów po Gemini JSON |
| 2026-08-18 s9 | Upload private: JmM7j19opGY (Katarina pentakill, 08-01-2026) |
| 2026-08-18 s10 | lol_thumbnail: FFMPEG_BIN auto-detect (C:\ffmpeg\...\ffmpeg.exe) |
| 2026-08-18 s10 | lol_thumbnail: crop 20% dołu (HUD cutoff), stroke czarny, logo 200px od dołu |
| 2026-08-18 s11 | lol_momentum_analyzer: OCR cooldown 2s→3.5s — eliminuje duplikaty TRIPLE/PENTA bannerów |
| 2026-08-18 s11 | lol_momentum_analyzer: trim_start rozszerzone do first_kill-1s — TRIPLE nie ucinane |
| 2026-08-18 s11 | Test klip 83s (penta@23.4s): przed fix 6 peaks/11.5s, po fix 4 peaks/13.2s ✅ |
| 2026-08-18 s12 | lol_editor: intermediate_peaks mini slow-mo 0.8x/0.5s na TRIPLE/QUADRA przed PENTA |
| 2026-08-18 s12 | lol_momentum_analyzer: first_kill buffer 1s→5s — klip zaczyna 5s przed TRIPLE |
| 2026-08-18 s12 | smart_camera: EMA_ALPHA 0.65→0.45, smooth_w 3→9 — płynniejsza kamera |
| 2026-08-18 s12 | DIAGNOZA: BANNER_SHIFT gap flicker — kill windows 7.0-7.3s i 11.3-11.7s powodują 320px jerk |
| 2026-08-18 s12 | FIX zaplanowany (sesja 13): scalanie overlapping kill windows (MERGE_GAP=1.5s) |
| 2026-08-18 s13 | FIX BANNER_SHIFT gap: MERGE_GAP=1.5s w lol_editor.py L860-881 — scal overlapping kill windows |
| 2026-08-18 s13 | Dry-run PASS: 4 kills → 2 merged windows (TRIPLE+QUADRA+PENTA=1 window, UNSTOPPABLE=osobne) |
| 2026-08-18 s13 | Kamera 88/89 klatek, short 17.3s, zero jerków między killami ✅ |
| 2026-08-18 s14 | lol_editor: ramp 0.5s (RAMP_SECS) przy wejściu/wyjściu z merged kill window — płynny shift |
| 2026-08-18 s14 | lol_config: CHAMPION_WHITELIST 10 championów — Gemini ograniczony do tej listy |
| 2026-08-18 s14 | lol_clip_analyzer: Gemini prompt + post-walidacja whitelist — zero halucynacji Evelynn/Kassadin |
| 2026-08-18 s14 | Dry-run PASS: -160px (ramp 0.5s) @ 2 merged windows, Katarina wykryta poprawnie ✅ |
| 2026-08-18 s15 | Publikacja Public: UZOmupNxfrU (Katarina Pentakill) + multi-hashtag + miniaturka API ✅ |
| 2026-08-19 s16 | Tesseract binary auto-detect fix w lol_clip_ranker.py |
| 2026-08-19 s16 | Skan 810 klipów Outplayed OCR: wykryto duplikat sesyjny (11-36-38-807 == 21-34-50-358) |
| 2026-08-19 s16 | Wdrożono Gemini Multi-Model Pool (3.7-flash, 3.5-flash, flash-latest) — 0 błędów 429 |
| 2026-08-19 s16 | Wdrożono Semantic OCR Action Fingerprint Deduplication w run_lol_agent.py ✅ |
| 2026-08-19 s16 | Test dedup: pomyślnie zablokowano duplikat 11-36-38-807 (UZOmupNxfrU) |
| 2026-08-19 s16 | Backup: CONTEXT_PRIME.md utworzony jako niezmienna kopia zapasowa v25 |
| 2026-08-19 s16 | Testy evaluatora: Pentakill = 91.2/100 (S_TIER), Słaby klip = 30.5/100 (REJECT) ✅ |
| 2026-08-19 s16 | Test Suite (5/5 PASS): Gemini Pool, Evaluator, OCR Dedup, Ranker, Watcher Engine ✅ |
| 2026-08-19 s16 | Zweryfikowano klip backlog: 19-04-04-255_0.mp4 (Score=81.0, S_TIER, TRIPLE@13s, PENTA@30.7s) |
| 2026-08-19 s16 | Smart Camera v11 (Stateful HD Trajectory Tracker 640x360): nearest-neighbor continuity + combat priority weighting |
| 2026-08-19 s16 | FFmpeg filtergraph pipeline fix: {trim} -> {crop_scale} -> {setpts} (eliminacja skoku kamery przy slow-mo/zoom-punch) |
| 2026-08-19 s16 | Optymalizacja startu: trim_start = first_kill_t - 8.2s (4.8s w tym meczu) — 0 sklepu, pełny 1. i 2. frag zachowany |
| 2026-08-19 s16 | Usunięcie mini slow-mo w trakcie walki — ciągłe, płynne 60fps w 1.0x z wejściem w slow-mo tylko na finałowy cios |
| 2026-08-19 s16 | Sekwencjonowanie napisów dynamicznych: natychmiastowe ucinanie poprzedniego napisu przy kolejnym killu |
| 2026-08-20 s17 | lol_smart_titles.py: FORBIDDEN template list (Rampage/Unstoppable/Domination) + wymuś narracyjny hook z perspektywy wroga (Enemy Tried to Die style) |
| 2026-08-20 s17 | lol_pre_pipeline_analyzer.py [NOWY]: skan Outplayed + OCR scoring + YT history (time-decay weights) → ranking klipów przed pipeline + gotowa komenda CLI |
| 2026-08-20 s17 | lol_editor.py: get_performance_insights() — dynamiczna adaptacja parametrów montażu (zoom, slowmo, audio) na podstawie najnowszych danych YT |
| 2026-08-24 s20 | merge_split_clips universalization + 4-layer dedup protection (check_duplicate_clip) + .exe build + sync real YT Studio metrics (6.5k views, 22.3h) |
| 2026-08-24 s20 | Combat Segment Jump-Cut Engine v6: Dual-signal detection, frame-accurate Smart Camera na step1, ucięcie pustego ogona (26.2s total) ✅ |
| 2026-08-24 s20 | Publikacja Public: d61bPr4MrII (Katarina Unofficial Pentakill) — Jump-Cut v6 + miniaturka + pinned comment ✅ |
| 2026-08-25 s21 | Player Death Detection (evaluator.py): HP mask check (R>160,G>130,B<110) @ last_kill+0.8s → score=15, tier=REJECT jeśli gracz padł |
| 2026-08-25 s21 | AFTER_PEAK: 1.2s→1.0s (lol_momentum_analyzer.py ~L80), after_k Quadra/Penta: 3.8s→1.0s (~L532) — eliminacja 6s martwego czasu |
| 2026-08-25 s21 | Opublikowano Quadrakill cInsKL3ge7c (18:30 CEST) + Double Kill rojVNLW34Nw (jutro 08:30) |
| 2026-08-26 s23 | **15s SNAP RULE** (lol_momentum_analyzer.py L531): jeśli raw okno 15.5–18.0s → snap do 14.0s raw (~15s po slow-mo) |
| 2026-08-26 s23 | **POST-RENDER 15s SNAP** (lol_editor.py ~L1171): jeśli finalny MP4 15.5–17.5s → FFmpeg -ss trim od początku → dokładnie 15.0s |
| 2026-08-26 s23 | **after_k: 1.0s → 1.5s** — baner kill widoczny + czyste zakończenie zapętlające |
| 2026-08-26 s23 | **CTA overlay**: "SUBSCRIBE FOR MORE!" → "LEAVE A LIKE & SUBSCRIBE FOR MORE!" (1.5s, nie 2.0s) |
| 2026-08-26 s23 | Opublikowano Triple Kill jtTa72ENbd0 (jutro 08:30 CEST) |
| 2026-08-26 s23 | **Context-aware titles**: kill_context dict (kill_count, sequence, timings, game_phase, solo/team signal) przekazywany do Gemini → eliminuje błędne tytuły ("dive" w jungli, "carry" przy solo kill) |
| 2026-08-26 s23 | **lol_smart_titles.py**: TITLE ACCURACY RULES w prompcie — early game→jungle, late game→teamfight, spread<3s→burst, spread>3s→clutch, "dive" tylko pod wieżą |
| 2026-08-26 s23 | **run_lol_agent.py**: game_time inference z nazwy pliku Outplayed (HH-MM-SS→minuty meczu→early/mid/late) |
| 2026-08-26 s23 | **ROADMAP FIXES — OCR Fallback**: action_hint przekazywany przez run→analyzer→momentum. Jeśli OCR=0 a action=triple/quadra/penta → syntetyczny peak @ duration-3.5s |
| 2026-08-26 s23 | **ROADMAP FIXES — OCR Region**: KILL_REGION zmieniony z (0.05-0.25y, 0.20-0.80x) na (0.30-0.65y, 0.25-0.75x) — tylko centralny baner, eliminuje false positives z kill-feedu |
| 2026-08-26 s23 | **ROADMAP FIXES — Thumbnail**: peaks[-1][0]+1.5s → baner TRIPLE KILL zawsze widoczny na thumb |
| 2026-08-26 s23 | **Desktop App — Outputs.tsx**: przycisk YouTube teraz ma onClick → modal z edytowalnym tytułem + opisem + prywatnością → apiUploadToYt → link do YT po uploaderze |
| 2026-08-26 s23 | **Desktop App — Settings.tsx**: sekcja YouTube OAuth — status tokenu (ShieldCheck/ShieldAlert/ShieldOff), przycisk "Autoryzuj"→otwiera przeglądarkę, pole na kod + Clipboard paste → apiExchangeYtCode → zapisuje lol_token.pickle |
| 2026-08-26 s23 | **api/youtube_uploader.py**: dodano scope youtube.force-ssl → token z tej autoryzacji umożliwia pinned comments (fix 403 na commentThreads.insert) |
| 2026-08-26 s23 | **OAuth REWRITE**: OOB (deprecated 2022) zastąpiony localhost callback serverem. get_auth_url() → losowy port → _run_callback_server (daemon thread) → Google redirect → token zapisany automatycznie. Brak wklejania kodu. |
| 2026-08-26 s23 | **Settings.tsx OAuth flow**: przycisk Autoryzuj → openExternal → polling apiGetYtTokenStatus co 2.5s → spinner "Czekam na autoryzację..." → auto-sukces gdy token pojawi się w backend. Bez kodu paste. |
| 2026-08-26 s23 | **lol_publisher.py authorize fix**: zamieniono run_local_server na OOB+webbrowser.open. Instrukcja: jeśli przeglądarka nie otworzy się automatycznie, URL jest wypisany w konsoli do ręcznego skopiowania. |
| 2026-08-27 s24 | **v17 Multi-Template True-Lock Tracker (smart_camera.py)**: Pełne rozwiązanie problemu pracy kamery 9:16. Auto-discovery szablonu postaci gracza w pierwszych klatkach (odznaka poziomu [LVL] + złoty pasek HP area >= 100, aspect >= 2.5), full-frame matchTemplate (cv2.TM_CCOEFF_NORMED) na przestrzeni BGR z auto-adaptacją po awansie poziomu (12→13). Zerowy drift na wieże i pochodnie. |
| 2026-08-27 s24 | **Klip #1 (12-36-25-676_0.mp4)**: Opublikowany pomyślnie (ID: `6kpFYG3flMY`, link: https://www.youtube.com/shorts/6kpFYG3flMY). |
| 2026-08-27 s24 | **Klip #2 (13-44-46-087_0.mp4)**: Zmontowany perfekcyjnie (10.3s→25.5s, 3 fragi w dead center), zakolejkowany na rano 08:30 CEST. |

---

## 13.5 INTELIGENTNY SILNIK CIĘCIA WALKI & TIGHT CLIMAX (COMBAT JUMP-CUT ENGINE v6)

```
Problem:
  W wielu klipach (np. nieoficjalna penta, rozciągnięty teamfight) gracz zdobywa 2 fragi,
  potem biegnie przez rzekę/linię przez 5-10 sekund, po czym zdobywa kolejne 3 fragi do ACE.
  Trzymanie ciągłego klipu (35-40s) niszczy retencję (widzowie dropują na bieganiu),
  a ucięcie początku gubi pierwsze zabójstwa. Ponadto, przeciąganie ogona (5s slowmo + 5s chodzenia)
  sprawiało, że short trwał 34s zamiast idealnych 24-25s.

Złote Reguły Montażu (ZWERYFIKOWANE — SESJA 24):
  1. Dual-Signal Combat Detection (find_combat_segments w lol_momentum_analyzer.py):
     - Łączy OCR kill peaks + ciągłą krzywą momentum (ruch + VFX czarów).
     - Parametry: activity_threshold = 48.0, pre_roll = 1.2s, post_roll = 1.0s, merge_gap = 2.5s.
     - Jeśli przerwa > 2.5s (bieganie/pościg) → automatyczny JUMP CUT.
  
  2. Multi-Segment Concat & Frame-Accurate Smart Camera (lol_editor.py & smart_camera.py):
     - Smart Camera v17 True-Lock Tracker analizuje 01_cut.mp4 i utrzymuje postać w centrum kadru 9:16.
     - Auto-wykrywanie szablonu badge gracza z klatek początkowych + matching przez cv2.matchTemplate.
     - Redukcja ścieżki do 14-16 kluczowych punktów zapewnia bezbłędny parsing w FFmpeg (<300 znaków).

  3. Tight Climax & Anti-Dragging Ending:
     - Pentakill/Climax slow-mo duration: _slowmo_dur = 1.5s (speed 0.50x), zoom=1.20x.
     - Klip kończy się maksymalnie 1.0-1.2s po ostatnim killu / banerze ACE + 2.0s CTA overlay.
     - Całkowity czas gotowego Shorta wynosi ~15-25s (idealna retencja YT Shorts).
```

---

## 13.6 UNIVERSAL SMART CAMERA ARCHITECTURE (v17 TRUE-LOCK)

```
Zasada Działania:
  1. Ekstrakcja Klatek: extract_sample_frames() pobiera klatki w 1080p (RGB np.float32), konwertowane do BGR uint8.
  2. Auto-Discovery: W pierwszych 10 klatkach wykrywa komponenty złotego paska HP gracza (area >= 100, cw 30-130, aspect >= 2.5).
     Wyciąga szablon odznaki poziomu [LVL] znajdujący się po lewej stronie paska: bx0=cx-65, bx1=cx+15, by0=cy-15, by1=cy+25.
  3. Dynamic Multi-Template Match: W każdej klatce przeszukuje pole gry (120:850, 80:1840) szukając szablonu z progiem 0.55.
     W przypadku awansu na wyższy poziom dodaje nowy szablon do listy aktywnych wzorców.
  4. Fallback: Jeśli postać jest niewidoczna (tarcza / Death Lotus / untargetable), utrzymuje poprzednią pozycję lub wspiera się kolorem.
  5. Kinowe Wygładzanie: Ścieżka x jest wygładzana oknem win=5 i downsamplowana do 14 punktów dla zwięzłego wyrażenia FFmpeg.
```

---

## 14. KONWENCJE EDYTOWANIA KODU

```
✅ view_file(StartLine=X, EndLine=Y) PRZED każdą edycją — sprawdź dokładne linie
✅ replace_file_content dla jednej zmienionej sekwencji
✅ multi_replace_file_content dla wielu miejsc w pliku
✅ Po edycji: python -c "from ... import ..." — sprawdź import
✅ Wskazuj FUNKCJĘ i LINIĘ, nie generuj całego pliku

❌ Nie generuj całego pliku
❌ Nie używaj // (floor div Python) w wyrażeniach FFmpeg — używaj trunc()
❌ Nie używaj text_w/text_h w FFmpeg drawbox — aproksymuj (font_size * 0.6 * len(text))
❌ Nie zmieniaj parametrów kamery bez testu (FREEZE_STREAK, MAX_DELTA)
```