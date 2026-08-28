from pydantic import Field, FilePath

from helomi_common import BaseConfig, HFModel

_DEFAULT_MODEL_ID = "openbmb/VoxCPM2"


class VoxCPM2Config(BaseConfig):
    model: HFModel = Field(
        validation_alias="model_id",
        default_factory=lambda _: HFModel(_DEFAULT_MODEL_ID),
    )
    load_denoiser: bool = False


class VoxCPM2Options(BaseConfig):
    ref_audio: FilePath | None = None
    inference: int = 7
    cfg_value: float = 2.6
    min_len: int = 2
    max_len: int = 1024
    normalize: bool = False
    denoise: bool = False
