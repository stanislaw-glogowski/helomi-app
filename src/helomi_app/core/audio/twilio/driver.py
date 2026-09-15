import asyncio
import threading
from typing import ClassVar

import uvicorn

from ..domain import AudioDriverKind
from ..messages import AudioCmd, DisconnectCmd, DisconnectedEvent, InterruptCmd, PlayCmd
from ..ports import AudioDriver
from .config import TwilioProfile, TwilioSettings
from .entrypoint import Bridge, create_app


class TwilioDriver(AudioDriver):
    _CLOSE_TIMEOUT: ClassVar[float] = 5.0

    def __init__(
        self,
        settings: TwilioSettings,
        profiles: dict[str, TwilioProfile],
    ) -> None:
        super().__init__(settings, profiles)

        self._bridge = Bridge(
            settings=settings,
            profiles=profiles,
            dispatch_event=self._dispatch_event,
        )
        self._server = uvicorn.Server(
            config=uvicorn.Config(
                app=create_app(bridge=self._bridge),
                host="0.0.0.0",
                port=settings.port,
                log_level="warning",
                access_log=False,
                lifespan="on",
            )
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def kind(self) -> AudioDriverKind:
        return AudioDriverKind.GSM

    @property
    def room_voice_supported(self) -> bool:
        return False

    def execute_command(self, cmd: AudioCmd) -> bool:
        if self._loop is None:
            return False

        match cmd:
            case PlayCmd():
                asyncio.run_coroutine_threadsafe(
                    self._bridge.send_audio(cmd.audio, cmd.is_final),
                    self._loop,
                )
                if cmd.is_final:
                    self._dispatch_event(DisconnectedEvent())
                return True

            case InterruptCmd():
                if not self._bridge.is_sending_audio:
                    return False

                asyncio.run_coroutine_threadsafe(
                    self._bridge.abort_sending_audio(),
                    self._loop,
                )
                return True

            case DisconnectCmd():
                asyncio.run_coroutine_threadsafe(
                    self._bridge.disconnect_profile(),
                    self._loop,
                )
                return True

            case _:
                return False

    async def _do_open(self) -> None:
        thread = threading.Thread(
            target=self._serve,
            name=self.__label__,
            daemon=True,
        )

        self._thread = thread
        self._server.should_exit = False
        thread.start()

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
        self._loop = loop
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
