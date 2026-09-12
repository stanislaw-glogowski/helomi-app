from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..audio import RawAudio
from ..profile import ReactionKind

if TYPE_CHECKING:
    from .extension import PipelineExtension
else:
    PipelineExtension = object

type PipelineExtensionType = type[PipelineExtension]
type PipelineExtensionLike = PipelineExtensionType | PipelineExtension


class PipelineOptions(BaseModel):
    greeting_enabled: bool = True
    room_voice_enabled: bool = True
    wakeword_enabled: bool = False


type PipelineCmd = Annotated[
    SetOptionsCmd | ActivateProfileCmd | DeactivateProfileCmd | SayCmd,
    Field(discriminator="type"),
]

type PipelineEvent = Annotated[
    OptionsSetEvent
    | ExtensionActivatedEvent
    | ExtensionDeactivatedEvent
    | ProfileActivatedEvent
    | ProfileDeactivatedEvent
    | TranscriptionReadyEvent
    | SpeechInterruptedEvent
    | SynthesisReadyEvent,
    Field(discriminator="type"),
]


# base


class _BaseMsg(BaseModel):
    trace_id: str | None = None


class _BaseEvent(_BaseMsg):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    extension: PipelineExtensionType | None = Field(default=None, exclude=True)


class _OptionsChanges(BaseModel):
    greeting_enabled: bool | None = None
    room_voice_enabled: bool | None = None
    wakeword_enabled: bool | None = None


class _ProfileCmd(_BaseMsg):
    profile_id: str | None = None


class _ProfileEvent(_BaseEvent):
    profile_id: str


# commands


class SetOptionsCmd(_OptionsChanges):
    type: Literal["set_options"] = "set_options"


class ActivateProfileCmd(_ProfileCmd):
    type: Literal["activate_profile"] = "activate_profile"


class DeactivateProfileCmd(_BaseMsg):
    type: Literal["deactivate_profile"] = "deactivate_profile"


class SayTextCmd(_ProfileCmd):
    type: Literal["say_text"] = "say_text"
    text: str


class SayReactionCmd(_ProfileCmd):
    type: Literal["say_reaction"] = "say_reaction"
    reaction: ReactionKind


type SayCmd = SayTextCmd | SayReactionCmd


# events


class OptionsSetEvent(_BaseEvent, _OptionsChanges):
    type: Literal["options_set"] = "options_set"


class ExtensionActivatedEvent(_BaseEvent):
    type: Literal["extension_activated"] = "extension_activated"
    active_profile_id: str | None
    options: PipelineOptions


class ExtensionDeactivatedEvent(_BaseEvent):
    type: Literal["extension_deactivated"] = "extension_deactivated"


class ProfileActivatedEvent(_ProfileEvent):
    type: Literal["profile_activated"] = "profile_activated"


class ProfileDeactivatedEvent(_ProfileEvent):
    type: Literal["profile_deactivated"] = "profile_deactivated"


class TranscriptionReadyEvent(_ProfileEvent):
    type: Literal["transcription_ready"] = "transcription_ready"
    text: str


class SynthesisReadyEvent(_ProfileEvent):
    type: Literal["synthesis_ready"] = "synthesis_ready"
    audio: RawAudio | None = Field(default=None, exclude=True)


class SpeechInterruptedEvent(_ProfileEvent):
    type: Literal["speech_interrupted"] = "speech_interrupted"
