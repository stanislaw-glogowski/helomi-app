from typing import Literal

from helomi_common import AdapterConfig, AdapterExtractor

from .supertonic.config import SupertonicConfig, SupertonicOptions
from .voxcpm2.config import VoxCPM2Config, VoxCPM2Options


class _BaseConfig(AdapterConfig):
    adapter: Literal["supertonic", "voxcpm2"] = "voxcpm2"


class TTSSettings(_BaseConfig, AdapterExtractor[SupertonicConfig | VoxCPM2Config]):
    supertonic: SupertonicConfig | None = None
    voxcpm2: VoxCPM2Config | None = None


class TTSProfile(_BaseConfig, AdapterExtractor[SupertonicOptions | VoxCPM2Options]):
    supertonic: SupertonicOptions | None = None
    voxcpm2: VoxCPM2Options | None = None
