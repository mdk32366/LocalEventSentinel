"""
database.py — SQLite database layer for PNW Event Monitor
"""

import sqlite3
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "events.db"


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                hash        TEXT UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                date_raw    TEXT,
                date_parsed TEXT,
                time_raw    TEXT,
                location    TEXT,
                description TEXT,
                url         TEXT,
                category    TEXT,
                source_name TEXT,
                found_at    TEXT NOT NULL,
                emailed     INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TEXT NOT NULL,
                finished_at TEXT,
                sources_ok  INTEGER DEFAULT 0,
                sources_err INTEGER DEFAULT 0,
                events_found INTEGER DEFAULT 0,
                events_new  INTEGER DEFAULT 0,
                notes       TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_date ON events(date_parsed);
            CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
            CREATE INDEX IF NOT EXISTS idx_events_emailed ON events(emailed);
            CREATE INDEX IF NOT EXISTS idx_events_found ON events(found_at);
        """)
    return True


def make_hash(title: str, date_raw: str, location: str) -> str:
    key = f"{title.lower().strip()}|{(date_raw or '').lower().strip()}|{(location or '').lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def upsert_event(event: dict) -> bool:
    """Insert event if not duplicate. Returns True if new."""
    h = make_hash(event.get("title", ""), event.get("date_raw", ""), event.get("location", ""))
    try:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO events
                    (hash, title, date_raw, date_parsed, time_raw, location,
                     description, url, category, source_name, found_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                h,
                event.get("title", "Unknown event"),
                event.get("date_raw"),
                event.get("date_parsed"),
                event.get("time_raw"),
                event.get("location"),
                event.get("description"),
                event.get("url"),
                event.get("category"),
                event.get("source_name"),
                datetime.utcnow().isoformat(),
            ))
        return True
    except sqlite3.IntegrityError:
        return False  # Duplicate


def query_events(
    category: str = None,
    days_ahead: int = 14,
    since_days: int = None,
    emailed: bool = None,
    limit: int = 200,
) -> list:
    conditions = []
    params = []

    if days_ahead is not None:
        future = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        conditions.append("(date_parsed IS NULL OR (date_parsed >= ? AND date_parsed <= ?))")
        params += [today, future]

    if since_days is not None:
        cutoff = (datetime.utcnow() - timedelta(days=since_days)).isoformat()
        conditions.append("found_at >= ?")
        params.append(cutoff)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if emailed is not None:
        conditions.append("emailed = ?")
        params.append(1 if emailed else 0)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT * FROM events
        {where}
        ORDER BY date_parsed ASC NULLS LAST, found_at DESC
        LIMIT ?
    """
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def mark_emailed(event_ids: list):
    with get_connection() as conn:
        conn.execute(
            f"UPDATE events SET emailed=1 WHERE id IN ({','.join('?'*len(event_ids))})",
            event_ids,
        )


def purge_old(retention_days: int = 90):
    cutoff = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM events WHERE found_at < ?", (cutoff,))


def log_scan(started_at, finished_at, sources_ok, sources_err, events_found, events_new, notes=""):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO scan_log (started_at, finished_at, sources_ok, sources_err,
                                  events_found, events_new, notes)
            VALUES (?,?,?,?,?,?,?)
        """, (started_at, finished_at, sources_ok, sources_err, events_found, events_new, notes))


def get_scan_history(limit: int = 20) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scan_log ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
