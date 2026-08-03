# Testing

Tests must be deterministic and hardware-independent: no microphone, speaker,
Metal model execution, downloads, external endpoint, or network access. Use
fakes and observable synchronization, not time-based sleeps.

Run focused checks while working:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/common
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/resources
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/speech
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/conversation
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/cli
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/tools
```

Run the full gate for final or broad work:

```bash
make verify
```

It checks Ruff lint/formatting, Pyrefly, pytest with the coverage threshold,
Python compilation, Swift formatting and tests, and the distributable package.
Report real-device and real-model checks separately.
