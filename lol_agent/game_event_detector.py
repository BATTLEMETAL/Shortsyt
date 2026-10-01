"""
Shortsyt — Universal Game Event Detector
Wykrywa kill events i peak momenty dla wielu gier na bazie profili (game_profiles/*.json).
"""
import json
import os
from pathlib import Path
from typing import List, Tuple, Optional

PROFILES_DIR = Path(__file__).resolve().parent / "game_profiles"

class GameEventDetector:
    def __init__(self, game_profile: str = "lol"):
        self.profile = self.load_profile(game_profile)
        self.game_id = self.profile.get("game_id", "lol")

    def load_profile(self, game_profile: str) -> dict:
        target = PROFILES_DIR / f"{game_profile}.json"
        if not target.exists():
            target = PROFILES_DIR / "lol.json"
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"game_id": "lol", "game_name": "League of Legends", "hud_type": "top_center_kills"}

    def detect_events(
        self,
        video_path: str,
        clip_start: float,
        clip_end: float,
        clip_duration: Optional[float] = None
    ) -> List[Tuple[float, str]]:
        dur = clip_duration if clip_duration is not None else (clip_end - clip_start)
        hud_type = self.profile.get("hud_type", "top_center_kills")

        if self.game_id == "product_ad" or hud_type == "none":
            try:
                from lol_agent.ad_event_detector import detect_ad_events
                ad_peaks = detect_ad_events(video_path, clip_start, clip_end, dur)
                return [(ts, label) for ts, label, _ in ad_peaks]
            except Exception:
                return [(clip_start + dur / 2, "reveal")]

        if hud_type == "motion_only":
            try:
                from lol_agent.ad_event_detector import detect_ad_events
                peaks = detect_ad_events(video_path, clip_start, clip_end, dur)
                return [(ts, "highlight") for ts, _, _ in peaks]
            except Exception:
                return [(clip_start + dur / 2, "outplay")]

        # Dla LoL i innych FPS/MOBA gier z bannerami killowymi:
        try:
            from lol_agent.smart_camera import detect_kill_events as _detect_kills
            return _detect_kills(video_path, clip_start, clip_end, dur)
        except Exception:
            return []


def detect_kill_events(
    video_path: str,
    clip_start: float,
    clip_end: float,
    clip_duration: Optional[float] = None,
    game_profile: str = "lol"
) -> List[Tuple[float, str]]:
    """Backward-compatible wrapper delegating to GameEventDetector."""
    detector = GameEventDetector(game_profile)
    return detector.detect_events(video_path, clip_start, clip_end, clip_duration)
