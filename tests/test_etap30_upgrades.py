import json
import struct
from pathlib import Path
from unittest.mock import patch

from lol_agent import lol_editor, lol_metadata_generator, outplayed_db, synapsa_overnight_batch, synapsa_title_trainer
from lol_agent.multi_platform_copywriter import (
    _instagram_hashtags,
    generate_all_platform_copy,
    generate_instagram_copy,
)
from lol_agent.synapsa_engine import _AI_JARGON_PHRASES


def _v8_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _v8_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return b'"' + _v8_varint(len(raw)) + raw


def _v8_int(val: int) -> bytes:
    zz = (val << 1) ^ (val >> 31)
    return b"I" + _v8_varint(zz)


def _v8_double(val: float) -> bytes:
    return b"N" + struct.pack("<d", float(val))


def test_parse_idb_v8_records_decodes_match_kda_and_filters_trash():
    clip_path = r"C:\Users\dev\Videos\Overwolf\Outplayed\League of Legends\League of Legends_11-24-2026_19-28-34-486\League of Legends 11-24-2026 19-51-15-779_0.mp4"
    trash_path = r"C:\Users\dev\Videos\Overwolf\Outplayed\League of Legends\Recently Deleted\deleted_0.mp4"

    buf = b"".join([
        _v8_str("selectedChampion"), _v8_str("Katarina"),
        _v8_str("killCount"), _v8_int(18),
        _v8_str("assistCount"), _v8_int(10),
        _v8_str("deathCount"), _v8_int(11),
        _v8_str("isVictory"), b"T",
        _v8_str("startTime"), _v8_double(1732476514000.0),
        _v8_str("endTime"), _v8_double(1732476542000.0),
        _v8_str("isFavorite"), b"F",
        _v8_str("path"), _v8_str(clip_path),
        _v8_str("type"), _v8_str("kill"), _v8_str("time"), _v8_int(21500),
        _v8_str("label"), _v8_str("quadrakill"),
        _v8_str("past"), _v8_int(12000), _v8_str("future"), _v8_int(12000),
        b"o" + _v8_str("startTime") + _v8_double(1732476600000.0),
        _v8_str("endTime"), _v8_double(1732476615000.0),
        _v8_str("path"), _v8_str(trash_path),
        _v8_str("type"), _v8_str("kill"), _v8_str("time"), _v8_int(6000),
        _v8_str("label"), _v8_str("doublekill"),
    ])

    delta = outplayed_db._parse_idb_v8_records(buf)
    unique_paths = {v["raw_path"] for v in delta.values()}
    assert len(unique_paths) == 1
    assert not any("deleted_0.mp4" in k for k in delta)
    entry = next(iter(delta.values()))
    assert entry["champion"] == "Katarina"
    assert entry["match_kda"] == "18/11/10"
    assert entry["event_tier"] == "quadrakill"
    assert entry["event_tier_rank"] == 4
    assert abs(float(entry["best_event_time_s"]) - 21.5) < 0.01
    assert outplayed_db._build_clip_entry({"path": trash_path}, None, "outplayed_live") is None
    assert outplayed_db._build_clip_entry({"path": r"C:\Clips\.trash\old.mp4"}, None, "outplayed_live") is None


def test_p02_apply_outplayed_anchor_prevents_slow_intro_over_3_25s():
    clip_info = {
        "event_source": "outplayed_live",
        "best_event_time_s": 24.0,
        "event_tier": "doublekill",
        "event_tier_rank": 2,
        "best_event_past_s": 10.0,
        "best_event_future_s": 2.5,
        "events_summary": [
            {"type": "kill", "time_s": 20.5},
            {"type": "kill", "time_s": 24.0},
        ],
    }
    raw_kills = [{"timestamp": 20.5, "tier": 1}]
    _rk, _det, new_start, new_end, _pk, _segs = synapsa_overnight_batch._apply_outplayed_anchor(
        clip_info=clip_info,
        raw_kills=raw_kills,
        raw_det="doublekill",
        clip_start=12.0,
        clip_end=26.5,
        peak_moment=24.0,
        combat_segs=None,
        duration=35.0,
    )
    assert 20.5 - new_start <= 3.25
    assert new_end >= 26.8


def test_lol_editor_vignette_pill_and_auto_trim_intro_contract(tmp_path: Path):
    filters_multi = lol_editor.build_dynamic_captions_filters(
        peaks=[(2.0, "KILL"), (3.6, "DOUBLE KILL"), (5.2, "TRIPLE KILL"), (6.8, "QUADRAKILL")],
        trim_start=0.0,
        video_duration=12.0,
        peak_moment=6.8,
        action_type="quadrakill",
    )
    joined_multi = "\n".join(filters_multi)
    assert "4 KILLS IN 4.8S" in joined_multi
    assert "y=h*0.305" in joined_multi

    filters_clutch = lol_editor.build_dynamic_captions_filters(
        peaks=[(3.5, "SOLO BOLO")],
        trim_start=0.0,
        video_duration=9.0,
        peak_moment=3.5,
        action_type="clutch",
    )
    assert "1%% HP SURVIVAL" in "\n".join(filters_clutch)

    out_mp4 = tmp_path / "vignette_test.mp4"
    captured_fc = []

    def _cap_run(cmd, **_kw):
        fc = tmp_path / "vignette_test_filter.txt"
        if fc.exists():
            captured_fc.append(fc.read_text(encoding="utf-8"))
        return type("R", (), {"returncode": 0, "stderr": b"", "stdout": b""})()

    with patch("lol_agent.lol_editor._run_ffmpeg", side_effect=_cap_run), \
         patch("lol_agent.lol_editor.detect_hardware", return_value=("h264_nvenc", "nvenc")):
        lol_editor.apply_editor_effects(
            input_path="in.mp4",
            output_path=str(out_mp4),
            clip_duration=10.0,
            crop_x="656",
            peak_moment=7.0,
            zoom_level=1.18,
            zoom_duration=0.8,
            intermediate_peaks=[],
        )
    assert captured_fc and "vignette=angle=PI/7" in captured_fc[0]

    import inspect
    sig = inspect.signature(lol_editor.render_short)
    assert sig.parameters["auto_trim_intro"].default is False


def test_multi_platform_copywriter_and_metadata_no_spam():
    ig_tags = _instagram_hashtags("Katarina", "quadrakill")
    assert len(ig_tags) <= 6

    ig_copy = generate_instagram_copy(
        "Katarina",
        "pentakill",
        base_metadata={"title": "POV: Five Enemies. Zero Escape. 💀 #shorts #lol"},
    )
    cap_low = ig_copy["caption"].lower()
    assert "facebook.com" not in cap_low
    assert "tiktok:" not in cap_low
    assert "rate this" not in cap_low
    assert "1-10" not in cap_low

    with patch("lol_agent.multi_platform_copywriter._call_gemini", return_value=""):
        all_copy = generate_all_platform_copy(
            "Katarina",
            "double",
            base_metadata={"title": "Deleted in 2 Seconds Flat ⚡ #shorts #leagueoflegends"},
            platforms=["youtube", "tiktok", "instagram", "facebook"],
        )
    assert len(all_copy) == 4
    assert all_copy["facebook"]["title"].startswith("Deleted in 2 Seconds Flat")
    assert "#shorts" not in all_copy["facebook"]["caption"].lower()

    desc_solo = lol_metadata_generator.build_channel_description("Katarina", "solo_bolo")
    desc_dbl = lol_metadata_generator.build_channel_description("Katarina", "double")
    for d in (desc_solo, desc_dbl):
        assert "rate this" not in d.lower()
        assert "1-10" not in d


def test_synapsa_trainer_dataset_etap30_clean(tmp_path: Path):
    ds_file = tmp_path / "etap30_ds.jsonl"
    info = synapsa_title_trainer.build_training_dataset(
        output_path=ds_file,
        mine_youtube=False,
        write_file=True,
    )
    assert info["overnight_rank_examples"] >= 18
    rows = [json.loads(line) for line in ds_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == info["total_examples"]

    has_kebab = False
    has_nails = False
    bad_jargon = [j for j in _AI_JARGON_PHRASES]
    for r in rows:
        inst = r["instruction"]
        out_txt = r["output"]
        out_obj = json.loads(out_txt)
        if '"operation"' in out_txt and "montage_director" in inst.lower():
            assert out_obj["operation"] != "SPEED_RAMP_FLOW"
            assert out_obj["style"] in {"PRIMARY", "SPEED_RAMP_FLOW", "IN_MEDIA_RES"}
        if '"title_candidates"' in out_txt and '"champion": "Katarina"' in inst:
            blob = " ".join(out_obj.get("title_candidates", []) + [out_obj.get("description", ""), out_obj.get("hook_text", "")]).lower()
            for j in bad_jargon:
                assert j not in blob, f"AI jargon `{j}` leaked into training row: {blob}"
        if "FOOD_GASTRO" in inst:
            has_kebab = True
        if "NAILS_BEAUTY" in inst:
            has_nails = True

    assert has_kebab and has_nails
