# GIT STATUS — Shortsyt / LOL Agent
> Ostatnia aktualizacja: 2026-08-23
> Repo: https://github.com/BATTLEMETAL/Shortsyt
> Branch: main | Ostatni commit: `7d25f89` (CI fix, Python 3.12)

---

## ✅ CO JEST NA GITHUBIE (wrzucone wcześniej)

### Core pipeline (zmodyfikowane lokalnie, NIEZSYNCHRONIZOWANE):
- `lol_agent/lol_clip_analyzer.py` — OCR + Gemini Vision champion detect
- `lol_agent/lol_config.py` — CHAMPION_WHITELIST, parametry
- `lol_agent/lol_editor.py` — FFmpeg pipeline, Auto Chase Speedup 2.8x, MERGE_GAP
- `lol_agent/lol_metadata_generator.py` — hashtagi, tytuł, opis
- `lol_agent/lol_publisher.py` — YouTube OAuth + upload
- `lol_agent/run_lol_agent.py` — main CLI: --start/--end/--no-slowmo/--music (NOWE flagi niewrzucone!)
- `.env.example` — template kluczy API
- `authorize_channel.py`, `prettywoman_agent.py`, `prettywoman_processor.py`, `pw_upload_single.py`

> ⚠️ Te pliki są ZMODYFIKOWANE lokalnie ale NIE wrzucone na GitHub.
> Zawierają dziesiątki godzin pracy z sesji 9–19.

---

## ❌ CO NIE JEST NA GITHUBIE (nigdy nie wrzucone — UNTRACKED)

### Kluczowe pliki produkcyjne:
| Plik | Co robi | Priorytet wrzucenia |
|---|---|---|
| `lol_agent/smart_camera.py` | **Computer Vision v11** — player_gold/ally_green tracking, MAX_DELTA, FREEZE_STREAK | 🔴 KRYTYCZNY |
| `lol_agent/lol_smart_titles.py` | AI tytuły z few-shot bazy kanału | 🔴 KRYTYCZNY |
| `lol_agent/lol_title_database.py` | Baza autentycznych tytułów Dwannellenga | 🔴 KRYTYCZNY |
| `lol_agent/lol_thumbnail.py` | Generator miniaturek 9:16 (FFMPEG auto-detect) | 🔴 KRYTYCZNY |
| `lol_agent/lol_momentum_analyzer.py` | OCR kill timing, peak detection, Auto Chase | 🔴 KRYTYCZNY |
| `lol_agent/lol_clip_ranker.py` | Ranking klipów Outplayed przed pipeline | 🟡 WAŻNY |
| `lol_agent/lol_pre_pipeline_analyzer.py` | Skan folderów + OCR scoring + CLI top N | 🟡 WAŻNY |
| `lol_agent/lol_performance_tracker.py` | 48h check views/CTR z YT API | 🟡 WAŻNY |
| `lol_agent/lol_quality_scorer.py` | QA score 0–100 po renderze | 🟡 WAŻNY |
| `lol_agent/qa_after_render.py` | QA skrypt: OCR kill + velocity + cisza | 🟡 WAŻNY |
| `lol_agent/api/` | **FastAPI backend** (15 endpointów, JWT, YT OAuth, /thumbnails, /camera-preview) | 🔴 KRYTYCZNY |
| `shortsyt-desktop/` | **Electron Desktop Studio** (React 18, Vite, TailwindCSS) | 🟡 WAŻNY |
| `shortsyt-app/` | React Native Expo app (Android) | 🟠 NISKI PRIORYTET |
| `lol_agent/lol_music/` | Muzyka NCS (sprawdź licencje!) | ⚠️ OSTROŻNIE (copyright) |
| `lol_agent/CONTEXT.md` | Master dokumentacja projektu | 🟡 WAŻNY (bez tokenów) |

### Pliki których NIE wrzucamy (dane prywatne / binaria):
```
accounts/lol_token.pickle     ← TOKEN YOUTUBE — nigdy nie wrzucać!
.env                          ← GEMINI_API_KEY — nigdy!
lol_agent/lol_temp/           ← surowe wideo — .gitignore
lol_agent/processed_hashes.json ← dane operacyjne, nie kod
lol_agent/yt_perf_cache.json  ← cache YT, nie kod
lol_agent/published_videos.jsonl ← logi prywatne
scratch/                      ← tymczasowe
debug_frames/, debug_jinx/    ← tymczasowe
*.jpg, *.mp4 (surowe/temp)    ← binaria
```

---

## 🔧 CO TRZEBA NAPRAWIĆ PRZED WRZUCENIEM

1. **`.gitignore` — sprawdź czy blokuje:**
   ```
   accounts/
   .env
   lol_agent/lol_temp/
   lol_agent/processed_hashes.json
   lol_agent/published_videos.jsonl
   lol_agent/yt_perf_cache.json
   lol_agent/pending_checks.json
   lol_agent/performance_log.jsonl
   lol_agent/quality_log.jsonl
   lol_agent/last_dry_run.json
   lol_agent/beat_drop_cache.json
   scratch/
   lol_agent/debug_*/
   *.mp4
   *.jpg (z wyjątkiem README assets)
   lol_agent/lol_music/*.mp3  ← copyright NCS
   ```

2. **README.md — wymaga aktualizacji:**
   - Dodać sekcję "Smart Camera v11" z wynikami (90/90 klatek)
   - Dodać CLI przykłady z nowymi flagami (--music, --no-slowmo, --start, --end)
   - Dodać screenshot Desktop Studio + miniaturkę 9:16
   - Dodać linki do 3 opublikowanych Shortsów jako portfolio

3. **`lol_agent/lol_music/`** — NCS muzyka ma licencje "free for YouTube" ale może być problematyczna w publicznym repo. Alternatywa: wrzucić tylko `music_attributions.json` bez plików MP3, z instrukcją jak pobrać.

---

## 📋 KOLEJNOŚĆ COMMITÓW (plan)

```
COMMIT 1 — "core: smart camera v11 + momentum analyzer + titles engine"
  git add lol_agent/smart_camera.py
  git add lol_agent/lol_momentum_analyzer.py
  git add lol_agent/lol_smart_titles.py
  git add lol_agent/lol_title_database.py
  git add lol_agent/lol_thumbnail.py
  git add lol_agent/lol_quality_scorer.py
  git add lol_agent/qa_after_render.py

COMMIT 2 — "feat: CLI --music --no-slowmo --start --end flags + performance tracker"
  git add lol_agent/run_lol_agent.py
  git add lol_agent/lol_editor.py
  git add lol_agent/lol_clip_analyzer.py
  git add lol_agent/lol_config.py
  git add lol_agent/lol_metadata_generator.py
  git add lol_agent/lol_publisher.py
  git add lol_agent/lol_performance_tracker.py
  git add lol_agent/lol_pre_pipeline_analyzer.py
  git add lol_agent/lol_clip_ranker.py

COMMIT 3 — "feat: FastAPI backend v2 + JWT + YT OAuth + thumbnails + camera-preview"
  git add lol_agent/api/

COMMIT 4 — "feat: Electron Desktop Studio (React 18 + Vite + TailwindCSS)"
  git add shortsyt-desktop/

COMMIT 5 — "docs: update README + CONTEXT.md"
  git add README.md lol_agent/CONTEXT.md START_HERE.md
```

---

## 📊 REALNE DANE PROJEKTU (do README)

| Metryka | Wartość |
|---|---|
| Opublikowane Shortsy | 3 ([Pentakill](https://www.youtube.com/shorts/cVTTQASHe9w), [Pentakill 2](https://www.youtube.com/shorts/UZOmupNxfrU), [Triple Kill](https://www.youtube.com/shorts/rfWXE2-7fkQ)) |
| Smart Camera detekcja | 88–90/90 klatek (97–100%) |
| Quality Score | 91–92/100 |
| Czas pipeline → YT | ~5 minut |
| Koszt renderowania | ~0 zł (lokalny PC) |
| Stack | Python 3.13, OpenCV, Tesseract, FFmpeg, FastAPI, Electron 32, React 18 |
