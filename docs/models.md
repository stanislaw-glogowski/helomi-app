# Models & Adapters

Helomi supports running inference using local models directly from Hugging Face.

## Downloading Models

The application automatically downloads and caches models required by the configured adapters from Hugging Face. Ensure
you have an active internet connection on the first run. Models are cached locally using the standard Hugging Face
caching mechanism.

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
