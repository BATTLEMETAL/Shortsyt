import sys
sys.stdout.reconfigure(encoding="utf-8")
from quality_auditor import audit_short, APPROVE_THRESHOLD

print(f"Prog zatwierdzenia: {APPROVE_THRESHOLD}/100")
print()

tests = [
    ("duplikat 100%",
     "Why Asking Someone for a Favor Makes Them",
     "Most people miss this. Have you noticed why asking someone a favor makes them like you. The Ben Franklin Effect. Follow for more."),
    ("zakazane slowo",
     "The Dark Truth Revealed About Fake Smiles",
     "Most people miss this. Have you noticed how fake smiles look different in the eyes. The orbicularis muscle never lies. Follow for more."),
    ("dobry skrypt",
     "Can you spot who actually controls the room?",
     "Most people miss this. Have you ever noticed how one person steeples their fingers and everyone goes quiet. That gesture signals complete confidence. Next time you see it you know who holds the power. Follow for more."),
    ("kicz",
     "Game Changer Mind Blowing Alpha Domination",
     "Knowledge is power. Use this wisely. Be the alpha. The power is yours. Mind-blowing dark truth. Share this before it disappears."),
]

all_ok = True
for name, title, script in tests:
    r = audit_short(title, script, verbose=False)
    bad_case = "duplikat" in name or "zakazane" in name or "kicz" in name
    expected = "REJECTED" if bad_case else "APPROVED"
    ok = r["decision"] == expected
    status = "OK" if ok else "FAIL"
    if not ok:
        all_ok = False
    print(f"  [{status}] {name}: {r['decision']} {r['score']}/100  (oczekiwano: {expected})")

print()
print("=== WYNIK:", "WSZYSTKO OK" if all_ok else "SA BLEDY!" , "===")
