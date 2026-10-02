import base64
import binascii
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _BaseMessage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


# Messages received from Twilio.


class ConnectedMessage(_BaseMessage):
    type: Literal["connected"] = Field(alias="event")
    protocol: str
    version: str


class MediaFormat(_BaseMessage):
    encoding: str
    sample_rate: int = Field(alias="sampleRate")
    channels: int


class StartPayload(_BaseMessage):
    account_sid: str = Field(alias="accountSid")
    stream_sid: str = Field(alias="streamSid")
    call_sid: str = Field(alias="callSid")
    tracks: list[str]
    format: MediaFormat = Field(alias="mediaFormat")
    custom_parameters: dict[str, Any] = Field(
        default_factory=dict,
        alias="customParameters",
    )


class StartMessage(_BaseMessage):
    type: Literal["start"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    start: StartPayload


class MediaPayload(_BaseMessage):
    track: str
    chunk: str
    timestamp: str
    payload: str


class MediaMessage(_BaseMessage):
    type: Literal["media"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    media: MediaPayload

    @property
    def data(self) -> bytes:
        try:
            return base64.b64decode(self.media.payload, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Invalid base64 Twilio media payload") from error


class StopMessage(_BaseMessage):
    type: Literal["stop"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    stop: StopPayload


class StopPayload(_BaseMessage):
    account_sid: str = Field(alias="accountSid")
    call_sid: str = Field(alias="callSid")


class MarkMessage(_BaseMessage):
    type: Literal["mark"] = Field(alias="event")
    sequence_number: str = Field(alias="sequenceNumber")
    stream_sid: str = Field(alias="streamSid")
    mark: MarkPayload


class MarkPayload(_BaseMessage):
    name: str


TwilioMessageAdapter = TypeAdapter(
    Annotated[
        ConnectedMessage | StartMessage | MediaMessage | StopMessage | MarkMessage,
        Field(discriminator="type"),
    ]
)

# Commands sent to Twilio.


class MediaCommand(_BaseMessage):
    event: Literal["media"] = "media"
    stream_sid: str = Field(default="", alias="streamSid")
    media: dict[str, str]

    @classmethod
    def create(cls, data: bytes) -> Self:
        payload = base64.b64encode(data).decode("utf-8")
        return cls(
            media={
                "payload": payload,
            },
        )


class ClearCommand(_BaseMessage):
    event: Literal["clear"] = "clear"
    stream_sid: str = Field(default="", alias="streamSid")


class MarkCommand(_BaseMessage):
    event: Literal["mark"] = "mark"
    stream_sid: str = Field(default="", alias="streamSid")
    mark: dict[str, str]

    @classmethod
    def create(cls, name: str) -> Self:
        return cls(
            mark={
                "name": name,
            },
        )


type TwilioCommand = MediaCommand | ClearCommand | MarkCommand
