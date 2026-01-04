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


def log_activity(conn: sqlite3.Connection, event_type: str, result: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO activity_log (event_type, result, created_at)
        VALUES (?, ?, ?)
        """,
        (event_type, result, time.time()),
    )
    conn.commit()
