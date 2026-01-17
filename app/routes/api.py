from __future__ import annotations

from datetime import datetime
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas import (
    BookDescriptionResult,
    BookDescriptionUpdate,
    MetadataApplyRequest,
    MetadataApplyResult,
    MetadataAiCleanRequest,
    MetadataAiCleanResult,
    MetadataAiStep,
    MetadataPrepareRequest,
    MetadataPrepareResult,
    MetadataSearchRequest,
    MetadataSearchResult,
    ScanResult,
)
from ..services.db_queries import (
    fetch_book_detail,
    update_book_description,
    update_book_raw_description,
)


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
    get_or_create_tag,
    add_tags_to_book,
    remove_non_topic_tags_from_book,
    get_inference_order,
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

    @router.post("/books/{book_id}/metadata/search", response_model=list[MetadataSearchResult])
    def metadata_search(book_id: int, payload: MetadataSearchRequest) -> list[MetadataSearchResult]:
        """Search external metadata sources for a book."""
        title = payload.title or ""
        author = payload.author or ""
        results = books_provider.search(author=author, title=title)
        response: list[MetadataSearchResult] = []
        for result in results[:5]:
            volume = {}
            if isinstance(result.raw_payload, dict):
                volume = result.raw_payload.get("volumeInfo", {}) or {}
            published_date = volume.get("publishedDate") if isinstance(volume, dict) else None
            published_year = None
            if isinstance(published_date, str) and published_date:
                published_year = published_date[:4]
            categories = volume.get("categories") if isinstance(volume, dict) else None
            if not isinstance(categories, list):
                categories = []
            isbn10 = None
            isbn13 = None
            identifiers = volume.get("industryIdentifiers") if isinstance(volume, dict) else None
            if isinstance(identifiers, list):
                for identifier in identifiers:
                    if not isinstance(identifier, dict):
                        continue
                    id_type = identifier.get("type")
                    id_value = identifier.get("identifier")
                    if not isinstance(id_type, str) or not isinstance(id_value, str):
                        continue
                    if id_type == "ISBN_10" and not isbn10:
                        isbn10 = id_value
                    elif id_type == "ISBN_13" and not isbn13:
                        isbn13 = id_value
            description = volume.get("description") if isinstance(volume, dict) else None
            if not isinstance(description, str):
                description = None
            response.append(
                MetadataSearchResult(
                    result_id=result.result_id,
                    title=result.title,
                    author=result.author,
                    published_year=published_year,
                    isbn10=isbn10,
                    isbn13=isbn13,
                    categories=[str(item) for item in categories],
                    description=description,
                    source="google_books",
                )
            )
        return response

    @router.post("/books/{book_id}/metadata/prepare", response_model=MetadataPrepareResult)
    def metadata_prepare(book_id: int, payload: MetadataPrepareRequest) -> MetadataPrepareResult:
        """Prepare external metadata for review."""
        title = payload.title or ""
        author = payload.author or ""
        description = payload.description or ""
        categories = payload.categories or []
        topics: list[str] = []
        seen: set[str] = set()
        for raw in categories:
            if not raw:
                continue
            parts = [part.strip() for part in str(raw).replace(">", "/").split("/") if part.strip()]
            for part in parts:
                key = f"topic:{part}".lower()
                if key in seen:
                    continue
                seen.add(key)
                topics.append(f"topic:{part}")
        if payload.result_id:
            tag_candidates = books_provider.get_tags(payload.result_id)
            for tag in tag_candidates:
                tag_text = str(tag.tag_text).strip()
                if not tag_text:
                    continue
                key = tag_text.lower()
                if key in seen:
                    continue
                seen.add(key)
                topics.append(tag_text)
        return MetadataPrepareResult(
            tags=topics,
            description=description or None,
        )

    @router.post("/books/{book_id}/metadata/apply", response_model=MetadataApplyResult)
    def metadata_apply(book_id: int, payload: MetadataApplyRequest) -> MetadataApplyResult:
        """Apply reviewed metadata to a book."""
        with get_connection() as conn:
            book = fetch_book_detail(conn, book_id)
            if book is None:
                raise HTTPException(status_code=404, detail="Book not found.")
            remove_non_topic_tags_from_book(conn, book_id)
            tag_ids: list[int] = []
            for tag_text in payload.tags:
                cleaned = " ".join(str(tag_text).split())
                if not cleaned:
                    continue
                tag_id, _ = get_or_create_tag(conn, cleaned)
                if tag_id is not None:
                    tag_ids.append(tag_id)
            added = add_tags_to_book(conn, book_id, tag_ids)
            description_updated = False
            if payload.source == "google_books" and payload.raw_description:
                update_book_raw_description(conn, book_id, payload.raw_description)
            if payload.description is not None:
                update_book_description(conn, book_id, payload.description)
                description_updated = True
        return MetadataApplyResult(tags_added=added, description_updated=description_updated)

    @router.post("/books/{book_id}/metadata/ai_clean", response_model=MetadataAiCleanResult)
    def metadata_ai_clean(
        book_id: int,
        payload: MetadataAiCleanRequest,
    ) -> MetadataAiCleanResult:
        """Run AI clean/tag inference in configured order."""
        title = payload.title or ""
        author = payload.author or ""
        description = payload.description or ""
        tags: list[str] = []
        steps: list[MetadataAiStep] = []
        for step in get_inference_order():
            if step == "description_clean":
                cleaned, reasoning = books_provider.clean_description(
                    description=description,
                    include_reasoning=True,
                )
                if cleaned:
                    description = cleaned
                steps.append(MetadataAiStep(action="description_clean", reasoning=reasoning))
            elif step == "tag_inference":
                tags, reasoning = books_provider.tag_inference(description, include_reasoning=True)
                steps.append(MetadataAiStep(action="tag_inference", reasoning=reasoning))
        return MetadataAiCleanResult(description=description or None, tags=tags, steps=steps)

    @router.post("/books/{book_id}/metadata/ai_clean/stream")
    def metadata_ai_clean_stream(
        book_id: int,
        payload: MetadataAiCleanRequest,
    ) -> StreamingResponse:
        """Stream AI clean/tag inference steps in configured order."""
        title = payload.title or ""
        author = payload.author or ""
        description = payload.description or ""

        def _send_event(event: str, data: dict[str, object]) -> bytes:
            payload_text = json.dumps(data, ensure_ascii=True)
            return f"event: {event}\ndata: {payload_text}\n\n".encode("utf-8")

        def _generate():
            nonlocal description
            try:
                yield _send_event("ping", {"status": "started"})
                for step in get_inference_order():
                    if step == "description_clean":
                        yield _send_event("step_start", {"action": "description_clean"})
                        cleaned, reasoning = books_provider.clean_description(
                            description=description,
                            include_reasoning=True,
                        )
                        if cleaned:
                            description = cleaned
                        yield _send_event(
                            "step_result",
                            {
                                "action": "description_clean",
                                "description": description,
                                "reasoning": reasoning,
                            },
                        )
                    elif step == "tag_inference":
                        yield _send_event("step_start", {"action": "tag_inference"})
                        tags, reasoning = books_provider.tag_inference(description, include_reasoning=True)
                        yield _send_event(
                            "step_result",
                            {
                                "action": "tag_inference",
                                "tags": tags,
                                "reasoning": reasoning,
                            },
                        )
                yield _send_event("done", {"status": "ok"})
            except HTTPException as exc:
                yield _send_event(
                    "error",
                    {"status": exc.status_code, "detail": str(exc.detail)},
                )
            except Exception as exc:  # pragma: no cover - defensive for streaming
                yield _send_event("error", {"status": 500, "detail": str(exc)})

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(_generate(), media_type="text/event-stream", headers=headers)

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
