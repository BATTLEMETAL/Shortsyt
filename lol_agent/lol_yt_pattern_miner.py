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
    {"title": "POV: You Left Reset Carry Open For 3 Seconds 💀 #shorts", "archetype": "RAMPAGE", "views": 2960000, "duration_s": 14.0, "like_rate_pct": 5.4, "comment_rate_pct": 0.14},
    {"title": "When Enemy Squad Thinks 3v1 Is Free ⚡ #shorts", "archetype": "CURIOSITY_GAP", "views": 1850000, "duration_s": 15.0, "like_rate_pct": 5.1, "comment_rate_pct": 0.12},
    {"title": "Wait Until The Last Second Reset 💀 #shorts", "archetype": "CURIOSITY_GAP", "views": 1420000, "duration_s": 16.0, "like_rate_pct": 4.9, "comment_rate_pct": 0.11},
    {"title": "How Is This Legal In Ranked? 🔥 #shorts", "archetype": "EGO_CHECK", "views": 980000, "duration_s": 13.0, "like_rate_pct": 4.8, "comment_rate_pct": 0.10},
    {"title": "They Thought 1v1 Was Safe 😏 #shorts", "archetype": "DISRESPECT_1V1", "views": 540000, "duration_s": 12.0, "like_rate_pct": 5.0, "comment_rate_pct": 0.13},
    {"title": "Entire Team Vanished in 2 Seconds ⚡ #shorts", "archetype": "RAMPAGE", "views": 490000, "duration_s": 14.5, "like_rate_pct": 5.2, "comment_rate_pct": 0.11},
    {"title": "Surviving on 1 HP to Win 🩸 #shorts", "archetype": "CLUTCH_1HP", "views": 380000, "duration_s": 15.5, "like_rate_pct": 4.7, "comment_rate_pct": 0.10},
    {"title": "Walking Up Like That Is Crazy 💀 #shorts", "archetype": "EGO_CHECK", "views": 260000, "duration_s": 11.5, "like_rate_pct": 4.5, "comment_rate_pct": 0.09},
    {"title": "No Escape From the Reset Chain 🔥 #shorts", "archetype": "RAMPAGE", "views": 210000, "duration_s": 16.5, "like_rate_pct": 4.6, "comment_rate_pct": 0.08},
    {"title": "Duel Accepted. Duel Won. 👑 #shorts", "archetype": "DISRESPECT_1V1", "views": 175000, "duration_s": 12.5, "like_rate_pct": 4.9, "comment_rate_pct": 0.09},
    {"title": "Greedy Overchase Punished Instantly 💀 #shorts", "archetype": "EGO_CHECK", "views": 160000, "duration_s": 13.5, "like_rate_pct": 4.4, "comment_rate_pct": 0.08},
    {"title": "1% HP Miracle Turnaround 🔥 #shorts", "archetype": "CLUTCH_1HP", "views": 195000, "duration_s": 14.0, "like_rate_pct": 4.8, "comment_rate_pct": 0.10},
]

_FORBIDDEN_REF_WORDS = ("flash", "ignite", "exhaust", "master ", "bad idea", "rate 1-10")


def _clean_ref_title(title: str) -> str:
    t = re.sub(r"#\S+", "", title or "").strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_iso8601_duration_sec(dur: str) -> float:
    """Konwertuje ISO 8601 duration YouTube (np. 'PT14S', 'PT1M2S') na sekundy."""
    m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$", str(dur or "").strip().upper())
    if not m:
        return 0.0
    hours = float(m.group(1) or 0.0)
    minutes = float(m.group(2) or 0.0)
    seconds = float(m.group(3) or 0.0)
    return round(hours * 3600.0 + minutes * 60.0 + seconds, 2)


def _derive_viral_edit_blueprint(
    title: str,
    duration_s: float,
    views: int,
    like_rate_pct: float = 0.0,
    comment_rate_pct: float = 0.0,
) -> Dict[str, Any]:
    """Wyznacza strukturę hooka, pacingu i rekomendowanego dropu z metadanych virala LoL."""
    clean = _clean_ref_title(title)
    up = clean.upper()

    if up.startswith("POV:") or up.startswith("WHEN "):
        hook_type = "POV"
    elif "?" in clean or up.startswith(("HOW ", "WHY ", "DID ", "CAN ")):
        hook_type = "QUESTION"
    elif any(k in up for k in ("MOST ", "DISGUSTING", "INSANE", "RANK 1", "BROKEN", "GOD")):
        hook_type = "SUPERLATIVE"
    elif any(k in up for k in (" VS ", "1V1", "DUEL", "SOLO")):
        hook_type = "VS_DUEL"
    elif re.search(r"\b\d+\s*(?:S|SEC|SECOND|SECONDS)\b", up):
        hook_type = "TIME_MATH"
    else:
        hook_type = "DIRECT"

    dur = float(duration_s or 0.0)
    if dur <= 0.0:
        dur = 15.0
    if dur <= 12.0:
        pacing_bucket = "ultra_fast_<=12s"
        buildup = 0.8
    elif dur <= 20.0:
        pacing_bucket = "balanced_13_20s"
        buildup = 1.2
    else:
        pacing_bucket = "story_>20s"
        buildup = 1.8

    is_multikill_or_chain = any(
        k in up for k in ("PENTA", "QUADRA", "TRIPLE", "TEAM", "VANISH", "RESET", "SECONDS", "1V3", "1V4", "1V5", "WIPED")
    )
    drop_anchor = "first_kill_engage" if is_multikill_or_chain else "climax_final_kill"

    return {
        "hook_type": hook_type,
        "pacing_bucket": pacing_bucket,
        "recommended_buildup_sec": buildup,
        "recommended_drop_anchor": drop_anchor,
        "target_duration_s": round(dur, 1),
        "engagement_tier": "high" if (like_rate_pct >= 4.5 or int(views or 0) >= 500000) else "standard",
        "comment_rate_pct": round(float(comment_rate_pct or 0.0), 3),
    }


def _enrich_pattern_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    dur = float(out.get("duration_s") or 0.0)
    lr = float(out.get("like_rate_pct") or 0.0)
    cr = float(out.get("comment_rate_pct") or 0.0)
    views = int(out.get("views") or 0)
    bp = _derive_viral_edit_blueprint(out.get("title", ""), dur, views, lr, cr)
    out["duration_s"] = round(dur, 1) if dur > 0 else bp["target_duration_s"]
    out["like_rate_pct"] = round(lr, 2)
    out["comment_rate_pct"] = round(cr, 3)
    out["hook_type"] = bp["hook_type"]
    out["edit_blueprint"] = bp
    return out


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
                return [_enrich_pattern_record(p) for p in cached["patterns"]]
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
                    "league of legends pentakill montage shorts",
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
                        maxResults=max(5, max_results // 3),
                        relevanceLanguage="en",
                    ).execute()
                    vids = [it["id"]["videoId"] for it in res.get("items", []) if it.get("id", {}).get("videoId")]
                    if not vids:
                        continue
                    stats_res = yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(vids)).execute()
                    for item in stats_res.get("items", []):
                        raw_title = (item.get("snippet") or {}).get("title", "").strip()
                        stats = item.get("statistics") or {}
                        views = int(stats.get("viewCount") or 0)
                        likes = int(stats.get("likeCount") or 0)
                        comments = int(stats.get("commentCount") or 0)
                        dur_s = _parse_iso8601_duration_sec((item.get("contentDetails") or {}).get("duration", ""))
                        clean = _clean_ref_title(raw_title)
                        low = clean.lower()
                        if not clean or len(clean) < 12 or len(clean) > 75 or low in seen_titles:
                            continue
                        if any(fw in low for fw in _FORBIDDEN_REF_WORDS):
                            continue
                        if views >= 5000:
                            seen_titles.add(low)
                            like_rate = round((likes / views) * 100.0, 2) if views > 0 else 0.0
                            comment_rate = round((comments / views) * 100.0, 3) if views > 0 else 0.0
                            patterns.append(_enrich_pattern_record({
                                "title": f"{clean} #shorts",
                                "archetype": _classify_external_archetype(clean),
                                "views": views,
                                "duration_s": dur_s or 15.0,
                                "like_rate_pct": like_rate,
                                "comment_rate_pct": comment_rate,
                            }))
        except Exception:
            pass

    if len(patterns) < 6:
        existing_low = {p["title"].lower() for p in patterns}
        for fb in FALLBACK_YT_PATTERNS:
            if fb["title"].lower() not in existing_low:
                patterns.append(_enrich_pattern_record(fb))
    else:
        patterns = [_enrich_pattern_record(p) for p in patterns]

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
