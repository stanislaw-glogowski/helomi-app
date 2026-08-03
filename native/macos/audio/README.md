# Helomi native audio helper

`audio` is Helomi's macOS audio-device process. It owns microphone capture,
48 kHz TTS playback, Apple Voice Processing, and playback interruption in one
`AVAudioEngine` session. It extracts a mono capture stream from Voice Processing;
the Python adapter resamples it to the 16 kHz model format.

The helper communicates with Python over versioned framed binary messages on
standard input and output. Protocol version 3 carries interleaved Float32 audio,
request identifiers, playback outcomes, gain acknowledgements, diagnostics, and
selected-device information. `AVFAudioDriver` starts and stops it; it is not a
daemon and owns no user configuration.

Build, test, and package it from the repository root:

```bash
swift format lint --recursive native/macos/audio
swift test --package-path native/macos/audio
native/macos/build.sh
```

The build places the release binary in
`src/helomi/speech/audio/adapters/avfaudio/bin/audio` for packaging. A protocol
change must update the Swift helper, Python adapter and process code, fake
helper, Swift tests, Python tests, and protocol version together.

See [the architecture guide](../../../docs/architecture/native-audio.md) for
the Python/Swift ownership boundary.
