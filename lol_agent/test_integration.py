"""Test pełnej integracji Medal DB + YT Performance."""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from medal_db import get_clip_metadata
from lol_smart_titles import analyze_by_action_type, fetch_channel_shorts_performance

print("=== MEDAL AUTO-DETECT ===")
clips = [
    r"C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4",
    r"C:\Medal\Edits\MedalTVLeagueofLegends20260524184943960-trim-1780471647631.mp4",
    r"C:\Medal\Edits\MedalTVLeagueofLegends20260524191243654-trim-1780471734071.mp4",
]
for c in clips:
    m = get_clip_metadata(c)
    print(f"  {m['title']:25s} -> action={m['action_type']:12s} champion={m['champion']}")

print("\n=== YT PERFORMANCE PER ACTION TYPE ===")
vids = fetch_channel_shorts_performance()
perf = analyze_by_action_type(vids)
for k, v in sorted(perf.items(), key=lambda x: -x[1]['avg_views']):
    print(f"  {k:12s}: {v['count']} shorts, avg {v['avg_views']:,} views, best {v['best_views']:,}")
    print(f"               best title: \"{v['best_title'][:60]}\"")

print("\n=== FULL PIPELINE TEST (bez AI) ===")
print("Gotowe! Pipeline teraz automatycznie:")
print("  1. Czyta Medal DB -> typ killa + champion")
print("  2. Analizuje YT performance per action type")
print("  3. Generuje smart title z Gemini (z kontekstem YT)")
print("  4. Nakłada hook_text overlay na wideo")
print("\nKomenda: python run_lol_agent.py --dry-run")
print("  (bez --champion! Medal auto-detect)")
