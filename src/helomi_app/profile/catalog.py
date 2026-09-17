from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, overload

from ..common import AdapterExtractor, ConfigFile, DeepMergeDict
from ..resources import ResourceCatalog

if TYPE_CHECKING:
    from ..settings import Settings

from .profile import Profile


class ProfileCatalog(Iterable[Profile]):
    _DEFAULTS_FILE: ClassVar[str] = "defaults"

    def __init__(self, profiles: dict[str, Profile]):
        self._profiles = profiles

    def __iter__(self) -> Iterator[Profile]:
        return iter(self._profiles.values())

    def __len__(self) -> int:
        return len(self._profiles)

    @overload
    def get(self, key: str, throw_on_not_found: Literal[True] = True) -> Profile: ...

    @overload
    def get(self, key: str, throw_on_not_found: Literal[False]) -> Profile | None: ...

    def get(self, key: str, throw_on_not_found=True) -> Profile | None:
        found = self._profiles.get(key, None)
        if found is None and throw_on_not_found:
            raise KeyError(f"Profile not found: {key}")
        return found

    def get_adapter_profiles[TProfile](
        self,
        adapter: Literal[
            "audio",
            "stt",
            "tts",
            "wakeword",
        ],
    ) -> dict[str, TProfile]:
        profiles: dict[str, Any] = {}

        for profile_id, profile in self._profiles.items():
            extractor: AdapterExtractor[Any] | None = None

            match adapter:
                case "audio":
                    extractor = profile.audio
                case "stt":
                    extractor = profile.stt
                case "tts":
                    extractor = profile.tts
                case "wakeword":
                    extractor = profile.wakeword

            if value := extractor.extract_adapter(False) if extractor else None:
                profiles[profile_id] = value

        return profiles

    @classmethod
    def load(cls, settings: Settings, resources: ResourceCatalog) -> Self:
        base_path = resources.build_path("profiles")

        settings_data = DeepMergeDict(
            {
                "audio": {"adapter": settings.audio.adapter},
                "stt": {"adapter": settings.stt.adapter},
                "tts": {"adapter": settings.tts.adapter},
                "wakeword": {"adapter": settings.wakeword.adapter},
            }
        )

        defaults_data = ConfigFile.read_configs(
            path=base_path / cls._DEFAULTS_FILE,
        )

        profiles = {
            profile.id: profile
            for root_path in base_path.iterdir()
            if (
                profile := Profile.load(
                    root_path,
                    settings_data,
                    settings.profile.default,
                    settings.prompts,
                    defaults_data,
                )
            )
            is not None
        }

        if not profiles:
            raise RuntimeError("No supported profile found")

        return cls(
            profiles=dict(
                sorted(
                    profiles.items(), key=lambda item: item[1].priority, reverse=True
                )
            ),
        )
