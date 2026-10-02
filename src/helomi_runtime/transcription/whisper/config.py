from helomi_foundation import ConfigModel, HFModel

_DEFAULT_MODEL_ID = "mlx-community/whisper-large-v3-turbo"


class WhisperSettings(ConfigModel):
    model: HFModel = HFModel.default_field(_DEFAULT_MODEL_ID)


class WhisperProfile(ConfigModel):
    language: str | None = None
    initial_prompt: str | None = None
