from typing import ClassVar

import uvicorn

from helomi_foundation import on_run, on_unmount

from ..domain import (
    AudioDriverCapabilities,
    AudioDriverDescriptor,
    AudioDriverKind,
    AudioDriverState,
)
from ..messages import AudioCommand
from ..ports import AudioDriver
from .bridge import TwilioBridge
from .config import TwilioProfile, TwilioSettings
from .entrypoint import create_app


class TwilioDriver(AudioDriver[TwilioSettings, TwilioProfile]):
    _DESCRIPTOR: ClassVar[AudioDriverDescriptor] = AudioDriverDescriptor(
        id="twilio",
        name="Twilio",
        kind=AudioDriverKind.GSM,
        capabilities=AudioDriverCapabilities(
            capture=True,
            playback=True,
            interrupt=True,
            room_voice=True,
            remote_session=True,
            local_monitoring=False,
            manual_profile_selection=False,
        ),
    )

    def __init__(
        self,
        settings: TwilioSettings,
        profiles: dict[str, TwilioProfile],
    ):
        super().__init__(settings, profiles)
        self._bridge = TwilioBridge(
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

    @property
    def descriptor(self) -> AudioDriverDescriptor:
        return self._DESCRIPTOR

    @property
    def state(self) -> AudioDriverState:
        if self._bridge.is_connected:
            return AudioDriverState.CONNECTED
        return super().state

    async def execute_command(self, cmd: AudioCommand) -> bool:
        return await self._bridge.execute_command(cmd)

    @on_run()
    async def _serve(self):
        self._server.should_exit = False
        await self._server.serve()

    @on_unmount()
    async def _stop(self):
        self._server.should_exit = True
        await self._bridge.shutdown()
