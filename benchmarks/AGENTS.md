# Benchmark instructions

Commit suites, prompts, schemas, and evaluation protocols under `benchmarks/`.
Keep recordings, generated audio, reports, manifests, model output, and measured
results below `$HELOMI_HOME/benchmarks`; never commit generated benchmark data.

Read [`conversation/README.md`](conversation/README.md) for model runs,
[`voice/README.md`](voice/README.md) for voice protocol, and
[`docs/benchmarks/conversation-model-selection.md`](../docs/benchmarks/conversation-model-selection.md)
only when the task concerns those benchmarks. Benchmark tooling belongs in
`tools/benchmark/`, not production runtime packages.
