from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from helomi_common import AbstractAsyncComponent

from .domain import AudioMode, RawAudio


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
    async def interrupt(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def start_room_voice(self):
        raise NotImplementedError

    @abstractmethod
    async def stop_room_voice(self):
        raise NotImplementedError
