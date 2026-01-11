from __future__ import annotations

import sqlite3
from datetime import datetime
from urllib.parse import quote_plus

from .db_queries import (
    fetch_books_per_author,
    fetch_books_per_tag,
    fetch_dashboard_totals,
    fetch_recent_activity,
)


def urlencode_value(value: object) -> str:
    """URL-encode template values in app/main.py template filters."""
    if value is None:
        return ""
    return quote_plus(str(value))


def format_bytes(size_bytes: int) -> str:
    """Format file sizes for UI display in app/main.py and app/routes/ui.py."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


def format_activity_rows(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    """Format activity for UI display in app/main.py."""
    return [
        {
            "event_type": entry["event_type"],
            "result": entry["result"],
            "created_at": datetime.fromtimestamp(entry["created_at"]).isoformat(),
        }
        for entry in rows
    ]


def format_bar_chart(rows: list[sqlite3.Row]) -> dict[str, object]:
    """Format chart rows with percentages for the dashboard."""
    max_count = max((int(row["book_count"]) for row in rows), default=0)
    items: list[dict[str, object]] = []
    for row in rows:
        name = str(row["name"]) if row["name"] is not None else "Unknown"
        count = int(row["book_count"])
        percent = 0 if max_count == 0 else int(round((count / max_count) * 100))
        items.append({"name": name, "count": count, "percent": percent})
    return {"items": items, "max": max_count}


def split_tags(raw: str) -> list[str]:
    """Normalize and de-duplicate tag input for UI forms in app/routes/ui.py."""
    parts = [part.strip() for part in raw.replace("\n", ",").split(",")]
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in parts:
        normalized = " ".join(part.split())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    return cleaned


def normalize_search(raw: str | None) -> str | None:
    """Normalize search terms for filtering in app/routes/ui.py."""
    if not raw:
        return None
    cleaned = " ".join(raw.split())
    return cleaned or None


def get_dashboard_data(
    get_connection,
) -> tuple[sqlite3.Row, list[dict[str, object]], dict[str, object]]:
    """Load dashboard totals and activity for app/routes/ui.py via app/main.py."""
    with get_connection() as conn:
        totals = fetch_dashboard_totals(conn)
        activity = fetch_recent_activity(conn, limit=8)
        author_rows = fetch_books_per_author(conn, limit=10)
        tag_rows = fetch_books_per_tag(conn, limit=10)
    formatted_activity = format_activity_rows(activity)
    charts = {
        "authors": format_bar_chart(author_rows),
        "tags": format_bar_chart(tag_rows),
    }
    return totals, formatted_activity, charts
