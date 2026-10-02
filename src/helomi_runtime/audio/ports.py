from abc import ABC, abstractmethod

from helomi_foundation import EventSource

from .domain import AudioDriverDescriptor, AudioDriverState, RawAudio
from .messages import (
    AudioCommand,
    AudioEvent,
    DisconnectCommand,
    InterruptCommand,
    PlayCommand,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)


class AudioDriver[TSettings, TProfile](EventSource[AudioEvent], ABC):
    """Define capture, playback, and remote-session driver operations."""

    def __init__(self, settings: TSettings, profiles: dict[str, TProfile]):
        super().__init__()
        self._settings = settings
        self._profiles = profiles

    @property
    @abstractmethod
    def descriptor(self) -> AudioDriverDescriptor:
        raise NotImplementedError

    @property
    def state(self) -> AudioDriverState:
        return AudioDriverState.READY if self.is_mounted else AudioDriverState.STOPPED

    async def play(
        self,
        audio: RawAudio,
        *,
        playback_id: str | None = None,
        turn_id: int | None = None,
    ) -> bool:
        return await self.execute_command(
            PlayCommand(
                audio=audio,
                playback_id=playback_id,
                turn_id=turn_id,
            )
        )

    async def interrupt(
        self,
        audio: RawAudio | None = None,
        *,
        turn_id: int | None = None,
    ) -> bool:
        return await self.execute_command(
            InterruptCommand(
                audio=audio,
                turn_id=turn_id,
            )
        )

    async def start_room_voice(self, profile_id: str) -> bool:
        return await self.execute_command(
            StartRoomVoiceCommand(
                profile_id=profile_id,
            )
        )

    async def stop_room_voice(self) -> bool:
        return await self.execute_command(
            StopRoomVoiceCommand(),
        )

    async def disconnect(self, audio: RawAudio | None = None) -> bool:
        return await self.execute_command(
            DisconnectCommand(
                audio=audio,
            ),
        )

    @abstractmethod
    async def execute_command(self, cmd: AudioCommand) -> bool:
        raise NotImplementedError
