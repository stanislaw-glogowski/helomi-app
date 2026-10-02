from typing import Literal

from pydantic import Field

from helomi_foundation import ConfigModel

from ..selection import SelectedAdapterSettings
from .openwakeword.config import OpenWakeWordConfig, OpenWakeWordProfile
from .silero_vad.config import SileroVADConfig
from .smart_turn.config import SmartTurnConfig


class TurnSettings(SelectedAdapterSettings):
    _ADAPTERS = ("smart_turn",)
    adapter: Literal["smart_turn"]
    smart_turn: SmartTurnConfig | None = None


class VADOptions(ConfigModel):
    threshold: float = Field(default=0.5, ge=0, le=1)


class VADSettings(SelectedAdapterSettings):
    _ADAPTERS = ("silero_vad",)
    adapter: Literal["silero_vad"]
    options: VADOptions = Field(default_factory=VADOptions)
    silero_vad: SileroVADConfig | None = None


class WakeWordSettings(SelectedAdapterSettings):
    _ADAPTERS = ("openwakeword",)
    adapter: Literal["openwakeword"]
    openwakeword: OpenWakeWordConfig | None = None


class WakeWordProfiles(ConfigModel):
    openwakeword: OpenWakeWordProfile | None = None


class DetectionSettings(ConfigModel):
    turn: TurnSettings
    vad: VADSettings
    wakeword: WakeWordSettings | None = None
