from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "library.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
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
            details TEXT,
            result TEXT,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            author_id INTEGER,
            path TEXT UNIQUE NOT NULL,
            created_at REAL NOT NULL,
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
    _ensure_column(conn, "files", "book_id", "INTEGER")
    _ensure_column(conn, "activity_log", "event_type", "TEXT")
    _ensure_column(conn, "activity_log", "details", "TEXT")
    _ensure_column(conn, "activity_log", "result", "TEXT")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


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


def clear_library(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM book_tags;
        DELETE FROM tags;
        DELETE FROM files;
        DELETE FROM books;
        DELETE FROM authors;
        """
    )
    conn.commit()
    log_activity(conn, "clear_library", "Library tables cleared")


def clear_tags(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM book_tags;
        DELETE FROM tags;
        """
    )
    conn.commit()
    log_activity(conn, "clear_tags", "Tags tables cleared")

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

def log_activity(conn: sqlite3.Connection, event_type: str, result: str | None = None, details: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO activity_log (event_type, details, result, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (event_type, details, result, time.time()),
    )
    conn.commit()
