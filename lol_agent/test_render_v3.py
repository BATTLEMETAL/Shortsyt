import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_editor import render_short

# Test ze smart camera na clip2
result = render_short(
    source_path=r'C:\Medal\Edits\MedalTVLeagueofLegends20260524184943960-trim-1780471647631.mp4',
    clip_start=0,
    clip_end=14.2,
    action_type='outplay',
    champion_name='Yone',
    rank='Gold',
    use_speed_ramp=True,
    use_zoom_punch=True,
    use_smart_camera=True,
    peak_moment=8.0,
    output_filename='test_v3_smart_camera.mp4'
)
print('GOTOWE:', result)
