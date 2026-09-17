from abc import ABC, abstractmethod

from ...common import AbstractAdapter
from ..audio import AudioChunk
from .domain import VADPrediction


class VADAdapter[TSettings](AbstractAdapter[TSettings], ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk) -> VADPrediction:
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError
