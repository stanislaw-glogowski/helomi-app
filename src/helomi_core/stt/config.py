from typing import Literal

from helomi_common import AdapterConfig, AdapterExtractor

from .parakeet.config import ParakeetConfig, ParakeetOptions
from .whisper.config import WhisperConfig, WhisperOptions


class _BaseConfig(AdapterConfig):
    adapter: Literal["parakeet", "whisper"] = "parakeet"


class STTSettings(_BaseConfig, AdapterExtractor[ParakeetConfig | WhisperConfig]):
    parakeet: ParakeetConfig | None = None
    whisper: WhisperConfig | None = None


class STTProfile(_BaseConfig, AdapterExtractor[ParakeetOptions | WhisperOptions]):
    parakeet: ParakeetOptions | None = None
    whisper: WhisperOptions | None = None
