from abc import ABC, abstractmethod

from ...common import AbstractEventSource
from .domain import AudioDriverKind, RawAudio
from .messages import (
    AudioCmd,
    AudioEvent,
    DisconnectCmd,
    InterruptCmd,
    PlayCmd,
    StartRoomVoiceCmd,
    StopRoomVoiceCmd,
)


class AudioDriver[TSettings, TProfile](AbstractEventSource[AudioEvent], ABC):
    def __init__(self, settings: TSettings, profiles: dict[str, TProfile]) -> None:
        super().__init__()
        self._settings = settings
        self._profiles = profiles

    @property
    @abstractmethod
    def kind(self) -> AudioDriverKind:
        raise NotImplementedError

    @property
    @abstractmethod
    def room_voice_supported(self) -> bool:
        raise NotImplementedError

    async def play(self, audio: RawAudio) -> bool:
        return await self.execute_command(PlayCmd(audio=audio))

    async def interrupt(self) -> bool:
        return await self.execute_command(InterruptCmd())

    async def start_room_voice(self, profile_id: str) -> bool:
        return await self.execute_command(
            StartRoomVoiceCmd(
                profile_id=profile_id,
            )
        )

    async def stop_room_voice(self) -> bool:
        return await self.execute_command(
            StopRoomVoiceCmd(),
        )

    async def disconnect(self) -> bool:
        return await self.execute_command(
            DisconnectCmd(),
        )

    @abstractmethod
    async def execute_command(self, cmd: AudioCmd) -> bool:
        raise NotImplementedError
