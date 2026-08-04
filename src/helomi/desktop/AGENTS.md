# Desktop instructions

`helomi.desktop` is the thin macOS menu-bar shell. Keep runtime composition in
`helomi.app` and domain behavior with its owning package. Do not duplicate
startup policy or speech/conversation workers here.

Keep desktop imports lightweight and platform integration explicit. Add focused
tests under `tests/helomi/desktop/` when desktop behavior becomes testable.
Run the focused desktop and application tests while iterating:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/app tests/helomi/desktop
```
