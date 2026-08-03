# Helomi voice benchmark

This benchmark compares Polish STT, endpointing, and TTS. Recording prompts are
reference transcriptions; model output is kept separately. Recordings are
sensitive local data and must never be committed.

Run all commands through the benchmark dispatcher:

```bash
uv run python -m tools.benchmark --type voice --help
```

By default generated voice data is written below `benchmarks/voice/report/` in
the checkout. Prefer `--output /path/outside/the/checkout` for recordings and
results.

## Recording

Display a suite without opening a device or loading a model:

```bash
uv run python -m tools.benchmark --type voice list --suite pl-core
```

Record a session through the native audio path:

```bash
uv run python -m tools.benchmark --type voice record \
  --suite pl-core \
  --speaker speaker-01 \
  --condition quiet \
  --output /path/to/helomi-voice-benchmark
```

The recorder prompts for a session id when `--session` is omitted. It displays
each prompt, waits for Enter to start and stop recording, and permits accepting,
playing, retaking, skipping, or quitting each take. Resume an existing session:

```bash
uv run python -m tools.benchmark --type voice record \
  --suite pl-core \
  --speaker speaker-01 \
  --condition quiet \
  --session kitchen-morning \
  --resume \
  --output /path/to/helomi-voice-benchmark
```

Each session contains `metadata.yml`, `manifest.jsonl`, and 16 kHz mono WAV
files. `metadata.yml` is a human-editable consent/device template; do not add
direct personal identifiers.

## STT and endpointing

Use a distinct result directory for each run:

```bash
uv run python -m tools.benchmark --type voice stt \
  --session /path/to/helomi-voice-benchmark/recordings/pl-core/speaker-01/SESSION \
  --adapter mlx:parakeet-tdt \
  --output /path/to/helomi-voice-benchmark/results/parakeet

uv run python -m tools.benchmark --type voice endpoint \
  --session /path/to/helomi-voice-benchmark/recordings/pl-turn-taking/speaker-01/SESSION \
  --output /path/to/helomi-voice-benchmark/results/endpoint
```

STT supports `mlx:parakeet-tdt`, `mlx:qwen3-asr`, and `mlx:whisper`; use
`--model` to override its model and `--language pl` for a Whisper language hint.
The result contains WER, CER, inference time, and real-time factor. Endpointing
replays recordings through production VAD and segmentation and reports endpoint
latency, utterance count, and premature endpoints.

## TTS and listening review

```bash
uv run python -m tools.benchmark --type voice tts \
  --suite pl-tts \
  --adapter piper \
  --model pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx \
  --output /path/to/helomi-voice-benchmark/results/piper

uv run python -m tools.benchmark --type voice report \
  --results /path/to/helomi-voice-benchmark/results

uv run python -m tools.benchmark --type voice tts-review \
  --results /path/to/helomi-voice-benchmark/results/piper /path/to/helomi-voice-benchmark/results/chatterbox \
  --output /path/to/helomi-voice-benchmark/reviews/piper-vs-chatterbox
```

TTS metrics cover model loading, time to first audio, total inference time, and
real-time factor. Pronunciation, prosody, and naturalness need a listening
review. Complete `ratings.csv` without opening `mapping.json`; reveal the
mapping only after review.

## Natural conversation acceptance

Use `pl-turn-taking` with the Alexa profile to compare a baseline and candidate
on the same Mac, AVFAudio device path, model, voice, and scripted Polish turns.
Keep recordings and generated reviews outside the checkout. Blind the run label,
then require no critical endpointing, backchannel, interruption, continuity,
cancellation, or brevity failure; higher aggregate naturalness and
appropriateness; no lower reviewed category; and direct-path warm median
playback-start latency within 10% of baseline. Report classifier-path latency
separately. PyAudio and real model or hardware validation remain separate from
fake-driven tests.

## Consent

Use anonymous identifiers such as `speaker-02`. Obtain informed consent, agree
how recordings will be stored and deleted, and obtain guardian consent for a
child. Voice can be biometric data.
