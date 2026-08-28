# Server API Specification

Helomi features a local FastAPI server to orchestrate the speech pipeline and interact with external interfaces.

## Endpoints

### `GET /api/v1/speech`

Subscribes to the Server-Sent Events (SSE) stream for real-time speech pipeline events.

- **Query Parameters:**
    - `profile_id` (string): ID of the profile to lock and use for the session.
- **Headers:**
    - Returns `X-Session-ID` in the response headers to authenticate commands.
- **Events:** Streams real-time events such as VAD state changes, transcription results, and TTS status.

### `POST /api/v1/speech`

Sends a command to the speech pipeline.

- **Headers:**
    - `x-session-id`: The Session ID obtained from the SSE stream connection.
- **Body:** JSON payload matching the internal `SpeechCmd` schema.
- **Supported Commands:**
    - `SayText`: Request the TTS engine to synthesize speech from the provided text.
    - `ActivateProfile`: Change the active profile in the current session.

By default, all API routes are served on `http://127.0.0.1:4356`.
