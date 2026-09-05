# Profiles Configuration

Profiles define the persona and voice configuration for an assistant profile, such as wake-word model assets, TTS voice
styles, reference audio, and STT language prompts.

> [!IMPORTANT]
> **Adapters are configured exclusively in `settings.yml`**, never in `profile.yml`.
>
> In `profile.yml`, you only provide the configuration parameters for the adapters (e.g. `wakeword.openwakeword`,
`tts.voxcpm2`, `stt.parakeet`).
> If a profile does not include a configuration section for the currently active STT or TTS adapter specified in
`settings.yml`, that profile is **automatically skipped** and will not be loaded into the catalog.

## Creating a Profile

Profiles are stored in the `.helomi/profiles/` directory. Each profile has its own subdirectory containing a
`profile.yml` (or `.json`) file:

```text
.helomi/
└── profiles/
    ├── default/
    │   ├── profile.yml
    │   └── models/
    │       └── alexa_v0.1.onnx
    └── my_profile/
        ├── profile.yml
        └── voice.wav
```

The profile ID is derived automatically from the directory name (e.g., `default`, `my_profile`).

## Default Profile Values (`defaults.yml`)

You can define base configuration values inherited by all profiles in `.helomi/profiles/defaults.yml`. Specific profile
definitions will automatically extend and override these defaults.

## Example `profile.yml`

Notice that `adapter` is **not** specified here — the active adapters are chosen in `settings.yml`:

```yaml
name: "My Custom Assistant"

wakeword:
  openwakeword:
    model_path: "path://models/hey_helomi.onnx"
    threshold: 0.75

tts:
  voxcpm2:
    ref_audio: "path://voice.wav"
    inference: 7
    cfg_value: 2.6

stt:
  whisper:
    language: "en"
```

## Disabling a Profile

To temporarily prevent a profile from loading regardless of active adapters, set:

```yaml
disabled: true
```

