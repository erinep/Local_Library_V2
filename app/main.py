from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import iter_files, load_config
from .db import (
    add_tags_to_book,
    clean_unused_tags,
    ActivityEvent,
    clear_all_tags,
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
from .routes.api import build_api_router
from .routes.bulk_actions import build_bulk_actions_router
from .routes.ui import build_ui_router

app = FastAPI(title="Audiobook Library Backend")
_books_provider = GoogleBooksProvider()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _urlencode(value: object) -> str:
    if value is None:
        return ""
    return quote_plus(str(value))


templates.env.filters["urlencode"] = _urlencode

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


@app.on_event("startup")
def startup() -> None:
    with get_connection() as conn:
        init_db(conn)


def _format_bytes(size_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} {units[-1]}"


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


app.include_router(
    build_api_router(
        books_provider=_books_provider,
        load_config=load_config,
        iter_files=iter_files,
        get_connection=get_connection,
        upsert_files=upsert_files,
        log_activity=log_activity,
        ActivityEvent=ActivityEvent,
        infer_book_id=_infer_book_id,
    )
)
app.include_router(
    build_ui_router(
        templates=templates,
        get_connection=get_connection,
        get_dashboard_data=_get_dashboard_data,
        get_book_tags=get_book_tags,
        add_tags_to_book=add_tags_to_book,
        remove_tag_from_book=remove_tag_from_book,
        get_or_create_tag=get_or_create_tag,
        log_activity=log_activity,
        ActivityEvent=ActivityEvent,
        split_tags=_split_tags,
        normalize_search=_normalize_search,
        format_bytes=_format_bytes,
        TAG_NAMESPACE_CONFIG=TAG_NAMESPACE_CONFIG,
        TAG_NAMESPACE_LIST=TAG_NAMESPACE_LIST,
    )
)
app.include_router(
    build_bulk_actions_router(
        get_connection=get_connection,
        log_activity=log_activity,
        ActivityEvent=ActivityEvent,
        clean_unused_tags=clean_unused_tags,
        clear_all_tags=clear_all_tags,
        get_or_create_tag=get_or_create_tag,
        add_tags_to_book=add_tags_to_book,
        TAG_NAMESPACE_LIST=TAG_NAMESPACE_LIST,
    )
)
