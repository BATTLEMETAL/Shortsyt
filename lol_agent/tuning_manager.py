"""
Shortsyt — Centralny Menedżer Profili Stylu i Pacingu
Zarządza 3 profilami montażu:
  1. aggressive: 'Ekstremalnie Szybkie' (natychmiastowy hook 0.8s, short 10-13s, zoom 1.30x, slowmo 0.9s, muzyka 90%)
  2. balanced:   'Zbalansowane' (buildup 1.8s, short 14-17s, zoom 1.20x, slowmo 1.4s, muzyka 85%)
  3. cinematic:  'Cinematic Outplay' (buildup 4.0s, short 20-25s, zoom 1.10x, slowmo 2.2s, muzyka 70%, gra 80%)
"""
import os
import json
from pathlib import Path
from typing import Dict, Any

TUNING_FILE = Path(__file__).parent / "tuning_config.json"

PACING_PRESETS: Dict[str, Dict[str, Any]] = {
    "aggressive": {
        "id": "aggressive",
        "name": "Ekstremalnie Szybkie 🔥",
        "buildup_sec": 0.8,         # 0.8s przed pierwszym killem (wejście w akcję z impetem!)
        "outro_sec": 1.5,           # 1.5s po kulminacji / ostatnim killu
        "target_min_dur": 10.0,     # minimalna długość shorta
        "target_max_dur": 13.0,     # maksymalna długość shorta (krótki, wysoka retencja 10-13s)
        "zoom_aggression": 1.30,    # mocny zoom-punch przy eliminacjach
        "slowmo_duration": 0.9,     # krótkie, dynamiczne zwolnienie na decydujący cios
        "music_balance": 0.90,      # głośna muzyka Phonk / NCS
        "game_sound_balance": 0.50, # dźwięki gry w tle
        "title_tone": "hype",
    },
    "balanced": {
        "id": "balanced",
        "name": "Zbalansowane (Dwannellenga v25) ✅",
        "buildup_sec": 1.8,
        "outro_sec": 2.2,
        "target_min_dur": 14.0,
        "target_max_dur": 17.0,
        "zoom_aggression": 1.20,
        "slowmo_duration": 1.4,
        "music_balance": 0.85,
        "game_sound_balance": 0.65,
        "title_tone": "narrative",
    },
    "cinematic": {
        "id": "cinematic",
        "name": "Cinematic Outplay 🎬",
        "buildup_sec": 4.0,
        "outro_sec": 3.5,
        "target_min_dur": 20.0,
        "target_max_dur": 25.0,
        "zoom_aggression": 1.10,
        "slowmo_duration": 2.2,
        "music_balance": 0.70,
        "game_sound_balance": 0.80,
        "title_tone": "narrative",
    },
}


def load_tuning_config() -> Dict[str, Any]:
    """Wczytuje surowy plik tuning_config.json lub zwraca domyślny profil."""
    if TUNING_FILE.exists():
        try:
            with open(TUNING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Błąd odczytu {TUNING_FILE}: {e}")
            
    return {
        "pacing": "aggressive",
        "zoomAggression": 1.30,
        "slowmoDuration": 0.9,
        "musicBalance": 0.90,
        "gameSoundBalance": 0.50,
        "titleTone": "hype",
        "userNotes": "Ekstremalnie Szybkie: natychmiastowe wejście w akcję (0.5s przed walką), mocny zoom-punch 1.30x przy każdym killu, głośna muzyka Phonk/NCS i agresywne tytuły pod CTR (INSANE / UNSTOPPABLE 🔥)."
    }


def save_tuning_config_to_file(config: Dict[str, Any]) -> bool:
    """Zapisuje profil do pliku tuning_config.json."""
    try:
        with open(TUNING_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Błąd zapisu {TUNING_FILE}: {e}")
        return False


def get_pacing_parameters() -> Dict[str, Any]:
    """
    Zwraca aktywne parametry pacingu z uwzględnieniem wybranego presetu
    oraz ewentualnych ręcznych dostrojeń użytkownika (suwaki).
    """
    cfg = load_tuning_config()
    pacing_id = cfg.get("pacing", "aggressive")
    base = PACING_PRESETS.get(pacing_id, PACING_PRESETS["aggressive"]).copy()

    if "zoomAggression" in cfg:
        base["zoom_aggression"] = float(cfg["zoomAggression"])
    if "slowmoDuration" in cfg:
        base["slowmo_duration"] = float(cfg["slowmoDuration"])
    if "musicBalance" in cfg:
        base["music_balance"] = float(cfg["musicBalance"])
    if "gameSoundBalance" in cfg:
        base["game_sound_balance"] = float(cfg["gameSoundBalance"])
    if "titleTone" in cfg:
        base["title_tone"] = str(cfg["titleTone"])
    if "userNotes" in cfg:
        base["user_notes"] = str(cfg["userNotes"])

    return base
