# Diagnostics

The audio diagnostic opens the configured or requested audio driver, records a
short microphone sample, and plays it back:

```bash
uv run python -m tools.diagnostic --type audio --seconds 5
```

Use `--duplex` to play a generated test signal while recording the residual
microphone signal. Remain silent during the measurement:

```bash
uv run python -m tools.diagnostic --type audio --seconds 5 --duplex
```

Compare the fallback driver explicitly when required:

```bash
uv run python -m tools.diagnostic --type audio --driver pyaudio
```

These commands are interactive, access real devices, and may produce audible
output. They are diagnostic tools, not automated tests.
