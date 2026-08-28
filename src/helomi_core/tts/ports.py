from abc import ABC, abstractmethod
from collections.abc import Iterator

from helomi_common import AbstractAdapter

from .domain import TTSChunk, TTSRequest


class TTSAdapter[TConfig, TOptions](AbstractAdapter[TConfig], ABC):
    @abstractmethod
    def synthesize(
        self,
        request: TTSRequest,
        options: TOptions,
    ) -> Iterator[Exception | TTSChunk]:
        raise NotImplementedError
