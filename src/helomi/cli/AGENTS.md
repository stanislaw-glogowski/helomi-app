# CLI instructions

`helomi.cli` is the terminal presentation frontend. `helomi.app` owns runtime
composition, worker readiness, retry, and shutdown; the CLI binds terminal
signals and projects the runtime's events, logs, and progress.

Keep UI state derived from domain events. Start event subscriptions before
publishing, await readiness explicitly, and propagate shutdown through the
event bus before awaiting runtime and UI tasks.

For CLI changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/cli
```
