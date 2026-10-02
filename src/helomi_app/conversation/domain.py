from dataclasses import dataclass
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from ..config import ConversationSettings


class ConversationOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    persistent_profile: bool
    reactions: bool
    room_voice: bool
    wakeword: bool

    @classmethod
    def from_settings(cls, settings: ConversationSettings):
        return cls(
            persistent_profile=settings.persistent_profile,
            reactions=settings.reactions,
            room_voice=settings.room_voice,
            wakeword=settings.wakeword,
        )


@dataclass(frozen=True, slots=True)
class TurnToken:
    session_id: str
    turn_id: int


class ConversationIdentity:
    def __init__(self):
        self._session_id: str | None = None
        self._turn_id = 0

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def turn_id(self) -> int:
        return self._turn_id

    def start_session(self) -> TurnToken:
        self._session_id = uuid4().hex
        self._turn_id = 0
        return self.current()

    def next_turn(self) -> TurnToken:
        if self._session_id is None:
            raise RuntimeError("Conversation session is not active")
        self._turn_id += 1
        return self.current()

    def current(self) -> TurnToken:
        if self._session_id is None:
            raise RuntimeError("Conversation session is not active")
        return TurnToken(self._session_id, self._turn_id)

    def is_current(self, token: TurnToken) -> bool:
        return token == TurnToken(self._session_id or "", self._turn_id)

    def clear(self) -> None:
        self._session_id = None
        self._turn_id = 0
