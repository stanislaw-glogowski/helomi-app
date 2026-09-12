from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, ClassVar, Literal, Self, overload

from helomi_common import ConfigFile, DeepMergeDict

from ..resources import ResourceCatalog

if TYPE_CHECKING:
    from ..settings import Settings

from .config import ProfileSettings
from .profile import Profile


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
    def get(
        self, key: str | None, throw_on_not_found: Literal[True] = True
    ) -> Profile: ...

    @overload
    def get(
        self, key: str | None, throw_on_not_found: Literal[False]
    ) -> Profile | None: ...

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

        return cls(
            settings=settings.profile,
            profiles=dict(
                sorted(
                    profiles.items(), key=lambda item: item[1].priority, reverse=True
                )
            ),
        )
