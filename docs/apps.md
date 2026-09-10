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

The tray icon and title change dynamically based on the current state of the assistant:

| Icon            | State                                                            |
|-----------------|------------------------------------------------------------------|
| `⠋` … `⠏`       | Assistant runtime is starting up (animated spinner)              |
| `👂`            | Idle, listening for wake-words (no profile locked)               |
| *Profile Emoji* | Active profile (displays configured emoji, e.g. `👩🏻`, `🦆`)      |
| `👤`            | Active profile (fallback when no emoji is configured in profile) |
| `🦜`            | Parrot Mode extension is active                                  |
| `🗣️`            | Text-to-Speech (TTS) mode is active                              |
| `☾`            | Application is shutting down                                     |

The menu bar title follows the format `<Icon> <Label>`, where `<Label>` displays the active profile name (e.g.
`👩🏻 Alexa`, `🗣️ Alexa`, `🦜 Alexa`) or `Helomi` when no profile is locked (e.g. `👂 Helomi`, `☾ Helomi`).

### Menu & Keyboard Shortcuts

The tray menu provides rapid hotkey navigation:

- **Profile Switching (`0` – `8`):** Quickly switch between available voice profiles.
- **Settings Submenu:**
    - **Room Voice:** Toggle ambient background audio playback for profiles that define `audio.room_voice_path`.
    - **Wake Word:** Toggle wake-word listening. When unchecked, wake-word detection is disabled, the active profile
      remains active across conversations without auto-deactivating, and initial greeting reactions are suppressed.
    - *(Note: Settings are dynamically disabled while TTS mode is active).*
- **Toggle API Server (`a`):** Enable or toggle the FastAPI HTTP/SSE server extension for external integrations (such as
  the TypeScript web demo).
- **Toggle Parrot Mode (`p`):** Enable or toggle Parrot repetition mode for testing STT and TTS live.
- **Text to Speech (`t`):** Open the dedicated Text-to-Speech (TTS) synthesis window. Automatically pauses other
  extension modes while open and restores the previous mode upon close.
- **Quit Application (`q`):** Gracefully stops audio drivers, background threads, and shuts down the runtime. Can also
  be interrupted via `SIGINT` (`Ctrl+C`) or `SIGTERM`.

### Dedicated TTS Window & Audio Export

Selecting **Text to Speech** (`t`) opens a native macOS Cocoa window (`TTSWindow`) for interactive speech synthesis and
audio file export:

- **Multi-line Text Editor:** Supports tag auto-completion (e.g. `[laugh]`, `[sigh]`, `[whisper]`, `[gasp]`).
- **Native Clipboard & Editing:** Full Cocoa Edit menu support for `Cmd+V` (paste), `Cmd+C` (copy), `Cmd+A` (select
  all), `Cmd+Z` (undo), and `Cmd+X` (cut).
- **Speaker Feedback Isolation:** While TTS mode is active, microphone capture is bypassed so that speaker output does
  not cause false barge-in self-interruptions (`"Tak?"`).
- **Send Button:** Synthesizes and plays the input text using the currently active profile without playing unintended
  greeting reactions.
- **Save to … Button:** Accumulates synthesized speech into an audio buffer and triggers a native macOS `NSSavePanel`
  dialog to export the audio as a 48 kHz mono `.wav` file (`<profile_id>_<YYYYMMDD_HHMMSS>.wav`).
- **Close Button:** Closes the window and automatically restores the previous operating mode (`Server`, `Parrot`, or
  idle).

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

