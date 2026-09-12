# Helomi Voice Assistant – TypeScript Demo

An interactive conversational voice agent built with [Bun](https://bun.sh/), TypeScript, and
the [Vercel AI SDK](https://sdk.vercel.ai/), demonstrating real-time integration with Helomi's local speech processing
pipeline.

## Overview

The demo connects to a running Helomi FastAPI server over HTTP and Server-Sent Events (SSE). When you speak into your
microphone, Helomi captures audio, executes on-device Voice Activity Detection (VAD) and Speech-to-Text (STT), and
streams transcription events to this application. The demo then streams replies from an LLM (such as Ollama or OpenAI)
sentence-by-sentence back to Helomi's Text-to-Speech (TTS) synthesizer for low-latency voice playback.

### Key Capabilities

- **Real-Time Speech Streaming**: Subscribes to SSE speech events via `GET /api/v1/profile/{profile_id}/stream`.
- **Low-Latency Sentence Streaming**: LLM responses are streamed and synthesized sentence-by-sentence rather than
  waiting for full generation.
- **Barge-in / Interruption Handling**: If you speak while the assistant is speaking, Helomi sends a
  `speech_interrupted` event which instantly cancels LLM generation via `AbortController`.
- **Rolling Conversation History**: Retains the last 10 messages per profile session to provide multi-turn conversation
  memory.
- **Modular Profile Prompts via API**: Fetches system prompts directly from Helomi using `require_prompt: "demo"`, rendered by Helomi's on-device prompt template engine (`resources/profiles/<profile_id>/prompts/demo.md`).
- **Conversational Termination Tool**: Equips the LLM with an `endConversation` tool to gracefully end interactions when the user says goodbye.

---

## Architecture & Event Flow

```text
  User Speech ──► [Helomi Core (VAD + STT)]
                          │
            SSE Event: transcription_ready
                          ▼
            [Demo Application (MessageManager)]
                          │
                    streamText()
                          ▼
              [LLM (Ollama / OpenAI)]
                          │
                     Text delta
                          ▼
              [Sentence Line Splitting]
                          │
             POST /api/v1/command (say_text)
                          ▼
          [Helomi Core (TTS Synthesis & Audio Playback)]
```

---

## Prerequisites

- **macOS on Apple Silicon**
- **[Bun](https://bun.sh/)** (>= 1.4.0)
- **Helomi Speech Server** installed and running
- **OpenAI-compatible LLM** (local [Ollama](https://ollama.com/) or an OpenAI API key)

---

## Setup & Configuration

### 1. Install Dependencies

From the `demo/` directory, install dependencies using Bun:

```bash
bun install
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Configure your LLM provider and server settings in `.env`:

#### Example: Local Ollama

```env
API_BASE_URL=http://127.0.0.1:4356
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL_ID=gemma4:e4b-mlx
```

#### Example: OpenAI

```env
API_BASE_URL=http://127.0.0.1:4356
LLM_BASE_URL=
LLM_API_KEY=sk-your-openai-key
LLM_MODEL_ID=gpt-5.6-luna
```

---

## Running the Demo

In the `demo/` directory:

```bash
bun start
```

Once connected, speak into your microphone. Transcriptions and generated spoken replies will stream directly in the
terminal and through your speakers.

---

## Prompts & Profiles

Prompts are managed centrally by Helomi in `resources/` and retrieved on-the-fly by the demo client:

1. **Profile Personas (`resources/profiles/<profile_id>/prompts/demo.md`)**:
   Defines the personality, traits, and response style of the profile. Helomi's `PromptReader` substitutes parameters such as `{{ name }}` and `{{ description }}` before serving it via the API (`GET /api/v1/profile?require_prompt=demo`).
2. **Shared Formatting Instructions (`resources/prompts/demo/instructions.md`)**:
   Shared rules ensuring LLM output is formatted for real-time speech synthesis (plain text without markdown, and allowed vocal delivery tags such as `[laughter]`, `[sigh]`, `[breath]`).
3. **Conversational Termination (`endConversation`)**:
   The LLM provider is equipped with an `endConversation` tool. When the user indicates they want to end or exit the chat (e.g., "bye", "goodbye", "stop conversation"), the tool triggers and the provider yields `null`, prompting the session to close gracefully.

---

## Available Scripts

| Script      | Command                   | Description                                 |
|-------------|---------------------------|---------------------------------------------|
| `start`     | `bun run src/main.ts`     | Runs the demo voice agent application       |
| `test`      | `bun test`                | Runs the Bun unit test suite                |
| `coverage`  | `bun run test --coverage` | Runs unit tests with coverage reporting     |
| `lint`      | `bun run lint`            | Checks code formatting and lints with Biome |
| `format`    | `bun run format`          | Formats TypeScript code with Biome          |
| `typecheck` | `bun run typecheck`       | Validates strict types with `tsc --noEmit`  |
