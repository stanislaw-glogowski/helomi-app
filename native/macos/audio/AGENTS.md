# Native audio instructions

This Swift package owns Helomi's single full-duplex AVAudioEngine helper process:
capture, playback, Voice Processing, and interruption. Its framed binary
stdin/stdout protocol is owned jointly with the Python AVFAudio adapter.

Treat every protocol change as a synchronized update to Swift, Python protocol
and process code, `tests/fixtures/fake_avfaudio_helper.py`, Swift tests, Python
tests, and the protocol version. Keep tests hardware-independent; device checks
remain manual validation. See [`README.md`](README.md) for the protocol overview
and [`docs/configuration.md`](../../../docs/configuration.md) for audio settings.

```bash
swift format lint --recursive native/macos/audio
swift test --package-path native/macos/audio
```
