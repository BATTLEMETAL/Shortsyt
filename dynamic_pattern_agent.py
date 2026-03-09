import json
import os
from datetime import datetime, timedelta

QUARANTINE_FILE = "accounts/quarantine.json"
STATE_HISTORY_FILE = "accounts/pattern_state.json"

def load_json(filepath, default_value):
    if not os.path.exists(filepath):
        return default_value
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default_value

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def add_to_quarantine(topic):
    quarantine = load_json(QUARANTINE_FILE, [])
    entry = {
        "topic": topic,
        "banned_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=14)).isoformat()
    }
    quarantine.append(entry)
    save_json(QUARANTINE_FILE, quarantine)

def clean_quarantine():
    quarantine = load_json(QUARANTINE_FILE, [])
    now = datetime.now()
    valid_quarantine = []
    for entry in quarantine:
        expires_at = datetime.fromisoformat(entry["expires_at"])
        if now < expires_at:
            valid_quarantine.append(entry)
    save_json(QUARANTINE_FILE, valid_quarantine)

def get_quarantined_topics():
    clean_quarantine()
    quarantine = load_json(QUARANTINE_FILE, [])
    return [entry["topic"] for entry in quarantine]

def record_state(state_code):
    history = load_json(STATE_HISTORY_FILE, [])
    history.append({
        "state": state_code,
        "timestamp": datetime.now().isoformat()
    })
    # Keep last 50
    history = history[-50:]
    save_json(STATE_HISTORY_FILE, history)

def should_decay():
    """Returns True if Mode Collapse is detected (3 times S state in last 48 hours sequentially)."""
    history = load_json(STATE_HISTORY_FILE, [])
    if len(history) < 3:
        return False
    
    recent_3 = history[-3:]
    now = datetime.now()
    
    for entry in recent_3:
        if entry["state"] != "S":
            return False
        ts = datetime.fromisoformat(entry["timestamp"])
        if now - ts > timedelta(hours=48):
            return False
            
    return True

def get_adaptation_directive(micro_evs_percentage, current_topic, previous_hook="Have you noticed this psychological trick?"):
    """
    Evaluates the MicroEVS percentage (e.g., 160 for 160% of baseline)
    Returns a tuple: (Target State, Prompt Override String)
    """
    
    # 1. Check Decay Logic First
    if should_decay():
        print("☢️  [DYNAMIC PATTERN AGENT] DECAY ACTIVATED: Mode Collapse Warning! Forcing Hard Pivot (State F).")
        state = "F"
    else:
        # 2. Evaluate MicroEVS Metrics
        if micro_evs_percentage > 150:
            state = "S"
        elif 105 <= micro_evs_percentage <= 150:
            state = "A"
        elif 80 <= micro_evs_percentage < 105:
            state = "B"
        else:
            state = "F"

    # Record the decision
    record_state(state)
    
    override_prompt = ""

    if state == "S":
        override_prompt = f"""
URGENT OVERRIDE: Ostatni film odniósł sukces wirusowy. 
Zastosuj DOKŁADNIE tę samą strukturę Hooka: [{previous_hook}]. 
Zastąp temat nowym, zachowując dokładnie ten sam wydźwięk. 
Zachowaj ten sam rytm i liczbę słów (±5 słów). Użyj tego samego schematu Comment Baitingu.
"""
        print(f"🟢 [DYNAMIC PATTERN AGENT] Stan S: HYPER-CLONE. Replikacja wirusowa na nowym temacie.")
        
    elif state == "A":
        override_prompt = """
OVERRIDE: Temat działa, ale potrzebujemy wyższej retencji. 
Zachowaj zaplanowaną kategorię tematyczną, ale użyj INNEGO typu Hooka: zamiast pytania, użyj Szokującego Stwierdzenia. 
Zwiększ tempo skryptu skracając zdania do max 8 słów każde.
"""
        print(f"🟡 [DYNAMIC PATTERN AGENT] Stan A: SOFT-MUTATE. Mutacja krzyżowa (zmiana pacingu/hooka).")
        
    elif state == "B":
        # Placeholder for Hook Library lookup (Phase 3 integration)
        golden_hook_fallback = "Why does your brain force you to follow the crowd?"
        override_prompt = f"""
ADAPTATION: Ostatnie podejście nie zadziałało. Zmień całkowicie wejście. 
Zastosuj historycznie sprawdzony Hook o strukturze: [{golden_hook_fallback}]. 
Stwórz całkowicie nową historię na ten temat.
"""
        print(f"🟠 [DYNAMIC PATTERN AGENT] Stan B: EXPLORE. Wycofanie i użycie Złotego Hooka z Biblioteki.")
        
    elif state == "F":
        add_to_quarantine(current_topic)
        override_prompt = f"""
CRITICAL OVERRIDE - HARD PIVOT: Poprzedni format to całkowita porażka. SUROWE ZASADY: 
1. Absolutny zakaz używania tematyki: [{current_topic}]. 
2. Hook musi być agresywny, zbudowany z maksymalnie 4 słów. 
3. Pacing: długie, opisowe środkowe zdania. 
4. Zmień ton z edukacyjnego na tajemniczy i ostrzegawczy.
"""
        print(f"🔴 [DYNAMIC PATTERN AGENT] Stan F: HARD PIVOT. Kwarantanna schematu i tematu ({current_topic}).")

    return state, override_prompt.strip()

if __name__ == "__main__":
    # Test
    print(get_adaptation_directive(160.0, "The psychology of silent people", "Why are silent people so scary?")[1])
