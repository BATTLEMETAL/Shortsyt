"""Reguły (engine_rules.json) muszą zgadzać się z kodem. To jest bezpiecznik na 'trzy zmiany później poprawka zniknęła'."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
RULES = json.load(open(os.path.join(ROOT, "engine_rules.json"), encoding="utf-8"))

def test_edit_limits_match_timeline():
    import lol_timeline as TL
    L = RULES["edit_limits"]
    assert (TL.ZOOM_MAX, TL.ZOOM_WINDOW_MAX, TL.SLOWMO_WINDOW_MAX) == (L["zoom_max"], L["zoom_window_max"], L["slowmo_window_max"])
    assert (TL.MINI_SLOWMO_SPEED, TL.MINI_SLOWMO_LEAD, TL.MINI_SLOWMO_WINDOW, TL.EASE_MAX) == (L["mini_slowmo_speed"], L["mini_slowmo_lead"], L["mini_slowmo_window"], L["ease_max"])
    assert TL.vertical_crop_width(RULES["frame"]["source"][1]) == RULES["frame"]["crop_width"]

def test_learning_thresholds_match():
    src = open(os.path.join(ROOT, "learning_engine.py"), encoding="utf-8").read()
    import re
    def const(name): return float(re.search(rf"^{name}\s*=\s*([0-9.]+)", src, re.M).group(1))
    L = RULES["learning"]
    for name, key in (("MIN_SAMPLE_FOR_WEIGHT", "min_sample_for_weight"), ("MIN_SAMPLE_FOR_BUCKET", "min_sample_for_bucket"), ("MIN_SAMPLE_FOR_SLOT", "min_sample_for_slot"),
                      ("MIN_SAMPLE_FOR_KEYWORD", "min_sample_for_keyword"), ("MIN_SAMPLE_FOR_STRUCTURE", "min_sample_for_structure"), ("MIN_LEAD_TO_WIN", "min_lead_to_win"),
                      ("SHRINK_K", "shrink_k"), ("ZERO_VIEWS_THRESHOLD", "zero_views_threshold")):
        assert const(name) == float(L[key]), name

def test_camera_constants_match():
    src = open(os.path.join(ROOT, "smart_camera.py"), encoding="utf-8").read()
    import re
    block = src[src.index("CAMERA = {"): src.index("}", src.index("CAMERA = {"))]
    code = {m.group(1): float(m.group(2)) for m in re.finditer(r'"(\w+)":\s*([0-9.]+)', block)}
    want = {k: float(v) for k, v in RULES["camera"].items() if k != "doc"}
    assert code == want, {k: (code.get(k), want.get(k)) for k in set(code) | set(want) if code.get(k) != want.get(k)}

def test_no_copy_trim_after_render():
    """AWARIA 6: po renderze nie wolno docinać przez -c copy (zamrożony początek, ucięty frag)."""
    src = open(os.path.join(ROOT, "lol_editor.py"), encoding="utf-8").read()
    body = src[src.index("def render_short("):]
    after_overlays = body[body.index("apply_overlays_unified("):]
    assert '"-c", "copy"' not in after_overlays and "'-c', 'copy'" not in after_overlays
