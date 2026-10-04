# Profiles Configuration

Profiles provide persona data and per-adapter voice settings. The supported public profile is `alexa`, stored in
`resources/profiles/alexa/`. The directory name is its ID; no profile is implicitly selected as a default.

Global driver and adapter choices live in `settings.yml`. A profile can store settings for every supported adapter;
only selected adapters and enabled audio drivers are retained and validated after defaults and overrides are merged.

A profile without the selected synthesis configuration, or with that configuration set to `null`, is excluded from
the catalog. An explicit `{}` declares support using adapter defaults; invalid active configuration produces an error
with the profile ID and source file. A missing selected transcription configuration uses defaults and the global
`transcription.options.language`, which a profile can override.

A missing wake-word configuration leaves the profile available for manual or Twilio activation, without wake-word
activation. Disabling global wake-word detection discards all profile wake-word configurations. Inactive variants do
not require their environment variables, model files, or assets. Twilio mappings and reactions use the filtered catalog.

## Layout

```text
resources/profiles/
├── defaults.yml
└── alexa/
    ├── profile.yml
    ├── profile.override.yml        # optional, local configuration
    ├── assets/
    │   └── ref_audio.wav
    ├── models/
    │   └── alexa_v0.1.onnx
    └── prompts/
        └── demo.md
```

`defaults.yml` is merged into each profile before validation. A profile-specific override file is merged last.

## Schema

```yaml
name: "Alexa"
description: "Helpful and friendly voice assistant"
priority: 1
emoji: "👩🏻"
disabled: false
readonly: false

reactions:
  connected:
    - "Hello, Alexa speaking. How can I help?"
  greeting:
    - "Hello! How can I help you?"
  farewell:
    - "Goodbye!"

audio:
  avfaudio:
    room_voice:
      path: path://assets/ambient.wav
      volume: 0.25
      ducking: 0.35
  twilio:
    callees:
      - "+15555550100"
    room_voice:
      path: path://assets/call-ambient.wav
      volume: 0.18
      ducking: 0.45

transcription:
  parakeet:
    language: en
  whisper:
    language: en

synthesis:
  supertonic:
    voice_name: F1
    language: en
  voxcpm2:
    ref_audio: path://assets/ref_audio.wav

wakeword:
  openwakeword:
    model_path: path://models/alexa_v0.1.onnx
```

Room voice is configured independently for each audio driver. `volume` and `ducking` are normalized values from `0.0`
to `1.0`. Twilio mixes the loop with clean speech before μ-law/8 kHz encoding; exported TTS audio never contains the
ambient track.

Automatic greetings play once when a new profile session begins through wake-word activation; CLI and tray activation
remain silent. The automatic `connected` reaction starts two seconds after an inbound phone call begins. Explicit
reaction commands remain immediate. Farewells are used for controlled shutdown and wait for a bounded playback
acknowledgement. Barge-in is deliberately silent: it clears stale playback immediately and does not speak an
interruption reaction.

## Prompts

Markdown files under a profile's `prompts/` directory are exposed through `profile.prompts`. Templates may use
`{{ name }}`, `{{ description }}`, and shared parameters. A requested missing prompt excludes the profile from list
results and produces `404` for a single-profile API request.

Set `disabled: true` to exclude the profile from the catalog. `readonly` is public metadata; it does not select or
activate a profile.
