from __future__ import annotations

from .normalization import normalize_author, normalize_title

TARGET_DESC_LEN = 800.0


def _tokenize(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part for part in value.split() if part}


def author_similarity(query: str | None, candidate: str | None) -> float:
    query_norm = normalize_author(query)
    cand_norm = normalize_author(candidate)
    query_tokens = _tokenize(query_norm)
    cand_tokens = _tokenize(cand_norm)
    if not query_tokens or not cand_tokens:
        return 0.0
    overlap = query_tokens.intersection(cand_tokens)
    union = query_tokens.union(cand_tokens)
    return len(overlap) / len(union)


def title_token_overlap(query: str | None, candidate: str | None) -> float:
    query_norm = normalize_title(query)
    cand_norm = normalize_title(candidate)
    query_tokens = _tokenize(query_norm)
    cand_tokens = _tokenize(cand_norm)
    if not query_tokens or not cand_tokens:
        return 0.0
    overlap = query_tokens.intersection(cand_tokens)
    return len(overlap) / len(query_tokens)


def desc_score(description: str | None, target_len: float = TARGET_DESC_LEN) -> float:
    if not description:
        return 0.0
    return min(len(description) / target_len, 1.0)


def confidence_score(
    *,
    query_title: str | None,
    query_author: str | None,
    candidate_title: str | None,
    candidate_author: str | None,
    description: str | None,
) -> tuple[float, float]:
    author_score = author_similarity(query_author, candidate_author)
    title_score = title_token_overlap(query_title, candidate_title)
    identity_score = (author_score + title_score) / 2.0
    description_score = desc_score(description)
    return identity_score * description_score, description_score, identity_score
