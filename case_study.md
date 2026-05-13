# 🧠 Shortsyt: Autonomous AI Content Pipeline — Case Study

## 📊 Production Metrics (Verified)

| Metric | Value |
|--------|-------|
| **Pipeline live since** | March 3, 2026 |
| **Days in production** | 73+ (March → May 2026) |
| **Videos published (confirmed)** | 95+ public uploads |
| **Publishing cadence** | 2 videos/day, fully autonomous |
| **Human interventions** | 0 (pipeline runs via Windows Task Scheduler) |
| **Cost per video** | $0 (100% local LLM — Qwen 2.5 7B NF4) |
| **Avg video duration** | 20–45s (optimized for Shorts retention loop) |
| **Channel** | [Dark Mindset](https://youtube.com/channel/UCp6u29DiETQta-9WoUmPjJw) |
| **Analytics data** | 29 days of channel-level smart_analysis JSON |
| **Trained models** | `video_success_model.pkl` (376KB sklearn), `model_stylu.pkl` (162KB) |

---

## 📝 Overview

**Shortsyt** is a fully autonomous, production-ready AI pipeline that generates, narrates, edits, and publishes YouTube Shorts. Built around the "Cash Cow" concept, it currently specializes in the **Dark Psychology** niche.

What sets this project apart is its **Phase 4: Real-Time Engagement Feedback Loop** — an autonomous system that doesn't just create content, but actively monitors initial YouTube performance and dynamically mutates its own prompts to avoid algorithmic decay.

---

## 🏗️ Core Architecture

### 1. Script Generation (`agent_dark_psychology.py` & `synapsa_bridge.py`)
- Instructs the LLM (Synapsa / Qwen 2.5 7B) to generate highly engaging 40–70 word scripts using the **Hook-Trick-Warning** framework.
- Enforces storytelling loops (last sentence connects to first) and compels comments as CTA.
- Maintains a deduplication memory (`topic_history.json`) to prevent identical concepts from recurring across 50+ videos.

### 2. Audio Validation & TTS
- Strips unwanted tags from LLM output and generates hyper-realistic TTS audio via `edge-tts`.
- Calculates precise audio length (optimizing for 20–45s retention sweet spot).
- Applies `FFmpeg silenceremove` to cut dead air, ensuring perfect endless loop on the YouTube Shorts player.

### 3. Visuals & Pacing (`cashcow_generator.py`)
- Automatically fetches relevant royalty-free background videos.
- Passes audio through **AI Whisper model** to generate precise `.vtt`/`.ass` subtitles.
- Injects Hormozi-style **Pop-Zoom animations** word-by-word.
- Uses semantic styling: core emotional keywords (FEAR, TRAP, EXPOSED) in red; loop-closing sentences in yellow.
- Merges 18% volume atmospheric dark music track beneath narration.

### 4. Diagnostic Pre-Flight (`analyze_video_features.py`)
- Before publishing, an internal auditor intercepts the `.mp4`.
- Validates: resolution (requires 9:16 vertical), duration, audio levels.
- Parses subtitle metadata (`.ass`) at `0:00:03.00` mark to calculate **Hook Density**.
  - If opening > 12 words in 3 seconds → upload halted (high "Swipe Away" risk).

### 5. Deployment (`upload_youtube.py`)
- Authenticates via OAuth2, uploads via official YouTube Data API v3.
- Generates SEO block with niche-specific tags.
- Logs official `video_id` into `publish_report.json`.

---

## 🚀 The "Secret Sauce": Real-Time Feedback Loop (Phase 4)

Standard AI generators suffer from "Mode Collapse" — they find one viral format and repeat it until the audience is bored. Shortsyt solves this through the **MicroEVS (Early Velocity Score)** architecture.

### How It Works

1. **Live Scraping (`real_time_monitor_agent.py`)**
   When generating the day's 2nd video, the system pauses and connects to the **YouTube Analytics API**. It fetches exact performance metrics (Views, Avg View Duration, Engagement) of the *previous* video published hours earlier.

2. **MicroEVS Calculation**
   ```
   MicroEVS = VPM_60 × (Viewed_Percentage / Swiped_Percentage) × Engagement_Factor
   ```

3. **Dynamic Prompt Injection (`dynamic_pattern_agent.py`)**
   Based on MicroEVS score, the agent selects an adaptation state:
   - 🟢 **State S (Hyper-Clone) [>150%]:** Viral hit. Forces the AI to clone exact grammatical syntax of the hook, only changing the subject.
   - 🟡 **State A (Soft-Mutate) [105%–150%]:** Good traction. Keeps core topic but changes Hook type (e.g., Question → Shocking Statement).
   - 🟠 **State B (Explore) [<105%]:** Stagnation. Ditches current hook; explores a previously successful style.
   - 🔴 **State F (Hard Pivot) [<80%]:** Total algorithmic rejection. Topic banned to `quarantine.json` (14-day timeout). Forces completely new educational tone and sub-4-word hook.

4. **Anti-Fatigue Decay Logic**
   If "State S" triggers 3× consecutively → forced Hard Pivot to discover new narrative patterns.

---

## 🔑 Key Engineering Decisions

| Decision | Rationale |
|----------|-----------|
| **Local LLM (Qwen 2.5 7B NF4)** | $0 cost per video vs. ~$0.01–$0.05 per OpenAI call at scale |
| **NF4 quantization** | 62% VRAM reduction (14.2 GB → 4.5 GB), fits RTX 3060 12GB |
| **Cross-venv IPC via subprocess** | Shortsyt runs lightweight; Synapsa (PyTorch/transformers) loaded only when needed |
| **VRAM guard (nvidia-smi check)** | Pipeline never crashes GPU-heavy games; falls back to 30 curated scripts |
| **Windows Task Scheduler** | Zero-dependency scheduling; no Docker needed on dev machine |

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Qwen 2.5 7B Instruct (NF4 quantized, local) |
| TTS | edge-tts (Microsoft Neural voices) |
| STT/Subtitles | OpenAI Whisper (local) |
| Video | MoviePy + FFmpeg |
| Analytics | google-api-python-client (YouTube Data API v3 + Analytics v2) |
| ML | scikit-learn (trained view-count predictor) |
| Automation | Python + Windows Task Scheduler |

---

## 📂 Project Scale

```
shortsyt/
├── agent_dark_psychology.py     1,121 lines — main pipeline orchestrator
├── quality_auditor.py             718 lines — 8-dim NLP quality engine
├── synapsa_bridge.py              493 lines — IPC bridge to Qwen 2.5
├── cashcow_generator.py         1,100 lines — video render engine
├── real_time_monitor_agent.py     248 lines — YouTube Analytics scraper
├── dynamic_pattern_agent.py       213 lines — MicroEVS prompt injector
├── smart_video_analyzer.py       ~29K lines — channel intelligence engine
├── facts_database.py             ~40K lines — curated psychology facts DB
├── accounts/
│   ├── topic_history.json        Deduplication DB (50+ topics)
│   └── smart_analysis_*.json    29 days of channel analytics
├── video_success_model.pkl       Trained sklearn classifier (376KB)
└── publish_report.json           Full history of 95+ published videos
```

Total: **174 files**, **~4,000+ lines** of production Python

---

## 💡 Future Roadmap

- Expand niche from Dark Psychology to "Brainrot" (high-stimulation gaming content)
- Full automation of thumbnail generation using diffusion models based on the initial hook

*(This AI agent is currently active and fully autonomous.)*
