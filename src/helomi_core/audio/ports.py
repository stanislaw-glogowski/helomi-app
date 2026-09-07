from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from helomi_common import AbstractAsyncComponent

from .domain import AudioMode, RawAudio

if TYPE_CHECKING:
    from .config import AudioProfile


class AudioDriver[TConfig](AbstractAsyncComponent, ABC):
    def __init__(self, config: TConfig, mode: AudioMode | None) -> None:
        super().__init__()
        self._config = config
        self._mode = AudioMode.DUPLEX if mode is None else mode

    @property
    def mode(self) -> AudioMode:
        return self._mode

    @abstractmethod
    def capture(self) -> AsyncIterator[RawAudio]:
        raise NotImplementedError

    @abstractmethod
    def play(self, audio: RawAudio) -> None:
        raise NotImplementedError

    @abstractmethod
    async def interrupt(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def activate(self, profile: AudioProfile) -> None:
        raise NotImplementedError

    @abstractmethod
    async def deactivate(self) -> None:
        raise NotImplementedError
