# Google Scholar MCP Server

An isolated stdio [Model Context Protocol](https://modelcontextprotocol.io/)
server for searching Google Scholar publications and retrieving author profiles.
It is designed to be connected from a Helomi profile without changing Helomi.

## Tools

- `search_papers(query, author?, year_from?, year_to?, limit=5)` searches
  publications. `limit` is 1–20; results exclude patents and citation-only rows.
- `get_author(scholar_id, publications_limit=10)` retrieves an author by the
  stable `user` value from their Google Scholar profile URL.

The server returns compact structured data: publication title, authors, year,
venue, abstract/snippet, citation count, public/eprint URLs, and author IDs;
or profile identity, affiliation, interests, metrics, and recent publications.

## Install and run

From this directory:

```sh
uv sync
.venv/bin/google-scholar-mcp
```

The process communicates over standard input and output. It deliberately emits
no runtime logs or diagnostics to stdout or stderr; tool failures are returned
through MCP responses.

## Connect from a Helomi profile override

After `uv sync`, add this endpoint to the selected profile's local override:

```text
.helomi/locales/<language>/profiles/<profile-id>/profile.override.yml
```

```yaml
mcp:
  endpoints:
    - id: google_scholar
      transport: stdio
      command: ./mcp/google_scholar/.venv/bin/google-scholar-mcp
      mode: immediate
      require_confirmation: false
```

Helomi starts stdio MCP servers with the source checkout root as their working
directory, so the relative `./mcp/...` command works regardless of the selected
profile. This local-server convention requires a source checkout; use a command
from `PATH` or an absolute executable path for installed deployments.

`profile.override.yml` is deep-merged over `profile.yml`, but its
`mcp.endpoints` list replaces the complete base list rather than appending to
it. Keep the override local: profile directories ignore it by default.

Helomi exposes the tools as `mcp__google_scholar__search_papers` and
`mcp__google_scholar__get_author`.

## Verify

```sh
UV_CACHE_DIR=/private/tmp/google-scholar-uv-cache uv run ruff check .
UV_CACHE_DIR=/private/tmp/google-scholar-uv-cache uv run ruff format --check .
UV_CACHE_DIR=/private/tmp/google-scholar-uv-cache uv run pyrefly check
UV_CACHE_DIR=/private/tmp/google-scholar-uv-cache uv run pytest -q
```

## Operational limits

Google Scholar is not a public API and can rate-limit or block automated
requests with CAPTCHA pages. The server reports those failures to the MCP host;
wait before retrying. For non-trivial volume, use a properly authorized proxy
configuration and comply with Google Scholar's terms of service.
