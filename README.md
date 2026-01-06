# Book Site V2

Simple audiobook library UI powered by FastAPI, Jinja2 templates, and SQLite.

## Architecture

- FastAPI backend serves JSON endpoints and HTML pages.
- Jinja2 templates render server-side views under `app/templates`.
- SQLite (`library.db`) stores authors, books, tags, and file metadata.
- Static assets are served from `app/static`.

## High-level flow

1. `POST /scan` indexes library files into SQLite.
2. `GET /ui/*` routes query SQLite and render templates.
3. Tag-driven recommendations filter books via tag prefixes.

## Tech stack

- FastAPI (Python)
- Jinja2 templates
- SQLite
