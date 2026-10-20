"""
Shortsyt — Rollback to Golden Baseline Script
Uruchom: python rollback_to_baseline.py

Przywraca parametry robocze kanału Dwannellenga (te, które wygenerowały 45.8k wyświetleń)
w przypadku jakiejkolwiek regresji podczas testowania nowych modułów.
"""
import os
import sys
import json
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BASELINE_JSON = ROOT_DIR / "GOLDEN_BASELINE_PARAMS.json"
TUNING_FILE = ROOT_DIR / "lol_agent" / "tuning_config.json"

def rollback():
    print("🔄 [ROLLBACK] Rozpoczynam procedurę przywracania parametrów bazowych...")
    if not BASELINE_JSON.exists():
        print(f"❌ [BŁĄD] Nie znaleziono pliku wzorcowego: {BASELINE_JSON}")
        sys.exit(1)

    with open(BASELINE_JSON, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    # 1. Przywróć tuning_config.json
    active_tuning = baseline.get("active_tuning_config", {})
    with open(TUNING_FILE, "w", encoding="utf-8") as f:
        json.dump(active_tuning, f, indent=2, ensure_ascii=False)
    print(f"✅ Przywrócono: {TUNING_FILE}")

    print("\n📋 [PARAMETRY BAZOWE PRZYWRÓCONE]")
    print(f"   Pacing:             {active_tuning.get('pacing')}")
    print(f"   Zoom Aggression:    {active_tuning.get('zoomAggression')}")
    print(f"   Slowmo Duration:    {active_tuning.get('slowmoDuration')}s")
    print(f"   Music Balance:      {active_tuning.get('musicBalance')}")
    print(f"   Game Sound Balance: {active_tuning.get('gameSoundBalance')}")
    print(f"   Title Tone:         {active_tuning.get('titleTone')}")
    print("\n🚀 System jest w stanie identycznym jak podczas rekordowych 45.8k wyświetleń.")

if __name__ == "__main__":
    rollback()
