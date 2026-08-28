from typing import Literal

from pydantic import Field, FilePath

from helomi_common import BaseConfig, HFModel

type _ModelName = Literal["supertonic", "supertonic-2", "supertonic-3"]
type _VoiceName = Literal["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]

_DEFAULT_MODEL_ID = "Supertone/supertonic-3"


class SupertonicConfig(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    language: str = "en"
    intra_threads: int | None = None
    inter_threads: int | None = None


class SupertonicOptions(BaseConfig):
    language: str | None = None
    voice_name: _VoiceName = "F1"
    voice_path: FilePath | None = None
    quality: int = 8
    speed: float = 1.0
    max_chunk_length: int | None = None
    silence_duration: float = 0.3
