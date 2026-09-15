from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from .extension import PipelineExtension
else:
    PipelineExtension = object

type PipelineExtensionType = type[PipelineExtension]
type PipelineExtensionLike = PipelineExtensionType | PipelineExtension


class PipelineOptions(BaseModel):
    persistent_profile_enabled: bool
    persistent_profile_supported: bool
    reactions_enabled: bool
    reactions_supported: bool
    room_voice_enabled: bool
    room_voice_supported: bool
    wakeword_enabled: bool
    wakeword_supported: bool

    def is_enabled(
        self,
        key: Literal[
            "persistent_profile",
            "reactions",
            "room_voice",
            "wakeword",
        ],
    ) -> bool:
        return getattr(self, f"{key}_enabled", False) and getattr(
            self, f"{key}_supported", False
        )
