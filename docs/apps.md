# Applications

Helomi provides two interfaces for interacting with the core engine:

1. **System Tray Application (`helomi_tray`) — Primary Application**: A native macOS menu bar app designed for daily
   voice assistant interaction, profile switching, and background service control.
2. **Developer CLI (`helomi_cli`) — Developer Tooling**: A terminal user interface and automation CLI used for acoustic
   model installation, headless testing, and development debugging.

---

## System Tray Application (`helomi_tray`) — Primary Application

A native macOS menu bar application built with `rumps`. It embeds the `Runtime` directly, running quietly in the
background while providing instant visual status monitoring and profile controls.

### Launch

```bash
make run-tray
# or
uv run helomi-tray
```

### Status Bar Indicators

The tray icon changes dynamically based on the current state of the assistant:

| Icon        | State                                                    |
|-------------|----------------------------------------------------------|
| `🚀`        | Assistant runtime is starting up                         |
| `👂`        | Idle, listening for wake-words (no profile locked)       |
| `👩🏻` / `🦆` | Active profile (displays the profile's configured emoji) |
| `🤖`        | Active profile (fallback when no emoji is configured)    |
| `🦜`        | Parrot Mode extension is active (appended to title)      |
| `🎙️`        | Recording active (appended to title)                     |
| `💤`        | Application is shutting down                             |

### Menu & Keyboard Shortcuts

The tray menu provides rapid hotkey navigation:

- **Profile Switching (`0` – `8`):** Quickly switch between available voice profiles.
- **Toggle API Server (`a`):** Enable or toggle the FastAPI HTTP/SSE server extension for external integrations (such as
  the TypeScript web demo).
- **Toggle Parrot Mode (`p`):** Enable or toggle Parrot repetition mode for testing STT and TTS live.
- **Toggle Recording (`r`):** Start or pause recording synthesized assistant speech. When recording is active, the `🎙️`
  indicator appears in the menu bar title.
- **Save As … (`s`):** Open the native macOS save dialog (`NSSavePanel`) to export accumulated recording audio as a
  `.wav` file.
- **Quit Application (`q`):** Gracefully stops audio drivers, background threads, and shuts down the runtime. Can also
  be interrupted via `SIGINT` (`Ctrl+C`) or `SIGTERM`.

### Audio Recording & Export

The system tray application includes built-in audio recording for synthesized assistant responses:

1. Press **`r`** (or select **Recording** from the menu) to begin recording. The menu bar title will show the `🎙️`
   indicator.
2. Interact with the assistant or let it speak responses. Each synthesized speech chunk is captured in memory.
3. Toggle **`r`** again to stop recording. The recording remains buffered in memory.
4. Press **`s`** (or select **Save As …**) to open a native macOS `NSSavePanel` and save the recording to your desired
   location as a 48 kHz mono `.wav` file.

---

## Developer CLI (`helomi_cli`) — Developer Tooling

A command-line interface and Terminal User Interface (TUI) intended for developers, automated CI environments, and
headless operation.

### Usage

```bash
make run-cli -- [command]
# or
uv run helomi-cli [command]
```

### Key Commands

- `install`: Installs required acoustic models from OpenWakeWord releases (`embedding_model.onnx`,
  `melspectrogram.onnx`, `silero_vad.onnx`) to `resources/models/`, and the default profile wake-word model
  (`alexa_v0.1.onnx`) to `resources/profiles/alexa/models/`. Typically executed automatically via `make init`.
- `parrot [profile_id]`: Starts developer speech recognition in the terminal with real-time spoken repetition, rich
  model status display, and live event logging. If `profile_id` is omitted, defaults to `alexa`.
- `serve` (alias `server`): Starts the local FastAPI server directly in the terminal for speech pipeline orchestration
  and REST/SSE clients.

