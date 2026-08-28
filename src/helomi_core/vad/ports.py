from abc import ABC, abstractmethod

from helomi_common import AbstractAdapter

from ..audio import AudioChunk
from .domain import VADPrediction


class VADAdapter[TConfig](AbstractAdapter[TConfig], ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk) -> VADPrediction:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError
