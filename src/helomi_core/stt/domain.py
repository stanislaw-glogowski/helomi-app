from dataclasses import dataclass
from typing import Self

from ..audio import AudioChunk


@dataclass(frozen=True, slots=True)
class STTRequest:
    audio: AudioChunk


@dataclass(frozen=True, slots=True)
class STTChunk:
    text: str


@dataclass(frozen=True, slots=True)
class STTResponse(STTChunk):
    @classmethod
    def from_chunks(cls, chunks: list[STTChunk]) -> Self | None:
        if not chunks:
            return None

        return cls(
            text=" ".join(chunk.text for chunk in chunks),
        )
