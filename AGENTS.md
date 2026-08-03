# Helomi instructions

Helomi is a local, privacy-first voice assistant for Apple Silicon Macs.

## Routing

Read this file and only the scoped `AGENTS.md` files covering changed paths.
From the repository root, discover those files explicitly. For tests, read
`tests/AGENTS.md` and the matching source-package file. Cross-package work
reads each affected package file; linked documentation is opt-in and only for
the relevant task.

## Ownership

- `speech`: voice I/O and speech-domain behavior.
- `conversation`: graph execution and conversation-domain behavior.
- `resources`: local runtime-resource discovery and loading.
- `common`: shared lifecycle, events, logging, and validation primitives.
- `cli`: application composition, startup, and terminal UI integration.
- `desktop`: thin macOS desktop shell.

Keep state and policy with their owner. Use explicit contracts and package-owned
adapters. Acquire heavy resources lazily at lifecycle boundaries. A blocking
resource or worker has one owner; cross thread or asyncio boundaries with
queues, futures, or loop handoff. Shutdown signals work, awaits tasks, closes
resources, and joins workers. Each successful queue `get()` has one
`task_done()`.

## Workflow

Inspect staged and unstaged changes before editing; preserve unrelated work.
Prefer targeted searches, reads, and command output. Do not delegate routine
work. Keep code, logs, errors, and docs in English. Do not commit local data,
models, recordings, generated artifacts, caches, or secrets.

Use the narrow check from the relevant scoped file while iterating. Run
`make verify` for broad, cross-package, dependency, build, or final changes.
Report required hardware or model validation separately. Run `uv sync` after
dependency or lockfile changes.

## Documentation

Do not read documentation broadly for routine implementation work. Open only
the documents directly relevant to the requested behavior or changed paths.
Treat source code, configuration models, tests, and executable commands as the
current contract; verify documentation against those sources before relying on
it.

When a change modifies a documented public workflow, configuration contract,
architecture decision, or operational command, update the relevant document in
the same change. ADRs explain durable decisions; they are not an API reference
or a substitute for inspecting the current implementation.
