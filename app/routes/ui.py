from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse


def build_ui_router(
    *,
    templates,
    get_connection,
    get_dashboard_data,
    get_book_tags,
    add_tags_to_book,
    remove_tag_from_book,
    get_or_create_tag,
    log_activity,
    ActivityEvent,
    split_tags,
    normalize_search,
    format_bytes,
    TAG_NAMESPACE_CONFIG,
    TAG_NAMESPACE_LIST,
) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    def ui_dashboard(request: Request):
        totals, formatted_activity = get_dashboard_data()
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "totals": totals, "issues": [], "activity": formatted_activity},
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
        return templates.TemplateResponse(
            "bulk_actions.html",
            {"request": request, "tag_namespaces": TAG_NAMESPACE_LIST},
        )

    @router.get("/summary")
    def ui_summary() -> dict[str, object]:
        totals, formatted_activity = get_dashboard_data()
        return {"totals": dict(totals), "activity": formatted_activity}

    @router.get("/recommendations")
    def ui_recommendations(request: Request):
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
        namespace_inputs = {
            entry["query_param"]: _parse_int_list(query_params.getlist(entry["query_param"]))
            for entry in TAG_NAMESPACE_CONFIG
        }
        namespace_filters = {
            entry["tag_prefix"]: _unique_ids(namespace_inputs[entry["query_param"]])
            for entry in TAG_NAMESPACE_CONFIG
        }
        topic_ids = _unique_ids(_parse_int_list(query_params.getlist("topic_id")))
        with get_connection() as conn:
            tag_rows = conn.execute(
                """
                SELECT id, name
                FROM tags
                WHERE name LIKE '%:%'
                ORDER BY name
                """
            ).fetchall()
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

            selected_tag_ids = [tag_id for ids in namespace_filters.values() for tag_id in ids]
            selected_tag_ids.extend(topic_ids)

            if selected_tag_ids:
                placeholders = ", ".join("?" for _ in selected_tag_ids)
                having_clauses: list[str] = []
                params: list[object] = [*selected_tag_ids]
                for ids in namespace_filters.values():
                    if not ids:
                        continue
                    namespace_placeholders = ", ".join("?" for _ in ids)
                    having_clauses.append(
                        f"SUM(CASE WHEN bt.tag_id IN ({namespace_placeholders}) THEN 1 ELSE 0 END) > 0"
                    )
                    params.extend(ids)
                if topic_ids:
                    topic_placeholders = ", ".join("?" for _ in topic_ids)
                    having_clauses.append(
                        f"SUM(CASE WHEN bt.tag_id IN ({topic_placeholders}) THEN 1 ELSE 0 END) > 0"
                    )
                    params.extend(topic_ids)

                rows = conn.execute(
                    f"""
                    SELECT
                        b.id,
                        b.title,
                        a.name AS author,
                        (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
                    FROM books b
                    LEFT JOIN authors a ON a.id = b.author_id
                    INNER JOIN book_tags bt ON bt.book_id = b.id
                    WHERE bt.tag_id IN ({placeholders})
                    GROUP BY b.id
                    HAVING {' AND '.join(having_clauses)}
                    ORDER BY a.name, b.title
                    """,
                    params,
                ).fetchall()
            else:
                rows = []

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
        author_name = None
        tag_name = None
        search_term = normalize_search(q)
        with get_connection() as conn:
            if author_id is not None and tag_id is not None:
                rows = []
            else:
                if author_id is not None:
                    author_row = conn.execute(
                        "SELECT name FROM authors WHERE id = ?",
                        (author_id,),
                    ).fetchone()
                    author_name = author_row["name"] if author_row else None
                if tag_id is not None:
                    tag_row = conn.execute(
                        "SELECT name FROM tags WHERE id = ?",
                        (tag_id,),
                    ).fetchone()
                    tag_name = tag_row["name"] if tag_row else None

                joins = []
                where_clauses = []
                params: list[object] = []
                if tag_id is not None:
                    joins.append("INNER JOIN book_tags bt ON bt.book_id = b.id")
                    where_clauses.append("bt.tag_id = ?")
                    params.append(tag_id)
                if author_id is not None:
                    where_clauses.append("b.author_id = ?")
                    params.append(author_id)
                if search_term:
                    where_clauses.append("(b.title LIKE ? OR a.name LIKE ?)")
                    like_term = f"%{search_term}%"
                    params.extend([like_term, like_term])

                join_sql = "\n                ".join(joins)
                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                order_by = "ORDER BY b.title" if author_id is not None else "ORDER BY a.name, b.title"

                rows = conn.execute(
                    f"""
                    SELECT
                        b.id,
                        b.title,
                        a.name AS author,
                        (SELECT COUNT(*) FROM files f WHERE f.book_id = b.id) AS file_count
                    FROM books b
                    LEFT JOIN authors a ON a.id = b.author_id
                    {join_sql}
                    {where_sql}
                    {order_by}
                    """,
                    params,
                ).fetchall()
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
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    (SELECT COUNT(*) FROM books b WHERE b.author_id = a.id) AS book_count
                FROM authors a
                ORDER BY a.name
                """
            ).fetchall()
        return templates.TemplateResponse(
            "authors.html",
            {"request": request, "authors": rows},
        )

    @router.get("/tags")
    def ui_tags(request: Request):
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.id,
                    t.name,
                    (SELECT COUNT(*) FROM book_tags bt WHERE bt.tag_id = t.id) AS book_count
                FROM tags t
                WHERE t.name NOT LIKE 'topic:%'
                ORDER BY t.name
                """
            ).fetchall()
        return templates.TemplateResponse(
            "tags.html",
            {"request": request, "tags": rows},
        )

    @router.get("/topics")
    def ui_topics(request: Request):
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    t.id,
                    t.name,
                    (SELECT COUNT(*) FROM book_tags bt WHERE bt.tag_id = t.id) AS book_count
                FROM tags t
                WHERE t.name LIKE 'topic:%'
                ORDER BY t.name
                """
            ).fetchall()
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
        with get_connection() as conn:
            book = conn.execute(
                """
                SELECT
                    b.id,
                    b.title,
                    b.path,
                    a.name AS author,
                    b.author_id AS author_id
                FROM books b
                LEFT JOIN authors a ON a.id = b.author_id
                WHERE b.id = ?
                """,
                (book_id,),
            ).fetchone()
            tags = get_book_tags(conn, book_id)
            files = conn.execute(
                """
                SELECT path, size_bytes, modified_time
                FROM files
                WHERE book_id = ?
                ORDER BY path
                """,
                (book_id,),
            ).fetchall()
        if book is None:
            return Response(status_code=404)
        return templates.TemplateResponse(
            "book_detail.html",
            {
                "request": request,
                "book": book,
                "tags": [tag for tag in tags if not str(tag["name"]).lower().startswith("topic:")],
                "topics": [
                    {
                        "id": tag["id"],
                        "name": tag["name"],
                        "display_name": str(tag["name"]).split(":", 1)[1].strip()
                        if ":" in str(tag["name"])
                        else tag["name"],
                    }
                    for tag in tags
                    if str(tag["name"]).lower().startswith("topic:")
                ],
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
