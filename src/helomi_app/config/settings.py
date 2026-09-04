from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import Field, PrivateAttr

from helomi_common import BaseConfig, ConfigFile
from helomi_core.audio import AudioSettings
from helomi_core.stt import STTSettings
from helomi_core.tts import TTSSettings
from helomi_core.turn import TurnSettings
from helomi_core.vad import VADSettings
from helomi_core.wakeword import WakeWordSettings

from ..resources import ResourceCatalog
from ..server import ServerSettings
from .profile import ProfileSettings


class Settings(BaseConfig):
    _CONFIG_FILE: ClassVar[str] = "settings"

    profile: ProfileSettings = Field(default_factory=ProfileSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    turn: TurnSettings = Field(default_factory=TurnSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    wakeword: WakeWordSettings = Field(default_factory=WakeWordSettings)

    _root_path: Path = PrivateAttr()

    @property
    def root_path(self) -> Path:
        return self._root_path

    @classmethod
    def load(cls, resources: ResourceCatalog) -> Self:
        root_path = resources.root_path
        data = ConfigFile.read_configs(root_path / cls._CONFIG_FILE)

        if not data:
            raise ValueError(f"No settings file found: {root_path}")

        return cls.model_validate(
            data,
            context={
                "root_path": root_path,
            },
        )

    def model_post_init(self, context: dict[str, Any]) -> None:
        if isinstance(context, dict):
            self._set_private_attr("root_path", context.get("root_path"))
