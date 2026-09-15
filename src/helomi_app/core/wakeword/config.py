from typing import Any, Literal

from pydantic import model_validator

from ...common import AdapterConfig, AdapterExtractor
from .openwakeword.config import OpenWakeWordProfile, OpenWakeWordSettings


class _BaseConfig(AdapterConfig):
    adapter: Literal["none", "openwakeword"] = "openwakeword"


class WakeWordSettings(_BaseConfig, AdapterExtractor[OpenWakeWordSettings | None]):
    openwakeword: OpenWakeWordSettings | None = None


class WakeWordProfile(_BaseConfig, AdapterExtractor[OpenWakeWordProfile | None]):
    openwakeword: OpenWakeWordProfile | None = None

    @model_validator(mode="before")
    @classmethod
    def filter_openwakeword(cls, data: Any) -> Any:
        if isinstance(data, dict):
            openwakeword = data.get("openwakeword", None)
            if isinstance(openwakeword, dict) and not openwakeword.get(
                "model_path", None
            ):
                data.pop("openwakeword")

        return data
