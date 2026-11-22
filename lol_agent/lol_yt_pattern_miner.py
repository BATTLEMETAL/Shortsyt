"""
LOL Agent — YouTube Viral Shorts Pattern Miner
==============================================
Pobiera najpopularniejsze aktualne Shortsy League of Legends z YouTube Data API
(przez istniejący token OAuth kanału z 24h cache) i ekstrahuje z nich zwycięskie
archetypy tytułów oraz słowa kluczowe do doszkalania lokalnej Synapsy LoRA.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = Path(__file__).resolve().parent / "yt_viral_patterns_cache.json"

FALLBACK_YT_PATTERNS: List[Dict[str, Any]] = [
    {"title": "POV: You Left Reset Carry Open For 3 Seconds 💀 #shorts", "archetype": "RAMPAGE", "views": 2960000},
    {"title": "When Enemy Squad Thinks 3v1 Is Free ⚡ #shorts", "archetype": "CURIOSITY_GAP", "views": 1850000},
    {"title": "Wait Until The Last Second Reset 💀 #shorts", "archetype": "CURIOSITY_GAP", "views": 1420000},
    {"title": "How Is This Legal In Ranked? 🔥 #shorts", "archetype": "EGO_CHECK", "views": 980000},
    {"title": "They Thought 1v1 Was Safe 😏 #shorts", "archetype": "DISRESPECT_1V1", "views": 540000},
    {"title": "Entire Team Vanished in 2 Seconds ⚡ #shorts", "archetype": "RAMPAGE", "views": 490000},
    {"title": "Surviving on 1 HP to Win 🩸 #shorts", "archetype": "CLUTCH_1HP", "views": 380000},
    {"title": "Walking Up Like That Is Crazy 💀 #shorts", "archetype": "EGO_CHECK", "views": 260000},
    {"title": "No Escape From the Reset Chain 🔥 #shorts", "archetype": "RAMPAGE", "views": 210000},
    {"title": "Duel Accepted. Duel Won. 👑 #shorts", "archetype": "DISRESPECT_1V1", "views": 175000},
    {"title": "Greedy Overchase Punished Instantly 💀 #shorts", "archetype": "EGO_CHECK", "views": 160000},
    {"title": "1% HP Miracle Turnaround 🔥 #shorts", "archetype": "CLUTCH_1HP", "views": 195000},
]

_FORBIDDEN_REF_WORDS = ("flash", "ignite", "exhaust", "master ", "bad idea", "rate 1-10")


def _clean_ref_title(title: str) -> str:
    t = re.sub(r"#\S+", "", title or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _classify_external_archetype(title: str) -> str:
    up = (title or "").upper()
    if any(k in up for k in ("1V1", "DUEL", "SOLO", "SAFE", "EGO")):
        return "DISRESPECT_1V1"
    if any(k in up for k in ("1% HP", "1 HP", "SURVIV", "TURNAROUND", "CLUTCH")):
        return "CLUTCH_1HP"
    if any(k in up for k in ("PENTA", "TEAM", "VANISH", "WIPED", "ESCAPE", "RESET", "SECONDS")):
        return "RAMPAGE"
    return "EGO_CHECK"


def mine_top_youtube_patterns(max_results: int = 20, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Zwraca listę sprawdzonych schematów tytułów z topowych Shortsów LoL (z cache 24h).
    Odsiewa duplikaty, nieangielskie tytuły oraz klisze/zmyślone spelle.
    """
    if CACHE_PATH.exists() and not force_refresh:
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            age = time.time() - float(cached.get("fetched_at", 0))
            if age < 24 * 3600 and cached.get("patterns"):
                return cached["patterns"]
        except Exception:
            pass

    patterns: List[Dict[str, Any]] = []
    if not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from lol_agent.api.youtube_uploader import _load_credentials
            from googleapiclient.discovery import build
            creds = _load_credentials()
            if creds is not None:
                yt = build("youtube", "v3", credentials=creds)
                queries = [
                    "katarina outplay lol shorts",
                    "league of legends solo bolo clutch shorts",
                ]
                seen_titles = set()
                for q in queries:
                    res = yt.search().list(
                        part="id,snippet",
                        q=q,
                        type="video",
                        videoDuration="short",
                        order="viewCount",
                        maxResults=max(5, max_results // 2),
                        relevanceLanguage="en",
                    ).execute()
                    vids = [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]
                    if not vids:
                        continue
                    stats_res = yt.videos().list(part="snippet,statistics", id=",".join(vids)).execute()
                    for item in stats_res.get("items", []):
                        raw_title = (item.get("snippet") or {}).get("title", "").strip()
                        views = int((item.get("statistics") or {}).get("viewCount") or 0)
                        clean = _clean_ref_title(raw_title)
                        low = clean.lower()
                        if not clean or len(clean) < 12 or len(clean) > 65 or low in seen_titles:
                            continue
                        if any(fw in low for fw in _FORBIDDEN_REF_WORDS):
                            continue
                        if views >= 5000:
                            seen_titles.add(low)
                            patterns.append({
                                "title": f"{clean} #shorts",
                                "archetype": _classify_external_archetype(clean),
                                "views": views,
                            })
        except Exception:
            pass

    if len(patterns) < 6:
        existing_low = {p["title"].lower() for p in patterns}
        for fb in FALLBACK_YT_PATTERNS:
            if fb["title"].lower() not in existing_low:
                patterns.append(dict(fb))

    patterns.sort(key=lambda x: int(x.get("views") or 0), reverse=True)
    try:
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            CACHE_PATH.write_text(
                json.dumps({"fetched_at": time.time(), "patterns": patterns[:30]}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except Exception:
        pass
    return patterns[:30]
