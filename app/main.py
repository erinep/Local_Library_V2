from __future__ import annotations

from datetime import datetime
import csv
import io
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
    clean_unused_tags,
    ActivityEvent,
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

TAG_NAMESPACE_CONFIG = [
    {"tag_prefix": "Genre", "query_param": "genre", "ui_label": "Genre"},
    {"tag_prefix": "Pacing", "query_param": "pacing", "ui_label": "Pacing"},
    {"tag_prefix": "Reader", "query_param": "reader", "ui_label": "Reader"},
    {"tag_prefix": "Romance", "query_param": "romance", "ui_label": "Romance"},
    {"tag_prefix": "Scale", "query_param": "scale", "ui_label": "Scale"},
    {"tag_prefix": "Series", "query_param": "series", "ui_label": "Series"},
    {"tag_prefix": "Setting", "query_param": "setting", "ui_label": "Setting"},
    {"tag_prefix": "Spice", "query_param": "spice", "ui_label": "Spice"},
    {"tag_prefix": "StoryEngine", "query_param": "storyengine", "ui_label": "Story engine"},
    {"tag_prefix": "Tone", "query_param": "tone", "ui_label": "Tone"},
]
TAG_NAMESPACE_LIST = [entry["tag_prefix"] for entry in TAG_NAMESPACE_CONFIG]


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


class BulkTaggingResult(BaseModel):
    status: str
    processed: int | None = None
    total: int | None = None


@app.on_event("startup")
def startup() -> None:
    with get_connection() as conn:
        init_db(conn)



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
        log_activity(
            conn,
            ActivityEvent.SCAN_LIBRARY,
            f"{indexed} files indexed",
            metadata={"indexed": indexed},
            source="scan_library",
        )

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
    results = list(books.values())
    with get_connection() as conn:
        log_activity(
            conn,
            ActivityEvent.BULK_TAGGING_STARTED,
            f"{len(results)} books loaded for bulk tagging",
            metadata={"book_count": len(results)},
            source="bulk_actions_books",
        )
    return results


@app.get("/ui/bulk-actions/export")
def ui_bulk_actions_export() -> Response:
    with get_connection() as conn:
        rows = conn.execute(
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
    books: dict[int, dict[str, object]] = {}
    prefixes: set[str] = set()
    for row in rows:
        book_id = int(row["id"])
        entry = books.get(book_id)
        if entry is None:
            entry = {
                "id": book_id,
                "title": row["title"],
                "author": row["author"] or "",
                "tags": {},
            }
            books[book_id] = entry
        tag_name = row["tag_name"]
        if not tag_name:
            continue
        tag_text = str(tag_name)
        if ":" in tag_text:
            prefix, value = tag_text.split(":", 1)
            prefix = prefix.strip() or "General"
            value = value.strip()
        else:
            prefix = "General"
            value = tag_text.strip()
        if not value:
            continue
        prefixes.add(prefix)
        tag_bucket = entry["tags"].setdefault(prefix, [])
        tag_bucket.append(value)

    sorted_prefixes = sorted(prefixes)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "title", "author", *sorted_prefixes])
    for entry in books.values():
        row_values = [
            entry["id"],
            entry["title"],
            entry["author"],
        ]
        tags_by_prefix: dict[str, list[str]] = entry["tags"]
        for prefix in sorted_prefixes:
            values = tags_by_prefix.get(prefix, [])
            row_values.append(", ".join(values))
        writer.writerow(row_values)
    headers = {"Content-Disposition": "attachment; filename=books_export.csv"}
    with get_connection() as conn:
        log_activity(
            conn,
            ActivityEvent.EXPORT_LIBRARY_CSV,
            f"{len(books)} books exported",
            metadata={"book_count": len(books), "tag_prefixes": sorted_prefixes},
            source="bulk_actions_export",
        )
    return Response(content=output.getvalue(), media_type="text/csv", headers=headers)


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


@app.post("/ui/bulk-actions/cleanup-tags")
def ui_cleanup_tags() -> dict[str, int]:
    with get_connection() as conn:
        removed = clean_unused_tags(conn)
        log_activity(
            conn,
            ActivityEvent.CLEAN_UNUSED_TAGS,
            f"{removed} tags removed",
            metadata={"removed": removed},
            source="cleanup_tags",
        )
    return {"removed": removed}


@app.post("/ui/bulk-actions/complete")
def ui_bulk_actions_complete(payload: BulkTaggingResult) -> dict[str, int | None | str]:
    normalized = payload.status.lower()
    if normalized not in {"completed", "stopped"}:
        normalized = "completed"
    with get_connection() as conn:
        log_activity(
            conn,
            ActivityEvent.BULK_TAGGING_COMPLETED,
            f"bulk tagging {normalized}",
            status="success" if normalized == "completed" else "stopped",
            metadata={
                "processed": payload.processed,
                "total": payload.total,
                "status": normalized,
            },
            source="bulk_tagging_complete",
        )
    return {"processed": payload.processed, "total": payload.total, "status": normalized}


@app.get("/ui/summary")
def ui_summary() -> dict[str, object]:
    totals, formatted_activity = _get_dashboard_data()
    return {"totals": dict(totals), "activity": formatted_activity}


@app.get("/ui/recommendations")
def ui_recommendations(
    request: Request,
):
    def _unique_ids(values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))

    def _parse_int_list(values: list[str]) -> list[int]:
        parsed: list[int] = []
        for value in values:
            stripped = value.strip()
            if not stripped:
                continue
            try:
                parsed.append(int(stripped))
            except ValueError:
                continue
        return parsed

    query_params = request.query_params
    namespace_inputs = {
        entry["query_param"]: _parse_int_list(query_params.getlist(entry["query_param"]))
        for entry in TAG_NAMESPACE_CONFIG
    }
    namespace_filters = {
        entry["tag_prefix"]: _unique_ids(namespace_inputs[entry["query_param"]])
        for entry in TAG_NAMESPACE_CONFIG
    }
    topic_ids = _unique_ids(_parse_int_list(query_params.getlist("topic_id")))
    with get_connection() as conn:
        tag_rows = conn.execute(
            """
            SELECT id, name
            FROM tags
            WHERE name LIKE '%:%'
            ORDER BY name
            """
        ).fetchall()
        grouped: dict[str, list[dict[str, object]]] = {ns: [] for ns in TAG_NAMESPACE_LIST}
        topics: list[dict[str, object]] = []
        for row in tag_rows:
            name = str(row["name"])
            if ":" not in name:
                continue
            namespace, value = name.split(":", 1)
            value = value.strip()
            if namespace.lower() == "topic":
                topics.append({"id": row["id"], "name": name, "display_name": value})
            elif namespace in grouped:
                grouped[namespace].append({"id": row["id"], "name": name, "display_name": value})

        selected = {
            **namespace_filters,
            "Topic": topic_ids,
        }

        selected_tag_ids = [tag_id for ids in namespace_filters.values() for tag_id in ids]
        selected_tag_ids.extend(topic_ids)

        if selected_tag_ids:
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

            rows = conn.execute(
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
        else:
            rows = []

        label_map = {item["id"]: item["display_name"] for group in grouped.values() for item in group}
        topic_labels = {item["id"]: item["display_name"] for item in topics}
        summary_parts: list[str] = []
        label_lookup = {
            entry["tag_prefix"]: entry["ui_label"]
            for entry in TAG_NAMESPACE_CONFIG
        }
        for key in TAG_NAMESPACE_LIST:
            tag_ids = namespace_filters.get(key, [])
            if not tag_ids:
                continue
            names = [label_map.get(tag_id) for tag_id in tag_ids if label_map.get(tag_id)]
            if names:
                summary_label = label_lookup.get(key, key)
                summary_parts.append(f"{summary_label}: {', '.join(names)}")
        if topic_ids:
            names = [topic_labels.get(tid) for tid in topic_ids if topic_labels.get(tid)]
            if names:
                summary_parts.append(f"Topics: {', '.join(names)}")
        summary = "No filters selected." if not summary_parts else "Filters: " + " | ".join(summary_parts)

    return templates.TemplateResponse(
        "recommendations.html",
        {
            "request": request,
            "namespace_config": TAG_NAMESPACE_CONFIG,
            "grouped": grouped,
            "topics": topics,
            "selected": selected,
            "books": rows,
            "summary": summary,
        },
    )


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
            WHERE t.name NOT LIKE 'topic:%'
            ORDER BY t.name
            """
        ).fetchall()
    return templates.TemplateResponse(
        "tags.html",
        {"request": request, "tags": rows},
    )


@app.get("/ui/topics")
def ui_topics(request: Request):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                t.id,
                t.name,
                (SELECT COUNT(*) FROM book_tags bt WHERE bt.tag_id = t.id) AS book_count
            FROM tags t
            WHERE t.name LIKE 'topic:%'
            ORDER BY t.name
            """
        ).fetchall()
    topics = [
        {
            "id": row["id"],
            "name": row["name"],
            "display_name": row["name"].split(":", 1)[1].strip() if ":" in row["name"] else row["name"],
            "book_count": row["book_count"],
        }
        for row in rows
    ]
    return templates.TemplateResponse(
        "topics.html",
        {"request": request, "topics": topics},
    )


@app.post("/ui/tags")
def ui_add_tags(tags: str = Form(...)) -> RedirectResponse:
    tag_names = _split_tags(tags)
    tag_names = [
        name if name.lower().startswith("topic:") else f"topic:{name}"
        for name in tag_names
    ]
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
            "tags": [tag for tag in tags if not str(tag["name"]).lower().startswith("topic:")],
            "topics": [
                {
                    "id": tag["id"],
                    "name": tag["name"],
                    "display_name": str(tag["name"]).split(":", 1)[1].strip()
                    if ":" in str(tag["name"])
                    else tag["name"],
                }
                for tag in tags
                if str(tag["name"]).lower().startswith("topic:")
            ],
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
    tag_names = [
        name if name.lower().startswith("topic:") else f"topic:{name}"
        for name in tag_names
    ]
    tag_ids: list[int] = []
    with get_connection() as conn:
        for tag_name in tag_names:
            tag_id, _ = get_or_create_tag(conn, tag_name)
            if tag_id is not None:
                tag_ids.append(tag_id)
        added = add_tags_to_book(conn, book_id, tag_ids)
        log_activity(
            conn,
            ActivityEvent.BOOK_TAGS_UPDATED,
            f"{added} tags added",
            metadata={"book_id": book_id, "tag_ids": tag_ids, "added": added},
            source="add_book_tags",
        )
    return RedirectResponse(f"/ui/books/{book_id}", status_code=303)


@app.post("/ui/books/{book_id}/tags/{tag_id}/remove")
def ui_remove_book_tag(book_id: int, tag_id: int) -> RedirectResponse:
    with get_connection() as conn:
        removed = remove_tag_from_book(conn, book_id, tag_id)
        log_activity(
            conn,
            ActivityEvent.BOOK_TAGS_UPDATED,
            "tag removed",
            metadata={"book_id": book_id, "tag_id": tag_id, "removed": removed},
            source="remove_book_tag",
        )
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
