# Helomi Assistant with Dynamic Prompts & Per-Profile Memory

A TypeScript example demonstrating how to build an intelligent conversational voice assistant on top of the **Helomi** speech runtime.

This example features:
- **Dynamic Prompt Loading**: System prompts are automatically loaded from `./prompts/<profile_id>.md` based on the currently active voice profile.
- **Graceful Fallback**: If `./prompts/<profile_id>.md` does not exist, it falls back to `./prompts/default.md` (or a built-in safe default).
- **Per-Profile Conversation Memory**: Each voice profile maintains its own isolated sliding window history of the last 10 messages (configurable via `MAX_MEMORY_MESSAGES`), ensuring multi-turn context without profile cross-contamination.
- **Concurrent Multi-Profile Streaming**: Automatically discovers all loaded Helomi profiles and handles speech interactions across all of them simultaneously.

---

## Architecture Overview

```text
 ┌────────────────────────────────────────┐
 │             Helomi Server              │
 │  GET /api/v1/profile (Discovery)       │
 │  GET /api/v1/speech  (SSE Audio Flow)  │
 └──────┬───────────────────────────▲─────┘
        │ SSE: transcription_ready  │ POST: say_text
        │ { profile_id, text }      │ { profile_id, text }
        ▼                           │
 ┌──────────────────────────────────┴─────┐
 │       Profile Memory Application       │
 │                                        │
 │  1. Load Prompt:                       │
 │     ./prompts/<profile_id>.md          │
 │     (fallback: ./prompts/default.md)   │
 │                                        │
 │  2. Load Context:                      │
 │     ProfileMemory[profile_id] (<= 10)  │
 │                                        │
 │  3. Query LLM:                         │
 │     Vercel AI SDK (Ollama / OpenAI)    │
 │                                        │
 │  4. Update Memory & Speak Back         │
 └────────────────────────────────────────┘
```

---

## Prerequisites

- **Node.js**: `>= 18.0.0`
- **Helomi Server**: Running locally (`uv run helomi-cli serve`)
- **LLM Provider**:
  - **Ollama**: A local model running (e.g. `llama3.2`, `qwen2.5:7b`, or `gemma2`), OR
  - **OpenAI**: An API key.

---

## Quick Start

### 1. Install Dependencies

```bash
cd examples/profile-memory-typescript
npm install
```

*(Alternatively, if working within this monorepo without re-downloading, you can copy or symlink `node_modules` from `examples/yes-minister-typescript`)*.

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Configure your LLM provider in `.env`:

```env
# Ollama Example (OpenAI-compatible mode with /v1):
LLM_MODEL=llama3.2
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# For OpenAI:
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=sk-...

# Helomi Server:
HELOMI_SERVER_URL=http://127.0.0.1:4356

# Optional: Restrict to single profile (leave empty for auto-discovery)
HELOMI_PROFILE_ID=

# Memory capacity (default: 10 messages)
MAX_MEMORY_MESSAGES=10
```

### 3. Run

Ensure Helomi server is running in another terminal:

```bash
uv run helomi-cli serve
```

Then launch the assistant:

```bash
npm start
```

For live development with auto-reloading:

```bash
npm run dev
```

---

## Customizing Personas & Prompts

Prompts reside in the `./prompts` directory:

```text
prompts/
└── default.md   # Default system prompt (fallback)
```

### Adding a New Profile Prompt

Custom profile prompts (`./prompts/<profile_id>.md`) are gitignored so you can maintain your own private personas without committing them.

To add a prompt for a profile (e.g. `gizmo`, `trump`, `wojan`, or any custom profile registered in Helomi):

1. Create a file named `prompts/<profile_id>.md` (e.g. `prompts/gizmo.md`):
   ```markdown
   Jesteś Gizmo – starszym, upartym polskim politykiem.
   Odpowiadaj dosadnie (2-3 zdania).
   Wpleć naturalnie tagi emocji TTS w nawiasach kwadratowych, np. [throat-clearing], [sigh], [snicker].
   Nie używaj formatowania markdown ani emotikonów.
   ```
2. Whenever Helomi activates that profile and detects speech, the matching `./prompts/<profile_id>.md` is automatically loaded and applied.
3. If no file exists for an active profile, the application seamlessly falls back to `prompts/default.md`.

> [!TIP]
> Prompt files are loaded on-demand per utterance. You can modify markdown prompt files while the assistant is running to immediately adjust its persona without restarting the process.

---

## Conversation Memory Details

- **Isolation**: Each profile stores its own independent list of turns. Speaking to one profile will never pollute the context of another.
- **Sliding Window**: Memory retains up to 10 messages (configurable via `MAX_MEMORY_MESSAGES`). When a new user utterance and assistant reply are recorded, the oldest turns slide out of context.
- **Context Injection**: All stored messages are sent to the LLM as structured `messages` alongside the profile's system prompt:
  ```typescript
  const { text } = await generateText({
    model,
    system: promptInfo.prompt,
    messages: [
      ...history,
      { role: "user", content: userText },
    ],
  });
  ```

---

## Configuration Reference

| Variable | Description | Default |
| --- | --- | --- |
| `LLM_MODEL` | Model identifier to query (e.g. `llama3.2`, `gpt-4o-mini`) | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | Base URL for OpenAI or Ollama (`http://localhost:11434/v1`) | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API key (`ollama` for local models) | `ollama` |
| `HELOMI_SERVER_URL` | Address of the Helomi server | `http://127.0.0.1:4356` |
| `HELOMI_PROFILE_ID` | Single target profile ID (leave blank to listen to all profiles) | *(Auto-discover all)* |
| `MAX_MEMORY_MESSAGES` | Number of messages to retain in memory per profile | `10` |

---

## Project Structure

```text
examples/profile-memory-typescript/
├── prompts/
│   └── default.md     # Default system prompt (fallback)
├── main.ts            # SSE stream handler & LLM orchestrator
├── memory.ts          # ProfileMemoryManager (sliding window)
├── prompt.ts          # PromptLoader (resolution & fallback)
├── package.json       # Dependencies & npm scripts
├── tsconfig.json      # TypeScript compiler configuration
├── .env.example       # Environment template
└── README.md          # Documentation
```
