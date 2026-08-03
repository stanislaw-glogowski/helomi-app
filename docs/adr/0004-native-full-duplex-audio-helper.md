# ADR-0004: Native full-duplex audio helper

- Status: Accepted
- Date: 2026-08-03
- Supersedes: None
- Superseded by: None
- Implementation: Existing implementation; retrospective record.

## Context

Reliable speaker barge-in requires capture, playback, and Apple Voice Processing
in one macOS audio session. A generic Python audio stack cannot provide that
native speaker-reference path.

## Decision or proposal

Use a Swift `AVAudioEngine` helper process as the default audio driver. Communicate
with Python using a versioned framed stdin/stdout protocol; keep PyAudio as a
fallback driver.

## Consequences

Native audio requires Swift build/test tooling and synchronized protocol changes
across Swift, Python, fakes, and tests. PyAudio remains available but has weaker
full-duplex behavior.

## Alternatives considered

- PyAudio only: rejected because it does not provide the required native voice
  processing path.
- Separate capture and playback processes: rejected because voice processing
  needs a single owning audio session.

## References

- [Native macOS audio](../architecture/native-audio.md)
- [Native helper README](../../native/macos/audio/README.md)
