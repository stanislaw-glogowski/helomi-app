import asyncio

from helomi_foundation import EventSource, Logger, on_mount, on_run

from .config import AudioDriverId, AudioRouterSettings
from .domain import AudioDriverDescriptor, RawAudio
from .messages import (
    AudioEvent,
    CapturedEvent,
    ConnectedEvent,
    DisconnectedEvent,
    PlaybackFinishedEvent,
    RouteChangedEvent,
)
from .ports import AudioDriver


class AudioRouter(EventSource[AudioEvent]):
    """Own audio drivers and expose one active conversation route."""

    def __init__(
        self,
        settings: AudioRouterSettings,
        drivers: dict[AudioDriverId, AudioDriver],
        logger: Logger | None = None,
    ):
        super().__init__(logger)
        configured = set(settings.drivers)
        if configured != set(drivers):
            raise ValueError("Audio driver instances do not match router settings")
        self._settings = settings
        self._drivers = drivers
        self._active_driver_id = settings.initial_driver
        self._previous_driver_id: AudioDriverId | None = None
        self._remote_profile_id: str | None = None
        self._monitoring_enabled = settings.monitor_driver is not None
        self._playback_waiters: dict[str, asyncio.Future[bool]] = {}
        self._playback_drivers: dict[str, AudioDriverId] = {}
        self._route_lock = asyncio.Lock()

    @property
    def active_driver_id(self) -> AudioDriverId:
        return self._active_driver_id

    @property
    def remote_profile_id(self) -> str | None:
        return self._remote_profile_id

    @property
    def monitoring_enabled(self) -> bool:
        return self._monitoring_enabled

    @property
    def is_remote_session(self) -> bool:
        return self.active_driver.descriptor.capabilities.remote_session

    @property
    def active_driver(self) -> AudioDriver:
        return self._drivers[self._active_driver_id]

    @property
    def driver_descriptors(self) -> tuple[AudioDriverDescriptor, ...]:
        return tuple(driver.descriptor for driver in self._drivers.values())

    def require_driver(self, driver_id: AudioDriverId) -> AudioDriver:
        try:
            return self._drivers[driver_id]
        except KeyError:
            raise KeyError(f"Audio driver is not configured: {driver_id}") from None

    async def switch_driver(
        self,
        driver_id: AudioDriverId,
        *,
        end_remote_session: bool = False,
    ) -> bool:
        driver = self.require_driver(driver_id)
        if not driver.descriptor.capabilities.manual_profile_selection:
            return False

        # Change route state atomically so capture sees one complete transition.
        async with self._route_lock:
            if driver_id == self._active_driver_id:
                return False
            active = self.active_driver
            if active.descriptor.capabilities.remote_session:
                if not end_remote_session:
                    return False
                await self.interrupt()
                if not await active.disconnect():
                    return False
            else:
                await self.interrupt()

            previous = self._active_driver_id
            self._active_driver_id = driver_id
            self._previous_driver_id = None
            self._remote_profile_id = None

        self._dispatch_event(
            RouteChangedEvent(
                driver_id=driver_id,
                previous_driver_id=previous,
            )
        )
        return True

    def set_monitoring(self, enabled: bool) -> bool:
        if self._settings.monitor_driver is None:
            return False
        changed = self._monitoring_enabled != enabled
        self._monitoring_enabled = enabled
        return changed

    async def play(
        self,
        audio: RawAudio,
        *,
        playback_id: str | None = None,
        turn_id: int | None = None,
    ) -> bool:
        if playback_id is not None and playback_id not in self._playback_waiters:
            self._playback_waiters[playback_id] = (
                asyncio.get_running_loop().create_future()
            )
            self._playback_drivers[playback_id] = self._active_driver_id
        try:
            result = await self.active_driver.play(
                audio,
                playback_id=playback_id,
                turn_id=turn_id,
            )
        except BaseException:
            if playback_id is not None:
                self._playback_waiters.pop(playback_id, None)
                self._playback_drivers.pop(playback_id, None)
            raise
        if not result and playback_id is not None:
            self._playback_waiters.pop(playback_id, None)
            self._playback_drivers.pop(playback_id, None)
        return result

    async def interrupt(self, *, turn_id: int | None = None) -> bool:
        result = await self.active_driver.interrupt(turn_id=turn_id)
        for waiter in self._playback_waiters.values():
            if not waiter.done():
                waiter.set_result(False)
        self._playback_waiters.clear()
        self._playback_drivers.clear()
        return result

    async def start_room_voice(self, profile_id: str) -> bool:
        if not self.active_driver.descriptor.capabilities.room_voice:
            return False
        return await self.active_driver.start_room_voice(profile_id)

    async def stop_room_voice(self) -> bool:
        return await self.active_driver.stop_room_voice()

    async def disconnect(self, farewell: RawAudio | None = None) -> bool:
        return await self.active_driver.disconnect(farewell)

    async def wait_for_playback(self, playback_id: str, timeout_seconds: float) -> bool:
        future = self._playback_waiters.get(playback_id)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            self._playback_waiters[playback_id] = future
        try:
            return await asyncio.wait_for(future, timeout_seconds)
        except TimeoutError:
            return False
        finally:
            self._playback_waiters.pop(playback_id, None)
            self._playback_drivers.pop(playback_id, None)

    @on_mount()
    async def _mount_drivers(self):
        exit_stack = self._exit_stack
        if exit_stack is None:
            raise RuntimeError("Audio router exit stack is not ready")
        for driver in self._drivers.values():
            await exit_stack.enter_async_context(driver)

    @on_run()
    async def _forward_events(self):
        async with asyncio.TaskGroup() as tasks:
            for driver_id, driver in self._drivers.items():
                tasks.create_task(
                    self._forward_driver_events(driver_id, driver),
                    name=f"audio-router:{driver_id}",
                )

    async def _forward_driver_events(
        self,
        driver_id: AudioDriverId,
        driver: AudioDriver,
    ) -> None:
        async for event in driver.subscribe_events():
            await self._handle_event(driver_id, event)

    async def _handle_event(
        self,
        driver_id: AudioDriverId,
        event: AudioEvent,
    ) -> None:
        match event:
            case ConnectedEvent():
                await self._take_over_remote(driver_id, event)
            case DisconnectedEvent():
                await self._restore_route(driver_id, event)
            case CapturedEvent(audio=audio) if driver_id == self._active_driver_id:
                if self.is_remote_session:
                    await self._monitor(audio)
                self._dispatch_event(
                    CapturedEvent(
                        audio=audio,
                        profile_id=event.profile_id,
                        driver_id=driver_id,
                    )
                )
            case PlaybackFinishedEvent(playback_id=playback_id):
                waiter = self._playback_waiters.get(playback_id)
                if (
                    waiter is not None
                    and not waiter.done()
                    and self._playback_drivers.get(playback_id) == driver_id
                ):
                    waiter.set_result(event.status == "played")
                if driver_id == self._active_driver_id:
                    self._dispatch_event(event)
            case _ if driver_id == self._active_driver_id:
                self._dispatch_event(event)

    async def _take_over_remote(
        self,
        driver_id: AudioDriverId,
        event: ConnectedEvent,
    ) -> None:
        driver = self.require_driver(driver_id)
        if not driver.descriptor.capabilities.remote_session:
            return
        async with self._route_lock:
            previous = self._active_driver_id
            if previous != driver_id:
                await self.interrupt()
                self._previous_driver_id = previous
            self._active_driver_id = driver_id
            self._remote_profile_id = event.profile_id
        self._dispatch_event(
            RouteChangedEvent(
                driver_id=driver_id,
                previous_driver_id=previous,
                profile_id=event.profile_id,
            )
        )
        self._dispatch_event(event)

    async def _restore_route(
        self,
        driver_id: AudioDriverId,
        event: DisconnectedEvent,
    ) -> None:
        async with self._route_lock:
            if driver_id != self._active_driver_id:
                self._dispatch_event(event)
                return
            previous = self._active_driver_id
            await self.interrupt()
            restored = self._previous_driver_id or self._settings.initial_driver
            self._active_driver_id = restored
            self._previous_driver_id = None
            self._remote_profile_id = None
        self._dispatch_event(event)
        self._dispatch_event(
            RouteChangedEvent(
                driver_id=restored,
                previous_driver_id=previous,
            )
        )

    async def _monitor(self, audio: RawAudio) -> None:
        monitor_id = self._settings.monitor_driver
        if not self._monitoring_enabled or monitor_id is None:
            return
        if monitor_id == self._active_driver_id:
            return
        await self.require_driver(monitor_id).play(audio)
