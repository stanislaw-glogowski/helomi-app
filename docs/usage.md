# Using Helomi

## Profiles

Helomi discovers profiles below `<data-root>/profiles`. The terminal UI lists
invalid profiles too, together with the validation error, so a broken local
profile does not hide the rest. The configured `default_profile` is selected by
default when it is valid.

Each profile supplies the assistant identity, prompts, wake-word label and ONNX
model path, conversation model roles, and speech-model overrides. See
[Profiles](profiles.md) before editing one.

## Voice turn

```mermaid
sequenceDiagram
  participant U as User
  participant S as Speech worker
  participant C as Conversation worker
  U->>S: Wake word
  S->>C: ConversationActivated
  U->>S: Spoken turn
  S->>C: UserTurn(text)
  C-->>S: Streamed reply phrases
  S-->>U: Synthesized playback
```

The wake word starts an interaction. Speech is segmented, transcribed, and
committed as a user turn. The conversation worker streams text; the speech
worker separates phrases, synthesizes them, and starts playback before the full
reply has necessarily completed.

## Interrupting a reply

During playback, detected speech can duck playback and trigger barge-in. The
speech worker cancels the active reply and tells the conversation worker exactly
which spoken prefix was delivered. The next response therefore does not assume
that the user heard the unplayed remainder.

This behavior depends on actual microphone/speaker conditions. The default
native driver uses Apple Voice Processing; the PyAudio fallback does not provide
the same speaker-reference echo cancellation.
