"""Data access for leads, history events and the webhook log."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from .db import CLOSED_STATUSES, STATUSES, now_iso

LEAD_COLUMNS = (
    "id, name, phone, email, request, source, status, amount, manager, "
    "created_at, updated_at, closed_at"
)


def _row(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    return dict(row) if row is not None else None


def add_event(
    conn: sqlite3.Connection,
    lead_id: int,
    kind: str,
    text: str = "",
    author: str = "Система",
    from_status: str | None = None,
    to_status: str | None = None,
    at: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO events (lead_id, kind, text, author, from_status, to_status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (lead_id, kind, text, author, from_status, to_status, at or now_iso()),
    )


def create_lead(
    conn: sqlite3.Connection,
    data: dict[str, Any],
    author: str = "Система",
    note: str = "Заявка создана",
) -> dict[str, Any]:
    ts = data.get("created_at") or now_iso()
    cur = conn.execute(
        "INSERT INTO leads (name, phone, email, request, source, status, amount, manager,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'new', ?, ?, ?, ?)",
        (
            data["name"],
            data.get("phone", ""),
            data.get("email", ""),
            data.get("request", ""),
            data["source"],
            data.get("amount", 0),
            data.get("manager"),
            ts,
            ts,
        ),
    )
    lead_id = int(cur.lastrowid)
    add_event(conn, lead_id, "created", note, author, None, "new", ts)
    return get_lead(conn, lead_id)  # type: ignore[return-value]


def get_lead(conn: sqlite3.Connection, lead_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(f"SELECT {LEAD_COLUMNS} FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return _row(row)


def list_leads(
    conn: sqlite3.Connection,
    status: str | None = None,
    source: str | None = None,
    manager: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if manager:
        clauses.append("manager = ?")
        params.append(manager)
    if q:
        clauses.append("(name LIKE ? OR phone LIKE ? OR request LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT {LEAD_COLUMNS} FROM leads {where} ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def lead_history(conn: sqlite3.Connection, lead_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, kind, text, author, from_status, to_status, created_at"
        " FROM events WHERE lead_id = ? ORDER BY created_at, id",
        (lead_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def change_status(
    conn: sqlite3.Connection, lead_id: int, new_status: str, author: str, at: str | None = None
) -> Optional[dict[str, Any]]:
    lead = get_lead(conn, lead_id)
    if lead is None:
        return None
    old = lead["status"]
    if old == new_status:
        return lead
    ts = at or now_iso()
    closed_at = ts if new_status in CLOSED_STATUSES else None
    conn.execute(
        "UPDATE leads SET status = ?, updated_at = ?, closed_at = ? WHERE id = ?",
        (new_status, ts, closed_at, lead_id),
    )
    text = f"{STATUSES[old]} → {STATUSES[new_status]}"
    add_event(conn, lead_id, "status", text, author, old, new_status, ts)
    return get_lead(conn, lead_id)


def patch_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    amount: int | None,
    manager: str | None,
    author: str,
) -> Optional[dict[str, Any]]:
    lead = get_lead(conn, lead_id)
    if lead is None:
        return None
    ts = now_iso()
    if amount is not None and amount != lead["amount"]:
        conn.execute("UPDATE leads SET amount = ?, updated_at = ? WHERE id = ?", (amount, ts, lead_id))
        add_event(conn, lead_id, "amount", f"Сумма: {lead['amount']} → {amount} ₽", author, at=ts)
    if manager is not None and manager != lead["manager"]:
        conn.execute("UPDATE leads SET manager = ?, updated_at = ? WHERE id = ?", (manager, ts, lead_id))
        add_event(conn, lead_id, "manager", f"Ответственный: {manager}", author, at=ts)
    return get_lead(conn, lead_id)


def add_comment(conn: sqlite3.Connection, lead_id: int, text: str, author: str) -> bool:
    if get_lead(conn, lead_id) is None:
        return False
    ts = now_iso()
    add_event(conn, lead_id, "comment", text, author, at=ts)
    conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (ts, lead_id))
    return True


def log_webhook(
    conn: sqlite3.Connection,
    remote_ip: str,
    payload: str,
    http_status: int,
    lead_id: int | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO webhook_log (received_at, remote_ip, payload, http_status, lead_id, error)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), remote_ip, payload[:4000], http_status, lead_id, error),
    )


def webhook_log(conn: sqlite3.Connection, after_id: int = 0, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, received_at, remote_ip, payload, http_status, lead_id, error"
        " FROM webhook_log WHERE id > ? ORDER BY id DESC LIMIT ?",
        (after_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
