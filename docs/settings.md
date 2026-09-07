# Settings Configuration

Helomi uses a hierarchical configuration system. The application locates its configuration and resources directory
(`resources/`) using the following precedence:

1. **Environment Variable:** `$HELOMI_HOME` (if set)
2. **Local Workspace:** `resources/` in the current working directory or parent directories (e.g.
   `./resources/settings.yml`)
3. **macOS System Default:** `~/Library/Application Support/HelomiApp/settings.yml`

## File Format

Settings can be defined using YAML or JSON formats (e.g., `settings.yml` or `settings.json`).

## Overriding Settings

You can override specific settings without modifying the main configuration file by creating an override file in the
same directory:

- `settings.override.yml`
- `settings.override.json`

The application will automatically merge the override file with the base settings.

## Relative Paths (`path://` prefix)

When defining paths in your configuration files (e.g., paths to local ONNX models or reference audio files), you can use
the `path://` prefix. This tells the application to resolve the path relative to the directory where the configuration
file itself is located.

**Example:**
`path://models/silero_vad.onnx` will resolve to the `models/` directory next to your `settings.yml` file.

## Adapter Configuration

Adapters for speech components (`stt`, `tts`, `turn`, `vad`, `wakeword`) are configured **only in `settings.yml`** (or
`settings.override.yml`), never in individual `profile.yml` files:

- `stt.adapter`: `parakeet` or `whisper`
- `tts.adapter`: `supertonic` or `voxcpm2`
- `turn.adapter`: `smart_turn`
- `vad.adapter`: `silero_vad`
- `wakeword.adapter`: `openwakeword`

> [!IMPORTANT]
> The active adapter configured here dictates which profiles can be loaded. When Helomi starts, it inspects every
profile in `resources/profiles/`. If a profile lacks configuration for the currently active STT or TTS adapter, that
profile is **automatically skipped**.

## Example Configuration

`resources/settings.yml`:

```yaml
profile:
  default: "alexa"

server:
  host: "127.0.0.1"
  port: 4356

audio:
  adapter: "avfaudio"
  avfaudio:
    voice_processing: true

stt:
  adapter: "parakeet"
  parakeet:
    model_id: "mlx-community/parakeet-tdt-0.6b-v3"
    language: "en"

tts:
  adapter: "voxcpm2"
  supertonic:
    model_id: "Supertone/supertonic-3"
    language: "en"
  voxcpm2:
    model_id: "openbmb/VoxCPM2"
    load_denoiser: false

turn:
  adapter: "smart_turn"
  smart_turn:
    model_id: "mlx-community/smart-turn-v3"
    threshold: 0.5

vad:
  adapter: "silero_vad"
  silero_vad:
    engine: "mlx"
    model_id: "mlx-community/silero-vad"

wakeword:
  adapter: "openwakeword"
  openwakeword:
    embedding_path: "path://models/embedding_model.onnx"
    melspec_path: "path://models/melspectrogram.onnx"
```

