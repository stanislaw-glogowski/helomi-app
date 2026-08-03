# Contributing to Helomi

Helomi is a local voice assistant for Apple Silicon Macs. Contributions should
keep its local-first behavior, explicit package ownership, and predictable
lifecycle contracts intact.

## Development setup

Install Python 3.14, uv, Xcode command-line tools, and Swift. Then run:

```bash
uv sync
make init
```

`make init` builds the Swift audio helper and downloads the models selected by
the installed default profile. It has network, disk-space, and model-license
implications. Use a separate data directory when needed:

```bash
HELOMI_HOME=/path/to/helomi-data make init
```

Run the terminal application with `make run-cli`. The desktop entrypoint is a
thin shell and is not yet a complete desktop product surface.

## Ownership and instructions

Read the root [AGENTS.md](AGENTS.md) and only the scoped `AGENTS.md` files that
cover files you change. Package ownership is deliberate:

- `speech` owns voice I/O, session state, STT, TTS, playback, and adapters.
- `conversation` owns graph runs, history, profiles, model adapters, and reply
  segmentation.
- `resources` owns local settings, profiles, model-path discovery, and data-root
  validation.
- `common` owns reusable lifecycle, events, logging, and validation primitives.
- `cli` owns runtime composition, startup, shutdown, and the terminal UI.
- `desktop` remains a thin macOS shell.

Do not move domain policy into `common`, duplicate runtime composition in
`desktop`, or turn developer tools into alternate production runtimes.

## Validation

Use the focused command from the applicable scoped instructions while iterating.
Examples:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/speech
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/conversation
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/resources
```

For final, cross-package, dependency, build, or broad changes run:

```bash
make verify
```

Automated checks are hardware-independent. State separately whether you ran a
real microphone/speaker session, Voice Processing interruption check, native
helper check, Metal inference, or downloaded-model smoke test.

## Code and test expectations

- Keep code, logs, errors, and documentation in English.
- Keep heavy devices, native helpers, and MLX models lazy at lifecycle
  boundaries.
- Give each blocking worker or resource one owner. Cross thread/asyncio
  boundaries with queues, futures, or loop handoff.
- Shutdown signals work, awaits tasks, closes resources, and joins workers.
  Every successful queue `get()` has exactly one `task_done()`.
- Tests must not need hardware, Metal, downloads, network access, or arbitrary
  sleeps. Use observable synchronization and add regression tests for fixes.

## Local data and privacy

Never commit local models, recordings, generated benchmark output, caches, or
secrets. Use anonymous identifiers for benchmark participants and obtain
informed consent before recording anyone else. Repository source is MIT, but
models, voices, and downloaded assets retain their own licenses and terms.

## Documentation and ADRs

Treat source code, configuration models, tests, and executable commands as the
current contract. Update relevant documentation in the same change when a public
workflow, configuration contract, architecture, or operational command changes.

Read documentation selectively; do not use an ADR as an API reference. Use an
ADR for durable decisions about ownership, configuration contracts, concurrency,
native protocol compatibility, privacy boundaries, persistence, or core
technology choices. Follow the [ADR policy](docs/adr/README.md).

## Pull requests

Keep a pull request focused, describe user-visible and architecture effects,
list validation performed, and call out hardware/model checks that were not run.
Link related ADRs, benchmarks, and follow-up issues where relevant.
