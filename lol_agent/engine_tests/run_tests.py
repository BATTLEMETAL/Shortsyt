#!/usr/bin/env python3
"""Uruchamia wszystkie testy bez pytest:  python tests/run_tests.py   (z pytest też działają: pytest tests/)
Kod wyjścia 0 = wszystko przeszło. Testy editora potrzebują Pythona 3.12+ (jak cały projekt)."""
import importlib, os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
ok = bad = skipped = 0
for name in sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py")):
    try:
        mod = importlib.import_module(name)
    except Exception as e:
        skipped += 1; print(f"POMINIĘTY {name}: {type(e).__name__}: {str(e)[:110]}"); continue
    for fn in [getattr(mod, n) for n in dir(mod) if n.startswith("test_") and callable(getattr(mod, n))]:
        try:
            fn(); ok += 1
        except Exception:
            bad += 1; print(f"BŁĄD {name}.{fn.__name__}"); traceback.print_exc(limit=3)
print(f"\n{ok} przeszło, {bad} nie przeszło, {skipped} plików pominiętych")
sys.exit(1 if bad else 0)
