import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI

from helomi_common import AbstractAsyncComponent, TaskManager

from ..speech import SpeechCmd, SpeechEvent, SpeechPipeline
from .app import ServerContext, create_app
from .config import ServerSettings
from .session import SessionManager

if TYPE_CHECKING:
    from ..config import Profile
    from ..runtime import Runtime

type EventListener = Callable[[SpeechEvent], None | Awaitable[None]]


class UvicornServerThread:
    def __init__(
        self,
        app: FastAPI,
        config: ServerSettings | None = None,
    ) -> None:
        self._server_settings = config or ServerSettings()
        self._config = uvicorn.Config(
            app=app,
            host=self._server_settings.host,
            port=self._server_settings.port,
            log_level="warning",
            access_log=False,
            lifespan="on",
        )
        self._server = uvicorn.Server(config=self._config)
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()

    @property
    def config(self) -> ServerSettings:
        return self._server_settings

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="helomi-uvicorn",
        )
        self._thread.start()
        self._started.wait(timeout=10.0)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        config = self._config
        if not config.loaded:
            config.load()
        self._server.lifespan = config.lifespan_class(config)
        await self._server.startup()
        self._started.set()
        if not self._server.should_exit:
            await self._server.main_loop()
        await self._server.shutdown()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)


class Server(AbstractAsyncComponent):
    def __init__(
        self,
        runtime: Runtime,
        config: ServerSettings | None = None,
        auto_server: bool = True,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._config = config or runtime.settings.server
        self._auto_server = auto_server
        self._session_manager = SessionManager()
        self._pipeline = runtime.get_speech_pipeline()
        self._tasks = TaskManager()
        self._server_thread: UvicornServerThread | None = None
        self._listeners: list[EventListener] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def runtime(self) -> Runtime:
        return self._runtime

    @property
    def config(self) -> ServerSettings:
        return self._config

    @property
    def pipeline(self) -> SpeechPipeline:
        return self._pipeline

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    @property
    def active_profile(self) -> Profile | None:
        return self._pipeline.active_profile

    @property
    def host(self) -> str:
        return self._config.host

    @property
    def port(self) -> int:
        return self._config.port

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def activate_profile(
        self,
        profile_id: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        return await self._pipeline.activate_profile(profile_id, trace_id)

    async def deactivate_profile(self, trace_id: str | None = None) -> bool:
        return await self._pipeline.deactivate_profile(trace_id)

    async def say_text(
        self,
        text: str,
        profile_id: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        return await self._pipeline.say_text(text, profile_id, trace_id)

    async def publish(self, cmd: SpeechCmd) -> bool:
        return await self._pipeline.publish(cmd)

    async def _do_open(self) -> None:
        self._loop = asyncio.get_running_loop()
        await self._exit_stack.enter_async_context(self._tasks)
        await self._exit_stack.enter_async_context(self._pipeline)

        if self._auto_server:
            speech_loop = self._loop

            async def publish_command(cmd: SpeechCmd) -> bool:
                future = asyncio.run_coroutine_threadsafe(
                    self._pipeline.publish(cmd),
                    speech_loop,
                )
                return await asyncio.wrap_future(future)

            context = ServerContext(
                runtime=self._runtime,
                session_manager=self._session_manager,
                publish_command=publish_command,
            )
            app = create_app(context)
            self._server_thread = UvicornServerThread(
                app=app,
                config=self._config,
            )
            self._server_thread.start()

        self._tasks.add_task(self._event_dispatcher_loop())

    async def _do_close(self) -> None:
        if self._server_thread is not None:
            self._server_thread.stop()
            self._server_thread = None
        await self._session_manager.close_all()

    async def _event_dispatcher_loop(self) -> None:
        async for event in self._pipeline.subscribe():
            self._session_manager.dispatch_event(event)

            for listener in list(self._listeners):
                try:
                    res = listener(event)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
