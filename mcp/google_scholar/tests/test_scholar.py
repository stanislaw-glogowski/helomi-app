from __future__ import annotations

import pytest

from google_scholar_mcp import scholar as scholar_module
from google_scholar_mcp.scholar import ScholarError, ScholarService


class FakeScholar:
    def __init__(self) -> None:
        self.search_arguments: dict[str, object] | None = None
        self.author_arguments: dict[str, object] | None = None

    def search_pubs(self, query: str, **kwargs: object) -> object:
        self.search_arguments = {"query": query, **kwargs}
        return iter(
            [
                {
                    "bib": {
                        "title": "A paper",
                        "author": ["Ada Lovelace"],
                        "pub_year": "2024",
                        "venue": "Journal of Tests",
                    },
                    "num_citations": "12",
                    "pub_url": "https://example.test/paper",
                    "eprint_url": "https://example.test/paper.pdf",
                    "author_id": ["Ada123"],
                }
            ]
        )

    def search_author_id(self, identifier: str, **kwargs: object) -> object:
        self.author_arguments = {"identifier": identifier, **kwargs}
        return {
            "scholar_id": identifier,
            "name": "Ada Lovelace",
            "affiliation": "Analytical Engine",
            "interests": ["Mathematics"],
            "citedby": 42,
            "hindex": 3,
            "i10index": 2,
            "publications": [
                {
                    "bib": {
                        "title": "Notes",
                        "author": ["Ada Lovelace"],
                        "pub_year": "1843",
                    }
                }
            ],
        }


def test_search_papers_normalizes_results_and_applies_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeScholar()
    monkeypatch.setattr(scholar_module, "scholarly", fake)

    papers = ScholarService().search_papers("algorithms", "Ada Lovelace", 2020, 2025, 3)

    assert fake.search_arguments == {
        "query": 'algorithms author:"Ada Lovelace"',
        "patents": False,
        "citations": False,
        "year_low": 2020,
        "year_high": 2025,
    }
    assert papers[0].model_dump() == {
        "title": "A paper",
        "authors": ("Ada Lovelace",),
        "year": 2024,
        "venue": "Journal of Tests",
        "abstract": None,
        "cited_by": 12,
        "publication_url": "https://example.test/paper",
        "eprint_url": "https://example.test/paper.pdf",
        "author_ids": ("Ada123",),
    }


@pytest.mark.parametrize(
    ("query", "year_from", "year_to", "limit", "message"),
    [
        ("   ", None, None, 5, "query must not be blank"),
        ("tests", 2025, 2020, 5, "year_from must not be later than year_to"),
        ("tests", None, None, 21, "limit must be between 1 and 20"),
    ],
)
def test_search_papers_rejects_invalid_arguments(
    query: str,
    year_from: int | None,
    year_to: int | None,
    limit: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ScholarService().search_papers(query, None, year_from, year_to, limit)


def test_get_author_normalizes_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeScholar()
    monkeypatch.setattr(scholar_module, "scholarly", fake)

    author = ScholarService().get_author("Ada123", 5)

    assert fake.author_arguments == {
        "identifier": "Ada123",
        "filled": True,
        "publication_limit": 5,
    }
    assert author.name == "Ada Lovelace"
    assert author.publications[0].title == "Notes"


def test_search_papers_translates_captcha_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockedScholar:
        def search_pubs(self, query: str, **kwargs: object) -> object:
            raise RuntimeError("CAPTCHA required")

    monkeypatch.setattr(scholar_module, "scholarly", BlockedScholar())

    with pytest.raises(ScholarError, match="blocked the request"):
        ScholarService().search_papers("algorithms", None, None, None, 5)
