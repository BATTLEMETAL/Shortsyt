"""
LOL Agent — Autonomous Folder Watcher Daemon
Monitoruje w tle folder nagrań Outplayed.
Automatycznie kwalifikuje i montuje tylko akcje S_TIER i A_TIER (score >= 70)
z zerowym narzutem na CPU podczas gry.
"""
import os
import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add paths
_current_dir = os.path.dirname(os.path.abspath(__file__))
_lol_agent_dir = os.path.dirname(_current_dir)
_project_root = os.path.dirname(_lol_agent_dir)
for _p in (_lol_agent_dir, _project_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lol_config import LOL_INPUT_DIR
from autonomous.evaluator import evaluate_clip_quality
from run_lol_agent import run_pipeline, _clip_hash, _is_duplicate_action, _compute_action_fingerprint

HISTORY_FILE = os.path.join(_current_dir, "watcher_history.json")


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] [AUTONOMOUS] {msg}"
    print(entry, flush=True)


def load_history() -> dict:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_history(history: dict):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Błąd zapisu historii: {e}")


def is_file_ready(file_path: str, wait_seconds: int = 4) -> bool:
    """Sprawdza czy Outplayed skończył zapisywać plik MP4 (brak locka i stały rozmiar)."""
    try:
        if not os.path.exists(file_path):
            return False
        
        initial_size = os.path.getsize(file_path)
        if initial_size < 1024 * 1024:  # Mniej niż 1MB
            return False
        
        time.sleep(wait_seconds)
        new_size = os.path.getsize(file_path)
        
        if initial_size == new_size:
            # Próba otwarcia w trybie dopisywania (sprawdza czy inny proces nie trzyma locka)
            with open(file_path, "ab"):
                pass
            return True
        return False
    except Exception:
        return False


def process_new_clip(file_path: str, auto_publish: bool = False):
    """Ocenia i ewentualnie montuje nowo zapisany klip z gry."""
    history = load_history()
    h = _clip_hash(file_path)
    
    if h in history:
        return  # Już oceniony

    log(f"🔍 Wykryto nowe nagranie: {os.path.basename(file_path)}")
    log("   Rozpoczynam ewaluację jakości (OCR + Pacing + Clutch)...")

    # 1. Ewaluacja jakości (0% API calls)
    eval_res = evaluate_clip_quality(file_path)
    score = eval_res.get("score", 0)
    tier = eval_res.get("tier", "REJECT")
    worthy = eval_res.get("worthy", False)

    log(f"   📊 Wynik: {score:.1f}/100 | TIER: {tier} | Kills: {eval_res.get('highest_kill', 'NONE')} ({eval_res.get('kills_count', 0)})")

    history_entry = {
        "timestamp": datetime.now().isoformat(),
        "file": file_path,
        "score": score,
        "tier": tier,
        "worthy": worthy,
        "highest_kill": eval_res.get("highest_kill", "NONE"),
        "status": "EVALUATED"
    }

    if not worthy:
        log(f"   ❌ ODRZUCONO (Score {score:.1f} < 68.0 progu jakości)")
        history_entry["status"] = "REJECTED_LOW_SCORE"
        history[h] = history_entry
        save_history(history)
        return

    # 2. Sprawdzenie deduplikacji meczu (Semantic Fingerprint)
    action_fp = _compute_action_fingerprint(
        peaks=eval_res.get("kills", []),
        champion="katarina",  # default or auto
        action_type=eval_res.get("highest_kill", "outplay").lower()
    )
    
    processed_path = os.path.join(_lol_agent_dir, "processed_hashes.json")
    processed = {}
    if os.path.exists(processed_path):
        with open(processed_path, encoding="utf-8") as f:
            processed = json.load(f)

    is_dup, dup_info = _is_duplicate_action(action_fp, processed)
    if is_dup:
        log(f"   ⚠️  DUPLIKAT MECZU: Identyczna akcja była już wgrana ({dup_info.get('url', '?')})")
        history_entry["status"] = "DUPLICATE_GAMEPLAY"
        history[h] = history_entry
        save_history(history)
        return

    # 3. Kwalifikacja do montażu!
    log(f"   🔥 AKCJA ZAKWALIFIKOWANA! ({tier} - {score:.1f} pkt) -> Uruchamiam montaż...")
    
    # Uruchomienie z priorytetem BELOW_NORMAL w tle
    dry_run_mode = not auto_publish
    log(f"   🎬 Tryb: {'PUBLIKACJA NA YT' if auto_publish else 'DRY-RUN (gotowy do podglądu)'}")
    
    try:
        run_pipeline(
            video_path=file_path,
            dry_run=dry_run_mode,
            force=False
        )
        history_entry["status"] = "RENDERED_SUCCESS"
        log("   ✅ Montaż zakończony sukcesem!")
    except Exception as e:
        log(f"   ❌ Błąd montażu: {e}")
        history_entry["status"] = f"ERROR: {e}"

def is_game_running() -> bool:
    """Sprawdza czy proces meczu League of Legends jest aktywny (zapobiega spadkom FPS w grze)."""
    try:
        cmd = 'tasklist /FI "IMAGENAME eq League of Legends.exe" /NH'
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
        return "League of Legends.exe" in out
    except Exception:
        return False


def start_watcher(watch_dir: str = None, auto_publish: bool = False, poll_interval: float = 3.0):
    """Główna pętla demona monitorującego nagrania."""
    watch_dir = watch_dir or LOL_INPUT_DIR
    log("="*60)
    log(f"👀 AUTONOMOUS FOLDER WATCHER URUCHOMIONY")
    log(f"📁 Monitorowany folder: {watch_dir}")
    log(f"⚙️  Tryb publikacji: {'AUTOMATYCZNY UPLOAD' if auto_publish else 'DRY-RUN (kolejka do zatwierdzenia)'}")
    log(f"🛡️  Ochrona FPS: ZERO przetwarzania w trakcie aktywnego meczu")
    log("="*60)

    # Indeksowanie początkowe (żeby nie przetwarzać starych plików)
    seen_files = set()
    base_path = Path(watch_dir)
    if base_path.exists():
        for mp4 in base_path.rglob("*.mp4"):
            seen_files.add(str(mp4.resolve()))
    log(f"Indeks startowy: {len(seen_files)} istniejących plików pominięto.\n")

    pending_queue = []
    game_was_running = False

    try:
        while True:
            game_active = is_game_running()

            # 1. Wykryj nowe pliki z Outplayed
            if base_path.exists():
                for mp4 in base_path.rglob("*.mp4"):
                    abs_p = str(mp4.resolve())
                    if abs_p not in seen_files:
                        seen_files.add(abs_p)
                        pending_queue.append(abs_p)
                        log(f"📥 Zarejestrowano nagranie: {mp4.name} (w kolejce: {len(pending_queue)})")

            # 2. Ochrona FPS: W trakcie gry ZERO CPU (nie ruszaj OpenCV / FFmpeg)
            if game_active:
                if not game_was_running:
                    log("🎮 Wykryto aktywny mecz League of Legends — pełna ochrona FPS (0% CPU, kolejkowanie w tle).")
                    game_was_running = True
                time.sleep(poll_interval)
                continue
            else:
                if game_was_running:
                    log("🏁 Mecz zakończony! Rozpoczynam przetwarzanie zebranych nagrań...")
                    game_was_running = False

            # 3. Po meczu — przetwórz kolejkę
            if pending_queue:
                next_clip = pending_queue.pop(0)
                if is_file_ready(next_clip):
                    process_new_clip(next_clip, auto_publish=auto_publish)

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        log("Zatrzymano Watchera.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LOL Agent Autonomous Watcher")
    parser.add_argument("--publish", action="store_true", help="Automatyczny upload na YouTube po kwalifikacji")
    parser.add_argument("--dir", type=str, default=None, help="Ścieżka do folderu nagrań")
    args = parser.parse_args()

    start_watcher(watch_dir=args.dir, auto_publish=args.publish)
