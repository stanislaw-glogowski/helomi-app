# Conversation instructions

`helomi.conversation` owns finite graph runs, history, profiles, model adapters,
and streamed reply segmentation. It does not own microphone, playback, or
voice-session policy.

Keep graph input and delivery state explicit. Acquire language-model runtimes
lazily in their service lifecycle, cancel active generation before replacing it,
and keep streamed chunks safe for speech delivery. See
[`docs/configuration.md`](../../../docs/configuration.md) for configured model
adapters.

For conversation changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/conversation
```
