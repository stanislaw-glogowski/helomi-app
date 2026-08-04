# MCP endpoint instructions

Each directory under `mcp/` is an isolated MCP server project. Keep its runtime
dependencies, `pyproject.toml`, lockfile, source, tests, and README inside that
endpoint directory; do not add endpoint dependencies to Helomi's root project.

For stdio servers, reserve stdout exclusively for MCP protocol messages and do
not emit runtime logs or diagnostics to stdout or stderr. Return operational
failures through MCP tool errors or structured results. Do not commit
credentials, proxy configuration, local environments, caches, recordings, or
generated artifacts.

Document local Helomi connections with relative commands rooted at `./mcp/` and
place examples in a profile's `profile.override.yml`. Treat these internal
relative endpoints as source-checkout development/testing integrations.

Run the endpoint-local formatter, linter, type checker, and tests from its own
directory. Use an explicit temporary `UV_CACHE_DIR` when the normal cache is
not writable. Cross-package changes must also follow the repository root
instructions and relevant Helomi package instructions.
