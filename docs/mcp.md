# MCP endpoints

Helomi can connect a profile to [Model Context Protocol](https://modelcontextprotocol.io/)
(MCP) tool servers. Configure endpoints under `mcp.endpoints` in the selected
profile. Keep machine-local commands, tokens, and endpoints in that profile's
`profile.override.yml` rather than versioning them in `profile.yml`.

## Local profile configuration

`profile.override.yml` is deep-merged over `profile.yml`. An `endpoints` list
in the override replaces the profile's whole endpoint list; it does not append
to it.

For example, after preparing a local MCP project under this repository's
`mcp/` directory, add this to:
`<data-root>/locales/<language>/profiles/<profile-id>/profile.override.yml`.

```yaml
mcp:
  endpoints:
    - id: google_scholar
      transport: stdio
      command: ./mcp/google_scholar/.venv/bin/google-scholar-mcp
      mode: immediate
      require_confirmation: false
```

For stdio endpoints, Helomi explicitly starts the child process with its
working directory set to the source checkout root: the directory containing
both `pyproject.toml` and `mcp/`. Consequently, commands beginning with
`./mcp/` work regardless of which profile is selected or where its data lives.
This convention is for internal source-checkout servers; installed deployments
should use an executable available through `PATH` or an absolute path.

## Endpoint contract

| Transport | Required fields | Optional fields |
| --- | --- | --- |
| `stdio` | `id`, `command` | `args`, `mode`, `require_confirmation`, `env_from_env` |
| `streamable_http` | `id`, `url` | `mode`, `require_confirmation`, `headers_from_env` |

`id` must be unique in the profile and use lowercase letters, digits,
underscores, or hyphens. Helomi exposes a server tool named `search_papers` as
`mcp__<endpoint-id>__search_papers` to the conversation model.

Stdio commands are literal executables: Helomi does not invoke a shell. The
child receives only a small inherited environment (`PATH`, locale, home, and
temporary-directory variables) plus names explicitly mapped through
`env_from_env`. Streamable HTTP headers are mapped similarly with
`headers_from_env`.

```yaml
mcp:
  endpoints:
    - id: calendar
      transport: streamable_http
      url: https://example.test/mcp
      mode: background
      require_confirmation: true
      headers_from_env:
        Authorization: HELOMI_CALENDAR_AUTHORIZATION
```

## Execution and failures

`mode: immediate` runs the tool during the current reply. `mode: background`
queues calls one at a time and adds a later result to the conversation.
`require_confirmation: true` requires an explicit confirmation before a tool
call.

Endpoint startup is isolated: an unavailable or misconfigured endpoint adds a
warning and disables only its own tools. This includes a relative stdio command
when Helomi cannot identify a source checkout containing `mcp/`.

See [Profiles](profiles.md) for profile layout and merging. Each local server's
README documents its own installation and tool contract.
