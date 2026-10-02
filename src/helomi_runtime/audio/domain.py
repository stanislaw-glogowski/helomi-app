import wave
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Self

import numpy as np
from numpy.typing import NDArray

from helomi_foundation import PathFile

from .codec import (
    float32_to_int16,
    float32_to_mulaw,
    int16_to_float32,
    mulaw_to_float32,
)

if TYPE_CHECKING:
    import mlx.core

    type MLXArray = mlx.core.array
else:
    type MLXArray = Any


class AudioDriverKind(StrEnum):
    LOCAL = auto()
    GSM = auto()


class AudioDriverState(StrEnum):
    STOPPED = auto()
    READY = auto()
    CONNECTED = auto()


@dataclass(frozen=True, slots=True)
class AudioDriverCapabilities:
    capture: bool
    playback: bool
    interrupt: bool
    room_voice: bool
    remote_session: bool
    local_monitoring: bool
    manual_profile_selection: bool


@dataclass(frozen=True, slots=True)
class AudioDriverDescriptor:
    id: str
    name: str
    kind: AudioDriverKind
    capabilities: AudioDriverCapabilities


@dataclass(frozen=True, slots=True)
class AudioFormat:
    MONO_8: ClassVar[AudioFormat]
    MONO_16: ClassVar[AudioFormat]
    MONO_44: ClassVar[AudioFormat]
    MONO_48: ClassVar[AudioFormat]

    _BLOCK_DURATION: ClassVar[float] = 0.032

    sample_rate: int
    channels: int = 1

    def __post_init__(self):
        if self.sample_rate <= 0:
            raise ValueError(
                f"Sample rate must be greater than 0, got {self.sample_rate}"
            )
        if self.channels != 1:
            raise ValueError(
                f"Only mono audio is supported, got {self.channels} channels"
            )

    @property
    def block_size(self) -> int:
        return round(self.sample_rate * self._BLOCK_DURATION)


AudioFormat.MONO_8 = AudioFormat(sample_rate=8_000, channels=1)
AudioFormat.MONO_16 = AudioFormat(sample_rate=16_000, channels=1)
AudioFormat.MONO_44 = AudioFormat(sample_rate=44_100, channels=1)
AudioFormat.MONO_48 = AudioFormat(sample_rate=48_000, channels=1)


@dataclass(frozen=True, slots=True)
class RawAudio:
    format: AudioFormat
    data: bytes

    @property
    def duration_seconds(self) -> float:
        return len(self.data) / (4 * self.format.sample_rate * self.format.channels)

    def __add__(self, other: RawAudio) -> RawAudio:
        return RawAudio.concat([self, other])

    @classmethod
    def from_int16(cls, data: bytes, format: AudioFormat) -> Self:
        return cls(
            format=format,
            data=int16_to_float32(data),
        )

    def to_int16(self) -> bytes:
        return float32_to_int16(self.data)

    @classmethod
    def from_mulaw(cls, data: bytes, format: AudioFormat) -> Self:
        return cls(
            format=format,
            data=mulaw_to_float32(data),
        )

    def to_mulaw(self) -> bytes:
        return float32_to_mulaw(self.data)

    @classmethod
    def concat(cls, chunks: list[Self]) -> Self:
        if not chunks:
            raise ValueError("Empty sequence of chunks")

        if len(chunks) == 1:
            return chunks[0]

        return cls(
            format=chunks[0].format,
            data=b"".join(chunk.data for chunk in chunks),
        )


@dataclass(frozen=True, slots=True)
class AudioChunk:
    format: AudioFormat
    samples: NDArray

    def __add__(self, other: AudioChunk) -> AudioChunk:
        return AudioChunk.concat([self, other])

    @classmethod
    def from_raw(cls, raw: RawAudio) -> Self:
        return cls(
            format=raw.format,
            samples=np.frombuffer(raw.data, dtype=np.float32),
        )

    @classmethod
    def from_mulaw(cls, data: bytes, format: AudioFormat) -> Self:
        return cls.from_raw(RawAudio.from_mulaw(data, format))

    def to_mulaw(self) -> bytes:
        return float32_to_mulaw(self.samples)

    @classmethod
    def from_int16(cls, data: bytes, format: AudioFormat) -> Self:
        return cls.from_raw(RawAudio.from_int16(data, format))

    def to_int16(self) -> bytes:
        return float32_to_int16(self.samples)

    def to_raw(self) -> RawAudio:
        return RawAudio(
            format=self.format,
            data=self.samples.tobytes(),
        )

    def to_bytes(self) -> bytes:
        return self.samples.tobytes()

    def to_mlx(self) -> MLXArray:
        import mlx.core as mx

        return mx.array(self.samples.tolist())

    @classmethod
    def concat(cls, chunks: Sequence[Self]) -> Self:
        if not chunks:
            raise ValueError("Empty sequence of chunks")

        if len(chunks) == 1:
            return chunks[0]

        return cls(
            format=chunks[0].format,
            samples=np.concatenate([c.samples for c in chunks], axis=0),
        )


class AudioFile(PathFile):
    _SUFFIXES: ClassVar[tuple[str, ...]] = (".wav", ".wave")
    _SAMPLE_WIDTH: ClassVar[int] = 2

    def read(self) -> RawAudio:
        with wave.open(str(self.path), "rb") as f:
            data = f.readframes(f.getnframes())
            format = AudioFormat(
                sample_rate=f.getframerate(),
                channels=f.getnchannels(),
            )
            return RawAudio.from_int16(data, format)

    def write(self, audio: RawAudio | AudioChunk):
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with wave.open(str(self.path), "wb") as f:
            f.setnchannels(audio.format.channels)
            f.setframerate(audio.format.sample_rate)
            f.setsampwidth(self._SAMPLE_WIDTH)
            f.writeframes(audio.to_int16())
