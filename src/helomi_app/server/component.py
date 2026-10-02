from typing import TYPE_CHECKING

import uvicorn

from helomi_foundation import ManagedComponent, on_mount, on_run, on_unmount

from ..config import ServerSettings
from .api import create_api
from .session import SessionManager

if TYPE_CHECKING:
    from ..application import Application


class ServerModule(ManagedComponent):
    def __init__(
        self,
        settings: ServerSettings,
        application: Application,
    ):
        super().__init__()
        self._settings = settings
        self._application = application
        self._sessions = SessionManager()
        self._server = uvicorn.Server(
            uvicorn.Config(
                app=create_api(application, self._sessions),
                host=settings.host,
                port=settings.port,
                log_level="warning",
                access_log=False,
                lifespan="on",
            )
        )

    @property
    def url(self) -> str:
        return f"http://{self._settings.host}:{self._settings.port}"

    @property
    def docs_url(self) -> str:
        return f"{self.url}/docs"

    @on_mount()
    async def _mount_sessions(self):
        exit_stack = self._exit_stack
        if exit_stack is None:
            raise RuntimeError("Server exit stack is not ready")
        await exit_stack.enter_async_context(self._sessions)

    @on_run()
    async def _serve(self):
        self._server.should_exit = False
        await self._server.serve()

    @on_run()
    async def _forward_events(self):
        async for event in self._application.subscribe_events():
            self._sessions.dispatch(event)

    @on_unmount()
    def _stop(self):
        self._server.should_exit = True
