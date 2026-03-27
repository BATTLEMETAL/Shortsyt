# Shortsyt - Autonomous AI YouTube Shorts Factory

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](.)
[![Status](https://img.shields.io/badge/Status-Production-green)](.)

Autonomous pipeline that researches trends, generates scripts, renders videos, and publishes YouTube Shorts automatically. Zero human intervention required.

---

## Pipeline

```
Trend Analysis (YouTube API)
        |
Script Generation (Local LLM / GPT)
        |
Audio Synthesis (TTS Engine)
        |
Video Rendering (FFmpeg + Effects)
        |
Auto-Upload (YouTube Data API v3)
        |
Performance Analytics Loop
  (auto-adapts strategy based on metrics)
```

## Tech Stack

| Component | Technology |
|---|---|
| Script Generation | Local LLM (Qwen) / OpenAI API |
| Audio | TTS (ElevenLabs / Edge-TTS) |
| Video | FFmpeg + custom effects |
| Upload | YouTube Data API v3 |
| Scheduling | Python scheduler / cron |
| Analytics | Custom performance tracker |

## Quick Start

```bash
git clone https://github.com/BATTLEMETAL/Shortsyt.git
cd Shortsyt
pip install -r requirements.txt
# Configure credentials in config.yaml
python pipeline.py
```

## Results

- Pipeline runs 24/7 without supervision
- - Automatic strategy adaptation based on view metrics
  - - Generates ~1 Short per day
   
    - ## Roadmap
   
    - - [x] Autonomous script generation
      - [ ] - [x] TTS + FFmpeg rendering pipeline
      - [ ] - [x] Auto-upload to YouTube
      - [ ] - [x] Performance analytics loop
      - [ ] - [ ] A/B testing for thumbnails
      - [ ] - [ ] Multi-channel support
      - [ ] 
