from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..common import AbstractAdapter
from .domain import STTChunk, STTRequest


class STTAdapter[TSettings, TProfile](AbstractAdapter[TSettings], ABC):
    def __init__(self, settings: TSettings, profiles: dict[str, TProfile]) -> None:
        super().__init__(settings)
        self._profiles = profiles

    @abstractmethod
    def transcribe(self, request: STTRequest) -> Iterator[Exception | STTChunk]:
        raise NotImplementedError
