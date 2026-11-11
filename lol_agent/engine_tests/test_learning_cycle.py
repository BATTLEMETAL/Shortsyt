"""Cały cykl uczenia na zmyślonych filmach (bez YouTube): pilnuje, że run_channel_learning_cycle przechodzi od początku
do końca po zmianach i że nie rusza ustawień użytkownika."""
import json, os, random, shutil, sys, tempfile, types
from pathlib import Path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import learning_engine as LE

def _videos():
    r = random.Random(3); out = []
    acts = ["solo_bolo"] * 9 + ["outplay"] * 16 + ["triple"] * 26 + ["double"] * 20 + ["pentakill"] * 6
    for i, a in enumerate(acts):
        base = {"solo_bolo": 2100, "outplay": 1700, "triple": 1550, "double": 1400, "pentakill": 1270}[a]
        title = ("They Tried To Run SOLO BOLO" if a == "solo_bolo" else "Clean Triple Kill In River" if a == "triple" else "Smooth Outplay Mid")
        out.append({"video_id": f"v{i:03d}", "title": title + f" {i % 7}", "views": int(base * r.uniform(0.6, 1.5)), "action_type": a,
                    "duration_s": r.choice([13.0, 15.0, 15.0, 16.0, 21.0]), "engagement_rate": r.uniform(0.1, 0.5),
                    "published_at": f"2026-10-{1 + i % 28:02d}T{r.choice([7, 11, 17, 17, 19]):02d}:00:00Z", "avg_view_pct": r.uniform(90, 120)})
    out += [{"video_id": f"z{i}", "title": "draft", "views": 3, "action_type": "double", "published_at": "2026-10-05T10:00:00Z"} for i in range(5)]
    return out

def _run(tmp, tuning=None, feedback=None):
    LE.LEARNING_DIR = Path(tmp); LE.DIRECTIVE_FILE = LE.LEARNING_DIR / "learning_directive.json"
    LE.TUNING_FILE = LE.LEARNING_DIR / "tuning_config.json"; LE.PUB_LOG_FILE = LE.LEARNING_DIR / "published_videos.jsonl"
    if tuning is not None: LE.TUNING_FILE.write_text(json.dumps(tuning), encoding="utf-8")
    if feedback is not None: (LE.LEARNING_DIR / "user_feedback_history.json").write_text(json.dumps(feedback), encoding="utf-8")
    api = types.ModuleType("api"); up = types.ModuleType("api.youtube_uploader")
    up.get_channel_videos_and_performance = lambda max_results=50, force_refresh=False: {"published": _videos()}
    up.infer_frag_type_from_title = lambda t: "outplay"
    an = types.ModuleType("api.youtube_analytics")
    an.fetch_channel_retention_overview = lambda max_videos=20: {"status": "success", "total_curves_analyzed": 3, "channel_avg_swiped_away_pct": 15.0,
        "channel_avg_view_pct": 200.0, "videos": [{"video_id": "v001", "views": 2000, "swiped_away_pct": 18.0, "avg_view_pct": 98.0},
                                                  {"video_id": "v002", "views": 1800, "swiped_away_pct": 0.0, "avg_view_pct": 101.0},
                                                  {"video_id": "v003", "views": 1500, "swiped_away_pct": 16.0, "avg_view_pct": 400.0}]}
    sys.modules.update({"api": api, "api.youtube_uploader": up, "api.youtube_analytics": an,
                        "lol_agent.api": api, "lol_agent.api.youtube_uploader": up, "lol_agent.api.youtube_analytics": an})
    for k in ("lol_agent", "lol_performance_tracker"): sys.modules.pop(k, None)
    return LE.run_channel_learning_cycle(force_refresh=True)

def test_full_cycle_runs_and_weights_follow_data():
    tmp = tempfile.mkdtemp(prefix="flikcut_learn_")
    try:
        res = _run(tmp)
        assert res["status"] == "success", res
        d = res["directive"]
        assert d["zero_views_filtered"] == 5 and d["total_videos_valid"] == 77
        st = d["action_stats"]
        assert st["solo_bolo"]["weight"] > 1.0 > st["pentakill"]["weight"]            # waga po tej stronie 1.0, po której stosunek
        for a, s in st.items():
            assert (s["weight"] - 1.0) * (s["performance_ratio_median"] - 1.0) >= -0.02 or "breakout_floor" in s["weight_source"], (a, s)
            assert len(s["ratio_ci90"]) == 2 and "reliable" in s
        assert d["retention_robust"]["avg_view_pct"]["median"] == 101.0              # nie 200 ze średniej
        assert d["best_pub_hour_analysis"]["best_hour_utc"] is not None and "best_hour_clear" in d["best_pub_hour_analysis"]
        assert all("median_ratio_within_action" in v for v in d["title_structure_stats"].values())
        json.dumps(d)                                                                # dyrektywa zapisuje się do JSON
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_cycle_never_overwrites_user_tuning():
    tmp = tempfile.mkdtemp(prefix="flikcut_learn_")
    try:
        mine = {"pacing": "aggressive", "zoomAggression": 1.3, "musicBalance": 0.2, "userLocked": ["musicBalance"]}
        _run(tmp, tuning=mine, feedback={"history": [{"param": "zoom", "old_value": 1.2, "new_value": 1.3}]})
        after = json.loads((Path(tmp) / "tuning_config.json").read_text(encoding="utf-8"))
        assert after["musicBalance"] == 0.2 and after["zoomAggression"] == 1.3      # zablokowane i zmienione ręcznie: nietknięte
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
