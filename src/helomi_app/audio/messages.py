from dataclasses import dataclass

from .domain import RawAudio

type AudioCmd = (
    PlayCmd | InterruptCmd | StartRoomVoiceCmd | StopRoomVoiceCmd | DisconnectCmd
)
type AudioEvent = (
    CapturedEvent
    | PlayedEvent
    | InterruptedEvent
    | RoomVoiceStartedEvent
    | RoomVoiceStoppedEvent
    | DisconnectedEvent
)


@dataclass(frozen=True, slots=True)
class PlayCmd:
    audio: RawAudio
    profile_id: str


@dataclass(frozen=True, slots=True)
class DisconnectCmd:
    pass


@dataclass(frozen=True, slots=True)
class InterruptCmd:
    profile_id: str


@dataclass(frozen=True, slots=True)
class StartRoomVoiceCmd:
    profile_id: str


@dataclass(frozen=True, slots=True)
class StopRoomVoiceCmd:
    pass


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    audio: RawAudio
    profile_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlayedEvent:
    profile_id: str


@dataclass(frozen=True, slots=True)
class InterruptedEvent:
    profile_id: str


@dataclass(frozen=True, slots=True)
class DisconnectedEvent:
    pass


@dataclass(frozen=True, slots=True)
class RoomVoiceStartedEvent:
    profile_id: str


@dataclass(frozen=True, slots=True)
class RoomVoiceStoppedEvent:
    pass
