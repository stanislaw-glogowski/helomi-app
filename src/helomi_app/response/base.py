from abc import ABC

from helomi_foundation import ManagedComponent

from ..config import ResponseMode


class ResponseModule(ManagedComponent, ABC):
    mode: ResponseMode

    async def respond(self, text: str, profile_id: str) -> str | None:
        return None


class APIResponseModule(ResponseModule):
    mode = ResponseMode.API


class ParrotResponseModule(ResponseModule):
    mode = ResponseMode.PARROT

    async def respond(self, text: str, profile_id: str) -> str | None:
        return text


class OperatorResponseModule(ResponseModule):
    mode = ResponseMode.OPERATOR
