# Profiles

A profile defines an assistant identity and adapter-compatible runtime choices.
It does not choose global technical adapters; those belong in `settings.yml`.

## Required layout

```text
profiles/<profile-id>/
├── profile.yml
├── prompts/
│   ├── system.md
│   ├── opening.md
│   └── summary.md
└── reactions/
    ├── wake.txt
    └── wait.txt
```

All six content files are required. Prompt paths are fixed and reaction files
contain one non-empty phrase per line. Profile id is the directory name; `name`
is the displayed name.

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
```

The wake-word model must be an `.onnx` filename that exists under
`<data-root>/models`. `wakeword.label` is human-facing; it is not inferred from
the model filename.

## Create a profile

1. Copy an existing profile directory under `<data-root>/profiles`.
2. Rename the directory to the new stable profile id and set its display `name`.
3. Replace all prompts and reactions, retaining the required filenames.
4. Set a wake-word label and place the matching ONNX model in `<data-root>/models`.
5. Set model fields accepted by the adapters selected in `settings.yml`.
6. Start Helomi and inspect the profile picker for validation errors.

Do not commit personal prompts, local model paths, recordings, or private
endpoints unless they are intentionally versioned defaults. Add an override to
`settings.override.yml` for machine-specific technical choices.
