# 🎮 Shortsyt Studio — Quickstart Guide

## 1. Quick Launch
To start both the FastAPI backend and the Desktop Studio:
```powershell
.\Uruchom_Shortsyt_Studio.bat
```
Or start manually via Python CLI:
```powershell
python lol_agent/run_lol_agent.py --file "path/to/clip.mp4" --champion Katarina --action triple --dry-run
```

## 2. Supported Action Types
- `pentakill` — 5-kill continuous sequence with climax slow-mo
- `quadrakill` — 4-kill momentum sequence
- `triple` — 3-kill outplay
- `double` — 2-kill fast turnaround
- `clutch` — Low HP (<= 20%) survival outplay
- `outplay` — Mechanical solo kill / shutdown

## 3. Configuration
- Copy `.env.example` to `.env` and provide your `GEMINI_API_KEY`.
- Set your clips directory in `lol_agent/lol_config.py` or directly select via the Desktop Studio folder picker.
