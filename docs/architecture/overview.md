# Architecture overview

Helomi separates runtime composition, local resources, voice behavior, and
conversation behavior. The dependency direction is toward package-owned
contracts, not toward the terminal UI.

```mermaid
flowchart TB
  CLI["cli: composition, UI, signals"] --> Common["common: events, lifecycle, logging"]
  CLI --> Resources["resources: local settings, profiles, models"]
  CLI --> Speech["speech: voice session and audio"]
  CLI --> Conversation["conversation: graph and model reply"]
  Speech --> Common
  Speech --> Resources
  Conversation --> Common
  Conversation --> Resources
  Desktop["desktop: thin macOS shell"] --> CLI
  Swift["Swift AVAudioEngine helper"] <--> Speech
```

| Package | Responsibility |
| --- | --- |
| `common` | Reusable lifecycle, events, logging, and validation primitives. |
| `resources` | `HELOMI_HOME` resolution, local settings/profiles, model-path discovery, and boundary validation. |
| `speech` | Audio capture, VAD, wake word, segmentation, STT, TTS, playback, voice-session state, and adapters. |
| `conversation` | Finite graph runs, history, profiles, language-model adapters, and streamed reply segmentation. |
| `cli` | Startup, readiness, signals, shutdown, terminal UI, and composition. |
| `desktop` | Thin macOS entrypoint only. |

The [voice pipeline](voice-pipeline.md) and [conversation guide](conversation.md)
describe the two workers. [Lifecycle and concurrency](lifecycle-and-concurrency.md)
documents their shared event and shutdown contracts.
