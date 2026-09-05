import asyncio
import threading
from typing import ClassVar

import uvicorn

from ..pipeline import PipelineExtension, PipelineService
from .api import create_api
from .config import ServerSettings
from .session import SessionManager


class ServerExtension(PipelineExtension):
    _CLOSE_TIMEOUT: ClassVar[float] = 5.0

    def __init__(
        self,
        config: ServerSettings,
        pipeline: PipelineService,
        sessions: SessionManager | None = None,
    ) -> None:
        super().__init__(pipeline)

        if sessions is None:
            sessions = SessionManager()

        self._config = config
        self._sessions = sessions
        self._server = uvicorn.Server(
            config=uvicorn.Config(
                app=create_api(
                    pipeline=self,
                    sessions=sessions,
                ),
                host=config.host,
                port=config.port,
                log_level="warning",
                access_log=False,
                lifespan="on",
            )
        )
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self._config.host}:{self._config.port}"

    def __str__(self) -> str:
        return f"{self.__component__}(url={self.url})"

    async def _do_open(self) -> None:
        thread = threading.Thread(
            target=self._serve,
            name=self.__label__,
            daemon=True,
        )

        self._thread = thread
        self._server.should_exit = False
        thread.start()

        self._tasks.add_task(self._event_loop())

    async def _post_close(self) -> None:
        self._thread, self._loop, thread = None, None, self._thread

        if thread is None:
            return

        self._server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=self._CLOSE_TIMEOUT)

    def _serve(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._server_loop())
        finally:
            loop.close()

    async def _server_loop(self) -> None:
        cfg = self._server.config

        if not cfg.loaded:
            cfg.load()

        self._server.lifespan = cfg.lifespan_class(cfg)

        await self._server.startup()

        if not self._server.should_exit:
            await self._server.main_loop()

        await self._server.shutdown()

    async def _event_loop(self) -> None:
        async for event in self._subscribe_event():
            self._sessions.dispatch_event(event)
