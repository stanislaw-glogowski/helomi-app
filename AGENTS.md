# Helomi – Agent Rules

Privacy-first voice assistant for Apple Silicon macOS (Python >=3.14 + Swift).

## Commands

```bash
make verify      # Full CI validation (lint + tests + swift + build)
make test        # Fast pytest suite with >=90% branch coverage check
make lint        # ruff + pyrefly (do NOT use mypy/pyright) + swift format
make format      # Auto-format Python and Swift
make typecheck   # Fast pyrefly typecheck
make init        # Build Swift helper & sync uv
```

Targeted test: `UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/unit/test_xxx.py`

## Architecture Boundaries

- `helomi_common`: Shared models/utils. **Zero inward dependencies** (cannot import `helomi_core`, `helomi_cli`,
  `helomi_tray`).
- `helomi_core`: Audio orchestration, VAD, STT, TTS, turn, wakeword adapters/workers, application runtime, pipeline
  service, config, resources, server API/extension, parrot extension. Cannot import `helomi_cli` or `helomi_tray`.
- `helomi_cli`: Terminal user interface. Interacts with `helomi_core`. Cannot import `helomi_tray`.
- `helomi_tray`: macOS system tray interface. Interacts with `helomi_core`. Cannot import `helomi_cli`.
- `native/`: Swift package. See `native/AGENTS.md`.

*Boundaries enforced by `tests/unit/test_architecture.py`.*

## Coding & Testing Standards

- **Language**: All code, docstrings, comments, log messages, error messages, and CLI/tray output must strictly be in
  **English**.
- **Python 3.14**: Use `T | None` (never legacy `Optional`/`Union`), Pydantic v2 `BaseModel`, strict types (`pyrefly`).
- **Async**: Native `asyncio`. Offload blocking audio/C calls to threadpools.
- **Coverage**: `>=90%` branch coverage required (`--cov-fail-under=90`). Test all branches.
- **Mocks & Fixtures**: Never access real mic or heavy MLX models in tests. Use `tests/fixtures/audio.py`
  (`create_raw_audio`, `create_silence_raw_audio`, `create_noise_raw_audio`) and `tests/fixtures/mocks.py`.

