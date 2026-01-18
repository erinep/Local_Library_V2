from __future__ import annotations

import sqlite3
from enum import Enum
from pathlib import Path
from typing import Iterable
import time

from .config import load_config
from .services.normalization import normalize_author, normalize_title


class ActivityEvent(str, Enum):
    SCAN_LIBRARY = "scan_library"
    EXPORT_LIBRARY_CSV = "export_library_csv"
    CLEAN_UNUSED_TAGS = "clean_unused_tags"
    BOOK_TAGS_UPDATED = "book_tags_updated"
    BULK_TAG_IMPORT = "bulk_tag_import"
    CLEAR_ALL_TAGS = "clear_all_tags"
    CLEAR_DATABASE = "clear_database"
    BULK_METADATA_JOB_CREATED = "bulk_metadata_job_created"
    BULK_METADATA_JOB_COMPLETED = "bulk_metadata_job_completed"
    BULK_METADATA_JOB_FAILED = "bulk_metadata_job_failed"
    BULK_METADATA_JOB_CANCELLED = "bulk_metadata_job_cancelled"


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
            description TEXT,
            raw_description TEXT,
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
        CREATE TABLE IF NOT EXISTS metadata_jobs (
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            total_books INTEGER NOT NULL DEFAULT 0,
            processed_books INTEGER NOT NULL DEFAULT 0,
            succeeded_books INTEGER NOT NULL DEFAULT 0,
            failed_books INTEGER NOT NULL DEFAULT 0,
            current_book_id INTEGER,
            last_error TEXT,
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            cancelled_at REAL
        );
        CREATE TABLE IF NOT EXISTS metadata_job_events (
            id INTEGER PRIMARY KEY,
            job_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY(job_id) REFERENCES metadata_jobs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
        CREATE INDEX IF NOT EXISTS idx_files_book_id ON files(book_id);
        CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
        CREATE INDEX IF NOT EXISTS idx_books_author_id ON books(author_id);
        CREATE INDEX IF NOT EXISTS idx_metadata_jobs_status ON metadata_jobs(status);
        CREATE INDEX IF NOT EXISTS idx_metadata_job_events_job_id ON metadata_job_events(job_id);
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "description" not in columns:
        conn.execute("ALTER TABLE books ADD COLUMN description TEXT")
    if "raw_description" not in columns:
        conn.execute("ALTER TABLE books ADD COLUMN raw_description TEXT")
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
    normalized = normalize_author(name)
    conn.execute(
        """
        INSERT OR IGNORE INTO authors (name, created_at, normalized_author)
        VALUES (?, ?, ?)
        """,
        (name, time.time(), normalized),
    )
    row = conn.execute("SELECT id FROM authors WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to load author id.")
    return int(row["id"])


def get_or_create_book(conn: sqlite3.Connection, title: str, author_id: int | None, path: str) -> int:
    normalized = normalize_title(title)
    conn.execute(
        """
        INSERT OR IGNORE INTO books (title, author_id, path, created_at, normalized_title)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, author_id, path, time.time(), normalized),
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


def remove_non_topic_tags_from_book(conn: sqlite3.Connection, book_id: int) -> int:
    """Remove all tags for a book except those starting with 'topics:'."""
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM book_tags
        WHERE book_id = ?
          AND tag_id IN (
              SELECT id
              FROM tags
              WHERE name NOT LIKE 'topics:%'
          )
        """,
        (book_id,),
    )
    removed = cur.rowcount
    conn.commit()
    return removed


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


