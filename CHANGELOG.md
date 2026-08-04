# Changelog

All notable changes to Helomi are documented in this file.

## [0.2.0] - Unreleased

### Added

- A reusable application runtime and a macOS menu-bar frontend, including
  conversation-history and system-diagnostics windows.
- One-run language and profile overrides, localized profile configuration, and
  explicit profile selection.
- Prepared acknowledgement, wait, background, and quit reactions, including a
  deterministic spoken quit flow.
- MCP tool integration with immediate and background execution, plus a local
  Google Scholar server for publication and author-profile searches.
- Profile-scoped SQLite conversation memory with explicit remembered facts.

### Changed

- Refined desktop menu statuses, live updates, and utility-window presentation.
- Documented MCP endpoint configuration and made source-checkout stdio commands
  resolve from the repository root.
- Isolated MCP stdio endpoints from runtime logging and discarded their stderr
  so the protocol stream remains clean.

### Fixed

- Removed empty reply phrases from updates and cancellation handling.

## [0.1.0] - 2026-08-03

### Added

- Initial local, privacy-first voice assistant for Apple Silicon Macs, with a
  CLI, local profiles, wake-word activation, VAD, transcription, streamed
  replies, synthesis, and playback.
- Native macOS AVAudioEngine helper with Apple Voice Processing, alongside a
  fallback audio driver and diagnostic tooling.
- Package ownership, lifecycle, configuration, privacy, benchmark, and
  architecture documentation, with automated Python and Swift validation.
- Natural conversation behavior including listener-backchannel handling,
  turn-planning policy, streamed reply delivery, and model-prefix caching.
