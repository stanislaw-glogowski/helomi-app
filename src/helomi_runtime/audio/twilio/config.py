from pydantic import Field, HttpUrl

from helomi_foundation import ConfigModel

from ..room_voice import RoomVoiceProfile


class TwilioSettings(ConfigModel):
    auth_token: str
    public_url: HttpUrl
    port: int = 4357
    allowed_callers: list[str] | None = None
    handshake_timeout: float = Field(default=10.0, gt=0)
    session_ttl: float = Field(default=30.0, gt=0)
    validate_signature: bool = True
    output_buffer_chunks: int = Field(default=50, ge=1)


class TwilioProfile(ConfigModel):
    callees: list[str] = Field(min_length=1)
    room_voice: RoomVoiceProfile | None = None
