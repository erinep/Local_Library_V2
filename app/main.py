from __future__ import annotations


from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import iter_files, load_config
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

app = FastAPI(title="Audiobook Library Backend")
_books_provider = get_default_provider()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _urlencode(value: object) -> str:
    if value is None:
        return ""
    return quote_plus(str(value))


templates.env.filters["urlencode"] = urlencode_value

TAG_NAMESPACE_CONFIG = [
    {"tag_prefix": "Genre", "query_param": "genre", "ui_label": "Genre"},                 # Fantasy, Sci-Fi, Mystery, Thriller, 
    {"tag_prefix": "Reader", "query_param": "reader", "ui_label": "Reader"},              # Commerical Fiction, Literay Ficiton, Young Adult, Middle Grade, Classics, Popular Non-Ficion, Academy/Scientific
    {"tag_prefix": "Romance", "query_param": "romance", "ui_label": "Romance"},           # Main, Subplot, None
    {"tag_prefix": "Setting", "query_param": "setting", "ui_label": "Setting"},           # Historical, Contemporary
    {"tag_prefix": "Commitment", "query_param": "commitment", "ui_label": "Commitment"},  # Standalone, Series (Sequential), Series (Episodic)
]
TAG_NAMESPACE_LIST = [entry["tag_prefix"] for entry in TAG_NAMESPACE_CONFIG]


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
    )
)
app.include_router(
    build_ui_router(
        templates=templates,
        get_connection=get_connection,
        get_dashboard_data=lambda: get_dashboard_data(get_connection),
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
