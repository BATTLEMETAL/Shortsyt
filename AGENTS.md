# Wytyczne Pracy dla Projektu Shortsyt / Flikcut

Te reguły obowiązują automatycznie przy każdej pracy w tym katalogu i jego podkatalogach.

## 1. Sykofankcja 0
- Zero pochlebstw, pustych uprzejmości, nadmiernego entuzjazmu i korporacyjnej waty.
- Odpowiedzi techniczne, bezpośrednie, oparte wyłącznie na twardych faktach z kodu i wyników poleceń.
- Komunikacja w języku polskim (o ile użytkownik nie poprosi inaczej).

## 2. Ekstremalna Oszczędność Tokenów (Zero Tabel i Opisów w Czacie)
- **ZAKAZ wypisywania tabel, diagramów Mermaid, przewidywań i długich opisów w konwersacji (czacie).** Wszystkie tabele, diagramy, diagnozy, zamierzenia i opisy co robi kod zapisuj **wyłącznie bezpośrednio w pliku `TODO.md`**.
- W oknie konwersacji pisz tylko absolutne minimum (2–4 krótkie zdania): co zapisano/zaktualizowano w `TODO.md` lub jaki jest wynik testu + krótkie pytanie o decyzję.
- Zawsze najpierw lokalizuj kod (`Select-String`), a następnie czytaj wyłącznie wąskie zakresy (`StartLine` / `EndLine`). Łącz niezależne wywołania równolegle.

## 3. Brak Zgadywania i Halucynacji (Stop & Ask on Missing Data)
- Jeśli brakuje kluczowych danych, konfiguracji, wymagań biznesowych albo dostęp do zasobu jest zablokowany — **przerwij pracę natychmiast** i napisz użytkownikowi, czego dokładnie brakuje.
- Nigdy nie wymyślaj nazw plików, symboli, wyników testów ani statystyk. Każda podawana liczba i status musi wynikać bezpośrednio z odczytanego pliku lub uruchomionego narzędzia.
- **Trudne klipy testowe (Outplayed Favorites):** Niewygodne klipy, na których skrypt nie wyrabia, znajdują się w ulubionych (`Favorites`) w Overwolf Outplayed (`C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\...`; aktualny klip referencyjny z quadrą i kradzieżą smoka: `C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_11-17-2026_18-04-02-494\League of Legends 11-17-2026 18-24-25-826_0.mp4`).

## 4. Standard Inżynierski (Senior / Staff AI Engineer)
- Brak duplikacji logiki (wydzielaj wspólne helpery), płytkie zagnieżdżenia, jawna obsługa błędów brzegowych.
- Każda zmiana w backendzie weryfikowana przez `pytest`, a zmiana we frontendzie przez `npm run build` (`tsc && vite build`).
- Jeśli zmiana dotyczy aplikacji desktopowej (`shortsyt-desktop`), na końcu przebuduj `dist/` i zaktualizuj `app.asar`.
- **Dyrektywa Lokalnego AI (Zero Limitów API):** Każde zadanie tekstowe lub klasyfikacyjne korzystające dotąd z płatnego/limitowanego `Gemini API` przenosimy na lokalny silnik **Synapsa** (`Qwen2.5-7B-4bit` na RTX 3060 12 GB + adaptery LoRA) oraz lokalną analizę obrazu (`OpenCV` + `pytesseract`), zostawiając API chmurowe najwyżej jako opcjonalny fallback.

## 5. Główny Dokument Kontekstu (`TODO.md` — Jedyne Miejsce na Tabele i Diagramy)
- Cała aktualna struktura projektu, mapa modułów, twarde liczby bazowe, **wszystkie tabele statusów/propozycji** oraz **diagramy architektury Mermaid** znajdują się **wyłącznie wewnątrz pliku `TODO.md`** (działa on jako pełna „Przypominajka Kontekstu” dla kolejnych sesji). Nie duplikuj ich w czacie.
- Każda tabela w `TODO.md` używa kolumn:
  `Zadanie / Moduł` | `Po co (Cel)` | `Co wdrażamy / wdrożyliśmy` | `Stan` | `Rezultat / Diagnoza` | `Oczekiwania (Efekt docelowy)`
- Każdą zmianę infrastruktury lub przepływu danych rozrysowuj w `TODO.md` czytelnym diagramem **Mermaid** (`flowchart LR`, `flowchart TD`, `sequenceDiagram` — bez tagów HTML w etykietach, etykiety ze znakami specjalnymi w cudzysłowie `id["tekst"]`).

## 6. Cykl Życia Zadań i Bieżąca Aktualizacja `TODO.md`
- **Najpierw wpis propozycji do `TODO.md` -> w czacie tylko krótkie pytanie o start prac:** Proponowane zadania, diagnozy i diagramy dopisuj bezpośrednio do `TODO.md`, a w czacie napisz jedno zdanie, że plan jest w `TODO.md`, i zapytaj użytkownika, czy zatwierdza start wdrożenia.
- **Natychmiastowa aktualizacja przy każdym kroku:** Gdy zadanie zostanie wykonane i zweryfikowane testem/buildem, od razu zmień jego status w tabeli w `TODO.md` (`[ ]` -> `[/]` -> `[x]`), zaktualizuj diagram architektury i wpisz twarde wyniki testów do kolumny `Rezultat`.
