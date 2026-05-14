"""
Shortsyt Dashboard - Flask Backend v2
Multi-account YouTube management panel
"""

import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
import json
import pickle
import subprocess
import threading
import time
import queue
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Setup paths
# ---------------------------------------------------------------------------
BASE_DIR       = Path(__file__).parent.parent.resolve()   # shortsyt/
DASHBOARD_DIR  = Path(__file__).parent.resolve()           # shortsyt/dashboard/
ACCOUNTS_DIR   = BASE_DIR / "accounts"
PROFILES_FILE  = DASHBOARD_DIR / "channel_profiles.json"
TOPIC_HISTORY_FILE = ACCOUNTS_DIR / "topic_history.json"

sys.path.insert(0, str(BASE_DIR))

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Live log streams: { stream_key: queue.Queue }
_log_queues: dict[str, queue.Queue] = {}
_running_processes: dict[str, subprocess.Popen] = {}

# ---------------------------------------------------------------------------
# Channel Profiles (channel_profiles.json)
# ---------------------------------------------------------------------------

def load_profiles() -> dict:
    if not PROFILES_FILE.exists():
        return {}
    with open(PROFILES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_profiles(profiles: dict):
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

def get_account(account_id: str) -> dict | None:
    profiles = load_profiles()
    return profiles.get(account_id)

# ---------------------------------------------------------------------------
# Token & stats helpers
# ---------------------------------------------------------------------------

def get_token_status(account_id: str) -> dict:
    token_file = ACCOUNTS_DIR / f"{account_id}_token.pickle"
    if not token_file.exists():
        return {"status": "missing", "label": "Brak tokenu"}
    try:
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.valid:
            return {"status": "ok", "label": "Aktywny"}
        elif creds and creds.expired and creds.refresh_token:
            return {"status": "expired", "label": "Wygas\u0142y (od\u015bwie\u017calny)"}
        else:
            return {"status": "expired", "label": "Wygas\u0142y"}
    except Exception as e:
        return {"status": "error", "label": f"B\u0142\u0105d: {str(e)[:40]}"}

def get_video_history(account_id: str) -> list[dict]:
    if not TOPIC_HISTORY_FILE.exists():
        return []
    try:
        with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get(account_id, [])
        return list(reversed(entries[-20:]))
    except Exception:
        return []

# ---------------------------------------------------------------------------
# API — Main
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/accounts", methods=["GET"])
def api_accounts():
    profiles = load_profiles()
    result = []
    for acc_id, acc in profiles.items():
        token   = get_token_status(acc_id)
        history = get_video_history(acc_id)
        result.append({
            **acc,
            "token":           token,
            "video_count":     len(history),
            "last_video":      history[0]["title"] if history else None,
            "last_video_date": history[0]["timestamp"][:10] if history else None,
            "is_running":      acc_id in _running_processes and _running_processes[acc_id].poll() is None,
        })
    return jsonify(result)


@app.route("/api/accounts", methods=["POST"])
def api_add_account():
    data = request.json
    acc_id       = data.get("id", "").strip().lower().replace(" ", "_")
    display_name = data.get("display_name", "").strip()
    niche        = data.get("niche", "").strip()
    client_name  = data.get("client_name", "").strip()
    genre        = data.get("genre", "general").strip()
    language     = data.get("language", "pl").strip()
    persona      = data.get("persona", "").strip()
    tone         = data.get("tone", "").strip()

    if not acc_id or not display_name or not niche:
        return jsonify({"error": "Wype\u0142nij wszystkie pola."}), 400

    profiles = load_profiles()
    if acc_id in profiles:
        return jsonify({"error": f"Konto '{acc_id}' ju\u017c istnieje."}), 409

    # Build default profile based on genre
    voice = "pl-PL-ZofiaNeural" if language == "pl" else "en-US-JennyNeural"
    if language == "en" and genre != "gaming_entertainment":
        voice = "en-US-ChristopherNeural"
    if language == "pl":
        voice = "pl-PL-MarekNeural"

    # Genre-specific defaults
    GENRE_DEFAULTS = {
        "product_review": {
            "hook_style": "Problem-solution hook",
            "subtitle_style": "Clean",
            "music_style": "soft background no copyright",
            "background_style": "clean white studio product shots",
            "persona_default": f"Honest product reviewer who saves people money on {niche}",
            "tone_default": "Friendly, direct, honest. Never pushy or salesy.",
            "forbidden_topics": ["fake reviews", "paid promotion without disclosure", "clickbait"],
            "title_format_rules": "Problem or question format — 'Is X worth it?', 'X vs Y', 'Don't buy X until...'",
            "description_template": "Honest review: {topic}. Saving you money! #shorts #{acc_id} #review",
            "content_principles": [
                "Always give honest verdict",
                "Compare alternatives when relevant",
                "Mention price-to-value ratio",
                "Never recommend products you haven't verified",
            ],
        },
        "psychology_education": {
            "hook_style": "Curiosity gap + shock fact",
            "subtitle_style": "CinematicDark",
            "music_style": "dark synthwave phonk slowed reverb no copyright",
            "background_style": "dark rainy city night dark red navy colors",
            "persona_default": f"Dark psychology and mindset expert on {niche}",
            "tone_default": "Cold, analytical, authoritative.",
            "forbidden_topics": ["illegal advice", "harmful manipulation against vulnerable people"],
            "title_format_rules": "Question or numbered list format",
            "description_template": "WARNING: {topic}. #darkpsychology #shorts",
            "content_principles": [],
        },
        "gaming_entertainment": {
            "hook_style": "Pattern interrupt + absurd scenario",
            "subtitle_style": "PopWordBrainrot",
            "music_style": "phonk no copyright",
            "background_style": "Minecraft parkour colorful gameplay",
            "persona_default": "Gen-Z internet culture expert",
            "tone_default": "Energetic, chaotic, fun.",
            "forbidden_topics": ["violence", "dark themes"],
            "title_format_rules": "Funny questions or absurd statements",
            "description_template": "Funny {genre} video! #shorts #viral",
            "content_principles": [],
        },
    }
    gd = GENRE_DEFAULTS.get(genre, {})

    profiles[acc_id] = {
        "id":           acc_id,
        "display_name": display_name,
        "niche":        niche,
        "client_name":  client_name,
        "added":        datetime.now().strftime("%Y-%m-%d"),
        "channel_profile": {
            "language":         language,
            "voice":            voice,
            "genre":            genre,
            "persona":          persona or gd.get("persona_default", f"Content creator for {niche}"),
            "tone":             tone or gd.get("tone_default", "Engaging, authentic, value-driven."),
            "hook_style":       gd.get("hook_style", "Pattern interrupt"),
            "subtitle_style":   gd.get("subtitle_style", "CinematicDark" if language == "en" else "PopWordBrainrot"),
            "music_style":      gd.get("music_style", "background music no copyright"),
            "background_style": gd.get("background_style", f"{niche} relevant visuals"),
            "universal_values": {
                "hook_must_stop_scroll_in_seconds": 0.5,
                "avoid_repeat_topics": True,
                "max_words_in_script": 60,
                "use_loop_ending": genre == "gaming_entertainment",
                "engagement_cta_at_end": True,
            },
            "genre_values": {
                "target_audience_age": data.get("target_age", "18-35"),
                "forbidden_topics":    gd.get("forbidden_topics", []),
                "required_keywords_pool": [w.strip() for w in niche.split()[:5]],
                "content_safe_for_kids": genre == "gaming_entertainment" and language == "pl",
                "title_format_rules":  gd.get("title_format_rules", "Question or numbered list"),
                "description_template": gd.get("description_template", f"Engaging content about {niche}. #shorts #{acc_id}"),
                **({"content_principles": gd["content_principles"]} if gd.get("content_principles") else {}),
            },
            "seo_tags": niche.split()[:6] + ["shorts", "viral"],
        }
    }
    save_profiles(profiles)
    return jsonify({"success": True, "id": acc_id})


@app.route("/api/accounts/<account_id>", methods=["DELETE"])
def api_delete_account(account_id: str):
    profiles = load_profiles()
    profiles.pop(account_id, None)
    save_profiles(profiles)
    return jsonify({"success": True})


@app.route("/api/accounts/<account_id>", methods=["GET"])
def api_account_detail(account_id: str):
    acc = get_account(account_id)
    if not acc:
        return jsonify({"error": "Nie znaleziono"}), 404
    history = get_video_history(account_id)
    return jsonify({**acc, "token": get_token_status(account_id), "history": history[:20]})


@app.route("/api/accounts/<account_id>/profile", methods=["PUT"])
def api_update_profile(account_id: str):
    profiles = load_profiles()
    if account_id not in profiles:
        return jsonify({"error": "Nie znaleziono konta"}), 404
    data = request.json
    # Merge channel_profile fields
    if "channel_profile" in data:
        cp = profiles[account_id].setdefault("channel_profile", {})
        for key, val in data["channel_profile"].items():
            if isinstance(val, dict) and isinstance(cp.get(key), dict):
                cp[key].update(val)
            else:
                cp[key] = val
    # Top-level fields
    for field in ["display_name", "niche", "client_name"]:
        if field in data:
            profiles[account_id][field] = data[field]
    save_profiles(profiles)
    return jsonify({"success": True})


@app.route("/api/accounts/<account_id>/history", methods=["GET"])
def api_history(account_id: str):
    return jsonify(get_video_history(account_id))


# ---------------------------------------------------------------------------
# Pipeline Management
# ---------------------------------------------------------------------------

PIPELINE_STEPS = [
    {"id": "trend_scout",      "name": "Skan Trendów YT",        "script": "trend_scout.py",           "icon": "📡"},
    {"id": "smart_analyzer",   "name": "Analiza Kanału (Deep)",   "script": "smart_video_analyzer.py",  "icon": "🔬"},
    {"id": "latest_shorts",    "name": "Analiza Najlepszych",     "script": "latest_shorts_analyzer.py","icon": "🏆"},
    {"id": "one_click",        "name": "Generuj + Publikuj",      "script": "one_click_cashcow.py",     "icon": "🚀"},
    {"id": "verify_pipeline",  "name": "Weryfikuj Pipeline",      "script": "verify_pipeline.py",       "icon": "🔍"},
    {"id": "quality_audit",    "name": "Quality Auditor",         "script": "quality_auditor.py",       "icon": "🎯"},
    {"id": "analyze_peak",     "name": "Analiza Peak Hours",      "script": "analyze_peak_hours.py",    "icon": "⏰"},
    {"id": "refresh_facts",    "name": "Odśwież Fakty AI",        "script": "refresh_facts.py",         "icon": "🧠"},
    {"id": "verify_channels",  "name": "Weryfikuj Tokeny",        "script": "verify_channels.py",       "icon": "🔐"},
    {"id": "run_all",              "name": "Uruchom Wszystkie",         "script": "run_all_channels.py",            "icon": "⚡"},
    {"id": "pw_analyze",           "name": "PrettyWoman: Analiza TikTok", "script": "prettywoman_tiktok_analyzer.py", "icon": "💇"},
    {"id": "pw_download",          "name": "PrettyWoman: Pobierz filmy",  "script": "prettywoman_agent.py",          "icon": "⬇️"},
    {"id": "pw_full",              "name": "PrettyWoman: Pełny Pipeline", "script": "prettywoman_agent.py",          "icon": "🌸"},
]


@app.route("/api/pipeline/steps", methods=["GET"])
def api_pipeline_steps():
    steps = []
    for s in PIPELINE_STEPS:
        script_path = BASE_DIR / s["script"]
        steps.append({
            **s,
            "exists":     script_path.exists(),
            "is_running": s["id"] in _running_processes and _running_processes[s["id"]].poll() is None,
        })
    return jsonify(steps)


@app.route("/api/pipeline/run/<step_id>", methods=["POST"])
def api_pipeline_run(step_id: str):
    step = next((s for s in PIPELINE_STEPS if s["id"] == step_id), None)
    if not step:
        return jsonify({"error": "Nieznany krok pipeline"}), 404

    if step_id in _running_processes:
        proc = _running_processes[step_id]
        if proc and proc.poll() is None:
            return jsonify({"error": "Ten krok juz dziala"}), 409

    # Build args
    data = request.json or {}
    account_id = data.get("account_id", "")
    acc = get_account(account_id) if account_id else None

    python  = str(BASE_DIR / "venv313" / "Scripts" / "python.exe")
    cmd     = [python, str(BASE_DIR / step["script"])]

    # Inject account-specific args
    if step_id == "one_click" and acc:
        cmd += ["--konto", account_id, "--nisza", acc.get("niche", "")]
    elif step_id in ["trend_scout"] and account_id:
        # trend_scout uses env/config — pass account via env
        pass

    stream_key = f"pipeline_{step_id}_{int(time.time())}"
    q = queue.Queue()
    _log_queues[stream_key] = q

    def run():
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        if acc and "channel_profile" in acc:
            cp = acc["channel_profile"]
            env["CHANNEL_GENRE"]    = cp.get("genre", "")
            env["CHANNEL_PERSONA"]  = cp.get("persona", "")
            env["CHANNEL_TONE"]     = cp.get("tone", "")
            env["CHANNEL_LANGUAGE"] = cp.get("language", "")
            env["CHANNEL_VOICE"]    = cp.get("voice", "")
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(BASE_DIR)
            )
            _running_processes[step_id] = proc
            for line in iter(proc.stdout.readline, ""):
                q.put(line.rstrip())
            proc.wait()
            q.put(f"__EXIT__{proc.returncode}")
            _running_processes.pop(step_id, None)
        except Exception as e:
            q.put(f"BLAD: {e}")
            q.put("__EXIT__1")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "stream_key": stream_key})


@app.route("/api/pipeline/stop/<step_id>", methods=["POST"])
def api_pipeline_stop(step_id: str):
    proc = _running_processes.get(step_id)
    if proc and proc.poll() is None:
        proc.terminate()
        _running_processes.pop(step_id, None)
        return jsonify({"success": True})
    return jsonify({"error": "Brak aktywnego procesu"}), 404


# ---------------------------------------------------------------------------
# Content Scanner
# ---------------------------------------------------------------------------

@app.route("/api/scan/<account_id>", methods=["POST"])
def api_scan_content(account_id: str):
    acc = get_account(account_id)
    if not acc:
        return jsonify({"error": "Nie znaleziono konta"}), 404

    stream_key = f"scan_{account_id}_{int(time.time())}"
    q = queue.Queue()
    _log_queues[stream_key] = q

    niche = acc.get("niche", "")
    cp    = acc.get("channel_profile", {})
    genre_values = cp.get("genre_values", {})
    keywords = genre_values.get("required_keywords_pool", [])

    def run():
        python = str(BASE_DIR / "venv313" / "Scripts" / "python.exe")
        env    = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
                  "SCAN_NICHE": niche,
                  "SCAN_KEYWORDS": "|".join(keywords)}
        cmd = [python, str(BASE_DIR / "trend_scout.py")]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(BASE_DIR)
            )
            _running_processes[f"scan_{account_id}"] = proc
            for line in iter(proc.stdout.readline, ""):
                q.put(line.rstrip())
            proc.wait()
            q.put(f"__EXIT__{proc.returncode}")
            _running_processes.pop(f"scan_{account_id}", None)
        except Exception as e:
            q.put(f"BLAD: {e}")
            q.put("__EXIT__1")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "stream_key": stream_key})


# ---------------------------------------------------------------------------
# OAuth Authorization
# ---------------------------------------------------------------------------

@app.route("/api/authorize/<account_id>", methods=["POST"])
def api_authorize(account_id: str):
    q = queue.Queue()
    stream_key = f"auth_{account_id}"
    _log_queues[stream_key] = q

    def run():
        python = str(BASE_DIR / "venv313" / "Scripts" / "python.exe")
        cmd    = [python, str(BASE_DIR / "authorize_channel.py"), "--konto", account_id]
        env    = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(BASE_DIR)
            )
            for line in iter(proc.stdout.readline, ""):
                q.put(line.rstrip())
            proc.wait()
            q.put(f"__EXIT__{proc.returncode}")
        except Exception as e:
            q.put(f"BLAD: {e}")
            q.put("__EXIT__1")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "stream_key": stream_key})


# ---------------------------------------------------------------------------
# Token Status + Smart Analyzer
# ---------------------------------------------------------------------------

@app.route("/api/accounts/<account_id>/token_status", methods=["GET"])
def api_token_status(account_id: str):
    """Sprawdza stan tokenu OAuth dla danego konta."""
    token_file = BASE_DIR / "accounts" / f"{account_id}_token.pickle"
    if not token_file.exists():
        return jsonify({"status": "missing", "label": "Brak tokenu", "color": "red"})
    try:
        import pickle
        with open(token_file, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.valid:
            return jsonify({"status": "valid", "label": "✅ Autoryzowany", "color": "green"})
        elif creds and creds.expired and creds.refresh_token:
            return jsonify({"status": "expired", "label": "⚠️ Wygasły (auto-odnawialny)", "color": "orange"})
        else:
            return jsonify({"status": "invalid", "label": "❌ Nieważny — wymagana re-autoryzacja", "color": "red"})
    except Exception as e:
        return jsonify({"status": "error", "label": f"Błąd: {str(e)[:60]}", "color": "red"})


@app.route("/api/analyze/<account_id>", methods=["POST"])
def api_run_analyzer(account_id: str):
    """Uruchamia smart_video_analyzer.py dla wskazanego konta — pełna analiza kanału YT."""
    acc = get_account(account_id)
    if not acc:
        return jsonify({"error": "Nie znaleziono konta"}), 404
    stream_key = f"analyze_{account_id}"
    q = queue.Queue()
    _log_queues[stream_key] = q

    def run():
        python = str(BASE_DIR / "venv313" / "Scripts" / "python.exe")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
               "PROFILE_NAME": account_id}
        cmd = [python, str(BASE_DIR / "smart_video_analyzer.py")]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(BASE_DIR)
            )
            _running_processes[f"analyze_{account_id}"] = proc
            for line in iter(proc.stdout.readline, ""):
                q.put(line.rstrip())
            proc.wait()
            q.put(f"__EXIT__{proc.returncode}")
            _running_processes.pop(f"analyze_{account_id}", None)
        except Exception as e:
            q.put(f"BŁĄD: {e}")
            q.put("__EXIT__1")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "stream_key": stream_key})


# ---------------------------------------------------------------------------
# Run automation for specific account
# ---------------------------------------------------------------------------

@app.route("/api/run/<account_id>", methods=["POST"])
def api_run(account_id: str):
    if account_id in _running_processes:
        proc = _running_processes[account_id]
        if proc and proc.poll() is None:
            return jsonify({"error": "Automat juz dziala dla tego konta."}), 409

    acc = get_account(account_id)
    if not acc:
        return jsonify({"error": "Nie znaleziono konta."}), 404

    niche      = acc.get("niche", "")
    cp         = acc.get("channel_profile", {})
    stream_key = f"run_{account_id}"
    q          = queue.Queue()
    _log_queues[stream_key] = q

    def run():
        python = str(BASE_DIR / "venv313" / "Scripts" / "python.exe")
        cmd    = [python, str(BASE_DIR / "one_click_cashcow.py"),
                  "--konto", account_id, "--nisza", niche]
        env = {
            **os.environ,
            "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
            # Inject channel profile into environment so synapsa_bridge can use it
            "CHANNEL_GENRE":    cp.get("genre", "general"),
            "CHANNEL_PERSONA":  cp.get("persona", "Content creator"),
            "CHANNEL_TONE":     cp.get("tone", "Engaging and authentic"),
            "CHANNEL_LANGUAGE": cp.get("language", "pl"),
            "CHANNEL_VOICE":    cp.get("voice", "pl-PL-MarekNeural"),
            "CHANNEL_HOOK_STYLE": cp.get("hook_style", "Pattern interrupt"),
            "CHANNEL_BG_STYLE": cp.get("background_style", ""),
            "CHANNEL_MUSIC":    cp.get("music_style", ""),
        }
        # Universal values as env
        uv = cp.get("universal_values", {})
        env["CHANNEL_MAX_WORDS"]    = str(uv.get("max_words_in_script", 60))
        env["CHANNEL_USE_LOOP"]     = "1" if uv.get("use_loop_ending") else "0"
        # Genre-specific values
        gv = cp.get("genre_values", {})
        env["CHANNEL_KEYWORDS"]     = "|".join(gv.get("required_keywords_pool", []))
        env["CHANNEL_TITLE_RULES"]  = gv.get("title_format_rules", "")
        env["CHANNEL_DESC_TEMPLATE"]= gv.get("description_template", "")
        env["CHANNEL_FORBIDDEN"]    = "|".join(gv.get("forbidden_topics", []))
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=env, cwd=str(BASE_DIR)
            )
            _running_processes[account_id] = proc
            for line in iter(proc.stdout.readline, ""):
                q.put(line.rstrip())
            proc.wait()
            q.put(f"__EXIT__{proc.returncode}")
            _running_processes.pop(account_id, None)
        except Exception as e:
            q.put(f"BLAD: {e}")
            q.put("__EXIT__1")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "stream_key": stream_key})


@app.route("/api/stop/<account_id>", methods=["POST"])
def api_stop(account_id: str):
    proc = _running_processes.get(account_id)
    if proc and proc.poll() is None:
        proc.terminate()
        _running_processes.pop(account_id, None)
        return jsonify({"success": True})
    return jsonify({"error": "Brak aktywnego procesu."}), 404


# ---------------------------------------------------------------------------
# SSE Stream
# ---------------------------------------------------------------------------

@app.route("/api/stream/<stream_key>")
def api_stream(stream_key: str):
    def generate():
        q = _log_queues.get(stream_key)
        if not q:
            yield f"data: [Brak strumienia: {stream_key}]\n\n"
            return
        timeout_count = 0
        while True:
            try:
                line = q.get(timeout=1)
                if line.startswith("__EXIT__"):
                    code = line.replace("__EXIT__", "")
                    yield f"data: [ZAKONCZONE kod: {code}]\n\n"
                    yield "data: __DONE__\n\n"
                    _log_queues.pop(stream_key, None)
                    break
                safe = line.replace("\n", " ")
                yield f"data: {safe}\n\n"
            except queue.Empty:
                timeout_count += 1
                yield ": heartbeat\n\n"
                if timeout_count > 360:
                    yield "data: [Timeout 6 min]\n\n"
                    yield "data: __DONE__\n\n"
                    break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def api_stats():
    profiles     = load_profiles()
    total_videos = 0
    active_tokens= 0
    if TOPIC_HISTORY_FILE.exists():
        try:
            with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
            for acc_id in profiles:
                total_videos += len(history.get(acc_id, []))
        except Exception:
            pass
    for acc_id in profiles:
        if get_token_status(acc_id)["status"] == "ok":
            active_tokens += 1
    return jsonify({
        "total_accounts": len(profiles),
        "active_tokens":  active_tokens,
        "total_videos":   total_videos,
        "running":        len([p for p in _running_processes.values() if p.poll() is None]),
    })


# ---------------------------------------------------------------------------
# Trend scan results (reads latest trend_report json)
# ---------------------------------------------------------------------------

@app.route("/api/trends/<account_id>", methods=["GET"])
def api_trends(account_id: str):
    import glob as _glob
    reports = sorted(_glob.glob(str(BASE_DIR / "trend_report_*.json")), reverse=True)
    if not reports:
        return jsonify({"error": "Brak raportow trendow. Uruchom Skan Trendow."}), 404
    try:
        with open(reports[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Platform Connections (Bank Referencji)
# ---------------------------------------------------------------------------

PLATFORM_REFS_FILE = DASHBOARD_DIR / "platform_refs.json"

def load_refs() -> list:
    if not PLATFORM_REFS_FILE.exists():
        return []
    try:
        with open(PLATFORM_REFS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_refs(refs: list):
    with open(PLATFORM_REFS_FILE, "w", encoding="utf-8") as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)


@app.route("/api/connections", methods=["GET"])
def api_get_connections():
    return jsonify(load_refs())


@app.route("/api/connections", methods=["POST"])
def api_add_connection():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Brak URL"}), 400
    refs = load_refs()
    refs.append({
        "url":        url,
        "platform":   data.get("platform", "youtube"),
        "account_id": data.get("account_id", ""),
        "added":      datetime.now().strftime("%Y-%m-%d"),
    })
    save_refs(refs)
    return jsonify({"success": True})


@app.route("/api/connections/<int:index>", methods=["DELETE"])
def api_delete_connection(index: int):
    refs = load_refs()
    if 0 <= index < len(refs):
        refs.pop(index)
        save_refs(refs)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  [SHORTSYT] Dashboard v2 - uruchamiam...")
    print(f"  Projekt: {BASE_DIR}")
    print("  Adres:   http://localhost:5000")
    print("=" * 60)
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
