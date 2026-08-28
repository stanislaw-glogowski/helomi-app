from dataclasses import dataclass
from enum import StrEnum, auto

from ..audio import AudioChunk


class TurnStatus(StrEnum):
    COMPLETED = auto()
    CONTINUED = auto()
    TIMEOUT = auto()


@dataclass(frozen=True, slots=True)
class TurnPrediction:
    status: TurnStatus
    audio: AudioChunk | None = None
    score: float = 0.0
