"""
tests/test_quality_validator.py
===============================
Kompleksowe testy jednostkowe dla lol_quality_validator.py:
- Weryfikacja segmentów montażu (długość, gęstość akcji, martwy bieg)
- Realistyczna ocena jakości (eliminacja ślepego 100% z automatu)
- Bramki jakościowe: odrzucanie montażu gdy akcja jest poza pionowym oknem 9:16
- Weryfikacja wyrenderowanego wideo (Post-Flight QA)
"""

import pytest
import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lol_agent"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lol_quality_validator import (
    ValidationResult,
    validate_pre_flight,
    validate_montage_segments,
    validate_rendered_short,
    _check_enemy_combat_in_frame,
    _check_player_in_frame,
    _check_combat_in_frame,
)


def _create_synthetic_video(
    filepath: str,
    duration: float = 4.0,
    fps: float = 10.0,
    width: int = 1280,
    height: int = 720,
    draw_combat_at: list = None,
    combat_x: int = 640,
    combat_y: int = 360,
    is_player: bool = True,
    is_enemy: bool = True,
):
    """Pomocniczy generator krótkiego pliku wideo do testów audytora jakości."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
    total_frames = int(duration * fps)

    draw_combat_at = draw_combat_at or []

    for i in range(total_frames):
        t = i / fps
        bg_val = 35 + (i % 7)  # dynamiczna zmiana tła symulująca klatki w grze
        frame = np.full((height, width, 3), bg_val, dtype=np.uint8)

        should_draw = any(abs(t - ct) <= 0.4 for ct in draw_combat_at)
        if should_draw:
            if is_enemy:
                # Czerwony pasek HP wroga: BGR = [30, 20, 220]
                cv2.rectangle(frame, (combat_x, combat_y), (combat_x + 90, combat_y + 14), (30, 20, 220), -1)
            if is_player:
                # Złoty pasek HP gracza: BGR = [30, 190, 225]
                cv2.rectangle(frame, (combat_x - 10, combat_y + 25), (combat_x + 80, combat_y + 39), (30, 190, 225), -1)

        out.write(frame)

    out.release()


class TestQualityValidator:
    def test_validation_result_defaults(self):
        """ValidationResult dataclass powinien poprawnie inicjalizować domyślne parametry."""
        res = ValidationResult(
            passed=True,
            adjusted_trim_start=10.0,
            adjusted_trim_end=25.0,
        )
        assert res.passed is True
        assert res.adjusted_trim_start == 10.0
        assert res.adjusted_trim_end == 25.0
        assert res.qa_status == "PASS"
        assert res.qa_score == 95
        assert res.rejection_code is None
        assert res.hook_score == 100
        assert res.visibility_score == 100
        assert res.density_score == 100
        assert res.pacing_score == 100

    def test_missing_video_fails_validation_gracefully(self):
        """Brakujący plik wideo powinien być czysto odrzucony z kodem FILE_ERROR."""
        result = validate_pre_flight(
            video_path="non_existent_clip_12345.mp4",
            trim_start=0.0,
            trim_end=15.0,
            peaks=[(5.0, "kill")],
        )
        assert result.passed is False
        assert result.rejection_code == "FILE_ERROR"
        assert result.qa_status == "FAIL"
        assert result.qa_score == 0

    def test_blank_frame_has_no_combat_detected(self):
        """Pusta/czarna klatka nie powinna wykrywać żadnych pikseli walki."""
        blank_bgr = np.zeros((720, 1280, 3), dtype=np.uint8)
        is_combat, enemy_pixels, centroid = _check_enemy_combat_in_frame(blank_bgr)
        assert is_combat is False
        assert enemy_pixels == 0
        assert centroid is None

    def test_enemy_hp_bar_detection(self):
        """Syntetyczny czerwony pasek HP wroga powinien być precyzyjnie wykryty."""
        frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
        # Narysuj czerwony pasek na pozycji (600, 300)
        cv2.rectangle(frame, (600, 300), (690, 314), (30, 20, 220), -1)
        is_combat, pixels, centroid = _check_enemy_combat_in_frame(frame)
        assert is_combat is True
        assert pixels > 60
        assert centroid is not None
        assert 590 <= centroid[0] <= 700
        assert 290 <= centroid[1] <= 325

    def test_player_hp_bar_detection(self):
        """Syntetyczny złoty pasek HP gracza powinien być precyzyjnie wykryty."""
        frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
        # Narysuj złoty pasek na pozycji (500, 400)
        cv2.rectangle(frame, (500, 400), (590, 414), (30, 190, 225), -1)
        is_player, pixels, centroid = _check_player_in_frame(frame)
        assert is_player is True
        assert pixels > 40
        assert centroid is not None
        assert 490 <= centroid[0] <= 600

    def test_combined_combat_in_frame(self):
        """Funkcja _check_combat_in_frame powinna wykryć walkę zarówno przy wrogu jak i graczu."""
        frame = np.full((720, 1280, 3), 30, dtype=np.uint8)
        cv2.rectangle(frame, (600, 300), (690, 314), (30, 20, 220), -1)  # wrog
        cv2.rectangle(frame, (500, 400), (590, 414), (30, 190, 225), -1)  # gracz
        has_action, pixels, centroid = _check_combat_in_frame(frame)
        assert has_action is True
        assert pixels > 100
        assert centroid is not None

    def test_weak_montage_fails_and_scores_low(self, tmp_path):
        """
        Kluczowy test: Słaby montaż, w którym akcja/kill jest poza kadrem (np. x=1150 przy kadrze na środku)
        oraz z długim martwym biegiem NIE MOŻE mieć 100% z automatu!
        Powinien otrzymać niską ocenę (< 60) oraz status FAIL lub WARN.
        """
        video_file = str(tmp_path / "weak_montage.mp4")
        # Kill na x=1150 (prawy skraj ekranu, kadr 9:16 na środku to 336-944)
        _create_synthetic_video(
            filepath=video_file,
            duration=5.0,
            draw_combat_at=[3.5],
            combat_x=1150,
            combat_y=360,
        )

        res = validate_pre_flight(
            video_path=video_file,
            trim_start=0.0,
            trim_end=5.0,
            peaks=[(3.5, "KILL")],
        )

        # Montaż bez widocznego killa w kadrze 9:16 NIE MOŻE być 100% ani PASS!
        assert res.qa_score < 60, f"Oczekiwano qa_score < 60 dla słabego montażu, otrzymano {res.qa_score}"
        assert res.passed is False, "Słaby montaż z uciętym killem nie powinien przejść walidacji!"
        assert res.qa_status == "FAIL"
        assert res.rejection_code in ("NO_KILLS_VISIBLE", "POOR_MONTAGE_QUALITY")
        assert res.visibility_score < 50

    def test_action_centered_in_crop_scores_high(self, tmp_path):
        """
        Poprawny montaż: akcja na środku kadru (x=640), szybki hook (1.5s), wysoka dynamika.
        Powinien uzyskać wysoką ocenę (>= 80) i status PASS.
        """
        video_file = str(tmp_path / "good_montage.mp4")
        _create_synthetic_video(
            filepath=video_file,
            duration=5.0,
            draw_combat_at=[1.5, 2.5, 3.5],
            combat_x=640,
            combat_y=360,
        )

        res = validate_pre_flight(
            video_path=video_file,
            trim_start=0.0,
            trim_end=5.0,
            peaks=[(1.5, "DOUBLE KILL"), (3.5, "TRIPLE KILL")],
        )

        assert res.passed is True
        assert res.qa_status in ("PASS", "WARN")
        assert res.qa_score >= 70, f"Oczekiwano qa_score >= 70, otrzymano {res.qa_score}"
        assert res.kills_visible >= 1
        assert res.hook_score >= 80

    def test_montage_segment_verification(self, tmp_path):
        """Weryfikacja segmentów montażu powinna wykrywać mikrosegmenty oraz martwy bieg."""
        video_file = str(tmp_path / "segments_test.mp4")
        _create_synthetic_video(
            filepath=video_file,
            duration=6.0,
            draw_combat_at=[3.0],
            combat_x=640,
        )

        # Segment 1 jest za krótki (0.5s < 1.0s)
        # Segment 2 jest martwy (brak walki)
        # Segment 3 ma akcję
        segments = [(0.0, 0.5), (0.5, 2.2), (2.2, 5.0)]
        seg_res = validate_montage_segments(
            video_path=video_file,
            segments=segments,
            peaks=[(3.0, "KILL")],
        )

        assert len(seg_res["segments"]) == 3
        # Diagnoza powinna odnotować zbyt krótki segment
        assert any("Zbyt krótki" in d for d in seg_res["diagnostic_details"])
        # Composite score nie jest ślepym 100
        assert seg_res["composite_score"] <= 85

    def test_validate_rendered_short_missing_file(self):
        """Post-Flight walidacja wyrenderowanego pliku powinna wykryć brak pliku."""
        res = validate_rendered_short("non_existent_rendered.mp4")
        assert res.passed is False
        assert res.rejection_code == "FILE_MISSING"
        assert res.qa_status == "FAIL"
        assert res.qa_score == 0

    def test_validate_rendered_short_valid_vertical(self, tmp_path):
        """Post-Flight walidacja powinna zatwierdzić poprawny plik wideo 1080x1920 (9:16)."""
        video_file = str(tmp_path / "short_render.mp4")
        # Utwórz pionowe wideo 1080x1920 (9:16)
        _create_synthetic_video(
            filepath=video_file,
            duration=3.0,
            width=540,
            height=960,  # 9:16 aspect ratio
            draw_combat_at=[1.0, 2.0],
            combat_x=270,
            combat_y=480,
        )

        res = validate_rendered_short(
            rendered_path=video_file,
            peaks=[(1.0, "KILL")],
        )

        assert res.passed is True
        assert res.qa_status in ("PASS", "WARN")
        assert res.qa_score >= 70

    def test_validate_rendered_short_black_frames_penalty(self, tmp_path):
        """Wykrycie czarnych klatek w wyrenderowanym wideo powinno drastycznie obniżyć ocenę."""
        video_file = str(tmp_path / "black_video.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_file, fourcc, 10.0, (540, 960))
        # 30 całkowicie czarnych klatek
        for _ in range(30):
            out.write(np.zeros((960, 540, 3), dtype=np.uint8))
        out.release()

        res = validate_rendered_short(rendered_path=video_file, peaks=[(1.0, "KILL")])
        assert res.qa_score < 60, f"Oczekiwano qa_score < 60 dla czarnego wideo, otrzymano {res.qa_score}"
        assert any("czarnych klatek" in d for d in res.diagnostic_details)

    def test_pre_flight_no_jump_cut_on_short_multikill(self, tmp_path):
        """Krótki multikill (<=26s) nie powinien być krojony na mikro-segmenty jump-cut."""
        video_file = str(tmp_path / "multikill_continuous.mp4")
        _create_synthetic_video(
            filepath=video_file,
            duration=12.0,
            draw_combat_at=[3.0, 5.0, 7.0, 9.0],
            combat_x=640,
            combat_y=360,
        )

        peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (7.0, "TRIPLE KILL")]
        res = validate_pre_flight(
            video_path=video_file,
            trim_start=0.0,
            trim_end=10.0,
            peaks=peaks,
            action_type="triple",
            tuning_profile={"allow_jump_cut": False, "buildup_sec": 0.6, "outro_sec": 1.4},
        )

        assert res.qa_status in ("PASS", "WARN")
        assert res.suggested_combat_segments is None, "Krótki multikill (<=26s) nie może być dzielony na jump-cuty!"
        assert res.adjusted_trim_end >= 7.0

