"""SQLite storage shared by lapd and the web app.

One file, WAL mode, short transactions. lapd is the main writer (a few rows a
second at most); the web app reads, plus writes the admin row and settings.
Schema changes go in MIGRATIONS and are applied in order by `migrate`, tracked
with PRAGMA user_version.
"""

from __future__ import annotations

import os
import sqlite3
import time

MIGRATIONS: tuple[str, ...] = (
    # 1: first-run admin, settings, raw passings, decoder health
    """
    CREATE TABLE admin (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        username TEXT NOT NULL,
        pw_hash TEXT NOT NULL,
        created_at INTEGER NOT NULL
    );
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE passing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        heat_id INTEGER,
        transponder INTEGER NOT NULL,
        kind TEXT NOT NULL,
        decoder_ts_ms INTEGER NOT NULL,
        received_at_ms INTEGER NOT NULL,
        rssi REAL NOT NULL,
        hits INTEGER
    );
    CREATE INDEX passing_received ON passing (received_at_ms);
    CREATE TABLE decoder_status (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        updated_at_ms INTEGER NOT NULL,
        noise REAL,
        received INTEGER,
        processed INTEGER,
        learn_event TEXT,
        learn_transponder INTEGER,
        learn_at_ms INTEGER
    );
    """,
)


def now_ms() -> int:
    return int(time.time() * 1000)


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations; returns the schema version afterwards."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            # executescript would COMMIT our transaction, so split by statement.
            for statement in (s.strip() for s in sql.split(";")):
                if statement:
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return conn.execute("PRAGMA user_version").fetchone()[0]


def open_db(path: str) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn)
    return conn


# --- admin -------------------------------------------------------------------

def admin_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM admin WHERE id = 1").fetchone() is not None


def create_admin(conn: sqlite3.Connection, username: str, pw_hash: str) -> bool:
    """Insert the one admin. False if one already exists (setup is first-run only)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO admin (id, username, pw_hash, created_at) VALUES (1, ?, ?, ?)",
        (username, pw_hash, now_ms()),
    )
    return cur.rowcount == 1


def get_admin(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT username, pw_hash FROM admin WHERE id = 1").fetchone()


def set_admin_hash(conn: sqlite3.Connection, pw_hash: str) -> None:
    conn.execute("UPDATE admin SET pw_hash = ? WHERE id = 1", (pw_hash,))


# --- settings ----------------------------------------------------------------

def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def setdefault_setting(conn: sqlite3.Connection, key: str, value: str) -> str:
    """Store value only if key is unset; return whichever value is stored."""
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    return get_setting(conn, key)  # type: ignore[return-value]


# --- decoder feed ------------------------------------------------------------

def insert_passing(conn: sqlite3.Connection, *, transponder: int, kind: str,
                   decoder_ts_ms: int, rssi: float, hits: int | None,
                   received_at_ms: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO passing (transponder, kind, decoder_ts_ms, received_at_ms, rssi, hits)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (transponder, kind, decoder_ts_ms, received_at_ms or now_ms(), rssi, hits),
    )
    return int(cur.lastrowid)


def update_stats(conn: sqlite3.Connection, *, noise: float, received: int, processed: int,
                 at_ms: int | None = None) -> None:
    conn.execute(
        "INSERT INTO decoder_status (id, updated_at_ms, noise, received, processed)"
        " VALUES (1, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET updated_at_ms = excluded.updated_at_ms,"
        " noise = excluded.noise, received = excluded.received, processed = excluded.processed",
        (at_ms or now_ms(), noise, received, processed),
    )


def update_learn(conn: sqlite3.Connection, *, event: str, transponder: int | None,
                 at_ms: int | None = None) -> None:
    at = at_ms or now_ms()
    conn.execute(
        "INSERT INTO decoder_status (id, updated_at_ms, learn_event, learn_transponder, learn_at_ms)"
        " VALUES (1, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET updated_at_ms = excluded.updated_at_ms,"
        " learn_event = excluded.learn_event, learn_transponder = excluded.learn_transponder,"
        " learn_at_ms = excluded.learn_at_ms",
        (at, event, transponder, at),
    )


def recent_passings(conn: sqlite3.Connection, *, after_id: int = 0, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT id, transponder, kind, rssi, hits, received_at_ms FROM passing"
        " WHERE id > ? ORDER BY id DESC LIMIT ?",
        (after_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def decoder_status(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute("SELECT * FROM decoder_status WHERE id = 1").fetchone()
    return None if row is None else {k: row[k] for k in row.keys() if k != "id"}
