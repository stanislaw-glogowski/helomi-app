from abc import ABC, abstractmethod
from collections.abc import Iterator

from helomi_common import AbstractAdapter

from .domain import STTChunk, STTRequest


class STTAdapter[TConfig, TOptions](AbstractAdapter[TConfig], ABC):
    @abstractmethod
    def transcribe(
        self,
        request: STTRequest,
        options: TOptions,
    ) -> Iterator[Exception | STTChunk]:
        raise NotImplementedError
