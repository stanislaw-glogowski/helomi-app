# Audio Pipeline & Audio Assets

Helomi utilizes a native macOS CoreAudio / `AVFAudio` engine to achieve low-latency audio capture and playback with hardware acceleration.

## Native Audio Engine (`AVFAudio`)

The native audio engine bridge handles real-time microphone capture, synthesized speech playback, and ambient soundscapes.

### Apple Voice Processing (Echo Cancellation)

You can enable macOS system-level hardware acoustic echo cancellation (AEC) and automatic gain control in `.helomi/settings.yml`:

```yaml
audio:
  adapter: "avfaudio"
  avfaudio:
    voice_processing: true
```

When enabled, output speech played through speakers is automatically subtracted from the microphone capture buffer, minimizing accidental self-triggering and speech barge-in confusion.

---

## Room Voice / Ambient Audio Loop

Profiles can specify an ambient background audio track (room voice) that plays continuously while that profile is active:

```yaml
audio:
  room_voice_path: "path://assets/ref_audio.wav"
```

- **Format:** `.wav` (PCM)
- **Lifecycle:** Starts playing seamlessly when the profile is activated, and stops automatically when switching profiles or deactivating the assistant.

---

## Reference Audio (Voice Cloning with VoxCPM2)

TTS adapters, such as VoxCPM2, support voice style cloning through reference audio samples.

### Format Guidelines

The reference audio should be a clean, noise-free recording of the target voice:

- **Format:** `.wav`
- **Channels:** Mono
- **Length:** Typically 10 to 20 seconds of clear, uninterrupted speech
- **Sample Rate:** Matches TTS engine requirements (16kHz or 24kHz)

### Configuring Reference Audio

To use reference audio with VoxCPM2, specify the path to the `.wav` file in your `profile.yml` (or `defaults.yml`):

```yaml
tts:
  voxcpm2:
    ref_audio: "path://assets/ref_audio.wav"
    inference: 7
    cfg_value: 2.6
```

And ensure the VoxCPM2 adapter is active in `settings.yml`:

```yaml
tts:
  adapter: "voxcpm2"
```
