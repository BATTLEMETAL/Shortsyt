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
    assert 'queue_length' in state
    assert 'queue' in state
    assert 'title_variant_b' in state


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


def test_job_queue_mechanism():
    pipeline_runner.clear_job_queue()
    with pipeline_runner._lock:
        pipeline_runner._state.status = pipeline_runner.PipelineStatus.RUNNING

    # Without queue_if_busy, should reject
    started = pipeline_runner.start_pipeline(
        source_path="clip1.mp4",
        clip_start=0.0,
        clip_end=15.0,
        queue_if_busy=False,
    )
    assert started is False
    assert pipeline_runner.get_state()['queue_length'] == 0

    # With queue_if_busy, should accept and queue
    queued = pipeline_runner.start_pipeline(
        source_path="clip2.mp4",
        clip_start=0.0,
        clip_end=15.0,
        output_filename="clip2_output.mp4",
        queue_if_busy=True,
    )
    assert queued is True
    st = pipeline_runner.get_state()
    assert st['queue_length'] == 1
    assert len(st['queue']) == 1
    assert st['queue'][0]['output_filename'] == "clip2_output.mp4"
    queue = pipeline_runner.get_job_queue()
    assert len(queue) == 1
    assert queue[0]['output_filename'] == "clip2_output.mp4"

    pipeline_runner.stop_pipeline(clear_queue=True)
    assert pipeline_runner.get_state()['queue_length'] == 0
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
        mock_meta.return_value = {
            'title': 'Test Title',
            'title_variant_b': 'Test Title B (Hook)',
            'description': 'Test Desc',
            'pinned_comment': 'Test Comment',
        }

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
        assert state['title'] == 'Test Title'
        assert state['title_variant_b'] == 'Test Title B (Hook)'
        mock_render.assert_called_once()


def test_pipeline_runner_auto_centering_on_long_clip(tmp_path):
    """
    Kluczowy test regresyjny:
    Gdy użytkownik podaje klip trwający > 20s (np. 35s) z domyślnym oknem (0.0s do 15.0s),
    a akcja zaczyna się w dalszej części wideo (np. 8.7s),
    pipeline_runner MUSI automatycznie przesunąć clip_start na akcję,
    zamiast wyrenderować 15 sekund pustego marszu przez dżunglę.
    """
    dummy_video = tmp_path / 'long_clip.mp4'
    dummy_video.write_bytes(b'dummy content')

    with patch('cv2.VideoCapture') as mock_cap_cls, \
         patch('lol_agent.lol_frag_detector.analyze_clip_frags') as mock_frag, \
         patch('lol_agent.lol_editor.render_short') as mock_render, \
         patch('lol_agent.lol_thumbnail.generate_thumbnail') as mock_thumb, \
         patch('lol_agent.smart_camera.detect_kill_events') as mock_kills, \
         patch('lol_agent.lol_metadata_generator.generate_metadata_universal') as mock_meta, \
         patch('lol_agent.lol_quality_validator.validate_rendered_short') as mock_qa:

        # Mockowanie wideo o długości 35s
        mock_cap = MagicMock()
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else (1050.0 if prop == 7 else 0)
        mock_cap.isOpened.return_value = True
        mock_cap_cls.return_value = mock_cap

        # Frag detector wykrywa akcję w oknie 6.9s - 28.2s
        mock_frag_res = MagicMock()
        mock_frag_res.detected_frag_type = 'triple'
        mock_frag_res.suggested_title_hook = 'TRIPLE KILL!'
        mock_frag.return_value = mock_frag_res

        with patch('lol_agent.lol_frag_detector.compute_optimal_clip_window', return_value=(6.9, 28.2, 19.1, None)):
            mock_render.return_value = str(tmp_path / 'out.mp4')
            mock_thumb.return_value = str(tmp_path / 'out_thumb.jpg')
            mock_kills.return_value = [(1.8, 'DOUBLE KILL'), (8.4, 'KILL')]
            mock_meta.return_value = {'title': 'Auto Centered Title'}
            
            mock_qa_res = MagicMock()
            mock_qa_res.qa_status = 'PASS'
            mock_qa_res.qa_score = 94
            mock_qa_res.diagnostic_details = ['Auto-centered OK']
            mock_qa_res.rejection_code = None
            mock_qa.return_value = mock_qa_res

            pipeline_runner._cancel_event.clear()
            pipeline_runner._run_pipeline(
                source_path=str(dummy_video),
                clip_start=0.0,
                clip_end=15.0,
                action_type='triple',
                champion_name='Katarina',
                rank='Diamond',
                peak_moment=0.0,
                hook_text='TRIPLE KILL!',
                output_filename='out.mp4',
                use_speed_ramp=True,
                use_zoom_punch=True,
                use_smart_camera=True,
                notify_token=None,
            )

            state = pipeline_runner.get_state()
            assert state['status'] == 'done'
            # Sprawdź czy start został przesunięty z 0.0s na 6.9s!
            assert state['clip_start'] == 6.9
            assert state['clip_end'] == 28.2
            assert state['qa_status'] == 'PASS'
            assert state['qa_score'] == 94
            # Render_short musiał otrzymać nowe okno
            mock_render.assert_called_once()
            _, kwargs = mock_render.call_args
            assert kwargs['clip_start'] == 6.9
            assert kwargs['clip_end'] == 28.2

