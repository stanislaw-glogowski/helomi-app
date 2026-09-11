<div align="center">

# Helomi

**Local, privacy-first voice assistant optimized for Apple Silicon Macs.**

[![Python 3.14+](https://img.shields.io/badge/Python-3.14+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![macOS Apple Silicon](https://img.shields.io/badge/macOS-Apple%20Silicon-000000?logo=apple&logoColor=white)](https://support.apple.com/)
[![Built with MLX](https://img.shields.io/badge/ML-Apple%20MLX-F56300?logo=apple)](https://github.com/ml-explore/mlx)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked by pyrefly](https://img.shields.io/badge/type%20checker-pyrefly-blueviolet)](https://github.com/facebook/pyrefly)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

</div>

---

## Overview

Helomi runs entirely on-device, processing audio streams locally with hardware acceleration on Apple Silicon unified
memory. Zero telemetry, zero cloud audio streaming.

### Key Capabilities

- **Native Audio Pipeline**: Low-latency capture and playback powered by Swift (`AVAudioEngine` + Apple Voice
  Processing / Echo Cancellation).
- **On-Device Speech Stack**:
    - **Wake-Word**: OpenWakeWord engine
    - **VAD & Turn-Taking**: Silero VAD (MLX and ONNX backends) + Smart Turn detection
    - **STT (Speech-to-Text)**: Fast inference with Parakeet and MLX-Whisper
    - **TTS (Text-to-Speech)**: Streaming neural voice synthesis via VoxCPM2 and Supertonic (with voice style cloning &
      presets)
    - **Model Management**: Automatic local Hugging Face model cache resolution (`HFModel`)
- **Modular Architecture**: Clean separation between core audio orchestration, speech engines, and interfaces.

---

## Quickstart

### Prerequisites

- macOS running on Apple Silicon
- [uv](https://docs.astral.sh/uv/) package manager
- Xcode Command Line Tools (`xcode-select --install`)
- [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli)

### Download Speech Models

Helomi runs inference completely on-device using local Hugging Face models. Download the default models before starting
the application:

#### Default Models (~7.5 GB total)

| Component | Model Repository                     |    Size    | Description                                       |
|-----------|--------------------------------------|:----------:|---------------------------------------------------|
| **STT**   | `mlx-community/parakeet-tdt-0.6b-v3` | `~2.5 GB`  | Fast, low-latency Speech-to-Text                  |
| **TTS**   | `openbmb/VoxCPM2`                    | `~5.0 GB`  | Expressive neural voice synthesis & voice cloning |
| **Turn**  | `mlx-community/smart-turn-v3`        | `~32.0 MB` | Intelligent conversational turn-taking detection  |
| **VAD**   | `mlx-community/silero-vad`           | `~2.2 MB`  | Voice activity detection (MLX engine)             |

```bash
hf download mlx-community/parakeet-tdt-0.6b-v3
hf download openbmb/VoxCPM2
hf download mlx-community/smart-turn-v3
hf download mlx-community/silero-vad
```

### Installation & Setup

```bash
# 1. Clone repository
git clone https://github.com/stanislaw-glogowski/helomi-app.git
cd helomi-app

# 2. Build native Swift audio helper, sync environment, and install wake-word models
make init
```

#### Optional Alternative Models

| Component              | Model Repository                       |    Size     | Description                                         |
|------------------------|----------------------------------------|:-----------:|-----------------------------------------------------|
| **TTS (Lightweight)**  | `Supertone/supertonic-3`               | `~414.7 MB` | Ultra-fast, lightweight voice synthesis alternative |
| **STT (Multilingual)** | `mlx-community/whisper-large-v3-turbo` |  `~1.6 GB`  | Multilingual Whisper Speech-to-Text                 |

```bash
# Optional: alternative TTS adapter (supertonic)
hf download Supertone/supertonic-3

# Optional: alternative STT adapter (whisper)
hf download mlx-community/whisper-large-v3-turbo
```

### Running the Application (`helomi-tray`)

The primary way to use Helomi is via the **macOS System Tray application (`helomi-tray`)**. It runs in your macOS menu
bar, manages continuous on-device audio processing, displays real-time status indicators, provides hotkeys to switch
voice profiles and modes (Parrot mode or API server), and includes an interactive Text-to-Speech window (`t`) with
speech synthesis and WAV export:

```bash
# Launch the macOS system tray application
make run-tray
# or directly via uv:
uv run helomi-tray
```

### Developer CLI (`helomi-cli`)

For headless environments, automated CI provisioning, or debugging, a developer CLI is also available:

```bash
# List all available commands and options
make run-cli -- -h
# or: uv run helomi-cli -h

# 1. Install required acoustic models (OpenWakeWord, VAD) - already performed by make init
make run-cli install
# or directly via uv:
uv run helomi-cli install

# 2. Run developer parrot mode (live speech recognition and spoken echo in terminal)
make run-cli parrot
# or specify an active profile:
make run-cli parrot alexa
# or directly via uv:
uv run helomi-cli parrot [profile_id]

# 3. Start standalone local FastAPI server directly in terminal
make run-cli serve
# or directly via uv:
uv run helomi-cli serve

# 4. Enable debug logging with -d
make run-cli -- -d parrot
# or: uv run helomi-cli -d parrot
```

---

## Documentation

For more detailed information on configuring and extending Helomi, please refer to the documentation:

- [Settings Configuration](docs/settings.md)
- [Profiles Configuration](docs/profiles.md)
- [Models & Adapters](docs/models.md)
- [Reference Audio (Voice Cloning)](docs/audio.md)
- [Server API Specification](docs/api.md)
- [System Tray & CLI Applications](docs/apps.md)
- [TypeScript Demo Application](demo/README.md)
- [Configuration Examples](docs/examples.md)

---

## Project Structure

```text
helomi-app/
├── src/
│   ├── helomi_common/   # Shared domain models, foundation components & utilities
│   ├── helomi_core/     # Audio orchestration, adapters, workers, runtime, pipeline service, server API
│   ├── helomi_tray/     # Primary macOS system tray application (rumps)
│   └── helomi_cli/      # Developer CLI & terminal UI (install, parrot, serve)
├── native/
│   └── macos/avfaudio/  # Swift package for macOS CoreAudio/AVFAudio bridge
├── resources/           # Local configuration, profiles, and acoustic models
├── demo/                # Interactive TypeScript & Bun voice assistant demo client
└── tests/               # Unit, integration, and architecture test suite
```

---

## Development & Quality Assurance

All modifications are enforced with strict typing and $\ge 90\%$ branch coverage:

```bash
make test        # Run pytest suite with coverage check (>=90%)
make lint        # Run ruff + pyrefly + swift format checks
make format      # Auto-format Python and Swift code
make verify      # Full validation pipeline (Lint + Test + Native + Build)
```

---

## License

Helomi is licensed under the [MIT License](LICENSE). Third-party models and acoustic assets retain their respective
licenses.
