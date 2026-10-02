from enum import StrEnum, auto

from pydantic import Field

from helomi_foundation import ConfigModel


class ResponseMode(StrEnum):
    API = auto()
    PARROT = auto()
    OPERATOR = auto()


class ConversationSettings(ConfigModel):
    persistent_profile: bool = True
    wakeword: bool = True
    reactions: bool = True
    room_voice: bool = True
    playback_ack_timeout: float = Field(default=5.0, gt=0)


class ServerSettings(ConfigModel):
    host: str = "127.0.0.1"
    port: int = Field(default=4356, ge=1, le=65535)


class ApplicationSettings(ConfigModel):
    conversation: ConversationSettings = Field(default_factory=ConversationSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    response_mode: ResponseMode = ResponseMode.API
