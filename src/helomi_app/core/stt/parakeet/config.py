from pydantic import Field

from ....common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v3"


class ParakeetSettings(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    language: str = "en"


class ParakeetProfile(BaseConfig):
    language: str | None = None
