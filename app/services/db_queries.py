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


def fetch_books_with_authors_and_tags(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch books, authors, and tags for bulk tagging in app/routes/bulk_actions.py."""
    return conn.execute(
        """
        SELECT
            b.id AS book_id,
            b.title AS title,
            a.name AS author,
            b.normalized_title AS normalized_title,
            a.normalized_author AS normalized_author,
            t.name AS tag_name
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        LEFT JOIN book_tags bt ON bt.book_id = b.id
        LEFT JOIN tags t ON t.id = bt.tag_id
        ORDER BY a.name, b.title, t.name
        """
    ).fetchall()


def fetch_bulk_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch export rows for CSV in app/routes/bulk_actions.py."""
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
) -> list[sqlite3.Row]:
    """Fetch filtered recommendations in app/routes/ui.py."""
    selected_tag_ids = [tag_id for ids in namespace_filters.values() for tag_id in ids]
    selected_tag_ids.extend(topic_ids)
    if not selected_tag_ids:
        return []

    placeholders = ", ".join("?" for _ in selected_tag_ids)
    having_clauses: list[str] = []
    params: list[object] = [*selected_tag_ids]
    for ids in namespace_filters.values():
        if not ids:
            continue
        namespace_placeholders = ", ".join("?" for _ in ids)
        having_clauses.append(
            f"SUM(CASE WHEN bt.tag_id IN ({namespace_placeholders}) THEN 1 ELSE 0 END) > 0"
        )
        params.extend(ids)
    if topic_ids:
        topic_placeholders = ", ".join("?" for _ in topic_ids)
        having_clauses.append(
            f"SUM(CASE WHEN bt.tag_id IN ({topic_placeholders}) THEN 1 ELSE 0 END) > 0"
        )
        params.extend(topic_ids)

    return conn.execute(
        f"""
        SELECT
            b.id,
            b.title,
            a.name AS author,
            (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        INNER JOIN book_tags bt ON bt.book_id = b.id
        WHERE bt.tag_id IN ({placeholders})
        GROUP BY b.id
        HAVING {' AND '.join(having_clauses)}
        ORDER BY a.name, b.title
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
            a.normalized_author
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        WHERE b.id = ?
        """,
        (book_id,),
    ).fetchone()


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
    """Check book existence during CSV import in app/routes/bulk_actions.py."""
    row = conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
    return row is not None


def fetch_authors_for_normalization(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch authors to normalize in app/routes/bulk_actions.py."""
    return conn.execute(
        """
        SELECT id, name
        FROM authors
        ORDER BY id
        """
    ).fetchall()


def fetch_books_for_normalization(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch books to normalize in app/routes/bulk_actions.py."""
    return conn.execute(
        """
        SELECT id, title
        FROM books
        ORDER BY id
        """
    ).fetchall()


def update_normalized_author(conn: sqlite3.Connection, author_id: int, normalized: str | None) -> None:
    """Update normalized author names in app/routes/bulk_actions.py."""
    conn.execute(
        """
        UPDATE authors
        SET normalized_author = ?
        WHERE id = ?
        """,
        (normalized, author_id),
    )


def update_normalized_title(conn: sqlite3.Connection, book_id: int, normalized: str | None) -> None:
    """Update normalized titles in app/routes/bulk_actions.py."""
    conn.execute(
        """
        UPDATE books
        SET normalized_title = ?
        WHERE id = ?
        """,
        (normalized, book_id),
    )


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
