"""
Shortsyt / Flikcut — Multi-Account & Content Guidelines Registry
Zarządza wieloma profilami kont (kanał główny, konta poboczne Sandbox YT, klienci: salony, e-commerce),
ich tokenami OAuth oraz wytycznymi kontentu dla generatora metadanych i harmonogramu.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = ROOT_DIR / "accounts"
REGISTRY_FILE = ACCOUNTS_DIR / "profiles_registry.json"
PRETTY_WOMAN_CFG = ACCOUNTS_DIR / "prettywoman_yt_config.json"

CONTENT_MODE_PRESETS: Dict[str, Dict[str, Any]] = {
    "GAMING_HIGHLIGHTS": {
        "label": "Kanał Gamingowy / Konto Poboczne Sandbox",
        "game_type": "lol",
        "language": "en",
        "peak_hours_cet": ["11:00", "21:30"],
        "target_duration_range": [13.5, 17.5],
        "camera_mode": "yellow_hp_bar",
        "brand_voice": "Aggressive Hype Gaming / Ego Check",
        "value_proposition": "High-elo mechanical outplays, 1v1 solo bolo and multikills",
        "cta_text": "Rate this play 1-10! 👇",
        "cta_url": "",
        "mandatory_hashtags": ["#shorts", "#gaming", "#highlights"],
        "forbidden_words": [],
        "yt_category_id": "20",
    },
    "PRODUCT_ECOMMERCE_AD": {
        "label": "Reklama Produktu / Sklep E-commerce / Unboxing",
        "game_type": "product_ad",
        "language": "pl",
        "peak_hours_cet": ["11:00", "19:30"],
        "target_duration_range": [10.0, 18.0],
        "camera_mode": "face_and_center_subject",
        "brand_voice": "Konkretny, problem -> rozwiązanie, mocny hook produktowy w 1.5s",
        "value_proposition": "Prezentacja głównej korzyści produktu i efektu użycia",
        "cta_text": "Sprawdź w sklepie / link w bio 👇",
        "cta_url": "",
        "mandatory_hashtags": ["#shorts", "#polecane", "#zakupy", "#recenzja"],
        "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
        "yt_category_id": "22",
    },
    "BEAUTY_SALON_SERVICE": {
        "label": "Salon Beauty / Usługi Lokalne / Metamorfozy",
        "game_type": "product_ad",
        "language": "pl",
        "peak_hours_cet": ["11:00", "18:00"],
        "target_duration_range": [10.0, 16.0],
        "camera_mode": "face_and_center_subject",
        "brand_voice": "Ekspercki, kobiecy, efekt przed/po i zaufanie lokalne",
        "value_proposition": "Metamorfoza i efekty pracy salonu z jasnym zaproszeniem do rezerwacji",
        "cta_text": "Zapisz się lub zamów 👇",
        "cta_url": "",
        "mandatory_hashtags": ["#shorts", "#metamorfoza", "#salonbeauty"],
        "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
        "yt_category_id": "26",
    },
    "EXPERT_BRAND_SHORT": {
        "label": "Marka Osobista / Wideo Eksperckie / B2B",
        "game_type": "generic",
        "language": "pl",
        "peak_hours_cet": ["09:00", "18:00"],
        "target_duration_range": [15.0, 35.0],
        "camera_mode": "face_and_center_subject",
        "brand_voice": "Rzeczowy, zero lania wody, mocna teza w pierwszych 2s",
        "value_proposition": "Konkretna lekcja inżynierska / biznesowa poparta danymi",
        "cta_text": "Napisz swoją opinię w komentarzu 👇",
        "cta_url": "",
        "mandatory_hashtags": ["#shorts", "#biznes", "#technologia"],
        "forbidden_words": ["Katarina", "League of Legends"],
        "yt_category_id": "28",
    },
}


def _slugify_account_id(raw: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", (raw or "").strip().lower()).strip("_")
    return clean or f"acc_{int(datetime.now(timezone.utc).timestamp())}"


def _build_default_accounts() -> Dict[str, Any]:
    dwannellenga = {
        "account_id": "dwannellenga",
        "display_name": "Dwannellenga (LoL Highlights)",
        "handle": "@Dwannellenga",
        "content_mode": "GAMING_HIGHLIGHTS",
        "game_type": "lol",
        "language": "en",
        "yt_token_file": "lol_token.pickle",
        "tt_token_file": "tiktok_token.json",
        "ig_token_file": "instagram_token.json",
        "fb_token_file": "facebook_token.json",
        "peak_hours_cet": ["11:00", "21:30"],
        "target_duration_range": [13.5, 17.5],
        "camera_mode": "yellow_hp_bar",
        "brand_voice": "Aggressive Hype Gaming / Ego Check",
        "value_proposition": "High-elo Katarina mechanical outplays, 1v1 solo bolo and multikills",
        "cta_text": "Rate this play 1-10! 👇",
        "cta_url": "https://www.youtube.com/@Dwannellenga",
        "location": "",
        "phone": "",
        "mandatory_hashtags": ["#shorts", "#leagueoflegends", "#lol"],
        "forbidden_words": [],
        "target_audience": "Male 18-34, KR/PL/JP/US League of Legends players",
        "yt_category_id": "20",
        "builtin": True,
    }

    pw_raw: Dict[str, Any] = {}
    if PRETTY_WOMAN_CFG.exists():
        try:
            pw_raw = json.loads(PRETTY_WOMAN_CFG.read_text(encoding="utf-8"))
        except Exception:
            pw_raw = {}

    pw_tags = [f"#{t.lstrip('#').replace(' ', '').lower()}" for t in (pw_raw.get("default_tags") or []) if t][:6]
    pretty_woman = {
        "account_id": "pretty_woman",
        "display_name": pw_raw.get("channel_name", "Salon Pretty Woman Świdnica"),
        "handle": pw_raw.get("handle", "@salonprettywoman"),
        "content_mode": "BEAUTY_SALON_SERVICE",
        "game_type": "product_ad",
        "language": pw_raw.get("language", "pl"),
        "yt_token_file": "prettywoman_token.pickle",
        "tt_token_file": "",
        "ig_token_file": "",
        "fb_token_file": "",
        "peak_hours_cet": ["11:00", "18:00"],
        "target_duration_range": [10.0, 16.0],
        "camera_mode": "face_and_center_subject",
        "brand_voice": "Ekspercki, kobiecy, premium salon beauty",
        "value_proposition": pw_raw.get("niche", "Afroloki, warkoczyki, panda kucyki i peruki na zamówienie w Świdnicy"),
        "cta_text": "Zapisz się lub zamów w sklepie 👇",
        "cta_url": pw_raw.get("shop_url", "https://sklep.salon-prettywoman.pl"),
        "location": pw_raw.get("address", "ul. Ofiar Oświęcimskich 28, Świdnica"),
        "phone": pw_raw.get("phone", "788-945-643"),
        "mandatory_hashtags": pw_tags or ["#shorts", "#afroloki", "#warkoczyki", "#fryzjerświdnica"],
        "forbidden_words": ["Katarina", "League of Legends", "Pentakill"],
        "target_audience": "Kobiety 25-54, Polska / Dolny Śląsk (fryzury afro, metamorfozy)",
        "yt_category_id": "26",
        "builtin": False,
    }

    return {
        "active_account_id": "dwannellenga",
        "accounts": {
            "dwannellenga": dwannellenga,
            "pretty_woman": pretty_woman,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _load_registry() -> Dict[str, Any]:
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("accounts"), dict) and data["accounts"]:
                return data
        except Exception:
            pass
    default_reg = _build_default_accounts()
    _save_registry(default_reg)
    return default_reg


def _save_registry(data: Dict[str, Any]) -> None:
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = REGISTRY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, REGISTRY_FILE)


def _enrich_account_view(acc: Dict[str, Any], active_id: str) -> Dict[str, Any]:
    yt_file = acc.get("yt_token_file") or f"{acc.get('account_id', 'lol')}_token.pickle"
    yt_path = ACCOUNTS_DIR / yt_file
    out = dict(acc)
    out["is_active"] = (acc.get("account_id") == active_id)
    out["yt_token_exists"] = yt_path.exists()
    out["yt_token_path"] = str(yt_path)
    return out


def list_accounts() -> Dict[str, Any]:
    """Zwraca listę wszystkich profili kont, aktywne konto oraz szablony wytycznych."""
    reg = _load_registry()
    active_id = reg.get("active_account_id", "dwannellenga")
    accounts = [
        _enrich_account_view(acc, active_id)
        for acc in reg.get("accounts", {}).values()
    ]
    return {
        "active_account_id": active_id,
        "accounts": accounts,
        "presets": CONTENT_MODE_PRESETS,
    }


def get_active_account() -> Dict[str, Any]:
    """Zwraca pełny profil i wytyczne aktywnego konta."""
    reg = _load_registry()
    active_id = reg.get("active_account_id", "dwannellenga")
    accounts = reg.get("accounts", {})
    acc = accounts.get(active_id) or accounts.get("dwannellenga") or next(iter(accounts.values()))
    return _enrich_account_view(acc, active_id)


def set_active_account(account_id: str) -> Dict[str, Any]:
    """Przełącza aktywne konto aplikacji."""
    reg = _load_registry()
    acc_id = _slugify_account_id(account_id)
    if acc_id not in reg.get("accounts", {}):
        raise KeyError(f"Konto '{account_id}' nie istnieje")
    reg["active_account_id"] = acc_id
    _save_registry(reg)
    return _enrich_account_view(reg["accounts"][acc_id], acc_id)


def upsert_account(data: Dict[str, Any]) -> Dict[str, Any]:
    """Dodaje nowe konto z wytycznymi kontentu lub aktualizuje istniejące."""
    reg = _load_registry()
    raw_id = data.get("account_id") or data.get("display_name") or data.get("handle") or ""
    acc_id = _slugify_account_id(raw_id)

    content_mode = str(data.get("content_mode") or "PRODUCT_ECOMMERCE_AD").upper().strip()
    preset = CONTENT_MODE_PRESETS.get(content_mode, CONTENT_MODE_PRESETS["PRODUCT_ECOMMERCE_AD"])
    existing = reg.get("accounts", {}).get(acc_id, {})

    def _clean_tags(val: Any, fallback: List[str]) -> List[str]:
        if isinstance(val, str):
            items = [x.strip() for x in val.replace(",", " ").split() if x.strip()]
        elif isinstance(val, list):
            items = [str(x).strip() for x in val if str(x).strip()]
        else:
            items = list(fallback)
        return [f"#{t.lstrip('#').lower()}" for t in items] if items else list(fallback)

    def _clean_words(val: Any, fallback: List[str]) -> List[str]:
        if isinstance(val, str):
            return [x.strip() for x in val.split(",") if x.strip()]
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        return list(fallback)

    def _clean_hours(val: Any, fallback: List[str]) -> List[str]:
        if isinstance(val, str):
            items = [x.strip() for x in val.replace(";", ",").split(",") if x.strip()]
        elif isinstance(val, list):
            items = [str(x).strip() for x in val if str(x).strip()]
        else:
            items = list(fallback)
        return items or list(fallback)

    default_token = "lol_token.pickle" if acc_id == "dwannellenga" else f"{acc_id}_token.pickle"
    merged = {
        "account_id": acc_id,
        "display_name": data.get("display_name") or existing.get("display_name") or acc_id,
        "handle": data.get("handle") or existing.get("handle") or f"@{acc_id}",
        "content_mode": content_mode,
        "game_type": data.get("game_type") or existing.get("game_type") or preset["game_type"],
        "language": data.get("language") or existing.get("language") or preset["language"],
        "yt_token_file": data.get("yt_token_file") or existing.get("yt_token_file") or default_token,
        "tt_token_file": data.get("tt_token_file") if data.get("tt_token_file") is not None else existing.get("tt_token_file", ""),
        "ig_token_file": data.get("ig_token_file") if data.get("ig_token_file") is not None else existing.get("ig_token_file", ""),
        "fb_token_file": data.get("fb_token_file") if data.get("fb_token_file") is not None else existing.get("fb_token_file", ""),
        "peak_hours_cet": _clean_hours(data.get("peak_hours_cet"), existing.get("peak_hours_cet") or preset["peak_hours_cet"]),
        "target_duration_range": data.get("target_duration_range") or existing.get("target_duration_range") or preset["target_duration_range"],
        "camera_mode": data.get("camera_mode") or existing.get("camera_mode") or preset["camera_mode"],
        "brand_voice": data.get("brand_voice") if data.get("brand_voice") is not None else existing.get("brand_voice") or preset["brand_voice"],
        "value_proposition": data.get("value_proposition") if data.get("value_proposition") is not None else existing.get("value_proposition") or preset["value_proposition"],
        "cta_text": data.get("cta_text") if data.get("cta_text") is not None else existing.get("cta_text") or preset["cta_text"],
        "cta_url": data.get("cta_url") if data.get("cta_url") is not None else existing.get("cta_url", ""),
        "location": data.get("location") if data.get("location") is not None else existing.get("location", ""),
        "phone": data.get("phone") if data.get("phone") is not None else existing.get("phone", ""),
        "mandatory_hashtags": _clean_tags(data.get("mandatory_hashtags"), existing.get("mandatory_hashtags") or preset["mandatory_hashtags"]),
        "forbidden_words": _clean_words(data.get("forbidden_words"), existing.get("forbidden_words") or preset["forbidden_words"]),
        "target_audience": data.get("target_audience") if data.get("target_audience") is not None else existing.get("target_audience", ""),
        "yt_category_id": str(data.get("yt_category_id") or existing.get("yt_category_id") or preset.get("yt_category_id", "22")),
        "builtin": bool(existing.get("builtin", False)),
    }

    reg.setdefault("accounts", {})[acc_id] = merged
    if data.get("set_active"):
        reg["active_account_id"] = acc_id
    _save_registry(reg)
    return _enrich_account_view(merged, reg.get("active_account_id", "dwannellenga"))


def delete_account(account_id: str) -> bool:
    """Usuwa niestandardowe konto z rejestru (konto wbudowane jest chronione)."""
    reg = _load_registry()
    acc_id = _slugify_account_id(account_id)
    accounts = reg.get("accounts", {})
    if acc_id not in accounts:
        return False
    if accounts[acc_id].get("builtin"):
        raise ValueError("Nie można usunąć wbudowanego konta głównego")
    del accounts[acc_id]
    if reg.get("active_account_id") == acc_id:
        reg["active_account_id"] = "dwannellenga"
    _save_registry(reg)
    return True


def get_active_yt_token_path() -> Path:
    """Zwraca ścieżkę do pliku pickle tokenu YouTube dla aktywnego konta."""
    acc = get_active_account()
    return ACCOUNTS_DIR / (acc.get("yt_token_file") or "lol_token.pickle")


_PLATFORM_TOKEN_FIELDS = {
    "tiktok": ("tt_token_file", "tiktok_token.json"),
    "instagram": ("ig_token_file", "instagram_token.json"),
    "facebook": ("fb_token_file", "facebook_token.json"),
}


def get_active_platform_token_path(platform: str) -> Path:
    """
    Zwraca ścieżkę tokenu TikTok / Instagram / Facebook dla aktywnego konta.
    Gdy konto nie ma przypisanego pliku (np. salon klienta), zwraca ścieżkę
    `<account_id>_<plik>` która nie istnieje — publikacja zakończy się brakiem tokenu
    zamiast wysłania filmu klienta na główny kanał gamingowy.
    """
    field, default_name = _PLATFORM_TOKEN_FIELDS[platform.lower()]
    acc = get_active_account()
    configured = (acc.get(field) or "").strip()
    if configured:
        return ACCOUNTS_DIR / configured
    if acc.get("account_id") in (None, "", "dwannellenga"):
        return ACCOUNTS_DIR / default_name
    return ACCOUNTS_DIR / f"{acc['account_id']}_{default_name}"


def generate_account_aware_metadata(
    action_type: str = "demo",
    subject_name: str = "Produkt",
    extra_context: Optional[Dict[str, Any]] = None,
    account: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generuje tytuł, opis, przypięty komentarz i tagi ściśle według wytycznych aktywnego konta
    (dla kont reklamowych, salonów usługowych, marek osobistych i kont pobocznych).
    """
    acc = account or get_active_account()
    lang = (acc.get("language") or "pl").upper()
    tags_str = " ".join(acc.get("mandatory_hashtags") or ["#shorts"])
    brand = acc.get("display_name") or "Brand"
    voice = acc.get("brand_voice") or ""
    value_prop = acc.get("value_proposition") or ""
    cta_text = acc.get("cta_text") or "Sprawdź szczegóły 👇"
    cta_url = acc.get("cta_url") or ""
    location = acc.get("location") or ""
    phone = acc.get("phone") or ""
    audience = acc.get("target_audience") or ""
    forbidden = [w.strip() for w in (acc.get("forbidden_words") or []) if w.strip()]

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    try:
        from lol_agent.lol_config import GEMINI_API_KEY, GEMINI_MODEL
        if not gemini_key:
            gemini_key = GEMINI_API_KEY
    except Exception:
        GEMINI_MODEL = "gemini-2.5-flash"

    # Priorytet #1 dla EN oraz gdy brak klucza API / wymuszono SYNAPSA_FORCE_PL=1: Lokalna Synapsa (0 tokenów API)
    # Uwaga: dla komercyjnych kont w języku PL zachowujemy bezbłędny styl przez Gemini jeśli klucz dostępny (Qwen2.5-Coder-7B robi kalki w języku polskim).
    use_synapsa_local = (lang != "PL") or (not gemini_key) or (os.getenv("SYNAPSA_FORCE_PL") == "1")
    if use_synapsa_local:
        try:
            from lol_agent.synapsa_engine import generate_with_synapsa, score_and_select_best_titles
            syn_res = generate_with_synapsa(
                "account_metadata",
                {
                    "account_name": brand,
                    "content_mode": acc.get("content_mode"),
                    "language": lang,
                    "subject_name": subject_name,
                    "action_type": action_type,
                    "brand_voice": voice,
                    "value_proposition": value_prop,
                    "cta_text": cta_text,
                    "location": location,
                    "phone": phone,
                    "forbidden_words": forbidden,
                },
                timeout=140,
            )
            if syn_res and (syn_res.get("title_candidates") or syn_res.get("title")):
                cands = syn_res.get("title_candidates") or [syn_res.get("title")]
                best_a, best_b = score_and_select_best_titles([str(c) for c in cands], action_type=action_type)
                if best_a:
                    if "#shorts" not in best_a.lower():
                        best_a = f"{best_a[:88]} #shorts"
                    vb = (syn_res.get("title_variant_b") or best_b or best_a).strip()
                    if "#shorts" not in vb.lower():
                        vb = f"{vb[:88]} #shorts"
                    for fw in forbidden:
                        best_a = re.sub(re.escape(fw), "", best_a, flags=re.IGNORECASE).strip()
                    desc_body = (syn_res.get("description") or value_prop or brand).strip()
                    return {
                        "title": best_a[:100],
                        "title_variant_b": vb[:100],
                        "title_variants": [best_a[:100], vb[:100]],
                        "description": desc_body,
                        "pinned_comment": (syn_res.get("pinned_comment") or cta_text).strip(),
                        "tags": [str(t).lstrip("#").lower() for t in (syn_res.get("tags") or []) if str(t).strip()][:20],
                        "hook_text": (syn_res.get("hook_text") or subject_name.upper())[:40],
                        "champion": subject_name,
                        "action_type": action_type,
                        "account_id": acc.get("account_id"),
                        "source": f"account_synapsa_{acc.get('account_id')}",
                    }
        except Exception:
            pass

    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            prompt = f"""Jesteś strategiem wideo short-form ({lang}). Napisz metadane pod YouTube Shorts / Reels / TikTok ściśle według wytycznych konta:
Marka / Kanał: {brand} ({acc.get('handle', '')})
Tryb kontentu: {acc.get('content_mode')}
Styl / Głos marki: {voice}
Główna propozycja wartości: {value_prop}
Grupa docelowa: {audience}
Temat wideo / produkt / usługa: {subject_name} (akcja/scena: {action_type})
CTA: {cta_text} {cta_url}
Lokalizacja: {location} | Telefon: {phone}
Obowiązkowe hashtagi na końcu: {tags_str}
ZAKAZANE SŁOWA (nigdy nie używaj): {', '.join(forbidden) if forbidden else 'brak'}
Język odpowiedzi: {lang}.

Zwróć wyłącznie czysty JSON:
{{
  "title": "Krótki, mocny hook max 55 znaków + 2 hashtagi z listy obowiązkowej",
  "title_variant_b": "Alternatywny tytuł testowy A/B",
  "hook_text": "3-4 SŁOWA WIELKIMI LITERAMI DO NAŁOŻENIA NA WIDEO",
  "description": "2-3 konkretne zdania zgodne z propozycją wartości, CTA, linkiem i lokalizacją jeśli podane",
  "pinned_comment": "Pytanie lub wezwanie do działania pod komentarze + link jeśli podany",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}"""
            resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            raw = (resp.text or "").strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            parsed = json.loads(raw)
            title = (parsed.get("title") or f"{subject_name} | {brand}").strip()
            if "#shorts" not in title.lower():
                title = f"{title[:88]} #shorts"
            return {
                "title": title[:100],
                "title_variant_b": (parsed.get("title_variant_b") or title)[:100],
                "title_variants": [title[:100], (parsed.get("title_variant_b") or title)[:100]],
                "description": (parsed.get("description") or "").strip(),
                "pinned_comment": (parsed.get("pinned_comment") or cta_text).strip(),
                "tags": [str(t).lstrip("#").lower() for t in (parsed.get("tags") or []) if str(t).strip()][:20],
                "hook_text": (parsed.get("hook_text") or subject_name.upper())[:40],
                "champion": subject_name,
                "action_type": action_type,
                "account_id": acc.get("account_id"),
                "source": f"account_gemini_{acc.get('account_id')}",
            }
        except Exception:
            pass

    # Deterministyczny fallback ściśle z wytycznych konta (zero wzmianek gamingowych przy innych niszach)
    clean_subj = subject_name or brand
    title = f"{clean_subj} — {brand} #shorts"[:100]
    desc_lines = [value_prop or f"{clean_subj} — {brand}"]
    if location:
        desc_lines.append(f"📍 {location}")
    if phone:
        desc_lines.append(f"📞 {phone}")
    if cta_url:
        desc_lines.append(f"🔗 {cta_text} {cta_url}".strip())
    elif cta_text:
        desc_lines.append(cta_text)
    desc_lines.append(tags_str)
    pin = f"{cta_text} {cta_url}".strip()

    return {
        "title": title,
        "title_variant_b": f"{brand}: {clean_subj} ✨ #shorts"[:100],
        "title_variants": [title, f"{brand}: {clean_subj} ✨ #shorts"[:100]],
        "description": "\n".join([l for l in desc_lines if l]),
        "pinned_comment": pin,
        "tags": [t.lstrip("#").lower() for t in (acc.get("mandatory_hashtags") or ["shorts"])],
        "hook_text": clean_subj.upper()[:35],
        "champion": clean_subj,
        "action_type": action_type,
        "account_id": acc.get("account_id"),
        "source": f"account_template_{acc.get('account_id')}",
    }
