from typing import Literal

from pydantic import Field

from helomi_foundation import ConfigModel

from ..selection import SelectedAdapterSettings
from .parakeet.config import ParakeetProfile, ParakeetSettings
from .whisper.config import WhisperProfile, WhisperSettings


class TranscriptionOptions(ConfigModel):
    language: str = "en"


class TranscriptionSettings(SelectedAdapterSettings):
    _ADAPTERS = ("parakeet", "whisper")
    adapter: Literal["parakeet", "whisper"]
    options: TranscriptionOptions = Field(default_factory=TranscriptionOptions)
    parakeet: ParakeetSettings | None = None
    whisper: WhisperSettings | None = None


class TranscriptionProfile(ConfigModel):
    parakeet: ParakeetProfile | None = None
    whisper: WhisperProfile | None = None
