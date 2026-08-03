# CLI instructions

`helomi.cli` is the composition root for terminal startup, signals, worker
readiness, shutdown, and Textual integration. It may assemble dependencies but
must not redefine conversation, speech, or resource policy.

Keep UI state derived from domain events. Start event subscriptions before
publishing, await readiness explicitly, and propagate shutdown through the
event bus before awaiting runtime and UI tasks.

For CLI changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/cli
```
