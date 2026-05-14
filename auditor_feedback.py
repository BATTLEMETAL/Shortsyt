"""
auditor_feedback.py — Pętla zwrotna audytora jakości
=====================================================
Mechanizm uczenia audytora na podstawie realnych wyników:

1. ZAPIS (przy uploadzie):  save_pre_audit(video_id, title, audit_result)
2. WERYFIKACJA (po 24-48h): update_real_results(youtube)
3. KALIBRACJA:              recalculate_weights()
4. RAPORT:                  get_calibration_report()

Plik danych: auditor_feedback.json
Wagi:        auditor_weights.json

Zasada kalibracji:
  - Każda kategoria audytora ma wagę 1.0 (domyślnie)
  - Po zebraniu >=5 filmów: korelacja Pearsona sub_score vs real_views
  - Korelacja >0.5  → waga rośnie (max 1.5)
  - Korelacja 0-0.5 → waga neutralna (1.0)
  - Korelacja <0    → waga spada (min 0.5) — ta kategoria myli audytor
"""

import os
import json
import math
from datetime import datetime, timezone, timedelta

# Profil ustawiany przez zmienną środowiskową (domyślnie 'dark_mindset')
PROFILE_NAME = os.environ.get("SHORTSYT_PROFILE", "dark_mindset")

FEEDBACK_FILE  = f"accounts/{PROFILE_NAME}_auditor_feedback.json"
WEIGHTS_FILE   = f"accounts/{PROFILE_NAME}_auditor_weights.json"
MIN_SAMPLES_FOR_CALIBRATION = 5   # minimalna liczba filmów do kalibracji
RESULTS_CHECK_AFTER_H = 48        # sprawdź wyniki po 48h (Shorts algo dystrybuuje 48-72h, nie 24h)

# Kategorie audytora (muszą się zgadzać z quality_auditor.py)
AUDIT_CATEGORIES = ["title", "script", "hook", "ending", "uniqueness", "technical", "keywords", "ai_sense"]

# Domyślne wagi (1.0 = neutralna)
DEFAULT_WEIGHTS = {cat: 1.0 for cat in AUDIT_CATEGORIES}


# ─── Zapis rekordu przed uploadem ────────────────────────────────────────────
def save_pre_audit(video_id: str, title: str, audit_result: dict) -> None:
    """Zapisuje wynik audytu przed uploadem do późniejszego porównania z wynikami."""
    records = _load_feedback()

    # Sprawdź czy już istnieje
    for r in records:
        if r.get("video_id") == video_id:
            return  # już zapisany

    breakdown = audit_result.get("breakdown", {})
    sub_scores = {}
    for cat in AUDIT_CATEGORIES:
        cat_data = breakdown.get(cat, {})
        sub_scores[cat] = cat_data.get("score", 0)
        # Zapisz calibration_score dla ai_sense (pozytywna skala 0-15 dla Pearsona)
        if "calibration_score" in cat_data:
            sub_scores[cat + "_calibration"] = cat_data["calibration_score"]

    record = {
        "video_id":       video_id,
        "title":          title[:80],
        "upload_time":    datetime.now(timezone.utc).isoformat(),
        "audit_score":    audit_result.get("score", 0),
        "audit_decision": audit_result.get("decision", "?"),
        "sub_scores":     sub_scores,
        "real_views":     None,   # wypełnione po 24h
        "real_likes":     None,
        "real_engagement": None,
        "checked_at":     None,
        "prediction_ok":  None,   # czy audyt trafnie przewidział wynik?
    }
    records.append(record)
    _save_feedback(records)
    print(f"   📝 [FEEDBACK] Zapisano wynik audytu dla '{title[:40]}' (ID: {video_id})")


# ─── Aktualizacja realnych wyników z YouTube ─────────────────────────────────
def update_real_results(youtube) -> list[dict]:
    """
    Sprawdza YouTube API dla filmów, które:
    - zostały uploadowane >= RESULTS_CHECK_AFTER_H godzin temu
    - nie mają jeszcze real_views
    Zwraca listę zaktualizowanych rekordów.
    """
    records = _load_feedback()
    updated = []
    now = datetime.now(timezone.utc)
    check_ids = []

    for r in records:
        if r.get("real_views") is not None:
            continue  # już sprawdzony
        upload_time = r.get("upload_time", "")
        if not upload_time:
            continue
        try:
            up_dt = datetime.fromisoformat(upload_time)
            age_h = (now - up_dt).total_seconds() / 3600
            if age_h >= RESULTS_CHECK_AFTER_H:
                check_ids.append(r["video_id"])
        except Exception:
            continue

    if not check_ids:
        return []

    print(f"\n🔬 [FEEDBACK] Sprawdzam realne wyniki dla {len(check_ids)} film(ów)...")

    try:
        resp = youtube.videos().list(
            part="statistics",
            id=",".join(check_ids[:50])
        ).execute()

        stats_map = {}
        for item in resp.get("items", []):
            vid_id = item["id"]
            stats = item.get("statistics", {})
            views  = int(stats.get("viewCount", 0))
            likes  = int(stats.get("likeCount", 0))
            engage = round((likes) / max(views, 1) * 100, 2)
            stats_map[vid_id] = {"views": views, "likes": likes, "engagement": engage}

        for r in records:
            if r["video_id"] in stats_map:
                s = stats_map[r["video_id"]]
                r["real_views"]      = s["views"]
                r["real_likes"]      = s["likes"]
                r["real_engagement"] = s["engagement"]
                r["checked_at"]      = now.isoformat()

                # Czy prognoza audytu była trafna?
                # APPROVED + >= 80 views w 48h = trafna (poprz. 30 = fałszywy sukces)
                # REJECTED + < 80 = trafna
                # Weighted score: uwzględniamy engagement (views x engagement bonus)
                audit_dec = r.get("audit_decision", "")
                engagement_bonus = 1.0 + (s["engagement"] / 10)  # 5% eng = x1.5
                weighted = int(s["views"] * engagement_bonus)
                r["weighted_score"] = weighted  # zapisz do późniejszej kalibracji
                APPROVAL_VIEW_THRESHOLD = 80
                if audit_dec == "APPROVED":
                    r["prediction_ok"] = s["views"] >= APPROVAL_VIEW_THRESHOLD
                else:
                    r["prediction_ok"] = s["views"] < APPROVAL_VIEW_THRESHOLD

                updated.append(r)
                verdict = "✅ TRAFNA" if r["prediction_ok"] else "❌ BŁĘDNA"
                print(f"   {verdict} prognoza: '{r['title'][:40]}' — "
                      f"audit={r['audit_score']}/100 → {s['views']} views")

    except Exception as e:
        print(f"   ⚠️  [FEEDBACK] Błąd pobierania danych YT: {e}")

    _save_feedback(records)
    return updated


# ─── Kalibracja wag ──────────────────────────────────────────────────────────
def recalculate_weights() -> dict:
    """
    Oblicza nowe wagi dla każdej kategorii audytora na podstawie
    korelacji Pearsona między sub_score a real_views.

    FILTROWANIE: Wyklucza filmy z okresu suppresji algorytmu
    (views < 5 po 48h = nie mówi o jakości, tylko o karze algorytmu).
    """
    records = _load_feedback()

    # Tylko rekordy z realnymi wynikami
    all_valid = [r for r in records
                 if r.get("real_views") is not None and r.get("sub_scores")]

    # Filtruj filmy z okresu suppresji:
    # Film jest uznany za "sprawiedliwie oceniony" gdy MA >= MIN_VIEWS LUB jest wystarczająco stary
    MIN_VIEWS_FOR_CALIBRATION = 10  # minimum views żeby film nie był uznany za supressed
    reliable = []
    suppressed_excluded = []

    for r in all_valid:
        views = r.get("real_views", 0)
        upload_time = r.get("upload_time", "")
        age_h = 0
        try:
            from datetime import datetime, timezone
            up_dt = datetime.fromisoformat(upload_time)
            age_h = (datetime.now(timezone.utc) - up_dt).total_seconds() / 3600
        except Exception:
            pass

        # Film jest "reliable" jeśli:
        # 1. Ma >= MIN_VIEWS (algorytm go normalnie podsycał)
        # 2. LUB jest bardzo stary (>= 14 dni) z bardzo niskimi views (niszowy temat)
        if views >= MIN_VIEWS_FOR_CALIBRATION:
            reliable.append(r)
        elif age_h >= 14 * 24 and views > 0:  # stary film z jakimikolwiek views
            reliable.append(r)
        else:
            suppressed_excluded.append(r)

    if suppressed_excluded:
        print(f"   ⚠️  [KALIBRACJA] Wykluczone {len(suppressed_excluded)} filmów z okresu suppresji "
              f"(views < {MIN_VIEWS_FOR_CALIBRATION})")

    if len(reliable) < MIN_SAMPLES_FOR_CALIBRATION:
        print(f"   ℹ️  [KALIBRACJA] Za mało wiarygodnych danych "
              f"({len(reliable)}/{MIN_SAMPLES_FOR_CALIBRATION} po filtrowaniu suppresji).")
        print(f"   ℹ️  Aby skalibrować audytora potrzeba >= {MIN_SAMPLES_FOR_CALIBRATION} filmów z >= {MIN_VIEWS_FOR_CALIBRATION} views.")
        print(f"   ℹ️  Wagi pozostają domyślne (1.0x) do czasu zebrania danych.")
        return DEFAULT_WEIGHTS.copy()

    print(f"   ℹ️  [KALIBRACJA] Kalibruję na {len(reliable)} wiarygodnych filmach "
          f"(wykluczone: {len(suppressed_excluded)} suppressed).")

    views_list = [r.get("weighted_score") or r["real_views"] for r in reliable]
    weights = {}

    for cat in AUDIT_CATEGORIES:
        # ai_sense ma calibration_score (0-15) zamiast ujemnego raw score
        # — bez tego Pearson zawsze daje ujemna korelacje dla ai_sense
        scores_list = [
            r["sub_scores"].get(cat + "_calibration", r["sub_scores"].get(cat, 0))
            for r in reliable
        ]
        corr = _pearson(scores_list, views_list)

        if corr is None:
            weights[cat] = 1.0
        elif corr > 0.5:
            weights[cat] = min(1.0 + corr * 0.5, 1.5)
        elif corr > 0.0:
            weights[cat] = 1.0
        else:
            weights[cat] = max(0.5, 1.0 + corr * 0.5)

    _save_weights(weights)
    return weights


# ─── Raport kalibracji ───────────────────────────────────────────────────────
def get_calibration_report() -> str:
    """Zwraca czytelny raport porównujący prognozy audytora z realnymi wynikami."""
    records = _load_feedback()
    valid   = [r for r in records if r.get("real_views") is not None]
    weights = load_adaptive_weights()

    if not valid:
        return "   ℹ️  Brak danych do raportu (żaden film nie ma jeszcze realnych wyników)."

    lines = ["\n╔══════════════════════════════════════════════════════════════╗",
             "║  📊 AUDITOR FEEDBACK — Prognoza vs Realne Wyniki             ║",
             "╠══════════════════════════════════════════════════════════════╣"]

    correct = sum(1 for r in valid if r.get("prediction_ok"))
    accuracy = round(correct / len(valid) * 100) if valid else 0
    lines.append(f"  Trafność prognoz: {correct}/{len(valid)} ({accuracy}%)")
    lines.append(f"  Filmów przeanalizowanych: {len(records)} total, {len(valid)} z wynikami")
    lines.append("")

    # Top 3 najlepsze i najgorsze filmy wg wyników
    sorted_valid = sorted(valid, key=lambda x: x["real_views"], reverse=True)

    lines.append("  🏆 TOP 3 (realne wyniki):")
    for r in sorted_valid[:3]:
        verdict = "✅" if r.get("prediction_ok") else "❌ błąd"
        lines.append(f"    {verdict} [{r['audit_score']}/100] → {r['real_views']} views | '{r['title'][:45]}'")

    if len(sorted_valid) > 3:
        lines.append("\n  📉 Najsłabsze (wg wyników):")
        for r in sorted_valid[-3:]:
            verdict = "✅" if r.get("prediction_ok") else "❌ błąd"
            lines.append(f"    {verdict} [{r['audit_score']}/100] → {r['real_views']} views | '{r['title'][:45]}'")

    # Wagi
    lines.append("\n  ⚖️  AKTUALNE WAGI (po kalibracji):")
    for cat, w in weights.items():
        if w > 1.1:
            indicator = "↑ silna korelacja"
        elif w < 0.9:
            indicator = "↓ słaba korelacja"
        else:
            indicator = "→ neutralna"
        bar = "█" * int(w * 8) + "░" * (12 - int(w * 8))
        lines.append(f"    {cat:<14} [{bar}] {w:.2f}x  {indicator}")

    lines.append("╚══════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


# ─── Ładowanie wag ───────────────────────────────────────────────────────────
def load_adaptive_weights() -> dict:
    """Ładuje aktualne wagi audytora (po kalibracji lub domyślne)."""
    if not os.path.exists(WEIGHTS_FILE):
        return DEFAULT_WEIGHTS.copy()
    try:
        with open(WEIGHTS_FILE, "r", encoding="utf-8") as f:
            w = json.load(f)
        # Upewnij się że wszystkie kategorie są
        for cat in AUDIT_CATEGORIES:
            if cat not in w:
                w[cat] = 1.0
        return w
    except Exception:
        return DEFAULT_WEIGHTS.copy()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _load_feedback() -> list:
    if not os.path.exists(FEEDBACK_FILE):
        return []
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_feedback(records: list) -> None:
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def _save_weights(weights: dict) -> None:
    with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2, ensure_ascii=False)
    print(f"   ✅ [KALIBRACJA] Wagi zaktualizowane → {WEIGHTS_FILE}")


def _pearson(x: list, y: list) -> float | None:
    """Korelacja Pearsona między dwiema listami."""
    n = len(x)
    if n < 3:
        return None
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


# ─── CLI standalone ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    if "--report" in sys.argv:
        print(get_calibration_report())
    elif "--recalibrate" in sys.argv:
        w = recalculate_weights()
        print("Nowe wagi:")
        for k, v in w.items():
            print(f"  {k:<14}: {v:.2f}x")
    else:
        print("Użycie: python auditor_feedback.py --report | --recalibrate")
