# Conversation benchmarks

These benchmarks measure response routing and language-model generation without
opening an audio device, synthesizing speech, or starting the terminal UI.
Committed suites contain Polish inputs; implementation and reports remain in
English.

The current evidence and limitations for local profile model selection are in
[the dated model-selection report](../../docs/benchmarks/conversation-model-selection.md).

## Run a benchmark

The default uses the selected local default profile and `pl-core.yml`:

```bash
uv run python -m tools.benchmark --type conversation
```

Select a profile or suite explicitly:

```bash
uv run python -m tools.benchmark --type conversation \
  --profile henry \
  --suite benchmarks/conversation/suites/pl-henry.yml
```

Override all conversation model roles for a candidate run without editing a
profile:

```bash
uv run python -m tools.benchmark --type conversation \
  --profile alexa \
  --model-id mlx-community/gemma-4-26b-a4b-it-4bit \
  --suite benchmarks/conversation/suites/pl-core.yml \
  --output /path/to/helomi-benchmarks/gemma4-core
```

Without `--output`, reports are written below
`benchmarks/conversation/report/` in the checkout. Prefer an explicit directory
outside the checkout for generated output; do not commit result JSON or reports.

The selected profile must contain fields valid for the conversation adapter in
the active data-root settings. Direct MLX inference is supplied by default.
LangChain is an alternative for an Ollama-compatible endpoint. This tool does
not explicitly download models, although the selected adapter may resolve
missing weights through its underlying library.

## Suites and measurements

- `pl-core.yml` checks general short and detailed response routing.
- Persona suites (`pl-alexa.yml`, `pl-gizmo.yml`, `pl-henry.yml`, `pl-lucy.yml`,
  and `pl-viki.yml`) support focused persona review.

For each case, `results.json` records expected and selected turn intent and
response depth, cold or warm state, first-chunk and total generation time,
output length, and text. `report.md` aggregates planning accuracy for human
review. Older suites using `expected_mode` remain readable as brief or detailed
response cases; new suites should declare `expected_intent` and `expected_depth`.

First model chunk is not the first speakable phrase. These benchmarks do not
measure transcription, phrase segmentation, TTS, playback, interruption, or
end-to-end voice latency. Keep cold and warm results separate, and treat quality
scores as human review rather than statistical claims.
