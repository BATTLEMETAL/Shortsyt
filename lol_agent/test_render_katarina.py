import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_clip_analyzer import analyze_motion, find_peak_action, detect_action_type, get_video_duration
from lol_editor import render_short

CLIP = r'C:\Medal\Edits\MedalTVLeagueofLegends20260512150318232-trim-1780471794645.mp4'

# Analiza ruchu — znajdź najlepsze 15s z 28s
print("== Analiza klipu 28s Katarina ==")
duration = get_video_duration(CLIP)
print(f"Długość: {duration:.1f}s")

motion = analyze_motion(CLIP, sample_rate=3)
peak_start, peak_end = find_peak_action(motion, duration, target_duration=15.0)
action_type = detect_action_type(motion, peak_start, peak_end)

print(f"Najlepsza akcja: {peak_start:.1f}s → {peak_end:.1f}s")
print(f"Typ akcji: {action_type}")

# Oblicz peak_moment względem wyciętego fragmentu
clip_dur = peak_end - peak_start
# Peak moment wewnątrz okna ~ 60% długości (zakładamy kill blisko końca)
peak_in_clip = clip_dur * 0.60

# Wygeneruj smart title i hook_text
from lol_smart_titles import generate_smart_title
metadata = generate_smart_title(
    action_type=action_type,
    champion_name='Katarina',
    rank='Gold',
    clip_path=CLIP
)
hook_text = metadata.get("hook_text", "CLUTCH PLAY")

result = render_short(
    source_path=CLIP,
    clip_start=peak_start,
    clip_end=peak_end,
    action_type=action_type,
    champion_name='Katarina',
    rank='Gold',
    use_speed_ramp=True,
    use_zoom_punch=True,
    use_smart_camera=True,
    peak_moment=peak_in_clip,
    hook_text=hook_text,
    output_filename='test_katarina_28s.mp4'
)

print(f'\nGOTOWE: {result}')
