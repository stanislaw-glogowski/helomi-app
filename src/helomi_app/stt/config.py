from typing import Literal

from ..common import AdapterConfig, AdapterExtractor
from .parakeet.config import ParakeetProfile, ParakeetSettings
from .whisper.config import WhisperProfile, WhisperSettings


class _BaseConfig(AdapterConfig):
    adapter: Literal["parakeet", "whisper"] = "parakeet"


class STTSettings(_BaseConfig, AdapterExtractor[ParakeetSettings | WhisperSettings]):
    parakeet: ParakeetSettings | None = None
    whisper: WhisperSettings | None = None


class STTProfile(_BaseConfig, AdapterExtractor[ParakeetProfile | WhisperProfile]):
    parakeet: ParakeetProfile | None = None
    whisper: WhisperProfile | None = None
