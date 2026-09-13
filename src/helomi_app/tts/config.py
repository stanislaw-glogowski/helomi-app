from typing import Literal

from ..common import AdapterConfig, AdapterExtractor
from .supertonic.config import SupertonicProfile, SupertonicSettings
from .voxcpm2.config import VoxCPM2Profile, VoxCPM2Settings


class _BaseConfig(AdapterConfig):
    adapter: Literal["supertonic", "voxcpm2"] = "voxcpm2"


class TTSSettings(_BaseConfig, AdapterExtractor[SupertonicSettings | VoxCPM2Settings]):
    supertonic: SupertonicSettings | None = None
    voxcpm2: VoxCPM2Settings | None = None


class TTSProfile(_BaseConfig, AdapterExtractor[SupertonicProfile | VoxCPM2Profile]):
    supertonic: SupertonicProfile | None = None
    voxcpm2: VoxCPM2Profile | None = None
