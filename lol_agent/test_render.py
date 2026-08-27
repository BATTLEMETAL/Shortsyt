import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from lol_editor import render_short

result = render_short(
    source_path=r'C:\Medal\Edits\MedalTVLeagueofLegends20260524184943960-trim-1780471647631.mp4',
    clip_start=0,
    clip_end=14.2,
    action_type='outplay',
    champion_name='Katarina',
    rank='Gold',
    use_slowmo=False,
    output_filename='test_render_clip2.mp4'
)
print('GOTOWE:', result)
