from ..common import BaseConfig


class PipelineSettings(BaseConfig):
    persistent_profile: bool = True
    reactions: bool = True
    room_voice: bool = True
    wakeword: bool = True
