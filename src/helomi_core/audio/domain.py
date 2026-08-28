from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Self

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    import mlx.core

    type MLXArray = mlx.core.array
else:
    type MLXArray = Any


class AudioMode(StrEnum):
    INPUT = auto()
    OUTPUT = auto()
    DUPLEX = auto()

    @property
    def has_input(self) -> bool:
        return self in {self.INPUT, self.DUPLEX}

    @property
    def has_output(self) -> bool:
        return self in {self.OUTPUT, self.DUPLEX}

    def supports(self, required: AudioMode) -> bool:
        match required:
            case AudioMode.INPUT:
                return self.has_input
            case AudioMode.OUTPUT:
                return self.has_output
            case AudioMode.DUPLEX:
                return self is AudioMode.DUPLEX

    def verify(self, expected: AudioMode) -> None:
        if not self.supports(expected):
            raise RuntimeError(f"Expected audio mode: {expected}, got {self}")


@dataclass(frozen=True, slots=True)
class AudioFormat:
    MONO_16: ClassVar[AudioFormat]
    MONO_44: ClassVar[AudioFormat]
    MONO_48: ClassVar[AudioFormat]

    _BLOCK_DURATION: ClassVar[float] = 0.032

    sample_rate: int
    channels: int = 1

    def __post_init__(self) -> None:
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


AudioFormat.MONO_16 = AudioFormat(sample_rate=16_000, channels=1)
AudioFormat.MONO_44 = AudioFormat(sample_rate=44_100, channels=1)
AudioFormat.MONO_48 = AudioFormat(sample_rate=48_000, channels=1)


@dataclass(frozen=True, slots=True)
class RawAudio:
    format: AudioFormat
    data: bytes

    def __add__(self, other: RawAudio) -> RawAudio:
        return RawAudio.concat([self, other])

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

    def to_raw(self) -> RawAudio:
        return RawAudio(
            format=self.format,
            data=self.samples.tobytes(),
        )

    def to_pcm(self, normalize=False) -> tuple[int, bytes]:
        samples = self.samples.astype(np.float32).flatten()
        samples = np.clip(samples, -1.0, 1.0)

        if normalize:
            peak = np.max(np.abs(samples))
            if peak > 0:
                samples = samples / peak

        frame = (samples * 32767).astype(np.int16)
        return 2, frame.tobytes()

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
