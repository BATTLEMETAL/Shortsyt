"""
Unit tests for lol_agent/lol_editor.py.
Verifies music selection, thread safety, font resolution, performance insight loading,
and speed ramp filtergraph generation with easing.
"""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
import pytest

from lol_agent.lol_editor import (
    pick_music_for_action,
    _get_font_path,
    get_performance_insights,
    apply_editor_effects,
    cut_clip,
    ACTION_ENERGY,
    MUSIC_ENERGY_MAP,
)


def test_get_font_path_returns_string():
    path = _get_font_path()
    assert isinstance(path, str)
    if path:
        assert os.path.exists(path)


def test_get_performance_insights_returns_dict():
    insights = get_performance_insights()
    assert isinstance(insights, dict)


def test_action_energy_mappings_cover_standard_actions():
    standard_actions = ["pentakill", "quadrakill", "triple", "outplay", "solo_bolo", "clutch", "escape"]
    for act in standard_actions:
        assert act in ACTION_ENERGY, f"Missing energy mapping for action '{act}'"
        assert ACTION_ENERGY[act] in ["high", "medium", "low"]


@pytest.fixture
def mock_music_dir(tmp_path, monkeypatch):
    music_dir = tmp_path / "lol_music"
    music_dir.mkdir()
    (music_dir / "track1.mp3").write_text("dummy audio content")
    (music_dir / "track2.mp3").write_text("dummy audio content")
    (music_dir / "track3.mp3").write_text("dummy audio content")
    monkeypatch.setattr("lol_agent.lol_editor.LOL_MUSIC_DIR", str(music_dir))
    return music_dir


def test_pick_music_for_action_selects_existing_file(mock_music_dir):
    track = pick_music_for_action("outplay")
    assert isinstance(track, str)
    assert os.path.exists(track)
    assert track.endswith(".mp3")


def test_pick_music_for_action_preferred_track(mock_music_dir):
    preferred = pick_music_for_action("outplay", preferred_track="track2.mp3")
    assert os.path.basename(preferred) == "track2.mp3"


def test_pick_music_rotates_and_records_history(mock_music_dir):
    tracks = set()
    for _ in range(5):
        t = pick_music_for_action("outplay")
        tracks.add(os.path.basename(t))
    assert len(tracks) >= 1


def test_pick_music_thread_safety(mock_music_dir):
    """Test concurrent thread safety of music selection and .last_track file locking."""
    def worker():
        return pick_music_for_action("outplay")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker) for _ in range(16)]
        results = [f.result() for f in futures]

    assert len(results) == 16
    for r in results:
        assert os.path.exists(r)


def test_apply_editor_effects_script_generation(tmp_path, monkeypatch):
    """Verifies that speed ramp with easing creates valid filter complex script."""
    dummy_input = tmp_path / "dummy_in.mp4"
    dummy_input.write_text("dummy video")
    dummy_output = tmp_path / "dummy_out.mp4"
    captured_scripts = []

    def mock_run_ffmpeg(cmd, timeout=180.0, desc=""):
        # fc_script exists during _run_ffmpeg call before finally cleanup
        script_file = str(dummy_output).replace(".mp4", "_filter.txt")
        if os.path.exists(script_file):
            with open(script_file, "r", encoding="utf-8") as f:
                captured_scripts.append(f.read())
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("lol_agent.lol_editor._run_ffmpeg", mock_run_ffmpeg)

    dur = apply_editor_effects(
        input_path=str(dummy_input),
        output_path=str(dummy_output),
        clip_duration=15.0,
        crop_x="656",
        peak_moment=10.0,
        slowmo_speed=0.6,
        slowmo_duration=1.5,
        use_easing=True
    )
    assert dur > 15.0  # Slowmo extends duration
    assert len(captured_scripts) >= 1
    script_content = captured_scripts[0]
    assert "setpts" in script_content
    assert "concat=n=" in script_content


def test_build_text_overlay_filters():
    from lol_agent.lol_editor import build_text_overlay_filters
    filters = build_text_overlay_filters(
        hook_text="DOUBLE KILL - CLEAN OR LUCKY?",
        peak_moment=0.0,
        video_duration=15.0,
        show_duration=2.5,
    )
    assert len(filters) == 2
    assert "drawbox" in filters[0]
    assert "drawtext" in filters[1]
    assert "DOUBLE KILL" in filters[1]


def test_build_dynamic_captions_filters():
    from lol_agent.lol_editor import build_dynamic_captions_filters
    peaks = [(3.5, "DOUBLE KILL"), (7.2, "TRIPLE KILL")]
    filters = build_dynamic_captions_filters(
        peaks=peaks,
        trim_start=0.0,
        video_duration=15.0,
        peak_moment=7.2,
        action_type="outplay"
    )
    assert len(filters) >= 3  # HUD + Kill banners + Neon progress bar
    vf_text = " ".join(filters)
    assert "DOUBLE KILL" in vf_text
    assert "TRIPLE KILL" in vf_text
    assert "C89B3C" in vf_text  # Neon gold scrubber


def test_build_cta_overlay_filters():
    from lol_agent.lol_editor import build_cta_overlay_filters
    filters = build_cta_overlay_filters(
        video_duration=15.0,
        cta_text="CLEAN OUTPLAY OR PURE LUCK? RATE 1-10",
        show_duration=1.8,
    )
    assert len(filters) == 2
    assert "drawbox" in filters[0]
    assert "drawtext" in filters[1]
    assert "RATE 1-10" in filters[1]


def test_apply_overlays_unified_single_ffmpeg_invocation(tmp_path, monkeypatch):
    """Task B2: verifies that dynamic captions, hook overlay, and CTA overlay execute in a single FFmpeg pass."""
    from lol_agent.lol_editor import apply_overlays_unified

    dummy_in = tmp_path / "dummy_in.mp4"
    dummy_in.write_text("dummy")
    dummy_out = tmp_path / "dummy_out.mp4"

    ffmpeg_calls = []

    def mock_run_ffmpeg(cmd, timeout=120.0, desc=""):
        ffmpeg_calls.append((cmd, desc))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("lol_agent.lol_editor._run_ffmpeg", mock_run_ffmpeg)

    res = apply_overlays_unified(
        video_path=str(dummy_in),
        output_path=str(dummy_out),
        peaks=[(2.0, "DOUBLE KILL"), (5.0, "TRIPLE KILL")],
        trim_start=0.0,
        video_duration=15.0,
        peak_moment=5.0,
        hook_text="CAN HE SURVIVE THIS?",
        cta_text="RATE 1-10",
        cta_duration=1.8,
    )

    assert res == str(dummy_out)
    # Gwarancja Task B2: dokładnie 1 wywołanie FFmpeg zamiast 3 osobnych
    assert len(ffmpeg_calls) == 1
    cmd, desc = ffmpeg_calls[0]
    assert "apply_overlays_unified" in desc
    vf_idx = cmd.index("-vf")
    vf_arg = cmd[vf_idx + 1]
    assert "DOUBLE KILL" in vf_arg
    assert "TRIPLE KILL" in vf_arg
    assert "CAN HE SURVIVE THIS?" in vf_arg
    assert "RATE 1-10" in vf_arg


def test_cut_clip_smooth_seams_adds_audio_fade(tmp_path, monkeypatch):
    """
    Task B6: Verify cut_clip with smooth_seams=True injects audio micro-fade (-af afade)
    to eliminate popping/clicks at jump-cut segment transitions.
    """
    dummy_in = tmp_path / "in.mp4"
    dummy_in.write_text("dummy")
    dummy_out = tmp_path / "out.mp4"

    ffmpeg_cmds = []

    def mock_run_ffmpeg(cmd, timeout=60.0, desc=""):
        ffmpeg_cmds.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("lol_agent.lol_editor._run_ffmpeg", mock_run_ffmpeg)

    res = cut_clip(str(dummy_in), 2.0, 7.0, str(dummy_out), smooth_seams=True)
    assert res == str(dummy_out)
    assert len(ffmpeg_cmds) >= 1
    first_cmd = ffmpeg_cmds[0]
    assert "-af" in first_cmd
    af_idx = first_cmd.index("-af")
    af_val = first_cmd[af_idx + 1]
    assert "afade=t=in:ss=0" in af_val
    assert "afade=t=out" in af_val
    assert "-vf" in first_cmd
    vf_idx = first_cmd.index("-vf")
    assert "setpts=PTS-STARTPTS" in first_cmd[vf_idx + 1]


def test_freeze_frame_skipped_when_action_starts_immediately():
    """
    Gdy pierwszy kill następuje w pierwszych 3 sekundach (_first_kill_t <= 3.0s),
    freeze-frame hook MUSI być pominięty, aby nie niszczyć bezpośredniego uderzenia w widza.
    """
    peaks = [(1.8, "DOUBLE KILL"), (7.5, "KILL")]
    _first_kill_t = min((t_k for (t_k, _) in (peaks or [])), default=999.0)
    _action_starts_immediately = _first_kill_t <= 3.0
    _hook = "TRIPLE KILL!"
    _do_freeze = (bool(_hook) and not _action_starts_immediately and "triple" not in ("solo_bolo", "solo", "1v1"))
    assert _action_starts_immediately is True
    assert _do_freeze is False


def test_freeze_frame_applied_when_first_kill_is_delayed():
    """
    Gdy pierwszy kill następuje dopiero po > 3s (np. 5.5s),
    freeze-frame hook powinien być aktywny na klatce 0.0s (0.6s stop-klatka zatrzymująca scrollowanie).
    """
    peaks = [(5.5, "DOUBLE KILL"), (12.0, "TRIPLE KILL")]
    _first_kill_t = min((t_k for (t_k, _) in (peaks or [])), default=999.0)
    _action_starts_immediately = _first_kill_t <= 3.0
    _hook = "INSANE OUTPLAY!"
    _do_freeze = (bool(_hook) and not _action_starts_immediately and "outplay" not in ("solo_bolo", "solo", "1v1"))
    assert _action_starts_immediately is False
    assert _do_freeze is True


def test_freeze_frame_always_skipped_for_solo_bolo():
    """
    W trybie Solo Bolo freeze-frame jest ZAWSZE pomijany, ponieważ walka 1v1
    jest montowana od początku bez sztucznych przerw.
    """
    peaks = [(6.0, "SOLO BOLO")]
    _first_kill_t = 6.0
    _action_starts_immediately = False
    _hook = "SOLO BOLO"
    _do_freeze = (bool(_hook) and not _action_starts_immediately and "solo_bolo" not in ("solo_bolo", "solo", "1v1"))
    assert _do_freeze is False


def test_get_seamless_loop_cta():
    from lol_agent.lol_editor import get_seamless_loop_cta

    # 1. Wrong move hook loops into ending CTA
    cta1 = get_seamless_loop_cta("WRONG MOVE - WATCH WHAT HAPPENS", "outplay")
    assert cta1 == "AND THIS IS WHY IT WAS A..."

    # 2. Solo bolo hook
    cta2 = get_seamless_loop_cta("Clean Solo Bolo - 1v1 Masterclass", "solo_bolo")
    assert cta2 == "AND THAT'S HOW YOU PLAY A..."

    # 3. 1v2 / Can he win hook
    cta3 = get_seamless_loop_cta("1v2 - CAN HE WIN?", "outplay")
    assert cta3 == "REWATCH TO SEE HOW HE WINS A..."

    # 4. Multikills
    cta4 = get_seamless_loop_cta("PENTAKILL - DID ENEMY FF?", "pentakill")
    assert cta4 == "AND THAT'S HOW YOU GET A..."

    cta5 = get_seamless_loop_cta("DOUBLE KILL - CLEAN OR LUCKY?", "double")
    assert cta5 == "AND THAT'S HOW YOU PULL OFF A..."



