from abc import ABC, abstractmethod

from helomi_foundation import SyncManagedComponent

from ..audio import AudioChunk
from .domain import TurnPrediction, VADPrediction, WakeWordPrediction


class TurnAdapter(SyncManagedComponent, ABC):
    def reset_idle_timeout(self) -> None:
        """Restart inactivity tracking without discarding an active utterance."""

    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> TurnPrediction | None:
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError


class VADAdapter(SyncManagedComponent, ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk) -> VADPrediction:
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        raise NotImplementedError


class WakeWordAdapter(SyncManagedComponent, ABC):
    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> WakeWordPrediction:
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError
