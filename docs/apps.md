# Applications

Helomi provides multiple interfaces for interacting with the core engine.

## CLI Application (`helomi_cli`)

A feature-rich Terminal User Interface (TUI) for managing the assistant directly from the command line.

**Usage:**

```bash
make run-cli -- [command]
# or
uv run helomi-cli [command]
```

**Key Commands:**

- `install`: Installs required acoustic models from OpenWakeWord releases (`embedding_model.onnx`, `melspectrogram.onnx`, `silero_vad.onnx`) to `.helomi/models/`, and the default profile wake-word model (`alexa_v0.1.onnx`) to `.helomi/profiles/alexa/models/`.
- `parrot [profile_id]`: Starts live speech recognition with real-time spoken repetition, rich model status, and live event monitoring. If `profile_id` is not specified, uses the configured default profile (`alexa`).
- `serve` (alias `server`): Starts the local FastAPI server for speech pipeline orchestration and REST/SSE clients.

---

## System Tray (`helomi_tray`)

A native macOS menu bar application built with `rumps`. It embeds the `Runtime` directly, offering convenient status monitoring and voice switching.

**Launch:**

```bash
make run-tray
# or
uv run helomi-tray
```

### Status Bar Indicators

| Icon | State |
|---|---|
| `🚀` | Assistant runtime is starting up |
| `👂` | Idle, listening for wake-words (no profile locked) |
| `👩🏻` / `🦆` | Active profile (displays the profile's configured emoji) |
| `🤖` | Active profile (fallback when no emoji is configured) |
| `🦜` | Parrot Mode extension is active |
| `💤` | Application is shutting down |

### Menu & Keyboard Shortcuts

- **Profile Switching (`0` – `8`):** Quickly toggle voice profiles.
- **Toggle API Server (`a`):** Enable or switch to the FastAPI HTTP/SSE server extension.
- **Toggle Parrot Mode (`p`):** Enable or switch to Parrot repetition mode.
- **Quit Application (`q`):** Gracefully stops audio drivers, background threads, and shuts down runtime. Can also be interrupted via `SIGINT` (`Ctrl+C`) or `SIGTERM`.
