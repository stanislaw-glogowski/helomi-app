import base64
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _BaseMessage(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
    )


# events


class ConnectedEvent(_BaseMessage):
    type: Literal["connected"] = Field(alias="event")
    protocol: str
    version: str


class StartFormat(_BaseMessage):
    encoding: str
    sample_rate: int = Field(alias="sampleRate")
    channels: int


class StartData(_BaseMessage):
    account_sid: str = Field(alias="accountSid")
    stream_sid: str = Field(alias="streamSid")
    call_sid: str = Field(alias="callSid")
    tracks: list[str]
    format: StartFormat = Field(alias="mediaFormat")
    custom_parameters: dict[str, Any] = Field(
        default_factory=dict,
        alias="customParameters",
    )


class StartEvent(_BaseMessage):
    type: Literal["start"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    start: StartData


class MediaData(_BaseMessage):
    track: str
    chunk: str
    timestamp: str
    payload: str


class MediaEvent(_BaseMessage):
    type: Literal["media"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    media: MediaData

    @property
    def data(self) -> bytes:
        return base64.b64decode(self.media.payload)


class StopEvent(_BaseMessage):
    type: Literal["stop"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    stop: StopData


class StopData(_BaseMessage):
    account_sid: str = Field(alias="accountSid")
    call_sid: str = Field(alias="callSid")


class MarkEvent(_BaseMessage):
    type: Literal["mark"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    mark: MarkData


class MarkData(_BaseMessage):
    name: str


TwilioEvent = TypeAdapter(
    Annotated[
        ConnectedEvent | StartEvent | MediaEvent | StopEvent | MarkEvent,
        Field(discriminator="type"),
    ]
)

# commands


class MediaCmd(_BaseMessage):
    event: Literal["media"] = "media"
    stream_sid: str = Field(alias="streamSid")
    media: dict[str, str]

    @classmethod
    def create(cls, data: bytes) -> Self:
        payload = base64.b64encode(data).decode("utf-8")
        return cls(
            media={
                "payload": payload,
            },
        )


class ClearCmd(_BaseMessage):
    event: Literal["clear"] = "clear"
    stream_sid: str = Field(alias="streamSid")


class MarkCmd(_BaseMessage):
    event: Literal["mark"] = "mark"
    stream_sid: str = Field(alias="streamSid")
    mark: dict[str, str]

    @classmethod
    def create(cls, name: str) -> Self:
        return cls(
            mark={
                "name": name,
            },
        )


type TwilioCmd = MediaCmd | ClearCmd | MarkCmd
