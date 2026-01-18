from __future__ import annotations

import json
import sqlite3
import time


def get_book_tags(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
    """Fetch tags for a book in app/routes/ui.py."""
    return conn.execute(
        """
        SELECT t.id, t.name
        FROM tags t
        INNER JOIN book_tags bt ON bt.tag_id = t.id
        WHERE bt.book_id = ?
        ORDER BY t.name
        """,
        (book_id,),
    ).fetchall()


def fetch_dashboard_totals(conn: sqlite3.Connection) -> sqlite3.Row:
    """Fetch dashboard totals for app/main.py."""
    return conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM authors) AS authors,
            (SELECT COUNT(*) FROM books) AS books,
            (SELECT COUNT(*) FROM files) AS files
        """
    ).fetchone()


def fetch_books_per_author(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Fetch book counts per author for the dashboard."""
    return conn.execute(
        """
        SELECT
            a.id,
            a.name,
            COUNT(b.id) AS book_count
        FROM authors a
        LEFT JOIN books b ON b.author_id = a.id
        GROUP BY a.id
        ORDER BY book_count DESC, a.name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_books_per_tag(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Fetch book counts per tag for the dashboard (excluding topics)."""
    return conn.execute(
        """
        SELECT
            t.name,
            COUNT(bt.book_id) AS book_count
        FROM tags t
        LEFT JOIN book_tags bt ON bt.tag_id = t.id
        WHERE t.name NOT LIKE 'topic:%'
        GROUP BY t.id
        ORDER BY book_count DESC, t.name
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_books_per_tag_namespace(
    conn: sqlite3.Connection,
    tag_prefix: str,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Fetch book counts per tag within a namespace for the dashboard."""
    return conn.execute(
        """
        SELECT
            t.id,
            t.name,
            COUNT(bt.book_id) AS book_count
        FROM tags t
        LEFT JOIN book_tags bt ON bt.tag_id = t.id
        WHERE t.name LIKE ?
        GROUP BY t.id
        ORDER BY book_count DESC, t.name
        LIMIT ?
        """,
        (f"{tag_prefix}:%", limit),
    ).fetchall()


def fetch_recent_activity(conn: sqlite3.Connection, limit: int = 8) -> list[sqlite3.Row]:
    """Fetch recent activity for app/main.py."""
    return conn.execute(
        """
        SELECT event_type, result, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_bulk_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch export rows for CSV in app/routes/batch_actions.py."""
    return conn.execute(
        """
        SELECT
            b.id,
            b.title,
            a.name AS author,
            t.name AS tag_name
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        LEFT JOIN book_tags bt ON bt.book_id = b.id
        LEFT JOIN tags t ON t.id = bt.tag_id
        ORDER BY a.name, b.title, t.name
        """
    ).fetchall()


def fetch_books_for_metadata(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch minimal book data for bulk metadata workflows."""
    return conn.execute(
        """
        SELECT
            b.id,
            b.title,
            b.normalized_title,
            a.name AS author
            ,
            a.normalized_author
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        ORDER BY b.id
        """
    ).fetchall()


def fetch_tag_rows_for_recommendations(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch tag rows for filters in app/routes/ui.py."""
    return conn.execute(
        """
        SELECT id, name
        FROM tags
        WHERE name LIKE '%:%'
        ORDER BY name
        """
    ).fetchall()


def fetch_recommendation_books(
    conn: sqlite3.Connection,
    namespace_filters: dict[str, list[int]],
    topic_ids: list[int],
    range_filters: dict[str, tuple[float | None, float | None]],
) -> list[sqlite3.Row]:
    """Fetch filtered recommendations in app/routes/ui.py."""
    has_namespace = any(namespace_filters.values())
    has_topics = bool(topic_ids)
    has_range = any(
        min_value is not None or max_value is not None
        for min_value, max_value in range_filters.values()
    )
    if not (has_namespace or has_topics or has_range):
        return []

    where_clauses: list[str] = []
    params: list[object] = []

    for prefix, ids in namespace_filters.items():
        if not ids:
            continue
        placeholders = ", ".join("?" for _ in ids)
        where_clauses.append(
            f"""
            EXISTS (
                SELECT 1
                FROM book_tags bt
                WHERE bt.book_id = b.id
                  AND bt.tag_id IN ({placeholders})
            )
            """
        )
        params.extend(ids)

    if topic_ids:
        topic_placeholders = ", ".join("?" for _ in topic_ids)
        where_clauses.append(
            f"""
            EXISTS (
                SELECT 1
                FROM book_tags bt
                WHERE bt.book_id = b.id
                  AND bt.tag_id IN ({topic_placeholders})
            )
            """
        )
        params.extend(topic_ids)

    for prefix, (min_value, max_value) in range_filters.items():
        if min_value is None and max_value is None:
            continue
        min_value = 0.0 if min_value is None else min_value
        max_value = 1.0 if max_value is None else max_value
        where_clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM book_tags bt
                JOIN tags t ON t.id = bt.tag_id
                WHERE bt.book_id = b.id
                  AND t.name LIKE ?
                  AND CAST(substr(t.name, instr(t.name, ':') + 1) AS REAL) BETWEEN ? AND ?
            )
            """
        )
        params.extend([f"{prefix}:%", min_value, max_value])

    where_sql = " AND ".join(clause.strip() for clause in where_clauses)

    return conn.execute(
        f"""
        SELECT
            b.id,
            b.title,
            a.name AS author,
            b.description AS description,
            (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        WHERE {where_sql}
        ORDER BY RANDOM()
        """,
        params,
    ).fetchall()


def fetch_author_name(conn: sqlite3.Connection, author_id: int) -> str | None:
    """Fetch author names for app/routes/ui.py."""
    row = conn.execute(
        "SELECT name FROM authors WHERE id = ?",
        (author_id,),
    ).fetchone()
    return str(row["name"]) if row else None


def fetch_tag_name(conn: sqlite3.Connection, tag_id: int) -> str | None:
    """Fetch tag names for app/routes/ui.py."""
    row = conn.execute(
        "SELECT name FROM tags WHERE id = ?",
        (tag_id,),
    ).fetchone()
    return str(row["name"]) if row else None


def fetch_books(
    conn: sqlite3.Connection,
    *,
    author_id: int | None = None,
    tag_id: int | None = None,
    search_term: str | None = None,
) -> list[sqlite3.Row]:
    """Fetch filtered books for app/routes/ui.py."""
    joins = []
    where_clauses = []
    params: list[object] = []
    if tag_id is not None:
        joins.append("INNER JOIN book_tags bt ON bt.book_id = b.id")
        where_clauses.append("bt.tag_id = ?")
        params.append(tag_id)
    if author_id is not None:
        where_clauses.append("b.author_id = ?")
        params.append(author_id)
    if search_term:
        where_clauses.append("(b.title LIKE ? OR a.name LIKE ?)")
        like_term = f"%{search_term}%"
        params.extend([like_term, like_term])

    join_sql = "\n        ".join(joins)
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    order_by = "ORDER BY b.title" if author_id is not None else "ORDER BY a.name, b.title"

    return conn.execute(
        f"""
        SELECT
            b.id,
            b.title,
            a.name AS author,
            b.description AS description,
            (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        {join_sql}
        {where_sql}
        {order_by}
        """,
        params,
    ).fetchall()


def fetch_authors(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch authors with counts for app/routes/ui.py."""
    return conn.execute(
        """
        SELECT
            a.id,
            a.name,
            (SELECT COUNT(*) FROM books b WHERE b.author_id = a.id) AS book_count
        FROM authors a
        ORDER BY a.name
        """
    ).fetchall()


def fetch_tags_with_counts(conn: sqlite3.Connection, *, include_topics: bool) -> list[sqlite3.Row]:
    """Fetch tags for app/routes/ui.py, with or without topics."""
    like_clause = "LIKE" if include_topics else "NOT LIKE"
    return conn.execute(
        f"""
        SELECT
            t.id,
            t.name,
            (SELECT COUNT(*) FROM book_tags bt WHERE bt.tag_id = t.id) AS book_count
        FROM tags t
        WHERE t.name {like_clause} 'topic:%'
        ORDER BY t.name
        """
    ).fetchall()


def fetch_book_detail(conn: sqlite3.Connection, book_id: int) -> sqlite3.Row | None:
    """Fetch a single book for app/routes/ui.py."""
    return conn.execute(
        """
        SELECT
            b.id,
            b.title,
            b.path,
            a.name AS author,
            b.author_id AS author_id,
            b.normalized_title,
            a.normalized_author,
            b.description,
            b.raw_description
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        WHERE b.id = ?
        """,
        (book_id,),
    ).fetchone()


def fetch_adjacent_book_ids(
    conn: sqlite3.Connection,
    book_id: int,
) -> tuple[int | None, int | None]:
    """Fetch previous and next book ids for navigation in app/routes/ui.py."""
    prev_row = conn.execute(
        "SELECT id FROM books WHERE id < ? ORDER BY id DESC LIMIT 1",
        (book_id,),
    ).fetchone()
    next_row = conn.execute(
        "SELECT id FROM books WHERE id > ? ORDER BY id ASC LIMIT 1",
        (book_id,),
    ).fetchone()
    prev_id = int(prev_row["id"]) if prev_row else None
    next_id = int(next_row["id"]) if next_row else None
    return prev_id, next_id


def update_book_description(conn: sqlite3.Connection, book_id: int, description: str | None) -> None:
    """Update a book description in app/routes/api.py."""
    conn.execute(
        """
        UPDATE books
        SET description = ?
        WHERE id = ?
        """,
        (description, book_id),
    )
    conn.commit()


def update_book_raw_description(
    conn: sqlite3.Connection,
    book_id: int,
    raw_description: str | None,
) -> None:
    """Update the raw description for app/routes/api.py."""
    conn.execute(
        """
        UPDATE books
        SET raw_description = ?
        WHERE id = ?
        """,
        (raw_description, book_id),
    )
    conn.commit()


def fetch_book_files(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
    """Fetch book files for app/routes/ui.py."""
    return conn.execute(
        """
        SELECT path, size_bytes, modified_time
        FROM files
        WHERE book_id = ?
        ORDER BY path
        """,
        (book_id,),
    ).fetchall()


def book_exists(conn: sqlite3.Connection, book_id: int) -> bool:
    """Check book existence during CSV import in app/routes/batch_actions.py."""
    row = conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
    return row is not None


def log_activity(
    conn: sqlite3.Connection,
    event_type: str,
    result: str | None = None,
    *,
    level: str = "info",
    status: str = "success",
    metadata: dict[str, object] | None = None,
    source: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> None:
    """Write activity log entries in app/db.py and app/routes/ui.py."""
    payload = json.dumps(metadata) if metadata else None
    conn.execute(
        """
        INSERT INTO activity_log (
            event_type,
            level,
            status,
            result,
            metadata,
            source,
            actor_type,
            actor_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(event_type),
            level,
            status,
            result,
            payload,
            source,
            actor_type,
            actor_id,
            time.time(),
        ),
    )
    conn.commit()
