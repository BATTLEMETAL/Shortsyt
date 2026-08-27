import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_editor import render_short

# Test v2: clip2 (14.2s), Katarina outplay, peak moment w polowie klipu
result = render_short(
    source_path=r'C:\Medal\Edits\MedalTVLeagueofLegends20260524184943960-trim-1780471647631.mp4',
    clip_start=0,
    clip_end=14.2,
    action_type='outplay',
    champion_name='Katarina',
    rank='Gold',
    use_speed_ramp=True,
    use_zoom_punch=True,
    peak_moment=8.0,
    output_filename='test_v2_outplay.mp4'
)
print('GOTOWE:', result)
