# Architecture

This document summarizes the current backend structure, HTTP endpoints, and core data flow.

## Tech stack
- FastAPI backend serving JSON and HTML.
- Jinja2 templates in `app/templates`.
- SQLite storage (`library.db`).
- Static assets in `app/static`.

## Core modules
- Provider wiring: `app/metadataProvider.py` (DefaultMetadataProvider).
- LLM integration: `app/providers/llm_provider.py`.
- Google Books integration: `app/providers/google_books.py`.
- API routes: `app/routes/api.py`.
- UI routes: `app/routes/ui.py`.
- Bulk actions: `app/routes/bulk_actions.py`.
- DB + schema: `app/db.py`.
- Shared services: `app/services/*`.

## Data model (SQLite)
- `authors` -> `books` via `books.author_id`.
- `books` -> `tags` via `book_tags`.
- `books` -> `files` via `files.book_id`.
- Activity log in `activity_log`.

## Metadata flow
- Search and tag enrichment uses Google Books.
- Description cleaning and tag inference use the LLM provider.
- AI clean supports a synchronous JSON endpoint and a streaming SSE endpoint.

## API endpoints (JSON)
- POST `/scan` -- Scan library roots and index files.
- POST `/books/{book_id}/metadata/search` -- Search metadata provider.
- POST `/books/{book_id}/metadata/prepare` -- Normalize metadata for review.
- POST `/books/{book_id}/metadata/apply` -- Apply reviewed metadata to DB.
- POST `/books/{book_id}/metadata/ai_clean` -- Run AI clean + tag inference.
- POST `/books/{book_id}/metadata/ai_clean/stream` -- Stream AI clean steps (SSE).
- POST `/books/{book_id}/description` -- Save description override.
- DELETE `/books/{book_id}/description` -- Clear description override.

## Bulk actions (JSON)
- GET `/bulk-actions/export` -- Export books/tags as CSV.
- POST `/bulk-actions/cleanup-tags` -- Remove unused tags.
- POST `/bulk-actions/clear-tags` -- Remove all tags and links.
- POST `/bulk-actions/clear-database` -- Drop/recreate schema.
- POST `/bulk-actions/import-tags` -- Import tags from CSV.

## UI pages (HTML)
- GET `/` -- Dashboard.
- GET `/bulk-actions` -- Bulk actions UI.
- GET `/summary` -- Dashboard summary JSON.
- GET `/recommendations` -- Recommendations page.
- GET `/books` -- Books list.
- GET `/books/{book_id}` -- Book detail page.
- GET `/authors` -- Authors list.
- GET `/tags` -- Tags list (non-topic).
- GET `/topics` -- Topics list.
- GET `/favicon.ico` -- Favicon.

## UI form actions (HTML)
- POST `/tags` -- Create topic tags.
- POST `/books/{book_id}/tags` -- Add topic tags to a book.
- POST `/books/{book_id}/tags/{tag_id}/remove` -- Remove a tag from a book.

## Key service helpers (services/db_queries.py)
- Dashboard: `fetch_dashboard_totals`, `fetch_recent_activity`.
- Books/tags: `fetch_books`, `fetch_book_detail`, `get_book_tags`.
- Recommendations: `fetch_tag_rows_for_recommendations`, `fetch_recommendation_books`.
- Bulk actions: `fetch_bulk_export_rows`.
- Normalization: `fetch_authors_for_normalization`, `fetch_books_for_normalization`,
  `update_normalized_author`, `update_normalized_title`.
