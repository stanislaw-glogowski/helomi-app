from pathlib import Path
from typing import Any, ClassVar, Self

from pydantic import Field, PrivateAttr

from helomi_common import BaseConfig, ConfigFile, PromptReader

from ..audio.config import AudioSettings
from ..profile.config import ProfileSettings
from ..resources import ResourceCatalog
from ..server.config import ServerSettings
from ..stt.config import STTSettings
from ..tts.config import TTSSettings
from ..turn.config import TurnSettings
from ..vad.config import VADSettings
from ..wakeword.config import WakeWordSettings


class Settings(BaseConfig, PromptReader):
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
    _prompts: dict[str, str] = PrivateAttr()

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def prompts(self) -> dict[str, str]:
        return self._prompts

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
                "prompts": cls._read_prompts(root_path),
            },
        )

    def model_post_init(self, context: dict[str, Any]) -> None:
        for key in ("root_path", "prompts"):
            self._set_private_attr(key, context.get(key))
