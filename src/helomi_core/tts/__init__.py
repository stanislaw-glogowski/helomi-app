from .config import TTSProfile, TTSSettings
from .domain import TTSChunk, TTSRequest
from .ports import TTSAdapter
from .tags import TTS_TAGS
from .worker import TTSWorker


def get_tts_adapter(settings: TTSSettings) -> TTSAdapter:
    from .supertonic.config import SupertonicConfig
    from .voxcpm2.config import VoxCPM2Config

    match cfg := settings.extract_adapter():
        case SupertonicConfig():
            from .supertonic.adapter import SupertonicAdapter

            return SupertonicAdapter(cfg)
        case VoxCPM2Config():
            from .voxcpm2.adapter import VoxCPM2Adapter

            return VoxCPM2Adapter(cfg)


__all__ = [
    "TTS_TAGS",
    "TTSAdapter",
    "TTSChunk",
    "TTSProfile",
    "TTSRequest",
    "TTSSettings",
    "TTSWorker",
    "get_tts_adapter",
]
