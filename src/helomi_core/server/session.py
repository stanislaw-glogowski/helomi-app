import asyncio
import uuid
from dataclasses import dataclass, field

from ..speech import SpeechEvent


class ProfileLockedError(Exception):
    """Raised when an attempt is made to acquire a profile that is already locked."""


@dataclass(slots=True)
class Session:
    id: str
    profile_id: str
    queue: asyncio.Queue[SpeechEvent | None] = field(default_factory=asyncio.Queue)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._profile_to_session: dict[str, str] = {}
        self._lock = asyncio.Lock()

    @property
    def active_sessions_count(self) -> int:
        return len(self._sessions)

    async def acquire(self, profile_id: str) -> Session:
        async with self._lock:
            if existing_session_id := self._profile_to_session.get(profile_id):
                msg = (
                    f"Profile '{profile_id}' is already locked "
                    f"by session '{existing_session_id}'"
                )
                raise ProfileLockedError(msg)

            session_id = str(uuid.uuid4())
            session = Session(id=session_id, profile_id=profile_id)
            self._sessions[session_id] = session
            self._profile_to_session[profile_id] = session_id
            return session

    async def release(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                self._profile_to_session.pop(session.profile_id, None)
                session.queue.put_nowait(None)

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def dispatch_event(self, event: SpeechEvent) -> None:
        session_id = self._profile_to_session.get(event.profile_id)
        if session_id and (session := self._sessions.get(session_id)):
            session.queue.put_nowait(event)

    async def close_all(self) -> None:
        async with self._lock:
            for session in self._sessions.values():
                session.queue.put_nowait(None)
            self._sessions.clear()
            self._profile_to_session.clear()
