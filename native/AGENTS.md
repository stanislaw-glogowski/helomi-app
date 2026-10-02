# Native AVFAudio

```bash
./native/macos/build.sh
swift format lint --recursive native/macos/avfaudio
swift test --package-path native/macos/avfaudio
```

Keep the Swift helper standalone and communicate only through its versioned stdio wire protocol. Preserve message
IDs and payload compatibility across Python and Swift. Enforce Swift concurrency and avoid blocking audio callbacks.
The bundled binary belongs in `src/helomi_runtime/audio/avfaudio/bin/avfaudio`.
