from pathlib import Path
from typing import ClassVar

from pydantic import Field

from helomi_common import BaseConfig

from .audio import AudioSettings
from .server.config import ServerSettings
from .stt import STTProfile, STTSettings
from .tts import TTSProfile, TTSSettings
from .turn import TurnSettings
from .vad import VADSettings
from .wakeword import WakeWordProfile, WakeWordSettings


class Profile(BaseConfig):
    DEFAULT_ID: ClassVar[str] = "default"

    id: str = Field(exclude=True)
    name: str
    disabled: bool = Field(exclude=True, default=False)
    stt: STTProfile = Field(default_factory=STTProfile)
    tts: TTSProfile = Field(default_factory=TTSProfile)
    wakeword: WakeWordProfile = Field(default_factory=WakeWordProfile)
    root_path: Path = Field(exclude=True)

    @property
    def label(self) -> str:
        return f"{self.name}({self.id})"


class ProfileSettings(BaseConfig):
    default: str = Profile.DEFAULT_ID


class Settings(BaseConfig):
    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    turn: TurnSettings = Field(default_factory=TurnSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    wakeword: WakeWordSettings = Field(default_factory=WakeWordSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    root_path: Path = Field(exclude=True)
