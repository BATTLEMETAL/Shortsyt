"""Kamera: czysta kinematyka (bez wideo). Pilnuje reguł z PROJECT_GUIDELINES: statyw, płynne doganianie, doskok, zamrożenie."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
if sys.version_info >= (3, 10):
    import smart_camera as SC
else:   # starszy Python nie zna zapisu "X | None": wczytaj to samo źródło z odroczonymi adnotacjami
    import types
    SC = types.ModuleType("smart_camera"); SC.__file__ = os.path.join(ROOT, "smart_camera.py")
    exec(compile("from __future__ import annotations\n" + open(os.path.join(ROOT, "smart_camera.py"), encoding="utf-8").read(), "smart_camera.py", "exec"), SC.__dict__)

def bar(x, y=500): return (x - 50, y - 6, 100, 12, 1200.0, float(x), float(y))   # (lewy, górny, szer., wys., ocena, środek x, środek y)
def run(xs, **kw): return [p[1] for p in SC.simulate_player_trajectory([([bar(x)] if x is not None else [], None) for x in xs], duration=len(xs) / 5.0, **kw)]

def test_standing_player_gives_a_still_frame():
    out = run([960] * 40)
    assert max(out) - min(out) == 0 and out[0] == 960 - 608 // 2

def test_jitter_inside_deadband_does_not_move():
    out = run([960 + (10 if i % 2 else -10) for i in range(40)])
    assert max(out) - min(out) <= 2

def test_walk_is_followed_smoothly():
    out = run([600 + i * 12 for i in range(50)])
    steps = [abs(b - a) for a, b in zip(out, out[1:])]
    assert max(steps) <= SC.CAMERA["max_pan_px"] and out[35] > out[5] + 200      # idzie za graczem, bez szarpnięć

def test_flash_snaps_at_once():
    out = run([500] * 20 + [1200] * 20)
    assert abs(out[20 + 3] - (1200 - 304)) <= 40                                 # po doskoku kadr jest na graczu w 3 próbki

def test_invisible_player_freezes():
    out = run([900] * 15 + [None] * 15 + [900] * 10)
    assert max(out[15:30]) - min(out[15:30]) <= 2                                # krzaki / stealth: żadnego dryfu

def test_frame_stays_inside_the_source():
    out = run([20] * 10 + [1900] * 10)
    assert min(out) >= 0 and max(out) <= 1920 - 608

def test_bar_mode_prescan():
    assert SC.detect_player_bar_mode(5000, 800) == "standard"      # złote efekty nie przejmą kamery
    assert SC.detect_player_bar_mode(100, 4000) == "colorblind"
    assert SC.detect_player_bar_mode(0, 0) == "standard"

def test_path_finder_runs_on_drawn_frames():
    """Cała ścieżka find_action_path (pre-skan koloru, maski, detekcja paska) na narysowanych klatkach: zielony pasek gracza
    idzie w prawo, a złoty błysk (efekt czaru) stoi z lewej. Kamera ma iść za zielonym."""
    import numpy as np
    frames = []
    for i in range(40):
        f = np.zeros((1080, 1920, 3), dtype=np.uint8) + 30
        x = 600 + i * 15
        f[500:512, x - 50:x + 50] = (66, 187, 39)        # zielony pasek gracza (#42bb27)
        f[380:440, 200:500] = (255, 215, 0)              # duży złoty efekt czaru: nie może przejąć kamery ani przełączyć trybu
        frames.append(f)
    SC.extract_sample_frames = lambda *a, **k: frames
    pts = SC.find_action_path("x.mp4", 0.0, 8.0, crop_w=608, n_samples=40)
    xs = [p[1] for p in pts]
    assert len(pts) == 40 and xs[30] > xs[2] + 250                 # kadr poszedł w prawo za graczem
    assert all(abs(x - (600 + i * 15 - 304)) < 140 for i, x in enumerate(xs[:34]))   # i trzyma gracza w kadrze (przed zamrożeniem końca)
