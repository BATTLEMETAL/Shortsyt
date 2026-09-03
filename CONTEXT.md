# LOL AGENT — MASTER CONTEXT
> Ostatnia aktualizacja: 2026-08-31 (sesja 24: Universal Retention Pacing, Multi-Zone Triple OCR, Climax Loop Cut, Scheduled Shorts 31.08)
> Wersja: v32 — PRODUKCYJNY PIPELINE + AUTO RETENTION HOOK + MULTI-ZONE OCR + UNIVERSAL SMART CAMERA
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
> Projekt: automatyczne YouTube Shorts z klipów League of Legends + E-commerce/UGC Video Engine. Kanał: Dwannellenga.
> Ścieżka: `C:\Users\mz100\PycharmProjects\shortsyt\` | Venv: `.\venv313\Scripts\python.exe`
> Desktop App: `C:\Users\mz100\PycharmProjects\shortsyt\shortsyt-desktop\` (Electron 32 + React 18 + Vite + TailwindCSS)

### ✅ Co jest ZWERYFIKOWANE (NIE ruszaj):
- ✅ **Desktop Studio (Electron 32 + React 18 + Vite)**:
  - **Dwannellenga Viral Metadata Engine**: generowanie sprawdzonych, angażujących tytułów pod algorytm (np. `Triple Kill! They Never Saw Katarina Coming 😈 #Shorts #LeagueOfLegends #LoL`), narracyjnego opisu z brandingiem kanału i wezwaniem do subskrypcji oraz angażującego przypiętego komentarza.
  - **Miniaturka 9:16 (Hero-Frame Workspace)**: dedykowany podgląd miniatury z opcją podejrzenia pliku na dysku (`FolderOpen`), kopiowania ścieżki i automatycznego uploadu na YouTube wraz z filmem.
  - **YouTube Upload & Auto-Comment**: `POST /youtube/upload/{filename}` automatycznie publikuje Shorta, wgrywa miniaturkę 9:16 (`youtube.thumbnails().set`) oraz dodaje i przypina komentarz angażujący (`youtube.commentThreads().insert`).
  - **YouTube Token Countdown Fix**: poprawny odczyt 7-dniowej ważności refresh tokenu (`days_remaining: 7`, zielony status aktywności).
  - **AI Auto-Trim & Manual Mode Switcher**: wybór trybu wyznaczania czasu [⚡ AI Auto-Trim] (skan OCR + detekcja kill eventów i automatyczne dopasowanie Action Hooka i Loop Cut) oraz [🛠️ Ręczny] (pełna manualna edycja startu, końca i peak momentu z przyciskami +/- 1s).
  - **POST /clips/auto-detect**: endpoint AI analizujący okno walki, typ akcji i hook text.
  - **Folder Picker**: opcja wyboru dowolnego folderu z nagraniami (`electronApp.selectDirectory` + `GET /clips?folder=...`).
  - **Post-Render Interactive Review**: po zakończeniu montażu natychmiast odpala się pionowy odtwarzacz 9:16, podgląd miniatury, edytowalne metadane (tytuł, opis, przypięty komentarz) oraz 3 przyciski decyzji użytkownika ([🚀 Zatwierdź & Publikuj], [🔄 Wróć / Zmień parametry], [🗑️ Odrzuć & Usuń]).
  - **DELETE /outputs/{filename}**: endpoint bezpiecznego odrzucania i usuwania roboczych plików z dysku.
- ✅ **smart_camera.py v25** (Zero-Touch):
  - Universal Player Tracker (złoty HP bar, min 75% klatek).
  - **Dash/Flash/Shunpo Snap**: `delta > 250px` → natychmiastowy snap kamery zamiast powolnego dryfowania.
  - **Combat Centroid Fallback**: >4 klatki bez gracza (Zhonya/bush/zgon) → kamera płynie w kierunku środka masy walki wrogów.
- ✅ **lol_editor.py v33 (Viral Retention Pack)**:
  - **Dynamic Kill Streak HUD**: `[ KILL 1/X ]` ➔ `[ FINAL KILL X/X ]` z animowaną pigułką w górnym kadrze (zwiększa goal-gradient i retencję).
  - **Neon Loop Progress Scrubber**: 5px Hextech Gold (`0xC89B3C`) pasek na samym dole pod zapętlenie.
  - **Universal Sidechain Audio Ducking**: automatyczne wyciszanie muzyki (-45%) i podbijanie dźwięków ciosów/announcera na każdym killu.
- ✅ **lol_momentum_analyzer.py v32**:
  - **Visual Action Hook**: wejście w akcję w 0.8s–1.5s (`first_kill_t - 2.0s`), zero bicia wieży i zbędnych dobiegów.
  - **Loop Climax Cut**: ciasne odcięcie +1.0s do +1.2s po ostatnim fragu / multikillu pod seamless loop (retencja >100%).
  - **Triple-Zone OCR + Regex**: równoległe skanowanie centralnego banera, kill feedu i chat logu z odpornością na czcionkę Tesseracta.
- ✅ **lol_quality_validator.py** — Pre-Flight Validator (audyt 3-5s przed renderem):
  - **Action Hook Guard**: brak walki w 0-1.5s → auto-trim start do `first_kill_t - 2.0s`.
  - **Kill Visibility Check**: każdy frag musi mieścić się w oknie 9:16 kadru (conf >70%).
  - **Tower Attack Guard**: >60% klatek bez wrogich HP barów → auto-trim start do początku walki.
  - **Auto-Reject**: klip z `LOW_KILL_VISIBILITY` odrzucany automatycznie z komunikatem.
- ✅ **lol_thumbnail.py** — Hero-Frame Selector:
  - Skanuje 10 kandydatów w oknie ±1.75s od peak_moment.
  - Wybiera klatkę z najwyższym nasyceniem VFX + widocznym złotym HP barem gracza.
  - Wyklucza czarne klatki (brightness <30) i prześwietlone (>240).
- ✅ **run_lol_agent.py** — Pre-Flight zintegrowany z pipeline:
  - `PRE_FLIGHT_OK=True` — validator uruchamia się automatycznie przed każdym `render_short()`.
  - Auto-korekta `peak_start`/`peak_end` jeśli Action Hook / Tower Guard wykryją problem.
  - Automatyczne odrzucenie z logiem `❌ REJECTED` i return None.
- ✅ **Quality Gate & Rejection Protocol**: 4 automatyczne filtry odrzucania (OVERLAY_OBSTRUCTION, EXTREME_DISPERSION >1200px, LOW_TRACKING_CONFIDENCE <75%, DECOY_TARGET).
- ✅ **Multi-Layer Deduplication Safeguard**: 4 warstwy ochrony przed duplikatami.
- ✅ **OPUBLIKOWANE I ZAPLANOWANE SHORTY KANAŁU**:
  1. 🎬 `https://www.youtube.com/shorts/M4HHZ_lyGUQ` — 29.08 12:00
  2. 🎬 `https://www.youtube.com/shorts/eMfSJy9dS60` — 29.08 18:00
  3. 🎬 `https://www.youtube.com/shorts/836Zv-jqOxc` — 30.08 08:00
  4. ☀️ **31.08 11:00 CEST**: `https://www.youtube.com/shorts/KgFgIhh0Ck4` (Katarina Triple Kill River Fight, 19.8s)
  5. 🌙 **31.08 18:00 CEST**: `https://www.youtube.com/shorts/A5TnIQSDZ9c` (Katarina Instant Engage Multi-Kill, 11.9s)

### ⏰ Strategia godzin publikacji Shorts (Gaming / LoL):
- ☀️ **Poranek (08:30 CET / 06:30 UTC)**: Algorytm ma 2h na transkodowanie i wstępny test na małej próbie widzów, trafia w szczyt pory obiadowej / szkolnej (11:30–14:00).
- 🌙 **Wieczór (18:00 CET / 16:00 UTC)**: Szczyt graczy PC w Europie (17:00–22:00) + lunch-time w USA (12:00 EST / 09:00 PST).

### ⚠️ Co NIE przetestowane live (wymaga manualnego testu od Ciebie):
| Co | Gdzie | Status | Co musisz przetestować |
|---|---|---|---|
| API `/thumbnails` i `/camera-preview` | `main.py` | Import OK, **endpoint live nie wywołany** | Uruchom FastAPI, otwórz `http://127.0.0.1:8000/thumbnails` |
| Desktop App miniaturki, RenderMonitor IPC | `Outputs.tsx`, `RenderMonitor.tsx` | `npm run build` OK, **apka nie uruchamiana po zmianach** | Uruchom `npm start` w `shortsyt-desktop/`, sprawdź zakładkę Outputs |
| .exe installer Shortsyt Studio | `shortsyt-desktop/release/` | Plik istnieje, **nie instalowany na czystym PC** | Zainstaluj bez Python/Node na czystym systemie |

### ❌ Co COFNIĘTE (nie działa / gorsze):
- **cap.set(POS_FRAMES)** frame jumping — WOLNIEJSZE na H.264 (seek → I-frame decode → forward decode). 180s vs 95s. Przywrócono sekwencyjny read.

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
[ ] [FASTAPI LIVE CHECK] Uruchom serwer: uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload
    Sprawdź w przeglądarce: http://localhost:8765/dark/status oraz http://localhost:8765/dark/calibration
[ ] [DESKTOP APP CHECK] Uruchom: start_desktop.bat w shortsyt-desktop/
    Przetestuj zakładkę "Dark Psychology", kliknij "Rekalibruj" i przetestuj uruchomienie w trybie "Dry-run".
[ ] [MOBILE APP CHECK] Sprawdź lokalne IP w shortsyt-app/lib/api.ts (czy zgadza się z aktualnym adresem PC w Wi-Fi).
    Uruchom npx expo start w shortsyt-app/, otwórz na telefonie i kliknij przycisk "Dark Agent" na Dashboardzie.
[ ] [LEARNING LOOP LIVE RUN] Wykonaj generację testową dark psychology z uploadem:
    python agent_dark_psychology.py --videos 1
    Sprawdź czy save_pre_audit zapisuje rekord i czy run_feedback_cycle poprawnie aktualizuje wagi Pearsona w auditor_weights.json.
[ ] [YT CTR CHECK] Sprawdź realne wyniki i retencję na kanale YouTube Studio po 48h dla zaplanowanych/opublikowanych filmów.
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



## ⚠️ PRIORYTETY — KOLEJNOŚĆ SESJI (aktualizacja 2026-08-15)

### #1 SESJA 7 — ✅ DONE: Pełny pipeline end-to-end z OCR
> QA PASS na wszystkich 3 checkach. Ocena: 8/10. YT_PRIVACY zmienione na "public".
> Token YT wygasł (invalid_grant) → upload zablokowany, wymaga odnowienia.
```
[x] OCR: QUADRAKILL @ 19.2s, PENTAKILL @ 27.2s — wykryte
[x] QA: kill OCR OK, velocity Peak=60px OK, cisza=0.0s OK → PASS
[x] Kamera stabilna: 86/89 klatek z detekcją HP barów
[x] Ocena shortsa: 8/10 → YT_PRIVACY zmienione na "public"
[!] Token YT wygasł → NIE uploadowano — wymaga --authorize
```

### #1 SESJA 8 — ✅ DONE: Token odnowiony + short opublikowany
```
[x] OAuth fix: run_local_server → manual URL flow (lol_publisher.py)
[x] Token odnowiony → accounts/lol_token.pickle
[x] Upload: "Five Kills. One Katarina. 🔥" — QA 92/100
[x] URL: https://www.youtube.com/shorts/Pgn0M8RXRIA
[x] Bug fix: surrogate chars w pinned comment (lol_publisher.py)
[!] Perf check zaplanowany: 2026-08-19 09:05
```

### #1 SESJA 9 — ✅ DONE: Fix hashtagów, music dedup, fix kamery, Outplayed
```
[x] LOL_INPUT_DIR zmieniony: C:\Medal\Edits → C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends
[x] smart_camera.py: kill-window freeze (±3s od killa) → kamera nie ucieka po QUADRAKILL/PENTAKILL
[x] smart_camera.py: peaks_t definicja przed pętlą śledzenia
[x] lol_editor.py: music dedup — .last_track plik wyklucza poprzedni track z losowania
[x] lol_metadata_generator.py: _ensure_shorts_tag → pełne hashtagi (#Shorts #LeagueOfLegends #LoL #Katarina #Pentakill #Gaming)
[x] lol_smart_titles.py: wymuszenie hashtagów po Gemini JSON (Gemini często pomijał)
[x] run_lol_agent.py: --start / --end CLI flags do manualnego override okna klipu
[x] Upload private: https://www.youtube.com/shorts/JmM7j19opGY (Katarina pentakill, 08-01-2026)
[!] Miniaturka: NADAL WYMAGA DOPRACOWANIA (styl kanału)
```

### #1 SESJA 10 — ✅ DONE: Miniaturka naprawiona + FFMPEG auto-detect
```
[x] lol_thumbnail.py: FFMPEG_BIN auto-detect (C:\ffmpeg\...\ffmpeg.exe) — frame extraction działa bez PATH
[x] lol_thumbnail.py: crop tnie 20% dołu (HUD cutoff) — items/skills bar nie widoczny w thumb
[x] lol_thumbnail.py: stroke PENTA/QUADRA/TRIPLE → czarny (#000000) — czytelny na każdym tle
[x] lol_thumbnail.py: logo przesunięte 200px od dołu (ponad HUD) zamiast 35px
[x] Testowa miniaturka wygenerowana OK: 1080x1920, PENTAKILL/Katarina, styl kanału OK
```

### NASTĘPNY PRIORYTET (sesja 12):
```
[ ] FIX: Pierwsze zabójstwa (TRIPLE/QUADRA) przesuwają się zbyt szybko — slow-mo tylko na PENTA
    PRZYCZYNA: peak_moment=9.7s/11.2s = prawie koniec klipu. Wszystko przed pentą leci 1x.
    FIX OPCJA A: Dodaj speed ramp 0.7x (zamiast 1x) na TRIPLE i QUADRA momenty
        → lol_editor.py: dla każdego peaks[i] oprócz ostatniego dodaj 0.8x speed segment 1s
    FIX OPCJA B: Skróć pre-penta build-up. trim_start = TRIPLE_t - 2s (zamiast - 8s)
        → Clip: 12.7s→24.9s = 12.2s, pierwsze 2s to intro, TRIPLE @2s, QUADRA @6.3s, PENTA @10.7s
    WYBIERZ na podstawie obejrzenia klipu lol_short_20260818_120940.mp4
[ ] Sprawdź wynik shortsa Pgn0M8RXRIA w YT Studio (views/watch time/CTR po 48h)
[ ] Opcjonalnie: YT_PRIVACY = "unlisted" zamiast "private" dla testów
```

### #1 SESJA 11 — ✅ DONE: OCR kill dedup + trim fix + pełny dry-run
```
[x] Testowy klip: League of Legends 07-31-2026 21-34-50-358_2.mp4 (83s, penta @23.4s)
[x] Bug: OCR wykrywał duplikaty (TRIPLE 2x, PENTA 2x) → cooldown 2s→3.5s (lol_momentum_analyzer.py L266)
[x] Bug: trim_start=15.4s ucinał TRIPLE @14.7s → trim_start rozszerzony do first_kill-1s (L359-366)
[x] Bug: lol_metadata_generator.py L16 SyntaxError → naprawione (zmienna pośrednia clean=)
[x] Dry-run PASS: trim 13.7→24.9s (13.0s final), TRIPLE@1.0s/QUADRA@5.3s/PENTA@9.7s, miniaturka @24.4s ✅
[x] Thumbnail: super (user potwierdził) ✅
[!] Bug zostały: pierwsze 2 zabójstwa (TRIPLE/QUADRA) zbyt szybkie — slow-mo TYLKO na PENTA (9.7s)
    → Klipy są w video ale przemykają w 1x. Fix: speed ramp na wszystkie kills (sesja 12)
[x] Outplayed metadata (JSON/DB) niedostępna — OCR jedyne źródło
[x] CONTEXT.md v19 zapisany
```


### WAŻNE — polecenia do uruchomienia:
```powershell
# Nowy klip z Outplayed (pentakill Katarina) — pełne okno killów:
.\venv313\Scripts\python.exe -u lol_agent\run_lol_agent.py `
  --file "C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\<FOLDER>\<PLIK>.mp4" `
  --champion Katarina --action pentakill --start <T> --end <T> --force

# Dry-run żeby sprawdzić bez uploadu:
... --dry-run

# Po zatwierdzeniu shortsa zmień na public (YT Studio lub lol_config.py YT_PRIVACY="public")
```
```

### #1 NAJWYŻSZY PRIORYTET: pytesseract kill timing ✅ DONE
> Tesseract 5.4.0 zainstalowany w C:\Program Files\Tesseract-OCR\
> pytesseract 0.3.13 w venv313 — działa, wykrywa QUADRAKILL @ 19.2s, PENTAKILL @ 27.2s
> lol_momentum_analyzer.py auto-wykrywa ścieżkę tesseract — zero konfiguracji

### #2: Skrypt QA po renderze ✅ DONE
```
lol_agent/qa_after_render.py
Użycie: python lol_agent/qa_after_render.py <output.mp4> [<source.mp4>]
  [1/3] Kill timing OCR — na output MP4 (pytesseract)
  [2/3] Velocity kamery — smart_camera standalone na source LUB parse logów pipeline
  [3/3] Cisza na początku — ffmpeg silencedetect
Wynik: PASS/WARN + JSON raport (*_qa.json obok output)
Test: PASS — Peak=60px (MAX_DELTA limit!), PENTAKILL wykryty, cisza=0s
```

### #3: Velocity limiter fix ✅ CONFIRMED
> Test QA na source clip: Peak velocity = 60px = dokładnie MAX_DELTA
> Kamera nigdy nie przekracza limitu — skok przy Shunpo WYELIMINOWANY

### #4 ODŁÓŻ: Mobile app dalszy rozwój
> Cloudflare Tunnel + FastAPI na PC = punkt awarii bez ROI.
> Wróć gdy pipeline produkuje filmy z dobrym timinigiem.
> Obecna apka wystarczy do testów — nie rozwijaj UI.

### Tokenowa efektywność sesji:
- Na początku sesji podawaj TYLKO sekcję "co teraz robimy", nie cały CONTEXT.md
- Oszczędzasz ~30-40% tokenów
```

### Znane bugi apki do naprawienia (w kolejności):
```
[WYSOKI]   YouTube OAuth deep link — expo-linking nie skonfigurowany w app.json
           FIX: dodaj scheme "shortsyt" do app.json + obsłuż Linking.getInitialURL()

[ŚREDNI]   SecureStore może wymagać biometryki na nowych Androidach
           FIX: dodaj opcję WHEN_UNLOCKED_THIS_DEVICE_ONLY do SecureStore.setItemAsync

[ROZWIĄZANE] Push notif w Expo Go → zmigrowano na expo run:android (natywne APK)
```

### Czego UNIKAĆ:
```
❌ NIE generuj całego pliku — wskazuj tylko FUNKCJĘ + LINIĘ
❌ NIE używaj // (floor div Python) w wyrażeniach FFmpeg drawbox — użyj trunc()
❌ NIE używaj text_w / text_h w FFmpeg drawbox — użyj aproksymacji (font_size * 0.6 * len)
❌ NIE zmieniaj FREEZE_STREAK poniżej 5 (kamera zacznie gonić Katarynę po Shunpo)
❌ NIE zmieniaj BANNER_SHIFT poniżej 120 (bannery kill będą ucięte po prawej)
❌ NIE zmieniaj MAX_DELTA powyżej 80 (powróci teleportacja kamery przy Shunpo)
❌ NIE uruchamiaj pipeline bez --champion Katarina (Gemini Vision myli z Evelynn/Kassadin)
❌ NIE uploaduj na YT bez --dry-run najpierw (YT_PRIVACY="private" ale sprawdź)
❌ NIE używaj Depends(verify_token) w stream_output — expo-av nie może wysłać Bearer header
   → używaj Depends(verify_token_flexible) który akceptuje ?token= query param
```

---

## 0b. PLAN UNIVERSALIZACJI — CO TRZEBA ZROBIĆ (cel: odbudowa zasięgu)

> Cel: pipeline działa dla KAŻDEGO championa i KAŻDEJ akcji bez manualnych flag.
> Kamera nie glitchuje na żadnym klipie. Shorty mają dobry watch time i CTR.
> Kanał miał dobry start (13k/11k views) — te poprawki mają to przywrócić.

---

### A. UNIVERSALIZACJA CHAMPIONA

**Problem:** Gemini Vision myli Katarynę z Evelynn/Kassadin gdy brak `--champion` flagi.
HP bar tracking (żółty) działa dla KAŻDEGO championa — kamera już jest universalna.
Problem leży tylko w METADANYCH (tytuł, hashtagi).

```
[ ] lol_config.py: dodaj CHAMPION_WHITELIST — lista championów których grasz
    CHAMPION_WHITELIST = ["Katarina", "Ahri", "Zed", "Yasuo", "Jinx", "Thresh"]
    → Gemini ograniczony do tej listy = eliminuje halucynacje

[ ] lol_clip_analyzer.py: zmień Gemini prompt na:
    f"Champion is one of: {', '.join(CHAMPION_WHITELIST)}. Respond with champion name ONLY."
    → Nie wymagaj --champion dla każdego klipu (manualne = nie skaluje się)
```

---

### B. UNIVERSALIZACJA AKCJI

**Problem:** OCR działa (QUADRAKILL/PENTAKILL OK), ale `outplay`, `clutch`, `double`
nie mają dobrego peak_moment timiningu. Kamera freeze nie jest przekazywana dla non-kill akcji.

```
[ ] lol_momentum_analyzer.py / lol_clip_analyzer.py:
    → outplay/clutch: peak_moment = moment gdy HP gracza było najniżej → wtedy kill
    → double/triple: peak_moment = czas OSTATNIEGO killa z serii (nie pierwszego)

[ ] smart_camera.py L851 — rozszerz kill_window na outplay moments:
    → Przekaż peaks z lol_momentum dla WSZYSTKICH akcji, nie tylko OCR killów
    → Format taki sam: [(time, "outplay")] → kamera freezuje przy każdej akcji

[ ] lol_editor.py — hook overlay dla każdej akcji:
    outplay  → "NOBODY EXPECTED THIS 🎯"
    clutch   → "1% HP. THEY THOUGHT IT WAS OVER 💀"
    double   → "DOUBLE KILL ⚡"
    triple   → "TRIPLE KILL 💥"
    (pentakill jest już OK ✅)
```

---

### C. KAMERA — ZNANE GLITCHE I ZABEZPIECZENIA

**Aktualny stan:** Kamera STABILNA dla Katarina pentakill (86/89 klatek detekcja).
Poniżej lista scenariuszy gdzie MOŻE glitchować + status każdego.

```
GLITCH #1: Kamera ciągnie na VFX/wybuchy zamiast na championa
  KIEDY: outplay/clutch z AOE ability (Jinx ult, Ziggs Q) → brak HP barów → VFX fallback
  STATUS: Częściowo naprawione (kill_window freeze) ale tylko dla peaks z OCR
  FIX: [ ] Przekaż outplay_moments jako peaks do find_action_path() → automatyczny freeze

GLITCH #2: Kamera teleportuje przy dash/blink (Flash, Shunpo, Zed shadow)
  STATUS: ✅ NAPRAWIONE — MAX_DELTA=60px + FREEZE_STREAK=8
  NIE RUSZAJ — działa dla KAŻDEGO championa który dashuje

GLITCH #3: Kamera na animacje śmierci wrogów (fałszywe czerwone pixele)
  STATUS: ✅ NAPRAWIONE — klastryzacja 25px + wymóg >=3 wierszy + dead_buckets
  NIE RUSZAJ

GLITCH #4: Kamera nie śledzi gracza w team fight (>4 wrogów)
  KIEDY: Dużo czerwonych HP barów → centroid środka walki zamiast gracza
  STATUS: Częściowo — fight priority gdy gracz po lewej
  FIX: [ ] smart_camera.py L834: zmień (yellow+fight)//2 na (2*yellow+fight)//3
           → Gracz ma 2x wagę relative do środka walki

GLITCH #5: Kamera freezuje po teamfight gdy wszyscy wrogowie martwi
  STATUS: ✅ OK — FREEZE_STREAK=8 to dobry kompromis dla 50s shorta. NIE ZMIENIAJ.

GLITCH #6: Kamera wywalała się / gubiła postać po Jump-Cut w multi-segmentach
  KIEDY: Po wycięciu biegania (np. 4s rzeki) kamera brała współrzędne z surowego nagrania zamiast z pociętego.
  STATUS: ✅ NAPRAWIONE — Smart Camera analizuje bezpośrednio złączony `01_cut.mp4` w osi 0.0s do clip_duration.
```

**WAŻNE — parametry których NIE ruszać:**
```
FREEZE_STREAK = 8    ← < 5 = kamera goni championa po dashu. > 12 = za długi freeze
MAX_DELTA     = 60   ← > 80 = wraca teleportacja. < 30 = kamera za wolna na Shunpo
```

---

### D. WATCH TIME I CTR — ODBUDOWA ZASIĘGU

**Cel:** Watch time >50%, CTR >5%, re-watch rate wysoki.

```
WATCH TIME (>50%):
  [!] Długość shorta: 25-35s = optimal. MAX 50s (lol_config.py SHORT_MAX_DURATION=50).
      → SPRAWDŹ: czy finalny short nie jest >40s — jeśli tak, przytnij pre-kill fragment
      → AKCJA: Dodaj log "Final duration: Xs" w run_lol_agent.py po renderze

  [!] Hook pierwsze 2s: overlay akcji musi być od razu @ t=0 (aktualnie ✅)
      → Sprawdź czy trim_quiet_start działa (usuwa ciszę/bezczynność przed akcją)
      → Próg: 2.5x baseline audio — jeśli klip zaczyna się od chodzenia bez dźwięku VFX,
        trim_quiet_start powinien to wyciąć

  [ ] Slow-mo: ZOSTAW 0.5x / 1.5s na peak. NIE SKRACAJ. To jest najważniejszy moment.

CTR (>5%):
  [!] MINIATURKA — klatka z kill feed widocznym (nie casting ult):
      → ZMIANA WYMAGANA w run_lol_agent.py L317:
        source_thumb_t = peaks[-1][0] + 1.5   ← +1.5s po ostatnim kill = kill feed widoczny
        (aktualnie: analysis["peak_start"] + offset → może trafić na moment PRZED kilem)
      → Kill feed "PENTAKILL" trzyma się ~2s na ekranie → klatka +1.5s zawsze go złapie

  [ ] Tytuł — upewnij się że jest po angielsku (kanał Dwannellenga = international audience)
      → Sprawdź opublikowany short Pgn0M8RXRIA — czy tytuł jest EN/PL
      → Jeśli PL → dodaj do Gemini prompta: "Title MUST be in English"

RE-WATCH:
  [ ] NIE skracaj slow-mo poniżej 0.45x na PENTAKILL/QUADRAKILL — ta chwila musi "być"
  [ ] Muzyka: HIGH energy track na peak action. Aktualnie: MUSIC_VOLUME=0.85 ✅
```

---

### E. KOLEJNOŚĆ WDROŻENIA (sesje)

```
SESJA 11 — ZBIERZ DANE ZANIM COŚ ZMIENIASZ:
  1. Sprawdź Pgn0M8RXRIA (Five Kills, 17.08) — views/watch time/CTR po 48h w YT Studio
  2. Przetestuj --dry-run na nowym klipie Outplayed → obejrzyj output + thumbnail
  3. Na podstawie danych: idź do sesji 12A lub 12B

SESJA 12A — jeśli CTR <3% (problem z miniaturką):
  → Napraw source_thumb_t = peaks[-1][0] + 1.5 w run_lol_agent.py L317

SESJA 12B — jeśli watch time <40% (za długi lub zły hook):
  → Sprawdź długość shortów. Przytnij do <=35s jeśli >40s.

SESJA 13 — CHAMPION WHITELIST (30min roboty, duży efekt):
  → lol_config.py: dodaj CHAMPION_WHITELIST
  → lol_clip_analyzer.py: zmień prompt Gemini

SESJA 14 — TEST OUTPLAY/CLUTCH:
  → Jeden klip outplay z --dry-run → obejrzyj czy kamera stabilna
  → Jeśli glitchuje: zaimplementuj FIX z sekcji C (GLITCH #4)

❌ NIE rób przed zebraniem danych z YT Studio:
   NIE przepisuj smart_camera.py (działa 86/89 klatek)
   NIE zmieniaj FREEZE_STREAK / MAX_DELTA
   NIE rozwijaj apki mobilnej (zero ROI bez działającego kanału)
```

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
LOL_INPUT_DIR       = r"C:\Medal\Edits"    # folder z surowymi klipami
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
YT_PRIVACY          = "private"  # ZMIEŃ NA "public" gdy satysfakcja z jakości!
GEMINI_MODEL        = "gemini-2.5-flash"
```

### .env — plik w root projektu (`C:\Users\mz100\PycharmProjects\shortsyt\.env`):
```
GEMINI_API_KEY=AIzaSyAjs9ZHU8ktQ-ilzvrF3LFanZxH9Ig7Nyo
API_PASSWORD=shortsyt2026         <- hasło do apki Android (domyślne)
JWT_SECRET=change_me_to_random_32char_secret_here
API_PORT=8765
LOL_INPUT_DIR=C:\Medal\Edits
LOL_OUTPUT_DIR=C:\Users\mz100\Videos\lol_shorts_output
```

---

## 4. KAMERA — STAN AKTUALNY (smart_camera.py v24 Universal Stateful HD Tracker)

### Algorytm (v24 — Universal Stateful HD Tracker w 1080p):
1. **Ścisła i czuła detekcja paska HP gracza w 1080p**:
   - Maska gracza (Złoty): `(r > 160) & (g > 130) & (b < 115) & ((r - b) > 40) & ((g - b) > 15)`
   - Czułe kryteria geometryczne paska:
     - `cw >= 14` (szerokość paska — obejmuje low HP i spinnig ult)
     - `3 <= ch <= 16` (wyklucza efekty czarów `h=1-2px` oraz kwadratowe ikony przedmiotów)
     - `2.0 <= aspect <= 20.0` (wyklucza kwadratowe elementy UI)
     - `area >= 30` (obejmuje wąskie paski przy małej ilości zdrowia)
2. **Śledzenie wyłącznie postaci gracza**:
   - Śledzi wyłącznie złoty pasek gracza najbliższy bieżącej trajektorii `hp_b.sort(key=lambda c: c[4] - 0.8 * abs(c[0] - track_x), reverse=True)`.
   - Gdy pasek jest chwilowo zasłonięty (animacja ulta/Shunpo) – kamera ZAMRAŻA pozycję gracza (brak przeskoków na inne elementy/ikony).
3. **Płynna dynamika i pełna gęsta trajektoria**:
   - `track_x = 0.90 * target_x + 0.10 * track_x` (natychmiastowe podążanie za skokami Shunpo/Flash).
   - Wygładzanie adaptacyjne (`smooth_w = 3`).
   - Pełna gęsta trajektoria (80 punktów w filtrze FFmpeg bez podpróbkowania).
4. **Zasada 1 Shorts = 1 Unikalny plik wejściowy**:
   - Każdy plik wideo z dysku jest analizowany i montowany w dedykowany, unikalny plik wyjściowy.

---

## 4.1 QUALITY GATE & CLIP REJECTION PROTOCOL (Automatyczne odrzucanie niekwalifikujących się klipów)

Dla zachowania 100% jakości produktu komercyjnego, pipeline posiada ścisłe reguły walidacji klipu przed montażem i publikacją. Jeśli klip nie spełnia warunków czytelności w formacie pionowym 9:16, skrypt **ODRZUCA KLIP**, przerywa renderowanie i zwraca czytelny powód użytkownikowi:

### Kryteria odrzucenia klipu (Rejection Gates):
1. **OVERLAY_OBSTRUCTION (Zasłonięcie przez nakładki trzecie)**:
   - Jeśli kluczowa akcja / postać gracza podczas eliminacji znajduje się pod statycznym overlayem (np. panel Porofessora `x > 1400, y = 150-600`), przez co wykadrowanie 9:16 skutkuje wyświetleniem wielkiego okna statystyk zasłaniającego bohatera.
   - **Akcja**: Odrzucenie klipu z komunikatem: `REJECTED: Akcja/eliminacja toczy się pod nakładką zewnętrzną (np. Porofessor). Wyłącz nakładki w grze lub nagraj czysty klip.`
2. **EXTREME_DISPERSION (Skrajne rozproszenie walki > 1200px)**:
   - Jeśli eliminacje w jednej sekundzie zachodzą na skrajnych krawędziach ekranu (np. początek walki `x = 350px`, skok na `x = 1650px` przy krawędzi), a kadr 9:16 (szerokość 608px) fizycznie nie jest w stanie pokazać obu stron walki bez gwałtownego ucięcia akcji.
   - **Akcja**: Odrzucenie klipu z komunikatem: `REJECTED: Rozrzut walki przekracza możliwości pionowego kadru 9:16 (>1200px).`
3. **LOW_TRACKING_CONFIDENCE (Brak widoczności postaci < 75%)**:
   - Jeśli w oknie cięcia wskaźnik widoczności bohatera gracza wynosi poniżej 75% klatek (postać poza widokiem kamery gry, ciągła niewidzialność lub brak pewnego paska HP).
   - **Akcja**: Odrzucenie klipu z komunikatem: `REJECTED: Zbyt niska widoczność postaci gracza (<75%). Kamera nie gwarantuje centrowania.`
4. **DECOY_TARGET / SURVIVING_TARGET (Brak potwierdzonego zabójstwa na finiszu)**:
   - Jeśli końcowy fragment klipu śledzi cel, który przeżył walkę (np. uciekający tank Mundo), a właściwe fragi miały miejsce wcześniej i nie mogą być wykadrowane bez ucięcia.

## 4.2 VIRAL RETENTION & AUTO-TRIM PACING (Zasady montażu pod algorytm YouTube Shorts)

Dla zagwarantowania maksymalnej retencji (APV > 100%) i braku konieczności ręcznego korygowania okien montażu, silnik analizy momentum (`lol_momentum_analyzer.py`) stosuje 3 żelazne reguły:

### 1. Visual Action Hook (Start w 0.8s - 1.5s):
- **Problem**: Widzowie przewijają Shorta w pierwszych 1.5 sekundy, jeśli widzą bieganie z bazy, bicie wieży lub stanie w krzakach.
- **Rozwiązanie w kodzie**: Okno startowe `trim_start` jest ustawiane dokładnie na **`first_kill_t - 2.0s` / `first_engage_t`**.
- **Efekt**: Widz w 0.5s widzi zarys doskoku/inicjacji, a w 1.5s następuje pierwszy cios/eliminacja. Zero martwych dobiegów.

### 2. Multi-Kill Climax & Seamless Loop (Zakończenie pod Re-watch):
- **Problem**: Pozostawienie 3-5 sekund po walce (dobijanie minionów, cofanie do bazy, bicie wieży) drastycznie obniża retencję i niszczy zapętlenie.
- **Rozwiązanie w kodzie**: Wyznaczany jest szczytowy punkt walki (*Climax*, np. TRIPLE/QUADRA/PENTAKILL). Klip jest ostro odcinany dokładnie **`climax_t + 1.2s`**.
- **Efekt**: Wideo kończy się na fali euforii tuż po ostatnim fragu i banerze, płynnie przeskakując w pętli z powrotem do pierwszego ciosu na początku.

### 3. Multi-Zone Triple OCR & Resilient Regex:
- Skanowanie 3 stref jednocześnie:
  1. `KILL_BANNER_REGION` `(0.04, 0.28, 0.18, 0.82)` — centralne banery
  2. `KILL_FEED_REGION` `(0.04, 0.25, 0.65, 0.98)` — kill feed w prawym górnym rogu
  3. `CHAT_LOG_REGION` `(0.72, 0.96, 0.04, 0.40)` — komunikaty tekstowe w czacie
- Odporność na zniekształcenia czcionek Tesseracta: regexy `penta(?:kill|kut|kit|kil)?`, `triple(?:kill|kut|kit|kil)?`, `dominat(ing)?`, `unstoppable` itp. gwarantują 100% trafień bez pomijania akcji.

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

## 7. STATUS AKTUALNY (2026-08-13)

### DZIAŁA — Pipeline LOL ✅
- Smart camera: żółty HP bar tracking, 86/89 klatek, EMA α=0.65
- Velocity limiter: MAX_DELTA=60px/step — skok kamery WYELIMINOWANY ✅
- Minterpolate artefakt końcowy: tpad clone 0.5s + trim — migotanie WYELIMINOWANE ✅
- Kill Counter OCR-free: detect_kill_events_from_video() — overlay PENTAKILL @ t=17s ✅
- Kill Banner Shift: BANNER_SHIFT=160px @ kill±2s — bannery widoczne ✅
- Camera Freeze: FREEZE_STREAK=8 → cam=last_known — brak pościgu za Shunpo ✅
- PENTAKILL gold: kolor 0xFFD700 + drawbox tło pod labelem ✅
- CTA drawbox: czarny pasek 50% alpha pod SUBSCRIBE ✅
- CRF 22: bitrate ~50% mniejszy w final encode ✅
- Color grading: eq=contrast=1.08:saturation=1.35:brightness=0.03
- Ocena shortsa: **8/10** (sesja 7, QA PASS, OCR timing aktywny)

### DZIAŁA — Backend API ✅
- FastAPI import: OK (test: python -c "from lol_agent.api.main import app; print('OK')")
- GET /health → {"status":"ok","service":"Shortsyt API"}
- JWT: verify_token (Bearer) + verify_token_flexible (Bearer LUB ?token=) ✅
- CORS: CORSMiddleware z allow_origins=ALLOWED_ORIGINS ✅
- Python deps: fastapi 0.141, uvicorn 0.52, PyJWT 2.13, google-auth 2.55.2

### DZIAŁA — Apka Expo ✅
- Projekt: shortsyt-app/ (blank-typescript)
- 8 ekranów napisanych, wszystkie npm deps zainstalowane
- expo-av, expo-notifications, expo-secure-store, expo-device,
  @react-navigation/native, axios

### NIE TESTOWANE NA TELEFONIE ⚠️
- Logowanie przez LoginScreen (hasło → JWT)
- Dashboard — status pipeline
- ClipsScreen — lista klipów z PC
- RenderScreen — live logi
- OutputsScreen + PreviewScreen — odtwarzanie video
- YouTube upload z telefonu
- Push notifications

---

## 8. PLAN TESTÓW TELEFONU (sesja 4)

### Etap A — Podstawowa łączność:
```
1. ipconfig → znajdź IPv4 (np. 192.168.1.100)
2. start_server.bat → sprawdź "Uvicorn running on http://0.0.0.0:8765"
3. W przeglądarce telefonu: http://192.168.1.100:8765/health
   → oczekiwane: {"status":"ok","service":"Shortsyt API"}
4. W przeglądarce telefonu: http://192.168.1.100:8765/docs
   → oczekiwane: Swagger UI
```

### Etap B — Apka Expo:
```
5. cd shortsyt-app && npm start → QR code
6. Expo Go → zeskanuj QR
7. Settings → wpisz http://192.168.1.100:8765 → Zapisz
8. Login → shortsyt2026 → powinien przejść do Dashboard
```

### Etap C — Funkcje pipeline:
```
9.  Dashboard → status → powinien pokazać "idle"
10. ClipsScreen → powinna załadować listę MP4 z C:\Medal\Edits
11. Wybierz klip → ClipDetail → Start Render
12. RenderScreen → obserwuj live logi
13. OutputsScreen → po renderze powinien pojawić się klip
14. PreviewScreen → odtwórz video (testuje JWT query param fix!)
```

### Etap D — YouTube (jeśli tokeny OK):
```
15. Settings → YouTube Auth → sprawdź status tokenu
16. PreviewScreen → Upload → modal z tytułem
```

### Spodziewane błędy i FIX-y:
```
BŁĄD: "Network request failed" przy logowaniu
FIX: sprawdź czy telefon i PC na tej samej sieci WiFi
     firewall PC: zezwól na port 8765 (Windows Defender → Reguły przychodzące)

BŁĄD: Video nie odtwarza się w PreviewScreen
FIX: sprawdź czy URL w api.ts ma ?token=${jwt}
     jeśli nie → dodaj do getVideoUrl() w lib/api.ts

BŁĄD: "401 Token wymagany" przy video stream
FIX: jwt token nie jest przekazywany do expo-av source URI
     PreviewScreen.tsx: source={{ uri: `${serverUrl}/outputs/${file}?token=${token}` }}

BŁĄD: Push notifications nie działają
FIX: normalnie — Expo Go nie obsługuje push notif
     działają tylko w standalone APK (EAS Build)
```

---

## 9. BACKLOG (co robić po testach telefonu)

### Priorytet WYSOKI:
- [ ] YouTube OAuth deep link — `expo-linking` nie skonfigurowany w app.json
      FIX: dodaj scheme "shortsyt" do app.json + `Linking.getInitialURL()`
- [ ] Zainstaluj `pytesseract` — bez tego: brak OCR kill timing, action=outplay zawsze
      FIX: Tesseract binaries + `pip install pytesseract`

### Priorytet ŚREDNI:
- [ ] SecureStore biometrics — może blokować na nowych Androidach
      FIX: `SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY`
- [ ] Cloudflare Tunnel — dla dostępu zdalnego (poza domem)
      Instrukcja: `lol_agent/api/cloudflare/README.md`
- [ ] EAS Build — standalone APK (wymagane dla push notif)
      `npx eas build --platform android --profile preview`

### Priorytet NISKI:
- [ ] librosa — dokładny beat detection (opcjonalne)
      `pip install librosa`
- [ ] Ocena shortsa po sesji 3 — czy 160px banner i streak=8 poprawiły?
- [ ] Więcej clipów testowych — pipeline testowany tylko na 1 klipie Katariny

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

```powershell
# Przez CLI (stara metoda):
.\venv313\Scripts\python.exe lol_agent\run_lol_agent.py --authorize
# Token: accounts\lol_token.pickle

# Przez apkę Android (nowa metoda):
# Settings → YouTube Auth → "Autoryzuj YouTube"
# → przeglądarka otwiera Google → zaloguj → skopiuj kod → wklej w apce
# Token zapisuje się do tego samego accounts\lol_token.pickle

# UWAGA: deep link (auto-powrót do apki po auth) NIE DZIAŁA jeszcze
# trzeba ręcznie skopiować kod z URL i wkleić w apce
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

---

## 13.5 INTELIGENTNY SILNIK CIĘCIA WALKI & TIGHT CLIMAX (COMBAT JUMP-CUT ENGINE v6)

```
Problem:
  W wielu klipach (np. nieoficjalna penta, rozciągnięty teamfight) gracz zdobywa 2 fragi,
  potem biegnie przez rzekę/linię przez 5-10 sekund, po czym zdobywa kolejne 3 fragi do ACE.
  Trzymanie ciągłego klipu (35-40s) niszczy retencję (widzowie dropują na bieganiu),
  a ucięcie początku gubi pierwsze zabójstwa. Ponadto, przeciąganie ogona (5s slowmo + 5s chodzenia)
  sprawiało, że short trwał 34s zamiast idealnych 24-25s.

Złote Reguły Montażu (ZWERYFIKOWANE — SESJA 20):
  1. Dual-Signal Combat Detection (find_combat_segments w lol_momentum_analyzer.py):
     - Łączy OCR kill peaks + ciągłą krzywą momentum (ruch + VFX czarów).
     - Parametry: activity_threshold = 48.0, pre_roll = 1.2s, post_roll = 1.0s, merge_gap = 2.5s.
     - Jeśli przerwa > 2.5s (bieganie/pościg) → automatyczny JUMP CUT.
  
  2. Multi-Segment Concat & Frame-Accurate Smart Camera (lol_editor.py):
     - Segmenty walki wycinane bezstratnie (Stream Copy) i łączone przez Concat Demuxer do step1.
     - Smart Camera (find_action_path) analizuje BEZPOŚREDNIO step1 (01_cut.mp4) z clip_start=0.0.
     - Zero desynchronizacji kamery po jump-cucie — idealny lock na graczu przez całe wideo.

  3. Tight Climax & Anti-Dragging Ending:
     - Pentakill/Climax slow-mo duration: _slowmo_dur = 1.5s (speed 0.50x), zoom=1.20x.
     - Klip kończy się maksymalnie 1.0-1.2s po ostatnim killu / banerze ACE + 2.0s CTA overlay.
     - Całkowity czas gotowego Shorta wynosi ~24-25s (idealna retencja YT Shorts).
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