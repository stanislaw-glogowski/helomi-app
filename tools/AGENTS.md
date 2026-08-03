# Tool instructions

`tools` contains developer-facing diagnostics, installers, and benchmark
runners. Tools may print deliberately and may consume public production
contracts, but must not become alternate production runtimes or redefine domain
behavior.

Keep interactive device, model, and filesystem effects explicit in the command
interface. Put tool tests in `tests/tools/`; benchmark inputs and generated
output follow [`benchmarks/AGENTS.md`](../benchmarks/AGENTS.md).

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/tools
```
