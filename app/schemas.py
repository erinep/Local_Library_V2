from pydantic import BaseModel


class ScanResult(BaseModel):
    indexed: int
    scanned_at: str


class BookSearchResult(BaseModel):
    result_id: str
    title: str | None = None
    author: str | None = None


class TagCandidateResult(BaseModel):
    tag_text: str


class BookTagSummary(BaseModel):
    book_id: int
    title: str
    author: str | None = None
    normalized_title: str | None = None
    normalized_author: str | None = None
    tags: list[str]


class BulkTaggingResult(BaseModel):
    status: str
    processed: int | None = None
    total: int | None = None


class BulkTagImportResult(BaseModel):
    status: str
    rows_processed: int
    books_updated: int
    tags_added: int
    missing_book_ids: list[int]
    invalid_rows: int
