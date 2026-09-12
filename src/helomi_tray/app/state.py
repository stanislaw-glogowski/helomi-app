from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TypedDict


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
        greeting_enabled: bool
        room_voice_enabled: bool
        wakeword_enabled: bool

    status: AppStatus = AppStatus.STARTING
    mode: AppMode = AppMode.SERVER
    profile_id: str | None = None
    api_url: str | None = None
    greeting_enabled: bool | None = None
    room_voice_enabled: bool | None = None
    wakeword_enabled: bool | None = None
