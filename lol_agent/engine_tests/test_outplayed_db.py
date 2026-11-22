"""
Testy jednostkowe i integracyjne dla `lol_agent.outplayed_db` oraz ulepszeń Etapu 15
w `synapsa_overnight_batch.py`, `clips.py` i `overnight.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

import lol_agent.outplayed_db as opdb
import lol_agent.synapsa_overnight_batch as ob
from lol_agent.api.config import API_PASSWORD
from lol_agent.api.main import app


def _write_fake_backup(backup_dir: Path, filename: str, payload: Dict[str, Any], mtime: float = 1000.0) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    p = backup_dir / filename
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_pytest_isolation_blocks_default_appdata_read():
    """Przy domyślnych argumentach (None, None) w trakcie pytest load_outplayed_index zwraca {}."""
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert opdb.load_outplayed_index() == {}
    assert opdb.get_outplayed_clip_info("C:/fake/League of Legends 11-17-2026 18-24-25-826_0.mp4") is None


def test_parse_path_info_and_backup_records_and_corrupt_fallback(tmp_path: Path):
    """Parsuje backup library-*.json (zarówno string JSON jak dict/list), ignoruje zepsuty najnowszy plik."""
    backup_dir = tmp_path / "backup"
    idb_dir = tmp_path / "idb"
    idb_dir.mkdir(parents=True, exist_ok=True)

    clip_q = str(tmp_path / "Outplayed" / "League of Legends_11-17-2026_18-04-02-494" / "League of Legends 11-17-2026 18-24-25-826_0.mp4")
    clip_t = str(tmp_path / "Outplayed" / "League of Legends_11-18-2026_15-42-00-100" / "League of Legends 11-18-2026 16-02-49-130_0.mp4")
    clip_a = str(tmp_path / "Outplayed" / "League of Legends_11-18-2026_15-42-00-100" / "League of Legends 11-18-2026 16-05-00-000_0.mp4")
    clip_val = str(tmp_path / "Outplayed" / "Valorant" / "val_clip.mp4")

    matches_list = [
        {
            "gameId": 5426,
            "startTime": 1794938642000,
            "info": {"selectedChampion": "Katarina", "killCount": 25, "deathCount": 8, "assistCount": 4, "isVictory": False},
            "medias": [
                {
                    "path": clip_q,
                    "startTime": 100.0,
                    "endTime": 130.0,
                    "isFavorite": True,
                    "events": [
                        {"type": "kill", "time": 12000.0, "data": {"label": "kill"}},
                        {"type": "kill", "time": 19500.0, "timing": {"past": 10000, "future": 5000}, "data": json.dumps({"label": "quadra_kill"})},
                    ],
                },
                {
                    "path": clip_t,
                    "startTime": 200.0,
                    "endTime": 263.97,
                    "isFavorite": False,
                    "events": [
                        {"type": "kill", "time": 13130.0, "data": {"label": "kill"}},
                        {"type": "kill", "time": 31490.0, "data": {"label": "kill"}},
                        {"type": "kill", "time": 50090.0, "timing": {"past": 11000, "future": 4000}, "data": {"label": "triple_kill"}},
                    ],
                },
                {
                    "path": clip_a,
                    "startTime": 300.0,
                    "endTime": 318.0,
                    "isFavorite": False,
                    "events": [{"type": "assist", "time": 9000.0, "data": {"label": "assist"}}],
                },
            ],
        },
        {
            "gameId": 21640,  # Inna gra (Valorant) - ma być odfiltrowana
            "info": {"selectedChampion": "Jett"},
            "medias": [{"path": clip_val, "events": [{"type": "kill", "time": 3000.0, "data": {"label": "penta_kill"}}]}],
        },
    ]

    # Starszy poprawny backup (matches_0 jako JSON string, tak jak w prawdziwym Overwolf)
    _write_fake_backup(backup_dir, "library-2026-11-18T10-00-00Z.json", {"matches_0": json.dumps(matches_list)}, mtime=1000.0)
    # Nowszy uszkodzony backup — musi spaść na starszy poprawny bez crasha
    bad_p = backup_dir / "library-2026-11-19T10-00-00Z.json"
    bad_p.write_text("{CORRUPTED JSON", encoding="utf-8")
    os.utime(bad_p, (2000.0, 2000.0))

    idx = opdb.load_outplayed_index(backup_dir=backup_dir, idb_dir=idb_dir, force_reload=True)
    assert opdb.get_outplayed_clip_info(clip_val, index=idx) is None

    q_info = opdb.get_outplayed_clip_info(clip_q, index=idx)
    assert q_info is not None
    assert q_info["champion"] == "Katarina"
    assert q_info["is_favorite"] is True
    assert q_info["event_tier"] == "quadrakill"
    assert q_info["event_tier_rank"] == 4
    assert q_info["best_event_time_s"] == pytest.approx(19.5, abs=0.05)
    assert q_info["match_kda"] == "25/8/4"
    assert q_info["match_folder"] == "League of Legends_11-17-2026_18-04-02-494"
    assert q_info["match_date"] == "2026-11-17 18:04"
    assert q_info["total_kills_in_clip"] == 2

    t_info = opdb.get_outplayed_clip_info(clip_t, index=idx)
    assert t_info is not None
    assert t_info["event_tier"] == "triple"
    assert t_info["best_event_time_s"] == pytest.approx(50.09, abs=0.05)

    a_info = opdb.get_outplayed_clip_info(clip_a, index=idx)
    assert a_info is not None
    assert a_info["event_tier"] == "assist_only"
    assert a_info["event_tier_rank"] == 0


def test_live_idb_delta_overrides_favorite_and_adds_new_clip(tmp_path: Path):
    """Delta z IndexedDB *.log aktualizuje isFavorite i dokłada nowy klip ponad backup JSON."""
    backup_dir = tmp_path / "backup"
    idb_dir = tmp_path / "idb"
    idb_dir.mkdir(parents=True, exist_ok=True)

    c1 = str(tmp_path / "League of Legends_11-19-2026_12-00-00-000" / "League of Legends 11-19-2026 12-10-00-000_0.mp4")
    c2 = str(tmp_path / "League of Legends_11-19-2026_12-00-00-000" / "League of Legends 11-19-2026 12-15-00-000_0.mp4")

    _write_fake_backup(
        backup_dir,
        "library-1.json",
        {
            "matches_0": [
                {
                    "gameId": 5426,
                    "info": {"selectedChampion": "Katarina"},
                    "medias": [
                        {
                            "path": c1,
                            "startTime": 10.0,
                            "endTime": 30.0,
                            "isFavorite": False,
                            "events": [{"type": "kill", "time": 12000.0, "data": {"label": "double_kill"}}],
                        }
                    ],
                }
            ]
        },
    )

    # Symulowany binarny plik LevelDB *.log z losowymi bajtami wokół JSONów UTF-8
    frag1 = json.dumps({"path": c1, "isFavorite": True, "events": []}).encode("utf-8")
    frag2 = json.dumps(
        {
            "gameId": 5426,
            "info": {"selectedChampion": "Katarina", "killCount": 14, "deathCount": 2, "assistCount": 5},
            "medias": [
                {
                    "path": c2,
                    "startTime": 50.0,
                    "endTime": 75.0,
                    "isFavorite": False,
                    "events": [{"type": "kill", "time": 14500.0, "data": {"label": "penta_kill"}}],
                }
            ],
        }
    ).encode("utf-8")
    (idb_dir / "000100.log").write_bytes(b"\x00\xff\x12garbage" + frag1 + b"\xde\xad\xbe\xef" + frag2 + b"\x01\x02")

    idx = opdb.load_outplayed_index(backup_dir=backup_dir, idb_dir=idb_dir, force_reload=True)
    i1 = opdb.get_outplayed_clip_info(c1, index=idx)
    assert i1 is not None
    assert i1["is_favorite"] is True
    assert i1["event_tier"] == "double"  # zachowany wyższy tier z backupu

    i2 = opdb.get_outplayed_clip_info(c2, index=idx)
    assert i2 is not None
    assert i2["source"] == "outplayed_live"
    assert i2["event_tier"] == "pentakill"
    assert i2["event_tier_rank"] == 5
    assert i2["champion"] == "Katarina"
    assert i2["match_kda"] == "14/2/5"


def test_prefilter_skips_assist_wrong_champ_and_single_when_multikills_available(monkeypatch, tmp_path: Path):
    """Pre-filtr musi odrzucać assist_only, innego bohatera i single_kill (w auto) bez uruchamiania OCR."""
    analyzed_paths: list[str] = []

    def _make_clip(name: str, tier: str, rank: int, champ: str = "Katarina", match_f: str = "M1", base_suffix: str = "") -> Dict[str, Any]:
        fp = tmp_path / f"{name}.mp4"
        fp.write_bytes(b"0" * 1024)
        bk = base_suffix or name
        return {
            "filename": fp.name,
            "path": str(fp),
            "size_mb": 10.0,
            "modified": 100.0,
            "already_published": False,
            "champion": champ,
            "is_favorite": tier == "quadrakill",
            "event_tier": tier,
            "event_tier_rank": rank,
            "event_source": "outplayed_backup",
            "best_event_time_s": 14.0,
            "total_kills_in_clip": max(1, rank),
            "match_folder": match_f,
            "match_date": "2026-11-18 16:00",
            "clip_base_key": f"{match_f.lower()}::{bk}",
            "match_kda": "18/4/6",
        }

    fake_clips = [
        _make_clip("q_kata", "quadrakill", 4, "Katarina", "M1"),
        _make_clip("t_kata", "triple", 3, "Katarina", "M2"),
        _make_clip("d_kata_0", "double", 2, "Katarina", "M3", base_suffix="d_kata"),
        _make_clip("d_kata_1", "double", 2, "Katarina", "M3", base_suffix="d_kata"),  # duplikat _1
        _make_clip("s_kata", "single_kill", 1, "Katarina", "M1"),
        _make_clip("a_kata", "assist_only", 0, "Katarina", "M1"),
        _make_clip("t_yone", "triple", 3, "Yone", "M4"),
    ]

    import lol_agent.api.routers.clips as clips_router
    monkeypatch.setattr(clips_router, "scan_available_clips", lambda folder=None: list(fake_clips))

    def _fake_analyze(cl: Dict[str, Any]) -> Dict[str, Any]:
        analyzed_paths.append(cl["filename"])
        rk = int(cl.get("event_tier_rank") or 1)
        return ob._score_and_classify_candidate({
            **cl,
            "clip_start": 2.0,
            "clip_end": 18.0,
            "peak_moment": 14.0,
            "kills": [{"timestamp": 14.0, "tier": rk, "label": str(cl.get("event_tier") or "KILL").upper()}],
            "confidence": 0.9,
            "min_hp_percentage": 45.0,
            "is_clutch_1hp": False,
            "objective_secured": False,
            "ally_banner_blocked": False,
            "player_died": False,
            "raw_viable": True,
        })

    monkeypatch.setattr(ob, "_analyze_single_clip_for_overnight", _fake_analyze)

    res = ob.scan_and_rank_all_clips(
        folder=None,
        top_n=3,
        skip_published=True,
        use_cache=False,
        max_workers=1,
        champion_name="Katarina",
        tier_filter="auto",
        only_channel_champion=True,
    )

    # single_kill, assist_only i Yone nie mogły trafić do OCR!
    assert "a_kata.mp4" not in analyzed_paths
    assert "t_yone.mp4" not in analyzed_paths
    assert "s_kata.mp4" not in analyzed_paths
    bd = res["rejection_breakdown"]
    assert bd.get("REJECT_ASSIST_ONLY") == 1
    assert bd.get("REJECT_WRONG_CHAMPION") == 1
    assert bd.get("REJECT_SINGLE_KILL_MULTIKILLS_AVAILABLE") == 1

    # Duplikaty _0/_1 nigdy razem w Top N (max 1 z base_key "m3::d_kata")
    selected_names = [s["filename"] for s in res["selected"]]
    assert "q_kata.mp4" in selected_names
    assert "t_kata.mp4" in selected_names
    assert not ("d_kata_0.mp4" in selected_names and "d_kata_1.mp4" in selected_names)
    assert len(selected_names) == 3

    # Test jawnego filtra triple_plus -> odcina także double przed OCR
    analyzed_paths.clear()
    res_t3 = ob.scan_and_rank_all_clips(
        top_n=2,
        use_cache=False,
        max_workers=1,
        champion_name="Katarina",
        tier_filter="triple_plus",
        only_channel_champion=True,
    )
    assert set(analyzed_paths) == {"q_kata.mp4", "t_kata.mp4"}
    assert res_t3["rejection_breakdown"].get("REJECT_TIER_FILTER", 0) >= 2


def test_apply_outplayed_anchor_rescues_late_triple_in_64s_clip():
    """64s klip z triple_kill @ 50.09s, gdy OCR złapał tylko początek, musi zostać przekotwiczony na ~38..53s."""
    clip_info = {
        "event_source": "outplayed_backup",
        "event_tier": "triple",
        "event_tier_rank": 3,
        "best_event_time_s": 50.09,
        "best_event_past_s": 11.0,
        "best_event_future_s": 3.2,
        "events_summary": [
            {"type": "kill", "label": "kill", "time_s": 13.13},
            {"type": "kill", "label": "kill", "time_s": 31.49},
            {"type": "kill", "label": "triple_kill", "time_s": 50.09},
        ],
    }
    raw_kills = [{"timestamp": 13.1, "tier": 1, "label": "KILL"}]
    kills, det, cs, ce, peak, _segs = ob._apply_outplayed_anchor(
        clip_info=clip_info,
        raw_kills=raw_kills,
        raw_det="solo_bolo",
        clip_start=5.0,
        clip_end=19.0,
        peak_moment=13.1,
        combat_segs=[(5.0, 19.0)],
        duration=63.97,
    )
    assert det == "triple"
    assert cs >= 40.0
    assert ce >= 52.5
    assert cs < 50.09 < ce
    assert (ce - cs) <= 13.5
    assert peak == pytest.approx(50.09, abs=0.05)
    assert any(int(k.get("tier") or 0) == 3 and abs(float(k["timestamp"]) - 50.09) < 0.5 for k in kills)


def test_polish_note_guard_and_diversity_across_matches():
    """Strażnik komentarza PL odrzuca halucynacje LoRA i niespójne oceny liczbowe; selekcja dywersyfikuje mecze."""
    item = {
        "final_score": 81.1,
        "hype_score": 82.0,
        "watchability_score": 78.5,
        "qa_score": 86,
        "action_type": "triple",
        "defects": [],
        "has_critical_defect": False,
    }
    assert ob._is_clean_consistent_polish_note("Solidna Katarina Triple Kill, final=81.1/100 przy czytelnej klatce startowej.", item)
    assert not ob._is_clean_consistent_polish_note("3-triunfowa katarinska akcja idealna!", item)
    assert not ob._is_clean_consistent_polish_note("Świetny klip wynik final=68.0/100 z czystą kamerą.", item)
    assert not ob._is_clean_consistent_polish_note("Dobry klip Русский текст final=81.1.", item)
    assert not ob._is_clean_consistent_polish_note("Idealny klip bez żadnej wady w tym zestawieniu!", {**item, "has_critical_defect": True})
    assert not ob._is_clean_consistent_polish_note("Dwuekranowy dwufragowy (71.0) w dobrej walce drużynowej.", item)
    assert not ob._is_clean_consistent_polish_note("Trójka fragów z regresją (70.0) w tej akcji Katariny.", {**item, "action_type": "double"})
    assert not ob._is_clean_consistent_polish_note("Regresja po 2 fragach z czystą widocznością gracza.", {**item, "action_type": "double"})
    assert not ob._is_clean_consistent_polish_note("Trójka fragów z obiektywem 97.02 — bez wątpliwości najlepszy wynik z ostatnich kilku dni.", {**item, "overnight_rank": 5, "defects": ["low_player_visibility"]})
    assert not ob._is_clean_consistent_polish_note("Trójka fragów Katariny ocena 97.02 bardzo dynamiczna akcja.", {**item, "overnight_rank": 2})

    # Dywersyfikacja między meczami: maks. 2 z tego samego meczu w pierwszym przebiegu
    q = [
        {"path": f"C:/clips/M1/c{i}.mp4", "clip_base_key": f"m1::c{i}", "match_folder": "M1", "hype_score": 90 - i, "kill_count": 3, "is_favorite": False}
        for i in range(4)
    ] + [
        {"path": "C:/clips/M2/c0.mp4", "clip_base_key": "m2::c0", "match_folder": "M2", "hype_score": 80, "kill_count": 2, "is_favorite": True}
    ]
    sel = ob._select_top_diverse_candidates(q, [], top_n=3)
    m1_cnt = sum(1 for x in sel if x["match_folder"] == "M1")
    m2_cnt = sum(1 for x in sel if x["match_folder"] == "M2")
    assert m1_cnt == 2
    assert m2_cnt == 1


def test_overnight_catalog_and_recently_deleted_filter(monkeypatch, tmp_path: Path):
    """Endpoint /overnight/catalog grupuje tiery/mecze, a scan_available_clips omija Recently Deleted."""
    import lol_agent.api.routers.clips as clips_router
    import lol_agent.api.routers.overnight as overnight_router

    op_root = tmp_path / "Outplayed" / "League of Legends"
    match_dir = op_root / "League of Legends_11-18-2026_16-12-00-000"
    trash_dir = tmp_path / "Outplayed" / "Recently Deleted"
    match_dir.mkdir(parents=True)
    trash_dir.mkdir(parents=True)

    keep_file = match_dir / "League of Legends 11-18-2026 16-20-00-000_0.mp4"
    trash_file = trash_dir / "deleted_clip.mp4"
    keep_file.write_bytes(b"x" * (4 * 1024 * 1024))
    trash_file.write_bytes(b"x" * (4 * 1024 * 1024))

    monkeypatch.setattr(clips_router, "LOL_INPUT_DIR", tmp_path / "empty_in")
    monkeypatch.setattr(clips_router, "check_duplicate_clip", None, raising=False)
    monkeypatch.setattr(
        clips_router,
        "load_outplayed_index",
        lambda: {
            opdb._norm_path_key(str(keep_file.resolve())): {
                "source": "outplayed_backup",
                "champion": "Katarina",
                "is_favorite": True,
                "event_tier": "triple",
                "event_tier_rank": 3,
                "best_event_time_s": 12.5,
                "total_kills_in_clip": 3,
                "match_folder": match_dir.name,
                "match_date": "2026-11-18 16:12",
                "clip_base_key": f"{match_dir.name.lower()}::league of legends 11-18-2026 16-20-00-000",
                "match_kda": "21/3/7",
            }
        },
    )

    scanned = clips_router.scan_available_clips(str(tmp_path / "Outplayed"))
    names = [c["filename"] for c in scanned]
    assert keep_file.name in names
    assert "deleted_clip.mp4" not in names
    assert scanned[0]["event_tier"] == "triple"
    assert scanned[0]["champion"] == "Katarina"

    monkeypatch.setattr(overnight_router, "scan_available_clips", lambda folder=None: scanned)

    captured: Dict[str, Any] = {}
    def _mock_start(**kw):
        captured.update(kw)
        return True
    monkeypatch.setattr(ob, "start_overnight_batch_async", _mock_start)

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        cat_res = client.get("/overnight/catalog?champion_name=Katarina", headers=headers)
        assert cat_res.status_code == 200
        cat = cat_res.json()
        assert cat["total_clips"] == 1
        assert cat["multikill_clips"] == 1
        assert cat["favorites_count"] == 1
        assert cat["tier_counts"]["triple"] == 1
        assert cat["matches_count"] == 1

        st_res = client.post(
            "/overnight/start",
            json={"top_n": 5, "champion_name": "Katarina", "tier_filter": "triple_plus", "only_channel_champion": True},
            headers=headers,
        )
        assert st_res.status_code == 200
        assert captured.get("tier_filter") == "triple_plus"
        assert captured.get("only_channel_champion") is True


def test_merged_multikill_midpoint_est_last_kill_and_chronological_outro(tmp_path: Path):
    """Scalony event Outplayed (past == future) wylicza est_last_kill_s i chroni końcówkę walki przed ucięciem."""
    from lol_agent.lol_frag_detector import FragAnalysisResult, compute_optimal_clip_window

    clip_path = tmp_path / "League of Legends_11-18-2026_15-42-45-373" / "League of Legends 11-18-2026 16-02-49-130_0.mp4"
    backup_dir = tmp_path / "backup"
    idb_dir = tmp_path / "idb"
    idb_dir.mkdir(parents=True, exist_ok=True)
    _write_fake_backup(
        backup_dir,
        "library-1.json",
        {
            "matches_0": [
                {
                    "gameId": 5426,
                    "info": {"selectedChampion": "Katarina"},
                    "medias": [
                        {
                            "path": str(clip_path),
                            "startTime": 1191.61,
                            "endTime": 1255.58,
                            "events": [
                                {
                                    "type": "kill",
                                    "time": 50086.5,
                                    "timing": {"past": 13836.5, "future": 13836.5},
                                    "data": {"label": "triple_kill"},
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )
    idx = opdb.load_outplayed_index(backup_dir=backup_dir, idb_dir=idb_dir, force_reload=True)
    info = opdb.get_outplayed_clip_info(clip_path, index=idx)
    assert info is not None
    assert info["est_last_kill_s"] == pytest.approx(55.93, abs=0.05)
    assert info["est_first_kill_s"] == pytest.approx(48.25, abs=0.05)

    _kills, _det, cs, ce, peak, _segs = ob._apply_outplayed_anchor(
        clip_info={**info, "event_source": "outplayed_backup"},
        raw_kills=[{"timestamp": 47.0, "tier": 1, "label": "OUTPLAY"}],
        raw_det="outplay",
        clip_start=5.0,
        clip_end=20.0,
        peak_moment=15.0,
        combat_segs=None,
        duration=63.97,
    )
    assert ce >= 57.5, f"Okno ucięłoby finałowego killa (~55.9s): [{cs}, {ce}]"
    assert cs <= 46.0
    assert peak >= 55.0

    # Chronologicznie późniejszy kill (np. kill @ 11.0 po double @ 7.0) nie może zostać ucięty w compute_optimal_clip_window
    f_res = FragAnalysisResult(
        video_path="",
        duration=25.0,
        detected_frag_type="double",
        confidence=0.9,
        kill_count=3,
        kills=[
            {"timestamp": 3.0, "label": "KILL", "type": "kill", "tier": 1},
            {"timestamp": 7.0, "label": "DOUBLE KILL", "type": "double", "tier": 2},
            {"timestamp": 11.0, "label": "KILL", "type": "kill", "tier": 1},
        ],
        min_hp_percentage=55.0,
        is_clutch_1hp=False,
        badge_label="DOUBLE KILL",
        suggested_title_hook="DOUBLE",
        suggested_badge_color="#FFFFFF",
    )
    ws, we, _wp, _wsegs = compute_optimal_clip_window(f_res, total_dur=25.0, action_type="double")
    assert we >= 12.65 and (we - 11.0) <= 2.0, f"Outro po chronologicznie ostatnim killu (11.0s) nie mieści się w 1.65..2.0s: [{ws}, {we}]"


def test_thumbnail_upload_regenerate_and_overnight_backfill(monkeypatch, tmp_path: Path):
    """Testuje backfill miniaturek w paczce nocnej oraz upload/regenerate/stream i ochronę path-traversal."""
    import io
    from PIL import Image
    import lol_agent.api.helpers as api_helpers
    import lol_agent.api.routers.clips as clips_router
    import lol_agent.lol_thumbnail as lol_thumb

    temp_dir = tmp_path / "lol_temp"
    out_dir = tmp_path / "lol_output"
    on_dir = tmp_path / "overnight_batches"
    temp_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    on_dir.mkdir(parents=True)
    latest_file = on_dir / "latest_batch.json"

    video_name = "short_overnight_test_r1_triple.mp4"
    video_fp = temp_dir / video_name
    video_fp.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"0" * 1024)
    stale_out_thumb = out_dir / "short_overnight_test_r1_triple_thumb.jpg"
    Image.new("RGB", (108, 192), (10, 10, 10)).save(stale_out_thumb, format="JPEG")

    latest_file.write_text(
        json.dumps(
            {
                "batch_id": "test_batch_thumb",
                "status": "done",
                "items": [
                    {
                        "overnight_rank": 1,
                        "output_filename": video_name,
                        "output_path": str(video_fp),
                        "thumbnail_path": None,
                        "champion_name": "Katarina",
                        "action_type": "triple",
                        "peak_moment": 8.0,
                        "clip_start": 2.0,
                        "verdict": "PICK_WINNER",
                        "render_ok": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ob, "OVERNIGHT_DIR", on_dir)
    monkeypatch.setattr(ob, "LATEST_BATCH_FILE", latest_file)
    monkeypatch.setattr(clips_router, "LOL_TEMP_DIR", temp_dir)
    monkeypatch.setattr(clips_router, "LOL_OUTPUT_DIR", out_dir)
    monkeypatch.setattr(api_helpers, "LOL_TEMP_DIR", temp_dir)
    monkeypatch.setattr(api_helpers, "LOL_OUTPUT_DIR", out_dir)

    # 1. Backfill w load_latest_overnight_batch gdy thumbnail_path / thumbnail_filename nie były zapisane
    thumb_fp = temp_dir / "short_overnight_test_r1_triple_thumb.jpg"
    Image.new("RGB", (108, 192), (30, 40, 50)).save(thumb_fp, format="JPEG")
    loaded = ob.load_latest_overnight_batch()
    assert loaded is not None
    assert loaded["items"][0]["thumbnail_filename"] == thumb_fp.name
    assert loaded["items"][0]["thumbnail_path"] == str(thumb_fp)

    with TestClient(app) as client:
        login = client.post("/auth/login", json={"password": API_PASSWORD})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # 2. Upload własnego PNG -> konwersja 1080x1920 JPEG + aktualizacja .meta.json i latest_batch.json
        png_buf = io.BytesIO()
        Image.new("RGB", (640, 360), (220, 30, 30)).save(png_buf, format="PNG")
        png_buf.seek(0)
        up_res = client.post(
            f"/outputs/{video_name}/thumbnail",
            files={"file": ("custom.png", png_buf.getvalue(), "image/png")},
            headers=headers,
        )
        assert up_res.status_code == 200, up_res.text
        up_json = up_res.json()
        assert up_json["thumbnail_filename"] == thumb_fp.name
        assert not stale_out_thumb.exists(), "Stary duplikat miniaturki w LOL_OUTPUT_DIR powinien zostać usunięty"
        with Image.open(thumb_fp) as saved_img:
            assert saved_img.size == (1080, 1920)

        meta_saved = api_helpers._load_meta(video_name)
        assert meta_saved.get("thumbnail_path") == str(thumb_fp)

        # 3. GET /thumbnails/{name} + Cache-Control + blokada path traversal
        get_res = client.get(f"/thumbnails/{thumb_fp.name}")
        assert get_res.status_code == 200
        assert get_res.headers.get("content-type", "").startswith("image/jpeg")
        assert "no-cache" in (get_res.headers.get("cache-control") or "").lower()

        with pytest.raises(clips_router.HTTPException) as exc_info:
            clips_router._sanitize_single_filename("../secret.jpg")
        assert exc_info.value.status_code == 400

        for bad_url in ("/thumbnails/foo..bar.jpg", "/thumbnails/..%5Csecret.jpg"):
            bad_res = client.get(bad_url)
            assert bad_res.status_code in (400, 404), f"{bad_url} -> {bad_res.status_code}"
            assert not bad_res.headers.get("content-type", "").startswith("image/")

        # Uwaga: httpx normalizuje RFC3986 '/../' przed wysyłką do '/', więc SPA może zwrócić text/html, nigdy obraz/sekret
        norm_res = client.get("/thumbnails/..%2Fsecret.jpg")
        assert norm_res.status_code in (200, 400, 404)
        assert not norm_res.headers.get("content-type", "").startswith("image/")
        assert "thumb_fp" not in norm_res.text

        # 4. Regeneracja miniaturki
        def _fake_generate(video_path: str, peak_moment: float, action_label: str, champion_name: str = "", output_path: str = None, **_kw):
            assert Path(video_path).name == video_name
            assert action_label == "TRIPLE"
            assert champion_name == "Katarina"
            Image.new("RGB", (1080, 1920), (20, 180, 90)).save(output_path, format="JPEG")
            return output_path

        monkeypatch.setattr(lol_thumb, "generate_thumbnail", _fake_generate)
        reg_res = client.post(f"/outputs/{video_name}/thumbnail/regenerate", headers=headers)
        assert reg_res.status_code == 200, reg_res.text
        reg_json = reg_res.json()
        assert reg_json["thumbnail_filename"] == thumb_fp.name
        with Image.open(thumb_fp) as reg_img:
            assert reg_img.size == (1080, 1920)
        assert not list(temp_dir.glob("*.tmp"))
        assert not list(temp_dir.glob("*.regen_*"))
