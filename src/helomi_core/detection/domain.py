from dataclasses import dataclass
from enum import IntEnum, auto

from ..audio import AudioChunk

type DetectionResult = (
    ProfileDetected | UtteranceDetected | UtteranceContinued | ConversationEnded | None
)


class DetectionMode(IntEnum):
    PROFILE = auto()
    UTTERANCE = auto()


@dataclass(frozen=True, slots=True)
class ProfileDetected:
    profile_id: str


@dataclass(frozen=True, slots=True)
class UtteranceContinued:
    pass


@dataclass(frozen=True, slots=True)
class UtteranceDetected:
    audio: AudioChunk


@dataclass(frozen=True, slots=True)
class ConversationEnded:
    pass
