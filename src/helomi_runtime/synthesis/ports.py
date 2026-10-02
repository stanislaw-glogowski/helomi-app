from abc import ABC, abstractmethod
from collections.abc import Iterator

from helomi_foundation import SyncManagedComponent

from .domain import SynthesisChunk, SynthesisRequest


class SynthesisAdapter[TSettings, TProfile](SyncManagedComponent, ABC):
    def __init__(self, settings: TSettings, profiles: dict[str, TProfile]):
        super().__init__()
        self._settings = settings
        self._profiles = profiles

    @abstractmethod
    def synthesize(
        self, request: SynthesisRequest
    ) -> Iterator[Exception | SynthesisChunk]:
        raise NotImplementedError
