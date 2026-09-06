"""
Shortsyt — User Learning & Preference Memory (Pętla Uczenia z Korekt Użytkownika)
================================================================================
Zapisuje i analizuje wszelkie korekty dokonywane przez użytkownika (suwaki, odrzucenia klipów,
zmiany tytułów, preferencje audio), aby system uczył się jego stylu montażu i automatycznie
stosował optymalne parametry bez potrzeby ręcznego poprawiania każdego skryptu.

Plik pamięci: lol_agent/user_feedback_history.json
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

MEMORY_FILE = Path(__file__).parent / "user_feedback_history.json"


def _load_memory() -> Dict[str, Any]:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[UserLearning] Błąd odczytu {MEMORY_FILE}: {e}")

    return {
        "version": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_corrections": 0,
        "total_renders_accepted": 0,
        "total_renders_rejected": 0,
        "learned_preferences": {
            "music_balance": 0.60,
            "game_sound_balance": 0.85,
            "min_lead_in_sec": 4.5,
            "max_outro_sec": 1.8,
            "preferred_pacing": "aggressive",
            "smooth_win": 5,
            "end_freeze_sec": 0.6,
        },
        "history": [],
    }


def _save_memory(mem: Dict[str, Any]) -> bool:
    try:
        mem["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[UserLearning] Błąd zapisu {MEMORY_FILE}: {e}")
        return False


def record_user_correction(param_name: str, old_val: Any, new_val: Any, source: str = "ui_manual", reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Rejestruje korektę parametru wykonaną przez użytkownika (np. suwak głośności muzyki, zmiana presetu).
    Aktualizuje wyuczone preferencje.
    """
    mem = _load_memory()
    mem["total_corrections"] += 1

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "parameter_correction",
        "source": source,
        "param": param_name,
        "old_value": old_val,
        "new_value": new_val,
        "reason": reason or "",
    }
    mem["history"].append(entry)
    # Trzymaj ostatnie 100 wpisów
    if len(mem["history"]) > 100:
        mem["history"] = mem["history"][-100:]

    # Adaptacja wyuczonych parametrów
    learned = mem.setdefault("learned_preferences", {})
    if param_name in ("musicBalance", "music_balance"):
        try:
            learned["music_balance"] = round(float(new_val), 2)
        except Exception:
            pass
    elif param_name in ("gameSoundBalance", "game_sound_balance"):
        try:
            learned["game_sound_balance"] = round(float(new_val), 2)
        except Exception:
            pass
    elif param_name in ("pacing", "pacing_mode"):
        learned["preferred_pacing"] = str(new_val)
    elif param_name in ("buildup_sec", "lead_in"):
        try:
            learned["min_lead_in_sec"] = max(3.5, round(float(new_val), 1))
        except Exception:
            pass

    _save_memory(mem)
    print(f"[UserLearning] 🧠 Zapisano korektę użytkownika: {param_name}: {old_val} -> {new_val}")
    return learned


def record_render_accepted(filename: str, action_type: str, duration: float, qa_score: int) -> None:
    """Zapisuje pozytywne zatwierdzenie renderu (użytkownik zaakceptował lub opublikował film)."""
    mem = _load_memory()
    mem["total_renders_accepted"] += 1
    mem["history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "render_approved",
        "filename": filename,
        "action_type": action_type,
        "duration": duration,
        "qa_score": qa_score,
    })
    _save_memory(mem)
    print(f"[UserLearning] ✅ Render zaakceptowany: {filename} ({action_type}, QA {qa_score}/100)")


def record_render_rejected(filename: str, reason: Optional[str] = None, qa_details: Optional[List[str]] = None) -> None:
    """Zapisuje odrzucenie lub usunięcie renderu przez użytkownika (sygnał negatywny do analizy błędu)."""
    mem = _load_memory()
    mem["total_renders_rejected"] += 1
    mem["history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "render_rejected",
        "filename": filename,
        "reason": reason or "Usunięty przez użytkownika w monitorze",
        "qa_details": qa_details or [],
    })
    _save_memory(mem)
    print(f"[UserLearning] ❌ Render odrzucony: {filename}. Powód: {reason or 'Usunięty przez użytkownika'}")


def get_learned_preferences() -> Dict[str, Any]:
    """Zwraca aktualnie wyuczone preferencje użytkownika do użycia przy następnym renderze."""
    mem = _load_memory()
    return mem.get("learned_preferences", {
        "music_balance": 0.60,
        "game_sound_balance": 0.85,
        "min_lead_in_sec": 4.5,
        "max_outro_sec": 1.8,
        "preferred_pacing": "aggressive",
        "smooth_win": 5,
        "end_freeze_sec": 0.6,
    })
