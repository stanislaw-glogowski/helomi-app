from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from helomi_core import Profile

type SpeechCmd = Annotated[
    ActivateProfile | DeactivateProfile | SayText,
    Field(discriminator="type"),
]

type SpeechEvent = Annotated[
    ProfileActivated | ProfileDeactivated | TranscriptionReady,
    Field(discriminator="type"),
]


class _BaseMessage(BaseModel):
    trace_id: str | None = None


class _BaseCmd(_BaseMessage):
    pass


class ActivateProfile(_BaseCmd):
    type: Literal["activate_profile"] = "activate_profile"
    profile_id: str | None = None


class DeactivateProfile(_BaseCmd):
    type: Literal["deactivate_profile"] = "deactivate_profile"


class SayText(_BaseCmd):
    type: Literal["say_text"] = "say_text"
    profile_id: str | None = None
    text: str


class _BaseEvent(_BaseMessage):
    profile_id: str


class ProfileActivated(_BaseEvent):
    type: Literal["profile_activated"] = "profile_activated"


class ProfileDeactivated(_BaseEvent):
    type: Literal["profile_deactivated"] = "profile_deactivated"


class TranscriptionReady(_BaseEvent):
    type: Literal["transcription_ready"] = "transcription_ready"
    text: str


@dataclass(frozen=True, slots=True)
class SpeechRequest[TData]:
    profile_id: str
    data: TData
    trace_id: str | None = None

    def verify_profile(self, profile: Profile | None) -> Profile | None:
        return (
            profile if profile is not None and self.profile_id == profile.id else None
        )
