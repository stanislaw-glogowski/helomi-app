from typing import Literal

from helomi_common import AdapterConfig, AdapterExtractor

from .smart_turn.config import SmartTurnConfig


class TurnSettings(AdapterConfig, AdapterExtractor[SmartTurnConfig]):
    adapter: Literal["smart_turn"] = "smart_turn"
    smart_turn: SmartTurnConfig | None = None
