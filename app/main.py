from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import iter_files, load_config
from .db import clear_library, clear_tags, get_connection, get_or_create_author, get_or_create_book, init_db, log_activity, upsert_files

app = FastAPI(title="Audiobook Library Backend")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


class ScanResult(BaseModel):
    indexed: int
    scanned_at: str


@app.on_event("startup")
def startup() -> None:
    with get_connection() as conn:
        init_db(conn)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon() -> Response:
    favicon_path = Path(__file__).resolve().parent / "static" / "favicon.ico"
    if favicon_path.is_file():
        return FileResponse(favicon_path)
    return Response(status_code=204)


@app.post("/scan", response_model=ScanResult)
def scan_library() -> ScanResult:
    config = load_config()
    rows: list[tuple[str, int, float, int | None]] = []
    author_cache: dict[str, int] = {}
    book_cache: dict[str, int] = {}

    with get_connection() as conn:
        for path in iter_files(config.library_roots, config.allowed_extensions, config.ignore_patterns):
            stat = path.stat()
            book_id = _infer_book_id(conn, path, config.library_roots, author_cache, book_cache)
            rows.append((str(path), stat.st_size, stat.st_mtime, book_id))
        indexed = upsert_files(conn, rows)
        log_activity(conn, "scan_library", f"{indexed} files indexed")

    scanned_at = datetime.utcnow().isoformat() + "Z"
    return ScanResult(indexed=indexed, scanned_at=scanned_at)


@app.get("/ui")
def ui_dashboard(request: Request):
    totals, formatted_activity = _get_dashboard_data()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "totals": totals, "issues": [], "activity": formatted_activity},
    )


@app.get("/ui/summary")
def ui_summary() -> dict[str, object]:
    totals, formatted_activity = _get_dashboard_data()
    return {"totals": dict(totals), "activity": formatted_activity}


@app.post("/ui/reset")
def ui_reset_library() -> Response:
    with get_connection() as conn:
        clear_library(conn)
    return Response(status_code=204)


@app.post("/ui/reset-tags")
def ui_reset_tags() -> Response:
    with get_connection() as conn:
        clear_tags(conn)
    return Response(status_code=204)

@app.get("/ui/books")
def ui_books(request: Request, author_id: int | None = None, tag_id: int | None = None):
    author_name = None
    tag_name = None
    with get_connection() as conn:
        if author_id is not None and tag_id is not None:
            rows = []
        elif author_id is not None:
            author_row = conn.execute(
                "SELECT name FROM authors WHERE id = ?",
                (author_id,),
            ).fetchone()
            author_name = author_row["name"] if author_row else None
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.title,
                    a.name AS author,
                    (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
                FROM books b
                LEFT JOIN authors a ON a.id = b.author_id
                WHERE b.author_id = ?
                ORDER BY b.title
                """,
                (author_id,),
            ).fetchall()
        elif tag_id is not None:
            tag_row = conn.execute(
                "SELECT name FROM tags WHERE id = ?",
                (tag_id,),
            ).fetchone()
            tag_name = tag_row["name"] if tag_row else None
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.title,
                    a.name AS author,
                    (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
                FROM books b
                LEFT JOIN authors a ON a.id = b.author_id
                INNER JOIN book_tags bt ON bt.book_id = b.id
                WHERE bt.tag_id = ?
                ORDER BY a.name, b.title
                """,
                (tag_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    b.id,
                    b.title,
                    a.name AS author,
                    (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
                FROM books b
                LEFT JOIN authors a ON a.id = b.author_id
                ORDER BY a.name, b.title
                """
            ).fetchall()
    return templates.TemplateResponse(
        "books.html",
        {"request": request, "books": rows, "author_name": author_name, "tag_name": tag_name},
    )


@app.get("/ui/authors")
def ui_authors(request: Request):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id,
                a.name,
                (SELECT COUNT(*) FROM books b WHERE b.author_id = a.id) AS book_count
            FROM authors a
            ORDER BY a.name
            """
        ).fetchall()
    return templates.TemplateResponse(
        "authors.html",
        {"request": request, "authors": rows},
    )


@app.get("/ui/tags")
def ui_tags(request: Request):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.id,
                t.name,
                (SELECT COUNT(*) FROM book_tags bt WHERE bt.tag_id = t.id) AS book_count
            FROM tags t
            ORDER BY t.name
            """
        ).fetchall()
    return templates.TemplateResponse(
        "tags.html",
        {"request": request, "tags": rows},
    )


@app.get("/ui/books/{book_id}")
def ui_book_detail(request: Request, book_id: int):
    with get_connection() as conn:
        book = conn.execute(
            """
            SELECT
                b.id,
                b.title,
                b.path,
                a.name AS author
            FROM books b
            LEFT JOIN authors a ON a.id = b.author_id
            WHERE b.id = ?
            """,
            (book_id,),
        ).fetchone()
        files = conn.execute(
            """
            SELECT path, size_bytes, modified_time
            FROM files
            WHERE book_id = ?
            ORDER BY path
            """,
            (book_id,),
        ).fetchall()
    if book is None:
        return Response(status_code=404)
    return templates.TemplateResponse(
        "book_detail.html",
        {
            "request": request,
            "book": book,
            "files": [
                {
                    "path": row["path"],
                    "size": _format_bytes(row["size_bytes"]),
                    "modified": datetime.fromtimestamp(row["modified_time"]).isoformat(),
                }
                for row in files
            ],
        },
    )


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024


def _get_dashboard_data():
    with get_connection() as conn:
        totals = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM authors) AS authors,
                (SELECT COUNT(*) FROM books) AS books,
                (SELECT COUNT(*) FROM files) AS files
            """
        ).fetchone()
        activity = conn.execute(
            """
            SELECT event_type, result, created_at
            FROM activity_log
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()
    formatted_activity = [
        {
            "event_type": entry["event_type"],
            "result": entry["result"],
            "created_at": datetime.fromtimestamp(entry["created_at"]).isoformat(),
        }
        for entry in activity
    ]
    return totals, formatted_activity


def _infer_book_id(
    conn,
    file_path: Path,
    roots: list[Path],
    author_cache: dict[str, int],
    book_cache: dict[str, int],
) -> int | None:
    root = next((r for r in roots if file_path.is_relative_to(r)), None)
    if root is None:
        return None
    parts = file_path.relative_to(root).parts
    if len(parts) < 3:
        return None
    author = parts[0]
    title = parts[1]
    book_folder = root / author / title
    book_key = str(book_folder)
    author_id = author_cache.get(author)
    if author_id is None:
        author_id = get_or_create_author(conn, author)
        author_cache[author] = author_id
    book_id = book_cache.get(book_key)
    if book_id is None:
        book_id = get_or_create_book(conn, title, author_id, book_key)
        book_cache[book_key] = book_id
    return book_id
