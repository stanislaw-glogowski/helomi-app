# Server API Specification

Helomi features a local FastAPI server to orchestrate the speech pipeline and interact with external interfaces and
applications.

By default, the server runs on `http://127.0.0.1:4356` (configurable via `settings.yml`).

## Endpoints

### `GET /api/v1/health`

Simple health check endpoint returning server status.

- **Response:** `{"status": "OK"}`

---

### `GET /api/v1/profile`

Lists all loaded voice assistant profiles and identifies whether each is currently active.

- **Response:**
  ```json
  [
    {
      "id": "alexa",
      "name": "Alexa",
      "is_active": true
    }
  ]
  ```

---

### `GET /api/v1/profile/{profile_id}`

Retrieves detailed information for a specific profile ID.

- **Path Parameters:**
    - `profile_id` (string): Profile identifier.
- **Response:**
  ```json
  {
    "id": "alexa",
    "name": "Alexa",
    "is_active": true
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
    - `session`: Initial event providing `session_id` and locked `profile_id`.
    - `profile_activated`: Profile activation notification (`profile_id`, `trace_id`).
    - `profile_deactivated`: Profile deactivation notification (`profile_id`).
    - `transcription_ready`: Transcribed user utterance (`profile_id`, `text`).
    - `speech_interrupted`: Playback interruption notification (`profile_id`).
- **Status Codes:** `200 OK`, `404 Not Found` (unknown profile), `409 Conflict` (profile already in use by an active
  session).

---

### `POST /api/v1/command`

Sends a command to the speech pipeline within an active session.

- **Headers:**
    - `X-Session-ID`: The Session ID obtained from the SSE stream connection.
- **Body:** JSON payload matching the `PipelineCmd` schema:
    - **`SayText`**: Request TTS engine to synthesize and play speech:
      ```json
      {
        "type": "say_text",
        "text": "Hello, world!",
        "profile_id": "alexa"
      }
      ```
    - **`ActivateProfile`**: Activate session profile:
      ```json
      {
        "type": "activate_profile",
        "profile_id": "alexa",
        "greet": true
      }
      ```
        - `greet` (optional, boolean, default `true`): Whether to synthesize and speak the profile's greeting reaction
          upon activation. Pass `false` to activate silently.
    - **`DeactivateProfile`**: Deactivate current profile:
      ```json
      {
        "type": "deactivate_profile"
      }
      ```
- **Response:** `{"success": true}`
- **Status Codes:** `200 OK`, `401 Unauthorized` (missing/invalid session), `403 Forbidden` (profile mismatch)


