"""
Shortsyt API — Kalendarz Publikacji i Rezerwacja Pipeline
Zarządza harmonogramem publikacji na YouTube Shorts w oparciu o Peak Hours (08:30, 12:00, 18:30, 20:30 CET)
oraz rezerwacjami slotów produkcyjnych.
"""
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from zoneinfo import ZoneInfo
    TZ_CET = ZoneInfo("Europe/Warsaw")
except Exception:
    TZ_CET = timezone(timedelta(hours=2))

CALENDAR_FILE = Path(__file__).resolve().parent.parent / "publishing_calendar.json"
PEAK_HOURS_CET = ["08:30", "12:00", "18:30", "20:30"]


def _load_calendar_db() -> Dict[str, Any]:
    """Wczytaj bazę rezerwacji kalendarza."""
    if CALENDAR_FILE.exists():
        try:
            with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_calendar_db(data: Dict[str, Any]):
    """Zapisz bazę rezerwacji kalendarza."""
    CALENDAR_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_calendar_slots(start_date: Optional[str] = None, days: int = 14) -> List[Dict[str, Any]]:
    """
    Zwraca siatkę slotów publikacji na zadany okres (domyślnie 14 dni).
    Łączy wygenerowane okna Peak Hours z zapisanymi rezerwacjami.
    """
    db = _load_calendar_db()
    now_cet = datetime.now(TZ_CET)

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=TZ_CET)
        except Exception:
            start_dt = now_cet
    else:
        start_dt = now_cet.replace(hour=0, minute=0, second=0, microsecond=0)

    slots = []
    
    for day_offset in range(days):
        day = start_dt + timedelta(days=day_offset)
        date_str = day.strftime("%Y-%m-%d")

        for time_str in PEAK_HOURS_CET:
            h, m = map(int, time_str.split(":"))
            slot_dt = day.replace(hour=h, minute=m, second=0, microsecond=0)
            slot_id = f"slot_{date_str}_{h:02d}-{m:02d}"
            
            utc_dt = slot_dt.astimezone(timezone.utc)
            publish_at_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            is_past = slot_dt < now_cet - timedelta(minutes=15)
            
            existing = db.get(slot_id, {})
            
            slot_status = existing.get("status")
            if not slot_status:
                slot_status = "past" if is_past else "free"
            elif is_past and slot_status == "scheduled":
                slot_status = "published"

            slot_data = {
                "slot_id": slot_id,
                "date": date_str,
                "time": time_str,
                "datetime_local": slot_dt.strftime("%Y-%m-%d %H:%M CET"),
                "datetime_utc": publish_at_iso,
                "is_peak": True,
                "is_past": is_past,
                "status": slot_status,  # 'free' | 'reserved' | 'rendering' | 'ready' | 'scheduled' | 'published' | 'past'
                "title": existing.get("title", ""),
                "champion": existing.get("champion", ""),
                "frag_type": existing.get("frag_type", "outplay"),
                "source_clip": existing.get("source_clip", ""),
                "output_video": existing.get("output_video", ""),
                "thumbnail_url": existing.get("thumbnail_url", ""),
                "yt_video_id": existing.get("yt_video_id", ""),
                "yt_url": existing.get("yt_url", ""),
                "notes": existing.get("notes", ""),
                "created_at": existing.get("created_at"),
            }
            slots.append(slot_data)

    # Dodaj również niestandardowe (ręcznie dodane) sloty
    for sid, sval in db.items():
        if not any(s["slot_id"] == sid for s in slots):
            slots.append(sval)

    # Posortuj chronologicznie
    slots.sort(key=lambda s: s["datetime_utc"])
    return slots


def reserve_slot(
    slot_id: str,
    title: str = "",
    champion: str = "",
    frag_type: str = "outplay",
    source_clip: str = "",
    output_video: str = "",
    notes: str = "",
    custom_dt_cet: Optional[str] = None,
) -> Dict[str, Any]:
    """Rezerwuje lub aktualizuje slot w kalendarzu."""
    db = _load_calendar_db()
    
    # Wylicz daty
    if slot_id.startswith("slot_"):
        parts = slot_id.replace("slot_", "").split("_")
        date_str = parts[0]
        h_m = parts[1].replace("-", ":")
        h, m = map(int, h_m.split(":"))
        dt_obj = datetime.strptime(f"{date_str} {h}:{m}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ_CET)
    elif custom_dt_cet:
        dt_obj = datetime.fromisoformat(custom_dt_cet).replace(tzinfo=TZ_CET)
        date_str = dt_obj.strftime("%Y-%m-%d")
        h_m = dt_obj.strftime("%H:%M")
        slot_id = f"slot_{date_str}_{dt_obj.hour:02d}-{dt_obj.minute:02d}"
    else:
        dt_obj = datetime.now(TZ_CET) + timedelta(hours=2)
        date_str = dt_obj.strftime("%Y-%m-%d")
        h_m = dt_obj.strftime("%H:%M")
        slot_id = f"slot_{date_str}_{dt_obj.hour:02d}-{dt_obj.minute:02d}"

    utc_dt = dt_obj.astimezone(timezone.utc)
    publish_at_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    entry = {
        "slot_id": slot_id,
        "date": date_str,
        "time": h_m,
        "datetime_local": dt_obj.strftime("%Y-%m-%d %H:%M CET"),
        "datetime_utc": publish_at_iso,
        "is_peak": h_m in PEAK_HOURS_CET,
        "status": "ready" if output_video else "reserved",
        "title": title,
        "champion": champion,
        "frag_type": frag_type,
        "source_clip": source_clip,
        "output_video": output_video,
        "thumbnail_url": "",
        "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    db[slot_id] = entry
    _save_calendar_db(db)
    return entry


def release_slot(slot_id: str) -> bool:
    """Zwalnia zarezerwowany slot."""
    db = _load_calendar_db()
    if slot_id in db:
        del db[slot_id]
        _save_calendar_db(db)
        return True
    return False


def update_slot_status(slot_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Aktualizuje status i dane istniejącego slotu."""
    db = _load_calendar_db()
    if slot_id not in db:
        return None
    db[slot_id].update(updates)
    _save_calendar_db(db)
    return db[slot_id]


def auto_fill_upcoming_slots(input_clips: List[Dict[str, Any]], max_slots: int = 4) -> List[Dict[str, Any]]:
    """
    Automatycznie przypisuje najlepsze nieprzypisane klipy do najbliższych wolnych slotów Peak Hours.
    """
    try:
        from lol_agent.lol_frag_detector import analyze_clip_frags
        from lol_agent.lol_metadata_generator import generate_channel_title
    except ImportError:
        from lol_frag_detector import analyze_clip_frags
        from lol_metadata_generator import generate_channel_title

    slots = get_calendar_slots(days=7)
    free_slots = [s for s in slots if s["status"] == "free" and not s["is_past"]]
    
    assigned = []
    used_clips = set()
    db = _load_calendar_db()

    for clip in input_clips:
        if len(assigned) >= max_slots or not free_slots:
            break

        clip_path = clip.get("path") or clip.get("file_path") or ""
        if not clip_path or clip_path in used_clips:
            continue

        # Przeanalizuj typ fraga
        analysis = analyze_clip_frags(clip_path)
        champ = clip.get("champion") or "Katarina"
        frag = analysis.detected_frag_type
        title = generate_channel_title(frag, champ)

        target_slot = free_slots.pop(0)
        slot_id = target_slot["slot_id"]

        entry = {
            "slot_id": slot_id,
            "date": target_slot["date"],
            "time": target_slot["time"],
            "datetime_local": target_slot["datetime_local"],
            "datetime_utc": target_slot["datetime_utc"],
            "is_peak": True,
            "status": "reserved",
            "title": title,
            "champion": champ,
            "frag_type": frag,
            "source_clip": clip_path,
            "output_video": "",
            "notes": f"Auto-rezerwacja AI: {analysis.badge_label} (Pewnosc: {int(analysis.confidence*100)}%)",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db[slot_id] = entry
        assigned.append(entry)
        used_clips.add(clip_path)

    _save_calendar_db(db)
    return assigned
