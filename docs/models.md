# Models & Adapters

Helomi runs inference from models already present in the local Hugging Face cache.

## Downloading Models

Settings validation resolves models with `local_files_only=True`; startup fails clearly when a selected adapter model is not
available. Download required models before the first run with the Hugging Face CLI (`hf` or `huggingface-cli`):

```bash
# Default Speech Stack (~7.5 GB)
hf download mlx-community/parakeet-tdt-0.6b-v3      # ~2.5 GB (Default STT)
hf download openbmb/VoxCPM2                         # ~5.0 GB (Default TTS)
hf download mlx-community/smart-turn-v3             # ~32.0 MB (Default Turn Taking)
hf download mlx-community/silero-vad                # ~2.2 MB (Default VAD MLX)

# Optional Alternatives
hf download Supertone/supertonic-3                  # ~414.7 MB (Lightweight TTS)
hf download mlx-community/whisper-large-v3-turbo    # ~1.6 GB (Multilingual STT)
```

## Recommended Models (Default Settings)

The default configuration is designed to offer the best balance of speed and accuracy on Apple Silicon hardware:

| Component          | Default Model                        |    Size    | Optional Alternative                   | Alternative Size |
|--------------------|--------------------------------------|:----------:|----------------------------------------|:----------------:|
| **STT**            | `mlx-community/parakeet-tdt-0.6b-v3` | `~2.5 GB`  | `mlx-community/whisper-large-v3-turbo` |    `~1.6 GB`     |
| **TTS**            | `openbmb/VoxCPM2`                    | `~5.0 GB`  | `Supertone/supertonic-3`               |   `~414.7 MB`    |
| **Turn Detection** | `mlx-community/smart-turn-v3`        | `~32.0 MB` | —                                      |        —         |
| **VAD (MLX)**      | `mlx-community/silero-vad`           | `~2.2 MB`  | —                                      |        —         |

## Adapter Requirements

Certain adapters require specific backends and dependencies to function correctly.

### OpenWakeWord (Wake-Word)

Requires pre-trained `.onnx` models for wake-word detection. You must install them before first use via the CLI:

```bash
uv run helomi-cli install
```

### Whisper & Parakeet (STT)

Relies on MLX backends for Apple Silicon hardware acceleration. Download the selected transcriber model before startup.

### VoxCPM2 (TTS)

Requires `openbmb/VoxCPM2` in the local Hugging Face cache. Denoising capabilities may require additional computational
overhead.
