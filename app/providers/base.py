from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TagCandidate:
    """Represents a normalized tag suggestion from a metadata provider."""
    tag_text: str


@dataclass(frozen=True)
class SearchResult:
    """Represents a single provider search result with optional raw payload."""
    result_id: str
    title: str | None = None
    author: str | None = None
    raw_payload: dict[str, object] | None = None
    tags: list[TagCandidate] | None = None


class MetadataProvider(Protocol):
    """Interface for metadata providers used by app/routes/api.py."""

    def search(self, author: str, title: str) -> list[SearchResult]:
        """Search by author/title and return normalized results."""
        raise NotImplementedError

    def get_tags(self, result_id: str) -> list[TagCandidate]:
        """Return tag candidates for a specific result id."""
        raise NotImplementedError

    def get_description(self, title: str, author: str) -> str | None:
        """Return a description for a title/author pair."""
        raise NotImplementedError

    def clean_description(self, title: str, author: str, description: str) -> str | None:
        """Return a cleaned description for a title/author pair."""
        raise NotImplementedError
