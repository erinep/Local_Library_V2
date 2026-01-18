from __future__ import annotations

"""UI routes that render templates and handle form submissions."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse

from ..services.db_queries import (
    fetch_author_name,
    fetch_authors,
    fetch_book_detail,
    fetch_book_files,
    fetch_books,
    fetch_recommendation_books,
    fetch_tag_name,
    fetch_tag_rows_for_recommendations,
    fetch_tags_with_counts,
    get_book_tags,
    log_activity,
)
from ..services.ui_helpers import format_bytes, normalize_search, split_tags


def build_ui_router(
    *,
    templates,
    get_connection,
    get_dashboard_data,
    add_tags_to_book,
    remove_tag_from_book,
    get_or_create_tag,
    ActivityEvent,
    TAG_NAMESPACE_CONFIG,
    TAG_NAMESPACE_LIST,
) -> APIRouter:
    """Create the UI router and bind template handlers to dependencies."""
    router = APIRouter()

    @router.get("/")
    def ui_dashboard(request: Request):
        """Render the dashboard with totals and recent activity."""
        totals, formatted_activity, charts = get_dashboard_data()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "totals": totals,
                "issues": [],
                "activity": formatted_activity,
                "charts": charts,
            },
        )

    @router.get("/favicon.ico")
    def favicon() -> Response:
        """Return the site favicon if present, otherwise a 204 response."""
        favicon_path = Path(__file__).resolve().parents[1] / "static" / "favicon.ico"
        if favicon_path.is_file():
            return FileResponse(favicon_path)
        return Response(status_code=204)

    @router.get("/bulk-actions")
    def ui_bulk_actions(request: Request):
        """Render the bulk-actions page."""
        return templates.TemplateResponse(
            "bulk_actions.html",
            {"request": request, "tag_namespaces": TAG_NAMESPACE_LIST},
        )

    @router.get("/summary")
    def ui_summary() -> dict[str, object]:
        """Return summary data for dashboard polling."""
        totals, formatted_activity, charts = get_dashboard_data()
        return {"totals": dict(totals), "activity": formatted_activity, "charts": charts}

    @router.get("/recommendations")
    def ui_recommendations(request: Request):
        """Render recommendations based on selected tag filters."""
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
        namespace_filters = {
            entry["tag_prefix"]: _unique_ids(
                _parse_int_list(query_params.getlist(entry["tag_prefix"]))
            )
            for entry in TAG_NAMESPACE_CONFIG
        }
        topic_ids = _unique_ids(_parse_int_list(query_params.getlist("topic_id")))
        with get_connection() as conn:
            tag_rows = fetch_tag_rows_for_recommendations(conn)
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

            rows = fetch_recommendation_books(conn, namespace_filters, topic_ids)

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

    @router.get("/books")
    def ui_books(
        request: Request,
        author_id: int | None = None,
        tag_id: int | None = None,
        q: str | None = None,
    ):
        """Render a filtered book list by author, tag, or search term."""
        author_name = None
        tag_name = None
        search_term = normalize_search(q)
        with get_connection() as conn:
            if author_id is not None and tag_id is not None:
                rows = []
            else:
                if author_id is not None:
                    author_name = fetch_author_name(conn, author_id)
                if tag_id is not None:
                    tag_name = fetch_tag_name(conn, tag_id)

                rows = fetch_books(
                    conn,
                    author_id=author_id,
                    tag_id=tag_id,
                    search_term=search_term,
                )
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

    @router.get("/authors")
    def ui_authors(request: Request):
        """Render the authors list with book counts."""
        with get_connection() as conn:
            rows = fetch_authors(conn)
        return templates.TemplateResponse(
            "authors.html",
            {"request": request, "authors": rows},
        )

    @router.get("/tags")
    def ui_tags(request: Request):
        """Render the tag list (excluding topics)."""
        with get_connection() as conn:
            rows = fetch_tags_with_counts(conn, include_topics=False)
        return templates.TemplateResponse(
            "tags.html",
            {"request": request, "tags": rows},
        )

    @router.get("/topics")
    def ui_topics(request: Request):
        """Render the topic list (topic: namespace)."""
        with get_connection() as conn:
            rows = fetch_tags_with_counts(conn, include_topics=True)
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

    @router.post("/tags")
    def ui_add_tags(tags: str = Form(...)) -> RedirectResponse:
        """Create new topic tags from the tags form."""
        tag_names = split_tags(tags)
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
        return RedirectResponse("/tags", status_code=303)

    @router.get("/books/{book_id}")
    def ui_book_detail(request: Request, book_id: int):
        """Render a single book detail page with tags and files."""
        with get_connection() as conn:
            book = fetch_book_detail(conn, book_id)
            tags = get_book_tags(conn, book_id)
            topic_rows = fetch_tags_with_counts(conn, include_topics=True)
            files = fetch_book_files(conn, book_id)
        if book is None:
            return templates.TemplateResponse(
                "404.html",
                {"request": request},
                status_code=404,
            )
        active_topics = [
            {
                "id": tag["id"],
                "name": tag["name"],
                "display_name": str(tag["name"]).split(":", 1)[1].strip()
                if ":" in str(tag["name"])
                else tag["name"],
            }
            for tag in tags
            if str(tag["name"]).lower().startswith("topic:")
        ]
        all_topics = [
            {
                "id": row["id"],
                "name": row["name"],
                "display_name": row["name"].split(":", 1)[1].strip()
                if ":" in row["name"]
                else row["name"],
            }
            for row in topic_rows
        ]
        return templates.TemplateResponse(
            "book_detail.html",
            {
                "request": request,
                "book": book,
                "tags": [tag for tag in tags if not str(tag["name"]).lower().startswith("topic:")],
                "active_topics": active_topics,
                "topics": all_topics,
                "files": [
                    {
                        "path": row["path"],
                        "size": format_bytes(row["size_bytes"]),
                        "modified": datetime.fromtimestamp(row["modified_time"]).isoformat(),
                    }
                    for row in files
                ],
            },
        )

    @router.post("/books/{book_id}/tags")
    def ui_add_book_tags(book_id: int, tags: str = Form(...)) -> RedirectResponse:
        """Attach topic tags to a book and log the update."""
        tag_names = split_tags(tags)
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
        return RedirectResponse(f"/books/{book_id}", status_code=303)

    @router.post("/books/{book_id}/tags/{tag_id}/remove")
    def ui_remove_book_tag(book_id: int, tag_id: int) -> RedirectResponse:
        """Remove a tag from a book and clean up unused tags."""
        with get_connection() as conn:
            removed = remove_tag_from_book(conn, book_id, tag_id)
            log_activity(
                conn,
                ActivityEvent.BOOK_TAGS_UPDATED,
                "tag removed",
                metadata={"book_id": book_id, "tag_id": tag_id, "removed": removed},
                source="remove_book_tag",
            )
        return RedirectResponse(f"/books/{book_id}", status_code=303)

    return router
