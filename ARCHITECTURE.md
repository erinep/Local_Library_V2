# Design Reference

This document lists the current HTTP endpoints and DB helpers grouped by testing focus.


## Tech stack

- FastAPI backend serves JSON endpoints and HTML pages.
- Jinja2 templates render server-side views under `app/templates`.
- SQLite (`library.db`) stores authors, books, tags, and file metadata.
- Static assets are served from `app/static`.

## System responsibilities
- Metadata providers (`app/metadataProvider.py`, `app/providers/*`) wrap third-party data calls.
- API routes (`app/routes/api.py`) expose third-party lookup endpoints.
- UI routes (`app/routes/ui.py`) render templates and handle form submissions.
- Bulk action routes (`app/routes/bulk_actions.py`) run maintenance workflows.
- Service modules (`app/services/*`) hold shared logic and DB helpers.
- Database schema and core DB utilities live in `app/db.py`.

## Data model
- `authors` links to `books` via `books.author_id`.
- `books` links to `tags` via `book_tags`.
- `files` links to `books` via `files.book_id`.
- Activity log entries live in `activity_log`.

## Background and maintenance workflows
- Library scan indexes files and infers books/authors.
- Bulk tag import applies tags from CSV and logs results.
- Normalization updates `books.normalized_title` and `authors.normalized_author`.
- Cleanup removes unused tags; clear flows reset tags or the whole DB.

## Testing strategy
- Unit tests: service helpers (normalization, parsing, formatting).
- Integration tests: DB helpers + routes (scan/import/normalize).
- Smoke tests: UI flows (bulk actions, CSV import modal, recommendations).

## Library scanning and search (API)
- POST `/scan` -- Scan library roots and index files.
  - Input: none
  - Returns: JSON `{ "indexed": int, "scanned_at": string }`
- GET `/search` -- Search the metadata provider by `title` and/or `author`.
  - Input: query params `title` (optional), `author` (optional); at least one required
  - Returns: JSON array of `{ "result_id": string, "title": string|null, "author": string|null }`
- GET `/search/{result_id}/tags` -- Fetch tag candidates for a search result.
  - Input: path param `result_id`
  - Returns: JSON array of `{ "tag_text": string }`

- POST `/book/{book_id}/metadata/search` -- fetch all metadata for a book
- POST `/book/{book_id}/metadata/prepare` -- preform data clean up on metadata
- POST `/book/{book_id}/metata/clean` -- extra **expensive** clean up operations on the db.
- POST `/book/{book_id}/metadata/apply` -- push the metadata results to the db

## Bulk actions (maintenance workflows)




- GET `/bulk-actions/books` -- List books with authors and tags for bulk tagging.
  - Input: none
  - Returns: JSON array of `{ "book_id": int, "title": string, "author": string|null, "tags": string[] }`
- GET `/bulk-actions/export` -- Download CSV export of books and tags.
  - Input: none
  - Returns: `text/csv` download
- POST `/bulk-actions/cleanup-tags` -- Remove unused tags.
  - Input: none
  - Returns: JSON `{ "removed": int }`
- POST `/bulk-actions/clear-tags` -- Remove all tags and tag links.
  - Input: none
  - Returns: JSON `{ "removed_links": int, "removed_tags": int }`
- POST `/bulk-actions/clear-database` -- Drop and recreate the database schema.
  - Input: none
  - Returns: JSON `{ "status": "cleared" }`
- POST `/bulk-actions/normalize-authors` -- Normalize author names.
  - Input: none
  - Returns: JSON `{ "normalized": int }`
- POST `/bulk-actions/normalize-titles` -- Normalize book titles.
  - Input: none
  - Returns: JSON `{ "normalized": int }`
- POST `/bulk-actions/complete` -- Log bulk tagging completion status.
  - Input: JSON `{ "status": "completed"|"stopped", "processed": int|null, "total": int|null }`
  - Returns: JSON `{ "processed": int|null, "total": int|null, "status": string }`
- POST `/bulk-actions/import-tags` -- Import namespaced tags from CSV.
  - Input: multipart form with `file` (CSV), `book_id_column` (string), `tag_columns` (string or JSON list)
  - Returns: JSON `{ "status": string, "rows_processed": int, "books_updated": int, "tags_added": int, "missing_book_ids": int[], "invalid_rows": int }`

## UI pages (HTML)
- GET `/` -- Dashboard.
  - Input: none
  - Returns: HTML
- GET `/bulk-actions` -- Bulk actions UI.
  - Input: none
  - Returns: HTML
- GET `/summary` -- Dashboard summary (JSON payload for UI polling).
  - Input: none
  - Returns: JSON `{ "totals": object, "activity": object[] }`
- GET `/recommendations` -- Recommendations page.
  - Input: query params from tag filters
  - Returns: HTML
- GET `/books` -- Book list, filterable by query params.
  - Input: query params `author_id` (optional), `tag_id` (optional), `q` (optional)
  - Returns: HTML
- GET `/books/{book_id}` -- Book detail page.
  - Input: path param `book_id`
  - Returns: HTML
- GET `/authors` -- Author list page.
  - Input: none
  - Returns: HTML
- GET `/tags` -- Tag list page (non-topic tags).
  - Input: none
  - Returns: HTML
- GET `/topics` -- Topic list page.
  - Input: none
  - Returns: HTML
- GET `/favicon.ico` -- Favicon.
  - Input: none
  - Returns: icon or 204

## UI form actions (HTML)
- POST `/tags` -- Create topic tags from a comma-separated list.
  - Input: form field `tags` (string)
  - Returns: redirect to `/tags`
- POST `/books/{book_id}/tags` -- Add topic tags to a book.
  - Input: path param `book_id`, form field `tags` (string)
  - Returns: redirect to `/books/{book_id}`
- POST `/books/{book_id}/tags/{tag_id}/remove` -- Remove a tag from a book.
  - Input: path params `book_id`, `tag_id`
  - Returns: redirect to `/books/{book_id}`

## Database helpers (services/db_queries.py)
- `fetch_dashboard_totals` -- Dashboard counts for authors/books/files.
- `fetch_recent_activity` -- Activity log entries for the dashboard.
- `fetch_books_with_authors_and_tags` -- Books joined with authors and tags.
- `fetch_bulk_export_rows` -- Export dataset for CSV generation.
- `fetch_tag_rows_for_recommendations` -- Namespaced tags for filters.
- `fetch_recommendation_books` -- Filtered recommendations by tag IDs.
- `fetch_author_name` -- Author lookup by id.
- `fetch_tag_name` -- Tag lookup by id.
- `fetch_books` -- Books list with optional filters.
- `fetch_authors` -- Authors list with book counts.
- `fetch_tags_with_counts` -- Tags list with counts (topics on/off).
- `fetch_book_detail` -- Book detail lookup.
- `fetch_book_files` -- Files linked to a book.
- `get_book_tags` -- Tags attached to a book.
- `book_exists` -- Existence check by book id.
- `fetch_authors_for_normalization` -- Author list for normalization.
- `fetch_books_for_normalization` -- Book list for normalization.
- `update_normalized_author` -- Persist normalized author value.
- `update_normalized_title` -- Persist normalized title value.
- `log_activity` -- Write an activity log entry.
