from typing import TYPE_CHECKING

from .domain import TurnPrediction, TurnStatus
from .ports import TurnAdapter

if TYPE_CHECKING:
    from .config import TurnSettings


def get_turn_adapter(settings: TurnSettings) -> TurnAdapter:
    from .smart_turn.config import SmartTurnConfig

    match cfg := settings.extract_adapter():
        case SmartTurnConfig():
            from .smart_turn.adapter import SmartTurnAdapter

            return SmartTurnAdapter(cfg)


__all__ = [
    "TurnAdapter",
    "TurnPrediction",
    "TurnStatus",
    "get_turn_adapter",
]
