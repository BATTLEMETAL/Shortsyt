import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from lol_agent.api import pipeline_runner

def test_pipeline_state_initial():
    state = pipeline_runner.get_state()
    assert isinstance(state, dict)
    assert 'status' in state
    assert 'progress' in state
    assert 'current_step' in state

def test_cancellation_flow():
    with pipeline_runner._lock:
        pipeline_runner._state.status = pipeline_runner.PipelineStatus.RUNNING
    pipeline_runner._cancel_event.clear()
    assert not pipeline_runner._cancel_event.is_set()
    pipeline_runner.stop_pipeline()
    assert pipeline_runner._cancel_event.is_set()
    pipeline_runner._cancel_event.clear()
    with pipeline_runner._lock:
        pipeline_runner._state.status = pipeline_runner.PipelineStatus.IDLE

def test_run_pipeline_no_name_errors(tmp_path):
    dummy_video = tmp_path / 'dummy.mp4'
    dummy_video.write_bytes(b'dummy video content')

    with patch('lol_agent.lol_editor.render_short') as mock_render, \
         patch('lol_agent.lol_thumbnail.generate_thumbnail') as mock_thumb, \
         patch('lol_agent.smart_camera.detect_kill_events') as mock_kills, \
         patch('lol_agent.lol_metadata_generator.generate_metadata_universal') as mock_meta:
        
        mock_render.return_value = str(tmp_path / 'lol_short_final.mp4')
        mock_thumb.return_value = str(tmp_path / 'lol_short_final_thumb.jpg')
        mock_kills.return_value = [(2.0, 'KILL')]
        mock_meta.return_value = {'title': 'Test Title', 'description': 'Test Desc', 'pinned_comment': 'Test Comment'}

        pipeline_runner._cancel_event.clear()
        pipeline_runner._run_pipeline(
            source_path=str(dummy_video),
            clip_start=0.0,
            clip_end=15.0,
            action_type='outplay',
            champion_name='Katarina',
            rank='Master',
            peak_moment=0.0,
            hook_text='Hook',
            output_filename='lol_short_final.mp4',
            use_speed_ramp=True,
            use_zoom_punch=True,
            use_smart_camera=True,
            notify_token=None,
        )

        state = pipeline_runner.get_state()
        assert state['status'] == 'done'
        assert state.get('error') is None
        mock_render.assert_called_once()
