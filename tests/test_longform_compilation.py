import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from lol_agent import lol_editor, lol_metadata_generator, scheduled_queue, state_db, synapsa_overnight_batch, viral_vault
from lol_agent.lol_longform_montage import _probe_media, render_longform_compilation
from lol_agent.lol_longform_thumbnail import LONGFORM_H, LONGFORM_W, MAX_THUMB_BYTES, generate_longform_thumbnail
from lol_agent.synapsa_engine import strip_rank_prefix


def _make_synthetic_tab_clip(path: Path) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (640, 360))
    bright = np.full((360, 640, 3), (90, 145, 195), dtype=np.uint8)
    # Symulacja tabeli TAB w centrum kadru (ciemne tło + poziome linie wierszy)
    tab = np.full((360, 640, 3), (38, 36, 34), dtype=np.uint8)
    for y in range(70, 290, 14):
        cv2.line(tab, (110, y), (530, y), (210, 210, 210), 2)
    for i in range(150):
        fr = bright if i < 115 else tab
        writer.write(fr)
    writer.release()


def _make_av_clip(path: Path, dur_s: float = 3.2, color: str = "blue") -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", f"{dur_s:.2f}", "-i", f"color=c={color}:s=640x360:r=30",
        "-f", "lavfi", "-t", f"{dur_s:.2f}", "-i", "sine=frequency=440:sample_rate=48000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def test_p02b_prefix_strip_single_peak_double_and_tab_detector(tmp_path: Path):
    assert strip_rank_prefix("Master Tier Ego Check 💀") == "Ego Check 💀"
    assert strip_rank_prefix("Tier Ego Check 💀 Triple Kill CHAOS") == "Ego Check 💀 Triple Kill CHAOS"
    assert strip_rank_prefix("Challenger Elo Clean Outplay") == "Clean Outplay"

    tab_mp4 = tmp_path / "tab_outro.mp4"
    _make_synthetic_tab_clip(tab_mp4)
    t_tab = lol_editor._detect_tab_scoreboard_start(str(tab_mp4), 0.0, 14.8, 9.2)
    assert t_tab is not None
    assert 11.2 <= t_tab <= 12.6

    # Jednopikowy DOUBLE bez drugiego zabójstwa przed nim nie może cofać startu o 8.5s
    clip_info = {
        "event_source": "outplayed_live",
        "best_event_time_s": 24.0,
        "event_tier": "double",
        "event_tier_rank": 2,
        "best_event_past_s": 9.5,
        "best_event_future_s": 2.8,
        "events_summary": [{"type": "kill", "time_s": 24.0}],
    }
    _rk, _det, new_start, _end, _pk, _segs = synapsa_overnight_batch._apply_outplayed_anchor(
        clip_info=clip_info,
        raw_kills=[],
        raw_det="double",
        clip_start=0.0,
        clip_end=26.5,
        peak_moment=24.0,
        combat_segs=None,
        duration=32.0,
    )
    assert 24.0 - new_start <= 4.7


def test_p11_state_db_and_scheduled_queue_sync(tmp_path: Path, monkeypatch):
    q_file = tmp_path / "scheduled_social_queue.json"
    vid = tmp_path / "short.mp4"
    vid.write_bytes(b"mp4")
    monkeypatch.setattr(scheduled_queue, "QUEUE_FILE", q_file)

    entry = scheduled_queue.queue_scheduled_post(
        platform="instagram",
        video_path=str(vid),
        caption="Clean Katarina triple",
        publish_at="2026-11-28T18:00:00Z",
    )
    assert entry["id"]
    db_path = q_file.with_suffix(".db")
    assert db_path.is_file()
    rows = state_db.load_queue_from_db(db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["id"] == entry["id"]

    # Test migracji legacy JSON/JSONL do SQLite w izolowanym katalogu
    la_dir = tmp_path / "la"
    la_dir.mkdir()
    (la_dir / "published_videos.jsonl").write_text(
        json.dumps({"video_id": "abc123", "title": "Test", "timestamp": "2026-11-25T00:00:00Z"}) + "\n",
        encoding="utf-8",
    )
    acc_dir = tmp_path / "acc"
    acc_dir.mkdir()
    (acc_dir / "scheduled_social_queue.json").write_text(json.dumps(rows), encoding="utf-8")
    mig = state_db.migrate_legacy_json_to_sqlite(acc_dir, la_dir, db_path=tmp_path / "mig.db")
    assert mig["queue_migrated"] == 1
    assert mig["published_migrated"] == 1


def test_viral_vault_staging_promotion_and_expiry(tmp_path: Path):
    vdir = tmp_path / "vault"
    src_hit = tmp_path / "hit_double.mp4"
    src_flop = tmp_path / "flop_double.mp4"
    src_quad = tmp_path / "instant_quadra.mp4"
    for p in (src_hit, src_flop, src_quad):
        p.write_bytes(b"video_payload")

    r1 = viral_vault.stage_short_original(src_hit, yt_video_id="yt_hit", metadata={"action_type": "double", "champion": "Katarina"}, vault_dir=vdir)
    r2 = viral_vault.stage_short_original(src_flop, yt_video_id="yt_flop", metadata={"action_type": "double", "champion": "Katarina"}, vault_dir=vdir)
    r3 = viral_vault.stage_short_original(src_quad, yt_video_id="yt_quad", metadata={"action_type": "quadrakill", "champion": "Katarina"}, vault_dir=vdir)
    assert r1["ok"] and r1["item"]["state"] == "staging"
    assert r2["ok"] and r2["item"]["state"] == "staging"
    assert r3["ok"] and r3["item"]["state"] == "approved"

    # Promocja yt_hit po >=2000 wyświetleń; yt_flop po 15 dniach wygasa ze staging bez ruszania pliku źródłowego
    promo = viral_vault.evaluate_and_promote_vault(
        [{"video_id": "yt_hit", "views": 2540, "avg_view_percentage": 96.5}],
        channel_median_views=1593.5,
        stale_days=14,
        now_utc=datetime.now(timezone.utc) + timedelta(days=15),
        vault_dir=vdir,
    )
    assert promo["promoted"] == 1
    assert promo["expired"] == 1
    assert src_flop.is_file()  # Oryginał musi pozostać nietknięty!

    selected = viral_vault.select_clips_for_compilation(mode="weekly", champion="Katarina", vault_dir=vdir)
    ids = {c["yt_video_id"] for c in selected}
    assert ids == {"yt_hit", "yt_quad"}


def test_longform_montage_thumbnail_and_seo(tmp_path: Path):
    c1 = tmp_path / "clip1.mp4"
    c2 = tmp_path / "clip2.mp4"
    _make_av_clip(c1, dur_s=3.4, color="navy")
    _make_av_clip(c2, dur_s=3.4, color="darkred")

    out_mp4 = tmp_path / "weekly_pilot.mp4"
    clips = [
        {"resolved_media_path": str(c1), "champion": "Katarina", "action_type": "double", "views": 2100, "match_kda": "12/4/5", "clip_start": 0.0, "clip_end": 3.4, "peaks": [[2.0, "DOUBLE KILL"]]},
        {"resolved_media_path": str(c2), "champion": "Katarina", "action_type": "quadrakill", "views": 3800, "match_kda": "21/6/9", "clip_start": 0.0, "clip_end": 3.4, "peaks": [[2.2, "QUADRAKILL"]]},
    ]
    manifest = render_longform_compilation(
        clips=clips,
        output_path=out_mp4,
        mode="weekly",
        champion="Katarina",
        music_dir=tmp_path / "no_music",
    )
    assert out_mp4.is_file()
    dur, has_a = _probe_media(out_mp4)
    assert dur >= 10.0
    assert has_a is True
    assert manifest["clips_count"] == 2

    # Weryfikacja 1920x1080
    probe_dim = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out_mp4)],
        capture_output=True, text=True,
    )
    assert probe_dim.stdout.strip() == "1920,1080"

    # Miniatura 1280x720 < 2 MB
    thumb_p = tmp_path / "thumb_16_9.jpg"
    generate_longform_thumbnail(c2, peak_time_s=1.5, headline="1 HP 1V4?!", subline="KATARINA WEEKLY #1", output_path=thumb_p)
    assert thumb_p.is_file()
    assert thumb_p.stat().st_size <= MAX_THUMB_BYTES
    with Image.open(thumb_p) as im:
        assert im.size == (LONGFORM_W, LONGFORM_H)

    # Metadane: brak #shorts, rozdziały tylko >= 360s, dokładnie 3 hasztagi
    meta_short = lol_metadata_generator.generate_longform_metadata("Katarina", clips, 240.0, manifest["chapters"], ["ncs_royalty"], use_local_ai=False)
    assert meta_short["chapters_included"] is False
    assert "#shorts" not in meta_short["title"].lower()
    assert "#shorts" not in meta_short["description"].lower()
    assert len(meta_short["hashtags"]) == 3

    meta_long = lol_metadata_generator.generate_longform_metadata("Katarina", clips, 520.0, manifest["chapters"], ["ncs_royalty"], use_local_ai=False)
    assert meta_long["chapters_included"] is True
    assert "Chapters:" in meta_long["description"]


def test_uploader_is_short_false_and_compilations_router(tmp_path: Path, monkeypatch):
    import importlib
    from lol_agent.api import youtube_uploader
    from lol_agent.api.auth import verify_token_flexible
    from lol_agent.api.main import app

    youtube_uploader = importlib.reload(youtube_uploader)

    vid_file = tmp_path / "comp.mp4"
    vid_file.write_bytes(b"mp4bytes")
    captured_bodies = []

    class _FakeReq:
        def __init__(self, body):
            self._body = body
        def next_chunk(self):
            return None, {"id": "lf_vid_999", "snippet": {"title": self._body["snippet"]["title"]}, "status": {"privacyStatus": "private"}}

    fake_yt = MagicMock()
    def _fake_insert(**kwargs):
        captured_bodies.append(kwargs["body"])
        return _FakeReq(kwargs["body"])
    fake_yt.videos.return_value.insert.side_effect = _fake_insert

    monkeypatch.setattr(youtube_uploader, "LOL_AGENT_DIR", tmp_path)
    with patch.object(youtube_uploader, "get_valid_credentials", return_value=MagicMock()), \
         patch.object(youtube_uploader, "build", return_value=fake_yt):
        res = youtube_uploader.upload_video(
            video_path=str(vid_file),
            title="Why Nobody Steps Up To Katarina | Best Plays",
            description="Clean highlights.\n\n#LeagueOfLegends #Katarina #LoLMontage",
            tags=["league of legends", "katarina montage"],
            privacy="private",
            is_short=False,
        )

    assert res["video_format"] == "longform"
    assert res["url"] == "https://www.youtube.com/watch?v=lf_vid_999"
    assert "#shorts" not in captured_bodies[0]["snippet"]["title"].lower()
    assert "#shorts" not in captured_bodies[0]["snippet"]["description"].lower()
    assert (tmp_path / "latest_longform_video.json").is_file()

    # Router /compilations/* + ochrona path traversal
    app.dependency_overrides[verify_token_flexible] = lambda: {"sub": "test"}
    try:
        client = TestClient(app)
        with patch("lol_agent.viral_vault.get_vault_summary", return_value={"vault_dir": str(tmp_path), "counts": {"staging": 0, "approved": 2, "expired": 0, "rendered": 1}, "items": []}), \
             patch("lol_agent.api.youtube_uploader.get_related_video_studio_links", return_value={"target_longform": None, "shorts": [], "api_limitation_note": "Studio only"}):
            rv = client.get("/compilations/vault")
            assert rv.status_code == 200
            assert rv.json()["vault"]["counts"]["approved"] == 2

        rl = client.get("/compilations/list")
        assert rl.status_code == 200

        r_bad = client.get("/compilations/media/..%2F..%2Fsecret.mp4")
        assert r_bad.status_code in (400, 404)
    finally:
        app.dependency_overrides.clear()
