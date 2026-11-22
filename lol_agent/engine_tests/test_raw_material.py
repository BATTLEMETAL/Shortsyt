"""Bramka 0: surowy klip, który się nie nadaje, nie jest renderowany (lol_quality_validator.is_raw_material_viable)."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stubs; _stubs.install()
import lol_quality_validator as V
R = json.load(open(os.path.join(ROOT, "engine_rules.json"), encoding="utf-8"))["raw_material"]

def test_rules_match_code():
    assert (V.RAW_MIN_HEIGHT, V.RAW_MIN_FPS, V.RAW_MIN_TRACKING, V.RAW_MIN_COMBAT_SHARE) == (R["min_height"], R["min_fps"], R["min_tracking"], R["min_combat_share"])
    assert (V.RAW_COMBAT_BEFORE_KILL, V.RAW_COMBAT_AFTER_KILL, V.RAW_INSTANT_DEATH_SEC) == (R["combat_before_kill"], R["combat_after_kill"], R["instant_death_sec"])

def test_good_material_passes():
    ok, code, why = V.is_raw_material_viable([(103.0, "KILL"), (106.0, "DOUBLE KILL"), (110.0, "TRIPLE KILL")], 100.0, 115.0, (1920, 1080), 60, 0.9)
    assert ok and code is None and "3 kill" in why
    assert V.is_raw_material_viable([(7.5, "KILL")], 0.0, 12.0)[0]                       # czasy względne, reszta nieznana: nie zgaduje

def test_trash_is_rejected_with_a_code():
    k = [(105.0, "KILL")]
    assert V.is_raw_material_viable(k, 100.0, 115.0, (1280, 640))[1] == "TRASH_LOW_FIDELITY"
    assert V.is_raw_material_viable(k, 100.0, 115.0, (1920, 1080), 24)[1] == "TRASH_LOW_FIDELITY"
    assert V.is_raw_material_viable(k, 100.0, 115.0, (1920, 1080), 60, 0.5)[1] == "TRASH_UNFRAMEABLE"
    assert V.is_raw_material_viable([], 100.0, 115.0)[1] == "TRASH_NO_KILL"
    assert V.is_raw_material_viable([(300.0, "KILL")], 100.0, 115.0)[1] == "TRASH_NO_KILL"   # kill poza oknem
    assert V.is_raw_material_viable([(128.0, "KILL")], 100.0, 130.0)[1] == "TRASH_DEAD_AIR"  # 4 s walki na 30 s
    assert V.is_raw_material_viable(k, 100.0, 112.0, death_times=[5.9])[1] == "TRASH_INSTANT_DEATH"
    assert V.is_raw_material_viable(k + [(106.0, "YOU HAVE BEEN SLAIN")], 100.0, 112.0)[1] == "TRASH_INSTANT_DEATH"
    assert V.is_raw_material_viable(k + [(108.0, "DOUBLE KILL")], 100.0, 112.0, death_times=[8.5])[0]   # wymiana po multikillu zostaje
