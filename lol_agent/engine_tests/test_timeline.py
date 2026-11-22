"""Oś czasu: obraz, muzyka, napisy i dźwięk gry muszą liczyć czas tak samo. Uruchom: python tests/run_tests.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lol_timeline as TL

def approx(a, b, eps=1e-6): return abs(a - b) <= eps

def test_no_slowmo_is_identity():
    segs = TL.build_speed_segments(15.0, 7.5, slowmo_speed=1.0)
    assert approx(TL.output_duration(segs), 15.0)
    for t in (0.0, 3.3, 7.5, 14.9): assert approx(TL.warp_time(segs, t), t)

def test_segments_cover_clip_in_order():
    for peak in (0.3, 2.0, 7.5, 14.6):
        for inter in ([], [3.0, 5.0], [1.0]):
            segs = TL.build_speed_segments(15.0, peak, 0.55, 1.2, 0.55, inter)
            assert segs and segs[0]["start"] <= 0.0501   # gdy cios pada w pierwszych 0.3 s, edytor gubi najwyżej 0.05 s początku
            for a, b in zip(segs, segs[1:]):
                assert 0.0 <= b["start"] - a["end"] <= 0.0501, (peak, inter, a, b)   # nigdy nakładki, dziura najwyżej 0.05 s
            assert 15.0 - segs[-1]["end"] <= 0.0501
            assert all(0.5 <= s["speed"] <= 1.0 for s in segs)                        # zakres atempo

def test_triple_kill_peak_moves_later():
    """Sedno błędu beat-sync: przy killach pośrednich cios w gotowym filmie jest później niż w surowym klipie."""
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.2, 0.55, [3.0, 5.0])
    mapped = TL.warp_time(segs, 7.5)
    assert mapped > 7.5 + 0.7, mapped
    start, early = TL.music_start_for_drop(30.0, mapped)
    assert approx(start + mapped, 30.0, 1e-3) and early == 0.0     # drop trafia w cios
    old_start = 30.0 - 7.5                                         # tak liczył stary kod
    assert abs((old_start + mapped) - 30.0) > 0.7                  # i mylił się o ponad 0.7 s

def test_solo_peak_barely_moves():
    segs = TL.build_speed_segments(15.0, 7.5, 0.70, 0.55, 0.40, [])
    assert abs(TL.warp_time(segs, 7.5) - 7.5) < 0.2

def test_warp_is_monotonic_and_ends_at_duration():
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.2, 0.55, [3.0, 5.0])
    prev = -1.0
    for i in range(0, 1501):
        w = TL.warp_time(segs, i / 100.0); assert w >= prev - 1e-9; prev = w
    assert abs(TL.warp_time(segs, 15.0) - TL.output_duration(segs)) < 0.06

def test_drop_before_peak_is_reported():
    start, early = TL.music_start_for_drop(5.0, 8.3)
    assert start == 0.0 and approx(early, 3.3, 1e-3)

def test_limits_are_applied():
    eff = TL.effective_edit_values(1.25, 0.55, 1.6)
    assert eff == {"zoom_level": TL.ZOOM_MAX, "zoom_window": TL.ZOOM_WINDOW_MAX, "slowmo_window": TL.SLOWMO_WINDOW_MAX}

def test_audio_filter_matches_segments():
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.2, 0.55, [3.0])
    f = TL.audio_warp_filter(segs, "2:a", "gwarp")
    assert f.count("atrim=") == len(segs) and f.endswith(f"concat=n={len(segs)}:v=0:a=1[gwarp]")
    assert f.count("atempo=") == sum(1 for s in segs if s["speed"] != 1.0)


def test_clean_audio_warp_coalesces_and_avoids_wsola_on_slowmo():
    segs = TL.build_speed_segments(13.5, 10.8, 0.55, 1.0, 0.40, [5.2, 8.7])
    merged = TL.coalesce_audio_segments(segs)
    assert len(merged) < len(segs)  # dwa przyległe bloki 0.55 (zoom=True/False) muszą zostać scalone
    f = TL.audio_warp_filter(segs, "2:a", "gwarp", mode="clean")
    assert f.count("atrim=") == len(merged)
    assert f.endswith(f"concat=n={len(merged)}:v=0:a=1[gwarp]")
    assert "aresample=44100,aformat=sample_rates=44100:channel_layouts=stereo" in f
    assert "asetrate=44100*0.550000,aresample=44100" in f
    assert "atempo=" not in f  # brak artefaktów WSOLA na slowmo < 1.0
    assert "afade=t=in:st=0:d=0.005" in f


def test_clean_audio_warp_uses_atempo_only_on_speedups():
    segs = [
        {"start": 0.0, "end": 2.0, "speed": 1.0, "zoom": False},
        {"start": 2.0, "end": 5.0, "speed": 3.0, "zoom": False},
        {"start": 5.0, "end": 6.5, "speed": 0.55, "zoom": True},
    ]
    f = TL.audio_warp_filter(segs, "2:a", "gwarp", mode="clean")
    assert "atempo=3.0000" in f
    assert "asetrate=44100*0.550000" in f

def test_crop_width_is_even():
    assert TL.vertical_crop_width(1080) == 608 and TL.vertical_crop_width(1440) % 2 == 0 and TL.vertical_crop_width(2160) % 2 == 0
