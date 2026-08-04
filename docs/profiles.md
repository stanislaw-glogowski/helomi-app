# Profiles

A profile defines an assistant identity and adapter-compatible runtime choices.
It does not choose global technical adapters; those belong in `settings.yml`.

## Required layout

```text
locales/<language>/profiles/<profile-id>/
├── profile.yml
├── profile.override.yml          # optional local override
├── prompts/
│   ├── system.md
│   ├── opening.md
│   └── summary.md
└── reactions/
    ├── wake.txt
    ├── acknowledge.txt
    ├── wait.txt
    ├── background.txt
    └── quit.txt
```

All eight content files are required. Prompt paths are fixed and reaction files
contain one non-empty phrase per line. `acknowledge.txt` and `wait.txt` need at
least four unique entries. Profile id is the directory name; `name` is the
displayed name.

`profile.override.yml` is optional and deep-merged over `profile.yml` before
validation. It can locally replace model parameters or set `wakeword: null` for
always-listening mode; prompt and reaction files remain fixed.

## Example

```yaml
name: Alexa

conversation:
  models:
    fast:
      model_id: mlx-community/gemma-4-26b-a4b-it-4bit
      max_tokens: 256
      temperature: 0.15
    detailed:
      model_id: mlx-community/gemma-4-26b-a4b-it-4bit
      max_tokens: 512
      temperature: 0.25
    classifier:
      model_id: mlx-community/gemma-4-26b-a4b-it-4bit
      max_tokens: 8
      temperature: 0.0
  recent_messages: 8

wakeword:
  label: Alexa
  model_path: alexa_v0.1.onnx

tts:
  model_path: pl/pl_PL/gosia/medium/pl_PL-gosia-medium.onnx

mcp:
  endpoints:
    - id: calendar
      transport: streamable_http
      url: https://example.test/mcp
      mode: background
      require_confirmation: true
      headers_from_env:
        Authorization: HELOMI_CALENDAR_AUTHORIZATION
```

The optional wake-word model must be an `.onnx` filename that exists under
`<data-root>/models`. `wakeword.label` is human-facing; it is not inferred from
the model filename. Omit the entire `wakeword` section to start in
always-listening mode; Helomi then processes speech immediately and does not
load an OpenWakeWord model.

## Create a profile

1. Copy an existing profile directory under `<data-root>/locales/<language>/profiles`.
2. Rename the directory to the new stable profile id and set its display `name`.
3. Replace all prompts and reactions, retaining the required filenames.
4. Optionally set a wake-word label and place the matching ONNX model in
   `<data-root>/models`; omit the section for always-listening mode.
5. Set model fields accepted by the adapters selected in `settings.yml`.
6. Start Helomi and inspect the profile picker for validation errors.

Do not commit personal prompts, local model paths, recordings, or private
endpoints unless they are intentionally versioned defaults. Add an override to
`settings.override.yml` for machine-specific technical choices.

## Tools and MCP

Helomi always exposes only local text-file tools and a quit action. Files are
limited to `<data-root>/data/**/*.txt`; writing requires an explicit `create`
or `replace` request. Tool calls may omit the `.txt` extension, so `test` resolves
to `test.txt`; any other extension is rejected. The directory is watched so
external changes appear in the file catalog without restarting the app.

`mcp.endpoints` is optional. An endpoint is either `streamable_http` with a URL
and optional request headers read from environment variables, or `stdio` with a
literal executable and argument list. Stdio never invokes a shell and receives
only a minimal environment plus explicitly mapped values. `mode` is
`immediate` or `background`; background calls run one at a time and later add a
spoken summary to the current conversation. An unavailable endpoint disables
only its own tools.
