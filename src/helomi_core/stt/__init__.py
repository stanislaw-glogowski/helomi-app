from typing import TYPE_CHECKING

from .domain import STTChunk, STTRequest, STTResponse
from .ports import STTAdapter
from .worker import STTWorker

if TYPE_CHECKING:
    from .config import STTSettings


def get_stt_adapter(settings: STTSettings) -> STTAdapter:
    from .parakeet.config import ParakeetConfig
    from .whisper.config import WhisperConfig

    match cfg := settings.extract_adapter():
        case ParakeetConfig():
            from .parakeet.adapter import ParakeetAdapter

            return ParakeetAdapter(cfg)

        case WhisperConfig():
            from .whisper.adapter import WhisperAdapter

            return WhisperAdapter(cfg)


__all__ = [
    "STTAdapter",
    "STTChunk",
    "STTRequest",
    "STTResponse",
    "STTWorker",
    "get_stt_adapter",
]
