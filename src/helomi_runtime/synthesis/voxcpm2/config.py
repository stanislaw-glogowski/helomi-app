from pydantic import FilePath

from helomi_foundation import ConfigModel, HFModel

_DEFAULT_MODEL_ID = "openbmb/VoxCPM2"


class VoxCPM2Settings(ConfigModel):
    model: HFModel = HFModel.default_field(_DEFAULT_MODEL_ID)
    load_denoiser: bool = False


class VoxCPM2Profile(ConfigModel):
    ref_audio: FilePath | None = None
    inference: int = 7
    cfg_value: float = 2.6
    min_len: int = 2
    max_len: int = 1024
    normalize: bool = False
    denoise: bool = False
