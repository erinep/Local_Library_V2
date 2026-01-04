from __future__ import annotations

from datetime import datetime
from pathlib import Path

from urllib.parse import quote_plus
from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import iter_files, load_config
from .db import (
    add_tags_to_book,
    clear_library,
    clear_tags,
    get_book_tags,
    get_connection,
    get_or_create_author,
    get_or_create_book,
    get_or_create_tag,
    init_db,
    log_activity,
    remove_tag_from_book,
    upsert_files,
)
from .metadataProvider import GoogleBooksProvider

app = FastAPI(title="Audiobook Library Backend")
_books_provider = GoogleBooksProvider()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _urlencode(value: object) -> str:
    if value is None:
        return ''
    return quote_plus(str(value))


templates.env.filters['urlencode'] = _urlencode


class ScanResult(BaseModel):
    indexed: int
    scanned_at: str


class BookSearchResult(BaseModel):
    result_id: str
    title: str | None = None
    author: str | None = None


class TagCandidateResult(BaseModel):
    tag_text: str


class BookTagSummary(BaseModel):
    book_id: int
    title: str
    author: str | None = None
    tags: list[str]


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


@app.get("/search", response_model=list[BookSearchResult])
def search_books(title: str | None = None, author: str | None = None) -> list[BookSearchResult]:
    if not title and not author:
        raise HTTPException(status_code=400, detail="Provide at least a title or author.")
    results = _books_provider.search(author=author or "", title=title or "")
    return [
        BookSearchResult(result_id=result.result_id, title=result.title, author=result.author)
        for result in results
    ]


@app.get("/search/{result_id}/tags", response_model=list[TagCandidateResult])
def search_tags(result_id: str) -> list[TagCandidateResult]:
    tags = _books_provider.get_tags(result_id)
    return [
        TagCandidateResult(tag_text=tag.tag_text)
        for tag in tags
    ]


@app.get("/ui/bulk-actions/books", response_model=list[BookTagSummary])
def ui_bulk_actions_books() -> list[BookTagSummary]:
    with get_connection() as conn:
        rows = conn.execute(
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
    books: dict[int, BookTagSummary] = {}
    for row in rows:
        book_id = int(row["book_id"])
        entry = books.get(book_id)
        if entry is None:
            entry = BookTagSummary(
                book_id=book_id,
                title=row["title"],
                author=row["author"],
                tags=[],
            )
            books[book_id] = entry
        tag_name = row["tag_name"]
        if tag_name:
            entry.tags.append(tag_name)
    return list(books.values())


@app.get("/ui")
def ui_dashboard(request: Request):
    totals, formatted_activity = _get_dashboard_data()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "totals": totals, "issues": [], "activity": formatted_activity},
    )


@app.get("/ui/bulk-actions")
def ui_bulk_actions(request: Request):
    return templates.TemplateResponse(
        "bulk_actions.html",
        {"request": request},
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
def ui_books(
    request: Request,
    author_id: int | None = None,
    tag_id: int | None = None,
    q: str | None = None,
):
    author_name = None
    tag_name = None
    search_term = _normalize_search(q)
    with get_connection() as conn:
        if author_id is not None and tag_id is not None:
            rows = []
        else:
            if author_id is not None:
                author_row = conn.execute(
                    "SELECT name FROM authors WHERE id = ?",
                    (author_id,),
                ).fetchone()
                author_name = author_row["name"] if author_row else None
            if tag_id is not None:
                tag_row = conn.execute(
                    "SELECT name FROM tags WHERE id = ?",
                    (tag_id,),
                ).fetchone()
                tag_name = tag_row["name"] if tag_row else None

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

            join_sql = "\n                ".join(joins)
            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            order_by = "ORDER BY b.title" if author_id is not None else "ORDER BY a.name, b.title"

            rows = conn.execute(
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
    return templates.TemplateResponse(
        "books.html",
        {
            "request": request,
            "books": rows,
            "author_name": author_name,
            "tag_name": tag_name,
            "author_id": author_id,
            "tag_id": tag_id,
            "query": search_term or "",
        },
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


@app.post("/ui/tags")
def ui_add_tags(tags: str = Form(...)) -> RedirectResponse:
    tag_names = _split_tags(tags)
    created = 0
    with get_connection() as conn:
        for tag_name in tag_names:
            tag_id, was_created = get_or_create_tag(conn, tag_name)
            if tag_id is not None and was_created:
                created += 1
    return RedirectResponse("/ui/tags", status_code=303)


@app.get("/ui/books/{book_id}")
def ui_book_detail(request: Request, book_id: int):
    with get_connection() as conn:
        book = conn.execute(
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
        tags = get_book_tags(conn, book_id)
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
            "tags": tags,
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


@app.post("/ui/books/{book_id}/tags")
def ui_add_book_tags(book_id: int, tags: str = Form(...)) -> RedirectResponse:
    tag_names = _split_tags(tags)
    tag_ids: list[int] = []
    with get_connection() as conn:
        for tag_name in tag_names:
            tag_id, _ = get_or_create_tag(conn, tag_name)
            if tag_id is not None:
                tag_ids.append(tag_id)
        added = add_tags_to_book(conn, book_id, tag_ids)
    return RedirectResponse(f"/ui/books/{book_id}", status_code=303)


@app.post("/ui/books/{book_id}/tags/{tag_id}/remove")
def ui_remove_book_tag(book_id: int, tag_id: int) -> RedirectResponse:
    with get_connection() as conn:
        removed = remove_tag_from_book(conn, book_id, tag_id)
    return RedirectResponse(f"/ui/books/{book_id}", status_code=303)


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


def _split_tags(raw: str) -> list[str]:
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


def _normalize_search(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = " ".join(raw.split())
    return cleaned or None


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
