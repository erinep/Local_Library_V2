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
    categories: list[str] = []
    description: str | None = None
    source: str | None = None
    identity_score: float | None = None
    overall_confidence: float | None = None
    desc_score: float | None = None


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
    description: str | None = None
    source: str | None = None
    description_rewritten: bool = False
    raw_description: str | None = None


class MetadataAiCleanRequest(BaseModel):
    title: str | None = None
    author: str | None = None
    description: str | None = None


class MetadataAiStep(BaseModel):
    action: str
    reasoning: str | None = None


class MetadataAiCleanResult(BaseModel):
    description: str | None = None
    tags: list[str]
    steps: list[MetadataAiStep]


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


class BulkMetadataJobCreateResult(BaseModel):
    job_id: int
    status: str
    total_books: int


class BulkMetadataJobStatus(BaseModel):
    job_id: int
    status: str
    total_books: int
    processed_books: int
    succeeded_books: int
    failed_books: int
    current_book_id: int | None = None
    last_error: str | None = None
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    cancelled_at: float | None = None
