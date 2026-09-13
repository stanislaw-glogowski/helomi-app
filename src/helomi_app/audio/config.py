from typing import Literal

from pydantic import Field

from ..common import AdapterConfig, AdapterExtractor
from .avfaudio.config import AVFAudioProfile, AVFAudioSettings


class _BaseConfig(AdapterConfig):
    adapter: Literal["avfaudio"] = "avfaudio"


class AudioSettings(_BaseConfig, AdapterExtractor[AVFAudioSettings]):
    avfaudio: AVFAudioSettings = Field(default_factory=AVFAudioSettings)


class AudioProfile(_BaseConfig, AdapterExtractor[AVFAudioProfile]):
    avfaudio: AVFAudioProfile = Field(default_factory=AVFAudioProfile)
