from .config import STTProfile, STTSettings
from .domain import STTChunk, STTRequest, STTResponse
from .ports import STTAdapter
from .worker import STTWorker


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
    "STTProfile",
    "STTRequest",
    "STTResponse",
    "STTSettings",
    "STTWorker",
    "get_stt_adapter",
]
