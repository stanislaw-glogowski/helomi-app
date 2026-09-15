from pydantic import HttpUrl

from ....common import BaseConfig


class TwilioSettings(BaseConfig):
    auth_token: str
    public_url: HttpUrl
    port: int = 4357
    allowed_callers: list[str] | None = None
    handshake_timeout: int = 30
    disable_signature_validation: bool = True


class TwilioProfile(BaseConfig):
    callee: str
