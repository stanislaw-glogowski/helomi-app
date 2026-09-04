# Yes, Minister! – Helomi Speech Translator

> *"To say nothing, especially when speaking, is the half-mark of a statesman."* — *Yes, Minister*

A lightweight TypeScript example demonstrating how to integrate with the **Helomi** local speech runtime. It captures your raw voice transcriptions in real time, translates them, and elevates them into pompous, diplomatic political statements before speaking them back through Helomi's text-to-speech engine.

---

## How It Works

```
  ┌─────────────────┐       SSE (transcription_ready)      ┌─────────────────────────┐
  │  Helomi Server  │ ───────────────────────────────────► │      Yes, Minister      │
  │  (STT & Audio)  │                                      │     (TypeScript App)    │
  └─────────────────┘ ◄─────────────────────────────────── └─────────────────────────┘
                            POST /api/v1/speech (say_text)              │
                                                                        ▼
                                                           ┌─────────────────────────┐
                                                           │   LLM (OpenAI / Ollama) │
                                                           │  "Translate & Politify" │
                                                           └─────────────────────────┘
```

1. **SSE Connection**: Subscribes to Helomi's Server-Sent Events stream (`GET /api/v1/speech?profile_id=default`).
2. **Speech Event**: When Helomi detects speech and transcribes it, a `transcription_ready` event is received.
3. **Political Transformation**: The text is passed to an LLM via the Vercel AI SDK with a custom prompt instructing it to translate and reformulate the sentence into diplomatic doublespeak.
4. **Voice Synthesis**: Sends a `say_text` command back to Helomi's REST API (`POST /api/v1/speech`) to synthesize and play the speech.

---

## Example Transformation

| User Speaks (Polish) | Helomi Speaks Back (Political English) |
| --- | --- |
| *"Nie chce mi się dzisiaj pracować."* | *"In light of prevailing circumstances, we are currently prioritizing strategic contemplation over immediate operational deliverables."* |
| *"Spóźnię się na spotkanie bo stoję w korku."* | *"Due to unforeseen infrastructural congestion, our bilateral consultations will require a temporary calendar realignment."* |
| *"Zepsułem produkcję."* | *"We have proactively initiated an unscheduled resilience audit across our core deployment environments."* |

---

## Prerequisites

- **Node.js**: `>= 18.0.0`
- **Helomi Server**: Running locally (`uv run helomi-cli serve`)
- **LLM Provider**:
  - **Ollama**: A local instance running (e.g. `gemma4:e4b-mlx`, `qwen2.5:7b`, or `llama3.2`), OR
  - **OpenAI**: An API key.

---

## Quick Start

### 1. Install Dependencies

```bash
cd examples/yes-minister-typescript
npm install
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` to select your preferred provider and language options:

```env
# --- LLM Settings (Ollama OpenAI-compatible mode, note /v1 at the end) ---
LLM_MODEL=llama3.2
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# --- For OpenAI: ---
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=https://api.openai.com/v1

# --- Languages & Helomi Settings ---
SOURCE_LANGUAGE=Polish
TARGET_LANGUAGE=English
HELOMI_SERVER_URL=http://127.0.0.1:4356
HELOMI_PROFILE_ID=default
```

### 3. Run

Make sure your Helomi server is running in another terminal:

```bash
# In the project root
uv run helomi-cli serve
```

Then start the translator:

```bash
npm start
```

For live development with auto-reloading:

```bash
npm run dev
```

---

## Configuration Reference

All settings can be configured via environment variables or rely on built-in constants:

| Variable | Description | Default |
| --- | --- | --- |
| `LLM_MODEL` | Model name to query (e.g. `llama3.2`, `gpt-4o-mini`) | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible endpoint (e.g. `http://localhost:11434/v1` for Ollama) | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API key (`ollama` for local Ollama, or OpenAI secret key) | `ollama` |
| `HELOMI_SERVER_URL` | Base URL of the Helomi server | `http://127.0.0.1:4356` |
| `HELOMI_PROFILE_ID` | Voice profile ID registered on the Helomi server | `default` |
| `SOURCE_LANGUAGE` | Language spoken by the user into the microphone | `Polish` |
| `TARGET_LANGUAGE` | Language for translation and political rephrasing | `English` |

---

## Project Structure

```
examples/yes-minister-typescript/
├── main.ts         # Minimal application script (SSE subscriber + LLM caller + TTS sender)
├── package.json    # Dependencies and execution scripts
├── tsconfig.json   # TypeScript configuration
├── .env.example    # Environment variables template
└── README.md       # Documentation & examples
```
