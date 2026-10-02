from typing import Any, Literal

from pydantic import Field, model_validator

from helomi_foundation import ConfigFile, ConfigModel

from ..selection import select_configs
from .avfaudio.config import AVFAudioProfile, AVFAudioSettings
from .room_voice import RoomVoiceProfile
from .twilio.config import TwilioProfile, TwilioSettings

type AudioDriverId = Literal["avfaudio", "twilio"]
type AudioDriverSettings = AVFAudioSettings | TwilioSettings


class AudioRouterSettings(ConfigModel):
    initial_driver: AudioDriverId
    monitor_driver: AudioDriverId | None = None
    drivers: list[AudioDriverId] = Field(min_length=1)
    avfaudio: AVFAudioSettings | None = None
    twilio: TwilioSettings | None = None

    @model_validator(mode="before")
    @classmethod
    def select_drivers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        drivers = ConfigFile.resolve_references(data.get("drivers", []))
        data = {**data, "drivers": drivers}
        selected = (
            [value for value in drivers if isinstance(value, str)]
            if isinstance(drivers, list)
            else []
        )
        return ConfigFile.resolve_references(
            select_configs(data, ("avfaudio", "twilio"), selected)
        )

    @model_validator(mode="after")
    def validate_routes(self):
        driver_ids = self.drivers
        duplicates = sorted(
            driver_id
            for driver_id in set(driver_ids)
            if driver_ids.count(driver_id) > 1
        )
        if duplicates:
            raise ValueError(f"Duplicate audio drivers: {', '.join(duplicates)}")
        if self.initial_driver not in driver_ids:
            raise ValueError(
                f"Initial audio driver is not configured: {self.initial_driver}"
            )
        if self.monitor_driver is not None and self.monitor_driver not in driver_ids:
            raise ValueError(
                f"Monitor audio driver is not configured: {self.monitor_driver}"
            )
        if self.monitor_driver == "twilio":
            raise ValueError("Twilio cannot be used as a monitor audio driver")
        return self

    def require_driver_settings(self, driver_id: AudioDriverId) -> AudioDriverSettings:
        settings = getattr(self, driver_id, None)
        if driver_id not in self.drivers or settings is None:
            raise KeyError(f"Audio driver is not configured: {driver_id}")
        return settings


class AudioProfile(ConfigModel):
    avfaudio: AVFAudioProfile | None = None
    twilio: TwilioProfile | None = None

    def find_driver_profile(
        self, driver_id: AudioDriverId
    ) -> AVFAudioProfile | TwilioProfile | None:
        return getattr(self, driver_id)


__all__ = [
    "AudioDriverId",
    "AudioDriverSettings",
    "AudioProfile",
    "AudioRouterSettings",
    "RoomVoiceProfile",
]
