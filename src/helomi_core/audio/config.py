from typing import Literal

from helomi_common import AdapterConfig, AdapterExtractor

from .avfaudio.config import AVFAudioConfig


class AudioSettings(AdapterConfig, AdapterExtractor[AVFAudioConfig]):
    adapter: Literal["avfaudio"] = "avfaudio"
    avfaudio: AVFAudioConfig | None = None
