from abc import ABC, abstractmethod

from helomi_common import AbstractAdapter

from ..audio import AudioChunk
from .domain import WakeWordPrediction


class WakeWordAdapter[TConfig, TOptions](AbstractAdapter[TConfig], ABC):
    def __init__(
        self,
        config: TConfig,
        words: dict[str, TOptions],
    ) -> None:
        super().__init__(config)
        self._words = words

    @abstractmethod
    def predict(self, audio: AudioChunk, voice_detected: bool) -> WakeWordPrediction:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError
