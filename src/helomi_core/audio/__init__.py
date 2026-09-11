from typing import TYPE_CHECKING

from .domain import (
    AudioChunk,
    AudioFile,
    AudioFormat,
    AudioMode,
    RawAudio,
)
from .ports import AudioDriver
from .resampler import AudioResampler

if TYPE_CHECKING:
    from .config import AudioSettings


def get_audio_driver(
    settings: AudioSettings,
    mode: AudioMode | None = None,
) -> AudioDriver:
    from .avfaudio.config import AVFAudioConfig

    match cfg := settings.extract_adapter():
        case AVFAudioConfig():
            from .avfaudio.driver import AVFAudioDriver

            return AVFAudioDriver(cfg, mode)


__all__ = [
    "AudioChunk",
    "AudioDriver",
    "AudioFile",
    "AudioFormat",
    "AudioMode",
    "AudioResampler",
    "RawAudio",
    "get_audio_driver",
]
