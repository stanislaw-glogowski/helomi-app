from typing import Any, Literal

from pydantic import model_validator

from ...common import AdapterConfig, AdapterExtractor
from .piper.config import PiperProfile, PiperSettings
from .supertonic.config import SupertonicProfile, SupertonicSettings
from .voxcpm2.config import VoxCPM2Profile, VoxCPM2Settings


class _BaseConfig(AdapterConfig):
    adapter: Literal["supertonic", "voxcpm2", "piper"] = "voxcpm2"


class TTSSettings(
    _BaseConfig, AdapterExtractor[SupertonicSettings | VoxCPM2Settings | PiperSettings]
):
    supertonic: SupertonicSettings | None = None
    voxcpm2: VoxCPM2Settings | None = None
    piper: PiperSettings | None = None


class TTSProfile(
    _BaseConfig, AdapterExtractor[SupertonicProfile | VoxCPM2Profile | PiperProfile]
):
    supertonic: SupertonicProfile | None = None
    voxcpm2: VoxCPM2Profile | None = None
    piper: PiperProfile | None = None

    @model_validator(mode="before")
    @classmethod
    def filter_piper(cls, data: Any) -> Any:
        if isinstance(data, dict):
            piper = data.get("piper", None)
            if isinstance(piper, dict) and (
                not piper.get("model_path", None) or not piper.get("config_path", None)
            ):
                data.pop("piper")

        return data
