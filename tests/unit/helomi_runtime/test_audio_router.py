import asyncio

from helomi_runtime.audio import (
    AudioDriver,
    AudioDriverCapabilities,
    AudioDriverDescriptor,
    AudioDriverKind,
    AudioEvent,
    AudioFormat,
    AudioRouter,
    CapturedEvent,
    ConnectedEvent,
    DisconnectCommand,
    DisconnectedEvent,
    InterruptCommand,
    PlaybackFinishedEvent,
    PlayCommand,
    RawAudio,
    RouteChangedEvent,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)
from helomi_runtime.audio.config import AudioRouterSettings


class FakeDriver(AudioDriver[object, object]):
    def __init__(self, info: AudioDriverDescriptor):
        super().__init__(object(), {})
        self._descriptor = info
        self.commands = []
        self.result = True

    @property
    def descriptor(self) -> AudioDriverDescriptor:
        return self._descriptor

    async def execute_command(self, cmd) -> bool:
        self.commands.append(cmd)
        return self.result

    def emit(self, event: AudioEvent) -> None:
        self._dispatch_event(event)


LOCAL_INFO = AudioDriverDescriptor(
    id="avfaudio",
    name="Local",
    kind=AudioDriverKind.LOCAL,
    capabilities=AudioDriverCapabilities(
        capture=True,
        playback=True,
        interrupt=True,
        room_voice=True,
        remote_session=False,
        local_monitoring=True,
        manual_profile_selection=True,
    ),
)
REMOTE_INFO = AudioDriverDescriptor(
    id="twilio",
    name="Remote",
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


def create_router() -> tuple[AudioRouter, FakeDriver, FakeDriver]:
    local = FakeDriver(LOCAL_INFO)
    remote = FakeDriver(REMOTE_INFO)
    settings = AudioRouterSettings.model_validate(
        {
            "initial_driver": "avfaudio",
            "monitor_driver": "avfaudio",
            "drivers": ["avfaudio", "twilio"],
            "avfaudio": {},
            "twilio": {
                "auth_token": "secret",
                "public_url": "https://example.test/voice/",
            },
        }
    )
    return AudioRouter(settings, {"avfaudio": local, "twilio": remote}), local, remote


async def test_remote_takeover_monitor_and_restore_event_order():
    router, local, remote = create_router()
    raw = RawAudio(AudioFormat.MONO_8, b"\x00" * 640)
    events: list[AudioEvent] = []

    async with router:

        async def collect():
            async for event in router.subscribe_events():
                events.append(event)
                if len(events) == 5:
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        remote.emit(ConnectedEvent("twilio", "alexa", "CA1", "+15555550100"))
        remote.emit(CapturedEvent(raw, profile_id="alexa"))
        remote.emit(DisconnectedEvent("twilio", "CA1"))
        await asyncio.wait_for(collector, 1)

        assert router.active_driver_id == "avfaudio"
        assert any(isinstance(command, PlayCommand) for command in local.commands)

    assert [type(event) for event in events] == [
        RouteChangedEvent,
        ConnectedEvent,
        CapturedEvent,
        DisconnectedEvent,
        RouteChangedEvent,
    ]


async def test_monitoring_can_be_disabled_and_local_capture_is_filtered():
    router, local, remote = create_router()
    raw = RawAudio(AudioFormat.MONO_8, b"\x00" * 640)
    events: list[AudioEvent] = []

    async with router:

        async def collect():
            async for event in router.subscribe_events():
                events.append(event)
                if len(events) == 5:
                    return

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        remote.emit(ConnectedEvent("twilio", "alexa", "CA1", "+15555550100"))
        assert router.set_monitoring(False)
        local.emit(CapturedEvent(raw))
        remote.emit(CapturedEvent(raw, profile_id="alexa"))
        await asyncio.sleep(0)
        remote.emit(DisconnectedEvent("twilio", "CA1"))
        await asyncio.wait_for(collector, 1)

    assert not any(isinstance(command, PlayCommand) for command in local.commands)
    assert sum(isinstance(event, CapturedEvent) for event in events) == 1


async def test_manual_switch_requires_remote_disconnect_confirmation():
    router, _, remote = create_router()

    async with router:
        await router._handle_event(
            "twilio",
            ConnectedEvent("twilio", "alexa", "CA1", "+15555550100"),
        )

        assert not await router.switch_driver("avfaudio")
        assert await router.switch_driver(
            "avfaudio",
            end_remote_session=True,
        )

    assert isinstance(remote.commands[-1], DisconnectCommand)
    assert not await router.switch_driver("twilio")


async def test_router_command_delegation_waiters_and_failures():
    router, local, remote = create_router()
    raw = RawAudio(AudioFormat.MONO_8, b"\x00" * 640)
    assert router.active_driver is local
    assert not router.is_remote_session
    assert router.monitoring_enabled
    assert tuple(item.id for item in router.driver_descriptors) == (
        "avfaudio",
        "twilio",
    )
    try:
        router.require_driver("missing")  # type: ignore[arg-type]
    except KeyError as error:
        assert "not configured" in str(error)
    else:
        raise AssertionError("Expected missing driver error")

    assert not await router.switch_driver("avfaudio")
    assert await router.play(raw, playback_id="one", turn_id=1)
    assert isinstance(local.commands[-1], PlayCommand)
    waiter = asyncio.create_task(router.wait_for_playback("one", 1))
    await asyncio.sleep(0)
    await router._handle_event("avfaudio", PlaybackFinishedEvent("avfaudio", "one"))
    assert await waiter

    timeout = await router.wait_for_playback("missing", 0.001)
    assert not timeout
    assert await router.start_room_voice("alexa")
    assert isinstance(local.commands[-1], StartRoomVoiceCommand)
    assert await router.stop_room_voice()
    assert isinstance(local.commands[-1], StopRoomVoiceCommand)
    assert await router.disconnect(raw)
    assert isinstance(local.commands[-1], DisconnectCommand)

    await router.play(raw, playback_id="interrupt")
    waiting = asyncio.create_task(router.wait_for_playback("interrupt", 1))
    await asyncio.sleep(0)
    assert await router.interrupt(turn_id=2)
    assert isinstance(local.commands[-1], InterruptCommand)
    assert local.commands[-1].turn_id == 2
    assert not await waiting

    local.result = False
    assert not await router.play(raw, playback_id="failed")
    assert "failed" not in router._playback_waiters
    remote.result = False
    await router._take_over_remote(
        "twilio", ConnectedEvent("twilio", "alexa", "CA1", "+100")
    )
    assert not await router.switch_driver("avfaudio", end_remote_session=True)


async def test_router_edge_routes_and_capabilities():
    router, _local, _ = create_router()
    raw = RawAudio(AudioFormat.MONO_8, b"\x00" * 640)
    await router._take_over_remote(
        "avfaudio", ConnectedEvent("avfaudio", "alexa", "CA1", "+100")
    )
    assert router.active_driver_id == "avfaudio"
    await router._restore_route("twilio", DisconnectedEvent("twilio", "CA1"))

    no_room = AudioDriverDescriptor(
        id="avfaudio",
        name="No room voice",
        kind=AudioDriverKind.LOCAL,
        capabilities=AudioDriverCapabilities(
            capture=True,
            playback=True,
            interrupt=True,
            room_voice=False,
            remote_session=False,
            local_monitoring=True,
            manual_profile_selection=True,
        ),
    )
    settings = AudioRouterSettings.model_validate(
        {"initial_driver": "avfaudio", "drivers": ["avfaudio"], "avfaudio": {}}
    )
    without_monitor = AudioRouter(settings, {"avfaudio": FakeDriver(no_room)})
    assert not without_monitor.set_monitoring(False)
    assert not await without_monitor.start_room_voice("alexa")
    await without_monitor._monitor(raw)

    invalid = FakeDriver(LOCAL_INFO)
    try:
        AudioRouter(settings, {"twilio": invalid})  # type: ignore[dict-item]
    except ValueError as error:
        assert "do not match" in str(error)
    else:
        raise AssertionError("Expected driver layout error")
