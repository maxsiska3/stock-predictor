# utils/db.py — SQLite database connection and schema
#
# Single file database (kouros.db) on disk. Set DATABASE_PATH env var on Render
# to point at a persistent volume (e.g. /data/kouros.db).

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DATA_DIR / "kouros.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    symbol   TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(user_id, symbol),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    symbol       TEXT NOT NULL,
    shares       REAL NOT NULL,
    avg_cost     REAL NOT NULL,
    purchased_at TEXT,
    updated_at   TEXT NOT NULL,
    UNIQUE(user_id, symbol),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_funds (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fund_holdings (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id INTEGER NOT NULL,
    symbol  TEXT NOT NULL,
    UNIQUE(fund_id, symbol),
    FOREIGN KEY (fund_id) REFERENCES user_funds(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user  ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_positions_user  ON positions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_funds_user ON user_funds(user_id);
CREATE INDEX IF NOT EXISTS idx_fund_holdings   ON fund_holdings(fund_id);
"""


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _migrate_fund_holdings_positions(conn):
    """Add shares/avg_cost to fund_holdings for existing databases."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(fund_holdings)").fetchall()}
    if "shares" not in cols:
        conn.execute("ALTER TABLE fund_holdings ADD COLUMN shares REAL")
    if "avg_cost" not in cols:
        conn.execute("ALTER TABLE fund_holdings ADD COLUMN avg_cost REAL")


def init_db():
    """Create data directory and tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrate_fund_holdings_positions(conn)
        conn.commit()


@contextmanager
def get_connection():
    """Yield a SQLite connection with row dict access and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def get_all_watchlist_symbols():
    """Union of every symbol saved by any user — used to warm the market cache."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM watchlist ORDER BY symbol").fetchall()
    return [row["symbol"] for row in rows]


def get_all_fund_symbols():
    """Union of every symbol in any user's fund — used to warm the market cache."""
    with get_connection() as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM fund_holdings ORDER BY symbol").fetchall()
    return [row["symbol"] for row in rows]
