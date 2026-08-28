# Helomi – Native Subsystem (Swift / macOS)

Package: `native/macos/avfaudio` -> Output: `src/helomi_core/audio/avfaudio/bin/avfaudio`

## Commands

```bash
./native/macos/build.sh                                           # Build & copy binary
swift format lint --recursive native/macos/avfaudio               # Lint
swift format format --in-place --recursive native/macos/avfaudio  # Format
swift test --package-path native/macos/avfaudio                   # Run Swift tests
```

## Rules

- **Zero Python dependency**: Standalone Swift binary communicating over stdio IPC (JSON/binary).
- **Concurrency & Memory**: Use `AVAudioEngine`/`CoreAudio`. Enforce Swift concurrency (`Sendable`, actors). No leaks in audio queues.
- **Distribution**: Binary is bundled via `hatch_build.py`. Touching `.swift` sources updates executable mtime.
