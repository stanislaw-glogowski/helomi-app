# Privacy and models

## Local-first boundary

The supplied configuration runs capture, transcription, language-model
inference, synthesis, and playback locally. Initialization downloads models and
assets from external sources. A LangChain configuration can point to an
Ollama-compatible `base_url`; review that endpoint before calling the setup
private or offline.

## Local data

The Helomi data root contains settings, prompts, wake-word models, and may also
contain downloaded assets and benchmark data. Keep it outside version control
when it contains personal material. Never commit recordings, generated audio,
benchmark output, model caches, API credentials, or private endpoints.

Voice recordings can be biometric data. Use anonymous identifiers, obtain
informed consent before recording another person, agree retention/deletion
rules, and obtain guardian consent for children.

## Licenses

Helomi source is licensed under MIT. Dependencies, model weights, voices,
wake-word assets, and Hugging Face repositories are separate works with their
own licenses, attribution, redistribution, and commercial-use conditions.
Check each model card and download source before redistribution or commercial
use. The repository license does not relicense downloaded models.
