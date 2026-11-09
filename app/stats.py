"""Dashboard numbers, all computed from the current DB state."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from .db import MANAGERS, SOURCES, STATUSES


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _source_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = {
        r["source"]: r
        for r in conn.execute(
            "SELECT source, COUNT(*) AS cnt,"
            " SUM(status = 'paid') AS paid, SUM(status = 'lost') AS lost,"
            " COALESCE(SUM(CASE WHEN status = 'paid' THEN amount END), 0) AS revenue"
            " FROM leads GROUP BY source"
        )
    }
    result = []
    for key, label in SOURCES.items():
        r = rows.get(key)
        cnt, paid = (r["cnt"], r["paid"]) if r else (0, 0)
        result.append(
            {
                "source": key,
                "label": label,
                "count": cnt,
                "paid": paid,
                "lost": r["lost"] if r else 0,
                "revenue": r["revenue"] if r else 0,
                "conversion": _ratio(paid, cnt),
            }
        )
    return result


def _manager_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = {
        r["manager"]: r
        for r in conn.execute(
            "SELECT manager, COUNT(*) AS cnt, SUM(status = 'paid') AS paid,"
            " SUM(status IN ('new','in_progress')) AS open,"
            " COALESCE(SUM(CASE WHEN status = 'paid' THEN amount END), 0) AS revenue"
            " FROM leads WHERE manager IS NOT NULL GROUP BY manager"
        )
    }
    return [
        {
            "manager": m,
            "count": rows[m]["cnt"] if m in rows else 0,
            "paid": rows[m]["paid"] if m in rows else 0,
            "open": rows[m]["open"] if m in rows else 0,
            "revenue": rows[m]["revenue"] if m in rows else 0,
        }
        for m in MANAGERS
    ]


def _weekly(conn: sqlite3.Connection, weeks: int, today: date) -> list[dict[str, Any]]:
    first = _week_start(today) - timedelta(weeks=weeks - 1)
    buckets = {first + timedelta(weeks=i): {"revenue": 0, "paid": 0, "leads": 0} for i in range(weeks)}
    since = first.isoformat()
    for r in conn.execute(
        "SELECT closed_at, amount FROM leads WHERE status = 'paid' AND closed_at >= ?", (since,)
    ):
        wk = _week_start(datetime.fromisoformat(r["closed_at"]).date())
        if wk in buckets:
            buckets[wk]["revenue"] += r["amount"]
            buckets[wk]["paid"] += 1
    for r in conn.execute("SELECT created_at FROM leads WHERE created_at >= ?", (since,)):
        wk = _week_start(datetime.fromisoformat(r["created_at"]).date())
        if wk in buckets:
            buckets[wk]["leads"] += 1
    return [{"week_start": wk.isoformat(), **vals} for wk, vals in sorted(buckets.items())]


def compute_stats(conn: sqlite3.Connection, weeks: int = 10, today: date | None = None) -> dict[str, Any]:
    by_status = {k: 0 for k in STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) AS cnt FROM leads GROUP BY status"):
        by_status[r["status"]] = r["cnt"]
    money = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN status='paid' THEN amount END), 0) AS revenue,"
        " COALESCE(SUM(CASE WHEN status IN ('new','in_progress') THEN amount END), 0) AS pipeline"
        " FROM leads"
    ).fetchone()
    total = sum(by_status.values())
    paid, lost = by_status["paid"], by_status["lost"]
    return {
        "totals": {
            "leads": total,
            "open": by_status["new"] + by_status["in_progress"],
            "paid": paid,
            "lost": lost,
            "revenue": money["revenue"],
            "pipeline": money["pipeline"],
            "avg_check": round(money["revenue"] / paid) if paid else 0,
            "conversion": _ratio(paid, total),
            "win_rate": _ratio(paid, paid + lost),
        },
        "by_status": [{"status": k, "label": STATUSES[k], "count": v} for k, v in by_status.items()],
        "by_source": _source_rows(conn),
        "by_manager": _manager_rows(conn),
        "revenue_by_week": _weekly(conn, weeks, today or date.today()),
    }
