import asyncio
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum, auto
from typing import Annotated, ClassVar, Protocol, Self, overload

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from ..domain import (
    AudioChunk,
    AudioFormat,
    AudioMode,
    RawAudio,
)

PROTOCOL_VERSION = 4


class StreamReader(Protocol):
    async def readexactly(self, n: int) -> bytes: ...


class StreamWriter(Protocol):
    def write(self, data: bytes | bytearray | memoryview) -> None: ...


class MessageKind(IntEnum):
    PLAY = 1
    STOP_PLAYBACK = 2
    SHUTDOWN = 3
    # 4 RESERVED
    # 5 RESERVED
    # 6 RESERVED
    CHECK_DUPLEX = 7
    START_AUDIO = 8
    STOP_AUDIO = 9
    START_ROOM_VOICE = 10
    STOP_ROOM_VOICE = 11
    SET_PLAYBACK_GAIN = 12
    GET_STATUS = 13

    READY = 128
    CAPTURE = 129
    PLAYBACK_FINISHED = 130
    PLAYBACK_STOPPED = 131
    PLAYBACK_GAIN_CHANGED = 132
    DIAGNOSTIC = 133
    # 134 RESERVED
    DUPLEX_CHECKED = 135
    AUDIO_STARTED = 136
    AUDIO_STOPPED = 137
    ROOM_VOICE_START_RESULT = 138
    ROOM_VOICE_STOP_RESULT = 139
    STATUS = 140
    ERROR = 255


class PlaybackStatus(IntEnum):
    PLAYED = 0
    INTERRUPTED = 1


class AudioStatusMode(StrEnum):
    STOPPED = auto()
    INPUT = auto()
    OUTPUT = auto()
    DUPLEX = auto()


class ErrorCode(StrEnum):
    INVALID_COMMAND = auto()
    INVALID_PAYLOAD = auto()
    INVALID_STATE = auto()
    DEVICE_UNAVAILABLE = auto()
    AUDIO_CONFIGURATION_FAILED = auto()
    AUDIO_CONVERSION_FAILED = auto()
    ROOM_VOICE_FAILED = auto()
    PROTOCOL_FAILURE = auto()


class PackedMessage(ABC):
    @classmethod
    @abstractmethod
    def unpack(cls, payload: bytes) -> Self:
        raise NotImplementedError

    @abstractmethod
    def pack(self) -> bytes:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class WireFrame:
    _HEADER: ClassVar[struct.Struct] = struct.Struct("<BII")
    _NEXT_REQUEST_ID: ClassVar[int] = 0

    kind: MessageKind
    payload: bytes
    request_id: int = field(default_factory=lambda: WireFrame._new_request_id())

    @classmethod
    def pack(cls, kind: MessageKind, msg: PackedMessage | None = None) -> Self:
        return cls(kind, msg.pack() if msg is not None else b"")

    @classmethod
    async def read_from(cls, stream: StreamReader | None) -> Self | None:
        if stream is None:
            return None
        try:
            data = await stream.readexactly(cls._HEADER.size)
        except asyncio.IncompleteReadError:
            return None

        if len(data) < cls._HEADER.size:
            raise RuntimeError(
                "AVFAudio payload header is truncated: "
                f"expected at least {cls._HEADER.size} bytes, got {len(data)}"
            )

        raw_kind, request_id, payload_size = cls._HEADER.unpack(data)
        try:
            kind = MessageKind(raw_kind)
        except ValueError as error:
            raise RuntimeError(
                f"Unknown AVFAudio audio message kind: {raw_kind}"
            ) from error

        payload = await stream.readexactly(payload_size)

        return cls(kind, payload, request_id)

    def write_to(self, stream: StreamWriter | None) -> bool:
        if stream is None:
            return False
        data = (
            self._HEADER.pack(self.kind, self.request_id, len(self.payload))
            + self.payload
        )
        stream.write(data)
        return True

    @overload
    def unpack_int(self, /) -> int: ...

    @overload
    def unpack_int[T: int](self, int_cls: type[T], /) -> T: ...

    def unpack_int[T: int](self, *args: type[T]) -> T | int:
        value = int.from_bytes(self.payload, "little")

        match args:
            case (int_cls,) if int_cls is not None:
                return int_cls(value)
            case _:
                return value

    def unpack_msg[T: PackedMessage](self, packed_cls: type[T]) -> T:
        return packed_cls.unpack(self.payload)

    def upack_bool(self, name: str) -> bool:
        if len(self.payload) != 1 or self.payload[0] not in {0, 1}:
            raise RuntimeError(t"Native audio {name} is invalid: expected one 0/1 byte")
        return bool(self.payload[0])

    @classmethod
    def _new_request_id(cls) -> int:
        request_id = cls._NEXT_REQUEST_ID
        cls._NEXT_REQUEST_ID = (request_id + 1) & 0xFFFFFFFF
        return cls._NEXT_REQUEST_ID


@dataclass(frozen=True, slots=True)
class HandshakePacked(PackedMessage):
    version: int
    version: int

    @classmethod
    def unpack(cls, payload: bytes) -> Self:
        if len(payload) != 2:
            raise RuntimeError(
                "Native audio helper returned an invalid handshake: "
                f"expected 2 bytes, got {len(payload)}"
            )
        return cls(int.from_bytes(payload, "little"))

    def pack(self) -> bytes:
        return self.version.to_bytes(2, "little")

    def verify(self) -> None:
        if self.version != PROTOCOL_VERSION:
            raise RuntimeError(
                "Unsupported avfaudio audio protocol version: "
                f"expected {PROTOCOL_VERSION}, got {self.version}"
            )


@dataclass(frozen=True, slots=True)
class AudioPacked(PackedMessage):
    _HEADER: ClassVar[struct.Struct] = struct.Struct("<IH")

    sample_rate: int
    channels: int
    data: bytes

    @classmethod
    def unpack(cls, payload: bytes) -> Self:
        sample_rate, channels = cls._HEADER.unpack(payload[: cls._HEADER.size])
        return cls(sample_rate, channels, payload[cls._HEADER.size :])

    @classmethod
    def encode(cls, value: AudioChunk | RawAudio) -> Self:
        audio = value if isinstance(value, RawAudio) else value.to_raw()
        return cls(audio.format.sample_rate, audio.format.channels, audio.data)

    def pack(self) -> bytes:
        return self._HEADER.pack(self.sample_rate, self.channels) + self.data

    def decode(self) -> RawAudio:
        return RawAudio(
            format=AudioFormat(self.sample_rate, self.channels),
            data=self.data,
        )


class JSONPacket(BaseModel, PackedMessage):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="allow",
        frozen=True,
        strict=True,
        validate_by_name=True,
    )

    @classmethod
    def unpack(cls, payload: bytes) -> Self:
        try:
            return cls.model_validate_json(payload or "{}")
        except ValidationError as error:
            raise RuntimeError(
                f"Native audio {cls.__name__} payload is invalid: {error}"
            ) from error

    def pack(self) -> bytes:
        return self.model_dump_json(by_alias=True, exclude_none=True).encode()


class ErrorPacket(JSONPacket):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1)]
    fatal: bool


class CheckDuplexPacked(JSONPacket):
    pass


class PlaybackGainChangedPacked(JSONPacket):
    gain: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class AudioStartedPacked(JSONPacket):
    mode: AudioMode
    duplex_interruption_available: bool


class DuplexCheckedPacket(JSONPacket):
    available: bool
    reason: str | None = None


class AudioStatusPacket(JSONPacket):
    audio_mode: AudioStatusMode
    room_voice_configured: bool
    room_voice_active: bool
    playback_gain: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    pending_playback_count: Annotated[int, Field(ge=0)]
    duplex_interruption_available: bool


# requests


class StartRoomVoiceRequest(JSONPacket):
    path: Annotated[str, Field(min_length=1)]


class StartAudioRequest(JSONPacket):
    mode: AudioMode
    voice_processing: bool | None = None
