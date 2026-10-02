from enum import StrEnum, auto
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from helomi_runtime.audio import RawAudio
from helomi_runtime.reaction import ReactionKind

from .config import ResponseMode


class ActivationSource(StrEnum):
    TRAY = auto()
    WAKEWORD = auto()
    TWILIO = auto()
    CLI = auto()


class ConversationState(StrEnum):
    IDLE = auto()
    ARMED = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    CLOSING = auto()


class CommandRejectionCode(StrEnum):
    INVALID_STATE = auto()
    PROFILE_NOT_FOUND = auto()
    PROFILE_MISMATCH = auto()
    PROFILE_REQUIRED = auto()
    MODE_INACTIVE = auto()
    DRIVER_NOT_FOUND = auto()
    CONFIRMATION_REQUIRED = auto()
    UNSUPPORTED = auto()
    BUSY = auto()
    EMPTY_TEXT = auto()
    STALE_TURN = auto()


class CommandResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    rejection_code: CommandRejectionCode | None = None
    detail: str | None = None

    @classmethod
    def ok(cls) -> CommandResult:
        return cls(accepted=True)

    @classmethod
    def reject(
        cls,
        rejection_code: CommandRejectionCode,
        detail: str | None = None,
    ) -> CommandResult:
        return cls(accepted=False, rejection_code=rejection_code, detail=detail)


class _Message(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
    )

    trace_id: str | None = None


class _ProfileCommand(_Message):
    profile_id: str


class ActivateProfileCommand(_ProfileCommand):
    type: Literal["activate_profile"] = "activate_profile"
    source: ActivationSource


class DeactivateProfileCommand(_Message):
    type: Literal["deactivate_profile"] = "deactivate_profile"
    play_farewell: bool = True


class _TurnCommand(_Message):
    session_id: str | None = None
    turn_id: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_turn(self):
        if (self.session_id is None) != (self.turn_id is None):
            raise ValueError("session_id and turn_id must be provided together")
        return self


class SayTextCommand(_TurnCommand):
    type: Literal["say_text"] = "say_text"
    text: str
    mode: ResponseMode
    profile_id: str | None = None


class SayReactionCommand(_TurnCommand):
    type: Literal["say_reaction"] = "say_reaction"
    reaction: ReactionKind
    mode: ResponseMode
    profile_id: str | None = None


class SetResponseModeCommand(_Message):
    type: Literal["set_response_mode"] = "set_response_mode"
    mode: ResponseMode


class SwitchDriverCommand(_Message):
    type: Literal["switch_driver"] = "switch_driver"
    driver_id: str
    end_remote_session: bool = False


class SetMonitoringCommand(_Message):
    type: Literal["set_monitoring"] = "set_monitoring"
    enabled: bool


class SetConversationOptionsCommand(_Message):
    type: Literal["set_conversation_options"] = "set_conversation_options"
    persistent_profile: bool | None = None
    reactions: bool | None = None
    room_voice: bool | None = None
    wakeword: bool | None = None


class EndConversationCommand(_TurnCommand):
    type: Literal["end_conversation"] = "end_conversation"
    play_farewell: bool = True
    wait_for_speech: bool = False


type ApplicationCommand = Annotated[
    ActivateProfileCommand
    | DeactivateProfileCommand
    | SayTextCommand
    | SayReactionCommand
    | SetResponseModeCommand
    | SwitchDriverCommand
    | SetMonitoringCommand
    | SetConversationOptionsCommand
    | EndConversationCommand,
    Field(discriminator="type"),
]


class _Event(_Message):
    session_id: str | None = None
    turn_id: int | None = None


class ProfileActivatedEvent(_Event):
    type: Literal["profile_activated"] = "profile_activated"
    profile_id: str
    source: ActivationSource


class ProfileDeactivatedEvent(_Event):
    type: Literal["profile_deactivated"] = "profile_deactivated"
    profile_id: str


class TranscriptionReadyEvent(_Event):
    type: Literal["transcription_ready"] = "transcription_ready"
    profile_id: str
    text: str


class SynthesisReadyEvent(_Event):
    type: Literal["synthesis_ready"] = "synthesis_ready"
    profile_id: str
    text: str
    audio: RawAudio = Field(exclude=True)


class SpeechInterruptedEvent(_Event):
    type: Literal["speech_interrupted"] = "speech_interrupted"
    profile_id: str


class ProcessingFailedEvent(_Event):
    type: Literal["processing_failed"] = "processing_failed"
    profile_id: str | None = None
    stage: Literal["detection", "transcription", "synthesis", "playback"]
    detail: str


class DriverChangedEvent(_Event):
    type: Literal["driver_changed"] = "driver_changed"
    driver_id: str
    previous_driver_id: str | None = None


class CallStartedEvent(_Event):
    type: Literal["call_started"] = "call_started"
    profile_id: str
    caller: str
    monitoring: bool


class CallEndedEvent(_Event):
    type: Literal["call_ended"] = "call_ended"
    profile_id: str | None = None


class ResponseModeChangedEvent(_Event):
    type: Literal["response_mode_changed"] = "response_mode_changed"
    mode: ResponseMode
    previous_mode: ResponseMode | None = None


class ConversationStateChangedEvent(_Event):
    type: Literal["conversation_state_changed"] = "conversation_state_changed"
    state: ConversationState
    previous_state: ConversationState


class ConversationOptionsChangedEvent(_Event):
    type: Literal["conversation_options_changed"] = "conversation_options_changed"
    persistent_profile: bool
    reactions: bool
    room_voice: bool
    wakeword: bool


type ApplicationEvent = Annotated[
    ProfileActivatedEvent
    | ProfileDeactivatedEvent
    | TranscriptionReadyEvent
    | SynthesisReadyEvent
    | SpeechInterruptedEvent
    | ProcessingFailedEvent
    | DriverChangedEvent
    | CallStartedEvent
    | CallEndedEvent
    | ResponseModeChangedEvent
    | ConversationStateChangedEvent
    | ConversationOptionsChangedEvent,
    Field(discriminator="type"),
]


__all__ = [
    "ActivateProfileCommand",
    "ActivationSource",
    "ApplicationCommand",
    "ApplicationEvent",
    "CallEndedEvent",
    "CallStartedEvent",
    "CommandRejectionCode",
    "CommandResult",
    "ConversationOptionsChangedEvent",
    "ConversationState",
    "ConversationStateChangedEvent",
    "DeactivateProfileCommand",
    "DriverChangedEvent",
    "EndConversationCommand",
    "ProcessingFailedEvent",
    "ProfileActivatedEvent",
    "ProfileDeactivatedEvent",
    "ResponseMode",
    "ResponseModeChangedEvent",
    "SayReactionCommand",
    "SayTextCommand",
    "SetConversationOptionsCommand",
    "SetMonitoringCommand",
    "SetResponseModeCommand",
    "SpeechInterruptedEvent",
    "SwitchDriverCommand",
    "SynthesisReadyEvent",
    "TranscriptionReadyEvent",
]
