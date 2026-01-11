from __future__ import annotations

import json
import sqlite3
import time
from enum import Enum
from pathlib import Path
from typing import Iterable

from .config import load_config


class ActivityEvent(str, Enum):
    SCAN_LIBRARY = "scan_library"
    EXPORT_LIBRARY_CSV = "export_library_csv"
    CLEAN_UNUSED_TAGS = "clean_unused_tags"
    BOOK_TAGS_UPDATED = "book_tags_updated"
    BULK_TAGGING_STARTED = "bulk_tagging_started"
    BULK_TAGGING_COMPLETED = "bulk_tagging_completed"
    BULK_TAG_IMPORT = "bulk_tag_import"
    NORMALIZE_TITLES = "normalize_titles"
    NORMALIZE_AUTHORS = "normalize_authors"
    CLEAR_ALL_TAGS = "clear_all_tags"
    CLEAR_DATABASE = "clear_database"


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = load_config().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        db_path.touch()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY,
            event_type TEXT NOT NULL,
            level TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            metadata TEXT,
            source TEXT,
            actor_type TEXT,
            actor_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL,
            normalized_author TEXT
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author_id INTEGER,
            path TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL,
            normalized_title TEXT,
            FOREIGN KEY(author_id) REFERENCES authors(id)
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS book_tags (
            book_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (book_id, tag_id),
            FOREIGN KEY(book_id) REFERENCES books(id),
            FOREIGN KEY(tag_id) REFERENCES tags(id)
        );
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            size_bytes INTEGER NOT NULL,
            modified_time REAL NOT NULL,
            book_id INTEGER,
            FOREIGN KEY(book_id) REFERENCES books(id)
        );
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
        CREATE INDEX IF NOT EXISTS idx_files_book_id ON files(book_id);
        CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
        CREATE INDEX IF NOT EXISTS idx_books_author_id ON books(author_id);
        """
    )
    conn.commit()



def upsert_files(conn: sqlite3.Connection, rows: Iterable[tuple[str, int, float, int | None]]) -> int:
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO files (path, size_bytes, modified_time, book_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            size_bytes=excluded.size_bytes,
            modified_time=excluded.modified_time,
            book_id=excluded.book_id
        """,
        rows,
    )
    conn.commit()
    return cur.rowcount


def get_or_create_author(conn: sqlite3.Connection, name: str) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO authors (name, created_at)
        VALUES (?, ?)
        """,
        (name, time.time()),
    )
    row = conn.execute("SELECT id FROM authors WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to load author id.")
    return int(row["id"])


def get_or_create_book(conn: sqlite3.Connection, title: str, author_id: int | None, path: str) -> int:
    conn.execute(
        """
        INSERT OR IGNORE INTO books (title, author_id, path, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (title, author_id, path, time.time()),
    )
    row = conn.execute("SELECT id FROM books WHERE path = ?", (path,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to load book id.")
    return int(row["id"])


def get_or_create_tag(conn: sqlite3.Connection, name: str) -> tuple[int | None, bool]:
    cleaned = " ".join(name.split())
    if not cleaned:
        return None, False
    row = conn.execute(
        "SELECT id FROM tags WHERE name = ? COLLATE NOCASE",
        (cleaned,),
    ).fetchone()
    if row is not None:
        return int(row["id"]), False
    conn.execute(
        """
        INSERT OR IGNORE INTO tags (name)
        VALUES (?)
        """,
        (cleaned,),
    )
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (cleaned,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to load tag id.")
    return int(row["id"]), True


def add_tags_to_book(conn: sqlite3.Connection, book_id: int, tag_ids: Iterable[int]) -> int:
    rows = [(book_id, tag_id) for tag_id in tag_ids]
    if not rows:
        return 0
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR IGNORE INTO book_tags (book_id, tag_id)
        VALUES (?, ?)
        """,
        rows,
    )
    conn.commit()
    return cur.rowcount


def remove_tag_from_book(conn: sqlite3.Connection, book_id: int, tag_id: int) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM book_tags
        WHERE book_id = ? AND tag_id = ?
        """,
        (book_id, tag_id),
    )
    cur.execute(
        """
        DELETE FROM tags
        WHERE id = ?
          AND NOT EXISTS (
              SELECT 1
              FROM book_tags
              WHERE tag_id = ?
          )
        """,
        (tag_id, tag_id),
    )
    conn.commit()
    return cur.rowcount


def clean_unused_tags(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM tags
        WHERE NOT EXISTS (
            SELECT 1
            FROM book_tags
            WHERE book_tags.tag_id = tags.id
        )
        """
    )
    conn.commit()
    return cur.rowcount


def clear_all_tags(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    cur.execute("DELETE FROM book_tags")
    removed_links = cur.rowcount
    cur.execute("DELETE FROM tags")
    removed_tags = cur.rowcount
    conn.commit()
    return removed_links, removed_tags


def clear_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS files;
        DROP TABLE IF EXISTS book_tags;
        DROP TABLE IF EXISTS tags;
        DROP TABLE IF EXISTS books;
        DROP TABLE IF EXISTS authors;
        DROP TABLE IF EXISTS activity_log;
        """
    )
    conn.commit()


def get_book_tags(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
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
    return conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM authors) AS authors,
            (SELECT COUNT(*) FROM books) AS books,
            (SELECT COUNT(*) FROM files) AS files
        """
    ).fetchone()


def fetch_recent_activity(conn: sqlite3.Connection, limit: int = 8) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT event_type, result, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_bulk_actions_books(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            b.id AS book_id,
            b.title AS title,
            a.name AS author,
            t.name AS tag_name
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        LEFT JOIN book_tags bt ON bt.book_id = b.id
        LEFT JOIN tags t ON t.id = bt.tag_id
        ORDER BY a.name, b.title, t.name
        """
    ).fetchall()


def fetch_bulk_export_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
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
    row = conn.execute(
        "SELECT name FROM authors WHERE id = ?",
        (author_id,),
    ).fetchone()
    return str(row["name"]) if row else None


def fetch_tag_name(conn: sqlite3.Connection, tag_id: int) -> str | None:
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
    return conn.execute(
        """
        SELECT
            b.id,
            b.title,
            b.path,
            a.name AS author,
            b.author_id AS author_id
        FROM books b
        LEFT JOIN authors a ON a.id = b.author_id
        WHERE b.id = ?
        """,
        (book_id,),
    ).fetchone()


def fetch_book_files(conn: sqlite3.Connection, book_id: int) -> list[sqlite3.Row]:
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
    row = conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
    return row is not None


def fetch_authors_for_normalization(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, name
        FROM authors
        ORDER BY id
        """
    ).fetchall()


def fetch_books_for_normalization(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, title
        FROM books
        ORDER BY id
        """
    ).fetchall()


def update_normalized_author(conn: sqlite3.Connection, author_id: int, normalized: str | None) -> None:
    conn.execute(
        """
        UPDATE authors
        SET normalized_author = ?
        WHERE id = ?
        """,
        (normalized, author_id),
    )


def update_normalized_title(conn: sqlite3.Connection, book_id: int, normalized: str | None) -> None:
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
    event_type: ActivityEvent | str,
    result: str | None = None,
    *,
    level: str = "info",
    status: str = "success",
    metadata: dict[str, object] | None = None,
    source: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
) -> None:
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
