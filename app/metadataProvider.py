from __future__ import annotations

"""Provider registry for selecting metadata sources."""

from .providers.base import MetadataProvider
from .providers.google_books import GoogleBooksProvider


def get_default_provider() -> MetadataProvider:
    """Return the default metadata provider used by app/main.py."""
    return GoogleBooksProvider()
