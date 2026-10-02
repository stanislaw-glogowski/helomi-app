from pydantic import Field, FilePath

from helomi_foundation import ConfigModel


class RoomVoiceProfile(ConfigModel):
    path: FilePath
    volume: float = Field(default=0.25, ge=0.0, le=1.0)
    ducking: float = Field(default=0.35, ge=0.0, le=1.0)
