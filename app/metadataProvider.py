from __future__ import annotations

"""Provider registry for selecting metadata sources."""

from .providers.base import MetadataProvider
from .providers.google_books import GoogleBooksProvider
from .providers.llm_provider import LlmProvider


class CompositeMetadataProvider:
    """Combine search/tag providers with an LLM description provider."""

    def __init__(self, search_provider, description_provider, cleanup_provider )-> None:
        self._search_provider = search_provider
        self._description_provider = description_provider
        self._cleanup_provider = cleanup_provider

    def search(self, author: str, title: str):
        return self._search_provider.search(author=author, title=title)

    def get_tags(self, result_id: str):
        return self._search_provider.get_tags(result_id)

    def get_description(self, title: str, author: str):
        return self._description_provider.get_description(title=title, author=author)

    def clean_description(self, title: str, author: str, description: str):
        return self._cleanup_provider.clean_description(
            title=title,
            author=author,
            description=description,
        )


def get_default_provider() -> MetadataProvider:
    """Return the default metadata provider used by app/main.py."""
    return CompositeMetadataProvider(
        GoogleBooksProvider(),
        GoogleBooksProvider(),
        LlmProvider(),
    )
