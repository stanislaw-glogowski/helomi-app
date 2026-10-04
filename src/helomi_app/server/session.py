import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

from helomi_foundation import ManagedComponent, on_unmount

from ..messages import ApplicationEvent


class Session:
    def __init__(self, profile_id: str):
        self.id = uuid4().hex
        self.profile_id = profile_id
        self._events: asyncio.Queue[ApplicationEvent | None] = asyncio.Queue()

    def dispatch(self, event: ApplicationEvent) -> None:
        self._events.put_nowait(event)

    def close(self) -> None:
        self._events.put_nowait(None)

    async def subscribe(
        self,
        heartbeat_interval_seconds: float | None = None,
    ) -> AsyncIterator[ApplicationEvent | None]:
        while True:
            try:
                if heartbeat_interval_seconds is None:
                    event = await self._events.get()
                else:
                    async with asyncio.timeout(heartbeat_interval_seconds):
                        event = await self._events.get()
            except TimeoutError:
                yield None
                continue
            try:
                if event is None:
                    return
                yield event
            finally:
                self._events.task_done()


class SessionManager(ManagedComponent):
    """Enforce one API event-stream owner for each profile."""

    def __init__(self):
        super().__init__()
        self._sessions: dict[str, Session] = {}
        self._profile_sessions: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, profile_id: str) -> Session | None:
        async with self._lock:
            if profile_id in self._profile_sessions:
                return None
            session = Session(profile_id)
            self._sessions[session.id] = session
            self._profile_sessions[profile_id] = session.id
            return session

    async def release(self, session: Session) -> None:
        async with self._lock:
            removed = self._sessions.pop(session.id, None)
            if removed is None:
                return
            self._profile_sessions.pop(removed.profile_id, None)
            removed.close()

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def dispatch(self, event: ApplicationEvent) -> None:
        profile_id = getattr(event, "profile_id", None)
        if not isinstance(profile_id, str):
            return
        session_id = self._profile_sessions.get(profile_id)
        if session_id is not None and (session := self._sessions.get(session_id)):
            session.dispatch(event)

    @on_unmount()
    async def _close_sessions(self):
        async with self._lock:
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
            self._profile_sessions.clear()
