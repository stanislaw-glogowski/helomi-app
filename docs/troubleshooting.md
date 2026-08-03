# Troubleshooting

## Initialization or downloads fail

Confirm Python and uv versions, network access, free disk space, and model
access permissions. `make init` only copies missing local defaults; inspect the
selected data root when an old configuration remains in effect.

```bash
HELOMI_HOME=/path/to/helomi-data make init
```

If a model was changed in a profile after initialization, install its required
repository or Piper files deliberately. Piper needs both the `.onnx` voice file
and adjacent `.onnx.json` configuration.

## No valid profile appears

Check `<data-root>/profiles/<id>/profile.yml` and all required prompt/reaction
files. Confirm that model fields match the active adapter in `settings.yml`, the
wake-word path is an ONNX filename, and referenced local wake-word assets exist
under `<data-root>/models`.

## Microphone, speaker, or interruption problems

Grant microphone permission to the terminal/application. Run an audio check:

```bash
uv run python -m tools.diagnostic --type audio --seconds 5
uv run python -m tools.diagnostic --type audio --seconds 5 --duplex
```

The duplex test plays a signal while recording residual microphone audio. Remain
silent for the measurement. The default `avfaudio` driver uses the packaged
Swift helper and Apple Voice Processing. `pyaudio` is useful for fallback and
comparison, but it does not provide equivalent speaker-reference cancellation:

```bash
uv run python -m tools.diagnostic --type audio --driver pyaudio
```

## Native helper fails to build or start

Install Xcode command-line tools and run the native package checks from the
repository root:

```bash
swift format lint --recursive native/macos/audio
swift test --package-path native/macos/audio
native/macos/build.sh
```

The helper binary is packaged at
`src/helomi/speech/audio/adapters/avfaudio/bin/audio`. A protocol version mismatch
requires synchronized Swift, Python, fake-helper, and test updates.

## Model startup or poor response behavior

Real MLX model runs require Metal access and sufficient unified memory. Check
the configured adapter and model id first; benchmark a candidate before changing
a profile permanently. See [Benchmarks](development/benchmarks.md). Automated
tests cannot establish language quality, latency, or real spoken quality.
