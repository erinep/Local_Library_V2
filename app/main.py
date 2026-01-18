from __future__ import annotations


from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from .config import (
    get_inference_order,
    get_tag_namespace_config,
    get_tag_namespace_list,
    iter_files,
    load_config,
)
from .db import (
    add_tags_to_book,
    clean_unused_tags,
    ActivityEvent,
    clear_all_tags,
    clear_database,
    get_connection,
    get_or_create_author,
    get_or_create_book,
    get_or_create_tag,
    init_db,
    remove_non_topic_tags_from_book,
    remove_tag_from_book,
    upsert_files,
)
from .metadataProvider import get_default_provider
from .routes.api import build_api_router
from .routes.bulk_actions import build_bulk_actions_router
from .routes.ui import build_ui_router
from .services.db_queries import log_activity
from .services.ingest import infer_book_id
from .services.ui_helpers import get_dashboard_data, urlencode_value

load_dotenv()

app = FastAPI(title="Audiobook Library Backend")
_books_provider = get_default_provider()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _urlencode(value: object) -> str:
    if value is None:
        return ""
    return quote_plus(str(value))


templates.env.filters["urlencode"] = urlencode_value


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and "text/html" in request.headers.get("accept", ""):
        return templates.TemplateResponse(
            "404.html",
            {"request": request},
            status_code=404,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

TAG_NAMESPACE_CONFIG = get_tag_namespace_config()
TAG_NAMESPACE_LIST = get_tag_namespace_list(TAG_NAMESPACE_CONFIG)


@app.on_event("startup")
def startup() -> None:
    with get_connection() as conn:
        init_db(conn)


app.include_router(
    build_api_router(
        books_provider=_books_provider,
        load_config=load_config,
        iter_files=iter_files,
        get_connection=get_connection,
        upsert_files=upsert_files,
        log_activity=log_activity,
        ActivityEvent=ActivityEvent,
        infer_book_id=lambda *args, **kwargs: infer_book_id(
            *args,
            **kwargs,
            get_or_create_author=get_or_create_author,
            get_or_create_book=get_or_create_book,
        ),
        get_or_create_tag=get_or_create_tag,
        add_tags_to_book=add_tags_to_book,
        remove_non_topic_tags_from_book=remove_non_topic_tags_from_book,
        get_inference_order=get_inference_order,
    )
)
app.include_router(
    build_ui_router(
        templates=templates,
        get_connection=get_connection,
        get_dashboard_data=lambda: get_dashboard_data(get_connection, TAG_NAMESPACE_CONFIG),
        add_tags_to_book=add_tags_to_book,
        remove_tag_from_book=remove_tag_from_book,
        get_or_create_tag=get_or_create_tag,
        ActivityEvent=ActivityEvent,
        TAG_NAMESPACE_CONFIG=TAG_NAMESPACE_CONFIG,
        TAG_NAMESPACE_LIST=TAG_NAMESPACE_LIST,
    )
)
app.include_router(
    build_bulk_actions_router(
        get_connection=get_connection,
        ActivityEvent=ActivityEvent,
        clean_unused_tags=clean_unused_tags,
        clear_all_tags=clear_all_tags,
        clear_database=clear_database,
        init_db=init_db,
        get_or_create_tag=get_or_create_tag,
        add_tags_to_book=add_tags_to_book,
        TAG_NAMESPACE_LIST=TAG_NAMESPACE_LIST,
    )
)
