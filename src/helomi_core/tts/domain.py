from dataclasses import dataclass

from ..audio import RawAudio


@dataclass(frozen=True, slots=True)
class TTSRequest:
    text: str


@dataclass(frozen=True, slots=True)
class TTSChunk:
    audio: RawAudio
