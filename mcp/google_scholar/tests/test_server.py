from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from google_scholar_mcp import server
from google_scholar_mcp.models import AuthorProfile, Paper


class FakeService:
    def search_papers(
        self,
        query: str,
        author: str | None,
        year_from: int | None,
        year_to: int | None,
        limit: int,
    ) -> list[Paper]:
        return [Paper(title=query, authors=(author,) if author else ())]

    def get_author(self, scholar_id: str, publications_limit: int) -> AuthorProfile:
        return AuthorProfile(scholar_id=scholar_id, name="Ada Lovelace")


def test_mcp_exposes_and_calls_both_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_scholar", FakeService())

    async def call_tools() -> None:
        async with Client(server.mcp) as client:
            listed_tools = await client.list_tools()
            assert {tool.name for tool in listed_tools.tools} == {
                "search_papers",
                "get_author",
            }

            papers = await client.call_tool(
                "search_papers", {"query": "algorithms", "author": "Ada Lovelace"}
            )
            assert papers.structured_content == {
                "result": [
                    {
                        "title": "algorithms",
                        "authors": ["Ada Lovelace"],
                        "year": None,
                        "venue": None,
                        "abstract": None,
                        "cited_by": None,
                        "publication_url": None,
                        "eprint_url": None,
                        "author_ids": [],
                    }
                ]
            }

            author = await client.call_tool("get_author", {"scholar_id": "Ada123"})
            assert author.structured_content == {
                "scholar_id": "Ada123",
                "name": "Ada Lovelace",
                "affiliation": None,
                "interests": [],
                "homepage": None,
                "cited_by": None,
                "hindex": None,
                "i10index": None,
                "publications": [],
            }

    asyncio.run(call_tools())
