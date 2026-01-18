from __future__ import annotations

import json
import time
from typing import Any

from dotenv import load_dotenv

from ..config import get_inference_order
from ..db import add_tags_to_book, get_connection, get_or_create_tag, remove_non_topic_tags_from_book
from ..metadataProvider import get_default_provider
from ..services.db_queries import (
    fetch_books_for_metadata,
    fetch_book_detail,
    update_book_description,
    update_book_raw_description,
)
from ..services.metadata_scoring import confidence_score

load_dotenv()


def create_metadata_job(conn, total_books: int) -> int:
    cur = conn.execute(
        """
        INSERT INTO metadata_jobs (status, total_books, created_at)
        VALUES (?, ?, ?)
        """,
        ("queued", total_books, time.time()),
    )
    conn.commit()
    return int(cur.lastrowid)


def fetch_metadata_job(conn, job_id: int) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT
            id,
            status,
            total_books,
            processed_books,
            succeeded_books,
            failed_books,
            current_book_id,
            last_error,
            created_at,
            started_at,
            finished_at,
            cancelled_at
        FROM metadata_jobs
        WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "job_id": int(row["id"]),
        "status": row["status"],
        "total_books": int(row["total_books"]),
        "processed_books": int(row["processed_books"]),
        "succeeded_books": int(row["succeeded_books"]),
        "failed_books": int(row["failed_books"]),
        "current_book_id": int(row["current_book_id"]) if row["current_book_id"] is not None else None,
        "last_error": row["last_error"],
        "created_at": float(row["created_at"]),
        "started_at": float(row["started_at"]) if row["started_at"] is not None else None,
        "finished_at": float(row["finished_at"]) if row["finished_at"] is not None else None,
        "cancelled_at": float(row["cancelled_at"]) if row["cancelled_at"] is not None else None,
    }


def fetch_active_metadata_job(conn) -> dict[str, object] | None:
    row = conn.execute(
        """
        SELECT id
        FROM metadata_jobs
        WHERE status IN ('queued', 'running')
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return fetch_metadata_job(conn, int(row["id"]))


def update_metadata_job(conn, job_id: int, **fields: object) -> None:
    if not fields:
        return
    columns = []
    values = []
    for key, value in fields.items():
        columns.append(f"{key} = ?")
        values.append(value)
    values.append(job_id)
    conn.execute(
        f"""
        UPDATE metadata_jobs
        SET {", ".join(columns)}
        WHERE id = ?
        """,
        values,
    )
    conn.commit()


def create_metadata_job_event(
    conn,
    job_id: int,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> None:
    payload_text = json.dumps(payload or {}, ensure_ascii=True)
    conn.execute(
        """
        INSERT INTO metadata_job_events (job_id, event_type, payload, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (job_id, event_type, payload_text, time.time()),
    )
    conn.commit()


def fetch_metadata_job_events(conn, job_id: int, after_id: int = 0) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT id, event_type, payload, created_at
        FROM metadata_job_events
        WHERE job_id = ? AND id > ?
        ORDER BY id
        """,
        (job_id, after_id),
    ).fetchall()
    events: list[dict[str, object]] = []
    for row in rows:
        payload = {}
        raw_payload = row["payload"]
        if isinstance(raw_payload, str) and raw_payload:
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                payload = {}
        events.append(
            {
                "id": int(row["id"]),
                "event_type": row["event_type"],
                "payload": payload,
                "created_at": float(row["created_at"]),
            }
        )
    return events


def cancel_metadata_job(conn, job_id: int) -> bool:
    row = conn.execute(
        "SELECT status FROM metadata_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return False
    if row["status"] in ("completed", "failed", "cancelled"):
        return True
    update_metadata_job(
        conn,
        job_id,
        status="cancelled",
        cancelled_at=time.time(),
    )
    return True


def _job_is_cancelled(conn, job_id: int) -> bool:
    row = conn.execute(
        "SELECT status FROM metadata_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    return row is not None and row["status"] == "cancelled"


def _extract_volume_info(raw_payload: object) -> dict[str, object]:
    if isinstance(raw_payload, dict):
        volume = raw_payload.get("volumeInfo", {})
        if isinstance(volume, dict):
            return volume
    return {}


def _normalize_search_results(results: list[object], title: str, author: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for result in results:
        volume = _extract_volume_info(getattr(result, "raw_payload", None))
        categories = volume.get("categories")
        if not isinstance(categories, list):
            categories = []
        description = volume.get("description") if isinstance(volume.get("description"), str) else None
        confidence_product, desc_score, identity_score = confidence_score(
            query_title=title,
            query_author=author,
            candidate_title=getattr(result, "title", None),
            candidate_author=getattr(result, "author", None),
            description=description,
        )
        normalized.append(
            {
                "result_id": getattr(result, "result_id", ""),
                "title": getattr(result, "title", None),
                "author": getattr(result, "author", None),
                "categories": [str(item) for item in categories],
                "description": description,
                "source": "google_books",
                "overall_confidence": confidence_product,
                "identity_score": identity_score,
                "desc_score": desc_score,
            }
        )
    return normalized


def _select_best_result(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not results:
        return None
    best = results[0]
    best_score = best.get("overall_confidence")
    best_score = best_score if isinstance(best_score, (int, float)) else -1.0
    for result in results[1:]:
        score = result.get("overall_confidence")
        score = score if isinstance(score, (int, float)) else -1.0
        if score > best_score:
            best_score = score
            best = result
    return best


def _prepare_metadata(provider, result: dict[str, Any]) -> tuple[list[str], str]:
    categories = result.get("categories") or []
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
    result_id = result.get("result_id")
    if result_id:
        try:
            tag_candidates = provider.get_tags(result_id)
        except Exception:
            tag_candidates = []
        for tag in tag_candidates:
            tag_text = str(getattr(tag, "tag_text", "")).strip()
            if not tag_text:
                continue
            key = tag_text.lower()
            if key in seen:
                continue
            seen.add(key)
            topics.append(tag_text)
    description = result.get("description") or ""
    return topics, description


def _build_tags_from_mapping(tag_mapping: dict[str, object]) -> list[str]:
    tags: list[str] = []
    for key, value in tag_mapping.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        if isinstance(value, list):
            for item in value:
                value_text = str(item).strip()
                if value_text:
                    tags.append(f"{key_text}:{value_text}")
            continue
        value_text = str(value).strip()
        if value_text:
            tags.append(f"{key_text}:{value_text}")
    return tags


def _run_ai_cleanup(provider, description: str) -> tuple[str, list[str]]:
    raw_description = description or ""
    cleaned = raw_description
    tags: list[str] = []
    tag_mapping: dict[str, object] = {}
    tag_prompt_lookup = {field: prompt for field, prompt in provider.get_tag_inference_fields()}

    def resolve_field(step_name: str) -> str | None:
        field_key = step_name.replace("tag_inference_", "").replace("_", "").lower()
        for candidate in tag_prompt_lookup:
            if candidate.replace("_", "").lower() == field_key:
                return candidate
        return None

    for step in get_inference_order():
        if step == "description_clean":
            cleaned_result, _ = provider.clean_description(
                description=cleaned,
                include_reasoning=False,
            )
            if cleaned_result:
                cleaned = cleaned_result
        elif step == "tag_inference":
            tags, _ = provider.tag_inference_split(raw_description, include_reasoning=False)
        elif step.startswith("tag_inference_"):
            field = resolve_field(step)
            if not field:
                continue
            prompt_name = tag_prompt_lookup.get(field)
            if not prompt_name:
                continue
            value, _ = provider.tag_inference_field(
                raw_description,
                field=field,
                prompt_name=prompt_name,
                include_reasoning=False,
            )
            tag_mapping[field] = value
            tags = _build_tags_from_mapping(tag_mapping)
    return cleaned, tags


def _apply_metadata(
    conn,
    book_id: int,
    *,
    tags: list[str],
    description: str | None,
    raw_description: str | None,
    source: str | None,
) -> None:
    remove_non_topic_tags_from_book(conn, book_id)
    tag_ids: list[int] = []
    for tag_text in tags:
        cleaned = " ".join(str(tag_text).split())
        if not cleaned:
            continue
        tag_id, _ = get_or_create_tag(conn, cleaned)
        if tag_id is not None:
            tag_ids.append(tag_id)
    add_tags_to_book(conn, book_id, tag_ids)
    if source == "google_books" and raw_description:
        update_book_raw_description(conn, book_id, raw_description)
    if description is not None:
        update_book_description(conn, book_id, description)


def _process_book(
    conn,
    provider,
    book_id: int,
    title: str,
    author: str,
) -> tuple[bool, str | None, dict[str, object] | None]:
    results = provider.search(author=author, title=title) or []
    if not isinstance(results, list):
        results = list(results)
    normalized = _normalize_search_results(results, title, author)
    best = _select_best_result(normalized)
    if not best:
        return False, "No metadata results.", None
    base_tags, prepared_description = _prepare_metadata(provider, best)
    raw_description = prepared_description or best.get("description") or ""
    try:
        cleaned_description, ai_tags = _run_ai_cleanup(provider, raw_description)
    except Exception as exc:
        return False, f"AI cleanup failed: {exc}", best
    merged_tags = list({*base_tags, *ai_tags})
    final_description = cleaned_description or raw_description or None
    _apply_metadata(
        conn,
        book_id,
        tags=merged_tags,
        description=final_description,
        raw_description=raw_description,
        source=best.get("source") or "google_books",
    )
    return True, None, best


def run_metadata_job(job_id: int) -> None:
    provider = get_default_provider()
    try:
        with get_connection() as conn:
            job = fetch_metadata_job(conn, job_id)
            if job is None:
                return
            if job["status"] == "cancelled":
                update_metadata_job(conn, job_id, finished_at=time.time())
                return

            update_metadata_job(conn, job_id, status="running", started_at=time.time())

            rows = fetch_books_for_metadata(conn)
            total_books = len(rows)
            if total_books != job["total_books"]:
                update_metadata_job(conn, job_id, total_books=total_books)

            processed = 0
            succeeded = 0
            failed = 0

            for row in rows:
                if _job_is_cancelled(conn, job_id):
                    update_metadata_job(
                        conn,
                        job_id,
                        status="cancelled",
                        finished_at=time.time(),
                        current_book_id=None,
                    )
                    return

                book_id = int(row["id"])
                raw_title = row["title"] or ""
                raw_author = row["author"] or ""
                title = row["normalized_title"] or raw_title
                author = row["normalized_author"] or raw_author
                update_metadata_job(conn, job_id, current_book_id=book_id)

                try:
                    if fetch_book_detail(conn, book_id) is None:
                        raise RuntimeError("Book not found.")
                    ok, error_message, selected = _process_book(conn, provider, book_id, title, author)
                    if not ok:
                        failed += 1
                        update_metadata_job(conn, job_id, last_error=error_message)
                        create_metadata_job_event(
                            conn,
                            job_id,
                            "book_failed",
                            {
                                "book_id": book_id,
                                "title": raw_title,
                                "author": raw_author,
                                "error": error_message,
                                "selected": selected,
                                "processed": processed + 1,
                                "succeeded": succeeded,
                                "failed": failed,
                            },
                        )
                    else:
                        succeeded += 1
                        create_metadata_job_event(
                            conn,
                            job_id,
                            "book_completed",
                            {
                                "book_id": book_id,
                                "title": raw_title,
                                "author": raw_author,
                                "selected": selected,
                                "processed": processed + 1,
                                "succeeded": succeeded,
                                "failed": failed,
                            },
                        )
                except Exception as exc:
                    failed += 1
                    update_metadata_job(conn, job_id, last_error=str(exc))
                    create_metadata_job_event(
                        conn,
                        job_id,
                        "book_failed",
                        {
                            "book_id": book_id,
                            "title": raw_title,
                            "author": raw_author,
                            "error": str(exc),
                            "processed": processed + 1,
                            "succeeded": succeeded,
                            "failed": failed,
                        },
                    )

                processed += 1
                update_metadata_job(
                    conn,
                    job_id,
                    processed_books=processed,
                    succeeded_books=succeeded,
                    failed_books=failed,
                )

            update_metadata_job(
                conn,
                job_id,
                status="completed",
                finished_at=time.time(),
                current_book_id=None,
            )
    except Exception as exc:
        with get_connection() as conn:
            update_metadata_job(
                conn,
                job_id,
                status="failed",
                finished_at=time.time(),
                last_error=str(exc),
                current_book_id=None,
            )
