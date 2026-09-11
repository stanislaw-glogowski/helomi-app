from typing import TYPE_CHECKING, Any

from .domain import WakeWordPrediction
from .ports import WakeWordAdapter

if TYPE_CHECKING:
    from .config import WakeWordProfile, WakeWordSettings


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
        case _:
            raise ValueError(f"Unsupported wakeword adapter config: {cfg}")


__all__ = [
    "WakeWordAdapter",
    "WakeWordPrediction",
    "get_wakeword_adapter",
]
