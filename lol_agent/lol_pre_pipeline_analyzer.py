r"""
lol_pre_pipeline_analyzer.py
=============================
Analizuje klipy z Outplayed PRZED wrzuceniem do pipeline:
  - Pobiera dane wydajnosci z YouTube (views/likes per action type)
  - Skanuje katalog Outplayed i wykrywa akcje przez OCR
  - Scoruje kazdy klip (kill count, duration, action type vs YT history)
  - Drukuje ranking: ktory klip wrzucic NAJPIERW
  - Zapisuje wyniki do lol_pre_analysis.json

Uzycie:
  python lol_agent/lol_pre_pipeline_analyzer.py
  python lol_agent/lol_pre_pipeline_analyzer.py --dir "C:\path\to\clips"
"""
import os
import sys
import json
import argparse
import pickle
import re
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from lol_config import (
    LOL_INPUT_DIR, TOKEN_PATH, GEMINI_API_KEY, GEMINI_FALLBACK_MODELS,
    SHORT_MAX_DURATION,
)

OUTPUT_FILE  = os.path.join(os.path.dirname(__file__), "lol_pre_analysis.json")
TOP_N        = 10
CACHE_PATH   = os.path.join(os.path.dirname(__file__), "yt_perf_cache.json")

# Wagi action type - na podstawie historii kanalu (outplay byl #1 z 13k views)
ACTION_WEIGHTS = {
    "pentakill":   1.0,
    "quadrakill":  1.15,
    "triple":      1.05,
    "outplay":     1.30,
    "clutch":      1.25,
    "double":      0.85,
}

OPTIMAL_MIN = 12
OPTIMAL_MAX = 35
MIN_KILL_COUNT = 2
# Akcje które nie wymagają multi-killa — historycznie outperformują pentakill (4k vs 1k avg views)
SINGLE_KILL_ACTIONS = {"outplay", "clutch", "escape", "oneshot"}


PUBLISHED_LOG = os.path.join(os.path.dirname(__file__), "published_videos.jsonl")


def fetch_yt_performance() -> dict:
    """Pobiera historyczne dane YT z cache lub published_videos.jsonl."""
    import time as _time

    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
            if _time.time() - cached.get("fetched_at", 0) < 4 * 3600:
                return _build_action_stats(cached.get("videos", []))
        except Exception:
            pass

    # Wczytaj video_id z published_videos.jsonl
    published_ids = []
    if os.path.exists(PUBLISHED_LOG):
        with open(PUBLISHED_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("video_id"):
                        published_ids.append(entry["video_id"])
                except Exception:
                    pass

    if not published_ids:
        print("  Brak published_videos.jsonl - uzywam domyslnych wag")
        return {}

    try:
        from googleapiclient.discovery import build
        if not os.path.exists(TOKEN_PATH):
            raise FileNotFoundError("No token")
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
        yt = build("youtube", "v3", credentials=creds)

        # Pobierz statystyki po ID (nie wymaga search scope)
        details = yt.videos().list(
            part="statistics,snippet",
            id=",".join(published_ids[-50:])   # max 50
        ).execute()

        videos = []
        for item in details.get("items", []):
            st = item.get("statistics", {})
            sn = item.get("snippet", {})
            videos.append({
                "videoId": item["id"],
                "title": sn.get("title", ""),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "publishedAt": sn.get("publishedAt", ""),
            })

        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": _time.time(), "videos": videos}, f)

        print(f"  Pobrano statystyki dla {len(videos)} filmow z YT")
        return _build_action_stats(videos)

    except Exception as e:
        print(f"  YT API: {e} - uzywam domyslnych wag")
        return {}


def _calculate_time_decay_weight(published_at_str: str) -> float:
    """
    Oblicza wagę na podstawie wieku filmu:
    - Ostatnie 7 dni: 1.0 (pełna waga, aktualny algorytm)
    - 7 - 30 dni: 0.8
    - 30 - 90 dni: 0.5
    - > 90 dni (stary algorytm / inne zasady): 0.3
    """
    if not published_at_str:
        return 0.5
    try:
        from datetime import datetime, timezone
        pub_date = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        days_old = (datetime.now(timezone.utc) - pub_date).total_seconds() / 86400.0
        if days_old <= 7:
            return 1.0
        elif days_old <= 30:
            return 0.8
        elif days_old <= 90:
            return 0.5
        else:
            return 0.3
    except Exception:
        return 0.5


def _build_action_stats(videos: list) -> dict:
    TITLE_PATTERNS = {
        "pentakill":  [r"pentakill", r"penta"],
        "quadrakill": [r"quadra"],
        "triple":     [r"triple"],
        "outplay":    [r"outplay", r"tried to die", r"trash talk", r"enemy tried"],
        "clutch":     [r"clutch", r"1%\s*hp"],
        "double":     [r"double kill"],
    }
    stats = {}
    for action, patterns in TITLE_PATTERNS.items():
        matched = [
            v for v in videos
            if any(re.search(p, v.get("title", "").lower()) for p in patterns)
        ]
        if matched:
            weighted_views_sum = 0.0
            total_weights = 0.0
            raw_views = []

            for v in matched:
                w = _calculate_time_decay_weight(v.get("publishedAt", ""))
                views = v.get("views", 0)
                raw_views.append(views)
                weighted_views_sum += views * w
                total_weights += w

            weighted_avg = int(weighted_views_sum / max(total_weights, 0.001))
            simple_avg = sum(raw_views) // len(raw_views)

            stats[action] = {
                "count":        len(matched),
                "avg_views":    simple_avg,
                "weighted_avg": weighted_avg,
                "best_views":   max(raw_views),
                "best_title":   max(matched, key=lambda x: x["views"])["title"],
            }
    return stats


def scan_outplayed_dir(directory: str) -> list:
    clips = []
    if not os.path.isdir(directory):
        print(f"  Katalog nie istnieje: {directory}")
        return clips

    for root, _, files in os.walk(directory):
        for fname in files:
            if not fname.lower().endswith(".mp4"):
                continue
            fpath = os.path.join(root, fname)
            size_mb = os.path.getsize(fpath) / 1_048_576
            if size_mb < 5:
                continue
            clips.append({
                "path":     fpath,
                "filename": fname,
                "size_mb":  round(size_mb, 1),
                "mtime":    os.path.getmtime(fpath),
            })

    clips.sort(key=lambda x: x["mtime"], reverse=True)
    return clips


def detect_action_ocr(filepath: str) -> dict:
    """Wykrywa akcje przez OCR (lol_momentum_analyzer). Fallback: heurystyka z nazwy pliku."""
    try:
        from lol_momentum_analyzer import analyze_momentum
        result = analyze_momentum(filepath)
        peaks = getattr(result, "peaks", [])
        kill_count = len(peaks)
        duration = getattr(result, "duration", 0.0)
        trim_start = getattr(result, "trim_start", 0.0)
        trim_end = getattr(result, "trim_end", duration)

        labels = [label.upper() for _, label in peaks]
        if any("PENTA" in l for l in labels):
            action_type = "pentakill"
            kill_count = max(kill_count, 5)
        elif any("QUADRA" in l for l in labels):
            action_type = "quadrakill"
            kill_count = max(kill_count, 4)
        elif any("TRIPLE" in l for l in labels):
            action_type = "triple"
            kill_count = max(kill_count, 3)
        elif any("DOUBLE" in l for l in labels):
            action_type = "double"
            kill_count = max(kill_count, 2)
        elif kill_count >= 5:
            action_type = "pentakill"
        elif kill_count == 4:
            action_type = "quadrakill"
        elif kill_count == 3:
            action_type = "triple"
        elif kill_count == 2:
            action_type = "double"
        else:
            action_type = "outplay"
            kill_count = max(kill_count, 1)

        clip_window = round(trim_end - trim_start, 1) if (trim_end > trim_start) else round(duration, 1)

        return {
            "action_type": action_type,
            "kill_count":  kill_count,
            "peaks":       peaks,
            "duration_s":  duration,
            "clip_window": clip_window,
            "trim_start":  trim_start,
            "trim_end":    trim_end,
        }
    except Exception:
        fname_lower = os.path.basename(filepath).lower()
        if "penta" in fname_lower:
            return {"action_type": "pentakill",  "kill_count": 5, "peaks": [], "duration_s": 0, "clip_window": 27}
        if "quadra" in fname_lower:
            return {"action_type": "quadrakill", "kill_count": 4, "peaks": [], "duration_s": 0, "clip_window": 25}
        if "triple" in fname_lower:
            return {"action_type": "triple",     "kill_count": 3, "peaks": [], "duration_s": 0, "clip_window": 22}
        if "double" in fname_lower:
            return {"action_type": "double",     "kill_count": 2, "peaks": [], "duration_s": 0, "clip_window": 16}
        return {"action_type": "outplay", "kill_count": 1, "peaks": [], "duration_s": 0, "clip_window": 0}


def score_clip(clip_meta: dict, ocr: dict, yt_stats: dict) -> float:
    action = ocr["action_type"]
    kills  = ocr["kill_count"]
    window = ocr["clip_window"]

    # Dla single-kill outplay bazowy kill_score to min 20.0 (wysoki potencjał virala na kanale)
    if action in SINGLE_KILL_ACTIONS:
        kill_score = max(kills * 10.0, 20.0)
    else:
        kill_score = kills * 10.0

    action_w = ACTION_WEIGHTS.get(action, 1.0)

    if OPTIMAL_MIN <= window <= OPTIMAL_MAX:
        dur_bonus = 1.2
    elif window < OPTIMAL_MIN:
        dur_bonus = 0.9 if window >= 12 else 0.7
    elif window <= 50:
        dur_bonus = 1.0
    else:
        dur_bonus = 0.7

    yt_bonus = 1.0
    if action in yt_stats:
        avg = yt_stats[action].get("weighted_avg", yt_stats[action].get("avg_views", 0))
        if avg > 5000:
            yt_bonus = 1.4
        elif avg > 2000:
            yt_bonus = 1.2
        elif avg > 1000:
            yt_bonus = 1.1

    return round(kill_score * action_w * dur_bonus * yt_bonus, 1)


def recommend(score: float, action: str, kills: int) -> str:
    if kills < 1:
        return "SKIP - brak killow"
    if kills < MIN_KILL_COUNT and action not in SINGLE_KILL_ACTIONS:
        return "SKIP - za malo killow"
    if score >= 60:
        return "PUBLISH FIRST"
    if score >= 35:
        return "PUBLISH"
    if score >= 20:
        return "ROZWAŻ"
    return "SKIP"


def main():
    parser = argparse.ArgumentParser(description="LOL Pre-Pipeline Analyzer")
    parser.add_argument("--dir",        default=LOL_INPUT_DIR)
    parser.add_argument("--no-ocr",     action="store_true", help="Pomijn OCR")
    parser.add_argument("--top",        type=int, default=TOP_N)
    parser.add_argument("--scan-limit", type=int, default=50,
                        help="Ile klipow przeskanowac (domyslnie 50)")
    args = parser.parse_args()

    print("=" * 60)
    print("  LOL PRE-PIPELINE ANALYZER")
    print(f"  Katalog: {args.dir}")
    print(f"  Data:    {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\nPobieranie danych YT...")
    yt_stats = fetch_yt_performance()
    if yt_stats:
        for action, s in sorted(yt_stats.items(), key=lambda x: -x[1]["avg_views"]):
            print(f"  {action:12s}: avg {s['avg_views']:,} views | best: {s['best_views']:,}")
    else:
        print("  Brak danych YT - uzywam domyslnych wag")

    # Wczytaj juz przetworzone (deduplikacja)
    processed_hashes_path = os.path.join(os.path.dirname(__file__), "processed_hashes.json")
    processed_hashes = set()
    if os.path.exists(processed_hashes_path):
        try:
            with open(processed_hashes_path, encoding="utf-8") as f:
                processed_hashes = set(json.load(f).keys())
        except Exception:
            pass

    print(f"\nSkanowanie katalogu...")
    clips = scan_outplayed_dir(args.dir)
    if not clips:
        print("  Brak klipow MP4 >5MB")
        return
    print(f"  Znaleziono {len(clips)} klipow")

    # Ogranicz do scan_limit — skanuj szeroko, nie tylko najnowsze
    to_analyze = clips[:args.scan_limit]
    print(f"\nAnalizuje {len(to_analyze)} klipow (OCR)...")

    results = []
    for i, clip in enumerate(to_analyze, 1):
        sys.stdout.write(f"\r  [{i}/{len(to_analyze)}] {clip['filename'][:55]:<55}")
        sys.stdout.flush()
        ocr = detect_action_ocr(clip["path"]) if not args.no_ocr else \
              {"action_type": "pentakill", "kill_count": 5, "peaks": [], "duration_s": 0, "clip_window": 27}
        sc  = score_clip(clip, ocr, yt_stats)
        rec = recommend(sc, ocr["action_type"], ocr["kill_count"])
        results.append({**clip, **ocr, "score": sc, "recommend": rec})


    print()

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:args.top]

    print(f"\n{'='*60}")
    print(f"  TOP {args.top} KLIPOW:")
    print(f"{'='*60}")
    for i, r in enumerate(top, 1):
        print(f"\n#{i} [{r['recommend']}] Score: {r['score']}")
        print(f"  Plik:   {r['filename'][:65]}")
        print(f"  Akcja:  {r['action_type'].upper()} ({r['kill_count']} kills) | Okno: {r['clip_window']}s")
        if r["action_type"] in yt_stats:
            s = yt_stats[r["action_type"]]
            print(f"  YT ref: avg {s['avg_views']:,} views | best: \"{s['best_title'][:50]}\"")

    if top:
        best = top[0]
        print(f"\n{'='*60}")
        print("  KOMENDA DLA #1:")
        print(f"{'='*60}")
        print(f'.\\venv313\\Scripts\\python.exe -u lol_agent\\run_lol_agent.py `')
        print(f'  --file "{best["path"]}" `')
        print(f'  --action {best["action_type"]} --dry-run')

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directory":    args.dir,
        "yt_stats":     yt_stats,
        "results":      results,
        "top":          top,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nWyniki zapisane: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
