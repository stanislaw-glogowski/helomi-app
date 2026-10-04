<div align="center">

# Helomi

**Local, privacy-first voice assistant for Apple Silicon Macs.**

[![Python 3.14+](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![macOS Apple Silicon](https://img.shields.io/badge/macOS-Apple%20Silicon-000000?logo=apple)](https://support.apple.com/)
[![Built with MLX](https://img.shields.io/badge/ML-Apple%20MLX-F56300?logo=apple)](https://github.com/ml-explore/mlx)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

Helomi runs wake-word detection, voice activity detection, turn detection, transcription, and synthesis locally. The
default AVFAudio route does not send audio to a cloud service. Optional inbound Twilio support necessarily transports
call audio through Twilio.

## Capabilities

- Multiple mounted audio drivers behind one active conversation route.
- Native AVFAudio capture and playback with Apple voice processing.
- Inbound Twilio calls with signature validation, callee-to-profile mapping, caller monitoring, room voice, barge-in,
  and playback acknowledgements.
- On-device Parakeet or Whisper transcription and VoxCPM2, Supertonic, or Piper synthesis.
- Continuous dialogue with follow-up listening, persistent profiles, silent interruption, greetings, and farewells.
- API, Parrot, and Operator response modes that can change without restarting audio.
- A macOS system tray application, developer CLI, REST/SSE API, and TypeScript demo client.

## Quickstart

Requirements: Apple Silicon macOS, Python 3.14+, [uv](https://docs.astral.sh/uv/), Xcode Command Line Tools, and the
[Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli).

```bash
git clone https://github.com/stanislaw-glogowski/helomi-app.git
cd helomi-app
make init
make run-tray
```

`make init` installs dependencies, builds the Swift AVFAudio helper, and installs wake-word assets. Speech models must
exist in the local Hugging Face cache; see [Models and Adapters](docs/models.md) for download commands and sizes.

The supported public profile is `alexa`. There is no implicit profile: select it explicitly, activate it by wake word,
or map an inbound Twilio number to it.

## Commands

```bash
make run-tray                  # Start the primary menu bar application
make run-cli -- parrot alexa  # Run local echo mode with an explicit profile
make run-cli parrot           # Wait for a configured wake word
make run-cli serve            # Start the REST/SSE API in API response mode
make run-cli install          # Install shared wake-word assets
```

Use `uv run helomi-tray` or `uv run helomi-cli ...` when invoking entry points directly.

## Architecture

```text
helomi_foundation <- helomi_runtime <- helomi_app <- helomi_cli / helomi_tray
```

- `helomi_foundation` contains neutral lifecycle, configuration, logging, and concurrency primitives.
- `helomi_runtime` owns profiles, resources, audio routing, adapters, and speech workers.
- `helomi_app` exposes the conversation state machine, messages, response modes, and public `Application` facade.
- CLI and tray depend only on that facade. The Swift AVFAudio helper lives under `native/macos/avfaudio`.

## Documentation

- [Settings](docs/settings.md)
- [Profiles](docs/profiles.md)
- [Models and Adapters](docs/models.md)
- [Audio Routing and Twilio](docs/audio.md)
- [Applications](docs/apps.md)
- [Server API](docs/api.md)
- [Examples](docs/examples.md)
- [TypeScript Demo](demo/README.md)

## Development

```bash
make test        # Python tests with at least 90% branch coverage
make lint        # Ruff, pyrefly, and Swift Format
make verify      # Lint, tests, Swift tests, demo checks, and package build
```

Helomi is available under the [MIT License](LICENSE). Model and acoustic asset licenses remain their own.
