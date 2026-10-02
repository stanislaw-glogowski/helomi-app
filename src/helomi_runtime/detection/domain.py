from dataclasses import dataclass
from enum import IntEnum, StrEnum, auto

from ..audio import AudioChunk


class DetectionMode(IntEnum):
    WAKEWORD = auto()
    UTTERANCE = auto()


class TurnStatus(StrEnum):
    STARTED = auto()
    COMPLETED = auto()
    CONTINUED = auto()
    TIMEOUT = auto()


@dataclass(frozen=True, slots=True)
class TurnPrediction:
    status: TurnStatus
    audio: AudioChunk | None = None
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class VADPrediction:
    detected: bool
    score: float


@dataclass(frozen=True, slots=True)
class WakeWordPrediction:
    matched: str | None
    scores: dict[str, float]
