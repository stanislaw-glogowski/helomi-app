# Changelog

All notable changes to Helomi are documented in this file.

## [Unreleased]

### Added

- **Default Profile (`alexa`)**:
    - Established `alexa` as the official default assistant profile across `resources/settings.yml`, `Profile.DEFAULT_ID`, and CLI/API interfaces.
    - Automatic wake-word model installation for Alexa (`alexa_v0.1.onnx`) into `resources/profiles/alexa/models/` via `helomi-cli install`.
- **Profile Customization (`emoji`, `readonly`, `room_voice_path`)**:
    - Added `emoji` field to `Profile` with single-emoji validation, displayed in the macOS system tray when the profile is active.
    - Added `readonly` flag to `Profile` model schema.
    - Added `audio.room_voice_path` to support continuous ambient room soundscapes upon profile activation.
- **Enhanced macOS System Tray (`helomi_tray`) UX**:
    - Added keyboard shortcuts for rapid menu actions: profile selection (`0`–`8`), API Server (`a`), Parrot Mode (`p`), and quitting (`q`).
    - Added dynamic status bar icons: active profile emoji (or `🤖` fallback), idle listening (`👂`), parrot mode (`🦜`), and exiting (`💤`).
    - Implemented clean signal handling for `SIGINT` (`Ctrl+C`) and `SIGTERM`.

### Changed

- **Resources Directory Migration**:
    - Migrated local workspace configuration and resources directory from `.helomi/` to `resources/` (`resources/settings.yml`, `resources/profiles/`, `resources/models/`).
    - Updated `.gitignore` patterns and `UserData` search paths to target `resources/`.
- **Audio Driver Architecture (`AudioDriver`)**:
    - Replaced `start_room_voice()` and `stop_room_voice()` with profile-aware lifecycle hooks `activate(profile: AudioProfile)` and `deactivate()`.
    - Streamlined native Swift `AVFAudio` engine wire protocol (`startRoomVoice` payload with file path, removed deprecated audio device listing).
- **Pipeline Robustness & Input Filtering**:
    - Added whitespace and empty text validation in `SayText` command handling and `ParrotExtension`, avoiding redundant TTS synthesis.
    - Wrapped audio driver activation in `PipelineService` with graceful error recovery to prevent audio playback errors from blocking assistant activation.
- **Documentation & Examples Overhaul**:
    - Added Hugging Face CLI (`hf` / `huggingface-cli`) prerequisite and model download guide with explicit disk size requirements (`~7.5 GB` default stack) to `README.md` and `docs/models.md`.
    - Promoted macOS system tray application (`helomi_tray` / `make run-tray`) as the primary user-facing application across `README.md`, `docs/apps.md`, and `docs/examples.md`, framing `helomi_cli` as developer and automation tooling.
    - Updated all documentation (`README.md`, `docs/profiles.md`, `docs/settings.md`, `docs/audio.md`, `docs/apps.md`, `docs/api.md`, `docs/examples.md`) to reflect `resources/` workspace directory, `alexa` as the default profile, `avfaudio.voice_processing`, ambient audio, and system tray shortcuts.
    - Updated TypeScript demo client (`demo/README.md`) to pair with `prompts/profiles/alexa.md`.

### Fixed

- Implemented `activate` and `deactivate` in `MockAudioDriver` test fixture to satisfy abstract interface requirements.
- Updated `TrayApp._render_title` test invocations to match the new positional parameter signature.
- Fixed `Profile.model_post_init` to safely handle missing or non-dict initialization context.
- Expanded automated unit test suite to 174 passing tests with 95.97% branch coverage.

## [0.6.0] - 2026-09-04

### Added

- **Application Layer (`helomi_app`)**:
    - Introduced `Runtime` context manager managing lifecycle and lazy component acquisition.
    - Added `PipelineService` orchestrating the event-driven speech processing loop (`_capture_loop`, `_detection_loop`,
      `_stt_loop`, `_tts_loop`).
    - Added `UserData` resource catalog supporting local storage paths (`.helomi/`).
    - Added modular extensions: `ParrotExtension` for speech echo and `ServerExtension` for FastAPI server hosting.
- **Enhanced CLI Commands & Interactive UX**:
    - `helomi-cli parrot [profile_id]`: Live speech-to-text with spoken echoing, rich status indicators, active profile
      overview, and asynchronous event streaming.
    - `helomi-cli serve` (alias `server`): Enhanced server startup with spinner animation, formatted banner, available
      profiles list, and REST/SSE endpoint table.
    - Reusable `Spinner` widget integrated with logger proxy for non-intrusive CLI status indicators.
- **Extended REST & SSE Endpoints**:
    - Added `GET /api/v1/health` for service health checks.
    - Added `GET /api/v1/profile` and `GET /api/v1/profile/{id}` for querying profile configurations.
    - Extended `GET /api/v1/speech` SSE streaming and `POST /api/v1/speech` command execution (`ActivateProfile`,
      `DeactivateProfile`, `SayText`).
- **Modernized macOS System Tray (`helomi_tray`)**:
    - Rewrote `TrayApp` to embed `Runtime` directly, enabling real-time switching between API Server mode and Parrot
      mode from the menu bar.
    - Implemented threaded asynchronous worker lifecycle with automatic UI synchronization and signal handling.
- **Coding & Documentation Standards**:
    - Explicit rule added to `AGENTS.md` requiring all code, docstrings, comments, log/error messages, and CLI/tray
      output to strictly be in English.

### Changed

- Consolidated application runtime, pipeline service, and server extensions (`helomi_app`) directly into `helomi_core`,
  streamlining the architecture to three primary layers (`helomi_common`, `helomi_core`, and UI layers `helomi_cli` / `helomi_tray`).
- Enhanced speech pipeline orchestration in `PipelineService`:
    - Introduced generation tracking (`PipelineRequest`) to invalidate outdated audio synthesis tasks on speech interruption.
    - Decoupled audio playback into dedicated `_playback_queue` and `_playback_loop`.
    - Added `SpeechInterrupted` event dispatched when user speech interrupts ongoing playback.
    - Added extension lifecycle management (`register_extension`, `set_active_extension`) with extension-scoped command and event filtering.
- Migrated user resources directory from `resources/` to `.helomi/` (`.helomi/settings.yml`, `.helomi/profiles/`).
- Modularized CLI command handlers into `helomi_cli/commands/` (`install.py`, `parrot.py`, `serve.py`) with rich banner widgets (`prints.py`).
- Removed deprecated CLI commands (`say`, `settings`).
- Standardized component lifecycle inheritance across the codebase (`BaseComponent`, `PipelineComponent`).

### Fixed

- Fixed PEP 479 `RuntimeError` by returning cleanly from async generators (`Session.subscribe_event` and
  `PipelineService.subscribe_event`).
- Fixed file suffix checking in `AbstractFile` and `ConfigFile` by replacing invalid identity checks with membership
  tests.
- Added `exist_ok=True` to `AbstractFile.as_dir` to prevent race conditions during directory creation.
- Fixed string identity comparison in FastAPI router session profile validation.
- Prevented recursive label prefix accumulation in `BaseComponent.__init_subclass__`.
- Fixed wave audio byte length validation in unit tests.

## [0.5.0] - 2026-08-28

### Added

- **Complete Architectural Refactoring**: Redesigned the entire codebase into strict layered packages:
    - `helomi_common`: Core base models, validation schemas (`BaseConfig`, `AdapterConfig`, `AdapterExtractor`),
      `HFModel` model resolver, and logging proxy.
    - `helomi_core`: Audio orchestration, worker lifecycles, VAD/wake-word/STT/TTS adapters, unified event-driven
      `Orchestrator`, local FastAPI server, and catalog/store configuration.
    - `helomi_cli`: Terminal UI powered by `rich`, featuring subcommands (`say`, `serve`, `install`, `profile.py`,
      `envelope.py`).
    - `helomi_tray`: macOS system tray application built with `rumps`.
    - `native/macos/avfaudio`: Native Swift helper for macOS CoreAudio/AVFAudio with Apple Voice Processing (Echo
      Cancellation).
- **Voice Cloning & Advanced Neural TTS**:
    - Supertonic TTS engine supporting both built-in voice styles (F1–F5, M1–M5) and custom voice style cloning from
      audio files (`voice_path`), with configurable inter/intra thread parallelism.
    - VoxCPM2 streaming neural voice synthesis with reference audio cloning (`ref_audio`), timesteps tuning, denoising,
      and CFG control.
- **Dual-Backend VAD & Turn Detection**:
    - Silero VAD adapter supporting both Apple Silicon **MLX** and **ONNX Runtime** execution engines.
    - Smart Turn adapter for intelligent end-of-turn detection.
- **Fast Speech Recognition (STT)**:
    - Integrated Parakeet TDT and MLX-Whisper Turbo inference engines.
- **Offline-First HuggingFace Model Resolution (`HFModel`)**:
    - Automatic local cache resolution for models (`snapshot_download(local_files_only=True)`) with Pydantic validation.
- **Interactive CLI Overhaul**:
    - `helomi-cli say [profile_id]`: Live speech-to-text with hybrid voice/text input and reactive prompt autocompletion
      (`SayCompleter`) for vocal delivery tags (e.g. `[laughter]`, `[whisper]`, `[sigh]`).
    - `helomi-cli install`: Automatic model downloader for OpenWakeWord and ONNX VAD assets.
    - `helomi-cli profiles [profile_id]`: Inspect loaded profile definitions in formatted JSON.
    - `helomi-cli settings`: Inspect active runtime settings in formatted JSON.
- **Hierarchical Profile Configuration**:
    - Default profile properties inheritance via `defaults.yml`.
    - Profile exclusion support via `disabled: true`.
- **Documentation Expansion**:
    - Structured `./docs` directory covering settings overrides, profile creation, recommended Hugging Face models,
      reference audio cloning, and FastAPI specification.
    - Formatted and aligned the `yes-minister-typescript` example application documentation to match the project's
      consistent styling.
    - Linked all documentation sections with a clean Table of Contents in the main `README.md`.
- **Quality & Developer Experience**:
    - Strict type checking with `pyrefly`.
    - Automated test suite with $\ge 90\%$ branch coverage enforcement (`make verify`).
    - Convenient Makefile targets (`make run-cli`, `make test`, `make lint`, `make format`, `make verify`).

### Changed

- Replaced legacy monolithic structure with clean unidirectional boundaries enforced by architectural unit tests.
- Replaced audio processing backend with high-performance native Swift `AVAudioEngine` bridge.
- Upgraded configuration system to Pydantic v2 with strict validation and discriminators.

## [0.2.0] - 2026-08-05

### Added

- A reusable application runtime and a macOS menu-bar frontend, including conversation-history and system-diagnostics
  windows.
- One-run language and profile overrides, localized profile configuration, and explicit profile selection.
- Prepared acknowledgement, wait, background, and quit reactions, including a deterministic spoken quit flow.
- MCP tool integration with immediate and background execution, plus a local Google Scholar server for publication and
  author-profile searches.
- Profile-scoped SQLite conversation memory with explicit remembered facts.

### Changed

- Refined desktop menu statuses, live updates, and utility-window presentation.
- Documented MCP endpoint configuration and made source-checkout stdio commands resolve from the repository root.
- Isolated MCP stdio endpoints from runtime logging and discarded their stderr so the protocol stream remains clean.

### Fixed

- Removed empty reply phrases from updates and cancellation handling.

## [0.1.0] - 2026-08-03

### Added

- Initial local, privacy-first voice assistant for Apple Silicon Macs, with a CLI, local profiles, wake-word activation,
  VAD, transcription, streamed replies, synthesis, and playback.
- Native macOS AVAudioEngine helper with Apple Voice Processing, alongside a fallback audio driver and diagnostic
  tooling.
- Package ownership, lifecycle, configuration, privacy, benchmark, and architecture documentation, with automated Python
  and Swift validation.
- Natural conversation behavior including listener-backchannel handling, turn-planning policy, streamed reply delivery,
  and model-prefix caching.
