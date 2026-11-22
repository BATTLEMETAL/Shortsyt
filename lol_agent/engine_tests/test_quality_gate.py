"""Bramka jakości i style zapasowe (OPUS_QUALITY_GATES_DIRECTIVE.md): short poniżej progu nigdy nie wychodzi z bramki
jako film do publikacji; dobry materiał dostaje ponowny montaż innym stylem. Bez FFmpeg: render i ocena są podstawione."""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import lol_timeline as TL
import lol_quality_gate as G
import lol_montage_director as D
RULES = json.load(open(os.path.join(ROOT, "engine_rules.json"), encoding="utf-8"))

def test_rules_match_code():
    f, g = RULES["timeline_fast_forward"], RULES["quality_gate"]
    assert (TL.FAST_FORWARD_SPEED, TL.FAST_GAP_MIN, TL.FAST_TAIL, TL.FAST_LEAD) == (f["speed"], f["gap_min"], f["tail"], f["lead"])
    assert all(G._DEFAULTS[k] == g[k] for k in G._DEFAULTS), [k for k in G._DEFAULTS if G._DEFAULTS[k] != g[k]]
    assert set(g["fallback"].values()) == set(D.FALLBACK_STYLES) == set(G._STYLE_ORDER)

def test_fast_forward_shortens_dead_time_only():
    base = TL.build_speed_segments(24.0, peak_moment=20.0, slowmo_speed=0.55, slowmo_duration=1.2, zoom_duration=0.55, intermediate_peaks=[5.5])
    fast = TL.apply_fast_forward(base, [6.0, 20.0])
    assert TL.output_duration(fast) < TL.output_duration(base) - 6.0                     # 14 s biegu: ok. 11 s krócej
    assert abs(sum(s["end"] - s["start"] for s in fast) - sum(s["end"] - s["start"] for s in base)) < 0.11   # nic nie wycięto
    assert [s for s in fast if s["speed"] < 1.0] == [s for s in base if s["speed"] < 1.0]   # zwolnienia nietknięte
    for k in (6.0, 20.0):                                                                # kille w normalnym tempie
        assert all(not (s["start"] <= k - 0.5 and k + 0.5 <= s["end"]) or s["speed"] <= 1.0 for s in fast)
        assert not any(s["speed"] > 1.0 and s["start"] < k + TL.FAST_TAIL - 0.01 and s["end"] > k - TL.FAST_LEAD + 0.01 for s in fast)
    assert TL.apply_fast_forward(base, [18.0, 20.0]) == base                             # krótka przerwa: bez zmian
    assert TL.warp_time(fast, 20.0) > TL.warp_time(fast, 6.0) > 0

def test_director_forced_styles():
    for st in D.FALLBACK_STYLES:
        d = D.direct_clip_montage("triple", "katarina", 30.0, [(5.0, "KILL"), (15.0, "DOUBLE KILL"), (25.0, "TRIPLE KILL")], force_style=st)
        assert d.archetype == st and d.allow_jump_cut is False and d.tuning_profile["archetype"] == st
    d = D.direct_clip_montage("triple", "katarina", 30.0, [(5.0, "KILL"), (15.0, "DOUBLE KILL"), (25.0, "TRIPLE KILL")])
    assert d.archetype == "SPACED_RAMPAGE"                                               # bez wymuszenia: jak dawniej

def _quality(score_parts):
    w = {"source_resolution": 0.15, "kill_coverage": 0.35, "beat_sync": 0.25, "first_frame": 0.15, "duration": 0.10}
    br = {k: {"score": float(v), "value": "", "weight": w[k]} for k, v in score_parts.items()}
    return {"score": sum(p["score"] * p["weight"] for p in br.values()), "pass": True, "breakdown": br, "issues": [],
            "kill_coverage_pct": score_parts["kill_coverage"], "beat_sync_error_seconds": 0.0}

def _recipe(drop=30.0, start=21.65, peak_out=8.35, verified=True, style="PRIMARY", step=40.0, kills=((3.0, "KILL"), (7.5, "TRIPLE KILL"))):
    return {"montage_style": style, "camera_peak_step_px": step, "peak_in_output": peak_out, "time_segments": [],
            "peaks_in_clip": [list(k) for k in kills],
            "music": {"track": "a.mp3", "drop_time": drop, "music_start": start, "peak_in_output": peak_out, "drop_verified": verified}}

def test_rescore_uses_measured_beat_error():
    old = _quality({"source_resolution": 100, "kill_coverage": 100, "beat_sync": 100, "first_frame": 70, "duration": 100})
    good = G.rescore(old, _recipe())
    assert good["pass"] and good["measured"]["beat_error_sec"] == 0.0 and good["codes"] == []
    # stary wzór dawał 100, a w filmie drop pada 2,4 s od ciosu
    bad = G.rescore(old, _recipe(start=19.25))
    assert bad["measured"]["beat_error_sec"] == 2.4 and bad["breakdown"]["beat_sync"]["score"] == 52.0 and bad["score"] < good["score"]
    unverified = G.rescore(old, _recipe(verified=False))
    assert unverified["breakdown"]["beat_sync"]["score"] <= 80.0                         # drop niesprawdzony uchem nie dostaje 100
    assert old["breakdown"]["beat_sync"]["score"] == 100.0                               # wejście nietknięte

def test_diagnosis_maps_to_styles():
    low = {"source_resolution": 100, "kill_coverage": 100, "beat_sync": 100, "first_frame": 20, "duration": 40}
    q = G.rescore(_quality(low), _recipe(start=17.0))                                    # drop 4,65 s od ciosu + słaba pierwsza klatka
    assert not q["pass"] and q["codes"][0] == "ERR_BEAT_SYNC" and "ERR_HOOK" in q["codes"]
    assert G.next_style(q["codes"], ["PRIMARY"], alt_tracks=["b.mp3"]) == "BEAT_REALIGN"
    assert G.next_style(q["codes"], ["PRIMARY"], alt_tracks=[]) == "IN_MEDIA_RES"        # brak drugiego utworu: następny styl
    q2 = G.rescore(_quality(dict(low, kill_coverage=50)), _recipe(step=120.0))
    assert "ERR_PACING" in q2["codes"] and "ERR_CAMERA" in q2["codes"]
    assert G.next_style(["ERR_UNDIAGNOSED"], ["PRIMARY", "SPEED_RAMP_FLOW", "IN_MEDIA_RES", "CINEMATIC_DUEL"], alt_tracks=[]) is None

def _run(scores, tracks=("a.mp3", "b.mp3")):
    tmp = tempfile.mkdtemp(prefix="flikcut_gate_"); video = os.path.join(tmp, "short.mp4"); renders = []
    def write(style="PRIMARY", track="a.mp3"):
        open(video, "wb").close()
        json.dump(_recipe(style=style) | {"music": dict(_recipe()["music"], track=track)}, open(os.path.join(tmp, "short.recipe.json"), "w"))
    def render(montage_style=None, preferred_track=None, **kw):
        renders.append(montage_style or ("BEAT_REALIGN:" + preferred_track)); write(montage_style or "PRIMARY", preferred_track or "a.mp3"); return video
    it = iter(scores)
    def score(rendered_path, beat_drop_time, music_file, **kw):
        assert beat_drop_time == 30.0 and music_file                                     # utwór i drop z przepisu, nie zgadywane
        s = next(it); return _quality({"source_resolution": 100, "kill_coverage": s, "beat_sync": 100, "first_frame": s, "duration": s})
    write(); logs = []
    out = G.run_gate(video, render, {"source_path": "x"}, score, {"source_path": "x", "analysis": {}}, verified_tracks=list(tracks), log=logs.append)
    return out, renders, tmp

def test_gate_passes_good_short_without_rerender():
    out, renders, _ = _run([90])
    assert out["video"] and renders == [] and out["attempts"][0]["pass"]

def test_gate_rerenders_in_another_style_then_passes():
    out, renders, _ = _run([40, 85])
    assert out["video"] and renders == ["SPEED_RAMP_FLOW"] and [a["pass"] for a in out["attempts"]] == [False, True]
    assert out["attempts"][1]["style"] == "SPEED_RAMP_FLOW"

def test_gate_never_releases_a_failing_short():
    out, renders, tmp = _run([40, 45, 48, 99])
    assert out["video"] is None and len(renders) == 2 and len(out["attempts"]) == 3      # 1 + max_retries, nie więcej
    assert len(set(renders)) == 2                                                        # dwa RÓŻNE style
    assert not os.path.exists(os.path.join(tmp, "short.mp4"))                            # film zabrany z kolejki publikacji
    rej = os.listdir(os.path.join(tmp, "rejected_montages"))
    assert any(f.endswith(".rejection.json") for f in rej) and any(f.endswith(".mp4") for f in rej)


def test_rescore_applies_qa_report_penalties():
    old = _quality({"source_resolution": 100, "kill_coverage": 100, "beat_sync": 100, "first_frame": 90, "duration": 100})
    qa_bad = {
        "ok": False,
        "status": "ERROR",
        "issues": ["Silence at start: 0.9s", "Camera velocity: skok 95px"],
        "warnings": ["Kill timing: brak"],
        "checks": {
            "silence_at_start": {"ok": False, "silence_at_start_s": 0.9},
            "camera_velocity": {"ok": False, "peak_velocity_px": 95.0},
            "kill_timing": {"ok": False, "reason": "no ocr"},
        },
    }
    r = G.rescore(old, _recipe(), qa_report=qa_bad)
    assert r["qa_report"]["penalty"] == 18.0
    assert abs(r["score"] - 80.5) < 0.2
    assert any("Silence" in i or "cisza" in i for i in r["issues"])


def test_attach_publication_to_recipe_and_run_gate_with_qa_fn():
    tmp = tempfile.mkdtemp(prefix="flikcut_pub_")
    video = os.path.join(tmp, "short.mp4")
    open(video, "wb").close()
    rec_path = os.path.join(tmp, "short.recipe.json")
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(_recipe(), f)

    saved = G.attach_publication_to_recipe(
        video,
        video_id="yt_12345",
        platform_ids={"tiktok": {"publish_id": "tt_9"}, "instagram_media_id": "ig_7"},
    )
    assert saved == rec_path
    rec = G.read_recipe(video)
    assert rec["video_id"] == "yt_12345"
    assert rec["publication"]["tiktok_publish_id"] == "tt_9"
    assert rec["publication"]["instagram_media_id"] == "ig_7"

    called = []
    def fake_qa(v, source_path=None):
        called.append((v, source_path))
        return {"ok": True, "status": "PASS", "issues": [], "warnings": [], "checks": {}}
    def fake_render(**kw):
        return video
    def fake_score(rendered_path, beat_drop_time, music_file, **kw):
        return _quality({"source_resolution": 100, "kill_coverage": 95, "beat_sync": 100, "first_frame": 95, "duration": 95})
    out = G.run_gate(video, fake_render, {"source_path": "src.mp4"}, fake_score, {}, log=lambda *a: None, qa_fn=fake_qa)
    assert out["video"] == video and out["quality"]["pass"] and called == [(video, "src.mp4")]
