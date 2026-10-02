# Settings Configuration

Helomi loads `settings.yml`, `settings.yaml`, or `settings.json` from the resources directory. The directory is resolved
in this order:

1. `$HELOMI_HOME`
2. The nearest `resources/` directory in the current working directory or one of its parents
3. `~/Library/Application Support/HelomiApp`

Create `settings.override.yml` (or `.yaml` / `.json`) next to the base file to override selected values. Dictionaries
are merged recursively; lists are replaced. `env://NAME` reads a required environment variable and `path://file`
resolves a path relative to the file that contains it. The configuration is strict: unknown fields, duplicate audio
drivers, and references to undefined routes fail at startup.

## Structure

```yaml
audio:
  initial_driver: avfaudio
  monitor_driver: avfaudio
  drivers:
  - avfaudio
  avfaudio:
    voice_processing: true
detection:
  turn:
    adapter: smart_turn
    smart_turn:
      model_id: mlx-community/smart-turn-v3
      threshold: 0.5
      max_audio_seconds: 30.0
      pre_roll_seconds: 0.5
      post_roll_seconds: 0.2
      min_speech_seconds: 0.3
      silence_seconds: 0.5
      fallback_silence_seconds: 1.8
      conversation_timeout_seconds: 30.0
  vad:
    adapter: silero_vad
    silero_vad:
      engine: mlx
      model_id: mlx-community/silero-vad
    options:
      threshold: 0.5
  wakeword:
    adapter: openwakeword
    openwakeword:
      threshold: 0.75
      patience: 2
      embedding_path: path://models/embedding_model.onnx
      melspec_path: path://models/melspectrogram.onnx
      frame_size: 1280
transcription:
  adapter: parakeet
  parakeet:
    model_id: mlx-community/parakeet-tdt-0.6b-v3
  options:
    language: en
synthesis:
  adapter: voxcpm2
  voxcpm2:
    model_id: openbmb/VoxCPM2
    load_denoiser: false
app:
  conversation:
    persistent_profile: true
    wakeword: true
    reactions: true
    room_voice: true
    playback_ack_timeout: 5.0
  server:
    host: 127.0.0.1
    port: 4356
  response_mode: parrot
```

`adapter` selects one named configuration in each speech section. Shared domain parameters live in `options`:
VAD uses `options.threshold`, and transcription uses `options.language`. Silero currently supports only `engine: mlx`.
Audio `drivers` lists enabled driver IDs; driver parameters live in the matching named sections. Omit `monitor_driver`
or set it to YAML `null` to disable monitoring.

You can keep configurations for every supported adapter or driver in the same file. Inactive sections are discarded
before environment variables, file paths, and model-cache entries are validated. Missing or `null` active sections use
an empty object and model defaults; required fields still produce an error. Unknown section names and fields in active
configurations are rejected. Changing a selector takes effect on the next application startup.

`app` is kept as a dictionary by runtime and parsed into application settings by `Application` before components mount.
The supported response modes are `api`, `parrot`, and `operator`. Rename the old `application` key to `app`; the previous
flat adapter configurations and object-valued audio `drivers` list must also be migrated to the format above.

There is no default profile. A profile is activated only by an explicit CLI/tray choice, a local wake word, or a
Twilio callee mapping. Running `helomi-cli parrot` without a profile therefore requires wake-word detection.

## Enabling inbound Twilio

Twilio is opt-in. Add both drivers because an override replaces the complete `drivers` list:

```yaml
audio:
  initial_driver: avfaudio
  monitor_driver: avfaudio
  drivers:
  - avfaudio
  - twilio
  avfaudio:
    voice_processing: true
  twilio:
    auth_token: env://TWILIO_AUTH_TOKEN
    public_url: env://TWILIO_PUBLIC_URL
    port: 4357
    allowed_callers:
    - '+15555550101'
    handshake_timeout: 10.0
    session_ttl: 30.0
    validate_signature: true
    output_buffer_chunks: 50
```

`TWILIO_PUBLIC_URL` is the exact public HTTPS URL routed to the Twilio driver root, including any proxy path prefix.
Configure that URL as the number's incoming voice webhook using `POST`. Signature validation is enabled by default and
uses the externally visible URL, including forwarded proxy headers and every form parameter.

Map the called number to the supported profile in `resources/profiles/alexa/profile.override.yml`:

```yaml
audio:
  twilio:
    callees:
      - "+15555550100"
```

A callee may belong to only one profile. A second simultaneous call is rejected as busy.
