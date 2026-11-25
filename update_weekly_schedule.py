#!/usr/bin/env python3
"""
Cotygodniowa automatyczna kalibracja godzin publikacji (Pon-Nd, 2 sloty/dzień) na podstawie
statystyk kanału YouTube (+ Analytics Geo/Retencja oraz TikTok/Instagram), zapisywana do
accounts/profiles_registry.json oraz logs/weekly_schedule_YYYY-MM-DD.json.

Uruchamiane samodzielnie lub automatycznie co niedzielę o 20:00 przez FlikcutWeekly
(weekly_channel_analyzer.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

DAY_NAMES_PL = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
_VALID_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _fetch_yt_geo_shares_180d() -> Dict[str, Any]:
    """Najlepszy wysiłek pobrania rozkładu krajów widowni z YouTube Analytics API v2 (bez rzucania błędów)."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return {}
    try:
        import pickle
        from googleapiclient.discovery import build
        from lol_agent.account_manager import get_active_yt_token_path

        tok_path = Path(get_active_yt_token_path())
        if not tok_path.exists():
            return {}
        with open(tok_path, "rb") as f:
            creds = pickle.load(f)
        yta = build("youtubeAnalytics", "v2", credentials=creds)
        end_d = datetime.now(timezone.utc).date().isoformat()
        start_d = (datetime.now(timezone.utc).date() - timedelta(days=180)).isoformat()
        resp = yta.reports().query(
            ids="channel==MINE",
            startDate=start_d,
            endDate=end_d,
            metrics="views,estimatedMinutesWatched",
            dimensions="country",
            sort="-views",
            maxResults=15,
        ).execute()
        rows = resp.get("rows") or []
        total_v = sum(int(r[1]) for r in rows) or 1
        top_countries = [
            {
                "country": str(r[0]),
                "views": int(r[1]),
                "share_pct": round(100.0 * int(r[1]) / total_v, 1),
            }
            for r in rows[:10]
        ]
        asia_codes = {"KR", "JP", "VN", "TW", "PH", "TH", "ID", "MY", "SG", "IN"}
        asia_pct = round(sum(float(c["share_pct"]) for c in top_countries if c["country"] in asia_codes), 1)
        americas_codes = {"US", "BR", "CA", "MX", "AR", "CL", "CO"}
        americas_pct = round(sum(float(c["share_pct"]) for c in top_countries if c["country"] in americas_codes), 1)
        return {
            "window_days": 180,
            "top_countries": top_countries,
            "asia_top_pct": asia_pct,
            "americas_top_pct": americas_pct,
        }
    except Exception:
        return {}


def _fallback_pub_hour_from_cache() -> Dict[str, Any]:
    """Awaryjna analiza z lokalnego yt_perf_cache.json gdy live run_channel_learning_cycle zawiedzie."""
    from lol_agent.learning_engine import _analyze_best_pub_hour

    cache_path = ROOT_DIR / "lol_agent" / "yt_perf_cache.json"
    if not cache_path.exists():
        return {}
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    videos = raw.get("videos", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    return _analyze_best_pub_hour(videos, include_omnichannel=True)


def refresh_weekly_peak_schedule(
    account_id: Optional[str] = None,
    fetch_live: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Przelicza 2 optymalne godziny publikacji dla każdego dnia tygodnia (Pon-Nd) ze statystyk kanału
    i zapisuje nowy tygodniowy rozkład w accounts/profiles_registry.json oraz snapshot w logs/.
    """
    from lol_agent.learning_engine import run_channel_learning_cycle, DEFAULT_RECOMMENDED_SLOTS_CET
    from lol_agent.account_manager import update_account_weekly_schedule, get_active_account

    directive: Dict[str, Any] = {}
    pub_hour: Dict[str, Any] = {}
    source_used = "learning_cycle_live" if fetch_live else "learning_cycle_cache"

    try:
        raw_res = run_channel_learning_cycle(force_refresh=bool(fetch_live)) or {}
        directive = raw_res.get("directive") if isinstance(raw_res.get("directive"), dict) else raw_res
        pub_hour = directive.get("best_pub_hour_analysis") or {}
    except Exception as exc:
        source_used = f"cache_fallback ({exc})"
        pub_hour = _fallback_pub_hour_from_cache()

    raw_weekly = pub_hour.get("recommended_slots_by_weekday_cet")
    if not isinstance(raw_weekly, dict) or len(raw_weekly) < 7:
        source_used = "direct_cache_analyzer"
        pub_hour = _fallback_pub_hour_from_cache()
        raw_weekly = pub_hour.get("recommended_slots_by_weekday_cet") or {}

    validated_weekly: Dict[str, List[str]] = {}
    for dw in range(7):
        key = str(dw)
        cand = raw_weekly.get(key) if isinstance(raw_weekly, dict) else None
        if cand is None and isinstance(raw_weekly, dict):
            cand = raw_weekly.get(dw)  # type: ignore[arg-type]
        cleaned = (
            sorted(set(str(s).strip() for s in cand if _VALID_HHMM_RE.match(str(s).strip())))
            if isinstance(cand, list)
            else []
        )
        validated_weekly[key] = cleaned[:2] if len(cleaned) >= 2 else list(DEFAULT_RECOMMENDED_SLOTS_CET)

    weekday_profiles = pub_hour.get("weekday_slot_profiles_cet") or {}
    geo_summary = _fetch_yt_geo_shares_180d() if fetch_live else {}
    now_utc = datetime.now(timezone.utc)
    snapshot = {
        "updated_at": now_utc.isoformat(),
        "source": source_used,
        "account_id": account_id or (get_active_account() or {}).get("account_id", "dwannellenga"),
        "peak_hours_by_weekday_cet": validated_weekly,
        "weekday_slot_profiles_cet": weekday_profiles,
        "global_fallback_slots_cet": list(DEFAULT_RECOMMENDED_SLOTS_CET),
        "geo_summary_180d": geo_summary,
    }

    if not dry_run:
        metadata_note = {
            "source": source_used,
            "updated_at": now_utc.isoformat(),
            "geo_asia_top_pct": geo_summary.get("asia_top_pct"),
            "geo_americas_top_pct": geo_summary.get("americas_top_pct"),
        }
        update_account_weekly_schedule(
            peak_hours_by_weekday_cet=validated_weekly,
            account_id=account_id,
            peak_hours_cet=None,  # Zachowaj globalny fallback ["15:00", "21:30"]
            schedule_metadata=metadata_note,
        )
        try:
            from lol_agent.api.youtube_uploader import invalidate_publish_cache
            invalidate_publish_cache()
        except Exception:
            pass

        log_dir = ROOT_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        snap_path = log_dir / f"weekly_schedule_{now_utc.strftime('%Y-%m-%d')}.json"
        snap_tmp = snap_path.with_suffix(".tmp")
        snap_tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(snap_tmp, snap_path)
        snapshot["snapshot_path"] = str(snap_path)

    return snapshot


def print_schedule_table(snapshot: Dict[str, Any]) -> None:
    weekly = snapshot.get("peak_hours_by_weekday_cet") or {}
    profiles = snapshot.get("weekday_slot_profiles_cet") or {}
    print(f"\n=== AKTUALNY HARMONOGRAM TYGODNIOWY CET ({snapshot.get('account_id')}) ===")
    print(f"Źródło: {snapshot.get('source')} | Aktualizacja: {snapshot.get('updated_at')}")
    for dw in range(7):
        key = str(dw)
        slots = weekly.get(key, [])
        prof = (profiles.get(key) or {}).get("slot_metrics") or {}
        details = []
        for s in slots:
            m = prof.get(s) or {}
            if m:
                details.append(f"{s} (med~{m.get('eb_median_views')}, >=2k={m.get('hit_2k_pct')}%, eff={m.get('eff_n')})")
            else:
                details.append(s)
        print(f"  {DAY_NAMES_PL[dw]:12s}: {'  |  '.join(details)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cotygodniowa aktualizacja optymalnych godzin publikacji (Pon-Nd).")
    parser.add_argument("--dry-run", action="store_true", help="Tylko przelicz i wydrukuj bez zapisu do profiles_registry.json.")
    parser.add_argument("--no-fetch", action="store_true", help="Użyj lokalnych cache zamiast pobierania świeżych danych z API.")
    parser.add_argument("--account", type=str, default=None, help="Opcjonalne ID konta z profiles_registry.json.")
    args = parser.parse_args()

    snap = refresh_weekly_peak_schedule(
        account_id=args.account,
        fetch_live=not args.no_fetch,
        dry_run=args.dry_run,
    )
    print_schedule_table(snap)
    if snap.get("snapshot_path"):
        print(f"\nZapisano snapshot: {snap['snapshot_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
