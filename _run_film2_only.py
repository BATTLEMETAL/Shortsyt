"""Uruchamia tylko 2. film (mind control body language) jako prywatny z harmonogramem +8h."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Wymusź UTF-8
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

os.environ["PYTHONIOENCODING"] = "utf-8"

from agent_dark_psychology import run_dark_agent_cycle, get_authenticated_service, PROFILE_NAME

print("=" * 60)
print("🎬 GENEROWANIE TYLKO FILM 2/2 (NAPRAWA)")
print("=" * 60)

youtube = get_authenticated_service(PROFILE_NAME)
if not youtube:
    print("❌ Błąd autoryzacji YouTube.")
    sys.exit(1)

# Wywołaj jako video_index=2 (dostanie +8h scheduling + nisza mind control)
success = run_dark_agent_cycle(video_index=2, total_videos=2, youtube=youtube)
if success:
    print("\n✅ Film 2 wygenerowany i wgrany jako PRYWATNY z harmonogramem!")
else:
    print("\n❌ Błąd generacji.")
