from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, overload

import emoji
from pydantic import Field, PrivateAttr, field_validator

from helomi_common import BaseConfig, ConfigFile, DeepMergeDict

from ..audio import AudioProfile
from ..resources import ResourceCatalog
from ..stt import STTProfile
from ..tts import TTSProfile
from ..wakeword import WakeWordProfile

if TYPE_CHECKING:
    from .settings import Settings


class Profile(BaseConfig):
    DEFAULT_ID: ClassVar[str] = "alexa"
    _CONFIG_FILE: ClassVar[str] = "profile"

    name: str
    emoji: str | None = None
    disabled: bool = False
    readonly: bool = False

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

        model = cls.model_validate(
            (
                defaults_data.merged_with(config) if defaults_data else config
            ).merged_with(settings_data),
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


class ProfileSettings(BaseConfig):
    default: str = Profile.DEFAULT_ID


class ProfileCatalog(Iterable[Profile]):
    _DEFAULTS_FILE: ClassVar[str] = "defaults"

    def __init__(
        self,
        settings: ProfileSettings,
        profiles: dict[str, Profile],
    ):
        self._default_profile: Profile = (
            profile
            if (profile := profiles.get(settings.default))
            else next(iter(profiles.values()))
        )
        self._profiles = profiles

    def __iter__(self) -> Iterator[Profile]:
        return iter(self._profiles.values())

    def __len__(self) -> int:
        return len(self._profiles)

    @overload
    def get(self, key: str | None, throw_on_not_found: Literal[True] = True) -> Profile:
        pass

    @overload
    def get(
        self, key: str | None, throw_on_not_found: Literal[False]
    ) -> Profile | None:
        pass

    def get(self, key: str | None, throw_on_not_found=True) -> Profile | None:
        if key is None:
            return self._default_profile

        found = self._profiles.get(key, None)
        if found is None and throw_on_not_found:
            raise KeyError(f"Profile not found: {key}")
        return found

    @classmethod
    def load(cls, settings: Settings, resources: ResourceCatalog) -> Self:
        base_path = resources.build_path("profiles")

        settings_data = DeepMergeDict(
            {
                "stt": {"adapter": settings.stt.adapter},
                "tts": {"adapter": settings.tts.adapter},
                "wakeword": {"adapter": settings.wakeword.adapter},
            }
        )

        defaults_data = ConfigFile.read_configs(
            path=base_path / cls._DEFAULTS_FILE,
        )

        return cls(
            settings=settings.profile,
            profiles={
                profile.id: profile
                for root_path in base_path.iterdir()
                if (profile := Profile.load(root_path, settings_data, defaults_data))
                is not None
            },
        )
