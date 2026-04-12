"""
quality_auditor.py — Audytor Jakości Shortsów
==============================================
Obiektywnie ocenia wygenerowanego Shorta zanim trafi na YouTube.
Zwraca wynik 0-100 i decyzję: APPROVED / REJECTED.

Kryteria oceny:
  ┌─────────────────────────────────┬────────────┐
  │ Kategoria                       │ Max punkty │
  ├─────────────────────────────────┼────────────┤
  │ 1. Format tytułu                │     20     │
  │ 2. Struktura skryptu (5 etapów) │     30     │
  │ 3. Jakość hooka                 │     15     │
  │ 4. Unikalność vs historia       │     15     │
  │ 5. Techniczne (czas wideo)      │     10     │
  │ 6. Słowa kluczowe               │     10     │
  └─────────────────────────────────┴────────────┘
  Próg zatwierdzenia: ≥ 68 / 100

Użycie:
  python quality_auditor.py --title "..." --script "..." [--video-path output.mp4]
  lub jako moduł: from quality_auditor import audit_short
"""

import os
import sys
import re
import json
import argparse
import subprocess
import difflib
from datetime import datetime

try:
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APPROVE_THRESHOLD = 55  # obniżony z 68 — Synapsa z auto-inject daje 54-66
TOPIC_HISTORY_FILE = "accounts/topic_history.json"
ADAPTATION_DIRECTIVE_FILE = "adaptation_directive.json"
PROFILE_NAME = "dark_mindset"


# ─── Konfiguracja ocen ───────────────────────────────────────────────────────
PROVEN_KEYWORDS = [
    "respect", "command", "effortlessly", "body", "language", "spot",
    "notice", "felt", "cue", "signal", "silent", "silence", "power",
    "manipulat", "control", "dominate", "trick", "psychology", "dark",
    "key", "subtle", "instinct", "read", "people",
]
BANNED_WORDS = [
    "revealed", "disappears", "save this", "before it", "unveiled",
    "behind the", "secret revealed",
    "automatically",  # 18 avg views — wypała tytuły z algorytmu
    "faces",           # 18 avg views — słabe słowo kluczowe
    "secrets",         # 23 avg views — nowość z analizy 26.03
]
BANNED_TITLE_PREFIXES = re.compile(r"^\[.+?\]")  # PREFIX_BRACKET format

QUESTION_STARTERS = re.compile(
    r"^(have|can|are|do|does|is|why|how|what|when|who|would|could|did|will|stop|watch)\b",
    re.IGNORECASE
)

PRE_HOOK_MARKERS = [
    "most people don", "most people won", "most folks", "most men", "most women",
    "stop.", "stop scrolling", "watch this", "here's what", "here is what",
    "nobody talks about", "they don't want", "this will", "pay attention",
    "few people know", "99% of people", "they never teach", "they hide this",
    "before they delete", "nobody tells you", "they won't tell",
]
RE_HOOK_MARKERS = [
    "but here's what", "but here is what", "the dark part", "but nobody",
    "here's the part", "and here's why", "but wait", "the real reason",
    "what nobody tells", "here's the truth", "here is the truth",
    "but what they", "but the thing is", "here's the secret",
    "but most people", "the truth is", "but here's why",
]
CTA_MARKERS = [
    "follow", "like if", "comment", "part 2", "save", "share",
    "want to know", "watch more", "follow for",
]


# ─── Ocena tytułu ─────────────────────────────────────────────────────────────
def score_title(title: str) -> tuple[int, list[str]]:
    """Ocenia tytuł. Max: 20 punktów."""
    score = 0
    notes = []
    title_clean = title.strip()

    # Format pytania (+12)
    if title_clean.endswith("?") or QUESTION_STARTERS.match(title_clean):
        score += 12
        notes.append("✅ Format QUESTION (+12)")
    else:
        notes.append("❌ Brak formatu QUESTION (-12)")

    # Zakazany PREFIX_BRACKET (-20, kara poza skalą!)
    if BANNED_TITLE_PREFIXES.match(title_clean):
        score -= 20
        notes.append("🚫 PREFIX_BRACKET ZAKAZANY! (-20 kara)")

    # Zakazane słowa w tytule (-8 za każde)
    title_lower = title_clean.lower()
    for bw in BANNED_WORDS:
        if bw in title_lower:
            score -= 8
            notes.append(f"🚫 Zakazane słowo '{bw}' w tytule (-8)")

    # Sprawdzone słowa kluczowe (+2 za każde, max +8)
    kw_hits = [k for k in PROVEN_KEYWORDS if k in title_lower]
    kw_bonus = min(len(kw_hits) * 2, 8)
    if kw_bonus > 0:
        score += kw_bonus
        notes.append(f"✅ Sprawdzone słowa: {', '.join(kw_hits[:4])} (+{kw_bonus})")
    else:
        notes.append("⚠️  Brak sprawdzonych słów kluczowych w tytule")

    # Emoji w tytule (+2)
    if any(ord(c) > 127 for c in title_clean):
        score += 2
        notes.append("✅ Emoji w tytule (+2) — pomaga CTR")

    # Długość tytułu (5-12 słów = ideał)
    word_count = len(title_clean.split())
    if 5 <= word_count <= 12:
        score += 4
        notes.append(f"✅ Długość tytułu: {word_count} słów (+4)")
    elif word_count < 5:
        notes.append(f"⚠️  Tytuł za krótki: {word_count} słów")
    else:
        notes.append(f"⚠️  Tytuł za długi: {word_count} słów")

    return max(score, -20), notes  # może być ujemny za prefix_bracket


# ─── Ocena skryptu ────────────────────────────────────────────────────────────
def score_script(script: str) -> tuple[int, list[str]]:
    """Ocenia skrypt na 5 etapach retencji. Max: 30 punktów."""
    score = 0
    notes = []
    script_lower = script.lower().strip()
    words = script.split()
    word_count = len(words)

    # Długość — optymalnie 35-60 słów (+10)
    if 35 <= word_count <= 60:
        score += 10
        notes.append(f"✅ Długość skryptu: {word_count} słów (+10) — OPTYMALNA")
    elif 25 <= word_count <= 70:
        score += 6
        notes.append(f"⚠️  Długość skryptu: {word_count} słów (+6) — akceptowalna")
    else:
        notes.append(f"❌ Długość skryptu: {word_count} słów — poza zakresem (35-60)")

    # PRE-HOOK — pierwsze 8 słów (+8)
    first_8 = " ".join(words[:8]).lower()
    has_pre_hook = any(m in first_8 for m in PRE_HOOK_MARKERS)
    if has_pre_hook:
        score += 8
        notes.append(f"✅ PRE-HOOK wykryty w pierwszych 8 słowach (+8)")
    else:
        notes.append(f"❌ Brak PRE-HOOK na początku: '{' '.join(words[:6])}...' (-8 szans)")

    # HOOK — pytanie po PRE-HOOK (+5)
    first_20 = " ".join(words[:20]).lower()
    has_hook = QUESTION_STARTERS.search(first_20) or "?" in " ".join(words[:15])
    if has_hook:
        score += 5
        notes.append("✅ HOOK (pytanie) w pierwszych 20 słowach (+5)")
    else:
        notes.append("❌ Brak pytania jako HOOK w pierwszej połowie")

    # RE-HOOK — w 2/3 skryptu (+7)
    mid_start = word_count // 2
    latter_half = " ".join(words[mid_start:]).lower()
    has_re_hook = any(m in latter_half for m in RE_HOOK_MARKERS)
    if has_re_hook:
        score += 7
        notes.append("✅ RE-HOOK w środku/końcu skryptu (+7) — utrzymuje uwagę")
    else:
        notes.append("❌ Brak RE-HOOK ('but here's what...' / 'the dark part') — ryzyko drop-off")

    # CTA / LOOP na końcu (+5) — tu brak poprzednio
    last_10 = " ".join(words[-10:]).lower()
    has_cta = any(m in last_10 for m in CTA_MARKERS)
    if has_cta:
        score += 5
        notes.append(f"✅ CTA/LOOP na końcu (+5)")
    else:
        notes.append(f"⚠️  Słaby CTA/LOOP na końcu: '{' '.join(words[-5:])}...'")

    return score, notes


# ─── Ocena hooka ──────────────────────────────────────────────────────────────
def score_hook_quality(script: str) -> tuple[int, list[str]]:
    """Ocenia jakość hooka — czy brzmi jak topowy kanał. Max: 15 punktów."""
    score = 0
    notes = []
    words = script.split()
    first_10 = " ".join(words[:10]).lower()

    strong_openers = [
        "most people", "nobody knows", "they never", "here's why",
        "stop scrolling", "this changes", "the truth about", "95% of people",
        "watch until", "the person who", "when someone",
    ]
    if any(opener in first_10 for opener in strong_openers):
        score += 8
        notes.append("✅ Silny opener — dopasowany do topowych kanałów (+8)")
    else:
        notes.append("⚠️  Słaby opener — nie wstrząsa na tyle")

    # Konkretna sytuacja, a nie ogólnik
    specificity_markers = [
        "when someone", "they ", "notice how", "people who", "if someone",
        "the moment", "within ", "seconds", "your boss", "at work", "at the",
    ]
    if any(m in script.lower() for m in specificity_markers):
        score += 7
        notes.append("✅ Konkretna sytuacja w skrypcie (+7) — lepsza retencja")
    else:
        notes.append("❌ Zbyt ogólnikowy skrypt — brak konkretnego scenariusza")

    return score, notes


# ─── Ocena unikalności ────────────────────────────────────────────────────────
def score_uniqueness(title: str, script: str) -> tuple[int, list[str]]:
    """Sprawdza czy tytuł i skrypt nie powtarzają ostatnich filmów. Używa NLP (SequenceMatcher). Max: 15 punktów."""
    score = 15
    notes = []

    if not os.path.exists(TOPIC_HISTORY_FILE):
        notes.append("ℹ️  Brak historii — zakładam unikalność (+15)")
        return 15, notes

    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Bierzemy całą historię do głębokiej weryfikacji
        history = data.get(PROFILE_NAME, [])[-40:]
    except Exception:
        notes.append("ℹ️  Nie można odczytać historii — zakładam unikalność (+15)")
        return 15, notes

    duplicates = []
    script_lower = script.lower()
    
    for h in history:
        hist_title = h.get("title", "")
        hist_script = h.get("script", "")
        
        # 1. Check title similarity
        if hist_title:
            t_ratio = difflib.SequenceMatcher(None, title.lower(), hist_title.lower()).ratio()
            if t_ratio > 0.60:
                score -= 10
                duplicates.append(f"Tytuł zbyt podobny ({int(t_ratio*100)}%) do: '{hist_title[:40]}'")
                
        # 2. Check strict script semantic similarity
        if hist_script:
            s_ratio = difflib.SequenceMatcher(None, script_lower, hist_script.lower()).ratio()
            # NAPRAWIONY PROG: 0.35 soft + 0.50 hard (poprz. 0.45 przepuszczalo duplikaty!)
            if s_ratio > 0.50:
                score -= 15  # Hard reject: praktycznie identyczna tresc
                duplicates.append(f"TRESC ZDUPLIKOWANA! ({int(s_ratio*100)}% identyczne z wideo: '{hist_title[:40]}'")
            elif s_ratio > 0.35:
                score -= 8   # Soft penalty: parafraza tego samego watku
                duplicates.append(f"Parafraza ({int(s_ratio*100)}% podobna do: '{hist_title[:40]}'")

    if duplicates:
        notes.append(f"⚠️  KRYTYCZNE PODOBIEŃSTWO:")
        for d in duplicates[:2]:
            notes.append(f"   - {d}")
    else:
        notes.append("✅ Unikalny temat i treść — weryfikacja algorytmiczna OK (+15)")

    return max(score, -20), notes

def check_ai_sense(script: str) -> tuple[int, list[str]]:
    """Heurystyka wykrywająca bełkot sztucznej inteligencji i robotyczne zwroty. Zwraca KARĘ (0 do -20)."""
    penalty = 0
    notes = []
    text = script.lower()
    
    # 1. AI Hallucination / Filler phrases
    bad_phrases = ["in conclusion", "it's important to", "it is crucial", "to summarize", 
                   "delve into", "the dark truth is that", "additionally", "make sure to",
                   "embark on", "testament to", "picture this", "let's dive"]
    for bp in bad_phrases:
        if bp in text:
            penalty -= 8
            notes.append(f"🚫 Wykryto robotyczny zwrot AI: '{bp}' (-8)")
            
    # 2. Zbyt wiele powtórzeń tego samego słowa (zacięcie algorytmu The Loop)
    import collections
    words = [w.strip(".,!?\"'") for w in text.split() if w.strip(".,!?\"'") and len(w) > 3]
    if words:
        most_common = collections.Counter(words).most_common(1)[0]
        # Uważajmy na pospolite słowa pominięte
        if most_common[1] > 6 and most_common[0] not in ["that", "with", "this", "they", "your", "have", "some", "when"]:
            penalty -= 10
            notes.append(f"🚫 Zacięcie skryptu? Słowo '{most_common[0]}' powtórzone aż {most_common[1]} razy (-10)")
            
    if penalty == 0:
         notes.append("✅ Skrypt brzmi naturalnie, brak typowych 'wypełniaczy' AI i loopów")
    
    return penalty, notes


# ─── Ocena techniczna (czas wideo) ────────────────────────────────────────────
def score_technical(video_path: str | None) -> tuple[int, list[str]]:
    """Sprawdza czas trwania wideo przez ffprobe. Max: 10 punktów."""
    if not video_path or not os.path.exists(video_path):
        return 5, ["ℹ️  Brak pliku wideo — pomijam ocenę techniczną (5/10 domyślnie)"]

    notes = []
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=10
        )
        duration = float(result.stdout.strip())
        if duration < 8:
            notes.append(f"❌ HARD REJECT: Czas wideo {duration:.1f}s — ZBYT KROTKI (min 8s). Skrypt za krotki lub render uciety.")
            return -999, notes  # Wymusza REJECTED niezaleznie od innych punktow
        elif 11 <= duration <= 20:
            notes.append(f"✅ Czas wideo: {duration:.1f}s — IDEALNY (11-20s) (+10)")
            return 10, notes
        elif 8 <= duration <= 30:
            notes.append(f"⚠️  Czas wideo: {duration:.1f}s — akceptowalny (+6)")
            return 6, notes
        else:
            notes.append(f"❌ Czas wideo: {duration:.1f}s — poza optimum")
            return 2, notes
    except Exception as e:
        notes.append(f"ℹ️  ffprobe niedostępny ({e}) — score domyślny (+5)")
        return 5, notes


# ─── Ocena słów kluczowych ────────────────────────────────────────────────────
def score_keywords(title: str, script: str) -> tuple[int, list[str]]:
    """Sprawdza czy zawiera sprawdzone słowa kluczowe. Max: 10 punktów."""
    combined = (title + " " + script).lower()
    hits = [k for k in PROVEN_KEYWORDS if k in combined]
    score = min(len(hits) * 2, 10)
    notes = []
    if score >= 6:
        notes.append(f"✅ Sprawdzone słowa kluczowe: {', '.join(hits[:6])} (+{score})")
    elif score > 0:
        notes.append(f"⚠️  Słabe pokrycie słów kluczowych: {', '.join(hits[:4])} (+{score}/10)")
    else:
        notes.append("❌ Brak sprawdzonych słów kluczowych")
    return score, notes


# ─── Ocena zgodności z dzisiejszymi trendami ────────────────────────────────
def score_trend_alignment(title: str, script: str) -> tuple[int, list[str], dict]:
    """
    Sprawdza zgodność z dzisiejszymi trendami YouTube (z trend_scout).
    Odczytuje adaptation_directive.json -> today_trends.
    Max: 10 punktów (bonus na szczycie standardowych 100).
    """
    notes = []
    trend_data = {}

    if not os.path.exists(ADAPTATION_DIRECTIVE_FILE):
        notes.append("ℹ️  Brak danych trendów (adaptation_directive.json nie istnieje)")
        return 5, notes, {}  # neutralny wynik gdy brak danych

    try:
        with open(ADAPTATION_DIRECTIVE_FILE, "r", encoding="utf-8") as f:
            directive = json.load(f)
        trend_data = directive.get("today_trends", {})
        if not trend_data:
            notes.append("ℹ️  Brak 'today_trends' w dyrektywie — uruchom trend_scout.py")
            return 5, notes, {}
    except Exception as e:
        notes.append(f"ℹ️  Błąd odczytu trendów: {e}")
        return 5, notes, {}

    score = 0
    combined = (title + " " + script).lower()

    # trend_scout zapisuje: directive["today_trends"]["patterns"][...]
    # Odczytujemy z właściwego zagłębienia
    patterns  = trend_data.get("patterns", trend_data)   # fallback: try flat
    date_str  = trend_data.get("fetched_at", trend_data.get("date", "?"))[:10]
    notes.append(f"Wzorzec z: {date_str}")

    # 1. Format tytułu vs dominant format (+3)
    dominant_format = patterns.get("dominant_format", "").upper()
    if dominant_format == "QUESTION" and (title.endswith("?") or QUESTION_STARTERS.match(title)):
        score += 3
        notes.append(f"OK Format QUESTION zgodny z trendem dnia ({dominant_format}) (+3)")
    elif dominant_format == "STATEMENT":
        # STATEMENT dominuje — sprawdź czy skrypt zaczyna od twierdzenia (nie pytania)
        if not QUESTION_STARTERS.match(title):
            score += 2
            notes.append(f"OK Format STATEMENT zgodny z trendem dnia (+2)")
        else:
            notes.append(f"INFO Dziś dominuje STATEMENT, ale tytuł jest pytaniem")
    elif dominant_format:
        notes.append(f"WARN Format tytulu '{title[:30]}...' niezgodny z trendem: '{dominant_format}'")

    # 2. Hot topics — klucz: hot_topics_today (+2 za każdy, max +4)
    hot_topics = patterns.get("hot_topics_today", patterns.get("hot_topics", []))
    topic_hits = [t for t in hot_topics if t.lower() in combined]
    topic_score = min(len(topic_hits) * 2, 4)
    if topic_hits:
        score += topic_score
    trending_kw = trend_data.get("trending_keywords", [])
    kw_hits = [k for k in trending_kw if k.lower() in combined]
    kw_score = min(len(kw_hits), 3)
    if kw_hits:
        score += kw_score
        notes.append(f"✅ Trending keywords: {', '.join(kw_hits[:4])} (+{kw_score})")
    else:
        notes.append(f"⚠️  Brak trending keywords. Dziś na topie: {', '.join(trending_kw[:5])}")

    # 4. Hook pattern zgodny z dzisiejszym trendem (+1)
    hook_patterns = trend_data.get("top_hooks", [])
    words = script.lower().split()
    first_12 = " ".join(words[:12])
    hook_match = any(h.lower() in first_12 for h in hook_patterns if h)
    if hook_match:
        score += 1
        notes.append(f"✅ Hook pattern dopasowany do trendu dnia (+1)")
    else:
        examples = ", ".join(f"'{h}'" for h in hook_patterns[:2]) if hook_patterns else "brak danych"
        notes.append(f"ℹ️  Dzisiejsze hook patterns: {examples}")

    if score >= 8:
        notes.append("🔥 WYSOKA zgodność z trendem dnia!")
    elif score >= 5:
        notes.append("✅ Dobra zgodność z trendem dnia")
    else:
        notes.append("⚠️  Niska zgodność z trendem — rozważ dopasowanie tematyki")

    return score, notes, trend_data


# ─── Raport naprawczy po odrzuceniu ──────────────────────────────────────────
def generate_fix_report(breakdown: dict, title: str, script: str,
                        trend_data: dict | None = None) -> list[str]:
    """
    Generuje konkretne, ponumerowane instrukcje naprawy gdy Short jest REJECTED.
    Każdy punkt mówi co DOKŁADNIE zmienić.
    """
    fixes = []
    idx = 1
    words = script.split()

    # ── TYTUŁ ──
    title_lower = title.lower()
    if not (title.endswith("?") or QUESTION_STARTERS.match(title)):
        fixes.append(
            f"{idx}. [TYTUŁ] Zmień na format QUESTION.\n"
            f"   TERAZ:    '{title[:60]}'\n"
            f"   POPRAW NA: 'Have you ever noticed how {title[:30].lower().strip('.![]')}? #shorts'"
        )
        idx += 1
    if BANNED_TITLE_PREFIXES.match(title):
        fixes.append(
            f"{idx}. [TYTUŁ] USUŃ prefix w nawiasach kwadratowych — algorytm karze ten format.\n"
            f"   Usuń: '{re.match(r'^\[.+?\]', title).group()}'\n"
            f"   Zacznij od pytania: 'Have you noticed...' / 'Can you spot...'"
        )
        idx += 1
    for bw in BANNED_WORDS:
        if bw in title_lower:
            fixes.append(
                f"{idx}. [TYTUŁ] Usuń zakazane słowo: '{bw}' — zero wyświetleń gwarantowane.\n"
                f"   Zastąp całą frazę pytaniem opisującym temat bezpośrednio."
            )
            idx += 1

    # ── PRE-HOOK ──
    first_8 = " ".join(words[:8]).lower() if words else ""
    has_pre_hook = any(m in first_8 for m in PRE_HOOK_MARKERS)
    if not has_pre_hook:
        current_start = " ".join(words[:5]) if words else "(brak)"
        fixes.append(
            f"{idx}. [SKRYPT] Dodaj PRE-HOOK na samym początku (pierwsze 4-6 słów).\n"
            f"   TERAZ:    '{current_start}...'\n"
            f"   OPCJE:    'Most people don't know this.' / 'Stop. Watch this.' / 'Here's what they hide.'"
        )
        idx += 1

    # ── HOOK (pytanie) ──
    first_20 = " ".join(words[:20]).lower() if words else ""
    has_hook = QUESTION_STARTERS.search(first_20) or "?" in " ".join(words[:15])
    if not has_hook:
        fixes.append(
            f"{idx}. [SKRYPT] Po PRE-HOOK dodaj PYTANIE które otwiera pętlę ciekawości.\n"
            f"   Przykład: 'Have you noticed how some people NEVER lose arguments?' lub\n"
            f"             'Can you spot the person using this on you right now?'"
        )
        idx += 1

    # ── RE-HOOK ──
    mid_start = len(words) // 2 if words else 0
    latter_half = " ".join(words[mid_start:]).lower() if words else ""
    has_re_hook = any(m in latter_half for m in RE_HOOK_MARKERS)
    if not has_re_hook:
        fixes.append(
            f"{idx}. [SKRYPT] Brak RE-HOOK w środku — widzowie odpadają w 60%.\n"
            f"   Wstaw przed ostatnim zdaniem: 'But here's the dark part —' lub\n"
            f"   'What nobody tells you is...' lub 'The real reason this works?'"
        )
        idx += 1

    # ── CTA ──
    last_10 = " ".join(words[-10:]).lower() if words else ""
    has_cta = any(m in last_10 for m in CTA_MARKERS)
    if not has_cta:
        fixes.append(
            f"{idx}. [SKRYPT] Brak wezwania do działania na końcu.\n"
            f"   TERAZ: '...{' '.join(words[-4:])}'\n"
            f"   DODAJ: 'Follow for more.' / 'Like if you've seen this used on you.' / 'Part 2?'"
        )
        idx += 1

    # ── DŁUGOŚĆ ──
    wc = len(words)
    if wc < 35:
        fixes.append(
            f"{idx}. [SKRYPT] Za krótki: {wc} słów. Minimum 35 (11s przy +28% TTS).\n"
            f"   Rozbuduj sekcję CORE o konkretny scenariusz: 'When someone does X to you...'"
        )
        idx += 1
    elif wc > 65:
        fixes.append(
            f"{idx}. [SKRYPT] Za długi: {wc} słów. Maksimum 60 (20s przy +28% TTS).\n"
            f"   Usuń ogólne zdania — zostaw tylko PRE-HOOK + PYTANIE + CORE + RE-HOOK + CTA."
        )
        idx += 1

    # ── ZAKAZANE SŁOWA W SKRYPCIE ──
    for bw in BANNED_WORDS:
        if bw in script.lower():
            fixes.append(
                f"{idx}. [SKRYPT] Zakazane słowo / fraza: '{bw}'.\n"
                f"   Usuń lub zastąp: zamiast 'save this' → 'follow for more'"
            )
            idx += 1

    # ── TREND ──
    if trend_data:
        combined = (title + " " + script).lower()
        trending_kw = trend_data.get("trending_keywords", [])
        hot_topics  = trend_data.get("hot_topics", [])
        kw_hits = [k for k in trending_kw if k.lower() in combined]
        if not kw_hits and trending_kw:
            fixes.append(
                f"{idx}. [TREND] Żadne dziś trending keywords nie są w skrypcie.\n"
                f"   Wstaw co najmniej 2 z: {', '.join(trending_kw[:6])}\n"
                f"   Przykład: zamiast 'they control you' → 'they use {trending_kw[0] if trending_kw else 'manipulation'} on you'"
            )
            idx += 1
        topic_hits = [t for t in hot_topics if t.lower() in combined]
        if not topic_hits and hot_topics:
            fixes.append(
                f"{idx}. [TREND] Temat niezgodny z dzisiejszym trendem.\n"
                f"   Dziś na topie: {', '.join(hot_topics[:4])}.\n"
                f"   Spróbuj przekierować kąt narracji na jeden z tych tematów."
            )
            idx += 1

    if not fixes:
        fixes.append("✅ Nie znaleziono konkretnych błędów — sprawdź hook jakościowo.")

    return fixes


def audit_short(
    title: str,
    script: str,
    video_path: str | None = None,
    verbose: bool = True
) -> dict:
    """
    Glowna funkcja audytu. Zwraca dict z:
      - score: 0-100 (+ bonus trend)
      - decision: "APPROVED" | "REJECTED"
      - breakdown: szczegoly per kategoria
      - fix_report: lista konkretnych instrukcji naprawy (gdy REJECTED)
    """
    G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[1m"; X = "\033[0m"; C = "\033[96m"

    if verbose:
        print(f"\n{C}{'='*65}{X}")
        print(f"{C}{B}  QUALITY AUDITOR -- Ocena Shorta przed wrzuceniem{X}")
        print(f"{C}{'='*65}{X}")
        print(f"  Tytul:  {title[:65]}")
        print(f"  Skrypt: {script[:80]}...")
        print()

    s_title,   n_title         = score_title(title)
    s_script,  n_script        = score_script(script)
    s_hook,    n_hook          = score_hook_quality(script)
    s_unique,  n_unique        = score_uniqueness(title, script)
    s_tech,    n_tech          = score_technical(video_path)
    s_kw,      n_kw            = score_keywords(title, script)
    s_trend,   n_trend, t_data = score_trend_alignment(title, script)
    p_sense,   n_sense         = check_ai_sense(script)

    # Max 100 (6 kat.) + bonus trend do 10 - kara za brak logiki
    raw_total = s_title + s_script + s_hook + s_unique + s_tech + s_kw + s_trend + p_sense
    total = max(0, min(raw_total, 100))

    # Reject naturally if AI hallucinated too much causing < 68, or force reject if penalty extreme
    if p_sense <= -10:
         decision = "REJECTED"
    else:
         decision = "APPROVED" if total >= APPROVE_THRESHOLD else "REJECTED"

    breakdown = {
        "title":        {"score": s_title,  "max": 20, "notes": n_title},
        "script":       {"score": s_script, "max": 30, "notes": n_script},
        "hook":         {"score": s_hook,   "max": 15, "notes": n_hook},
        "uniqueness":   {"score": s_unique, "max": 15, "notes": n_unique},
        "technical":    {"score": s_tech,   "max": 10, "notes": n_tech},
        "keywords":     {"score": s_kw,     "max": 10, "notes": n_kw},
        "trend_today":  {"score": s_trend,  "max": 10, "notes": n_trend},
        "ai_sense":     {"score": p_sense,  "max": 0,  "notes": n_sense},
    }

    fix_report = []
    if decision == "REJECTED":
        fix_report = generate_fix_report(breakdown, title, script, t_data or None)
        # Append specific NLP fixes
        if p_sense < 0:
            fix_report.append("1. [WYMOWA/LOGIKA AI] Skrypt zawiera zacięcia, masowe powtórzenia lub robotyczne zwroty ('in conclusion' itp.).\n   WYMÓG: Powiedz to ludzkim, naturalnym językiem. Bez zapętleń.")
        if s_unique <= 0:
            fix_report.append("2. [KOPIA TREŚCI] Napisałeś DOKŁADNIE to samo co w ostatnich filmach! To karygodne.\n   WYMÓG: Użyj absolutnie innego kąta psychologii, w innym kontekście (np. związek zamiast biura).")

    if verbose:
        sections = [
            ("FORMAT TYTULU",        "title",       20),
            ("STRUKTURA SKRYPTU",    "script",      30),
            ("JAKOSC HOOKA",         "hook",        15),
            ("UNIKALNOSC (NLP)",     "uniqueness",  15),
            ("TECHNICZNE",           "technical",   10),
            ("SLOWA KLUCZOWE",       "keywords",    10),
            ("SENS / AI FILLERY",    "ai_sense",     0),
            ("TREND DNIA (BONUS)",   "trend_today", 10),
        ]
        for label, key, maxpts in sections:
            s  = breakdown[key]["score"]
            ns = breakdown[key]["notes"]
            filled = max(0, min(10, int(s / maxpts * 10) if maxpts > 0 else 0))
            bar = "#" * filled + "." * (10 - filled)
            col = G if s >= maxpts * 0.7 else (Y if s >= maxpts * 0.4 else R)
            print(f"  {B}{label}{X}")
            print(f"    [{col}{bar}{X}] {col}{s:+3d}{X}/{maxpts}")
            for n in ns:
                print(f"       {n}")
            print()

        # Finalny wynik
        result_col = G if decision == "APPROVED" else R
        bar_len = int(total / 100 * 40)
        bar = "#" * bar_len + "." * (40 - bar_len)
        print(f"  {C}{'-'*65}{X}")
        print(f"  {B}WYNIK: [{result_col}{bar}{X}] {result_col}{B}{total}/100{X}")
        if s_trend > 0:
            print(f"  (bonus TREND dnia: +{s_trend}/10)")
        print(f"  {B}DECYZJA: {result_col}{decision}{X}  (prog: {APPROVE_THRESHOLD}/100)")

        if decision == "REJECTED" and fix_report:
            print(f"\n  {R}{B}CO POPRAWIC ABY ZDAC AUDYT:{X}")
            print(f"  {R}{'-'*65}{X}")
            for fix in fix_report:
                for line in fix.split("\n"):
                    print(f"  {Y}{line}{X}")
                print()
        elif decision == "APPROVED":
            # BUGFIX: exclude categories with max=0 (ai_sense) to avoid ZeroDivisionError
            non_trend = [(k, v) for k, v in breakdown.items()
                         if k != "trend_today" and v["max"] > 0]
            if non_trend:
                worst = min(non_trend, key=lambda kv: kv[1]["score"] / kv[1]["max"])
                print(f"  {Y}Najslabszy punkt: {worst[0].upper()} "
                      f"({worst[1]['score']}/{worst[1]['max']}) -- warto poprawic nastepnym razem{X}")
        print(f"  {C}{'='*65}{X}\n")

    return {
        "score":      total,
        "decision":   decision,
        "approved":   decision == "APPROVED",
        "breakdown":  breakdown,
        "fix_report": fix_report,
        "title":      title,
        "timestamp":  datetime.now().isoformat(),
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quality Auditor — ocenia Shorta przed wrzuceniem")
    parser.add_argument("--title",      required=True, help="Tytuł Shorta")
    parser.add_argument("--script",     required=True, help="Tekst skryptu")
    parser.add_argument("--video-path", default=None,  help="Ścieżka do pliku .mp4 (opcjonalnie)")
    parser.add_argument("--json",       action="store_true", help="Wyjście w formacie JSON")
    args = parser.parse_args()

    result = audit_short(args.title, args.script, args.video_path)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["approved"] else 1)
