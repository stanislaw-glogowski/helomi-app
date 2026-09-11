from typing import TYPE_CHECKING

from .domain import VADPrediction
from .ports import VADAdapter

if TYPE_CHECKING:
    from .config import VADSettings


def get_vad_adapter(settings: VADSettings) -> VADAdapter:
    from .silero_vad.config import SileroVADMLXConfig, SileroVADONNXConfig

    match cfg := settings.extract_adapter():
        case SileroVADMLXConfig():
            from .silero_vad.mlx_adapter import SileroVADMLXAdapter

            return SileroVADMLXAdapter(cfg)
        case SileroVADONNXConfig():
            from .silero_vad.onnx_adapter import SileroVADONNXAdapter

            return SileroVADONNXAdapter(cfg)


__all__ = [
    "VADAdapter",
    "VADPrediction",
    "get_vad_adapter",
]
