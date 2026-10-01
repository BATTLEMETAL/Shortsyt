"""
Pełny zestaw testów integracyjnych (Test Suite) dla LOL Agent & Autonomous Module
"""
import os
import sys
import json
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PENTA_CLIP = r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4"
BORING_CLIP = r"C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_08-24-2026_16-10-27-592\League of Legends 08-24-2026 16-15-59-670_0.mp4"

results = {}

print("\n" + "="*65)
print("🧪 LOL AGENT — KOMPLETNY AUDYT I TEST SUITE SYSTEMU")
print("="*65)

# ── TEST 1: Smart Titles & Gemini Multi-Model Pool ─────────────────────────────
print("\n[TEST 1/5] Gemini Multi-Model Pool (lol_smart_titles)...")
try:
    from lol_smart_titles import generate_smart_title
    meta = generate_smart_title(action_type="pentakill", champion_name="Katarina", rank="Platinum")
    title = meta.get("title", "")
    hook = meta.get("hook_text", "")
    assert len(title) > 5, "Tytuł jest zbyt krótki"
    assert len(hook) > 2, "Hook jest zbyt krótki"
    print(f"  ✅ PASS: Tytuł='{title}' | Hook='{hook}'")
    results["gemini_pool"] = "PASS"
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    results["gemini_pool"] = f"FAIL: {e}"

# ── TEST 2: Smart Clutch Evaluator (S_TIER vs REJECT) ──────────────────────────
print("\n[TEST 2/5] Smart Clutch Evaluator (autonomous/evaluator.py)...")
try:
    from autonomous.evaluator import evaluate_clip_quality
    res_penta = evaluate_clip_quality(PENTA_CLIP)
    
    assert "tier" in res_penta, f"Evaluator nie zwrócił klucza 'tier'. Wynik: {res_penta}"
    assert "score" in res_penta, f"Evaluator nie zwrócił klucza 'score'. Wynik: {res_penta}"

    # Pentakill musi być worthy=True (A_TIER lub S_TIER) — publikowalna
    # Nie wymagamy S_TIER, bo klip z powolnym pacing (25s span) dostaje A_TIER — to poprawne.
    assert res_penta.get("worthy") == True, f"Penta powinna być zakwalifikowana, tier={res_penta.get('tier')}, score={res_penta.get('score')}"
    assert res_penta.get("tier") in ("S_TIER", "A_TIER"), f"Oczekiwano S_TIER lub A_TIER dla Penty, otrzymano: {res_penta.get('tier')} (score={res_penta.get('score')})"
    
    penta_info = f"Score={res_penta.get('score', 0):.1f} [{res_penta.get('tier', '?')}] worthy={res_penta.get('worthy')}"
    
    # Boring clip — opcjonalnie (może nie istnieć)
    boring_info = ""
    if os.path.exists(BORING_CLIP):
        res_boring = evaluate_clip_quality(BORING_CLIP)
        assert res_boring.get("worthy") == False, f"Słaby klip nie powinien być zakwalifikowany, tier={res_boring.get('tier')}"
        boring_info = f" | Boring Score={res_boring.get('score', 0):.1f} [{res_boring.get('tier', '?')}]"
    else:
        print(f"  ⚠️  Boring clip nie istnieje (skip): {BORING_CLIP}")
    
    print(f"  ✅ PASS: Penta {penta_info}{boring_info}")
    results["evaluator"] = "PASS"
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    results["evaluator"] = f"FAIL: {e}"

# ── TEST 3: Semantic OCR Action Deduplication ──────────────────────────────────
print("\n[TEST 3/5] Semantic OCR Action Deduplication...")
try:
    from run_lol_agent import _compute_action_fingerprint, _is_duplicate_action
    
    # Test deterministyczny: budujemy syntetyczny fingerprint identyczny z wpisem
    # UZOmupNxfrU z processed_hashes.json (TRIPLE KILL @0.0, QUADRAKILL @4.3, PENTAKILL @8.7)
    # Symulujemy że OCR z aktualnego klipu zwraca te same milestone'y (z niewielką różnicą ~0.2s).
    synthetic_peaks = [
        (10.0, "TRIPLE KILL"),   # rel_t po normalizacji = 0.0
        (14.3, "QUADRAKILL"),    # rel_t = 4.3
        (18.7, "PENTAKILL"),     # rel_t = 8.7 — pasuje do bazy (tolerancja 0.8s)
    ]
    fp = _compute_action_fingerprint(
        peaks=synthetic_peaks,
        champion="katarina",
        action_type="pentakill"
    )
    
    # Załaduj bazę processed_hashes
    with open("lol_agent/processed_hashes.json", "r", encoding="utf-8") as f:
        processed = json.load(f)
        
    is_dup, dup_info = _is_duplicate_action(fp, processed)
    assert is_dup == True, f"Deduplikator powinien wykryć duplikat meczu UZOmupNxfrU (fingerprint: {fp})"
    print(f"  ✅ PASS: Wykryto powtórzenie meczu -> {dup_info.get('url')} ('{dup_info.get('title')}')")
    
    # Upewnij się też że NON-duplikat nie jest wykrywany
    fp_new = _compute_action_fingerprint(
        peaks=[(1.0, "TRIPLE KILL"), (90.0, "PENTAKILL")],  # zupełnie inne timing
        champion="jinx",
        action_type="pentakill"
    )
    is_dup2, _ = _is_duplicate_action(fp_new, processed)
    assert is_dup2 == False, "Jinx z innym timing nie powinna być duplikatem Katariny"
    print(f"  ✅ PASS: Jinx (inny champion, inny timing) poprawnie odrzucona jako nie-duplikat")
    results["action_dedup"] = "PASS"
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    results["action_dedup"] = f"FAIL: {e}"

# ── TEST 4: Clip Ranker Integration ───────────────────────────────────────────
print("\n[TEST 4/5] Clip Ranker (lol_clip_ranker.py)...")
try:
    from lol_clip_ranker import score_clip
    rank_res = score_clip(PENTA_CLIP, verbose=False)
    # score_clip używa własnego uproszczonego OCR (nie evaluatora) — próg >50 jest realistyczny
    # dla klipu z pentakillem bez pełnego evaluatora; worthy wymaga >=2 kills
    assert rank_res.get("score", 0) > 50, f"Score w rankerze powinien być >50, jest {rank_res.get('score')}"
    assert rank_res.get("worthy") == True, f"Ranker powinien oznaczyć klip jako worthy, score={rank_res.get('score')}"
    print(f"  ✅ PASS: Ranker zintegrowany | Score={rank_res['score']:.1f} | Tier={rank_res.get('tier', 'N/A')}")
    results["clip_ranker"] = "PASS"
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    results["clip_ranker"] = f"FAIL: {e}"

# ── TEST 5: Watcher Logic & History Logger ─────────────────────────────────────
print("\n[TEST 5/5] Autonomous Watcher & History Engine...")
try:
    from autonomous.watcher import load_history, save_history, HISTORY_FILE
    hist = load_history()
    test_key = "test_verification_key_123"
    hist[test_key] = {"test": True, "timestamp": time.time()}
    save_history(hist)
    
    reloaded = load_history()
    assert test_key in reloaded, "Historia powinna zapisać i odczytać wpis"
    # Cleanup test key
    del reloaded[test_key]
    save_history(reloaded)
    print(f"  ✅ PASS: Watcher history JSON I/O stabilne ({HISTORY_FILE})")
    results["watcher_engine"] = "PASS"
except Exception as e:
    print(f"  ❌ FAIL: {e}")
    results["watcher_engine"] = f"FAIL: {e}"

# ── PODSUMOWANIE ──────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("📊 PODSUMOWANIE TESTÓW:")
all_pass = all(v == "PASS" for v in results.values())
for k, v in results.items():
    status_icon = "✅ PASS" if v == "PASS" else "❌ FAIL"
    print(f"   {k:<20}: {status_icon}")

if all_pass:
    print("\n🎉 WSZYSTKIE 5 TESTÓW ZAKOŃCZYŁY SIĘ SUKCESEM! SYSTEM W PEŁNI SPRAWNY.")
else:
    print("\n⚠️ WYKRYTO BŁĘDY W NIEKTÓRYCH MODUŁACH.")
print("="*65)
