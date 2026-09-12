# Server API Specification

Helomi features a local FastAPI server to orchestrate the speech pipeline and interact with external interfaces and
applications.

By default, the server runs on `http://127.0.0.1:4356` (configurable via `settings.yml`).

## Endpoints

### `GET /`

Returns root service metadata and documentation links.

- **Response:**
  ```json
  {
    "title": "Helomi API",
    "version": "0.6.0",
    "description": "Privacy-first voice assistant API for audio orchestration, profile management, pipeline command execution, and real-time event streaming.",
    "docs_url": "/docs"
  }
  ```

---

### `GET /api/v1/health`

Simple health check endpoint returning server status.

- **Response:** `{"status": "OK"}`

---

### `GET /api/v1/profile`

Lists all loaded voice assistant profiles. Optionally filters by a required prompt template.

- **Query Parameters:**
    - `require_prompt` (string, optional): If specified, only returns profiles that define the requested prompt template.
- **Response:**
  ```json
  [
    {
      "id": "alexa",
      "name": "Alexa",
      "emoji": "👩🏻",
      "prompt": "You are Alexa, a helpful voice assistant...",
      "has_wakeword": true,
      "is_active": true,
      "is_default": true,
      "is_readonly": true
    }
  ]
  ```

---

### `GET /api/v1/profile/{profile_id}`

Retrieves detailed information for a specific profile ID.

- **Path Parameters:**
    - `profile_id` (string): Profile identifier.
- **Query Parameters:**
    - `require_prompt` (string, optional): If specified, includes the rendered prompt content in the `"prompt"` field. Returns `404 Not Found` if the profile does not define this prompt.
- **Response:**
  ```json
  {
    "id": "alexa",
    "name": "Alexa",
    "emoji": "👩🏻",
    "prompt": "You are Alexa, a helpful voice assistant...",
    "has_wakeword": true,
    "is_active": true,
    "is_default": true,
    "is_readonly": true
  }
  ```
- **Status Codes:** `200 OK`, `404 Not Found`

---

### `GET /api/v1/profile/{profile_id}/stream`

Subscribes to the Server-Sent Events (SSE) stream for real-time speech pipeline events bound to a specific profile.

- **Path Parameters:**
    - `profile_id` (string): ID of the profile to lock and stream events for.
- **Response Headers:**
    - `X-Session-ID`: Unique session ID required for sending authenticated commands.
- **Events Streamed:**
    - `session_started`: Initial event providing `session_id` and locked `profile_id`.
    - `profile_activated`: Profile activation notification (`profile_id`, `trace_id`).
    - `profile_deactivated`: Profile deactivation notification (`profile_id`).
    - `transcription_ready`: Transcribed user utterance (`profile_id`, `text`).
    - `synthesis_ready`: Synthesized audio readiness notification (`profile_id`).
    - `speech_interrupted`: Playback interruption notification (`profile_id`).
- **Status Codes:** `200 OK`, `404 Not Found` (unknown profile), `409 Conflict` (profile already in use by an active
  session).

---

### `POST /api/v1/command`

Sends a command to the speech pipeline within an active session.

- **Headers:**
    - `X-Session-ID`: The Session ID obtained from the SSE stream connection.
- **Body:** JSON payload matching the `PipelineCmd` schema:
    - **`SayTextCmd`**: Request TTS engine to synthesize and play speech:
      ```json
      {
        "type": "say_text",
        "text": "Hello, world!",
        "profile_id": "alexa"
      }
      ```
    - **`ActivateProfileCmd`**: Activate session profile:
      ```json
      {
        "type": "activate_profile",
        "profile_id": "alexa"
      }
      ```
    - **`SayReactionCmd`**: Trigger a pre-configured reaction utterance (e.g. `greeting`, `interrupted`):
      ```json
      {
        "type": "say_reaction",
        "reaction": "greeting"
      }
      ```
    - **`DeactivateProfileCmd`**: Deactivate current profile:
      ```json
      {
        "type": "deactivate_profile"
      }
      ```
- **Response:** `{"success": true}`
- **Status Codes:** `200 OK`, `401 Unauthorized` (missing/invalid session), `403 Forbidden` (profile mismatch)


