import random
from pathlib import Path
from typing import Any, ClassVar, Self

import emoji
from pydantic import Field, PrivateAttr, field_validator

from helomi_common import BaseConfig, ConfigFile, DeepMergeDict

from ..audio.config import AudioProfile
from ..stt.config import STTProfile
from ..tts.config import TTSProfile
from ..wakeword.config import WakeWordProfile
from .domain import ReactionKind


class Profile(BaseConfig):
    DEFAULT_ID: ClassVar[str] = "alexa"
    _CONFIG_FILE: ClassVar[str] = "profile"

    name: str
    emoji: str | None = None
    disabled: bool = False
    readonly: bool = False

    reactions: dict[ReactionKind, list[str] | None] = Field(default_factory=dict)

    audio: AudioProfile = Field(default_factory=AudioProfile)
    stt: STTProfile = Field(default_factory=STTProfile)
    tts: TTSProfile = Field(default_factory=TTSProfile)
    wakeword: WakeWordProfile = Field(default_factory=WakeWordProfile)

    _id: str = PrivateAttr()
    _root_path: Path = PrivateAttr()

    @property
    def id(self) -> str:
        return self._id

    @property
    def root_path(self) -> Path:
        return self._root_path

    @classmethod
    def load(
        cls,
        root_path: Path,
        settings_data: DeepMergeDict,
        defaults_data: DeepMergeDict | None = None,
    ) -> Self | None:
        config = ConfigFile.read_configs(root_path / cls._CONFIG_FILE)
        if not config:
            return None

        data = (
            defaults_data.merged_with(config) if defaults_data else config
        ).merged_with(settings_data)

        model = cls.model_validate(
            data,
            context={
                "id": root_path.name,
                "root_path": root_path,
            },
        )

        if (
            model.disabled
            or model.stt.extract_adapter(False) is None
            or model.tts.extract_adapter(False) is None
        ):
            return None

        return model

    @field_validator("reactions", mode="before")
    @classmethod
    def validate_reactions(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        cleaned: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(v, str):
                cleaned[k] = [v]
            else:
                cleaned[k] = v
        return cleaned

    @field_validator("emoji")
    @classmethod
    def validate_emoji(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not emoji.is_emoji(value):
            raise ValueError(f"Input should be a single emoji, got {value!r}")
        return value

    def model_post_init(self, context: Any) -> None:
        if context and isinstance(context, dict):
            for key in ("id", "root_path"):
                self._set_private_attr(key, context.get(key))

    def get_reaction(self, kind: ReactionKind) -> str | None:
        reactions = self.reactions.get(kind)
        if not reactions:
            return None
        return random.choice(reactions)
