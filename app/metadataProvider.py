from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TagCandidate:
    tag_text: str
    tag_type: str | None = None
    confidence: float | None = None
    source_url: str | None = None
    provider_key: str | None = None


@dataclass(frozen=True)
class SearchResult:
    result_id: str
    title: str | None = None
    author: str | None = None
    raw_payload: dict[str, object] | None = None
    tags: list[TagCandidate] | None = None


def _build_query(author: str, title: str) -> str:
    parts: list[str] = []
    if title:
        parts.append(f"intitle:{title}")
    if author:
        parts.append(f"inauthor:{author}")
    return " ".join(parts)


class GoogleBooksProvider:
    def __init__(self, api_key: str | None = None, max_results: int = 10, timeout: float = 10.0) -> None:
        self.api_key = os.getenv("GOOGLE_BOOKS_API_KEY")
        self.max_results = max_results
        self.timeout = timeout

    def search(self, author: str, title: str) -> list[SearchResult]:
        query = _build_query(author, title)
        if not query:
            return []
        params = {
            "q": query,
            "maxResults": str(self.max_results),
        }
        if self.api_key:
            params["key"] = self.api_key
        url = f"https://www.googleapis.com/books/v1/volumes?{urlencode(params)}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError):
            return []
        items = payload.get("items", []) or []
        results: list[SearchResult] = []
        for item in items:
            volume = item.get("volumeInfo", {}) if isinstance(item, dict) else {}
            result_id = item.get("id") if isinstance(item, dict) else None
            if not result_id:
                continue
            title_value = volume.get("title") if isinstance(volume, dict) else None
            authors = volume.get("authors") if isinstance(volume, dict) else None
            author_value = ", ".join(authors) if isinstance(authors, list) else None
            results.append(
                SearchResult(
                    result_id=str(result_id),
                    title=title_value,
                    author=author_value,
                    raw_payload={"volumeInfo": volume},
                )
            )
        return results

    def get_tags(self, result_id: str) -> list[TagCandidate]:
        return []
