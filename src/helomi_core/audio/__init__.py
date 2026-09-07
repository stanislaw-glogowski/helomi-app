from .config import AudioProfile, AudioSettings
from .domain import (
    AudioChunk,
    AudioFile,
    AudioFormat,
    AudioMode,
    RawAudio,
)
from .ports import AudioDriver
from .resampler import AudioResampler


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
    "AudioProfile",
    "AudioResampler",
    "AudioSettings",
    "RawAudio",
    "get_audio_driver",
]
