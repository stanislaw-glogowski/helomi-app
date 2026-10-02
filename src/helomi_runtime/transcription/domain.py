from dataclasses import dataclass
from typing import Self

from ..audio import AudioChunk


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    audio: AudioChunk
    profile_id: str


@dataclass(frozen=True, slots=True)
class TranscriptionChunk:
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptionResponse(TranscriptionChunk):
    @classmethod
    def from_chunks(cls, chunks: list[TranscriptionChunk]) -> Self | None:
        if not chunks:
            return None

        return cls(
            text=" ".join(chunk.text for chunk in chunks),
        )
