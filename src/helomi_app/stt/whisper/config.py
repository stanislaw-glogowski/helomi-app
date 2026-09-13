from pydantic import Field

from ...common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "mlx-community/whisper-large-v3-turbo"


class WhisperSettings(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    language: str = "en"


class WhisperProfile(BaseConfig):
    language: str | None = None
    initial_prompt: str | None = None
