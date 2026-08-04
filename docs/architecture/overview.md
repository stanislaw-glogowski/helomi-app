# Architecture overview

Helomi separates runtime composition, local resources, voice behavior, and
conversation behavior. The dependency direction is toward package-owned
contracts, not toward the terminal UI.

```mermaid
flowchart TB
  App["app: composition and lifecycle"] --> Common["common: events, lifecycle, logging"]
  App --> Resources["resources: local settings, profiles, models"]
  App --> Speech["speech: voice session and audio"]
  App --> Conversation["conversation: graph and model reply"]
  Speech --> Common
  Speech --> Resources
  Conversation --> Common
  Conversation --> Resources
  CLI["cli: terminal presentation and signals"] --> App
  Desktop["desktop: macOS menu-bar presentation"] --> App
  Swift["Swift AVAudioEngine helper"] <--> Speech
```

| Package | Responsibility |
| --- | --- |
| `common` | Reusable lifecycle, events, logging, and validation primitives. |
| `resources` | `HELOMI_HOME` resolution, local settings/profiles, model-path discovery, and boundary validation. |
| `speech` | Audio capture, VAD, wake word, segmentation, STT, TTS, playback, voice-session state, and adapters. |
| `conversation` | Finite graph runs, history, profiles, language-model adapters, and streamed reply segmentation. |
| `app` | Local resource discovery, profile validation, worker readiness, startup progress, retry, and ordered shutdown. |
| `cli` | Terminal presentation, signals, and terminal-specific event/log views. |
| `desktop` | macOS menu-bar presentation and AppKit/asyncio thread bridge. |

The [voice pipeline](voice-pipeline.md) and [conversation guide](conversation.md)
describe the two workers. [Lifecycle and concurrency](lifecycle-and-concurrency.md)
documents their shared event and shutdown contracts.
