# Applications

Both user interfaces depend only on the public `helomi_app.Application` façade. They do not assemble audio drivers,
speech workers, or profile catalogs.

## System tray

```bash
make run-tray
# or
uv run helomi-tray
```

The tray provides:

- profile selection when the active driver supports manual selection;
- live audio-driver selection and capability-aware controls;
- independent toggles for wake word, persistent profile, reactions, and room voice;
- `api`, `parrot`, and `operator` response modes without restarting audio or ending a profile;
- a TTS window whose clean synthesis can be exported as WAV;
- graceful shutdown and playback-aware farewell behavior.

When an inbound Twilio call arrives, profile selection is disabled because the called number determines the profile.
An independent Call window opens with masked caller number, profile, call state and duration, live caller transcript,
current response mode, monitoring control, a shortcut to TTS, and **End Call**. Opening the window does not change the
response mode. Opening TTS temporarily selects `operator`; closing it restores the preceding mode without changing
conversation options or room voice.

## CLI

```bash
uv run helomi-cli --help
uv run helomi-cli install
uv run helomi-cli parrot alexa
uv run helomi-cli parrot
uv run helomi-cli serve
uv run helomi-cli --version
```

- `install` installs the shared wake-word assets and the supported Alexa wake-word model.
- `parrot [profile_id]` runs spoken echo mode. With an ID, activation is explicit. Without one, it waits for a wake
  word and fails clearly if wake-word detection is disabled.
- `serve` starts the REST/SSE API in `api` response mode.

The CLI logs events, route changes, and calls; runtime option switches remain in the tray.
