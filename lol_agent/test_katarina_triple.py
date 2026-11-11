import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_momentum_analyzer import analyze_momentum
from lol_editor import render_short

VIDEO = r'C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_10-11-2026_12-13-07-564\League of Legends 10-11-2026 12-19-05-438_0.mp4'

# Krok 1: Pobierz trim window
print("Analyzing momentum...")
r = analyze_momentum(VIDEO, use_ocr=True, action_hint='triple')
print(f"\n=== MOMENTUM RESULT ===")
print(f"  trim: {r.trim_start:.1f}s → {r.trim_end:.1f}s ({r.trim_end-r.trim_start:.1f}s)")
print(f"  peak_in_clip: {r.main_peak_in_clip:.1f}s")
print(f"  kills: {[(round(t,1), l) for t,l in r.peaks]}")

# Krok 2: Przygotuj peaks jako relative do trim_start
peaks_rel = [(t - r.trim_start, lbl) for (t, lbl) in r.peaks if r.trim_start <= t <= r.trim_end]
print(f"  peaks (relative): {[(round(t,1),l) for t,l in peaks_rel]}")

# Krok 3: Renderuj
print(f"\nRendering {r.trim_end-r.trim_start:.1f}s clip...")
out = render_short(
    source_path=VIDEO,
    clip_start=r.trim_start,
    clip_end=r.trim_end,
    action_type='triple',
    champion_name='Katarina',
    rank='Diamond',
    use_speed_ramp=True,
    use_zoom_punch=True,
    use_smart_camera=True,
    peak_moment=r.main_peak_in_clip,
    hook_text='TRIPLE KILL!',
    peaks=peaks_rel,
    output_filename='test_katarina_triple_v2.mp4',
)
print(f"\n✅ OUTPUT: {out}")
