"""
Unit tests for AI Montage Director and Kill Anchor Lock.
"""
import pytest
from lol_agent.lol_montage_director import direct_clip_montage, MontageDirectorDecision
from lol_agent.smart_camera import simulate_player_trajectory


def test_montage_director_chaotic_teamfight_tight_burst():
    """Weryfikuje, że ciasny teamfight (Katarina triple kill, odstępy <=3.8s) ma zakaz jump-cut i kill-lock."""
    peaks = [(5.6, "KILL"), (8.6, "DOUBLE KILL"), (11.4, "TRIPLE KILL")]
    decision = direct_clip_montage(
        action_type="triple",
        champion_name="Katarina",
        duration=18.0,
        peaks=peaks
    )
    assert decision.archetype == "CHAOTIC_TEAMFIGHT"
    assert decision.allow_jump_cut is False
    assert decision.kill_lock_enabled is True
    assert decision.camera_mode == "tight_player"
    assert decision.buildup_sec <= 0.8
    assert decision.zoom_aggression >= 1.20


def test_montage_director_spaced_rampage_allows_jump_cut():
    """Weryfikuje, że multi-kill z długimi przerwami na bieg (>4.2s) włącza jump-cut."""
    peaks = [(4.0, "KILL"), (12.5, "DOUBLE KILL"), (21.0, "TRIPLE KILL")]
    decision = direct_clip_montage(
        action_type="triple",
        champion_name="Darius",
        duration=28.0,
        peaks=peaks
    )
    assert decision.archetype == "SPACED_RAMPAGE"
    assert decision.allow_jump_cut is True
    assert decision.kill_lock_enabled is True


def test_montage_director_solo_duel():
    """Weryfikuje, że Solo Bolo / 1v1 ma zakaz jump-cut i kinowe slow-mo."""
    peaks = [(10.0, "SOLO BOLO")]
    decision = direct_clip_montage(
        action_type="solo_bolo",
        champion_name="Zed",
        duration=15.0,
        peaks=peaks
    )
    assert decision.archetype == "SOLO_DUEL"
    assert decision.allow_jump_cut is False
    assert decision.camera_mode == "duel_centroid"
    assert 1.2 <= decision.slowmo_duration <= 1.8


def test_simulate_player_trajectory_kill_anchor_lock():
    """Weryfikuje, że Kill Anchor Lock bezwzględnie centruje kadr na graczu w oknie eliminacji."""
    duration = 10.0
    # 20 klatek (co 0.5s)
    # W klatce t=5.0s (indeks 10) następuje zabójstwo
    frames_data = []
    for i in range(20):
        # Gracz na x=1200, fałszywy wróg na x=300
        hp_bars = [(1180, 500, 40, 10, 500.0, 1200.0, 505.0)]
        enemy_cx = 300.0
        frames_data.append((hp_bars, enemy_cx))

    peaks = [(5.0, "DOUBLE KILL")]
    pts = simulate_player_trajectory(
        frames_data=frames_data,
        duration=duration,
        source_w=1920,
        source_h=1080,
        crop_w=608,
        peaks=peaks,
    )

    # W punkcie t=5.0s (indeks 10) gracz x=1200 powinien być idealnie w kadrze
    pt_at_kill = min(pts, key=lambda p: abs(p[0] - 5.0))
    crop_x = pt_at_kill[1]
    # Okno widoczne: [crop_x, crop_x + 608]
    # Środek okna powinien być bardzo bliski 1200px
    center_rendered = crop_x + 304
    assert abs(center_rendered - 1200.0) < 150.0  # Gracz w centrum, nie ściągnięty do wroga na 300px!
    assert crop_x <= 1200 <= crop_x + 608         # Gracz w 100% wewnątrz renderu 9:16
