import re
from dataclasses import dataclass

from ..audio import RawAudio


@dataclass(frozen=True, slots=True)
class TTSRequest:
    text: str

    @property
    def raw_text(self) -> str:
        return re.sub(r"\s*\[[a-zA-Z-]+]\s*", " ", self.text).strip()


@dataclass(frozen=True, slots=True)
class TTSChunk:
    audio: RawAudio
