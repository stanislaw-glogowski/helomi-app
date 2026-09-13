from dataclasses import dataclass

from ..audio import AudioChunk

type DetectionEvent = (
    ProfileDetectedEvent
    | UtteranceStartedEvent
    | UtteranceDetectedEvent
    | UtteranceContinuedEvent
    | ConversationEndedEvent
    | None
)


@dataclass(frozen=True, slots=True)
class ProfileDetectedEvent:
    profile_id: str


@dataclass(frozen=True, slots=True)
class UtteranceStartedEvent:
    pass


@dataclass(frozen=True, slots=True)
class UtteranceContinuedEvent:
    pass


@dataclass(frozen=True, slots=True)
class UtteranceDetectedEvent:
    audio: AudioChunk


@dataclass(frozen=True, slots=True)
class ConversationEndedEvent:
    pass
