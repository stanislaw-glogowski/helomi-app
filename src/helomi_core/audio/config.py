from typing import Literal

from pydantic import FilePath

from helomi_common import AdapterConfig, AdapterExtractor, BaseConfig

from .avfaudio.config import AVFAudioConfig


class AudioSettings(AdapterConfig, AdapterExtractor[AVFAudioConfig]):
    adapter: Literal["avfaudio"] = "avfaudio"
    avfaudio: AVFAudioConfig | None = None


class AudioProfile(BaseConfig):
    room_voice_path: FilePath | None = None
