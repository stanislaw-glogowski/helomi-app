import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Final

from helomi_common import AbstractAsyncComponent

from ..pipeline import PipelineEvent


class Session:
    def __init__(
        self,
        profile_id: str,
    ) -> None:
        self.id: Final[str] = str(uuid.uuid4())
        self.profile_id: Final[str] = profile_id

        self._events: asyncio.Queue[PipelineEvent | None] = asyncio.Queue()

    def dispatch(self, event: PipelineEvent) -> None:
        self._events.put_nowait(event)

    def close(self) -> None:
        self._events.put_nowait(None)

    async def subscribe(self) -> AsyncIterator[PipelineEvent]:
        while True:
            try:
                event = await self._events.get()
                if event is None:
                    return
                yield event
            finally:
                self._events.task_done()


class SessionManager(AbstractAsyncComponent):
    def __init__(self) -> None:
        super().__init__(is_quiet=True)
        self._sessions: dict[str, Session] = {}
        self._profile_to_session: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, profile_id: str) -> Session | None:
        async with self._lock:
            if self._profile_to_session.get(profile_id, None):
                return None

            session = Session(
                profile_id=profile_id,
            )

            self._sessions[session.id] = session
            self._profile_to_session[profile_id] = session.id

            return session

    async def release(self, session: Session) -> None:
        async with self._lock:
            popped = self._sessions.pop(session.id, None)
            if popped is None:
                return
            self._profile_to_session.pop(popped.profile_id, None)
            popped.close()

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def dispatch(self, event: PipelineEvent) -> None:
        session_id = self._profile_to_session.get(event.profile_id)
        if session_id and (session := self._sessions.get(session_id)):
            session.dispatch(event)

    async def _do_close(self) -> None:
        async with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
            self._profile_to_session.clear()
