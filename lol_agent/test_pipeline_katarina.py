import sys, os
sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(__file__))

from api.pipeline_runner import _run_pipeline, _state

VIDEO = r'C:\Users\mz100\Videos\Overwolf\Outplayed\League of Legends\League of Legends_10-11-2026_12-13-07-564\League of Legends 10-11-2026 12-19-05-438_0.mp4'

print("=== STARTING FULL PIPELINE VERIFICATION TEST ===")
_run_pipeline(
    source_path=VIDEO,
    clip_start=0.0,
    clip_end=15.0,
    action_type='triple',
    champion_name='Katarina',
    rank='Diamond',
    use_speed_ramp=True,
    use_zoom_punch=True,
    use_smart_camera=True,
    peak_moment=0.0,
    hook_text='TRIPLE KILL!',
    notify_token=None,
    output_filename='katarina_verified_golden.mp4',
)

print(f"\nPipeline finished!")
print(f"Status: {_state.status}")
print(f"Error: {_state.error}")
print(f"Output: {_state.output_path}")
print(f"Clip start: {_state.clip_start}s, Clip end: {_state.clip_end}s (Duration: {_state.clip_end - _state.clip_start:.1f}s)")
print(f"QA Status: {_state.qa_status}, QA Score: {_state.qa_score}")
