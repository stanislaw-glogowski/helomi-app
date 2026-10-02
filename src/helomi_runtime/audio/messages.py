from dataclasses import dataclass
from typing import Literal

from .domain import RawAudio

type AudioCommand = (
    PlayCommand
    | InterruptCommand
    | StartRoomVoiceCommand
    | StopRoomVoiceCommand
    | DisconnectCommand
)


@dataclass(frozen=True, slots=True)
class PlayCommand:
    audio: RawAudio
    playback_id: str | None = None
    turn_id: int | None = None


@dataclass(frozen=True, slots=True)
class DisconnectCommand:
    audio: RawAudio | None = None


@dataclass(frozen=True, slots=True)
class InterruptCommand:
    audio: RawAudio | None = None
    turn_id: int | None = None


@dataclass(frozen=True, slots=True)
class StartRoomVoiceCommand:
    profile_id: str


@dataclass(frozen=True, slots=True)
class StopRoomVoiceCommand:
    pass


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    audio: RawAudio
    profile_id: str | None = None
    driver_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectedEvent:
    driver_id: str
    profile_id: str
    call_sid: str
    caller: str


@dataclass(frozen=True, slots=True)
class PlaybackFinishedEvent:
    driver_id: str
    playback_id: str
    status: Literal["played", "interrupted", "failed"] = "played"


@dataclass(frozen=True, slots=True)
class DisconnectedEvent:
    driver_id: str | None = None
    call_sid: str | None = None


@dataclass(frozen=True, slots=True)
class RouteChangedEvent:
    driver_id: str
    previous_driver_id: str | None
    profile_id: str | None = None


type AudioEvent = (
    CapturedEvent
    | ConnectedEvent
    | DisconnectedEvent
    | PlaybackFinishedEvent
    | RouteChangedEvent
)
