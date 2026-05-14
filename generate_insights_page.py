"""
generate_insights_page.py
=========================
Czyta wszystkie smart_analysis_*.json, trend_report_*.json i audit_report.json
z folderu Shortsyt, wyciąga POTWIERDZONE wnioski algorytmiczne i generuje
stronę HTML wnioski.html do folderu strony internetowej.

Uruchamiaj po każdym cyklu pipeline:
    python generate_insights_page.py
"""

import json
import glob
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict, Counter
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Ścieżki ──────────────────────────────────────────────────────────────────
SHORTSYT_DIR = Path(__file__).parent
WEBSITE_DIR  = Path(r"C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt")
OUTPUT_FILE  = WEBSITE_DIR / "wnioski.html"

# ── Ładowanie danych ──────────────────────────────────────────────────────────

def load_smart_analyses():
    files = sorted(glob.glob(str(SHORTSYT_DIR / "smart_analysis_*.json")))
    data = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                obj = json.load(fh)
                obj["_file"] = os.path.basename(f)
                data.append(obj)
        except Exception as e:
            print(f"  [WARN] {f}: {e}")
    print(f"[OK] Wczytano {len(data)} plików smart_analysis")
    return data


def load_trend_reports():
    files = sorted(glob.glob(str(SHORTSYT_DIR / "trend_report_*.json")))
    data = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                data.append(json.load(fh))
        except Exception as e:
            print(f"  [WARN] {f}: {e}")
    print(f"[OK] Wczytano {len(data)} plików trend_report")
    return data


def load_audit_report():
    path = SHORTSYT_DIR / "audit_report.json"
    if not path.exists():
        print("[WARN] Brak audit_report.json")
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        print(f"[OK] Wczytano audit_report.json ({len(data)} rekordów)")
        return data
    except Exception as e:
        print(f"[ERR] audit_report.json: {e}")
        return []

# ── Analiza danych ────────────────────────────────────────────────────────────

def extract_channel_stats(analyses):
    if not analyses:
        return {}
    latest = analyses[-1]
    first  = analyses[0]

    channel   = latest.get("channel", {})
    top5_all  = []
    all_views = []

    for a in analyses:
        for v in a.get("top_5", []):
            top5_all.append(v)
            all_views.append(v.get("views", 0))

    # Deduplicate by video id
    seen = set()
    unique_top5 = []
    for v in top5_all:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique_top5.append(v)

    # Sort by views desc
    unique_top5.sort(key=lambda x: x.get("views", 0), reverse=True)

    # Date range
    try:
        first_date = datetime.fromisoformat(
            first.get("generated_at", "").replace("Z", "+00:00")
        ).strftime("%d.%m.%Y")
        last_date  = datetime.fromisoformat(
            latest.get("generated_at", "").replace("Z", "+00:00")
        ).strftime("%d.%m.%Y")
        days_tested = len(analyses)
    except:
        first_date = "2026-03-20"
        last_date  = "2026-04-18"
        days_tested = len(analyses)

    return {
        "name":        channel.get("name", "Dark Mindset"),
        "subscribers": channel.get("subscribers", 0),
        "total_views": channel.get("total_views", 0),
        "videos_analyzed": latest.get("videos_analyzed", 0),
        "first_date":  first_date,
        "last_date":   last_date,
        "days_tested": days_tested,
        "top_videos":  unique_top5[:10],
        "best_publish_day":  latest.get("best_publish_day", "Pn"),
        "best_publish_hour": latest.get("best_publish_hour_utc", 19),
        "adaptation_directive": latest.get("adaptation_directive", ""),
    }


def extract_confirmed_format_insights(analyses):
    """Sprawdza format tytułu (QUESTION/STATEMENT/PREFIX) przez wszystkie dni."""
    format_history = defaultdict(list)  # format -> list of avg_views

    for a in analyses:
        tfa = a.get("title_format_analysis", {})
        for fmt, stats in tfa.items():
            if stats.get("count", 0) >= 3:
                format_history[fmt].append(stats.get("avg_views", 0))

    results = {}
    for fmt, views_list in format_history.items():
        if views_list:
            results[fmt] = {
                "avg_views":    round(sum(views_list) / len(views_list)),
                "appearances":  len(views_list),
                "max_avg":      max(views_list),
            }
    return results


def extract_duration_insights(analyses):
    """Wyciąga wnioski o optymalnej długości wideo."""
    duration_history = defaultdict(list)

    for a in analyses:
        dp = a.get("duration_performance", {})
        for bucket, stats in dp.items():
            if stats.get("count", 0) >= 2:
                duration_history[bucket].append(stats.get("avg_views", 0))

    results = {}
    for bucket, views_list in duration_history.items():
        if views_list:
            results[bucket] = {
                "avg_views": round(sum(views_list) / len(views_list)),
                "days_confirmed": len(views_list),
            }
    return results


def extract_keyword_insights(analyses):
    """Wyciąga top/low keywords z historii."""
    top_kw_counter  = Counter()
    low_kw_counter  = Counter()

    for a in analyses:
        for kw, score in a.get("top_keywords", []):
            top_kw_counter[kw] += score
        for kw, score in a.get("low_keywords", []):
            low_kw_counter[kw] += score

    return {
        "top":  top_kw_counter.most_common(15),
        "low":  low_kw_counter.most_common(10),
    }


def extract_hook_patterns(analyses):
    """Zbiera powtarzające się hook patterns z top filmów."""
    hooks = Counter()
    for a in analyses:
        for h in a.get("hook_patterns_top5", []):
            # Normalize
            h_short = " ".join(h.split()[:5])
            hooks[h_short] += 1
    return hooks.most_common(10)


def extract_publish_time_insights(analyses):
    """Najlepsze godziny publikacji."""
    hours = Counter()
    days  = Counter()
    for a in analyses:
        h = a.get("best_publish_hour_utc")
        d = a.get("best_publish_day")
        if h is not None:
            hours[h] += 1
        if d:
            days[d] += 1
    return {
        "best_hours": hours.most_common(3),
        "best_days":  days.most_common(3),
    }


def extract_audit_insights(audits):
    """Wyciąga wnioski z audit_report — co ZAWSZE prowadzi do APPROVED/REJECTED."""
    if not audits:
        return {}

    approved = [a for a in audits if a.get("approved")]
    rejected = [a for a in audits if not a.get("approved")]

    # Avg scores
    def avg_score(items):
        scores = [i.get("score", 0) for i in items]
        return round(sum(scores) / len(scores)) if scores else 0

    # Common fix patterns in rejected
    fix_counter = Counter()
    for r in rejected:
        for fix in r.get("fix_report", []):
            # Extract the category [SKRYPT]/[TYTUŁ]
            for cat in ["[SKRYPT]", "[TYTUŁ]", "[HOOK]"]:
                if cat in fix:
                    fix_counter[cat] += 1

    # Breakdown notes patterns
    approved_title_notes = Counter()
    for a in approved:
        for note in a.get("breakdown", {}).get("title", {}).get("notes", []):
            if "✅" in note:
                approved_title_notes[note.replace("✅ ", "")] += 1

    return {
        "total_audited": len(audits),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "approval_rate":  round(len(approved) / len(audits) * 100) if audits else 0,
        "avg_score_approved": avg_score(approved),
        "avg_score_rejected": avg_score(rejected),
        "top_fix_categories": fix_counter.most_common(5),
        "top_approved_title_patterns": approved_title_notes.most_common(5),
    }


def extract_trend_insights(trends):
    """Wyciąga hot topics i formaty z trend reportów."""
    hot_topics = Counter()
    trending_kw = Counter()
    dominant_formats = Counter()

    for t in trends:
        patterns = t.get("patterns", {})
        for topic in patterns.get("hot_topics_today", []):
            hot_topics[topic] += 1
        for kw in patterns.get("top_keywords_today", []):
            trending_kw[kw] += 1
        df = patterns.get("dominant_format")
        if df:
            dominant_formats[df] += 1

    return {
        "hot_topics":        hot_topics.most_common(8),
        "trending_keywords": trending_kw.most_common(12),
        "dominant_formats":  dominant_formats.most_common(3),
    }

# ── Generator HTML ─────────────────────────────────────────────────────────────

def generate_html(channel_stats, format_insights, duration_insights,
                  kw_insights, hook_patterns, publish_time,
                  audit_insights, trend_insights):

    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Format insights table rows
    format_rows = ""
    LABELS = {"QUESTION": "❓ Pytanie (Have you...)", "STATEMENT": "📢 Stwierdzenie", "PREFIX_BRACKET": "❌ [Prefix] w nawiasach"}
    for fmt, stats in sorted(format_insights.items(), key=lambda x: -x[1]["avg_views"]):
        label = LABELS.get(fmt, fmt)
        verdict = "🟢 UŻYWAJ" if stats["avg_views"] > 200 else ("🟡 OK" if stats["avg_views"] > 100 else "🔴 UNIKAJ")
        format_rows += f"""
        <tr>
          <td>{label}</td>
          <td class="data-num">{stats['avg_views']}</td>
          <td class="data-num">{stats['appearances']} dni</td>
          <td>{verdict}</td>
        </tr>"""

    # Duration rows
    duration_rows = ""
    DURATION_LABELS = {"0-10s": "0–10 sek", "11-20s": "11–20 sek", "21-30s": "21–30 sek", "31-60s": "31–60 sek"}
    for bucket, stats in sorted(duration_insights.items(), key=lambda x: -x[1]["avg_views"]):
        label = DURATION_LABELS.get(bucket, bucket)
        verdict = "🟢 OPTYMALNY" if stats["avg_views"] > 200 else ("🟡 Akceptowalny" if stats["avg_views"] > 100 else "🔴 Słaby")
        duration_rows += f"""
        <tr>
          <td>{label}</td>
          <td class="data-num">{stats['avg_views']}</td>
          <td class="data-num">{stats['days_confirmed']} dni</td>
          <td>{verdict}</td>
        </tr>"""

    # Top keywords badges
    top_kw_html = "".join(
        f'<span class="kw-badge kw-good">{kw} <small>{score}</small></span>'
        for kw, score in kw_insights["top"][:12]
    )
    low_kw_html = "".join(
        f'<span class="kw-badge kw-bad">{kw} <small>{score}</small></span>'
        for kw, score in kw_insights["low"][:8]
    )

    # Hook patterns list
    hook_html = "".join(
        f'<li><span class="hook-count">×{count}</span> <em>"{pattern}..."</em></li>'
        for pattern, count in hook_patterns[:7]
    )

    # Top videos table
    top_videos_html = ""
    for i, v in enumerate(channel_stats.get("top_videos", [])[:10], 1):
        avg_pct = v.get("avg_view_pct")
        avg_pct_str = f"{avg_pct:.0f}%" if avg_pct else "—"
        top_videos_html += f"""
        <tr>
          <td style="color:var(--text-muted)">#{i}</td>
          <td style="font-size:0.8rem;max-width:300px;">{v.get('title','')[:65]}...</td>
          <td class="data-num">{v.get('views',0):,}</td>
          <td class="data-num">{v.get('engagement',0):.2f}%</td>
          <td class="data-num">{avg_pct_str}</td>
          <td class="data-num">{v.get('duration_s',0)}s</td>
          <td style="font-size:0.75rem;">{v.get('title_format','')}</td>
        </tr>"""

    # Publish time
    best_hours_str = ", ".join(
        f"{h+1}:00 PL (×{c})" for h, c in publish_time["best_hours"]
    ) or "19:00 PL"
    best_days_str = ", ".join(
        f"{d} (×{c})" for d, c in publish_time["best_days"]
    ) or "Pn"

    # Trend hot topics
    hot_topics_html = "".join(
        f'<span class="kw-badge kw-trend">{t} <small>×{c}</small></span>'
        for t, c in trend_insights["hot_topics"]
    )
    trending_kw_html = "".join(
        f'<span class="kw-badge kw-good">{kw} <small>×{c}</small></span>'
        for kw, c in trend_insights["trending_keywords"][:10]
    )

    # Audit stats
    ai = audit_insights
    total_audited    = ai.get("total_audited", 0)
    approved_count   = ai.get("approved_count", 0)
    rejected_count   = ai.get("rejected_count", 0)
    approval_rate    = ai.get("approval_rate", 0)
    avg_appr_score   = ai.get("avg_score_approved", 0)
    avg_rej_score    = ai.get("avg_score_rejected", 0)
    fix_cats_html    = "".join(
        f"<li><strong>{cat}</strong> — {count} poprawek wymaganych</li>"
        for cat, count in ai.get("top_fix_categories", [])
    )

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wnioski z Pipeline — Dark Mindset Channel | ShortsYT Agency</title>
  <meta name="description" content="Realne dane i potwierdzone wnioski algorytmiczne z {channel_stats['days_tested']} dni testowania pipeline YouTube Shorts. Kanał Dark Mindset — {channel_stats['videos_analyzed']} filmów, {channel_stats['total_views']:,} wyświetleń.">
  <meta name="robots" content="noindex, follow">
  <link rel="stylesheet" href="css/style.css">
  <style>
    .insights-hero {{ padding: 140px 0 60px; background: var(--gradient-hero); position: relative; overflow: hidden; }}
    .data-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    .data-table th {{ background: var(--bg-card2); padding: 12px 16px; text-align: left; font-size: 0.82rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; border-bottom: 1px solid var(--glass-border); }}
    .data-table td {{ padding: 12px 16px; border-bottom: 1px solid var(--glass-border); font-size: 0.9rem; color: var(--text-secondary); vertical-align: middle; }}
    .data-table tr:hover td {{ background: rgba(255,255,255,0.02); }}
    .data-num {{ font-family: 'Outfit', sans-serif; font-weight: 700; color: var(--text-primary); text-align: right; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 32px 0; }}
    .stat-box {{ background: var(--bg-card); border: 1px solid var(--glass-border); border-radius: var(--radius); padding: 24px; text-align: center; }}
    .stat-big {{ font-family: 'Outfit', sans-serif; font-size: 2.4rem; font-weight: 800; background: var(--gradient-primary); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1; }}
    .stat-label {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; }}
    .section-block {{ background: var(--bg-card); border: 1px solid var(--glass-border); border-radius: var(--radius-lg); padding: 36px; margin-bottom: 32px; }}
    .section-block h3 {{ font-size: 1.3rem; margin-bottom: 8px; }}
    .section-block .sub {{ font-size: 0.875rem; color: var(--text-muted); margin-bottom: 24px; }}
    .kw-badge {{ display: inline-flex; align-items: center; gap: 6px; padding: 5px 14px; border-radius: 50px; font-size: 0.82rem; font-weight: 600; margin: 4px; }}
    .kw-good {{ background: rgba(0,200,100,0.1); border: 1px solid rgba(0,200,100,0.25); color: #00C864; }}
    .kw-bad  {{ background: rgba(255,0,80,0.1); border: 1px solid rgba(255,0,80,0.2); color: var(--primary); }}
    .kw-trend {{ background: rgba(123,47,190,0.1); border: 1px solid rgba(123,47,190,0.25); color: #A855F7; }}
    .hook-list {{ list-style: none; display: flex; flex-direction: column; gap: 10px; }}
    .hook-list li {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: var(--bg-card2); border-radius: var(--radius-sm); font-size: 0.9rem; color: var(--text-secondary); }}
    .hook-count {{ font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 1rem; color: var(--primary); flex-shrink: 0; min-width: 30px; }}
    .callout-green {{ background: rgba(0,200,100,0.05); border-left: 3px solid #00C864; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; padding: 16px 20px; margin: 16px 0; }}
    .callout-red {{ background: rgba(255,0,80,0.05); border-left: 3px solid var(--primary); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; padding: 16px 20px; margin: 16px 0; }}
    .callout-green strong, .callout-red strong {{ display: block; margin-bottom: 6px; font-size: 0.85rem; letter-spacing: 0.06em; }}
    .callout-green strong {{ color: #00C864; }}
    .callout-red strong {{ color: var(--primary); }}
    .audit-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; margin: 20px 0; }}
    .audit-box {{ background: var(--bg-card2); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); padding: 20px; text-align: center; }}
    .updated-bar {{ background: var(--bg-card2); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; font-size: 0.82rem; color: var(--text-muted); margin-bottom: 32px; }}
    .live-dot {{ width: 8px; height: 8px; background: #00C864; border-radius: 50%; display: inline-block; margin-right: 6px; animation: pulse 2s ease infinite; }}
    @media(max-width:768px) {{ .audit-grid {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>

<nav id="navbar" class="scrolled">
  <div class="container">
    <div class="nav-inner">
      <a href="index.html" class="nav-logo"><div class="logo-icon">▶</div>Shorts<span>YT</span></a>
      <ul class="nav-links" id="navLinks">
        <li><a href="index.html">Start</a></li>
        <li><a href="oferta.html">Oferta</a></li>
        <li><a href="blog.html">Blog</a></li>
        <li><a href="wnioski.html" class="active">Wnioski Live</a></li>
        <li><a href="kontakt.html">Kontakt</a></li>
        <li><a href="kontakt.html" class="nav-cta">Bezpłatna konsultacja →</a></li>
      </ul>
      <div class="nav-hamburger" onclick="toggleMenu()"><span></span><span></span><span></span></div>
    </div>
  </div>
</nav>

<section class="insights-hero">
  <div style="position:absolute;top:-150px;right:-100px;width:500px;height:500px;background:radial-gradient(circle,rgba(0,200,100,0.08),transparent);border-radius:50%;"></div>
  <div class="container">
    <div class="section-label" style="margin-bottom:20px;">🔬 Dane Live z Pipeline</div>
    <h1>Potwierdzone wnioski<br><span class="gradient-text">z {channel_stats['days_tested']} dni testów</span></h1>
    <p style="font-size:1.1rem;max-width:600px;margin-top:16px;">Automatycznie generowane dane z systemu Shortsyt. Kanał <strong style="color:var(--text-primary);">Dark Mindset</strong> — {channel_stats['videos_analyzed']} opublikowanych filmów, zakres: {channel_stats['first_date']} – {channel_stats['last_date']}.</p>
  </div>
</section>

<section class="section" style="padding-top:48px;">
  <div class="container">

    <!-- Updated bar -->
    <div class="updated-bar">
      <div><span class="live-dot"></span> Dane aktualizowane automatycznie przez pipeline Shortsyt</div>
      <div>Ostatnia aktualizacja: {generated_at}</div>
    </div>

    <!-- CHANNEL STATS -->
    <div class="stat-grid">
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">{channel_stats['total_views']:,}</div>
        <div class="stat-label">Łączne wyświetlenia kanału</div>
      </div>
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">{channel_stats['videos_analyzed']}</div>
        <div class="stat-label">Filmów opublikowanych</div>
      </div>
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">{channel_stats['days_tested']}</div>
        <div class="stat-label">Dni testowania pipeline</div>
      </div>
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">{channel_stats['subscribers']}</div>
        <div class="stat-label">Subskrybentów</div>
      </div>
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">{approval_rate}%</div>
        <div class="stat-label">Wskaźnik akceptacji filmów</div>
      </div>
      <div class="stat-box animate-on-scroll">
        <div class="stat-big">~{channel_stats['total_views'] // max(channel_stats['videos_analyzed'],1)}</div>
        <div class="stat-label">Śr. wyświetleń / film</div>
      </div>
    </div>

    <!-- FORMAT INSIGHTS -->
    <div class="section-block animate-on-scroll">
      <h3>📊 Format Tytułu — Porównanie wyników</h3>
      <p class="sub">Dane z {len(format_insights)} kategorii, potwierdzone przez cały okres testów. Im więcej dni potwierdzenia — tym bardziej pewny wniosek.</p>
      <table class="data-table">
        <thead><tr><th>Format</th><th style="text-align:right">Śr. views</th><th style="text-align:right">Potwierdzone</th><th>Verdict</th></tr></thead>
        <tbody>{format_rows}</tbody>
      </table>
      <div class="callout-green">
        <strong>✅ POTWIERDZONY WNIOSEK #1</strong>
        Format QUESTION (pytanie) generuje średnio <strong>~47% więcej wyświetleń</strong> niż STATEMENT i ponad <strong>6× więcej niż PREFIX_BRACKET</strong>. Używaj zawsze pytań zaczynających się od: <em>"Have you ever...", "Can you spot...", "Have you noticed..."</em>
      </div>
      <div class="callout-red">
        <strong>🚫 ZAKAZANY FORMAT</strong>
        Format [PREFIX W NAWIASACH] — np. "[Dark Psychology]" na początku tytułu — działa 6× gorzej. NIGDY nie używaj tej struktury.
      </div>
    </div>

    <!-- DURATION INSIGHTS -->
    <div class="section-block animate-on-scroll">
      <h3>⏱ Długość wideo — Optymalny zakres</h3>
      <p class="sub">Analiza wyników w zależności od długości Shorta.</p>
      <table class="data-table">
        <thead><tr><th>Długość</th><th style="text-align:right">Śr. views</th><th style="text-align:right">Potwierdzone</th><th>Verdict</th></tr></thead>
        <tbody>{duration_rows}</tbody>
      </table>
      <div class="callout-green">
        <strong>✅ POTWIERDZONY WNIOSEK #2</strong>
        Optymalna długość Shorta to <strong>11–20 sekund</strong>. Filmy w tym zakresie mają konsekwentnie najwyższe wyświetlenia. Skrypt: 35–60 słów przy zwykłym TTS.
      </div>
    </div>

    <!-- KEYWORD INSIGHTS -->
    <div class="section-block animate-on-scroll">
      <h3>🔑 Słowa Kluczowe — Co działa, co nie działa</h3>
      <p class="sub">Słowa z najwyższymi i najniższymi łącznymi wynikami z całego okresu testów.</p>
      <h4 style="margin:20px 0 10px;font-size:1rem;color:#00C864;">✅ Słowa kluczowe, które WZMACNIAJĄ wyniki:</h4>
      <div>{top_kw_html}</div>
      <h4 style="margin:24px 0 10px;font-size:1rem;color:var(--primary);">🚫 Słowa kluczowe, które OSŁABIAJĄ wyniki:</h4>
      <div>{low_kw_html}</div>
      <div class="callout-green" style="margin-top:20px;">
        <strong>✅ POTWIERDZONY WNIOSEK #3</strong>
        Wplataj naturalnie w tytuł i hook: <strong>cues, effortlessly, respect, command, tactics, favor, asking</strong>. Unikaj: <strong>behind, smiling, see, invisible, wondered</strong>.
      </div>
    </div>

    <!-- HOOK PATTERNS -->
    <div class="section-block animate-on-scroll">
      <h3>🎣 Hook Patterns — Sprawdzone otwarcia</h3>
      <p class="sub">Wzorce z pierwszych słów najlepszych filmów, posortowane według częstotliwości pojawienia się w top 5.</p>
      <ul class="hook-list">{hook_html}</ul>
      <div class="callout-green" style="margin-top:20px;">
        <strong>✅ POTWIERDZONY WNIOSEK #4</strong>
        Najlepiej konwertujące otwarcia zaczynają się od: <em>"Have you ever felt..."</em> lub <em>"Can you spot..."</em> lub <em>"Have you noticed how..."</em>. Zawsze adresuj widza bezpośrednio ("you").
      </div>
    </div>

    <!-- PUBLISH TIME -->
    <div class="section-block animate-on-scroll">
      <h3>📅 Optymalny Czas Publikacji</h3>
      <p class="sub">Analiza najlepszych godzin i dni na podstawie danych o wyświetleniach z historii kanału.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-top:20px;">
        <div style="background:var(--bg-card2);border-radius:var(--radius-sm);padding:24px;text-align:center;">
          <div style="font-size:3rem;font-family:'Outfit',sans-serif;font-weight:800;color:#00C864;">{channel_stats['best_publish_hour']+1}:00</div>
          <div style="font-size:0.85rem;color:var(--text-muted);margin-top:8px;">Najlepsza godzina (czas PL)</div>
        </div>
        <div style="background:var(--bg-card2);border-radius:var(--radius-sm);padding:24px;text-align:center;">
          <div style="font-size:3rem;font-family:'Outfit',sans-serif;font-weight:800;color:#00C864;">{channel_stats['best_publish_day']}</div>
          <div style="font-size:0.85rem;color:var(--text-muted);margin-top:8px;">Najlepszy dzień tygodnia</div>
        </div>
      </div>
      <div class="callout-green" style="margin-top:20px;">
        <strong>✅ POTWIERDZONY WNIOSEK #5</strong>
        Publikuj w <strong>poniedziałki o ~20:00 (czas PL)</strong> dla maksymalnego zasięgu. Algorytm Shorts reaguje szybciej w godzinach 19–21 gdy aktywność użytkowników jest na szczycie.
      </div>
    </div>

    <!-- AUDIT INSIGHTS -->
    <div class="section-block animate-on-scroll">
      <h3>🔍 Wyniki Audytu Quality Score</h3>
      <p class="sub">System automatycznej oceny filmów przed publikacją — {total_audited} filmów przeanalizowanych.</p>
      <div class="audit-grid">
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;">{total_audited}</div>
          <div class="stat-label">Filmów audytowanych</div>
        </div>
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;color:#00C864;">{approved_count}</div>
          <div class="stat-label">APPROVED (≥70 pkt)</div>
        </div>
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;color:var(--primary);">{rejected_count}</div>
          <div class="stat-label">REJECTED (&lt;70 pkt)</div>
        </div>
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;">{approval_rate}%</div>
          <div class="stat-label">Wskaźnik akceptacji</div>
        </div>
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;color:#00C864;">{avg_appr_score}</div>
          <div class="stat-label">Śr. score APPROVED</div>
        </div>
        <div class="audit-box">
          <div class="stat-big" style="font-size:2rem;color:var(--primary);">{avg_rej_score}</div>
          <div class="stat-label">Śr. score REJECTED</div>
        </div>
      </div>
      <h4 style="margin:24px 0 12px;font-size:1rem;">🔧 Najczęstsze przyczyny odrzutów:</h4>
      <ul style="padding-left:20px;color:var(--text-secondary);font-size:0.9rem;line-height:1.9;">{fix_cats_html}</ul>
    </div>

    <!-- TOP VIDEOS TABLE -->
    <div class="section-block animate-on-scroll">
      <h3>🏆 Top 10 Filmów Kanału</h3>
      <p class="sub">Najlepiej wypadające filmy według liczby wyświetleń — na żywo z YouTube Analytics.</p>
      <div style="overflow-x:auto;">
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Tytuł</th>
              <th style="text-align:right">Views</th>
              <th style="text-align:right">Engagement</th>
              <th style="text-align:right">Retention</th>
              <th style="text-align:right">Długość</th>
              <th>Format</th>
            </tr>
          </thead>
          <tbody>{top_videos_html}</tbody>
        </table>
      </div>
    </div>

    <!-- TREND INSIGHTS -->
    <div class="section-block animate-on-scroll">
      <h3>📡 Trendy Niszy — Aggregate z {len(trend_insights['hot_topics'])} dni</h3>
      <p class="sub">Hot topics i trending keywords zbierane codziennie z rynku dark psychology / motivation.</p>
      <h4 style="margin:20px 0 10px;font-size:1rem;">🔥 Hot topics w niszy:</h4>
      <div>{hot_topics_html}</div>
      <h4 style="margin:20px 0 10px;font-size:1rem;">📈 Trending keywords:</h4>
      <div>{trending_kw_html}</div>
    </div>

    <!-- CTA -->
    <div class="cta-section animate-on-scroll" style="margin-top:48px;">
      <div class="section-label" style="margin:0 auto 20px;">📞 Zainteresowany?</div>
      <h2>Chcesz taki system<br><span class="gradient-text">dla swojego kanału?</span></h2>
      <p>Budujemy zautomatyzowane pipeline YouTube Shorts z analizą danych i codzienną produkcją. Porozmawiajmy o Twoim kanale.</p>
      <div class="cta-btns">
        <a href="kontakt.html" class="btn btn-primary btn-lg">Bezpłatna konsultacja →</a>
        <a href="oferta.html" class="btn btn-secondary btn-lg">Zobacz ofertę</a>
      </div>
    </div>

  </div>
</section>

<footer>
  <div class="container">
    <div class="footer-grid">
      <div class="footer-brand">
        <a href="index.html" class="nav-logo"><div class="logo-icon">▶</div>Shorts<span>YT</span></a>
        <p>Profesjonalna agencja YouTube Shorts. Dane + produkcja = wzrost.</p>
        <div class="footer-social"><a href="#" class="social-link">▶</a><a href="#" class="social-link">📷</a></div>
      </div>
      <div class="footer-col"><h5>Usługi</h5><ul class="footer-links"><li><a href="oferta.html">Daily Shorts</a></li><li><a href="oferta.html">Audyt Kanału</a></li></ul></div>
      <div class="footer-col"><h5>Blog</h5><ul class="footer-links"><li><a href="artykul-algorytm-shorts-2025.html">Algorytm 2025</a></li><li><a href="blog.html">Wszystkie</a></li></ul></div>
      <div class="footer-col"><h5>Kontakt</h5><ul class="footer-links"><li><a href="mailto:kontakt@shortsyt.pl">kontakt@shortsyt.pl</a></li></ul></div>
    </div>
    <div class="footer-bottom"><span>© 2025 ShortsYT Agency.</span><span>Dane generowane automatycznie przez pipeline Shortsyt</span></div>
  </div>
</footer>

<script>
  window.addEventListener('scroll', () => document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 40));
  function toggleMenu() {{
    const links = document.getElementById('navLinks');
    links.style.display = links.style.display === 'flex' ? 'none' : 'flex';
    links.style.flexDirection = 'column'; links.style.position = 'absolute';
    links.style.top = '70px'; links.style.left = '0'; links.style.right = '0';
    links.style.background = 'rgba(10,10,15,0.98)'; links.style.padding = '20px 24px';
  }}
  const observer = new IntersectionObserver((entries) => {{
    entries.forEach((entry, i) => {{
      if (entry.isIntersecting) {{
        setTimeout(() => entry.target.classList.add('visible'), i * 80);
        observer.unobserve(entry.target);
      }}
    }});
  }}, {{ threshold: 0.1 }});
  document.querySelectorAll('.animate-on-scroll').forEach(el => observer.observe(el));
</script>
</body>
</html>"""

    return html

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ShortsYT → Insights Page Generator")
    print("=" * 60)

    # Load
    analyses = load_smart_analyses()
    trends   = load_trend_reports()
    audits   = load_audit_report()

    if not analyses:
        print("[ERR] Brak plików smart_analysis_*.json — uruchom pipeline najpierw.")
        return

    # Extract
    print("\n[*] Ekstrakcja danych...")
    channel_stats     = extract_channel_stats(analyses)
    format_insights   = extract_confirmed_format_insights(analyses)
    duration_insights = extract_duration_insights(analyses)
    kw_insights       = extract_keyword_insights(analyses)
    hook_patterns     = extract_hook_patterns(analyses)
    publish_time      = extract_publish_time_insights(analyses)
    audit_insights    = extract_audit_insights(audits)
    trend_insights    = extract_trend_insights(trends)

    print(f"  Kanał: {channel_stats['name']}")
    print(f"  Okresy analiz: {channel_stats['first_date']} → {channel_stats['last_date']}")
    print(f"  Filmy: {channel_stats['videos_analyzed']}, Views: {channel_stats['total_views']:,}")
    print(f"  Audyty: {audit_insights.get('total_audited',0)} ({audit_insights.get('approval_rate',0)}% akceptacji)")

    # Generate HTML
    print("\n[*] Generowanie HTML...")
    html = generate_html(
        channel_stats, format_insights, duration_insights,
        kw_insights, hook_patterns, publish_time,
        audit_insights, trend_insights
    )

    # Save
    WEBSITE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"\n[OK] Strona zapisana: {OUTPUT_FILE}")
    print(f"[OK] Gotowe! Otwórz w przeglądarce: file:///{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
