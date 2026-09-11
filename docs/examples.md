# Examples

Here are some common usage examples for configuring and running Helomi.

## Running the System Tray Application (Primary Interface)

To launch the primary macOS menu bar assistant:

```bash
make run-tray
# or
uv run helomi-tray
```

From the menu bar icon, you can switch active voice profiles (shortcuts `0`–`8`), monitor the API server status, open the Text-to-Speech window (`t`), toggle Parrot mode (`p`), and quit the application (`q`).

## Running a Specific Profile via Developer CLI

To run the developer CLI with a custom profile named `my_assistant`:

```bash
uv run helomi-cli parrot my_assistant
```

## Overriding the Server Port

Create `settings.override.yml` in your `resources` directory:

```yaml
server:
  host: "0.0.0.0"
  port: 8080
```

Then start the server:

```bash
uv run helomi-cli serve
```

## Disabling Wake-Word

Wake-word detection can be toggled at runtime directly from the macOS system tray menu under **Settings -> Wake Word**. When unchecked, wake-word detection is disabled and the active profile remains persistent without automatic timeout deactivation.

In programmatic usage or integration testing, wake-word detection can be controlled dynamically via `PipelineOptions`:

```python
from helomi_core.pipeline.request import PipelineOptions

options = PipelineOptions(wakeword_enabled=False)
```

## Setting a Default Profile

To ensure the CLI or Server always defaults to a specific profile, you can set it in `settings.override.yml`:

```yaml
profile:
  default: "my_assistant"
```

## TypeScript Voice Assistant Demo

The [`demo/`](../demo/README.md) directory contains a complete reference client application built
with [Bun](https://bun.sh/), TypeScript, and the [Vercel AI SDK](https://sdk.vercel.ai/):

- **Real-Time Speech Streaming**: Subscribes to SSE pipeline events via `GET /api/v1/profile/{profile_id}/stream`.
- **Low-Latency LLM Streaming**: Streams text from OpenAI-compatible models (e.g. Ollama or OpenAI) and sends
  synthesized sentence lines immediately to `POST /api/v1/command`.
- **Barge-in / Interruption Handling**: Automatically aborts ongoing LLM generation upon receiving `speech_interrupted`.
- **Multi-Turn Memory**: Retains rolling conversation history per profile session.
- **Dynamic Prompts**: Loads persona prompts from `prompts/profiles/<profile_id>.md` (default: `alexa.md`) merged with
  output formatting instructions in `prompts/instructions.md`.

For setup and execution details, refer to the [Demo Documentation](../demo/README.md).


