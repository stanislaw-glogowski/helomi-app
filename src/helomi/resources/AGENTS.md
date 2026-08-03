# Resources instructions

`helomi.resources` owns local settings, profiles, model-path discovery,
`HELOMI_HOME` resolution, and configuration validation. It locates and validates
resources; adapters own model loading and downloads.

Keep filesystem precedence deterministic and failures actionable. Preserve the
fixed profile layout and validate data at the boundary. See
[`docs/configuration.md`](../../../docs/configuration.md) for runtime
configuration.

For resource changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/resources
```
