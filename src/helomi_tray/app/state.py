from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TypedDict

from helomi_app import AudioDriverDescriptor, ConversationState, ResponseMode


class TrayStatus(StrEnum):
    STARTING = auto()
    RUNNING = auto()
    QUITTING = auto()


@dataclass(frozen=True, slots=True)
class TrayState:
    class Update(TypedDict, total=False):
        status: TrayStatus
        response_mode: ResponseMode
        conversation_state: ConversationState
        profile_id: str | None
        api_url: str | None
        persistent_profile: bool
        reactions: bool
        room_voice: bool
        wakeword: bool
        active_driver_id: str | None
        driver_descriptors: tuple[AudioDriverDescriptor, ...]
        remote_session: bool
        monitoring: bool

    status: TrayStatus = TrayStatus.STARTING
    response_mode: ResponseMode = ResponseMode.PARROT
    conversation_state: ConversationState = ConversationState.IDLE
    profile_id: str | None = None
    api_url: str | None = None
    persistent_profile: bool = False
    reactions: bool = False
    room_voice: bool = False
    wakeword: bool = False
    active_driver_id: str | None = None
    driver_descriptors: tuple[AudioDriverDescriptor, ...] = ()
    remote_session: bool = False
    monitoring: bool = False
