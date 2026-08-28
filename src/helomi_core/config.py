from pathlib import Path
from typing import ClassVar

from pydantic import Field

from helomi_common import BaseConfig

from .audio import AudioSettings
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
    profile: ProfileSettings
    audio: AudioSettings
    stt: STTSettings
    tts: TTSSettings
    turn: TurnSettings
    vad: VADSettings
    wakeword: WakeWordSettings
    root_path: Path = Field(exclude=True)
