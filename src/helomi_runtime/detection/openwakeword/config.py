from pydantic import Field, FilePath

from helomi_foundation import ConfigModel


class OpenWakeWordConfig(ConfigModel):
    threshold: float = 0.75
    patience: int = Field(default=2, ge=1)
    embedding_path: FilePath
    melspec_path: FilePath
    frame_size: int = 1280


class OpenWakeWordProfile(ConfigModel):
    label: str | None = None
    model_path: FilePath
    threshold: float | None = None
    patience: int | None = Field(default=None, ge=1)
