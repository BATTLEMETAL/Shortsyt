"""Silnik uczenia: wnioski muszą wynikać z danych, nie z przypadku. Część testów liczy na danych z learning_directive.json."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import learning_engine as LE

def test_weight_follows_the_ratio():
    assert LE.shrunk_weight(0.95, 26) < 1.0          # triple: stosunek 0.95 → waga poniżej 1 (dawniej 1.34)
    assert LE.shrunk_weight(0.86, 20) < 1.0          # double (dawniej 1.25)
    assert 1.0 < LE.shrunk_weight(1.29, 9) < 1.29    # solo bolo: powyżej 1, ale 9 filmów nie daje pełnych 1.29
    assert abs(LE.shrunk_weight(1.5, 0) - 1.0) < 1e-9

def test_bootstrap_interval_is_wide_for_small_groups():
    lo, hi = LE.bootstrap_median_ratio_ci([2120, 1472, 2066, 1641, 2978, 3900, 2500, 1900, 3800], 1641.0)
    assert lo < hi and hi - lo > 0.3                 # 9 filmów: przedział szeroki, wniosek tylko wstępny

def test_retention_median_not_mean():
    d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_retention.json"), encoding="utf-8"))
    r = LE.summarize_retention(d["retention_analysis"]["videos"])
    assert r["avg_view_pct"]["median"] < 110 < d["retention_analysis"]["channel_avg_view_pct"]   # 122.9 % to średnia z odstającym 474.7 %
    assert 474.7 in r["avg_view_pct"]["outliers"]
    assert r["swiped_away_pct"]["median"] > d["retention_analysis"]["channel_avg_swiped_away_pct"]  # zera i film bez wyświetleń zaniżały

def test_tuning_respects_the_user():
    cur = {"pacing": "balanced", "zoomAggression": 1.2}
    prop = {"pacing": "cinematic", "zoomAggression": 1.1, "slowmoDuration": 2.0}
    assert LE.plan_tuning_update(cur, prop, clear_winner=False, locked=set()) == {}
    assert LE.plan_tuning_update(cur, prop, True, {"zoomAggression"}) == {"pacing": "cinematic", "slowmoDuration": 2.0}
    assert LE.plan_tuning_update(prop, prop, True, set()) == {}

def test_recency_weight_reads_datetimes():
    from datetime import datetime, timezone, timedelta
    old = datetime.now(timezone.utc) - timedelta(days=200)
    new = datetime.now(timezone.utc) - timedelta(days=2)
    m = LE._compute_robust_metric([1000, 3000], [old, new])
    assert abs(m["mean"] - (1000 * 0.5 + 3000 * 1.0) / 1.5) < 1.0   # dawniej wagi zawsze 1.0 → średnia 2000

def test_best_hour_needs_samples():
    vids = [{"views": 3000, "published_at": "2026-10-01T08:00:00Z"}, {"views": 3100, "published_at": "2026-10-02T08:00:00Z"}]
    vids += [{"views": 1500 + i, "published_at": f"2026-10-{3 + i:02d}T17:00:00Z"} for i in range(8)]
    r = LE._analyze_best_pub_hour(vids)
    assert r["best_hour_utc"] != 8                    # dwa filmy o 8:00 nie robią "najlepszej godziny"

def test_duration_buckets_use_all_videos():
    vids = [{"views": 2000 + i, "duration_s": 15.0} for i in range(10)] + [{"views": 2600, "duration_s": 21.0} for _ in range(3)]
    r = LE.correlate_viral_duration_and_pacing([v for v in vids if v["views"] > 2500], vids, 2005.0)
    assert r["bucket_stats"]["balanced_14_17s"]["count"] == 10 and r["bucket_stats"]["cinematic_18_25s"]["reliable"] is False
    assert r["best_bucket"] == "balanced_14_17s" and r["clear_winner"] is False


def test_load_game_profile_lol():
    import smart_camera as SC
    prof = SC.load_game_profile("lol")
    assert prof["game"] == "lol"
    assert abs(prof["hud_exclusion_zones"]["top_y_ratio"] - 0.10) < 1e-6
    assert abs(prof["hud_exclusion_zones"]["minimap_x_ratio"] - 0.76) < 1e-6
    assert prof["health_bar_colors"]["yellow_self_bar"]["r_min"] == 160
    assert "PENTAKILL" in prof["kill_labels"]


def test_recipe_experiments_require_sample_size_and_lead():
    import tempfile, shutil
    tmp = tempfile.mkdtemp(prefix="flikcut_rec_")
    try:
        vids = []
        # Small sample: 4 per bucket (< MIN_SAMPLE_FOR_BUCKET=8) -> reliable must stay False
        for i in range(4):
            vid = f"v_small_a_{i}"
            vids.append({"video_id": vid, "views": 5000})
            with open(os.path.join(tmp, f"{vid}.recipe.json"), "w", encoding="utf-8") as f:
                json.dump({"video_id": vid, "montage_style": "SPEED_RAMP_FLOW", "crop_mode": "smart"}, f)
        for i in range(4):
            vid = f"v_small_b_{i}"
            vids.append({"video_id": vid, "views": 1000})
            with open(os.path.join(tmp, f"{vid}.recipe.json"), "w", encoding="utf-8") as f:
                json.dump({"video_id": vid, "montage_style": "CINEMATIC_DUEL", "crop_mode": "center"}, f)
        r_small = LE.analyze_recipe_experiments(vids, shorts_dir=tmp)
        assert r_small["matched_videos"] == 8
        assert r_small["dimensions"]["montage_style"]["reliable"] is False
        assert r_small["dimensions"]["montage_style"]["winner"] is None

        # Sufficient sample: 8 per bucket with >15% lead -> reliable True and clear winner
        for i in range(4, 9):
            vid = f"v_big_a_{i}"
            vids.append({"video_id": vid, "views": 5200})
            with open(os.path.join(tmp, f"{vid}.recipe.json"), "w", encoding="utf-8") as f:
                json.dump({"video_id": vid, "montage_style": "SPEED_RAMP_FLOW", "crop_mode": "smart"}, f)
        for i in range(4, 9):
            vid = f"v_big_b_{i}"
            vids.append({"video_id": vid, "views": 1100})
            with open(os.path.join(tmp, f"{vid}.recipe.json"), "w", encoding="utf-8") as f:
                json.dump({"video_id": vid, "montage_style": "CINEMATIC_DUEL", "crop_mode": "center"}, f)
        r_big = LE.analyze_recipe_experiments(vids, shorts_dir=tmp)
        assert r_big["dimensions"]["montage_style"]["reliable"] is True
        assert r_big["dimensions"]["montage_style"]["winner"] == "SPEED_RAMP_FLOW"
        assert "montage_style" in r_big["reliable_dimensions"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_calibrate_quality_gate_guards_small_sample_and_clamps():
    few = [{"video_id": f"s_{i}", "quality_score": 60 + i * 5, "views": 1000 * (i + 1)} for i in range(5)]
    c_small = LE.calibrate_quality_gate(few, current_threshold=70.0)
    assert c_small["reliable"] is False and c_small["recommended_threshold"] == 70.0

    many = [
        {"video_id": f"m_{i}", "quality_score": 55 + i * 3, "views": 800 if i < 6 else 4000,
         "avg_view_pct": 65.0 if i < 6 else 105.0,
         "quality_breakdown": {"beat_sync": {"score": 50 + i * 4}}}
        for i in range(12)
    ]
    c_big = LE.calibrate_quality_gate(many, current_threshold=70.0)
    assert c_big["reliable"] is True
    assert 55.0 <= c_big["recommended_threshold"] <= 80.0
    assert c_big["correlation_qs_views"] > 0.5
    assert "beat_sync" in c_big["component_correlations"]


def test_evaluate_48h_post_publish_gate_verdicts():
    import lol_performance_tracker as LPT

    # Case 1: t=0h MEI obiecujacy mocny hook (>=75 i <=1.8s), ale po 48h slaby engaged_view_rate (<42% => score <70)
    entry_over = {
        "quality_score": 88.0,
        "mei": {"hook_score": 90.0, "hook_latency_s": 0.9, "pacing_score": 85.0, "combat_density_pct": 80.0},
    }
    stats_over = {
        "views": 600,
        "likes": 8,
        "comments": 0,
        "shares": 0,
        "engaged_view_rate_pct": 38.0,
        "avg_view_pct": 72.0,
    }
    gate_over = LPT.evaluate_48h_post_publish_gate(entry_over, stats_over, channel_median_views=1640.0)
    assert 0.0 <= gate_over["rwi_score"] <= 100.0
    assert gate_over["definition_audit"]["hook_verdict"] == "OVERESTIMATED_HOOK"

    # Case 2: Dobry montaz i świetne realne wyniki po 48h => FIT_CONFIRMED
    entry_ok = {
        "quality_score": 90.0,
        "mei": {"hook_score": 88.0, "hook_latency_s": 0.8, "pacing_score": 88.0, "combat_density_pct": 82.0},
    }
    stats_ok = {
        "views": 3200,
        "likes": 95,
        "comments": 6,
        "shares": 3,
        "subscribers_gained": 2,
        "hook_retention_pct": 86.0,
        "avg_view_pct": 112.0,
    }
    gate_ok = LPT.evaluate_48h_post_publish_gate(entry_ok, stats_ok, channel_median_views=1640.0)
    assert gate_ok["rwi_score"] >= 80.0
    assert gate_ok["watchability_tier"] == "EXCELLENT"
    assert gate_ok["definition_audit"]["hook_verdict"] == "HOOK_CONFIRMED"
    assert gate_ok["definition_audit"]["overall_verdict"] == "FIT_CONFIRMED"


def test_attach_publication_to_recipe_archives_permanently(tmp_path):
    import lol_quality_gate as LQG

    video_file = tmp_path / "test_short.mp4"
    video_file.write_bytes(b"fake_mp4")
    recipe_file = tmp_path / "test_short.recipe.json"
    recipe_file.write_text(json.dumps({"action_type": "SOLO_BOLO", "duration_s": 15.2}), encoding="utf-8")
    archive_dir = tmp_path / "recipes_archive"

    LQG.attach_publication_to_recipe(
        str(video_file),
        video_id="yt_vid_999",
        platform_ids={"tiktok_publish_id": "tt_777"},
        archive_dir=str(archive_dir),
    )

    archived_file = archive_dir / "yt_vid_999.recipe.json"
    assert archived_file.is_file()
    saved = json.loads(archived_file.read_text(encoding="utf-8"))
    assert saved["video_id"] == "yt_vid_999"
    assert saved["publication"]["tiktok_publish_id"] == "tt_777"


def test_clip_ranker_duration_range_maps_best_bucket(monkeypatch):
    import lol_clip_ranker as LCR

    monkeypatch.setattr(
        LE,
        "get_learning_directive",
        lambda: {
            "duration_analysis": {
                "best_bucket": "balanced_14_17s",
                "clear_winner": True,
                "bucket_stats": {"balanced_14_17s": {"reliable": True}},
            }
        },
    )
    assert LCR._load_optimal_duration_range() == (13.5, 17.5)


def test_account_manager_upsert_switch_and_metadata(tmp_path, monkeypatch):
    from pathlib import Path
    parent_dir = os.path.dirname(ROOT)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from lol_agent import account_manager as AM

    monkeypatch.setattr(AM, "ACCOUNTS_DIR", Path(tmp_path))
    monkeypatch.setattr(AM, "REGISTRY_FILE", Path(tmp_path) / "profiles_registry.json")
    monkeypatch.setattr(AM, "PRETTY_WOMAN_CFG", Path(tmp_path) / "missing_pw.json")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    try:
        from lol_agent import lol_config
        monkeypatch.setattr(lol_config, "GEMINI_API_KEY", "")
    except Exception:
        pass

    created = AM.upsert_account(
        {
            "display_name": "Salon Bella Świdnica",
            "handle": "@salonbella",
            "content_mode": "BEAUTY_SALON_SERVICE",
            "language": "pl",
            "value_proposition": "Afroloki i metamorfozy w 3 godziny",
            "cta_text": "Zarezerwuj termin 👇",
            "cta_url": "https://salonbella.example",
            "location": "ul. Rynek 10, Świdnica",
            "mandatory_hashtags": ["#shorts", "#afroloki"],
            "forbidden_words": ["Katarina", "Pentakill"],
            "set_active": True,
        }
    )
    assert created["account_id"] == "salon_bella_widnica" or "salon_bella" in created["account_id"]
    active = AM.get_active_account()
    assert active["account_id"] == created["account_id"]

    switched = AM.set_active_account("dwannellenga")
    assert switched["account_id"] == "dwannellenga"
    AM.set_active_account(created["account_id"])

    meta = AM.generate_account_aware_metadata(action_type="metamorfoza", subject_name="Afroloki Blond")
    assert "Katarina" not in meta["title"]
    assert "Katarina" not in meta["description"]
    assert "Świdnica" in meta["description"]
    assert "#shorts" in meta["title"].lower()


def test_screen_inspector_kill_span_and_champion_local(tmp_path):
    from lol_agent import lol_screen_inspector as LSI

    fake_vid = tmp_path / "Katarina_mid_triple.mp4"
    fake_vid.write_bytes(b"")
    info = LSI.inspect_clip_screens(str(fake_vid), peaks=[(5.0, "KILL"), (7.1, "TRIPLE KILL")], trim_start=0.0, clip_duration=14.0)
    assert info["kill_span_s"] == 2.1
    assert info["combo_tempo"] == "INSTANT_BURST"
    assert LSI.detect_champion_local(str(fake_vid)) == "Katarina"


def test_flush_pending_comments_handles_zero_byte_file(tmp_path):
    parent_dir = os.path.dirname(ROOT)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from lol_agent.api import youtube_uploader as YU

    q_file = tmp_path / "pending_comments.json"
    q_file.write_text("", encoding="utf-8")
    res = YU.flush_pending_comments(queue_path=q_file)
    assert res == {"sent": [], "still_pending": []}
    assert q_file.read_text(encoding="utf-8").strip() == "[]"


def test_pinned_comment_telemetry_antibot_and_non_repeating(tmp_path):
    from lol_agent import lol_metadata_generator as LMG

    # Zmyślony spell bez potwierdzenia z HUD musi zostać odrzucony
    assert LMG.sanitize_pinned_comment("They flashed into my dagger!", {"hud_spells_used": {"verified": False}}) == ""
    assert LMG.sanitize_pinned_comment("Rate this play 1-10!", {}) == ""
    assert LMG.sanitize_pinned_comment("Nice play 👉 facebook.com/Dwannellenga", {}) != ""
    assert "facebook.com" not in LMG.sanitize_pinned_comment("Nice play https://www.facebook.com/Dwannellenga", {})

    hist_path = tmp_path / "comment_history.json"
    ctx = {"kill_count": 3, "kill_span_s": 2.2, "min_hp_pct": 14.0, "low_hp_survival": True}
    seen = set()
    for _ in range(4):
        c = LMG.build_pinned_comment("Katarina", "triple", extra_context=ctx, comment_history_path=str(hist_path))
        assert "facebook.com" not in c.lower()
        assert "flash" not in c.lower()
        assert "rate 1-10" not in c.lower()
        assert c not in seen
        seen.add(c)


def test_outro_cta_non_repeating_window(tmp_path):
    from lol_agent import lol_editor as LED

    hist_file = tmp_path / "caption_history.json"
    picked_ids = []
    for _ in range(6):
        chosen = LED.select_non_repeating_outro_cta(history_path=str(hist_file), action_type="outplay")
        assert chosen["id"] not in picked_ids
        picked_ids.append(chosen["id"])


def test_synapsa_title_selector_penalizes_hallucinations():
    from lol_agent import synapsa_engine as SE

    cands = [
        "Master Katarina Flashed Bad Idea #shorts",
        "Rate this Katarina play 1-10 #shorts",
        "Surviving on 1% HP to Win #shorts",
        "They Thought 1v1 Was Safe #shorts",
    ]
    ctx = {"low_hp_survival": True, "hud_spells_used": {"verified": False}}
    directive = {"title_structure_stats": {"CLUTCH_1HP": {"avg_ratio": 1.76}, "DISRESPECT_1V1": {"avg_ratio": 1.40}}}
    best_a, best_b = SE.score_and_select_best_titles(cands, action_type="clutch", extra_context=ctx, directive=directive)
    assert "Surviving on 1% HP" in best_a
    assert "Flashed" not in best_a and "Rate this" not in best_a
    assert best_b != best_a




def test_platform_tokens_are_isolated_per_account(tmp_path, monkeypatch):
    from pathlib import Path
    parent_dir = os.path.dirname(ROOT)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from lol_agent import account_manager as AM

    monkeypatch.setattr(AM, "ACCOUNTS_DIR", Path(tmp_path))
    monkeypatch.setattr(AM, "REGISTRY_FILE", Path(tmp_path) / "profiles_registry.json")
    monkeypatch.setattr(AM, "PRETTY_WOMAN_CFG", Path(tmp_path) / "missing_pw.json")

    AM.set_active_account("dwannellenga")
    assert AM.get_active_platform_token_path("tiktok").name == "tiktok_token.json"
    assert AM.get_active_platform_token_path("instagram").name == "instagram_token.json"
    assert AM.get_active_platform_token_path("facebook").name == "facebook_token.json"

    # Konto klienta bez własnych tokenów NIE może dziedziczyć tokenów kanału gamingowego
    AM.set_active_account("pretty_woman")
    for plat in ("tiktok", "instagram", "facebook"):
        p = AM.get_active_platform_token_path(plat)
        assert p.name.startswith("pretty_woman_")
        assert not p.exists()


def test_publishers_follow_active_account_token(tmp_path, monkeypatch):
    parent_dir = os.path.dirname(ROOT)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from lol_agent import account_manager as AM
    from lol_agent import tiktok_publisher as TT

    fake = tmp_path / "other_tt.json"
    monkeypatch.setattr(AM, "get_active_platform_token_path", lambda platform: fake)
    assert TT._token_path() == fake
    assert TT.load_tiktok_token() is None  # brak pliku = brak tokenu, bez fallbacku na główne konto


def test_shared_48h_archive_helper_exists_and_archives(tmp_path):
    parent_dir = os.path.dirname(ROOT)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from lol_agent.api import helpers as H

    assert callable(H._archive_and_schedule_48h)
    video = tmp_path / "x.mp4"
    video.write_bytes(b"x")
    # brak .recipe.json i pending_checks pod PYTEST — funkcja nie może rzucać wyjątku
    H._archive_and_schedule_48h(str(video), "", {}, "t", {})


def test_reconcile_multikill_sequence_and_hard_case_memory(tmp_path):
    from lol_agent import lol_frag_detector as LFD
    from lol_agent import hard_case_learner as HCL

    raw_kills = [
        {"timestamp": 16.0, "label": "TRIPLE KILL", "tier": 3},
        {"timestamp": 18.5, "label": "DOUBLE KILL", "tier": 2},
        {"timestamp": 28.0, "label": "QUADRAKILL", "tier": 4},
    ]
    ally_times = [10.5, 11.0, 14.0, 15.0]
    obj_times = [21.5, 22.0, 27.0]

    reconciled = LFD._reconcile_multikill_sequence(
        kills_detected=raw_kills,
        ally_banner_times=ally_times,
        objective_times=obj_times,
        video_path="",
    )
    assert [k["tier"] for k in reconciled] == [1, 2, 3, 4]
    assert [k["label"] for k in reconciled] == ["KILL", "DOUBLE KILL", "TRIPLE KILL", "QUADRAKILL"]
    assert reconciled[1]["timestamp"] == 16.0
    assert reconciled[2]["timestamp"] == 21.5

    mem_path = tmp_path / "hard_cases_memory.json"
    saved = HCL.record_hard_case(
        video_path=r"C:\clips\quadra_dragon.mp4",
        detected_frag_type="quadrakill",
        kills=reconciled,
        clip_start=5.8,
        clip_end=29.8,
        reason="ally_banner_blocked, objective_steal_or_slain",
        objective_secured=True,
        objective_label="DRAGON_OR_OBJECTIVE_SLAIN",
        ally_banner_blocked=True,
        min_hp_pct=1.3,
        memory_path=mem_path,
    )
    assert saved["source_name"] == "quadra_dragon.mp4"
    loaded = HCL.get_hard_case_by_source("quadra_dragon.mp4", memory_path=mem_path)
    assert loaded is not None
    assert loaded["objective_secured"] is True
    assert len(HCL.load_hard_cases(memory_path=mem_path)) == 1


def test_synapsa_hybrid_director_and_rollback_guard():
    from lol_agent import synapsa_engine as SE
    from lol_agent import lol_quality_gate as LQG
    from lol_agent import lol_montage_director as LMD

    dec_dragon = SE.decide_montage_with_synapsa({
        "action_type": "quadrakill",
        "champion": "Katarina",
        "duration": 24.0,
        "kills": [{"timestamp": 11.5}, {"timestamp": 16.0}, {"timestamp": 21.0}, {"timestamp": 28.0}],
        "objective_secured": True,
        "ally_banner_blocked": True,
    })
    assert dec_dragon["operation"] == "KEEP_FULL_CONTINUOUS"
    assert dec_dragon["style"] == "PRIMARY"
    assert dec_dragon["param_contracts_applied"] is True
    assert 0.4 <= dec_dragon["buildup_sec"] <= 0.8
    assert dec_dragon["camera_mode"] == "tight_player"

    # Fizyczne przepięcie w direct_clip_montage()
    dir_dec = LMD.direct_clip_montage(
        action_type="solo_bolo",
        champion_name="Katarina",
        duration=13.5,
        peaks=[(7.5, "SOLO BOLO")],
    )
    assert dir_dec.synapsa_decision.get("param_contracts_applied") is True
    assert dir_dec.camera_mode == dir_dec.synapsa_decision["camera_mode"]
    assert dir_dec.zoom_aggression == dir_dec.synapsa_decision["zoom_aggression"]
    assert dir_dec.tuning_profile["buildup_sec"] == dir_dec.buildup_sec

    dec_isolated = SE.decide_montage_with_synapsa({
        "action_type": "triple",
        "champion": "Katarina",
        "duration": 22.0,
        "kills": [{"timestamp": 2.0}, {"timestamp": 12.0}, {"timestamp": 14.5}],
        "gap_has_combat": False,
        "objective_secured": False,
        "ally_banner_blocked": False,
    })
    assert dec_isolated["operation"] == "DROP_ISOLATED_FIRST_KILL"

    guard_block = LQG.simulate_and_guard_director_decision(
        base_window=(5.8, 29.8, 18.7),
        proposed_window=(13.5, 29.8, 18.7),
        all_kills_abs=[11.5, 16.0, 21.0, 28.0],
        objective_secured=True,
    )
    assert guard_block["approved"] is False
    assert guard_block["rollback_triggered"] is True
    assert guard_block["selected_window"] == (5.8, 29.8, 18.7)

    guard_ok = LQG.simulate_and_guard_director_decision(
        base_window=(0.5, 16.5, 14.5),
        proposed_window=(10.5, 16.5, 14.5),
        all_kills_abs=[2.0, 12.0, 14.5],
        objective_secured=False,
    )
    # 10.5 -> 16.5 trwa tylko 6.0s (<8.0s), więc symulator blokuje zbyt krótki klip; dla 8.5s..16.5s zatwierdzi
    assert guard_ok["rollback_triggered"] is True

    guard_ok_8s = LQG.simulate_and_guard_director_decision(
        base_window=(0.5, 16.5, 14.5),
        proposed_window=(8.5, 16.5, 14.5),
        all_kills_abs=[2.0, 12.0, 14.5],
        objective_secured=False,
    )
    assert guard_ok_8s["approved"] is True
    assert guard_ok_8s["rollback_triggered"] is False


def test_etap_5c_closed_loop_and_stability(tmp_path):
    import inspect
    from datetime import datetime, timedelta, timezone
    from lol_agent import lol_editor as LED
    from lol_agent import synapsa_engine as SE
    from lol_agent import synapsa_title_trainer as STT

    # 1. Sygnatura render_short przyjmuje director_decision i flagi obiektu/banera
    sig_params = inspect.signature(LED.render_short).parameters
    assert "director_decision" in sig_params
    assert "objective_secured" in sig_params
    assert "ally_banner_blocked" in sig_params

    # 2. _analyze_48h_reality_gate agreguje by_director_operation oraz decide_montage_with_synapsa ją odbiera
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
    rec_dir = tmp_path / "recipes"
    rec_dir.mkdir(parents=True, exist_ok=True)
    with open(rec_dir / "vid_op_keep.recipe.json", "w", encoding="utf-8") as f:
        json.dump({
            "video_id": "vid_op_keep",
            "montage_style": "PRIMARY",
            "director_operation": "KEEP_FULL_CONTINUOUS",
            "camera_mode": "tight_player",
        }, f)
    with open(rec_dir / "vid_op_ramp.recipe.json", "w", encoding="utf-8") as f:
        json.dump({
            "video_id": "vid_op_ramp",
            "montage_style": "SPEED_RAMP_FLOW",
            "camera_mode": "duel_centroid",
            "director": {"synapsa_decision": {"operation": "BRIDGE_GAP_SPEED_RAMP"}},
        }, f)

    vids_48h = [
        {
            "video_id": "vid_op_keep",
            "published_at": old_ts,
            "views": 4200,
            "likes": 60,
            "comments": 2,
            "duration_s": 16.0,
            "avg_view_pct": 112.0,
            "swiped_away_pct": 14.0,
            "hook_retention_pct": 86.0,
            "action_type": "quadrakill",
        },
        {
            "video_id": "vid_op_ramp",
            "published_at": old_ts,
            "views": 2100,
            "likes": 25,
            "comments": 1,
            "duration_s": 15.0,
            "avg_view_pct": 98.0,
            "swiped_away_pct": 21.0,
            "hook_retention_pct": 79.0,
            "action_type": "triple",
        },
    ]
    g48 = LE._analyze_48h_reality_gate(vids_48h, channel_median=1600.0, shorts_dir=rec_dir)
    assert "KEEP_FULL_CONTINUOUS" in g48["by_director_operation"]
    assert "BRIDGE_GAP_SPEED_RAMP" in g48["by_director_operation"]
    assert g48["by_director_operation"]["KEEP_FULL_CONTINUOUS"]["count"] == 1

    syn_dec = SE.decide_montage_with_synapsa(
        {"action_type": "quadrakill", "duration": 18.0, "kills": [{"timestamp": 4.0}, {"timestamp": 8.0}]},
        directive={"post_48h_gate_summary": g48},
    )
    assert "KEEP_FULL_CONTINUOUS" in syn_dec["director_operation_stats"]

    # 3. analyze_recipe_experiments liczy wymiary director_operation i camera_mode
    exp = LE.analyze_recipe_experiments(vids_48h, shorts_dir=rec_dir)
    assert "director_operation" in exp["dimensions"]
    assert "camera_mode" in exp["dimensions"]
    assert "KEEP_FULL_CONTINUOUS" in exp["dimensions"]["director_operation"]["buckets"]
    assert "duel_centroid" in exp["dimensions"]["camera_mode"]["buckets"]

    # 4. sync_incremental_training_dataset wylicza retrain_ready i zapisuje ds.jsonl do tmp_path
    ad_dir = tmp_path / "adapter"
    ad_dir.mkdir(parents=True, exist_ok=True)
    (ad_dir / "training_metrics.json").write_text(json.dumps({"dataset_examples": 100}), encoding="utf-8")
    ds_out = tmp_path / "ds.jsonl"
    sync_ready = STT.sync_incremental_training_dataset(
        directive={"post_48h_gate_summary": g48},
        min_new_for_retrain=5,
        write_dataset=True,
        output_path=ds_out,
        adapter_dir=ad_dir,
    )
    assert ds_out.is_file()
    assert sync_ready["retrain_ready"] is True
    assert sync_ready["new_examples_since_train"] == max(0, sync_ready["total_examples"] - 100)

    (ad_dir / "training_metrics.json").write_text(
        json.dumps({"dataset_examples": sync_ready["total_examples"]}),
        encoding="utf-8",
    )
    sync_up_to_date = STT.sync_incremental_training_dataset(
        directive={"post_48h_gate_summary": g48},
        min_new_for_retrain=5,
        write_dataset=True,
        output_path=ds_out,
        adapter_dir=ad_dir,
    )
    assert sync_up_to_date["retrain_ready"] is False
    assert sync_up_to_date["new_examples_since_train"] == 0


def test_etap7_attribute_delta_and_todo_lessons(tmp_path, monkeypatch):
    import lol_agent.synapsa_conversation_learner as SCL
    import lol_agent.synapsa_engine as SE

    rec_dir = tmp_path / "recipes"
    rec_dir.mkdir(parents=True, exist_ok=True)
    mem_file = tmp_path / "engineering_lessons_memory.json"
    todo_file = tmp_path / "TODO.md"
    todo_file.write_text(
        "## 1. Sekcja\n| Zadanie / Moduł | Po co (Cel) | Co wdrażamy / wdrożyliśmy | Stan | Rezultat / Diagnoza | Oczekiwania |\n"
        "| :--- | :--- | :--- | :---: | :--- | :--- |\n"
        "| **Naprawa audio slow-mo** (`lol_timeline.py`) | Brak trzasków | Użyto `asetrate` + `alimiter` | `[x]` | Skoki spadły `29 -> 0` | Płynne audio |\n"
        "| **Otwarte zadanie** (`x.py`) | Test | Coś | `[ ]` | Brak | Brak |\n",
        encoding="utf-8",
    )

    rec_before = {
        "source": "demo_match.mp4",
        "created_utc": "2026-11-18T18:00:00Z",
        "action_type": "quadrakill",
        "champion": "Katarina",
        "montage_style": "SPEED_RAMP_FLOW",
        "director_operation": "BRIDGE_GAP_SPEED_RAMP",
        "camera_mode": "tight_player",
        "camera_peak_step_px": 250.0,
        "clip_seconds_in": 24.0,
        "final_seconds": 19.0,
        "peaks_in_clip": [[12.0, "KILL"], [22.0, "QUADRAKILL"]],
        "peak_in_clip": 21.5,
        "peak_in_output": 14.0,
        "director": {"buildup_sec": 1.6, "outro_sec": 0.9, "asked_zoom": 1.2, "asked_slowmo": 1.0, "camera_mode": "tight_player"},
        "applied": {"zoom_level": 1.12, "slowmo_speed": 0.55, "game_audio_warped": True},
        "music": {"track": "t.mp3", "music_start": 10.0, "drop_time": 24.0},
    }
    rec_after = {
        **rec_before,
        "created_utc": "2026-11-18T19:00:00Z",
        "montage_style": "PRIMARY",
        "director_operation": "KEEP_FULL_CONTINUOUS",
        "camera_peak_step_px": 60.0,
        "final_seconds": 25.0,
        "director": {"buildup_sec": 0.8, "outro_sec": 1.3, "asked_zoom": 1.2, "asked_slowmo": 1.0, "camera_mode": "tight_player"},
    }
    (rec_dir / "b.recipe.json").write_text(json.dumps(rec_before), encoding="utf-8")
    after_path = rec_dir / "a.recipe.json"
    after_path.write_text(json.dumps(rec_after), encoding="utf-8")

    delta = SCL.record_recipe_delta_on_render(str(after_path), memory_path=mem_file, recipes_dirs=[rec_dir])
    assert delta is not None
    assert delta["verdict"] == "IMPROVED"
    assert delta["deltas"]["delta_camera_peak_step_px"] == -190.0
    assert "director_operation" in delta["changed_attributes"]

    sync_res = SCL.sync_engineering_memory(
        memory_path=mem_file, todo_path=todo_file, recipes_dirs=[rec_dir], include_transcripts=False, write_files=True
    )
    assert sync_res["todo_lessons_count"] == 1
    assert sync_res["attribute_deltas_count"] == 1

    # Kontekst Cause -> Effect trafia do payloadu synapsa_engine.decide_montage_with_synapsa
    ctx = SCL.get_cause_effect_context_for_director("quadrakill", memory_path=mem_file)
    assert ctx and ctx[0]["verdict"] == "IMPROVED"
    ce_ex = SCL.build_cause_effect_training_examples(memory_path=mem_file)
    assert len(ce_ex) >= 2 and "CAUSE_EFFECT_EVIDENCE" in ce_ex[0]["instruction"]

    monkeypatch.setattr(SCL, "DEFAULT_MEMORY_PATH", mem_file)
    captured = {}
    monkeypatch.setattr(SE, "is_synapsa_available", lambda: True)
    def _fake_gen(task, pload, timeout=120):
        captured["payload"] = pload
        return None
    monkeypatch.setattr(SE, "generate_with_synapsa", _fake_gen)
    SE.decide_montage_with_synapsa({"action_type": "quadrakill", "duration": 24.0, "kills": [{"timestamp": 12.0}, {"timestamp": 22.0}], "objective_secured": True})
    assert "verified_cause_effect_lessons" in captured["payload"]


def test_etap7_transcript_extractor_and_coding_sync(tmp_path):
    import lol_agent.synapsa_conversation_learner as SCL

    tp = tmp_path / "transcript.jsonl"
    code_ds = tmp_path / "moj_styl_kodowania.jsonl"
    code_ds.write_text(json.dumps({"instruction": "Old entry", "input": "", "output": "pass"}) + "\n", encoding="utf-8")

    steps = [
        {"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>\nnapraw upload na youtube oraz slowmo\n</USER_REQUEST>"},
        {
            "step_index": 1,
            "type": "PLANNER_RESPONSE",
            "tool_calls": [
                {
                    "name": "edit_file",
                    "args": {
                        "Path": json.dumps(r"c:\Users\dev\workspace\Shortsyt\lol_agent\lol_timeline.py"),
                        "Target": json.dumps("tempo = ',atempo=0.55'\nreturn tempo"),
                        "Replacement": json.dumps("def fixed_warp(speed):\n    return f',asetrate=44100*{speed:.6f},aresample=44100'\n"),
                    },
                }
            ],
        },
        {"step_index": 2, "type": "GENERIC", "content": "76 passed in 8.41s"},
    ]
    tp.write_text("\n".join(json.dumps(s) for s in steps) + "\n", encoding="utf-8")

    fixes, coding = SCL.extract_lessons_from_transcripts(transcript_paths=[tp])
    assert len(fixes) == 1
    assert "lol_agent\\lol_timeline.py" in fixes[0]["affected_files"]
    assert any("76 passed" in v for v in fixes[0]["verification"])
    assert len(coding) == 1 and "asetrate=44100" in coding[0]["output"]

    res1 = SCL.sync_coding_style_dataset(coding, coding_dataset_path=code_ds)
    res2 = SCL.sync_coding_style_dataset(coding, coding_dataset_path=code_ds)
    assert res1["added_from_shortsyt"] == 1 and res1["total_coding_examples"] == 2
    assert res2["added_from_shortsyt"] == 0 and res2["total_coding_examples"] == 2


def test_etap8b_katarina_shunpo_policy_and_high_retention_context(tmp_path, monkeypatch):
    from lol_agent import synapsa_conversation_learner as SCL
    from lol_agent import synapsa_engine as SE

    yt_cache = tmp_path / "yt_perf_cache.json"
    yt_cache.write_text(json.dumps({
        "videos": [
            {"video_id": "v_high1", "views": 2400, "avg_view_pct": 145.0, "action_type": "quadrakill", "initial_qa_score": 96},
            {"video_id": "v_high2", "views": 1900, "avg_view_pct": 105.0, "action_type": "triple", "initial_qa_score": 97},
            {"video_id": "v_low1", "views": 1100, "avg_view_pct": 78.7, "action_type": "triple", "initial_qa_score": 82},
        ]
    }), encoding="utf-8")

    pub_file = tmp_path / "published_videos.jsonl"
    pub_file.write_text(
        "\n".join([
            json.dumps({"video_id": "v_high1", "duration_s": 15.0, "initial_qa_score": 96}),
            json.dumps({"video_id": "v_high2", "duration_s": 14.2, "initial_qa_score": 97}),
        ]),
        encoding="utf-8",
    )

    dir_file = tmp_path / "learning_directive.json"
    dir_file.write_text(json.dumps({
        "duration_analysis": {"best_bucket": "balanced_14_17s", "viral_avg_duration_s": 15.0},
        "retention_by_action": {"by_action": {"quadrakill": {"avg_hook_retention_pct": 87.0}, "triple": {"avg_hook_retention_pct": 88.2}}},
    }), encoding="utf-8")

    rdir = tmp_path / "recipes_archive"
    rdir.mkdir()
    (rdir / "v_low1.recipe.json").write_text(json.dumps({
        "video_id": "v_low1",
        "camera_peak_step_px": 533.0,
        "montage_style": "PRIMARY",
        "director_operation": "KEEP_FULL_CONTINUOUS",
        "final_seconds": 15.0,
    }), encoding="utf-8")
    (rdir / "v_high1.recipe.json").write_text(json.dumps({
        "video_id": "v_high1",
        "camera_peak_step_px": 63.0,
        "montage_style": "PRIMARY",
        "director_operation": "KEEP_FULL_CONTINUOUS",
        "final_seconds": 15.0,
    }), encoding="utf-8")

    prof = SCL.analyze_high_retention_configs(
        yt_cache_path=yt_cache,
        published_path=pub_file,
        directive_path=dir_file,
        recipes_dir=rdir,
    )
    assert prof["high_avd_count"] == 2
    assert prof["low_avd_count"] == 1
    assert prof["best_duration_bucket"] == "balanced_14_17s"
    assert any(f.get("warning") and "533.0" in f["warning"] for f in prof["recipe_camera_findings"])

    captured = {}
    monkeypatch.setattr(SE, "is_synapsa_available", lambda: True)

    def _fake_gen(task_type, payload, timeout=120):
        captured["task_type"] = task_type
        captured["payload"] = payload
        return None

    monkeypatch.setattr(SE, "generate_with_synapsa", _fake_gen)
    decision = SE.decide_montage_with_synapsa(
        telemetry={"champion": "Katarina", "action_type": "quadrakill", "duration": 29.8, "kills": [5.7, 10.2, 15.2, 22.2], "objective_secured": True},
    )
    assert captured.get("task_type") == "montage_director"
    assert "camera_policy" in (captured.get("payload") or {})
    assert "high_retention_benchmarks" in (captured.get("payload") or {})
    cam_pol = decision.get("camera_policy") or {}
    assert "shunpo" in json.dumps(cam_pol).lower()
    assert any("dagger" in str(t).lower() for t in (cam_pol.get("shunpo_e_targets") or []))
    assert cam_pol.get("post_shunpo_action") == "center_on_katarina"
    assert "high_retention_benchmarks" in decision and decision["high_retention_benchmarks"].get("best_bucket") == "balanced_14_17s"





