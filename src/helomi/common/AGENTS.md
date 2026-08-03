# Common instructions

`helomi.common` contains only reusable lifecycle, event, logging, and
validation primitives. Do not add speech, conversation, resource, or UI
concepts here for convenience.

Preserve resource and executor ownership. Event subscriptions must close
cleanly; queue capacity and overload behavior are part of the contract. Every
received queue item gets exactly one `task_done()`, including cancellation and
error paths.

For common changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/common
```
