from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TypedDict

from helomi_app.core.audio import AudioDriverKind


class AppStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    QUITING = auto()


class AppMode(StrEnum):
    SERVER = auto()
    PARROT = auto()
    TTS = auto()


@dataclass(frozen=True, slots=True)
class AppState:
    class Update(TypedDict, total=False):
        status: AppStatus
        mode: AppMode
        profile_id: str | None
        api_url: str | None
        persistent_profile_enabled: bool
        persistent_profile_supported: bool
        reactions_enabled: bool
        reactions_supported: bool
        room_voice_enabled: bool
        room_voice_supported: bool
        wakeword_enabled: bool
        wakeword_supported: bool
        audio_driver: AudioDriverKind

    status: AppStatus = AppStatus.STARTING
    mode: AppMode = AppMode.SERVER
    profile_id: str | None = None
    api_url: str | None = None
    persistent_profile_enabled: bool = False
    persistent_profile_supported: bool = False
    reactions_enabled: bool = False
    reactions_supported: bool = False
    room_voice_enabled: bool = False
    room_voice_supported: bool = False
    wakeword_enabled: bool = False
    wakeword_supported: bool = False
    audio_driver: AudioDriverKind = AudioDriverKind.LOCAL
