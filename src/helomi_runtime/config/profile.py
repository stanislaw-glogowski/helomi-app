from pathlib import Path
from typing import Any, ClassVar, Self

import emoji
from pydantic import Field, PrivateAttr, field_validator

from helomi_foundation import (
    ConfigFile,
    ConfigModel,
    DeepMergeDict,
    PromptReader,
)

from ..audio.config import AudioDriverId, AudioProfile
from ..detection.config import WakeWordProfiles
from ..reaction import ReactionKind
from ..selection import select_configs
from ..synthesis.config import SynthesisProfile
from ..transcription.config import TranscriptionProfile
from .extractor import AdapterExtractor
from .settings import Settings


class Profile(ConfigModel, PromptReader):
    """Validated persona and per-adapter runtime configuration."""

    _CONFIG_FILE: ClassVar[str] = "profile"

    priority: int = 0
    name: str
    description: str | None = None
    emoji: str = "👤"
    disabled: bool = False
    readonly: bool = False
    reactions: dict[ReactionKind, list[str] | None] = Field(default_factory=dict)
    audio: AudioProfile = Field(default_factory=AudioProfile)
    transcription: TranscriptionProfile = Field(default_factory=TranscriptionProfile)
    synthesis: SynthesisProfile = Field(default_factory=SynthesisProfile)
    wakeword: WakeWordProfiles = Field(default_factory=WakeWordProfiles)

    _id: str = PrivateAttr()
    _config_path: Path = PrivateAttr()
    _root_path: Path = PrivateAttr()
    _prompts: dict[str, str] = PrivateAttr()

    @property
    def id(self) -> str:
        return self._id

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def root_path(self) -> Path:
        return self._root_path

    @property
    def prompts(self) -> dict[str, str]:
        return self._prompts

    @property
    def has_room_voice(self) -> bool:
        return any(
            profile is not None and profile.room_voice is not None
            for profile in (self.audio.avfaudio, self.audio.twilio)
        )

    def get_audio_profile(self, driver_id: AudioDriverId):
        return AdapterExtractor.extract(
            driver_id,
            self.audio,
            required=False,
            profile_id=self.id,
            path=self.config_path,
            section="audio",
        )

    def get_transcription_profile(self, adapter: str, *, required: bool = True):
        return AdapterExtractor.extract(
            adapter,
            self.transcription,
            required=required,
            profile_id=self.id,
            path=self.config_path,
            section="transcription",
        )

    def get_synthesis_profile(self, adapter: str, *, required: bool = True):
        return AdapterExtractor.extract(
            adapter,
            self.synthesis,
            required=required,
            profile_id=self.id,
            path=self.config_path,
            section="synthesis",
        )

    def get_wakeword_profile(self, adapter: str):
        return AdapterExtractor.extract(
            adapter,
            self.wakeword,
            required=False,
            profile_id=self.id,
            path=self.config_path,
            section="wakeword",
        )

    def to_public_dict(
        self,
        require_prompt: str | None = None,
        active_id: str | None = None,
    ) -> dict[str, Any]:
        prompt = self.prompts.get(require_prompt) if require_prompt else None
        if require_prompt and prompt is None:
            return {}
        return {
            "id": self.id,
            "name": self.name,
            "emoji": self.emoji,
            "prompt": prompt,
            "has_wakeword": any(
                value is not None for value in self.wakeword.model_dump().values()
            ),
            "is_active": self.id == active_id,
            "is_readonly": self.readonly,
        }

    @classmethod
    def load(
        cls,
        root_path: Path,
        prompt_params: dict[str, str],
        defaults_data: DeepMergeDict | None = None,
        *,
        settings: Settings | None = None,
    ) -> Self | None:
        config_path = cls._resolve_config_path(root_path / cls._CONFIG_FILE)
        config = ConfigFile.read_merged(
            root_path / cls._CONFIG_FILE, resolve_references=False
        )
        if config is None:
            return None
        data = defaults_data.merged_with(config) if defaults_data else config
        profile_id = root_path.name
        if settings is not None:
            synthesis = data.get("synthesis")
            if synthesis is None:
                return None
            if (
                isinstance(synthesis, dict)
                and synthesis.get(settings.synthesis.adapter) is None
            ):
                return None
            data = DeepMergeDict(data)
            data["synthesis"] = select_configs(
                synthesis,
                ("supertonic", "voxcpm2", "piper"),
                (settings.synthesis.adapter,),
                defaults=False,
            )
            data["transcription"] = select_configs(
                data.get("transcription", {}),
                ("parakeet", "whisper"),
                (settings.transcription.adapter,),
            )
            wakeword = settings.detection.wakeword
            data["wakeword"] = select_configs(
                data.get("wakeword", {}),
                ("openwakeword",),
                (wakeword.adapter,) if wakeword is not None else (),
                defaults=False,
            )
            data["audio"] = select_configs(
                data.get("audio", {}),
                ("avfaudio", "twilio"),
                settings.audio.drivers,
                defaults=False,
            )
        data = ConfigFile.resolve_references(data)

        try:
            model = cls.model_validate(
                data,
                context={
                    "id": profile_id,
                    "config_path": config_path,
                    "root_path": root_path,
                    "prompts": cls._read_prompts(
                        root_path,
                        {
                            **prompt_params,
                            "name": str(data.get("name", "")),
                            "description": str(data.get("description", "")),
                        },
                    ),
                },
            )
        except ValueError as error:
            raise ValueError(
                f"Invalid profile {profile_id!r} in {config_path}: {error}"
            ) from error

        return None if model.disabled else model

    @classmethod
    def _resolve_config_path(cls, stem: Path) -> Path:
        for suffix in (".yml", ".yaml", ".json"):
            path = stem.with_suffix(suffix)
            if path.is_file():
                return path
        return stem

    @field_validator("emoji", mode="before")
    @classmethod
    def validate_emoji(cls, value: Any) -> str:
        if not value:
            return "👤"
        if not emoji.is_emoji(value):
            raise ValueError(f"Input should be a single emoji, got {value!r}")
        return value

    @field_validator("reactions", mode="before")
    @classmethod
    def validate_reactions(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: [item] if isinstance(item, str) else item
            for key, item in value.items()
        }

    def model_post_init(self, context: Any):
        if isinstance(context, dict):
            for key in ("id", "config_path", "root_path", "prompts"):
                self._set_private_attr(key, context.get(key))
