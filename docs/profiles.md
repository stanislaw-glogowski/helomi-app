# Profiles Configuration

Profiles define the behavior of the voice assistant, including which STT/TTS adapters to use, wake-word settings, and
reference audio properties.

## Creating a Profile

Profiles are stored in the `resources/profiles/` directory. Each profile has its own subdirectory containing a
`profile.yml` (or `.json`) file.

```text
resources/
└── profiles/
    ├── default/
    │   └── profile.yml
    └── my_profile/
        └── profile.yml
```

The profile ID is derived automatically from the directory name (e.g., `default`, `my_profile`).

## Default Profile

You can specify default settings for all profiles in `resources/profiles/defaults.yml`. Specific profile configurations
will seamlessly extend and override these defaults.

## Example `profile.yml`

```yaml
name: "My Custom Assistant"
wakeword:
  adapter: "openwakeword"
  openwakeword:
    models: [ "hey_helomi" ]
tts:
  adapter: "voxcpm2"
  voxcpm2:
    ref_audio: "/absolute/path/to/my/voice.wav"
    inference: 7
```
