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

The process communicates over standard input and output. Do not write regular
output to its stdout.

## Connect from a Helomi profile

After `uv sync`, add this endpoint to the profile's `settings.yml`, replacing
`/absolute/path/to/helomi-app` with the actual repository path:

```yaml
mcp:
  endpoints:
    - id: google_scholar
      transport: stdio
      command: /absolute/path/to/helomi-app/mcp/google_scholar/.venv/bin/google-scholar-mcp
      mode: immediate
      require_confirmation: false
```

Helomi exposes the tools as `mcp__google_scholar__search_papers` and
`mcp__google_scholar__get_author`. This README is the only profile-connection
artifact added by this package; no Helomi profile is changed automatically.

## Operational limits

Google Scholar is not a public API and can rate-limit or block automated
requests with CAPTCHA pages. The server reports those failures to the MCP host;
wait before retrying. For non-trivial volume, use a properly authorized proxy
configuration and comply with Google Scholar's terms of service.
