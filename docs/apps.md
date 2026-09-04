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
- `parrot [profile_id]`: Start live speech recognition with real-time spoken repetition, rich model status, and live event monitoring.
- `serve` (alias `server`): Start the local FastAPI server for speech pipeline orchestration and REST/SSE clients.

## System Tray (`helomi_tray`)

A native macOS menu bar application built using `rumps` and `BaseComponent`. It embeds the `Runtime` directly, allowing you to:
- Monitor speech assistant status with dynamic status bar icons.
- Switch and toggle active voice profiles from the menu bar.
- Dynamically toggle between running extensions: **API Server** mode and **Parrot Mode**.
- Gracefully shut down all background workers and processes upon exit.

