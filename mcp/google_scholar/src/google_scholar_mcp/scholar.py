from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import islice
from threading import Lock
from typing import Any

from scholarly2 import scholarly

from .models import AuthorProfile, Paper


class ScholarError(RuntimeError):
    """An actionable failure while retrieving data from Google Scholar."""


class ScholarService:
    """Serialize access to the blocking, process-global scholarly2 client."""

    def __init__(self) -> None:
        self._lock = Lock()

    def search_papers(
        self,
        query: str,
        author: str | None,
        year_from: int | None,
        year_to: int | None,
        limit: int,
    ) -> list[Paper]:
        _validate_search(query, year_from, year_to, limit)
        scholar_query = _query_with_author(query, author)
        try:
            with self._lock:
                search_options: dict[str, Any] = {
                    "patents": False,
                    "citations": False,
                }
                if year_from is not None:
                    search_options["year_low"] = year_from
                if year_to is not None:
                    search_options["year_high"] = year_to
                results = scholarly.search_pubs(
                    scholar_query,
                    **search_options,
                )
                return [_paper(item) for item in islice(results, limit)]
        except Exception as error:
            raise ScholarError(_error_message(error)) from error

    def get_author(self, scholar_id: str, publications_limit: int) -> AuthorProfile:
        normalized_id = scholar_id.strip()
        if not normalized_id:
            raise ValueError("scholar_id must not be blank")
        if not 1 <= publications_limit <= 20:
            raise ValueError("publications_limit must be between 1 and 20")
        try:
            with self._lock:
                record = scholarly.search_author_id(
                    normalized_id,
                    filled=True,
                    publication_limit=publications_limit,
                )
            return _author(record, normalized_id, publications_limit)
        except Exception as error:
            raise ScholarError(_error_message(error)) from error


def _validate_search(
    query: str,
    year_from: int | None,
    year_to: int | None,
    limit: int,
) -> None:
    if not query.strip():
        raise ValueError("query must not be blank")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if year_from is not None and not 1000 <= year_from <= 9999:
        raise ValueError("year_from must be a four-digit year")
    if year_to is not None and not 1000 <= year_to <= 9999:
        raise ValueError("year_to must be a four-digit year")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must not be later than year_to")


def _query_with_author(query: str, author: str | None) -> str:
    if author is None or not author.strip():
        return query.strip()
    escaped_author = author.strip().replace('"', "")
    return f'{query.strip()} author:"{escaped_author}"'


def _paper(value: Mapping[str, Any]) -> Paper:
    bibliography = _mapping(value.get("bib"))
    return Paper(
        title=_text(bibliography.get("title")) or "Untitled publication",
        authors=_texts(bibliography.get("author")),
        year=_year(bibliography.get("pub_year")),
        venue=_text(bibliography.get("venue")) or _text(bibliography.get("journal")),
        abstract=_text(bibliography.get("abstract")),
        cited_by=_non_negative_int(value.get("num_citations")),
        publication_url=_text(value.get("pub_url")),
        eprint_url=_text(value.get("eprint_url")),
        author_ids=_texts(value.get("author_id")),
    )


def _author(
    value: Mapping[str, Any], scholar_id: str, publications_limit: int
) -> AuthorProfile:
    publications = _sequence(value.get("publications"))
    return AuthorProfile(
        scholar_id=_text(value.get("scholar_id")) or scholar_id,
        name=_text(value.get("name")) or "Unknown author",
        affiliation=_text(value.get("affiliation")),
        interests=_texts(value.get("interests")),
        homepage=_text(value.get("homepage")),
        cited_by=_non_negative_int(value.get("citedby")),
        hindex=_non_negative_int(value.get("hindex")),
        i10index=_non_negative_int(value.get("i10index")),
        publications=tuple(
            _paper(item)
            for item in publications[:publications_limit]
            if isinstance(item, Mapping)
        ),
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return ()


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _texts(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    return tuple(text for item in _sequence(value) if (text := _text(item)) is not None)


def _year(value: Any) -> int | None:
    year = _non_negative_int(value)
    return year if year is not None and 1000 <= year <= 9999 else None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _error_message(error: Exception) -> str:
    message = str(error).strip()
    lower = message.lower()
    if "captcha" in lower or "robot" in lower or "blocked" in lower:
        return (
            "Google Scholar blocked the request. Wait before retrying or configure "
            "a proxy."
        )
    if "rate" in lower and "limit" in lower:
        return "Google Scholar rate-limited the request. Wait before retrying."
    if message:
        return f"Google Scholar request failed: {message}"
    return "Google Scholar request failed without an error message."
