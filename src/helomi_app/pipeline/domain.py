from typing import Annotated, Literal

from pydantic import BaseModel, Field

type PipelineCmd = Annotated[
    ActivateProfile | DeactivateProfile | SayText,
    Field(discriminator="type"),
]

type PipelineEvent = Annotated[
    ProfileActivated | ProfileDeactivated | TranscriptionReady,
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


class ProfileActivated(PipelineMessage):
    type: Literal["profile_activated"] = "profile_activated"
    profile_id: str


class ProfileDeactivated(PipelineMessage):
    type: Literal["profile_deactivated"] = "profile_deactivated"
    profile_id: str


class TranscriptionReady(PipelineMessage):
    type: Literal["transcription_ready"] = "transcription_ready"
    profile_id: str
    text: str
