import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_editor import render_short
from smart_camera import detect_kill_events

SOURCE = r'C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_07-18-2026_16-42-23-642\League of Legends 07-18-2026 17-02-47-406_0.mp4'
CLIP_START = 0.0
CLIP_END   = 20.0

# ── Kill Event Detection ────────────────────────────────────────────────────
# Wykrywa kiedy wrogi HP bar znika = zabojstwo. Generuje etykiety multi-kill.
# Zwraca [(t_clip, label), ...] posortowane chronologicznie.
print("[PRE] Wykrywanie zabojstw...")
peaks = detect_kill_events(SOURCE, CLIP_START, CLIP_END, clip_duration=CLIP_END - CLIP_START,
                           action_type='pentakill')
print(f"[PRE] Kill peaks: {peaks}\n")

# ── Render ──────────────────────────────────────────────────────────────────
result = render_short(
    source_path   = SOURCE,
    clip_start    = CLIP_START,
    clip_end      = CLIP_END,
    action_type   = 'pentakill',
    champion_name = 'Katarina',
    rank          = 'Gold',
    use_speed_ramp  = True,
    use_zoom_punch  = True,
    use_smart_camera= True,
    peak_moment   = 17.0,    # QUADRA/PENTAKILL moment ~t=17-19s
    hook_text     = 'PENTAKILL',
    peaks         = peaks,   # Kill counter overlays
    output_filename = 'test_v23_katarina_kills.mp4'
)
print(f'\nGOTOWE: {result}')
