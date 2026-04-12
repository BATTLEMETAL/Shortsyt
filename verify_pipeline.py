"""
verify_pipeline.py — Pełna Weryfikacja Pipeline'u Shortsów
===========================================================
Sprawdza wszystkie krytyczne komponenty systemu i raportuje status.

Weryfikuje:
  1. Pliki konfiguracyjne i historię
  2. Duplikaty w historii shortów
  3. Audytor jakości (smoke test)
  4. Synapsa bridge (dostępność)
  5. Edge-TTS (głos AI)
  6. FFmpeg (renderowanie)
  7. Peak hours analysis summary
  8. Fallback script diversity

Użycie:
    python verify_pipeline.py
    python verify_pipeline.py --full   # Włącznie z testem audytora na żywo
"""

import os
import sys
import json
import difflib
import subprocess
import argparse
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

G = "\033[92m"
Y = "\033[93m"
R = "\033[91m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"

TOPIC_HISTORY_FILE  = "accounts/topic_history.json"
DIRECTIVE_FILE      = "adaptation_directive.json"
AUDIT_REPORT_FILE   = "audit_report.json"
PUBLISH_REPORT_FILE = "publish_report.json"


def check(label: str, ok: bool, detail: str = "", warn: bool = False):
    if ok:
        icon = f"{G}✅{X}"
    elif warn:
        icon = f"{Y}⚠️ {X}"
    else:
        icon = f"{R}❌{X}"
    detail_str = f"  {detail}" if detail else ""
    print(f"  {icon} {label}{detail_str}")
    return ok


def section(title: str):
    print(f"\n{C}── {title} {'─' * max(1, 55 - len(title))}{X}")


def run_external(cmd: list, timeout: int = 10) -> tuple:
    """Uruchamia zewnętrzne narzędzie, zwraca (ok, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except FileNotFoundError:
        return False, "", "not found"
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


# ─── 1. Pliki i konfiguracja ──────────────────────────────────────────────────
def verify_files() -> int:
    section("PLIKI KONFIGURACYJNE")
    fails = 0
    critical_files = [
        ("agent_dark_psychology.py", True),
        ("quality_auditor.py", True),
        ("cashcow_generator.py", True),
        ("synapsa_bridge.py", True),
        ("smart_video_analyzer.py", True),
        ("trend_scout.py", False),
        ("adaptation_directive.json", False),
        ("accounts/topic_history.json", False),
        ("accounts/topic_rotation.json", False),
        ("client_secret.json", True),
        ("accounts/dark_mindset_token.pickle", True),
        ("verify_duplicates.py", False),
        ("analyze_peak_hours.py", False),
    ]
    for fname, is_critical in critical_files:
        exists = os.path.exists(fname)
        size = os.path.getsize(fname) if exists else 0
        size_str = f"({size:,} B)" if exists else ""
        ok = check(fname, exists, size_str, warn=not is_critical)
        if is_critical and not exists:
            fails += 1
    return fails


# ─── 2. Historia i duplikaty ───────────────────────────────────────────────────
def verify_duplicates() -> int:
    section("HISTORIA SHORTÓW — DUPLIKATY")
    fails = 0

    if not os.path.exists(TOPIC_HISTORY_FILE):
        check("topic_history.json", False, "brak pliku", warn=True)
        return 0

    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        check("topic_history.json parse", False, str(e))
        return 1

    total_videos = sum(len(v) for v in data.values())
    total_dups = 0

    for profile, history in data.items():
        check(f"Profil '{profile}' — {len(history)} filmów w historii", True)

        # Szukaj duplikatów
        dups_found = []
        for i in range(len(history)):
            for j in range(i + 1, len(history)):
                sa = history[i].get("script", "")
                sb = history[j].get("script", "")
                if sa and sb:
                    ratio = difflib.SequenceMatcher(None, sa.lower(), sb.lower()).ratio()
                    if ratio > 0.40:
                        dups_found.append((i, j, ratio))

        if dups_found:
            total_dups += len(dups_found)
            for idx_a, idx_b, ratio in dups_found[:3]:
                ta = history[idx_a].get("title", "?")[:40]
                tb = history[idx_b].get("title", "?")[:40]
                check(
                    f"  DUP #{idx_a+1} vs #{idx_b+1} ({ratio:.0%})",
                    False,
                    f"'{ta}' vs '{tb}'"
                )
            fails += 1
        else:
            check(f"  Brak duplikatów w profilu '{profile}'", True)

    if not check(f"Łączna unikatowość ({total_videos} filmów, {total_dups} duplikatów)", total_dups == 0):
        print(f"    {Y}→ Uruchom: python verify_duplicates.py --fix{X}")
        fails += 1

    return fails


# ─── 3. Audytor jakości ────────────────────────────────────────────────────────
def verify_auditor(full: bool = False) -> int:
    section("AUDYTOR JAKOŚCI")
    fails = 0

    try:
        from quality_auditor import audit_short, APPROVE_THRESHOLD
        check("quality_auditor.py importowalny", True)
    except Exception as e:
        check("quality_auditor.py importowalny", False, str(e))
        return 1

    # Sprawdź threshold
    try:
        with open("quality_auditor.py", "r", encoding="utf-8") as f:
            qa_content = f.read()
        has_035 = "0.35" in qa_content
        has_050 = "0.50" in qa_content
        has_old = "0.45" in qa_content and "s_ratio > 0.45" in qa_content
        check("Próg deduplikacji: graduated 0.35/0.50", has_035 and has_050 and not has_old,
              "(fix naprawiony)" if has_035 else f"{R}STARY PRÓG 0.45 — uruchom fix_auditor_threshold.py!{X}",
              warn=not has_035)
    except Exception as e:
        check("Sprawdzenie progu", False, str(e), warn=True)

    if full:
        # Smoke test na przykładowym scripcie
        test_title = "Have you ever noticed how some people command respect effortlessly? 🧠 #shorts"
        test_script = (
            "Stop. Don't scroll. Have you ever felt completely drained after talking to someone? "
            "That's not a coincidence. They're using emotional vampirism deliberately triggering "
            "micro-frustrations. The moment you respond with absolute calm they lose all power. "
            "But here's the dark part — they often don't even know they're doing it. "
            "Follow if this sounds familiar."
        )
        try:
            result = audit_short(test_title, test_script, verbose=False)
            approved = result.get("approved", False)
            score = result.get("score", 0)
            check(f"Smoke test audytu: {score}/100 — {result.get('decision', '?')}",
                  score >= 50, f"(próg zatwierdzenia: {APPROVE_THRESHOLD})", warn=score < 68)
        except Exception as e:
            check("Smoke test audytu", False, str(e))
            fails += 1

    # Sprawdź ostatnie audyty
    if os.path.exists(AUDIT_REPORT_FILE):
        try:
            with open(AUDIT_REPORT_FILE, "r", encoding="utf-8") as f:
                audit_log = json.load(f)
            recent = audit_log[-5:] if audit_log else []
            approved_count = sum(1 for a in recent if a.get("approved"))
            avg_score = sum(a.get("score", 0) for a in recent) / max(len(recent), 1)
            check(
                f"Ostatnie audyty: {approved_count}/{len(recent)} approved, avg {avg_score:.0f}/100",
                approved_count > 0 or len(recent) == 0,
                warn=approved_count == 0 and len(recent) > 0
            )
        except Exception as e:
            check("audit_report.json", False, str(e), warn=True)

    return fails


# ─── 4. Narzędzia zewnętrzne ──────────────────────────────────────────────────
def verify_tools() -> int:
    section("NARZĘDZIA ZEWNĘTRZNE")
    fails = 0

    # FFmpeg
    ok, out, err = run_external(["ffmpeg", "-version"])
    ver = out.split("\n")[0][:50] if ok else err[:40]
    if not check("FFmpeg", ok, ver):
        fails += 1

    # FFprobe
    ok, out, _ = run_external(["ffprobe", "-version"])
    ver = out.split("\n")[0][:50] if ok else "brak"
    check("FFprobe", ok, ver, warn=not ok)

    # Edge-TTS
    ok, out, err = run_external(["edge-tts", "--list-voices"], timeout=15)
    if ok:
        voice_count = out.count("ShortName")
        check("Edge-TTS", True, f"{voice_count} głosów dostępnych")
    else:
        # Spróbuj przez venv
        venv_etss = os.path.join("venv313", "Scripts", "edge-tts.exe")
        if os.path.exists(venv_etss):
            check("Edge-TTS (venv)", True, venv_etss)
        else:
            check("Edge-TTS", False, "Zainstaluj: pip install edge-tts", warn=True)

    # yt-dlp
    ok, out, _ = run_external(["yt-dlp", "--version"])
    ver = out.strip()[:30] if ok else "brak"
    check("yt-dlp", ok, ver, warn=not ok)

    # Whisper (через importlib)
    try:
        import importlib.util
        spec = importlib.util.find_spec("whisper")
        if spec:
            check("OpenAI Whisper", True, spec.origin[:60] if spec.origin else "dostępny")
        else:
            check("OpenAI Whisper", False, "pip install openai-whisper", warn=True)
    except Exception:
        check("OpenAI Whisper", False, "sprawdź venv ML", warn=True)

    return fails


# ─── 5. Synapsa bridge ────────────────────────────────────────────────────────
def verify_synapsa() -> int:
    section("SYNAPSA BRIDGE")
    fails = 0

    synapsa_python = r"C:\Users\mz100\PycharmProjects\Synapsa\venv\Scripts\python.exe"
    synapsa_root   = r"C:\Users\mz100\PycharmProjects\Synapsa"

    check("Synapsa venv python", os.path.exists(synapsa_python), synapsa_python)
    check("Synapsa root", os.path.isdir(synapsa_root), synapsa_root)

    agent_file = os.path.join(synapsa_root, "agent.py")
    if not check("agent.py", os.path.exists(agent_file), agent_file, warn=True):
        fails += 1

    # VRAM check
    ok, out, _ = run_external(
        ["nvidia-smi", "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
        timeout=5
    )
    if ok and out.strip():
        parts = out.strip().split(",")
        if len(parts) >= 2:
            free_mb  = int(parts[0].strip())
            total_mb = int(parts[1].strip())
            free_gb  = free_mb / 1024
            total_gb = total_mb / 1024
            vram_ok  = free_gb >= 4.5
            check(f"VRAM GPU: {free_gb:.1f}/{total_gb:.1f} GB wolne",
                  vram_ok,
                  f"(min. 4.5 GB dla Synapsy)" if not vram_ok else "",
                  warn=not vram_ok)
    else:
        check("VRAM GPU", False, "nvidia-smi niedostępne", warn=True)

    return fails


# ─── 6. Publikacje i adaptation directive ────────────────────────────────────
def verify_directive() -> int:
    section("DYREKTYWA ADAPTACYJNA I PUBLIKACJE")
    fails = 0

    if not os.path.exists(DIRECTIVE_FILE):
        check("adaptation_directive.json", False, "brak — uruchom smart_video_analyzer.py", warn=True)
    else:
        try:
            with open(DIRECTIVE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            gen_at = d.get("generated_at", "?")[:16]
            hour   = d.get("best_publish_hour_utc", "?")
            pl_h   = (hour + 1) % 24 if isinstance(hour, int) else "?"
            directive_text = d.get("directive", "")
            check("adaptation_directive.json", True, f"Wygenerowano: {gen_at}")
            check(f"Optymalny czas: {hour}:00 UTC = {pl_h}:00 PL", isinstance(hour, int))
            check("Dyrektywa ma treść", bool(directive_text) and len(directive_text) > 50,
                  f"({len(directive_text)} znaków)")
        except Exception as e:
            check("adaptation_directive.json parse", False, str(e))
            fails += 1

    if os.path.exists(PUBLISH_REPORT_FILE):
        try:
            with open(PUBLISH_REPORT_FILE, "r", encoding="utf-8") as f:
                pub = json.load(f)
            last = pub[-1] if pub else {}
            ts   = last.get("timestamp", "?")[:16]
            title = last.get("title", "?")[:50]
            check(f"Ostatnia publikacja", bool(last), f"[{ts}] '{title}'")
        except Exception:
            check("publish_report.json", False, "błąd odczytu", warn=True)

    return fails


# ─── 7. Fallback script diversity ─────────────────────────────────────────────
def verify_fallback_diversity() -> int:
    section("RÓŻNORODNOŚĆ FALLBACK SCRIPTÓW")
    fails = 0

    # Wczytaj fallbacki z agenta
    try:
        with open("agent_dark_psychology.py", "r", encoding="utf-8") as f:
            agent_code = f.read()

        # Wyciągnij fallbacki między fbs = [ i ]
        import re
        fbs_match = re.search(r'fbs\s*=\s*\[(.*?)\]\s*#\s*──\s*ANTI-DUPLICATE', agent_code, re.DOTALL)
        if not fbs_match:
            check("Fallback scripts — lista fbs", False, "nie znaleziono nowej listy w kodzie")
            return 1

        fbs_block = fbs_match.group(1)
        # Wyciągnij stringi
        scripts = re.findall(r'"((?:[^"\\]|\\.)*)"\s*,\s*#', fbs_block)
        if not scripts:
            # Try single-quote variant
            scripts = re.findall(r"([A-Z][^\"]{40,200}\.)\s*(?:#|\")", fbs_block)

        # Count unique topics via first_keyword extraction
        check(f"Liczba fallback skryptów: {len(scripts)}", len(scripts) >= 6,
              "(min. 6 dla pełnej rotacji 2-filmowej)", warn=len(scripts) < 6)

        # Sprawdź wzajemne podobieństwo
        max_sim = 0.0
        worst_pair = (0, 0)
        for i in range(len(scripts)):
            for j in range(i + 1, len(scripts)):
                sim = difflib.SequenceMatcher(None, scripts[i].lower(), scripts[j].lower()).ratio()
                if sim > max_sim:
                    max_sim = sim
                    worst_pair = (i, j)

        check(
            f"Wzajemne podobieństwo fallbacków: max {max_sim:.0%}",
            max_sim < 0.50,
            f"(pary #{worst_pair[0]+1} vs #{worst_pair[1]+1})",
            warn=max_sim >= 0.35
        )

        # Sprawdź anti-duplicate selector
        has_selector = "_USED_FALLBACKS_" in agent_code
        check("Anti-duplicate fallback selector", has_selector,
              "(video_index-based rotation active)")

        # Sprawdź dedup guard
        has_guard = "DEDUP GUARD" in agent_code
        check("Pre-render DEDUP GUARD", has_guard)

    except Exception as e:
        check("agent_dark_psychology.py parse", False, str(e))
        fails += 1

    return fails


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Weryfikator pipeline'u shortsów")
    parser.add_argument("--full", action="store_true", help="Włącz smoke test audytora")
    args = parser.parse_args()

    print(f"\n{B}{'='*70}")
    print(f"  🔬 VERIFY PIPELINE — Pełna weryfikacja systemu ShortsYT")
    print(f"  Data: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Wersja: 2.0")
    print(f"{'='*70}{X}")

    total_fails = 0
    total_fails += verify_files()
    total_fails += verify_duplicates()
    total_fails += verify_auditor(full=args.full)
    total_fails += verify_tools()
    total_fails += verify_synapsa()
    total_fails += verify_directive()
    total_fails += verify_fallback_diversity()

    # Peak hours summary
    section("PEAK HOURS SUMMARY")
    if os.path.exists(DIRECTIVE_FILE):
        try:
            with open(DIRECTIVE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            h_utc = d.get("best_publish_hour_utc", 18)
            h_pl  = (h_utc + 1) % 24 if isinstance(h_utc, int) else "?"
            wd    = d.get("best_publish_weekday", "?")
            days  = {0: "Pn", 1: "Wt", 2: "Sr", 3: "Czw", 4: "Pt", 5: "Sob", 6: "Nd"}
            wd_name = days.get(wd, str(wd)) if isinstance(wd, int) else "?"
            print(f"  {G}Film 1{X}: publikuj natychmiast rano (~10:00 PL)")
            print(f"  {G}Film 2{X}: zaplanuj na {h_pl:02d}:00 PL ({h_utc:02d}:00 UTC) — najlepszy peak ({wd_name})")
            print(f"  {G}→{X} adaptation_directive.json: best_publish_hour_utc = {h_utc}")
        except Exception:
            print(f"  {Y}⚠️  Brak danych — uruchom: python analyze_peak_hours.py --update-directive{X}")

    # Finalne podsumowanie
    print(f"\n{C}{'='*70}{X}")
    if total_fails == 0:
        print(f"{G}{B}✅ PIPELINE OK — wszystkie komponenty działają poprawnie!{X}")
        print(f"{G}   Możesz bezpiecznie uruchomić: python agent_dark_psychology.py{X}")
    else:
        print(f"{R}{B}❌ PIPELINE MA {total_fails} PROBLEM(Y) — napraw przed uruchomieniem!{X}")
        if total_fails <= 2:
            print(f"{Y}   Nieduże problemy — pipeline działa ale nie w 100%.{X}")

    print(f"\n{C}Skrypty diagnostyczne:{X}")
    print(f"  python verify_duplicates.py --fix   # usuwa duplikaty z historii")
    print(f"  python analyze_peak_hours.py --update-directive  # aktualizuje peak hours")
    print(f"  python quality_auditor.py --title '...' --script '...'  # test audytora")
    print(f"{C}{'='*70}{X}\n")

    sys.exit(0 if total_fails == 0 else 1)


if __name__ == "__main__":
    main()
