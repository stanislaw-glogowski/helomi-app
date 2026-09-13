from typing import Literal

from ..common import AdapterConfig, AdapterExtractor
from .smart_turn.config import SmartTurnSettings


class TurnSettings(AdapterConfig, AdapterExtractor[SmartTurnSettings]):
    adapter: Literal["smart_turn"] = "smart_turn"
    smart_turn: SmartTurnSettings | None = None
