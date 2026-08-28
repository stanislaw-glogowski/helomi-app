from .config import AudioSettings
from .domain import AudioChunk, AudioFormat, AudioMode, RawAudio
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
    "AudioFormat",
    "AudioMode",
    "AudioResampler",
    "AudioSettings",
    "RawAudio",
    "get_audio_driver",
]
