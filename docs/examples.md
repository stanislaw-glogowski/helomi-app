# Examples

## Run the supported profile locally

```bash
uv run helomi-cli parrot alexa
```

To wait for the configured Alexa wake word instead:

```bash
uv run helomi-cli parrot
```

## Change the server port

Create `resources/settings.override.yml`:

```yaml
app:
  server:
    host: 0.0.0.0
    port: 8080
```

Then run:

```bash
uv run helomi-cli serve
```

## Change conversation defaults

```yaml
app:
  conversation:
    persistent_profile: false
    wakeword: true
    reactions: true
    room_voice: false
  response_mode: parrot
```

The same four options can be changed live from the tray without changing the active response mode.

## Add Twilio inbound

Add the Twilio driver in `settings.override.yml`, configure the exact public webhook URL and auth token through
environment variables, then map the number in `profiles/alexa/profile.override.yml`. Complete snippets are in
[Settings Configuration](settings.md#enabling-inbound-twilio).

During a call the Twilio route selects Alexa automatically. The tray may monitor only the caller through local
AVFAudio; playback and room voice remain on the telephone route.

## TypeScript client

The [`demo/`](../demo/README.md) application demonstrates `api` response mode:

- it acquires an SSE session for Alexa;
- consumes transcription and interruption events;
- streams an LLM response;
- sends `say_text` commands back for local synthesis;
- ends the conversation explicitly.
