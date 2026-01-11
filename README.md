# Book Site V2

Simple audiobook library UI powered by FastAPI, Jinja2 templates, and SQLite.

This project is a local-first media library system for managing and recommending books, primarily audiobooks, stored on a local file system. It scans an existing library, builds a relational database, and uses that data to support tag-based search and recommendations.

## High-level flow

At a high level, the system consists of the following components:

- Library Ingestion
- Relational database
- Tag-driven search and recommendations tools
- Bulk data management workflows

## Library Ingestion

The local file system is treated as the source of truth.

While scanning a new library, the system:

- Recursively scans directories defined in `library_roots`
- Indexes files matching `allowed_extensions`
- Infers authors and titles from directory structure
- Checks for existing entries in the database
- Creates a new entry for the author and/or book if not found

The folder containing media files must be the book title. The parent folder is treated as the author name. Expected file layout:

```text
root/
├── Author Name/
│ ├── Book Title/
│ │ ├── file1.ext
│ │ ├── file2.ext
│ │ └── ...
│ └── Another Book/
│ └── ...
└── Another Author/
└── Book Title/
└── ...
```

## Database

The backend uses SQLite as a lightweight relational store.

Core relationships include:

- authors → books
- books → files
- books → tags (many-to-many via join tables)

Tags are stored as normalized records and linked to books through join tables. This allows tags to be added, removed, or replaced independently of book records.

## 3. Tag-driven Search and Recommendations

All tags are stored internally using a `namespace:value` format.

Namespaces determine how tags are interpreted and how they participate in filtering, clustering, and recommendation scoring.

### Constrained Namespaces

Some namespaces are intentionally limited and controlled. These are used for structured clustering and higher-weight recommendation signals.

Examples include:

- `Genre:*`
- `Reader:*`
- `Setting:*`
- `ReadingExperience:*`

### Topics Namespace

The `topics:*` namespace is open-ended.

- It supports an unbounded set of descriptors
- It is intended for long-tail thematic tagging

Topic tags are lower-weight individually and are primarily useful in aggregate. This separation allows structured clustering via constrained namespaces while retaining detailed thematic information through topics.

## 4. Bulk Metadata Tools

Bulk operations are supported to allow large-scale changes to the tag map.

### Export

The system can export a CSV snapshot of the library containing:

- book ID
- title
- author
- one column per namespace

The exported file is intended for editing in spreadsheet tools.

### Tag Import

Edited CSV files can be re-imported to apply bulk updates.

- Each tag namespace is processed independently
- Empty cells leave existing tags unchanged
- Non-empty cells replace all tags within that namespace

This supports iterative refinement of tags and large-scale restructuring without manual per-book edits.

## System Configuration

System behavior is controlled through a `config.json` file.

```json
{
  "library_roots": ["<path to library scan>"],
  "allowed_extensions": ["<file types to include on scan>"],
  "ignore_patterns": ["<files or folders to ignore>"],
  "db_name": "<optional; defaults to library.db>"
}
```

## Architecture Reference

See `ARCHITECTURE.md` for API endpoints, database helpers, and testing guidance.