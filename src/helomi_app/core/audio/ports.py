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

    def play(self, audio: RawAudio, profile_id: str, is_final: bool) -> bool:
        result = self.execute_command(
            PlayCmd(
                audio=audio,
                profile_id=profile_id,
                is_final=is_final,
            )
        )

        return result

    def interrupt(self, profile_id: str) -> bool:
        return self.execute_command(
            InterruptCmd(
                profile_id=profile_id,
            )
        )

    def start_room_voice(self, profile_id: str) -> bool:
        return self.execute_command(
            StartRoomVoiceCmd(
                profile_id=profile_id,
            )
        )

    def stop_room_voice(self) -> bool:
        return self.execute_command(
            StopRoomVoiceCmd(),
        )

    def disconnect(self) -> bool:
        return self.execute_command(
            DisconnectCmd(),
        )

    @abstractmethod
    def execute_command(self, cmd: AudioCmd) -> bool:
        raise NotImplementedError
