# Server API

Run the local REST/SSE server in `api` response mode:

```bash
uv run helomi-cli serve
```

The default address is `http://127.0.0.1:4356`; configure it under `app.server`.

## Service endpoints

- `GET /` returns the title, version, and Swagger URL.
- `GET /health` returns `{"status":"OK"}`.
- `GET /docs` opens Swagger UI.

## Profiles

`GET /api/v1/profile` lists profiles. `GET /api/v1/profile/{profile_id}` returns one profile. Both accept an optional
`require_prompt` query parameter.

```json
{
  "id": "alexa",
  "name": "Alexa",
  "emoji": "👩🏻",
  "prompt": null,
  "has_wakeword": true,
  "is_active": false,
  "is_readonly": false
}
```

There is intentionally no `is_default` field.

## Session event stream

`GET /api/v1/profile/alexa/stream` acquires the profile and returns Server-Sent Events. Only one API session may own a
profile at a time; another request receives `409 Conflict`. The initial `session_started` event and `X-Session-ID`
response header contain the session ID required for commands.

The stream contains profile-scoped events: `profile_activated`, `profile_deactivated`, `transcription_ready`,
`synthesis_ready`, `speech_interrupted`, `processing_failed`, `call_started`, and `call_ended`. Global application events, such as route,
response-mode, state, or option changes, remain available through the in-process `Application` event subscription and
are not copied to every profile stream. Audio bytes are excluded from serialized synthesis events.

## Commands

Send `POST /api/v1/command` with `X-Session-ID`. The endpoint returns a structured `CommandResult`:

```json
{"accepted": true, "rejection_code": null, "detail": null}
```

Say text:

```json
{
  "type": "say_text",
  "text": "Hello!",
  "mode": "api"
}
```

Say a configured reaction:

```json
{
  "type": "say_reaction",
  "reaction": "greeting",
  "mode": "api"
}
```

End the conversation:

```json
{
  "type": "end_conversation",
  "play_farewell": true
}
```

The server binds profile and mode to the acquired session. It returns `401` for an invalid session and `409` when API
response mode is inactive. Domain rejections use explicit codes such as `profile_required`, `mode_inactive`, `busy`,
or `empty_text` instead of an ambiguous boolean. Accepted text requests are queued without a fixed item limit.

`say_text`, `say_reaction`, and `end_conversation` optionally accept `session_id` and `turn_id` together, using the
conversation identity from `transcription_ready`. This identity differs from the API subscription's `X-Session-ID`.
A stale conversation identity returns `stale_turn`; omitting these fields retains the current-turn behavior.

`end_conversation` also accepts `wait_for_speech: true` to finish queued speech before closing. Its default is `false`.
Waiting does not block barge-in; an interrupted or replaced conversation returns `stale_turn`.

The `connected` reaction plays once after an inbound phone call starts, replacing `greeting` for that activation.
Local activation continues to use `greeting`. Both respect the reactions option; an absent reaction remains silent.

`processing_failed` contains `stage` (`detection`, `transcription`, `synthesis`, or `playback`) and `detail`, plus the
available profile, trace, session, and turn identity. Failures are reported without terminating the request loops.
