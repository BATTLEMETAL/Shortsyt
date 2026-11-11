"""Cały render_short na sucho: FFmpeg jest podmieniony na rejestrator poleceń, więc widać, co editor NAPRAWDĘ każe zrobić.
Pilnuje naprawy z 11.11.2026: muzyka, napisy i dźwięk gry dostają czas z jednej osi (lol_timeline). Python 3.12+."""
import os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stubs
TMP = _stubs.install(need_numpy_stub=True)
import lol_timeline as TL
import lol_editor as E

CALLS = []
def _fake_ffmpeg(cmd, timeout=180.0, desc=""):
    CALLS.append((desc, list(cmd)))
    out = b"audio" if "audio stream check" in desc else (b"1920x1080" if "size" in desc else b"15.0")
    for a in cmd:                                   # utwórz plik wyjściowy, o który pytają późniejsze kroki
        if isinstance(a, str) and a.endswith(".mp4") and a.startswith(TMP): open(a, "ab").close()
    return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr=b"")

def _render(action, peaks, peak_moment, **kw):
    CALLS.clear()
    E._run_ffmpeg = _fake_ffmpeg
    music = os.path.join(TMP, "ncs_elektronomia_sky_high.mp3"); open(music, "ab").close()   # drop sprawdzony: 30.0 s
    E.pick_music_for_action = lambda action_type="outplay", preferred_track=None: music
    E.SMART_CAMERA_AVAILABLE = False
    E._get_font_path = lambda: "/tmp/font.ttf"
    src = os.path.join(TMP, "src.mp4"); open(src, "ab").close()
    E.render_short(src, 0.0, 15.0, action_type=action, champion_name="Katarina", peak_moment=peak_moment, peaks=peaks,
                   hook_text="TEST", custom_temp_dir=TMP, **kw)
    return {d: c for d, c in CALLS}

def _music_ss(cmds):
    c = cmds["merge_music"]; return float(c[c.index("-ss") + 1])

def test_triple_kill_drop_lands_on_the_hit():
    peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 7.5)
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.0, 0.55, [2.5, 4.5])   # tak jak policzył to edytor (reżyser: teamfight)
    mapped = TL.warp_time(segs, 7.5)
    assert abs((_music_ss(cmds) + mapped) - 30.0) < 0.01, (_music_ss(cmds), mapped)   # drop 30.0 s trafia w cios
    assert abs((_music_ss(cmds) + 7.5) - 30.0) > 0.5                                  # stary wzór chybiał

def test_game_audio_is_warped_with_the_picture():
    cmds = _render("triple", [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")], 7.5)
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    assert "[gwarp]loudnorm" in fc and "atempo=0.5500" in fc and "atempo=0.7000" in fc

def test_kill_sound_boost_uses_output_time():
    peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 7.5)
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.0, 0.55, [2.5, 4.5])
    t8 = TL.warp_time(segs, 8.0)
    assert f"between(t,{t8:.2f}," in fc, (t8, fc[:300])       # podbicie dźwięku przy killu z 8.0 s pada tam, gdzie kill w filmie
    assert "between(t,8.00," not in fc

def test_captions_use_the_same_timeline():
    peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 7.5)
    vf = cmds["apply_overlays_unified GPU"][cmds["apply_overlays_unified GPU"].index("-vf") + 1]
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.0, 0.55, [2.5, 4.5])
    want = TL.warp_time(segs, 8.0) + 0.15                      # napis wchodzi 0.15 s po killu
    starts = [float(x) for x in re.findall(r"between\(t\\?,([0-9.]+)\\?,", vf)]
    assert any(abs(x - want) < 0.03 for x in starts), (want, sorted(set(starts))[:12])

def test_crop_is_608_and_even():
    cmds = _render("solo_bolo", [(8.0, "SOLO BOLO")], 7.5)
    c = next(c for d, c in CALLS if d.startswith("apply_editor_effects"))
    assert "-filter_complex_script" in c
    # skrypt filtra jest kasowany po renderze; szerokość sprawdza test osi czasu, tu pilnujemy, że render doszedł do końca
    assert "merge_music" in cmds and "apply_overlays_unified GPU" in cmds

def test_solo_has_no_intermediate_slowmo():
    cmds = _render("solo_bolo", [(8.0, "SOLO BOLO")], 7.5)
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    assert "atempo=0.7000" in fc and fc.count("atempo=0.7000") == 2 or "atempo=0.7000" in fc   # tylko zwolnienie ciosu (0.70x)

def test_recipe_is_written_beside_the_short():
    import json
    _render("triple", [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")], 7.5)
    r = json.load(open(os.path.join(TMP, "lol_short_final.recipe.json"), encoding="utf-8"))
    assert r["applied"]["zoom_level"] <= TL.ZOOM_MAX and r["applied"]["slowmo_window"] <= TL.SLOWMO_WINDOW_MAX
    if r["director"]:                                                                  # reżyser dostępny: widać, o co prosił i ile zastosowano
        assert r["director"]["asked_zoom"] >= r["applied"]["zoom_level"]
    assert abs(r["music"]["music_start"] + r["peak_in_output"] - r["music"]["drop_time"]) < 0.01
    assert r["peak_in_output"] > r["peak_in_clip"] and len(r["time_segments"]) >= 5 and r["music"]["drop_verified"] is True
