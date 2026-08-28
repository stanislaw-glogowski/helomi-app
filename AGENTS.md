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

- `helomi_common`: Shared models/utils. **Zero inward dependencies** (cannot import `helomi_core`, `helomi_speech`, `helomi_cli`).
- `helomi_core`: Audio orchestration, VAD, state machine. Cannot import `helomi_cli` or `helomi_speech`.
- `helomi_speech`: MLX/Whisper/VoxCPM engines. Cannot import `helomi_cli`.
- `helomi_cli`: User interface. Interacts with `helomi_core`.
- `native/`: Swift package. See `native/AGENTS.md`.

*Boundaries enforced by `tests/unit/test_architecture.py`.*

## Coding & Testing Standards

- **Python 3.14**: Use `T | None` (never legacy `Optional`/`Union`), Pydantic v2 `BaseModel`, strict types (`pyrefly`).
- **Async**: Native `asyncio`. Offload blocking audio/C calls to threadpools.
- **Coverage**: `>=90%` branch coverage required (`--cov-fail-under=90`). Test all branches.
- **Mocks & Fixtures**: Never access real mic or heavy MLX models in tests. Use `tests/fixtures/audio.py` (`sample_raw_audio`, `sample_silence_raw_audio`, `sample_noise_raw_audio`) and `tests/fixtures/mocks.py`.
