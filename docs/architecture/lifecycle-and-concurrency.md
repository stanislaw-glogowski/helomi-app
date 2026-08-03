# Lifecycle and concurrency

`helomi.cli` creates one `EventBus`, starts the conversation and speech workers,
waits for both readiness events, and only then releases their start gate. This
prevents an early publication from being missed by an unsubscribed worker.

```mermaid
sequenceDiagram
  participant CLI
  participant CW as Conversation worker
  participant SW as Speech worker
  participant Bus as EventBus
  CLI->>CW: start
  CLI->>SW: start
  CW->>Bus: ConversationReady
  SW->>Bus: SpeechReady
  Bus-->>CLI: both ready
  CLI->>CW: set start gate
  CLI->>SW: set start gate
  Note over CW,SW: process voice session
  CLI->>Bus: ShutdownEvent
  Bus-->>CW: cancel and await tasks
  Bus-->>SW: cancel and await tasks
```

The EventBus carries typed events across package boundaries. It does not make
ownership implicit: speech still owns capture/playback, conversation still owns
graph execution, and the CLI still owns composition and application shutdown.

Each long-running loop makes queue completion explicit. Every successful
`get()` has one `task_done()` in a `finally` block, including error and
cancellation paths. Resources that can block—audio devices, native processes,
model runtimes, and workers—have a single owner and deterministic teardown.

```mermaid
flowchart LR
  Wake["Wake / user speech"] -->|GenerateReply| Conversation
  Conversation -->|ReplyGenerationStarted, ReplyPhrase| Speech
  Speech -->|CancelReply| Conversation
  CLI -->|ShutdownEvent| Speech
  CLI -->|ShutdownEvent| Conversation
```
