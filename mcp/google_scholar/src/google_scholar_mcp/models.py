from __future__ import annotations

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """A stable, compact view of a Google Scholar publication result."""

    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    cited_by: int | None = Field(default=None, ge=0)
    publication_url: str | None = None
    eprint_url: str | None = None
    author_ids: tuple[str, ...] = ()


class AuthorProfile(BaseModel):
    """A stable, compact view of a Google Scholar author profile."""

    scholar_id: str
    name: str
    affiliation: str | None = None
    interests: tuple[str, ...] = ()
    homepage: str | None = None
    cited_by: int | None = Field(default=None, ge=0)
    hindex: int | None = Field(default=None, ge=0)
    i10index: int | None = Field(default=None, ge=0)
    publications: tuple[Paper, ...] = ()
