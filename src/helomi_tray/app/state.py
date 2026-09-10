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
        server_url: str | None
        room_voice: bool
        wake_word: bool

    status: AppStatus = AppStatus.STARTING
    mode: AppMode = AppMode.SERVER
    profile_id: str | None = None
    server_url: str | None = None
    room_voice: bool = True
    wake_word: bool = True
