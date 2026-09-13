from abc import ABC, abstractmethod

from ..audio import AudioChunk
from ..common import AbstractAdapter
from .domain import WakeWordPrediction


class WakeWordAdapter[TSettings, TProfile](AbstractAdapter[TSettings], ABC):
    def __init__(
        self,
        settings: TSettings,
        profiles: dict[str, TProfile],
    ) -> None:
        super().__init__(settings)
        self._profiles = profiles

    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> WakeWordPrediction:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError
