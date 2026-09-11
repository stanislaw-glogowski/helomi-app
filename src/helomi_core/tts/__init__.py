from typing import TYPE_CHECKING

from .domain import TTSChunk, TTSRequest
from .ports import TTSAdapter
from .tags import TTS_TAGS
from .worker import TTSWorker

if TYPE_CHECKING:
    from .config import TTSSettings


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
    "TTSRequest",
    "TTSWorker",
    "get_tts_adapter",
]
