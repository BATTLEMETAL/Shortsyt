"""
Unit and integration tests for lol_agent.autonomous.watcher and evaluator.
Covers game process detection, file readiness checks, history persistence,
action qualification, duplicate gameplay checks, and evaluator heuristics.
"""
import os
import json
import pytest
from unittest.mock import MagicMock, patch
from lol_agent.autonomous.watcher import (
    is_game_running,
    is_file_ready,
    load_history,
    save_history,
    process_new_clip,
)
from lol_agent.autonomous.evaluator import (
    _get_evaluator_cfg,
    evaluate_clip_quality,
    KILL_WEIGHTS,
)


class TestWatcherGameDetection:
    """Tests for League of Legends game process detection."""

    def test_is_game_running_true_when_process_found(self, monkeypatch):
        mock_output = "League of Legends.exe   14520 Console   1   1,250,000 K"
        monkeypatch.setattr(
            "subprocess.check_output",
            lambda *args, **kwargs: mock_output
        )
        assert is_game_running() is True

    def test_is_game_running_false_when_process_not_found(self, monkeypatch):
        mock_output = "chrome.exe   8920 Console   1   120,000 K"
        monkeypatch.setattr(
            "subprocess.check_output",
            lambda *args, **kwargs: mock_output
        )
        assert is_game_running() is False

    def test_is_game_running_handles_exceptions_gracefully(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise OSError("Command not found (e.g. Linux environment)")
        monkeypatch.setattr("subprocess.check_output", _raise)
        assert is_game_running() is False


class TestWatcherFileReadiness:
    """Tests for checking if Outplayed video recording is complete and safe to process."""

    def test_file_does_not_exist(self, tmp_path):
        fake_path = str(tmp_path / "nonexistent.mp4")
        assert is_file_ready(fake_path, wait_seconds=0) is False

    def test_file_too_small_under_1mb(self, tmp_path):
        small_file = tmp_path / "small.mp4"
        small_file.write_bytes(b"A" * (512 * 1024))  # 512 KB < 1MB
        assert is_file_ready(str(small_file), wait_seconds=0) is False

    def test_file_ready_when_size_stable_and_unlocked(self, tmp_path, monkeypatch):
        test_file = tmp_path / "ready.mp4"
        test_file.write_bytes(b"B" * (1024 * 1024 + 100))  # > 1MB
        # Avoid real sleep in tests
        monkeypatch.setattr("time.sleep", lambda s: None)
        assert is_file_ready(str(test_file), wait_seconds=0) is True


class TestWatcherHistory:
    """Tests for watcher history serialization and persistence."""

    def test_load_history_empty_when_missing(self, tmp_path, monkeypatch):
        fake_file = str(tmp_path / "missing_history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", fake_file)
        assert load_history() == {}

    def test_save_and_load_history_roundtrip(self, tmp_path, monkeypatch):
        hist_file = str(tmp_path / "test_history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)

        data = {
            "hash_123": {
                "score": 85.5,
                "tier": "S_TIER",
                "status": "RENDERED_SUCCESS"
            }
        }
        save_history(data)
        loaded = load_history()
        assert loaded == data

    def test_load_history_handles_corrupt_json(self, tmp_path, monkeypatch):
        corrupt_file = tmp_path / "corrupt_history.json"
        corrupt_file.write_text("{invalid json", encoding="utf-8")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", str(corrupt_file))
        assert load_history() == {}


class TestWatcherClipProcessing:
    """Tests for evaluating, deduplicating, and queuing clips for rendering."""

    def test_process_new_clip_skips_already_evaluated(self, tmp_path, monkeypatch):
        clip_file = tmp_path / "already_done.mp4"
        clip_file.write_bytes(b"video_bytes")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: "known_hash")

        save_history({"known_hash": {"status": "EVALUATED"}})

        mock_eval = MagicMock()
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", mock_eval)

        process_new_clip(str(clip_file))
        mock_eval.assert_not_called()

    def test_process_new_clip_records_rejection_for_low_score(self, tmp_path, monkeypatch):
        clip_file = tmp_path / "low_score.mp4"
        clip_file.write_bytes(b"low_score_video")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: "low_hash")

        mock_eval = {
            "score": 45.0,
            "tier": "REJECT",
            "worthy": False,
            "highest_kill": "NONE",
            "kills_count": 0
        }
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", lambda p: mock_eval)

        process_new_clip(str(clip_file))
        hist = load_history()
        assert "low_hash" in hist
        assert hist["low_hash"]["status"] == "REJECTED_LOW_SCORE"

    def test_process_new_clip_detects_duplicate_gameplay(self, tmp_path, monkeypatch):
        clip_file = tmp_path / "duplicate.mp4"
        clip_file.write_bytes(b"duplicate_video")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: "dup_hash")

        mock_eval = {
            "score": 88.0,
            "tier": "S_TIER",
            "worthy": True,
            "highest_kill": "PENTAKILL",
            "kills_count": 5,
            "kills": [(10.0, "KILL"), (12.0, "DOUBLE KILL"), (14.0, "TRIPLE KILL"), (16.0, "QUADRAKILL"), (18.0, "PENTAKILL")]
        }
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", lambda p: mock_eval)
        monkeypatch.setattr("lol_agent.autonomous.watcher._is_duplicate_action", lambda fp, proc: (True, {"url": "https://youtu.be/old"}))

        process_new_clip(str(clip_file))
        hist = load_history()
        assert "dup_hash" in hist
        assert hist["dup_hash"]["status"] == "DUPLICATE_GAMEPLAY"

    def test_process_new_clip_qualifies_and_runs_pipeline(self, tmp_path, monkeypatch):
        clip_file = tmp_path / "worthy_penta.mp4"
        clip_file.write_bytes(b"penta_video")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: "penta_hash")

        mock_eval = {
            "score": 92.0,
            "tier": "S_TIER",
            "worthy": True,
            "highest_kill": "PENTAKILL",
            "kills_count": 5,
            "kills": [(5.0, "PENTAKILL")]
        }
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", lambda p: mock_eval)
        monkeypatch.setattr("lol_agent.autonomous.watcher._is_duplicate_action", lambda fp, proc: (False, {}))

        mock_run_pipeline = MagicMock()
        monkeypatch.setattr("lol_agent.autonomous.watcher.run_pipeline", mock_run_pipeline)

        process_new_clip(str(clip_file), auto_publish=False)

        mock_run_pipeline.assert_called_once_with(
            video_path=str(clip_file),
            action="pentakill",
            dry_run=True,
            force=False
        )
        hist = load_history()
        assert hist["penta_hash"]["status"] == "RENDERED_SUCCESS"

    def test_process_new_clip_pipeline_failure_records_error(self, tmp_path, monkeypatch):
        clip_file = tmp_path / "error_clip.mp4"
        clip_file.write_bytes(b"error_video")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: "err_hash")

        mock_eval = {
            "score": 80.0,
            "tier": "A_TIER",
            "worthy": True,
            "highest_kill": "QUADRAKILL",
            "kills_count": 4,
            "kills": []
        }
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", lambda p: mock_eval)
        monkeypatch.setattr("lol_agent.autonomous.watcher._is_duplicate_action", lambda fp, proc: (False, {}))

        def _boom(*args, **kwargs):
            raise RuntimeError("FFmpeg crashed out of memory")

        monkeypatch.setattr("lol_agent.autonomous.watcher.run_pipeline", _boom)

        process_new_clip(str(clip_file))
        hist = load_history()
        assert "err_hash" in hist
        assert "ERROR: FFmpeg crashed out of memory" in hist["err_hash"]["status"]

    @pytest.mark.parametrize("highest_kill,expected_action", [
        ("SOLO BOLO (1v1)", "solo_bolo"),
        ("1V1 DUEL", "solo_bolo"),
        ("QUADRAKILL", "quadrakill"),
        ("TRIPLE KILL", "triple"),
        ("DOUBLE KILL", "double"),
        ("CLEAN OUTPLAY", "outplay"),
    ])
    def test_process_new_clip_infers_action_types(self, tmp_path, monkeypatch, highest_kill, expected_action):
        clip_file = tmp_path / f"test_{expected_action}.mp4"
        clip_file.write_bytes(b"content")
        hist_file = str(tmp_path / "history.json")
        monkeypatch.setattr("lol_agent.autonomous.watcher.HISTORY_FILE", hist_file)
        monkeypatch.setattr("lol_agent.autonomous.watcher._clip_hash", lambda p: f"h_{expected_action}")

        mock_eval = {
            "score": 85.0,
            "tier": "A_TIER",
            "worthy": True,
            "highest_kill": highest_kill,
            "kills_count": 1,
            "kills": []
        }
        monkeypatch.setattr("lol_agent.autonomous.watcher.evaluate_clip_quality", lambda p: mock_eval)
        monkeypatch.setattr("lol_agent.autonomous.watcher._is_duplicate_action", lambda fp, proc: (False, {}))

        mock_pipeline = MagicMock()
        monkeypatch.setattr("lol_agent.autonomous.watcher.run_pipeline", mock_pipeline)

        process_new_clip(str(clip_file), auto_publish=False)
        mock_pipeline.assert_called_once_with(
            video_path=str(clip_file),
            action=expected_action,
            dry_run=True,
            force=False
        )


class TestEvaluatorHeuristics:
    """Tests for clutch and quality evaluation logic."""

    def test_get_evaluator_cfg_returns_expected_structure(self):
        cfg = _get_evaluator_cfg()
        assert "base_kill_weights" in cfg
        assert "s_tier_min" in cfg
        assert "a_tier_min" in cfg
        assert cfg["s_tier_min"] >= cfg["a_tier_min"]

    def test_evaluate_clip_quality_missing_file(self):
        res = evaluate_clip_quality("c:/nonexistent_eval_file.mp4")
        assert res["worthy"] is False
        assert res["score"] == 0
        assert "File not found" in res["error"]

    def test_evaluate_clip_quality_too_short(self, tmp_path, monkeypatch):
        short_file = tmp_path / "short.mp4"
        short_file.write_bytes(b"dummy")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 60.0  # 60 frames @ 30 fps = 2.0s

        monkeypatch.setattr("cv2.VideoCapture", lambda p: mock_cap)

        res = evaluate_clip_quality(str(short_file))
        assert res["worthy"] is False
        assert "Clip too short (<5s)" in res["error"]
        assert res["tier"] == "REJECT"

    def test_evaluate_clip_quality_penta_safety_floor(self, tmp_path, monkeypatch):
        video_file = tmp_path / "penta.mp4"
        video_file.write_bytes(b"dummy")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # 300 frames @ 30 fps = 10.0s
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 300.0

        monkeypatch.setattr("cv2.VideoCapture", lambda p: mock_cap)
        monkeypatch.setattr(
            "lol_agent.lol_momentum_analyzer._compute_kill_scores",
            lambda *args, **kwargs: ([], [(2.0, "KILL"), (4.0, "DOUBLE KILL"), (6.0, "TRIPLE KILL"), (8.0, "QUADRAKILL"), (9.0, "PENTAKILL")])
        )

        res = evaluate_clip_quality(str(video_file))
        assert res["worthy"] is True
        assert res["score"] >= 82.0
        assert res["tier"] == "S_TIER"
        assert res["action_type"] == "pentakill"

    def test_evaluate_clip_quality_player_died_few_kills_rejected(self, tmp_path, monkeypatch):
        video_file = tmp_path / "died_single.mp4"
        video_file.write_bytes(b"dummy")

        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # 300 frames @ 30 fps = 10.0s
        mock_cap.get.side_effect = lambda prop: 30.0 if prop == 5 else 300.0

        # Simulate player dead in trailing frames:
        # Mock frame reading: return grayscale / black frame (saturation = 0)
        import numpy as np
        black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, black_frame)

        monkeypatch.setattr("cv2.VideoCapture", lambda p: mock_cap)
        monkeypatch.setattr(
            "lol_agent.lol_momentum_analyzer._compute_kill_scores",
            lambda *args, **kwargs: ([], [(2.0, "KILL")])
        )

        res = evaluate_clip_quality(str(video_file))
        assert res["worthy"] is False
        assert res["tier"] == "REJECT"
        assert res["score"] == 0.0
