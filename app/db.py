"""SQLite storage: schema, connection helper, reference data."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE_DIR / "data" / "crm.sqlite3"

STATUSES: dict[str, str] = {
    "new": "Новая",
    "in_progress": "В работе",
    "paid": "Оплачено",
    "lost": "Отказ",
}
SOURCES: dict[str, str] = {
    "site": "Сайт",
    "telegram": "Telegram-бот",
    "avito": "Авито",
}
MANAGERS: tuple[str, ...] = ("Ольга Кравец", "Дмитрий Савин", "Марина Лаптева")
CLOSED_STATUSES = frozenset({"paid", "lost"})

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    phone       TEXT    NOT NULL DEFAULT '',
    email       TEXT    NOT NULL DEFAULT '',
    request     TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL CHECK (source IN ('site','telegram','avito')),
    status      TEXT    NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new','in_progress','paid','lost')),
    amount      INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    manager     TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    closed_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS ix_leads_source ON leads(source);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    kind        TEXT    NOT NULL,   -- created | status | comment | amount | manager
    text        TEXT    NOT NULL DEFAULT '',
    author      TEXT    NOT NULL DEFAULT 'Система',
    from_status TEXT,
    to_status   TEXT,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_lead ON events(lead_id, id);

CREATE TABLE IF NOT EXISTS webhook_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT    NOT NULL,
    remote_ip   TEXT    NOT NULL DEFAULT '',
    payload     TEXT    NOT NULL,
    http_status INTEGER NOT NULL,
    lead_id     INTEGER,
    error       TEXT
);
"""


def db_path() -> Path:
    return Path(os.environ.get("CRM_DB", DEFAULT_DB))


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    """One connection per request; commit on success, rollback on error."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
