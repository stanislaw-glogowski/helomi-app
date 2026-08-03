# Benchmarks

Benchmark inputs and evaluation protocols are committed under `benchmarks/`.
Generated results, recordings, audio, manifests, and reports belong under the
local Helomi data root or another explicitly chosen output directory; never
commit them.

## Conversation models

```bash
uv run python -m tools.benchmark --type conversation
uv run python -m tools.benchmark --type conversation \
  --profile alexa \
  --suite benchmarks/conversation/suites/pl-alexa.yml
uv run python -m tools.benchmark --type conversation \
  --model-id mlx-community/gemma-4-26b-a4b-it-4bit \
  --output /path/to/results
```

Conversation benchmarks use the production model adapter and can load models or
use Metal. They measure routing and generation, not microphone-to-speaker
latency. See [the dated model-selection report](../benchmarks/conversation-model-selection.md).

## Voice

Run the voice tool through the benchmark dispatcher:

```bash
uv run python -m tools.benchmark --type voice --help
uv run python -m tools.benchmark --type voice list --suite pl-core
```

Voice benchmarks record or process real audio and require appropriate consent.
Read [the voice benchmark README](../../benchmarks/voice/README.md) before
recording participants or comparing STT/TTS systems.
