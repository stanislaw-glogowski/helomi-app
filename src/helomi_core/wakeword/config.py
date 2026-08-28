from typing import Any, Literal

from pydantic import model_validator

from helomi_common import AdapterConfig, AdapterExtractor

from .openwakeword.config import OpenWakeWordConfig, OpenWakeWordOptions


class _BaseConfig(AdapterConfig):
    adapter: Literal["openwakeword", "none"] = "openwakeword"


class WakeWordSettings(_BaseConfig, AdapterExtractor[OpenWakeWordConfig]):
    openwakeword: OpenWakeWordConfig | None = None


class WakeWordProfile(_BaseConfig, AdapterExtractor[OpenWakeWordConfig]):
    openwakeword: OpenWakeWordOptions | None = None

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
