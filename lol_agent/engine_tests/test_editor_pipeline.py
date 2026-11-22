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
    hook = kw.pop("hook_text", "TEST")
    E.render_short(src, 0.0, 15.0, action_type=action, champion_name="Katarina", peak_moment=peak_moment, peaks=peaks,
                   hook_text=hook, custom_temp_dir=TMP, **kw)
    return {d: c for d, c in CALLS}

def _music_ss(cmds):
    c = cmds["merge_music"]; return float(c[c.index("-ss") + 1])

def test_triple_kill_drop_lands_on_the_hit():
    peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 7.5)
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.0, 0.55, [2.5, 4.5])   # tak jak policzył to edytor (reżyser: teamfight)
    mapped = TL.warp_time(segs, 7.5)
    expected_drop = E.MUSIC_DROP_MAP["ncs_elektronomia_sky_high.mp3"]
    assert abs((_music_ss(cmds) + mapped) - expected_drop) < 0.01, (_music_ss(cmds), mapped)   # drop trafia w cios
    assert abs((_music_ss(cmds) + 7.5) - expected_drop) > 0.5                                  # stary wzór chybiał

def test_game_audio_is_warped_with_the_picture():
    cmds = _render("triple", [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")], 7.5)
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    assert "[gwarp]loudnorm" in fc and "asetrate=44100*0.550000" in fc and "asetrate=44100*0.700000" in fc
    assert "[1:a]loudnorm" not in fc, "Dynamic loudnorm na muzyce nie może spłaszczać dropu!"
    assert "+between(t," in fc, "Drop muzyki ma dostawać impuls wzmacniający na kulminacji!"

def test_kill_sound_boost_uses_output_time():
    peaks = [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 7.5)
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    segs = TL.build_speed_segments(15.0, 7.5, 0.55, 1.0, 0.55, [2.5, 4.5])
    t8 = TL.warp_time(segs, 8.0)
    assert f"(t-{t8:.2f})" in fc, (t8, fc[-450:])           # podbicie dźwięku gry przy killu z 8.0 s pada tam, gdzie kill w filmie
    assert "between(t,8.00," not in fc and "(t-8.00)" not in fc

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
    assert fc.count("asetrate=44100*0.700000") == 1   # tylko jedno scalone zwolnienie ciosu (0.70x)

def test_recipe_is_written_beside_the_short():
    import json
    _render("triple", [(3.0, "KILL"), (5.0, "DOUBLE KILL"), (8.0, "TRIPLE KILL")], 7.5)
    r = json.load(open(os.path.join(TMP, "lol_short_final.recipe.json"), encoding="utf-8"))
    assert r["applied"]["zoom_level"] <= TL.ZOOM_MAX and r["applied"]["slowmo_window"] <= TL.SLOWMO_WINDOW_MAX
    if r["director"]:                                                                  # reżyser dostępny: widać, o co prosił i ile zastosowano
        assert r["director"]["asked_zoom"] >= r["applied"]["zoom_level"]
    assert abs(r["music"]["music_start"] + r["peak_in_output"] - r["music"]["drop_time"]) < 0.01
    assert r["peak_in_output"] > r["peak_in_clip"] and len(r["time_segments"]) >= 5 and r["music"]["drop_verified"] is True

def _recipe_of():
    import json
    return json.load(open(os.path.join(TMP, "lol_short_final.recipe.json"), encoding="utf-8"))

def test_style_speed_ramp_flow_fast_forwards_between_kills():
    peaks = [(3.0, "KILL"), (13.0, "DOUBLE KILL")]
    _render("double", peaks, 13.0)
    base = _recipe_of()
    cmds = _render("double", peaks, 13.0, montage_style="SPEED_RAMP_FLOW")
    r = _recipe_of()
    expected_drop = E.MUSIC_DROP_MAP["ncs_elektronomia_sky_high.mp3"]
    assert base["montage_style"] == "PRIMARY" and r["montage_style"] == "SPEED_RAMP_FLOW"
    assert any(s["speed"] > 2.0 for s in r["time_segments"]) and not any(s["speed"] > 1.0 for s in base["time_segments"])
    assert r["final_seconds"] < base["final_seconds"] - 3.0
    assert abs(_music_ss(cmds) + r["peak_in_output"] - expected_drop) < 0.01              # drop nadal na ciosie, na NOWEJ osi czasu
    assert "atempo=3.0000" in " ".join(cmds["merge_music"])                             # dźwięk gry przyspiesza razem z obrazem

def test_style_in_media_res_moves_the_start():
    peaks = [(9.0, "KILL"), (12.0, "DOUBLE KILL")]
    _render("double", peaks, 12.0)
    base = _recipe_of()
    _render("double", peaks, 12.0, montage_style="IN_MEDIA_RES")
    r = _recipe_of()
    assert abs(r["peaks_in_clip"][0][0] - 2.5) < 0.05 and abs(base["peaks_in_clip"][0][0] - 9.0) < 0.05
    assert abs(r["clip_seconds_in"] - (base["clip_seconds_in"] - 6.5)) < 0.05
    assert abs(r["peak_in_clip"] - (base["peak_in_clip"] - 6.5)) < 0.05                  # cios przesunięty razem z początkiem


def test_clean_slowmo_audio_avoids_wsola_and_uses_limiter():
    cmds = _render("double", [(3.0, "KILL"), (8.0, "DOUBLE KILL")], 8.0)
    mm_cmd = " ".join(str(x) for x in cmds["merge_music"])
    assert "asetrate=44100*" in mm_cmd
    assert "atempo=0.55" not in mm_cmd and "atempo=0.70" not in mm_cmd
    assert "alimiter=limit=" in mm_cmd


def test_youtube_save_credentials_preserves_live_rab_manager(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials
    import lol_agent.api.youtube_uploader as yu

    tok_file = tmp_path / "lol_token.pickle"
    monkeypatch.setattr(yu, "_get_yt_token_path", lambda: tok_file)
    creds = Credentials(token="tok", refresh_token="ref", token_uri="https://oauth2.googleapis.com/token", client_id="cid", client_secret="sec")
    had_rab_before = hasattr(creds, "_rab_manager")
    yu._save_credentials(creds)
    # Żywy obiekt w pamięci musi zachować _rab_manager przed wywołaniem build(...)
    assert hasattr(creds, "_rab_manager") == had_rab_before
    headers = {}
    creds.apply(headers)
    assert headers.get("authorization") == "Bearer tok"
    # Po odczycie z dysku _rab_manager nadal istnieje
    loaded = yu._load_credentials()
    assert loaded is not None and hasattr(loaded, "_rab_manager")
    headers2 = {}
    loaded.apply(headers2)
    assert headers2.get("authorization") == "Bearer tok"


def test_responsive_hook_and_centered_kill_overlays():
    cmds = _render(
        "quadrakill",
        [(3.0, "KILL"), (6.0, "QUADRAKILL")],
        6.0,
        hook_text="QUADRAKILL - ONE MORE LEFT TO WIN",
    )
    vf = cmds["apply_overlays_unified GPU"][cmds["apply_overlays_unified GPU"].index("-vf") + 1]
    mm = " ".join(str(x) for x in cmds["merge_music"])
    assert "-shortest" in mm
    assert "y=h*0.175" in vf
    assert "y=h*0.235" in vf
    assert "y=(h*0.54)" not in vf
    assert "box=1:boxcolor=black@0.44:boxborderw=14" in vf
    assert "fontsize=95" not in vf
    # Hook przy t=0.0 nie może mieć fade-in (musi być widoczny w pełni już od 1. klatki)
    assert "alpha='if(gt(t\\," in vf
    hook_boxes = re.findall(r"drawbox=x=trunc\(\(iw-(\d+)\)/2\):y=150", vf)
    assert hook_boxes and int(hook_boxes[0]) <= 980
    cta_boxes = re.findall(r"drawbox=x=trunc\(\(iw-(\d+)\)/2\):y=1380", vf)
    assert cta_boxes and int(cta_boxes[0]) <= 940


def test_hud_kill_counter_consistent_with_banner_tier():
    # Gdy 1. kill był zdominowany/pominięty, a w klipie wykryto DOUBLE KILL + TRIPLE KILL -> HUD pokazuje 2/3 i FINAL KILL 3/3
    cmds = _render(
        "triple",
        [(3.5, "DOUBLE KILL"), (7.5, "TRIPLE KILL")],
        7.5,
        hook_text="3 KILLS IN 4.0S",
    )
    vf = cmds["apply_overlays_unified GPU"][cmds["apply_overlays_unified GPU"].index("-vf") + 1]
    assert "text='KILL 2/3'" in vf
    assert "text='FINAL KILL 3/3'" in vf
    assert "FINAL KILL 2/2" not in vf


def test_beat_detector_finds_real_bass_drops_and_ignores_legacy_cache(tmp_path):
    import json
    import lol_beat_detector as BD

    if not BD.LIBROSA_OK:
        return
    music_dir = os.path.join(os.path.dirname(BD.__file__), "lol_music")
    old_cache = BD.BEAT_CACHE_PATH
    try:
        cache_p = tmp_path / "beat_cache.json"
        # Stary format v1 z zafałszowanymi dropami (34.53, 134.77) ma zostać zignorowany
        cache_p.write_text(json.dumps({"ncs_alan_walker_fade.mp3": 34.53, "ncs_robin_hustin_light_it_up.mp3": 134.77}), encoding="utf-8")
        BD.BEAT_CACHE_PATH = str(cache_p)

        fade_p = os.path.join(music_dir, "ncs_alan_walker_fade.mp3")
        euph_p = os.path.join(music_dir, "ncs_alex_skrindo_euphoria.mp3")
        light_p = os.path.join(music_dir, "ncs_robin_hustin_light_it_up.mp3")
        if os.path.exists(fade_p):
            d_fade = BD.detect_beat_drop(fade_p)
            assert 74.0 <= d_fade <= 77.2, f"fade drop unexpected: {d_fade}"
        if os.path.exists(euph_p):
            d_euph = BD.detect_beat_drop(euph_p)
            assert 45.0 <= d_euph <= 48.0, f"euphoria drop unexpected: {d_euph}"
        if os.path.exists(light_p):
            d_light = BD.detect_beat_drop(light_p)
            assert 51.0 <= d_light <= 54.0, f"light_it_up drop unexpected: {d_light}"
    finally:
        BD.BEAT_CACHE_PATH = old_cache


def test_drop_anchor_first_kill_engage_and_highpass_audio(tmp_path):
    import json
    import lol_beat_detector as BD

    peaks = [(4.2, "OUTPLAY"), (8.7, "DOUBLE KILL"), (14.7, "TRIPLE KILL")]
    cmds = _render("triple", peaks, 14.3, drop_anchor="first_kill_engage")
    r = _recipe_of()
    fc = cmds["merge_music"][cmds["merge_music"].index("-filter_complex") + 1]
    assert "[gwarp]loudnorm=I=-16:TP=-2.0:LRA=11,highpass=f=130," in fc
    assert r["drop_anchor"] == "first_kill_engage"
    assert abs(r["peak_in_clip"] - 3.85) < 0.05

    if BD.LIBROSA_OK:
        music_dir = os.path.join(os.path.dirname(BD.__file__), "lol_music")
        super_p = os.path.join(music_dir, "ncs_unknown_brain_superhero.mp3")
        if os.path.exists(super_p):
            old_cache = BD.BEAT_CACHE_PATH
            try:
                BD.BEAT_CACHE_PATH = str(tmp_path / "beat_prof_cache.json")
                prof = BD.get_track_beat_profile(super_p)
                assert 76.0 <= prof["drop_time"] <= 80.5
                assert 70.0 <= prof["bpm"] <= 200.0
                assert len(prof["beat_times"]) >= 8
            finally:
                BD.BEAT_CACHE_PATH = old_cache
