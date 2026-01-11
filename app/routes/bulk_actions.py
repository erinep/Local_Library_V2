from __future__ import annotations

import csv
import io
import json
import re
import unicodedata

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from ..schemas import BookTagSummary, BulkTagImportResult, BulkTaggingResult


def _parse_tag_columns(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in stripped.split(",") if part.strip()]


def _strip_bracketed(value: str) -> str:
    previous = None
    cleaned = value
    patterns = [r"\([^)]*\)", r"\[[^\]]*\]", r"\{[^}]*\}", r"<[^>]*>"]
    while previous != cleaned:
        previous = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, " ", cleaned)
    return cleaned


def _fold_to_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_title(value: str | None) -> str | None:
    if not value:
        return None
    text = _fold_to_ascii(value)
    text = _strip_bracketed(text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(vol|volume|book|part|series)\.?\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(#|no\.?|number)\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\"'`~!@#$%^*_=+|\\/;:,?.-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text or None


def _normalize_author(value: str | None) -> str | None:
    if not value:
        return None
    text = _fold_to_ascii(value)
    text = _strip_bracketed(text)
    if "," in text:
        last, rest = [part.strip() for part in text.split(",", 1)]
        if rest:
            text = f"{rest} {last}"
    text = text.replace("&", " and ")
    text = re.sub(r"[\"'`~!@#$%^*_=+|\\/;:,?.-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text or None


def build_bulk_actions_router(
    *,
    get_connection,
    log_activity,
    ActivityEvent,
    clean_unused_tags,
    clear_all_tags,
    clear_database,
    init_db,
    get_or_create_tag,
    add_tags_to_book,
    TAG_NAMESPACE_LIST,
) -> APIRouter:
    router = APIRouter()

    @router.get("/bulk-actions/books", response_model=list[BookTagSummary])
    def bulk_actions_books() -> list[BookTagSummary]:
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

    @router.get("/bulk-actions/export")
    def bulk_actions_export() -> Response:
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

    @router.post("/bulk-actions/cleanup-tags")
    def bulk_actions_cleanup_tags() -> dict[str, int]:
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

    @router.post("/bulk-actions/clear-tags")
    def bulk_actions_clear_tags() -> dict[str, int]:
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

    @router.post("/bulk-actions/clear-database")
    def bulk_actions_clear_database() -> dict[str, str]:
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

    @router.post("/bulk-actions/normalize-authors")
    def bulk_actions_normalize_authors() -> dict[str, int]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name
                FROM authors
                ORDER BY id
                """
            ).fetchall()
            updated = 0
            for row in rows:
                normalized = _normalize_author(row["name"])
                conn.execute(
                    """
                    UPDATE authors
                    SET normalized_author = ?
                    WHERE id = ?
                    """,
                    (normalized, row["id"]),
                )
                updated += 1
            conn.commit()
            log_activity(
                conn,
                ActivityEvent.NORMALIZE_AUTHORS,
                f"normalized {updated} authors",
                metadata={"authors": updated},
                source="normalize_authors",
            )
        return {"normalized": updated}

    @router.post("/bulk-actions/normalize-titles")
    def bulk_actions_normalize_titles() -> dict[str, int]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title
                FROM books
                ORDER BY id
                """
            ).fetchall()
            updated = 0
            for row in rows:
                normalized = _normalize_title(row["title"])
                conn.execute(
                    """
                    UPDATE books
                    SET normalized_title = ?
                    WHERE id = ?
                    """,
                    (normalized, row["id"]),
                )
                updated += 1
            conn.commit()
            log_activity(
                conn,
                ActivityEvent.NORMALIZE_TITLES,
                f"normalized {updated} titles",
                metadata={"books": updated},
                source="normalize_titles",
            )
        return {"normalized": updated}

    @router.post("/bulk-actions/complete")
    def bulk_actions_complete(payload: BulkTaggingResult) -> dict[str, int | None | str]:
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

    @router.post("/bulk-actions/import-tags", response_model=BulkTagImportResult)
    async def bulk_actions_import_tags(
        file: UploadFile = File(...),
        book_id_column: str = Form(...),
        tag_columns: str = Form(...),
    ) -> BulkTagImportResult:
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
            column for column in _parse_tag_columns(tag_columns)
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

                exists = conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
                if not exists:
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
