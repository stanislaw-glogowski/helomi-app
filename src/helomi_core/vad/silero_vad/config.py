from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, FilePath, Tag

from helomi_common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "mlx-community/silero-vad"


def _silero_vad_discriminator(v: Any) -> str:
    if isinstance(v, dict):
        return v.get("engine", "mlx")
    return getattr(v, "engine", "mlx")


type SileroVADConfig = Annotated[
    Annotated[SileroVADMLXConfig, Tag("mlx")]
    | Annotated[SileroVADONNXConfig, Tag("onnx")],
    Discriminator(_silero_vad_discriminator),
]


class _BaseConfig(BaseConfig):
    threshold: float = 0.5


class SileroVADMLXConfig(_BaseConfig):
    engine: Literal["mlx"] = "mlx"
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    model_path: Path | None = None


class SileroVADONNXConfig(_BaseConfig):
    engine: Literal["onnx"] = "onnx"
    model_path: FilePath
    model_id: str | None = None
