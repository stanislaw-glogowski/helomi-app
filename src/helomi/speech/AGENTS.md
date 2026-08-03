# Speech instructions

`helomi.speech` owns audio, capture, segmentation, STT, TTS, playback,
voice-session state, adapters, and worker queues. Keep conversation graph and
terminal UI policy outside this package.

Keep heavy MLX, device, and native-helper imports lazy. A driver, model, or
blocking worker has one owner; bridge concurrency with explicit queues or
futures and make cancellation drain or account for queued work. Native audio
protocol changes also require
[`native/macos/audio/AGENTS.md`](../../../native/macos/audio/AGENTS.md). See
[`docs/configuration.md`](../../../docs/configuration.md) for audio settings.

For speech changes, run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -q --no-cov tests/helomi/speech
```
