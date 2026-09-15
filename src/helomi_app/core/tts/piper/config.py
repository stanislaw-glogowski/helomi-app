from pydantic import Field, FilePath

from ....common import BaseConfig


class PiperSettings(BaseConfig):
    normalize_audio: bool = True
    volume: float = Field(default=1.0, gt=0.0)


class PiperProfile(BaseConfig):
    model_path: FilePath
    config_path: FilePath
    speaker_id: int | None = Field(default=None, ge=0)
    length_scale: float | None = Field(default=None, gt=0.0)
    noise_scale: float | None = Field(default=None, ge=0.0)
    noise_w_scale: float | None = Field(default=None, ge=0.0)
