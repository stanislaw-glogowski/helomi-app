# Profiles Configuration

Profiles define the persona and voice configuration for an assistant profile, such as wake-word model assets, TTS voice
styles, reference audio, ambient room audio, and STT language prompts.

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
    ├── alexa/
    │   ├── profile.yml
    │   ├── assets/
    │   │   └── ref_audio.wav
    │   └── models/
    │       └── alexa_v0.1.onnx
    ├── gizmo/
    │   ├── profile.yml
    │   ├── assets/
    │   │   └── circus_music.wav
    │   └── models/
    │       └── Hey_Gizmo_20260521_062457.onnx
    ├── trump/
    │   ├── profile.yml
    │   ├── assets/
    │   │   └── usa_anthem.wav
    │   └── models/
    │       └── Hey_Trump_20260816_230512.onnx
    └── defaults.yml
```

The profile ID is derived automatically from the directory name (e.g., `alexa`, `gizmo`, `trump`).

## Profile Attributes

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Display name of the assistant profile (e.g., `"Alexa"`). |
| `emoji` | `string` (optional) | Single emoji icon displayed in the macOS system tray when the profile is active (e.g. `👩🏻`, `🦆`). |
| `disabled` | `boolean` (optional) | Set to `true` to skip loading this profile (default: `false`). |
| `readonly` | `boolean` (optional) | Marks profile configuration as read-only (default: `false`). |
| `audio.room_voice_path` | `string` (optional) | Path to an audio file played in a continuous loop when the profile is active (`path://assets/...`). |
| `tts` | `object` | Configuration for TTS adapters (`supertonic`, `voxcpm2`). |
| `stt` | `object` | Configuration for STT adapters (`parakeet`, `whisper`). |
| `wakeword` | `object` | Configuration for wake-word adapters (`openwakeword`). |

## Default Profile Values (`defaults.yml`)

You can define base configuration values inherited by all profiles in `.helomi/profiles/defaults.yml`. Specific profile
definitions will automatically extend and override these defaults.

## Example `profile.yml`

Notice that `adapter` is **not** specified here — the active adapters are chosen in `settings.yml`:

```yaml
name: "Alexa"

emoji: "👩🏻"

audio:
  room_voice_path: "path://assets/room_sound.wav"

tts:
  supertonic:
    voice_name: "F1"
  voxcpm2:
    ref_audio: "path://assets/ref_audio.wav"

wakeword:
  openwakeword:
    model_path: "path://models/alexa_v0.1.onnx"
    threshold: 0.75

stt:
  parakeet:
    language: "en"
  whisper:
    language: "en"
```

## Disabling a Profile

To temporarily prevent a profile from loading regardless of active adapters, set:

```yaml
disabled: true
```
