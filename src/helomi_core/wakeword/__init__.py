from typing import Any

from .config import WakeWordProfile, WakeWordSettings
from .domain import WakeWordPrediction
from .ports import WakeWordAdapter


def get_wakeword_adapter(
    settings: WakeWordSettings | None = None,
    profiles: dict[str, WakeWordProfile] | None = None,
) -> WakeWordAdapter | None:
    if not settings or not profiles:
        return None

    from .openwakeword.config import OpenWakeWordConfig

    words: dict[str, Any] = {
        profile_id: word
        for profile_id, profile in profiles.items()
        if (word := profile.extract_adapter(False)) is not None
    }

    match cfg := settings.extract_adapter():
        case OpenWakeWordConfig():
            from .openwakeword.adapter import OpenWakeWordAdapter

            return OpenWakeWordAdapter(cfg, words)


__all__ = [
    "WakeWordAdapter",
    "WakeWordPrediction",
    "WakeWordProfile",
    "WakeWordSettings",
    "get_wakeword_adapter",
]
