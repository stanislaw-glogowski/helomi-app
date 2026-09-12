import random
from pathlib import Path
from typing import Any, ClassVar, Self

import emoji
from pydantic import Field, PrivateAttr, field_validator

from helomi_common import BaseConfig, ConfigFile, DeepMergeDict, PromptReader

from ..audio.config import AudioProfile
from ..stt.config import STTProfile
from ..tts.config import TTSProfile
from ..wakeword.config import WakeWordProfile
from .domain import ReactionKind


class Profile(BaseConfig, PromptReader):
    DEFAULT_ID: ClassVar[str] = "alexa"
    DEFAULT_PRIORITY: ClassVar[int] = 100

    _CONFIG_FILE: ClassVar[str] = "profile"

    priority: int = 0
    name: str
    description: str | None = None
    emoji: str = "👤"
    disabled: bool = False
    readonly: bool = False

    reactions: dict[ReactionKind, list[str] | None] = Field(default_factory=dict)

    audio: AudioProfile = Field(default_factory=AudioProfile)
    stt: STTProfile = Field(default_factory=STTProfile)
    tts: TTSProfile = Field(default_factory=TTSProfile)
    wakeword: WakeWordProfile = Field(default_factory=WakeWordProfile)

    _id: str = PrivateAttr()
    _root_path: Path = PrivateAttr()
    _prompts: dict[str, str] = PrivateAttr()

    @property
    def id(self) -> str:
        return self._id

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def prompts(self) -> dict[str, str]:
        return self._prompts

    def dump(
        self,
        require_prompt: str | None = None,
        active_id: str | None = None,
        default_id: str | None = None,
    ) -> dict[str, Any]:
        if require_prompt:
            prompt = self.prompts.get(require_prompt, None)
            if prompt is None:
                return {}
        else:
            prompt = None

        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "prompt": prompt,
            "has_wakeword": self.wakeword.extract_adapter(False) is not None,
            "is_active": self.id == active_id,
            "is_default": self.id == default_id,
            "is_readonly": self.readonly,
        }

    @classmethod
    def load(
        cls,
        root_path: Path,
        settings_data: DeepMergeDict,
        default_id: str,
        prompt_params: dict[str, str],
        defaults_data: DeepMergeDict | None = None,
    ) -> Self | None:
        config = ConfigFile.read_configs(root_path / cls._CONFIG_FILE)
        if not config:
            return None

        data = (
            defaults_data.merged_with(config) if defaults_data else config
        ).merged_with(settings_data)
        id = root_path.name

        if id == default_id:
            data["priority"] = cls.DEFAULT_PRIORITY

        model = cls.model_validate(
            data,
            context={
                "id": id,
                "root_path": root_path,
                "prompts": cls._read_prompts(
                    root_path,
                    {
                        **prompt_params,
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                    },
                ),
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

    @field_validator("emoji", mode="before")
    @classmethod
    def validate_emoji(cls, value: Any) -> str:
        if not value:
            return "👤"
        if not emoji.is_emoji(value):
            raise ValueError(f"Input should be a single emoji, got {value!r}")
        return value

    def model_post_init(self, context: Any) -> None:
        if context and isinstance(context, dict):
            for key in ("id", "root_path", "prompts"):
                self._set_private_attr(key, context.get(key))

    def get_reaction(self, kind: ReactionKind) -> str | None:
        reactions = self.reactions.get(kind)
        if not reactions:
            return None
        return random.choice(reactions)
