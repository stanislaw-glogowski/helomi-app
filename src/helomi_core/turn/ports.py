from abc import ABC, abstractmethod

from helomi_common import AbstractAdapter

from ..audio import AudioChunk
from .domain import TurnPrediction


class TurnAdapter[TConfig](AbstractAdapter[TConfig], ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> TurnPrediction | None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError
