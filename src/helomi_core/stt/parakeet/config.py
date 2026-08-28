from pydantic import Field

from helomi_common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v3"


class ParakeetConfig(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    language: str = "en"


class ParakeetOptions(BaseConfig):
    language: str | None = None
