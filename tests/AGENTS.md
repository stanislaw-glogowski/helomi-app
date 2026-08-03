# Test instructions

Read the matching source instructions before changing tests:

- `tests/helomi/cli/**` -> `src/helomi/cli/AGENTS.md`
- `tests/helomi/common/**` -> `src/helomi/common/AGENTS.md`
- `tests/helomi/conversation/**` -> `src/helomi/conversation/AGENTS.md`
- `tests/helomi/resources/**` -> `src/helomi/resources/AGENTS.md`
- `tests/helomi/speech/**` -> `src/helomi/speech/AGENTS.md`
- `tests/helomi/desktop/**` -> `src/helomi/desktop/AGENTS.md`

Tests must not require hardware, Metal, model downloads, external runtimes, or
network access. Synchronize with events, queues, futures, or observable state;
never use arbitrary sleeps. `asyncio.sleep(0)` is only an explicit event-loop
yield when no stronger synchronization fits.

Fixes need a regression test that fails for prior behavior. Put cross-package
helpers in `tests/support.py`, executable process fakes and shared fixtures in
`tests/fixtures/`, and local fakes beside their tests. Use `--no-cov` for
targeted work; the full suite keeps branch coverage and its 95% threshold.

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/<affected-path>
```
