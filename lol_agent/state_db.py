"""
Flikcut / Shortsyt — Zunifikowana baza SQLite (WAL) dla stanu kolejki, publikacji,
skarbca Viral Vault oraz wyrenderowanych kompilacji 16:9 (P1.1 + Etap 31).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
LOL_AGENT_DIR = Path(__file__).resolve().parent
ACCOUNTS_DIR = LOL_AGENT_DIR / "accounts"
DEFAULT_DB_PATH = ACCOUNTS_DIR / "flikcut_state.db"

_DB_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_state_db_path(queue_file: Optional[Path] = None) -> Path:
    """Wyznacza ścieżkę bazy SQLite (testy monkeypatchujące QUEUE_FILE pozostają w tmp_path)."""
    if queue_file is not None:
        return Path(queue_file).with_suffix(".db")
    return DEFAULT_DB_PATH


@contextmanager
def _connect(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scheduled_queue (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            platform TEXT NOT NULL,
            publish_at TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_queue_status_plat ON scheduled_queue(status, platform);

        CREATE TABLE IF NOT EXISTS published_videos (
            video_id TEXT PRIMARY KEY,
            video_format TEXT NOT NULL DEFAULT 'short',
            title TEXT,
            source_path TEXT,
            published_at TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pub_format_date ON published_videos(video_format, published_at);

        CREATE TABLE IF NOT EXISTS viral_vault (
            clip_id TEXT PRIMARY KEY,
            state TEXT NOT NULL DEFAULT 'staging',
            yt_video_id TEXT,
            champion TEXT,
            views INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_vault_state_champ ON viral_vault(state, champion);

        CREATE TABLE IF NOT EXISTS compilations (
            comp_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            output_path TEXT,
            thumbnail_path TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )


def init_state_db(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    with _DB_LOCK:
        with _connect(path):
            pass
    return path


def sync_queue_to_db(items: List[Dict[str, Any]], db_path: Optional[Path] = None) -> int:
    """Atomowo zapisuje bieżący stan kolejki `scheduled_social_queue` do tabeli SQLite."""
    now = _now_iso()
    with _DB_LOCK:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM scheduled_queue")
            for idx, item in enumerate(items or []):
                if not isinstance(item, dict):
                    continue
                row_id = str(item.get("id") or f"row_{idx}")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scheduled_queue (id, status, platform, publish_at, payload_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        str(item.get("status") or "pending"),
                        str(item.get("platform") or ""),
                        str(item.get("publish_at") or ""),
                        json.dumps(item, ensure_ascii=False),
                        now,
                    ),
                )
    return len(items or [])


def load_queue_from_db(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        with _connect(db_path) as conn:
            rows = conn.execute("SELECT payload_json FROM scheduled_queue ORDER BY rowid ASC").fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    out.append(json.loads(r["payload_json"]))
                except Exception:
                    continue
            return out


def record_published_video_db(record: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    vid = str(record.get("video_id") or "").strip()
    if not vid:
        return
    with _DB_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO published_videos (video_id, video_format, title, source_path, published_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    vid,
                    str(record.get("video_format") or "short"),
                    str(record.get("title") or ""),
                    str(record.get("source_path") or ""),
                    str(record.get("published_at") or _now_iso()),
                    json.dumps(record, ensure_ascii=False),
                ),
            )


def list_published_videos_db(
    video_format: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        with _connect(db_path) as conn:
            if video_format:
                rows = conn.execute(
                    "SELECT payload_json FROM published_videos WHERE video_format = ? ORDER BY published_at DESC",
                    (video_format,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM published_videos ORDER BY published_at DESC"
                ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    out.append(json.loads(r["payload_json"]))
                except Exception:
                    continue
            return out


def upsert_vault_item_db(item: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    cid = str(item.get("clip_id") or "").strip()
    if not cid:
        return
    with _DB_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO viral_vault (clip_id, state, yt_video_id, champion, views, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    str(item.get("state") or "staging"),
                    str(item.get("yt_video_id") or ""),
                    str(item.get("champion") or ""),
                    int(item.get("views") or 0),
                    json.dumps(item, ensure_ascii=False),
                    _now_iso(),
                ),
            )


def delete_vault_item_db(clip_id: str, db_path: Optional[Path] = None) -> None:
    with _DB_LOCK:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM viral_vault WHERE clip_id = ?", (str(clip_id),))


def list_vault_items_db(
    state: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        with _connect(db_path) as conn:
            if state:
                rows = conn.execute(
                    "SELECT payload_json FROM viral_vault WHERE state = ? ORDER BY views DESC, updated_at DESC",
                    (state,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload_json FROM viral_vault ORDER BY views DESC, updated_at DESC"
                ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    out.append(json.loads(r["payload_json"]))
                except Exception:
                    continue
            return out


def upsert_compilation_db(comp: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    comp_id = str(comp.get("comp_id") or "").strip()
    if not comp_id:
        return
    with _DB_LOCK:
        with _connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO compilations (comp_id, mode, status, output_path, thumbnail_path, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comp_id,
                    str(comp.get("mode") or "weekly"),
                    str(comp.get("status") or "done"),
                    str(comp.get("output_path") or ""),
                    str(comp.get("thumbnail_path") or ""),
                    json.dumps(comp, ensure_ascii=False),
                    str(comp.get("created_at") or _now_iso()),
                ),
            )


def list_compilations_db(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        with _connect(db_path) as conn:
            rows = conn.execute("SELECT payload_json FROM compilations ORDER BY created_at DESC").fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    out.append(json.loads(r["payload_json"]))
                except Exception:
                    continue
            return out


def migrate_legacy_json_to_sqlite(
    accounts_dir: Optional[Path] = None,
    lol_agent_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, int]:
    """Jednorazowo przenosi kolejki JSON oraz published_videos.jsonl do bazy SQLite."""
    acc = Path(accounts_dir) if accounts_dir is not None else ACCOUNTS_DIR
    la = Path(lol_agent_dir) if lol_agent_dir is not None else LOL_AGENT_DIR
    target_db = Path(db_path) if db_path is not None else (acc / "flikcut_state.db")

    init_state_db(target_db)
    queue_migrated = 0
    pub_migrated = 0

    q_file = acc / "scheduled_social_queue.json"
    if q_file.is_file():
        try:
            q_items = json.loads(q_file.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(q_items, list):
                queue_migrated = sync_queue_to_db(q_items, db_path=target_db)
        except Exception:
            pass

    pub_file = la / "published_videos.jsonl"
    if pub_file.is_file():
        for line in pub_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
                if isinstance(rec, dict) and rec.get("video_id"):
                    record_published_video_db(rec, db_path=target_db)
                    pub_migrated += 1
            except Exception:
                continue

    return {
        "db_path": str(target_db),
        "queue_migrated": queue_migrated,
        "published_migrated": pub_migrated,
    }
