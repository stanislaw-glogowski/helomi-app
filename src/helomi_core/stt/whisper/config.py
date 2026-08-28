from pydantic import Field

from helomi_common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "mlx-community/whisper-large-v3-turbo"


class WhisperConfig(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    language: str = "en"


class WhisperOptions(BaseConfig):
    language: str | None = None
    initial_prompt: str | None = None
