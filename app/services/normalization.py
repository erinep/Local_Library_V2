from __future__ import annotations

import re
import unicodedata


def strip_bracketed(value: str) -> str:
    """Remove bracketed text for normalization in app/routes/bulk_actions.py."""
    previous = None
    cleaned = value
    patterns = [r"\([^)]*\)", r"\[[^\]]*\]", r"\{[^}]*\}", r"<[^>]*>"]
    while previous != cleaned:
        previous = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, " ", cleaned)
    return cleaned


def fold_to_ascii(value: str) -> str:
    """Fold unicode strings to ASCII for normalization in app/routes/bulk_actions.py."""
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_title(value: str | None) -> str | None:
    """Normalize titles for bulk actions in app/routes/bulk_actions.py."""
    if not value:
        return None
    text = fold_to_ascii(value)
    text = strip_bracketed(text)
    text = text.replace("&", " and ")
    text = re.sub(r"\b(vol|volume|book|part|series)\.?\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(#|no\.?|number)\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[\"'`~!@#$%^*_=+|\\/;:,?.-]", " ", text)
    text = re.sub(r"^\s*\d+\s+", " ", text)
    text = re.sub(r"\s+\d+\s*$", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text or None


def normalize_author(value: str | None) -> str | None:
    """Normalize author names for bulk actions in app/routes/bulk_actions.py."""
    if not value:
        return None
    text = fold_to_ascii(value)
    text = strip_bracketed(text)
    if "," in text:
        last, rest = [part.strip() for part in text.split(",", 1)]
        if rest:
            text = f"{rest} {last}"
    text = text.replace("&", " and ")
    text = re.sub(r"[\"'`~!@#$%^*_=+|\\/;:,?.-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text or None
