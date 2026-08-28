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

- `install`: Install required acoustic models (e.g., OpenWakeWord onnx models).
- `say [profile_id]`: Start a live interactive speech-to-text and voice session in the terminal.
- `serve`: Start the local FastAPI server.
- `profiles`: List and format available profiles.
- `settings`: View current application settings.

## System Tray (`helomi_tray`)

A native macOS menu bar application built using `rumps`. It provides quick access to the assistant, allowing you to
monitor status, switch profiles, and toggle listening mode without opening a terminal window. It interacts with the core
engine via the local FastAPI server.
