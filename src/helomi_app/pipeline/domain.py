from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .extension import PipelineExtension
else:
    PipelineExtension = object

type PipelineExtensionType = type[PipelineExtension]
type PipelineExtensionLike = PipelineExtensionType | PipelineExtension


class PipelineOptions(BaseModel):
    greeting_enabled: bool = True
    room_voice_enabled: bool = True
    wakeword_enabled: bool = False
