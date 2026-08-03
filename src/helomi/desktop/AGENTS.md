# Desktop instructions

`helomi.desktop` is the thin macOS desktop entrypoint and platform shell. Keep
runtime composition in `helomi.cli` and domain behavior with its owning package.
Do not duplicate terminal UI state, startup policy, or speech/conversation
workers here.

Keep desktop imports lightweight and platform integration explicit. Add focused
tests under `tests/helomi/desktop/` when desktop behavior becomes testable.
Until then, run the focused Helomi namespace:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi
```
