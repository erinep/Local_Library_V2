from pydantic import BaseModel


class ScanResult(BaseModel):
    indexed: int
    scanned_at: str


class BookDescriptionResult(BaseModel):
    book_id: int
    description: str | None = None


class BookDescriptionUpdate(BaseModel):
    description: str | None = None


class MetadataSearchRequest(BaseModel):
    title: str | None = None
    author: str | None = None


class MetadataSearchResult(BaseModel):
    result_id: str
    title: str | None = None
    author: str | None = None
    published_year: str | None = None
    isbn10: str | None = None
    isbn13: str | None = None
    maturity_rating: str | None = None
    categories: list[str] = []
    description: str | None = None
    source: str | None = None


class MetadataPrepareRequest(BaseModel):
    result_id: str
    title: str | None = None
    author: str | None = None
    categories: list[str] = []
    description: str | None = None
    source: str | None = None


class MetadataPrepareResult(BaseModel):
    tags: list[str]
    description: str | None = None


class MetadataApplyRequest(BaseModel):
    tags: list[str] = []
    description_choice: str | None = None
    description: str | None = None
    source: str | None = None
    description_rewritten: bool = False


class MetadataCleanRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None


class MetadataCleanResult(BaseModel):
    description: str | None = None


class MetadataApplyResult(BaseModel):
    tags_added: int
    description_updated: bool


class BulkTagImportResult(BaseModel):
    status: str
    rows_processed: int
    books_updated: int
    tags_added: int
    missing_book_ids: list[int]
    invalid_rows: int
