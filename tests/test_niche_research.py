"""
Testy Etapu 29: Presety lokalne, dekonstrukcja wideo YT OpenCV, strażnik anty-plagiatu,
komercyjny renderer 9:16 (pitch mockup + multi-shot), detektor zdarzeń i API /research.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from lol_agent import niche_research_engine as nre
from lol_agent.account_manager import CONTENT_MODE_PRESETS
from lol_agent.ad_event_detector import detect_ad_events
from lol_agent.api.config import API_PASSWORD
from lol_agent.api.main import app
from lol_agent.commercial_montage import (
    _find_ffprobe,
    _probe_video,
    render_commercial_multishot,
    render_commercial_pitch_mockup,
)
from lol_agent.synapsa_engine import build_synapsa_instruction


def _write_synthetic_video(
    path: Path,
    width: int,
    height: int,
    fps: int = 20,
    segments: list[tuple[float, tuple[int, int, int]]] | None = None,
) -> Path:
    segs = segments or [
        (1.0, (20, 30, 220)),
        (1.0, (20, 220, 30)),
        (1.0, (220, 40, 20)),
        (1.0, (240, 240, 240)),
    ]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, float(fps), (width, height))
    assert writer.isOpened()
    try:
        for dur_s, bgr in segs:
            n_frames = max(1, int(round(dur_s * fps)))
            for f_i in range(n_frames):
                frame = np.full((height, width, 3), bgr, dtype=np.uint8)
                # Dodaj ruchomy jasny blok żeby zasymulować akcję w kadrze
                cx = int((width * 0.2) + ((f_i * 18) % max(40, int(width * 0.5))))
                cy = int(height * 0.45)
                cv2.rectangle(frame, (cx, cy), (min(width - 5, cx + 60), min(height - 5, cy + 60)), (255, 255, 255), -1)
                writer.write(frame)
    finally:
        writer.release()
    return path


def test_local_presets_and_product_ad_profile():
    assert "FOOD_GASTRO" in CONTENT_MODE_PRESETS
    assert "NAILS_BEAUTY" in CONTENT_MODE_PRESETS
    assert CONTENT_MODE_PRESETS["FOOD_GASTRO"]["language"] == "pl"
    assert CONTENT_MODE_PRESETS["NAILS_BEAUTY"]["language"] == "pl"

    profile_path = Path(__file__).resolve().parent.parent / "lol_agent" / "game_profiles" / "product_ad.json"
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    labels = raw.get("action_labels") or {}
    assert all("??" not in str(v) for v in labels.values())

    instr = build_synapsa_instruction("niche_research_blueprint", {"niche_query": "kebab"})
    assert "ANTI-PLAGIARISM" in instr
    assert "original_titles_pl" in instr


def test_analyze_reference_video_montage_detects_cuts(tmp_path):
    vid = _write_synthetic_video(
        tmp_path / "ref_short.mp4",
        width=360,
        height=640,
        fps=20,
        segments=[
            (1.0, (10, 20, 230)),
            (1.0, (20, 230, 30)),
            (1.0, (235, 30, 20)),
            (1.0, (245, 230, 220)),
        ],
    )
    stats = nre.analyze_reference_video_montage(vid)
    assert stats["is_vertical"] is True
    assert stats["duration_s"] >= 3.5
    assert stats["cut_count"] >= 2
    assert stats["cuts_per_10s"] > 0.0
    assert stats["avg_shot_len_s"] > 0.0


def test_ad_event_detector_motion_and_brightness_spike(tmp_path):
    vid = _write_synthetic_video(
        tmp_path / "ad_spike.mp4",
        width=480,
        height=270,
        fps=20,
        segments=[
            (1.2, (15, 15, 15)),
            (1.2, (230, 230, 230)),
            (1.2, (30, 200, 50)),
        ],
    )
    events = detect_ad_events(str(vid), clip_start=0.0, clip_end=3.6, clip_duration=3.6)
    assert len(events) >= 1
    labels = {ev[1] for ev in events}
    assert "brightness_spike" in labels or "motion_peak" in labels


def test_anti_plagiarism_blocks_copies_and_passes_original():
    refs = ["Najlepszy Kebab W Centrum Miasta Test Smaku #shorts"]
    forbidden = ["StreetFoodTesterPL"]
    cands = [
        "Najlepszy Kebab W Centrum Miasta Test Smaku",         # kopia
        "StreetFoodTesterPL testuje bułkę z mięsem",           # kopia obcej marki
        "Katarina Pentakill Kebab Reset",                      # wyciek gamingowy
        "Kebab u Mistrza Świdnica: świeże mięso i chrupiąca pita",  # oryginał
    ]
    report = nre.enforce_anti_plagiarism(
        candidates=cands,
        reference_titles=refs,
        forbidden_brands=forbidden,
        allowed_own_terms=["Kebab u Mistrza", "Świdnica", "budka z kebabem"],
        max_similarity=0.35,
        fallback_candidates=[
            "Świeża porcja z Kebab u Mistrza w 14 sekund",
            "Domowy sos czosnkowy i rożen w Kebab u Mistrza",
            "Dlaczego kolejka stoi po Kebab u Mistrza?",
            "Tak kręcimy chrupiącą pitę w Świdnicy",
        ],
        min_passing=5,
    )
    evals_by_title = {e["title"]: e for e in report["evaluations"]}
    assert evals_by_title[cands[0]]["passed"] is False
    assert evals_by_title[cands[1]]["passed"] is False
    assert evals_by_title[cands[2]]["passed"] is False
    assert evals_by_title[cands[3]]["passed"] is True
    assert len(report["approved_titles"]) == 5
    assert report["originality_score_pct"] >= 65.0


def test_build_blueprint_and_pitch_html(tmp_path):
    bp = nre.build_niche_research_blueprint(
        niche_query="budka z kebabem",
        business_name="Kebab u Mistrza",
        city="Świdnica",
        offer="Świeże mięso z rożna i domowy sos",
        cta="Wpadnij dziś po swój zestaw",
        niche_preset="FOOD_GASTRO",
        use_synapsa=False,
        output_dir=tmp_path,
    )
    assert bp["niche_preset"] == "FOOD_GASTRO"
    assert bp["originality_report"]["originality_score_pct"] >= 65.0
    assert len(bp["original_titles_pl"]) >= 5
    assert len(bp["storyboard"]) >= 5
    assert Path(bp["blueprint_path"]).is_file()

    # Sprawdź escapowanie HTML przed XSS w nazwie firmy
    bp_xss = dict(bp)
    bp_xss["comparison"] = {
        "youtube_pattern": dict(bp["comparison"]["youtube_pattern"]),
        "client_original_plan": {**bp["comparison"]["client_original_plan"], "business_name": "<script>alert(1)</script>Kebab"},
    }
    html_path = nre.generate_client_pitch_html(bp_xss, output_dir=tmp_path, preview_video_filename="demo.mp4")
    html_text = html_path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    assert "ANTY-PLAGIAT:" in html_text


def test_render_commercial_pitch_mockup_and_multishot(tmp_path):
    bp = nre.build_niche_research_blueprint(
        niche_query="budka z kebabem",
        business_name="Kebab u Mistrza",
        city="Świdnica",
        offer="Świeże mięso i chrupiąca pita",
        cta="Wpadnij dziś",
        niche_preset="FOOD_GASTRO",
        use_synapsa=False,
        output_dir=tmp_path,
    )
    # Skróć storyboard w teście do 2 krótkich scen żeby render był błyskawiczny
    bp["storyboard"] = bp["storyboard"][:2]
    for s in bp["storyboard"]:
        s["duration_s"] = 1.2

    pitch_mp4 = tmp_path / "pitch_preview.mp4"
    res_pitch = render_commercial_pitch_mockup(bp, pitch_mp4)
    assert res_pitch["ok"] is True
    assert pitch_mp4.is_file() and pitch_mp4.stat().st_size > 10_000
    assert Path(res_pitch["thumbnail_path"]).is_file()

    meta = _probe_video(pitch_mp4)
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    if _find_ffprobe():
        assert meta["has_audio"] is True

    # Teraz przetestuj realny multi-shot na mieszanych klipach 9:16 + 16:9
    clip_vert = _write_synthetic_video(tmp_path / "phone_vert.mp4", width=360, height=640, fps=20, segments=[(1.5, (40, 120, 220)), (1.5, (200, 140, 40))])
    clip_land = _write_synthetic_video(tmp_path / "phone_land.mp4", width=640, height=360, fps=20, segments=[(1.5, (60, 200, 90)), (1.5, (230, 80, 120))])
    reel_mp4 = tmp_path / "client_reel.mp4"
    res_reel = render_commercial_multishot([clip_vert, clip_land], bp, reel_mp4)
    assert res_reel["ok"] is True
    assert reel_mp4.is_file() and reel_mp4.stat().st_size > 10_000
    meta_reel = _probe_video(reel_mp4)
    assert meta_reel["width"] == 1080
    assert meta_reel["height"] == 1920


def test_api_research_endpoints_and_security(tmp_path, monkeypatch):
    monkeypatch.setattr(nre, "NICHE_RESEARCH_DIR", tmp_path)

    client = TestClient(app)
    login = client.post("/auth/login", json={"password": API_PASSWORD})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r_post = client.post(
        "/research/niche",
        headers=headers,
        json={
            "niche_query": "stylizacja paznokci",
            "business_name": "Studio Blask",
            "city": "Wrocław",
            "offer": "Trwały manicure hybrydowy",
            "cta": "Zapisz się przez Booksy",
            "niche_preset": "NAILS_BEAUTY",
            "use_synapsa": False,
        },
    )
    assert r_post.status_code == 200
    bp = r_post.json()["blueprint"]
    slug = bp["slug"]
    assert bp["niche_preset"] == "NAILS_BEAUTY"

    r_list = client.get("/research/niches", headers=headers)
    assert r_list.status_code == 200
    assert any(item["slug"] == slug for item in r_list.json()["items"])

    r_get = client.get(f"/research/niche/{slug}", headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["blueprint"]["client_profile"]["business_name"] == "Studio Blask"

    # Skróć zapisany storyboard żeby mockup preview w teście API był błyskawiczny
    saved_json = tmp_path / f"{slug}.json"
    raw_bp = json.loads(saved_json.read_text(encoding="utf-8"))
    raw_bp["storyboard"] = raw_bp["storyboard"][:2]
    for s in raw_bp["storyboard"]:
        s["duration_s"] = 1.1
    saved_json.write_text(json.dumps(raw_bp, ensure_ascii=False), encoding="utf-8")

    r_mock = client.post("/research/preview-mockup", headers=headers, json={"slug": slug})
    assert r_mock.status_code == 200
    mock_data = r_mock.json()
    assert mock_data["preview_video_filename"].endswith("_pitch_preview.mp4")

    r_media = client.get(f"/research/media/{mock_data['preview_video_filename']}", headers=headers)
    assert r_media.status_code == 200
    assert r_media.headers["content-type"].startswith("video/mp4")

    # Path traversal protection & 404 dla brakującego medium
    r_bad_backslash = client.get("/research/media/..%5C..%5Cmain.py", headers=headers)
    assert r_bad_backslash.status_code == 400
    r_bad_dot = client.get("/research/media/..secret.mp4", headers=headers)
    assert r_bad_dot.status_code == 400
    r_missing = client.get("/research/media/nie_istnieje_999.mp4", headers=headers)
    assert r_missing.status_code == 404
