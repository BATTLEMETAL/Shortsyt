# FLIKCUT / SHORTSYT STUDIO — MASTER HANDOVER & AI ARCHITECTURE CONTEXT
> Ten plik to kopia dokumentu przekazania dla Claude / innego modelu AI.
> Pełny plik ze szczegółami znajduje się również w brain konwersacji:
> C:\Users\mz100\.gemini\antigravity\brain\7f2390b8-9211-43ee-8c46-b054be9ea661\CLAUDE_COMPLETE_SYSTEM_CONTEXT_AND_TEST_HANDOVER.md

---

## 1. W SKRÓCIE O PROJEKCIE
Shortsyt (rebranding na FlikCut Studio, flikcut.com) to autonomiczny system do montażu klipów 16:9 60fps na pionowe wideo 9:16 (608x1080) na YouTube Shorts, TikTok, Instagram i Facebook.
- Silnik: Python 3.13 (`venv313`), NVIDIA NVENC GPU, FastAPI (8765), Electron + React (5173).
- Stan testów: 263/263 passed (`pytest tests/`).

## 2. REGUŁY NIENARUSZALNE (ZAKAZY)
1. Wymiar 9:16: DOKŁADNIE 608x1080 (nie 607, NVENC wymaga parzystej szerokości).
2. Kamera: Śledzi WYŁĄCZNIE zielony pasek HP gracza. Zakaz fallbacku na czerwone paski (wieże mają czerwone paski przy niskim HP i szerokość >180px). W trybie standardowym kolor złoty jest w 100% wyłączony.
3. Zakaz cięcia `-c copy` po wyrenderowaniu: Niszczy GOP/PTS, powoduje 2s freeze obrazu i ucina pierwszy frag.
4. Solo Bolo (1v1): ZERO jump-cutów. Ciągły montaż 15s od 0.0s do 15.0s.
5. Teamfighty: lol_montage_director.py blokuje jump-cuty dla archetypu CHAOTIC_TEAMFIGHT.
6. FFmpeg text: Każdy tekst musi być oczyszczony z Unicode i znaków specjalnych (\', \:, %%).
7. Zero śmiecenia: Telemetria i stan są nadpisywane w miejscu (UPSERT).

## 3. HISTORIA ANALITYCZNA I WNIOSKI
- Wyświetlenia łączne: 99 403 views (YouTube: 85k, TikTok: 9.9k z 5 filmów, IG: 4.3k).
- Format wygrywający: SOLO_BOLO (2 489 views avg, 1.29x mediany kanału).
- Długość: cinematic_18_25s (2 712 views) i balanced_14_17s (2 370 views).
- Tytuły: Styl DISRESPECT_1V1 (+42% views). Słowa CTR: 1V1, BOLO, SOLO, EGO, VANISHED, RUN.
- Retencja YT: Swiped away tylko 14.7% (85.3% ogląda), AVD%: 122.9%.

## 4. JAK TESTOWAĆ
- Testy: `.\venv313\Scripts\pytest tests/ -q`
- Serwer: `.\venv313\Scripts\python.exe -m uvicorn lol_agent.api.main:app --host 127.0.0.1 --port 8765`
- Synchronizacja www: `.\venv313\Scripts\python.exe scripts\sync_website_stats.py`

## 5. PLIKI DO PRZEKAZANIA CLAUDE:
1. `docs/PROJECT_GUIDELINES.md`
2. `lol_agent/lol_editor.py`
3. `lol_agent/smart_camera.py`
4. `lol_agent/lol_montage_director.py`
5. `lol_agent/social_analytics.py`
6. `scripts/sync_website_stats.py`
7. `lol_agent/api/main.py`
8. `accounts/omnichannel_analytics_cache.json`
