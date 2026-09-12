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

Profiles are stored in the `resources/profiles/` directory. Each profile has its own subdirectory containing a
`profile.yml` (or `.json`) file:

```text
resources/
└── profiles/
    ├── alexa/
    │   ├── profile.yml
    │   ├── assets/
    │   │   └── ref_audio.wav
    │   ├── models/
    │   │   └── alexa_v0.1.onnx
    │   └── prompts/
    │       └── demo.md
    └── defaults.yml
```

The profile ID is derived automatically from the directory name (e.g., `alexa`).

## Profile Attributes

| Field                   | Type                      | Description                                                                                                           |
|-------------------------|---------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `name`                  | `string`                  | Display name of the assistant profile (e.g., `"Alexa"`).                                                              |
| `description`           | `string` (optional)       | Description or persona definition for the assistant profile (e.g. `"Friendly voice assistant"`).                     |
| `priority`              | `integer` (optional)      | Sort priority for profile catalog ordering (higher numbers sorted first; default: `1`).                              |
| `emoji`                 | `string` (optional)       | Single emoji icon displayed in macOS system tray when active (e.g. `👩🏻`, `🦆`; default: `👤`).                        |
| `disabled`              | `boolean` (optional)      | Set to `true` to skip loading this profile (default: `false`).                                                        |
| `readonly`              | `boolean` (optional)      | Marks profile configuration as read-only (default: `false`).                                                          |
| `reactions.greeting`    | `list[string]` (optional) | Spoken greetings randomly selected when the profile is activated / wake-word detected (e.g., `["Hello! How can I help?", "Hi there! I'm listening."]`). |
| `reactions.interrupted` | `list[string]` (optional) | Spoken reactions randomly selected when the assistant's ongoing speech is interrupted (barge-in) (e.g., `["Yes?", "I'm listening."]`). |
| `audio.room_voice_path` | `string` (optional)       | Path to an audio file played in a continuous loop when the profile is active (`path://assets/...`).                   |
| `tts`                   | `object`                  | Configuration for TTS adapters (`supertonic`, `voxcpm2`).                                                             |
| `stt`                   | `object`                  | Configuration for STT adapters (`parakeet`, `whisper`).                                                               |
| `wakeword`              | `object`                  | Configuration for wake-word adapters (`openwakeword`).                                                                |

## Profile Prompts & Templates

Profiles can define modular prompt templates stored in the `prompts/` subdirectory within the profile folder, as well
as shared templates in `resources/prompts/`:

```text
resources/
├── prompts/
│   └── demo/
│       └── instructions.md     # Shared formatting / instructions template
└── profiles/
    └── alexa/
        ├── profile.yml
        └── prompts/
            └── demo.md          # Profile-specific prompt template
```

### Prompt Parameter Substitution (`PromptReader`)

Helomi's prompt engine (`PromptReader`) parses markdown prompts and dynamically interpolates parameters enclosed in
`{{ parameter }}` tags:

- Built-in profile parameters: `{{ name }}`, `{{ description }}`.
- Global / system parameters passed during catalog initialization.

```markdown
You are {{ name }}, {{ description }}.
Always answer concisely and naturally.
```

Loaded prompts are accessible on the profile via `profile.prompts["<prompt_name>"]` (e.g. `profile.prompts["demo"]`)
and can be requested through the API with the `require_prompt` query parameter.

## Spoken Reactions (`reactions`)

Profiles can define verbal acknowledgements that the assistant synthesizes and speaks in response to lifecycle events:

- **`greeting`**: Triggered when a profile is activated (e.g., when the wake-word is detected). The assistant randomly
  picks one phrase from the configured list.
- **`interrupted`**: Triggered when speech playback is actively interrupted by the user (barge-in).

```yaml
reactions:
  greeting:
    - "Hello! How can I help you?"
    - "Hi there! I'm listening."
  interrupted:
    - "Yes?"
    - "I'm listening."
```

## Default Profile Values (`defaults.yml`)

You can define base configuration values inherited by all profiles in `resources/profiles/defaults.yml`. Specific
profile definitions will automatically extend and override these defaults.

## Example `profile.yml`

Notice that `adapter` is **not** specified here — the active adapters are chosen in `settings.yml`:

```yaml
name: "Alexa"

description: "Helpful and friendly voice assistant"

priority: 1

emoji: "👩🏻"

reactions:
  greeting:
    - "Hello! How can I help you?"
    - "Hi there! I'm listening."
  interrupted:
    - "Yes?"
    - "I'm listening."

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
