from typing import Literal

from helomi_foundation import ConfigModel

from ..selection import SelectedAdapterSettings
from .piper.config import PiperProfile, PiperSettings
from .supertonic.config import SupertonicProfile, SupertonicSettings
from .voxcpm2.config import VoxCPM2Profile, VoxCPM2Settings


class SynthesisSettings(SelectedAdapterSettings):
    _ADAPTERS = ("supertonic", "voxcpm2", "piper")
    adapter: Literal["supertonic", "voxcpm2", "piper"]
    supertonic: SupertonicSettings | None = None
    voxcpm2: VoxCPM2Settings | None = None
    piper: PiperSettings | None = None


class SynthesisProfile(ConfigModel):
    supertonic: SupertonicProfile | None = None
    voxcpm2: VoxCPM2Profile | None = None
    piper: PiperProfile | None = None
