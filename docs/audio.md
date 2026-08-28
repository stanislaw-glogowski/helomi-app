# Reference Audio

TTS adapters, such as VoxCPM2, support voice cloning through reference audio samples.

## Format Guidelines

The reference audio should be a clean, noise-free recording of the target voice.

- **Format:** `.wav`
- **Channels:** Mono
- **Length:** Typically 10 to 20 seconds of clear, uninterrupted speech

*Note: Ensure the sample rate matches the specific TTS engine requirements (often 16kHz or 24kHz).*

## Connecting Reference Audio (VoxCPM2)

To use your reference audio with VoxCPM2, specify the absolute path to the `.wav` file in your `profile.yml`:

```yaml
tts:
  adapter: "voxcpm2"
  voxcpm2:
    ref_audio: "/absolute/path/to/reference_audio.wav"
    inference: 7
    cfg_value: 2.6
```

Ensure the file has proper read permissions for the application.
