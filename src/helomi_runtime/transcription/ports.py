from abc import ABC, abstractmethod
from collections.abc import Iterator

from helomi_foundation import SyncManagedComponent

from .domain import TranscriptionChunk, TranscriptionRequest


class TranscriptionAdapter[TSettings, TProfile](SyncManagedComponent, ABC):
    def __init__(self, settings: TSettings, profiles: dict[str, TProfile]):
        super().__init__()
        self._settings = settings
        self._profiles = profiles

    @abstractmethod
    def transcribe(
        self, request: TranscriptionRequest
    ) -> Iterator[Exception | TranscriptionChunk]:
        raise NotImplementedError
