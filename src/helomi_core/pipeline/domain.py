from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..audio import AudioChunk, RawAudio

type PipelineCmd = Annotated[
    ActivateProfile | DeactivateProfile | SayText,
    Field(discriminator="type"),
]

type PipelineEvent = Annotated[
    ProfileActivated
    | ProfileDeactivated
    | TranscriptionReady
    | SpeechInterrupted
    | SynthesisReady,
    Field(discriminator="type"),
]


class PipelineMessage(BaseModel):
    trace_id: str | None = None


# commands


class ActivateProfile(PipelineMessage):
    type: Literal["activate_profile"] = "activate_profile"
    profile_id: str | None = None


class DeactivateProfile(PipelineMessage):
    type: Literal["deactivate_profile"] = "deactivate_profile"


class SayText(PipelineMessage):
    type: Literal["say_text"] = "say_text"
    profile_id: str | None = None
    text: str


# events


class ProfileEvent(PipelineMessage):
    profile_id: str


class ProfileActivated(ProfileEvent):
    type: Literal["profile_activated"] = "profile_activated"


class ProfileDeactivated(ProfileEvent):
    type: Literal["profile_deactivated"] = "profile_deactivated"


class TranscriptionReady(ProfileEvent):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    type: Literal["transcription_ready"] = "transcription_ready"
    text: str
    audio: AudioChunk | RawAudio | None = Field(default=None, exclude=True)


class SynthesisReady(ProfileEvent):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    type: Literal["synthesis_ready"] = "synthesis_ready"
    text: str
    audio: RawAudio | None = Field(default=None, exclude=True)


class SpeechInterrupted(ProfileEvent):
    type: Literal["speech_interrupted"] = "speech_interrupted"
