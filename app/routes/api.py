from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, HTTPException

from ..schemas import (
    BookDescriptionResult,
    BookDescriptionUpdate,
    BookSearchResult,
    ScanResult,
    TagCandidateResult,
)
from ..services.db_queries import fetch_book_detail, update_book_description


def build_api_router(
    *,
    books_provider,
    load_config,
    iter_files,
    get_connection,
    upsert_files,
    log_activity,
    ActivityEvent,
    infer_book_id,
) -> APIRouter:
    router = APIRouter()

    @router.post("/scan", response_model=ScanResult)
    def scan_library() -> ScanResult:
        """Scan the library roots and upsert file metadata into the database."""
        config = load_config()
        rows: list[tuple[str, int, float, int | None]] = []
        author_cache: dict[str, int] = {}
        book_cache: dict[str, int] = {}

        with get_connection() as conn:
            for path in iter_files(config.library_roots, config.allowed_extensions, config.ignore_patterns):
                stat = path.stat()
                book_id = infer_book_id(conn, path, config.library_roots, author_cache, book_cache)
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

    @router.get("/search", response_model=list[BookSearchResult])
    def search_books(title: str | None = None, author: str | None = None) -> list[BookSearchResult]:
        """Search the provider by title/author and return candidate books."""
        if not title and not author:
            raise HTTPException(status_code=400, detail="Provide at least a title or author.")
        results = books_provider.search(author=author or "", title=title or "")
        return [
            BookSearchResult(result_id=result.result_id, title=result.title, author=result.author)
            for result in results
        ]

    @router.get("/search/{result_id}/tags", response_model=list[TagCandidateResult])
    def search_tags(result_id: str) -> list[TagCandidateResult]:
        """Fetch tag candidates for a provider result id."""
        tags = books_provider.get_tags(result_id)
        return [
            TagCandidateResult(tag_text=tag.tag_text)
            for tag in tags
        ]

    @router.post("/books/{book_id}/description/generate", response_model=BookDescriptionResult)
    def generate_description(book_id: int) -> BookDescriptionResult:
        """Generate a book description using the metadata provider (no save)."""
        with get_connection() as conn:
            book = fetch_book_detail(conn, book_id)
            if book is None:
                raise HTTPException(status_code=404, detail="Book not found.")
            title = book["normalized_title"] or book["title"] or ""
            author = book["normalized_author"] or book["author"] or ""
            description = books_provider.get_description(title=title, author=author)
        return BookDescriptionResult(book_id=book_id, description=description)

    @router.post("/books/{book_id}/description", response_model=BookDescriptionResult)
    def save_description(book_id: int, payload: BookDescriptionUpdate) -> BookDescriptionResult:
        """Save a book description to the database."""
        with get_connection() as conn:
            book = fetch_book_detail(conn, book_id)
            if book is None:
                raise HTTPException(status_code=404, detail="Book not found.")
            update_book_description(conn, book_id, payload.description)
        return BookDescriptionResult(book_id=book_id, description=payload.description)

    @router.delete("/books/{book_id}/description", response_model=BookDescriptionResult)
    def clear_description(book_id: int) -> BookDescriptionResult:
        """Clear a book description from the database."""
        with get_connection() as conn:
            book = fetch_book_detail(conn, book_id)
            if book is None:
                raise HTTPException(status_code=404, detail="Book not found.")
            update_book_description(conn, book_id, None)
        return BookDescriptionResult(book_id=book_id, description=None)

    return router
