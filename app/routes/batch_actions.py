from __future__ import annotations

"""Batch-action routes for tag management, normalization, and CSV workflows."""

import csv
import io
import time

import json
import time as _time

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse

from ..queue import get_queue
from ..services.db_queries import (
    book_exists,
    fetch_bulk_export_rows,
    fetch_books_for_metadata,
    log_activity,
)
from ..services.ingest import parse_tag_columns
from ..schemas import (
    BulkMetadataJobCreateResult,
    BulkMetadataJobStatus,
    BulkTagImportResult,
)
from ..services.metadata_jobs import (
    cancel_metadata_job,
    create_metadata_job,
    fetch_active_metadata_job,
    fetch_metadata_job,
    fetch_metadata_job_events,
    run_metadata_job,
    update_metadata_job,
)

def build_batch_actions_router(
    *,
    get_connection,
    ActivityEvent,
    clean_unused_tags,
    clear_all_tags,
    clear_database,
    init_db,
    get_or_create_tag,
    add_tags_to_book,
    TAG_NAMESPACE_LIST,
) -> APIRouter:
    """Create the batch-actions router and wire handlers to injected services."""
    router = APIRouter()

    @router.get("/batch-actions/export")
    def batch_actions_export() -> Response:
        """Export library data with tags as a CSV download."""
        with get_connection() as conn:
            rows = fetch_bulk_export_rows(conn)
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
                source="batch_actions_export",
            )
        return Response(content=output.getvalue(), media_type="text/csv", headers=headers)

    @router.get("/batch-actions/metadata/books")
    def batch_actions_metadata_books() -> list[dict[str, object]]:
        """Return basic book info for batch metadata workflows."""
        with get_connection() as conn:
            rows = fetch_books_for_metadata(conn)
        return [
            {
                "id": int(row["id"]),
                "title": row["title"],
                "author": row["author"] or "",
            }
            for row in rows
        ]

    @router.post("/batch-actions/metadata/jobs", response_model=BulkMetadataJobCreateResult)
    def batch_metadata_job_start() -> BulkMetadataJobCreateResult:
        """Queue a batch metadata processing job."""
        with get_connection() as conn:
            active = fetch_active_metadata_job(conn)
            if active:
                raise HTTPException(status_code=409, detail="Batch metadata job already running.")
            rows = fetch_books_for_metadata(conn)
            job_id = create_metadata_job(conn, len(rows))
            log_activity(
                conn,
                ActivityEvent.BULK_METADATA_JOB_CREATED,
                f"batch metadata job {job_id} queued",
                metadata={"job_id": job_id, "total_books": len(rows)},
                source="batch_metadata_job_start",
            )
        queue = get_queue()
        try:
            queue.enqueue(run_metadata_job, job_id, job_id=str(job_id))
        except Exception as exc:
            with get_connection() as conn:
                update_metadata_job(
                    conn,
                    job_id,
                    status="failed",
                    finished_at=time.time(),
                    last_error=str(exc),
                )
            raise HTTPException(status_code=500, detail="Failed to enqueue job.") from exc
        return BulkMetadataJobCreateResult(job_id=job_id, status="queued", total_books=len(rows))

    @router.get("/batch-actions/metadata/jobs/{job_id}", response_model=BulkMetadataJobStatus)
    def batch_metadata_job_status(job_id: int) -> BulkMetadataJobStatus:
        """Fetch the status of a batch metadata job."""
        with get_connection() as conn:
            job = fetch_metadata_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Metadata job not found.")
        return BulkMetadataJobStatus(**job)

    @router.get("/batch-actions/metadata/jobs/{job_id}/stream")
    def batch_metadata_job_stream(job_id: int) -> StreamingResponse:
        """Stream job updates (per-book events + status changes)."""
        def _send(event: str, data: dict[str, object]) -> bytes:
            payload_text = json.dumps(data, ensure_ascii=True)
            return f"event: {event}\ndata: {payload_text}\n\n".encode("utf-8")

        def _generate():
            last_event_id = 0
            last_status = None
            while True:
                with get_connection() as conn:
                    job = fetch_metadata_job(conn, job_id)
                    if job is None:
                        yield _send("error", {"detail": "Metadata job not found."})
                        return
                    status = job["status"]
                    if status != last_status:
                        last_status = status
                        yield _send("status", {"status": status, "job": job})
                    for event in fetch_metadata_job_events(conn, job_id, after_id=last_event_id):
                        last_event_id = event["id"]
                        yield _send(event["event_type"], event)
                    if status in ("completed", "failed", "cancelled"):
                        yield _send("done", {"status": status})
                        return
                _time.sleep(1.0)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        return StreamingResponse(_generate(), media_type="text/event-stream", headers=headers)

    @router.delete("/batch-actions/metadata/jobs/{job_id}", response_model=BulkMetadataJobStatus)
    def batch_metadata_job_cancel(job_id: int) -> BulkMetadataJobStatus:
        """Cancel a batch metadata job."""
        with get_connection() as conn:
            exists = cancel_metadata_job(conn, job_id)
            if not exists:
                raise HTTPException(status_code=404, detail="Metadata job not found.")
            job = fetch_metadata_job(conn, job_id)
            if job and job["status"] == "cancelled":
                log_activity(
                    conn,
                    ActivityEvent.BULK_METADATA_JOB_CANCELLED,
                    f"batch metadata job {job_id} cancelled",
                    metadata={"job_id": job_id},
                    source="batch_metadata_job_cancel",
                )
        if job is None:
            raise HTTPException(status_code=404, detail="Metadata job not found.")
        return BulkMetadataJobStatus(**job)

    @router.post("/batch-actions/cleanup-tags")
    def batch_actions_cleanup_tags() -> dict[str, int]:
        """Remove orphaned tags with no book associations."""
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

    @router.post("/batch-actions/clear-tags")
    def batch_actions_clear_tags() -> dict[str, int]:
        """Delete all tags and book-tag relationships."""
        with get_connection() as conn:
            removed_links, removed_tags = clear_all_tags(conn)
            log_activity(
                conn,
                ActivityEvent.CLEAR_ALL_TAGS,
                "all tags cleared",
                metadata={"removed_links": removed_links, "removed_tags": removed_tags},
                source="clear_tags",
            )
        return {"removed_links": removed_links, "removed_tags": removed_tags}

    @router.post("/batch-actions/clear-database")
    def batch_actions_clear_database() -> dict[str, str]:
        """Drop and recreate the database schema."""
        with get_connection() as conn:
            clear_database(conn)
            init_db(conn)
            log_activity(
                conn,
                ActivityEvent.CLEAR_DATABASE,
                "database cleared",
                source="clear_database",
            )
        return {"status": "cleared"}

    @router.post("/batch-actions/import-tags", response_model=BulkTagImportResult)
    async def batch_actions_import_tags(
        file: UploadFile = File(...),
        book_id_column: str = Form(...),
        tag_columns: str = Form(...),
    ) -> BulkTagImportResult:
        """Import tags from CSV using column-to-namespace mapping."""
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="CSV file is empty.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.") from exc

        reader = csv.reader(io.StringIO(text))
        headers = next(reader, None)
        if not headers:
            raise HTTPException(status_code=400, detail="CSV file is missing a header row.")

        cleaned_headers = [header.strip() for header in headers]
        header_lookup = {header.lower(): idx for idx, header in enumerate(cleaned_headers) if header}
        book_key = book_id_column.strip().lower()
        if book_key not in header_lookup:
            raise HTTPException(status_code=400, detail="Book ID column not found in headers.")
        book_id_index = header_lookup[book_key]

        selected_columns = [
            column for column in parse_tag_columns(tag_columns)
            if column.strip().lower() != book_key
        ]
        if not selected_columns:
            raise HTTPException(status_code=400, detail="Select at least one tag column.")

        namespace_lookup = {name.lower() for name in TAG_NAMESPACE_LIST}
        namespace_lookup.add("topic")
        invalid_namespaces = [
            name for name in selected_columns if name.strip().lower() not in namespace_lookup
        ]
        if invalid_namespaces:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tag namespaces: {', '.join(invalid_namespaces)}",
            )

        tag_indices: list[tuple[int, str]] = []
        for column in selected_columns:
            key = column.strip().lower()
            if key not in header_lookup:
                raise HTTPException(status_code=400, detail=f"Tag column missing: {column}")
            tag_indices.append((header_lookup[key], cleaned_headers[header_lookup[key]]))

        rows_processed = 0
        books_updated = 0
        tags_added = 0
        invalid_rows = 0
        missing_book_ids: set[int] = set()
        tag_cache: dict[str, int] = {}

        with get_connection() as conn:
            for row in reader:
                if not row or book_id_index >= len(row):
                    invalid_rows += 1
                    continue
                raw_id = row[book_id_index].strip()
                if not raw_id:
                    invalid_rows += 1
                    continue
                try:
                    book_id = int(raw_id)
                except ValueError:
                    invalid_rows += 1
                    continue

                if not book_exists(conn, book_id):
                    missing_book_ids.add(book_id)
                    continue

                tag_names: set[str] = set()
                for index, namespace in tag_indices:
                    if index >= len(row):
                        continue
                    cell_value = row[index].strip()
                    if not cell_value:
                        continue
                    for value in cell_value.split(","):
                        cleaned_value = value.strip()
                        if not cleaned_value:
                            continue
                        tag_names.add(f"{namespace}:{cleaned_value}")

                if not tag_names:
                    rows_processed += 1
                    continue

                tag_ids: list[int] = []
                for tag_name in sorted(tag_names):
                    tag_id = tag_cache.get(tag_name)
                    if tag_id is None:
                        tag_id, _ = get_or_create_tag(conn, tag_name)
                        if tag_id is None:
                            continue
                        tag_cache[tag_name] = tag_id
                    tag_ids.append(tag_id)

                added = add_tags_to_book(conn, book_id, tag_ids)
                if added:
                    books_updated += 1
                    tags_added += added
                rows_processed += 1

            log_activity(
                conn,
                ActivityEvent.BULK_TAG_IMPORT,
                f"Imported tags for {books_updated} books",
                metadata={
                    "rows_processed": rows_processed,
                    "books_updated": books_updated,
                    "tags_added": tags_added,
                    "missing_book_ids": sorted(missing_book_ids),
                    "invalid_rows": invalid_rows,
                    "namespaces": selected_columns,
                },
                source="bulk_tag_import",
            )

        return BulkTagImportResult(
            status="completed",
            rows_processed=rows_processed,
            books_updated=books_updated,
            tags_added=tags_added,
            missing_book_ids=sorted(missing_book_ids),
            invalid_rows=invalid_rows,
        )

    return router
