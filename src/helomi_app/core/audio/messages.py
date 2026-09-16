from dataclasses import dataclass

from .domain import RawAudio

type AudioCmd = (
    PlayCmd | InterruptCmd | StartRoomVoiceCmd | StopRoomVoiceCmd | DisconnectCmd
)
type AudioEvent = CapturedEvent | DisconnectedEvent


@dataclass(frozen=True, slots=True)
class PlayCmd:
    audio: RawAudio


@dataclass(frozen=True, slots=True)
class DisconnectCmd:
    pass


@dataclass(frozen=True, slots=True)
class InterruptCmd:
    pass


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
class DisconnectedEvent:
    pass
