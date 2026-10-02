from collections.abc import Iterable, Iterator
from typing import ClassVar, Literal, Self

from helomi_foundation import ConfigFile

from ..resources import ResourceCatalog
from .profile import Profile
from .settings import Settings

type ProfileSection = Literal["transcription", "synthesis", "wakeword"]


class ProfileCatalog(Iterable[Profile]):
    """Index validated profiles and unique Twilio callee assignments."""

    _DEFAULTS_FILE: ClassVar[str] = "defaults"

    def __init__(self, profiles: dict[str, Profile]):
        self._profiles = profiles
        self._callee_profiles = self._index_callees(profiles.values())

    def __iter__(self) -> Iterator[Profile]:
        return iter(self._profiles.values())

    def __len__(self) -> int:
        return len(self._profiles)

    def get(self, profile_id: str) -> Profile | None:
        """Return a profile when it exists."""
        return self._profiles.get(profile_id)

    def require(self, profile_id: str) -> Profile:
        """Return a profile or raise a descriptive lookup error."""
        profile = self.get(profile_id)
        if profile is None:
            raise KeyError(f"Profile not found: {profile_id}")
        return profile

    def find_by_callee(self, callee: str) -> Profile | None:
        profile_id = self._callee_profiles.get(callee)
        return self._profiles.get(profile_id) if profile_id is not None else None

    def collect_adapter_profiles[T](
        self,
        section: ProfileSection,
        adapter: str,
        *,
        required: bool = False,
    ) -> dict[str, T]:
        profiles: dict[str, T] = {}
        for profile in self:
            value: T | None
            match section:
                case "transcription":
                    value = profile.get_transcription_profile(
                        adapter, required=required
                    )
                case "synthesis":
                    value = profile.get_synthesis_profile(adapter, required=required)
                case "wakeword":
                    value = profile.get_wakeword_profile(adapter)
            if value is not None:
                profiles[profile.id] = value
        return profiles

    def collect_audio_profiles[T](self, driver: str) -> dict[str, T]:
        profiles: dict[str, T] = {}
        for profile in self:
            value = profile.get_audio_profile(driver)  # type: ignore[arg-type]
            if value is not None:
                profiles[profile.id] = value
        return profiles

    @classmethod
    def load(cls, settings: Settings, resources: ResourceCatalog) -> Self:
        base_path = resources.path_for("profiles")
        defaults_data = ConfigFile.read_merged(
            base_path / cls._DEFAULTS_FILE, resolve_references=False
        )
        profiles: dict[str, Profile] = {}

        if base_path.is_dir():
            for root_path in sorted(base_path.iterdir()):
                if not root_path.is_dir():
                    continue
                profile = Profile.load(
                    root_path,
                    settings.prompts,
                    defaults_data,
                    settings=settings,
                )
                if profile is not None:
                    profiles[profile.id] = profile

        if not profiles:
            raise RuntimeError(f"No supported profiles found in {base_path}")

        return cls(
            dict(
                sorted(
                    profiles.items(),
                    key=lambda item: (-item[1].priority, item[0]),
                )
            )
        )

    @staticmethod
    def _index_callees(profiles: Iterable[Profile]) -> dict[str, str]:
        callees: dict[str, str] = {}
        for profile in profiles:
            twilio = profile.audio.twilio
            if twilio is None:
                continue
            for callee in twilio.callees:
                if existing := callees.get(callee):
                    raise ValueError(
                        f"Twilio callee {callee!r} is assigned to both "
                        f"{existing!r} and {profile.id!r}"
                    )
                callees[callee] = profile.id
        return callees
