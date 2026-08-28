from .config import TurnSettings
from .domain import TurnPrediction, TurnStatus
from .ports import TurnAdapter


def get_turn_adapter(settings: TurnSettings) -> TurnAdapter:
    from .smart_turn.config import SmartTurnConfig

    match cfg := settings.extract_adapter():
        case SmartTurnConfig():
            from .smart_turn.adapter import SmartTurnAdapter

            return SmartTurnAdapter(cfg)


__all__ = [
    "TurnAdapter",
    "TurnPrediction",
    "TurnSettings",
    "TurnStatus",
    "get_turn_adapter",
]
