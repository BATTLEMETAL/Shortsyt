# LOL AGENT — MASTER CONTEXT
> Ostatnia aktualizacja: 2026-08-19 (sesja 16 — skan Outplayed OCR, dry-run batch mode, Tesseract path fix w rankerze)
> Wersja: v25 — PRODUKCYJNY PIPELINE (GOTOWY DO UPLOADU)
> CZYTAJ TEN PLIK NA POCZĄTKU KAŻDEJ SESJI — zastępuje analizę wszystkich plików

---

## ⚡ ZASADY OSZCZĘDZANIA TOKENÓW (dla AI — stosuj zawsze)
```
✅ Odpowiadaj KRÓTKO i na temat — zero sykofancji, zero wstępów
✅ Pokazuj tylko zmienione linie, nie cały plik
✅ Pytania zadawaj TYLKO gdy konieczne — nie pytaj o oczywiste rzeczy
✅ Jeśli błąd jest jasny — od razu napraw, nie opisuj co zrobisz
✅ Używaj view_file(StartLine, EndLine) — nie czytaj całych plików
✅ Maksymalnie 5 zdań w odpowiedzi do użytkownika jeśli to możliwe
❌ Nie powtarzaj tego co właśnie zrobiłeś
❌ Nie pisz "Świetnie!", "Oczywiście!", "Rozumiem" itp.
❌ Nie opisuj kroków przed ich wykonaniem — po prostu je wykonaj
```

---

## 0. SZYBKI START NOWEGO CZATU ← CZYTAJ TO NAJPIERW

> **Jesteś AI asystentem projektu LOL AGENT.**
> Projekt: automatyczne YouTube Shorts z klipów League of Legends. Kanał: Dwannellenga.
> Ścieżka: `C:\Users\mz100\PycharmProjects\shortsyt\` | Venv: `.\venv313\Scripts\python.exe`

### Co jest gotowe (NIE ruszaj):
- ✅ Pipeline LOL: smart camera, velocity limiter, kill counter, slow-mo, overlays
- ✅ OCR kill detection: Tesseract 5.4.0 + pytesseract, wykrywa TRIPLE/QUADRA/PENTA ✅
- ✅ OCR dedup: dynamiczny cooldown (1.2s dla nowej etykiety, 3.5s dla tej samej) — brak duplikatów
- ✅ trim_start: first_kill - 9.5s (lol_momentum_analyzer.py L368) — łapie pełną walkę od początku ✅
- ✅ trim_end: peak + 1.2s (lol_momentum_analyzer.py L73, run_lol_agent.py L273) — idealny bufor zakończenia ✅
- ✅ Intermediate slow-mo: MINI_SPEED=0.6x, MINI_DUR=1.0s (lol_editor.py L230-231) — TRIPLE/QUADRA wyraźnie zaznaczone ✅
- ✅ Kotwiczenie kamery: yellow_src anchor + Connected Components (smart_camera.py L120, L810) — zero uciekania w bok ✅
- ✅ Kamera po doskoku Shunpo: EMA_ALPHA=0.70, smooth_w=5, MAX_DELTA=120px — natychmiastowe centrowanie 1. killa ✅
- ✅ FFmpeg Windows limit fix: -filter_complex_script (lol_editor.py) — ominięcie limitu WinError 206 ✅
- ✅ Short OPUBLIKOWANY na YouTube (PUBLIC): https://www.youtube.com/shorts/UZOmupNxfrU (Video ID: UZOmupNxfrU)
- ✅ Zaktualizowany Tytuł na YT: `Katarina Unstoppable Pentakill! 💥 No Escape 💀 #Shorts #LeagueOfLegends #LoL #Katarina`
- ✅ Miniaturka 9:16: automatyczny upload przez YouTube API (`youtube.thumbnails().set()`) ✅
- ✅ Quality Score: 82/100 [PASS] | Długość: 22.7s | Status: PUBLIC
- ✅ Backend FastAPI: /health OK, JWT auth OK, CORS OK
- ✅ YouTube OAuth: token zweryfikowany i odświeżony w accounts/lol_token.pickle ✅
- ✅ Multi-Hashtag w Tytule (lol_publisher.py L126-133): automatyczne doklejanie 3-4 mocnych hashtagów (`#Shorts #LeagueOfLegends #LoL`) do limitu 100 znaków.
- ✅ Rotacja muzyki (lol_editor.py L121-155): dedup z historią ostatnich 4 utworów (.last_track) zapobiega powtórzeniom.
- ✅ BANNER_SHIFT = 90px + ramp 0.5s (lol_editor.py L868)
- ✅ Perfekcyjna synchronizacja: Lead-in slow-mo -0.4s oraz offset napisów dynamicznych -1.2s.
- ✅ Gemini Multi-Model Fallback (lol_config.py, smart_titles, metadata_generator, clip_analyzer): auto-failover (gemini-3.7-flash -> gemini-3.5-flash -> flash-latest) przy 429/503/404 — 0 strat smart titles ✅
- ✅ Semantic Action Deduplication (run_lol_agent.py): OCR Action Fingerprint (kill sequence + inter-kill relative delta ±0.8s) — eliminuje ponowny upload tego samego meczu z innych cięć/plików ✅


### Parametry produkcyjne (NIE zmieniaj bez powodu):
```
lol_config.py          →  YT_PRIVACY = "public", CRF=22, SLOWMO=0.5x, ZOOM=1.20x, MUSIC=0.85, GAME=0.60
lol_publisher.py L~126 →  multi-hashtag appending (#Shorts #LeagueOfLegends #LoL)
lol_editor.py   L~868  →  BANNER_SHIFT = 90      (kill banner shift w lewo — optymalne -90px)
lol_editor.py   L~869  →  BANNER_WINDOW = 2.0    (sekundy ±kill)
lol_editor.py   L~219  →  lead-in -0.4s          (wejście w slow-mo 0.4s przed uderzeniem Pentakilla)
lol_editor.py   L~535  →  caption offset -1.2s   (napisy zsynchronizowane z momentem zgonu w grze)
lol_editor.py   L230-231→ MINI_SPEED = 0.6, MINI_DUR = 1.0 (mini slow-mo na intermediate kills)
lol_editor.py   L121-155→ multi-track history dedup (aktywna rotacja muzyki bez powtórzeń)
smart_camera.py L~743  →  FREEZE_STREAK = 8      (klatek bez HP barów → freeze)
smart_camera.py L~969  →  MAX_DELTA = 120        (max px/krok — responsywne centrowanie doskoków Shunpo)
smart_camera.py L~931  →  EMA_ALPHA = 0.70       (szybki ruch za doskokiem postaci)
smart_camera.py L~953  →  smooth_w = 5           (responsywne okno wygładzania)
smart_camera.py L~120  →  HP bar connectedComp   (precyzyjna separacja paska gracza od pancerza/aury)
smart_camera.py L~810  →  yellow_src anchor      (stałe kotwiczenie kadru na graczu)
lol_momentum_analyzer.py L72-73 → BUILD_BEFORE_PEAK=15.0, AFTER_PEAK=1.2, MAX_DURATION=30.0
lol_momentum_analyzer.py L368 → first_kill buffer = 9.5s
```

### PROFIL VIRALNY SHORTA (wynik master renderu lol_short_20260818_173432.mp4):
```
1. HOOK (0.0 - 2.5s):
   - Złoty napis 'PENTAKILL!' o t=0.3s natychmiast zatrzymuje scroll (Viewed vs Swiped Away >75%).
   - Wejście w walkę od t=5.2s klipu źródłowego (brak nudnego chodzenia na starcie).

2. RETENCJA & DYNAMIKA (22.7s idealna długość esportowa):
   - 0.0s - 8.0s  : Dynamiczny build-up, wejście w teamfight, fragi 1 & 2 (kamera natychmiast centruje 1. frag po prawej).
   - 8.3s - 10.3s : TRIPLE KILL — natychmiastowy napis przy killu + mini slow-mo 0.6x (1.0s).
   - 12.0s - 14.2s: QUADRAKILL — perfekcyjna synchronizacja napisu z natychmiastowym zabójstwem w 12s.
   - 17.8s - 20.7s: PENTAKILL — lead-in 0.4s przed ciosem + zwięzłe, satysfakcjonujące slow-mo 0.5x z dźwiękiem i banerem.
   - 20.7s - 22.7s: Punchy 2-sekundowe outro z CTA 'SUBSCRIBE FOR MORE' bez przedłużania końcówki.

3. KAMERA & KADROWANIE:
   - Nowy algorytm detekcji geometrii paska HP gracza eliminuje mylenie z aurą Leony.
   - Kamera natychmiast wycentrowuje pierwsze zabójstwo po prawej stronie po doskoku.

4. METADANE:
   - Tytuł: "Katarina Unstoppable Pentakill! 💥 No Escape 💀 #Shorts #LeagueOfLegends #LoL #Katarina"
   - Miniaturka: Klatka z wyraźnym napisem PENTAKILL w killfeedzie, czarny obrys, 1080x1920 przesłana przez API.
```

### 🚀 ROADMAP NA KOLEJNY CZAT (Sesja 16):
1. **Przetwarzanie wsadowe nowych nagrań (Batch Mode)**:
   - Automatyczne przeszukiwanie katalogu `C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\` w poszukiwaniu nowych nagrań.
   - Automatyczny montaż i publikacja kolejnych shortów z zachowaniem sprawdzonych parametrów v25.
2. **Monitoring statystyk opublikowanego shorta**:
   - Odpytanie YouTube Analytics dla wideo `UZOmupNxfrU` (wyświetlenia, retencja, CTR miniaturki).
3. **Dalsze wzbogacanie biblioteki muzycznej**:
   - Dodanie nowych utworów NoCopyrightSounds do `lol_music/` z mapowaniem dropów w `MUSIC_DROP_MAP`.

### Komenda publikacji na YouTube (Public):
```powershell
$env:PYTHONIOENCODING="utf-8"
.\venv313\Scripts\python.exe -u lol_agent\run_lol_agent.py `
  --file "C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_07-31-2026_21-18-13-162\League of Legends 07-31-2026 21-34-50-358_2.mp4" `
  --champion Katarina --action pentakill
```

---



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