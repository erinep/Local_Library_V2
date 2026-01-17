from __future__ import annotations

"""Provider registry for selecting metadata sources."""

from .providers.base import MetadataProvider
from .providers.google_books import GoogleBooksProvider
from .providers.llm_provider import LlmProvider


class DefaultMetadataProvider:
    """Single metadata provider with fixed dependencies."""

    def __init__(
        self,
        search_provider: GoogleBooksProvider | None = None,
        llm_provider: LlmProvider | None = None,
    ) -> None:
        self._search_provider = search_provider or GoogleBooksProvider()
        self._llm_provider = llm_provider or LlmProvider()

    def search(self, author: str, title: str):
        return self._search_provider.search(author=author, title=title)

    def get_tags(self, result_id: str):
        return self._search_provider.get_tags(result_id)

    def clean_description(
        self,
        description: str,
        include_reasoning: bool = False,
        include_schema: bool = False,
    ):
        return self._llm_provider.clean_description(
            description=description,
            include_reasoning=include_reasoning,
            include_schema=include_schema,
        )

    def tag_inference(
        self,
        book_description: str,
        include_reasoning: bool = False,
        include_schema: bool = False,
    ):
        return self._llm_provider.tag_inference(
            book_description=book_description,
            include_reasoning=include_reasoning,
            include_schema=include_schema,
        )


def get_default_provider() -> MetadataProvider:
    """Return the default metadata provider used by app/main.py."""
    return DefaultMetadataProvider()
