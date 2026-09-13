from abc import ABC, abstractmethod

from ..audio import AudioChunk
from ..common import AbstractAdapter
from .domain import TurnPrediction


class TurnAdapter[TSettings](AbstractAdapter[TSettings], ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> TurnPrediction | None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError
