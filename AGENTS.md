# Helomi Agent Rules

Privacy-first voice assistant for Apple Silicon macOS (Python 3.14+ and Swift).

## Commands

```bash
make verify
make test
make format
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_xxx.py
```

Use Ruff and pyrefly, never mypy or pyright. `make verify` is the release gate and requires at least 90% branch
coverage.

## Boundaries

Dependencies flow in one direction:

`helomi_foundation <- helomi_runtime <- helomi_app <- {helomi_cli, helomi_tray}`

Foundation stays technically neutral. Runtime owns profiles, resources, audio, adapters, and workers. CLI and tray use
only the public `helomi_app.Application` facade. Architecture tests enforce these rules.

## Code

- Write all code, docstrings, comments, logs, errors, and UI output in English.
- Use Python 3.14 syntax, strict types, Pydantic v2, and native asyncio.
- Use full domain names in types; reserve common acronyms such as API, HTTP, SSE, VAD, STT, and TTS for established
  protocols or user-facing text.
- Comment non-obvious invariants and reasons, not visible control flow.
- Never use a real microphone, Twilio account, or heavyweight model in tests. Use fixtures under `tests/fixtures/`.

## Public Profile

Only `alexa` may appear in public documentation, examples, docstrings, or the changelog. Other profiles are local and
gitignored.

Swift-specific rules live in `native/AGENTS.md`.
