from __future__ import annotations

import asyncio
import logging

from mcp.server import MCPServer

from .models import AuthorProfile, Paper
from .scholar import ScholarError, ScholarService

mcp = MCPServer(
    "Google Scholar",
    description="Search Google Scholar publications and retrieve author profiles.",
    log_level="CRITICAL",
)
_scholar = ScholarService()


@mcp.tool()
async def search_papers(
    query: str,
    author: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 5,
) -> list[Paper]:
    """Search publications by query, with optional author and year filters."""
    try:
        return await asyncio.to_thread(
            _scholar.search_papers, query, author, year_from, year_to, limit
        )
    except (ScholarError, ValueError) as error:
        raise ValueError(str(error)) from error


@mcp.tool()
async def get_author(
    scholar_id: str,
    publications_limit: int = 10,
) -> AuthorProfile:
    """Retrieve a Google Scholar author profile by its stable Scholar ID."""
    try:
        return await asyncio.to_thread(
            _scholar.get_author, scholar_id, publications_limit
        )
    except (ScholarError, ValueError) as error:
        raise ValueError(str(error)) from error


def main() -> None:
    """Run the MCP server over standard input and output."""
    logging.disable(logging.CRITICAL)
    mcp.run(transport="stdio")
