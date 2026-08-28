# Models & Adapters

Helomi supports running inference using local models directly from Hugging Face.

## Downloading Models

The application automatically downloads and caches models required by the configured adapters from Hugging Face. Ensure
you have an active internet connection on the first run. Models are cached locally using the standard Hugging Face
caching mechanism.

If you prefer to pre-download them manually or want to use them offline, you can use the Hugging Face CLI:

```bash
# STT Models
huggingface-cli download mlx-community/parakeet-tdt-0.6b-v3
huggingface-cli download mlx-community/whisper-large-v3-turbo

# TTS Models
huggingface-cli download Supertone/supertonic-3
huggingface-cli download openbmb/VoxCPM2

# Smart Turn & VAD Models
huggingface-cli download mlx-community/smart-turn-v3
huggingface-cli download mlx-community/silero-vad
```

## Recommended Models (Default Settings)

The default configuration is designed to offer the best balance of speed and accuracy on Apple Silicon hardware. The
recommended default models are:

- **STT (Parakeet)**: `mlx-community/parakeet-tdt-0.6b-v3`
- **STT (Whisper)**: `mlx-community/whisper-large-v3-turbo`
- **TTS (Supertonic)**: `Supertone/supertonic-3`
- **TTS (VoxCPM2)**: `openbmb/VoxCPM2`
- **Turn Detection**: `mlx-community/smart-turn-v3`
- **VAD (Silero MLX)**: `mlx-community/silero-vad`

## Adapter Requirements

Certain adapters require specific backends and dependencies to function correctly.

### OpenWakeWord (Wake-Word)

Requires pre-trained `.onnx` models for wake-word detection. You must install them before first use via the CLI:

```bash
uv run helomi-cli install
```

### Whisper & Parakeet (STT)

Relies on MLX or ONNX backends for Apple Silicon hardware acceleration. Transcriber models are downloaded automatically
upon first use and cached.

### VoxCPM2 (TTS)

Requires the `openbmb/VoxCPM2` model. The application will pull the weights via the Hugging Face Hub. Denoising
capabilities may require additional computational overhead.
