import asyncio
import base64
import hashlib
import hmac
import json
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import httpx
import numpy as np
import pytest
from fastapi import HTTPException, WebSocketDisconnect
from starlette.requests import Request

from helomi_runtime.audio import (
    AudioChunk,
    AudioFile,
    AudioFormat,
    CapturedEvent,
    ConnectedEvent,
    DisconnectCommand,
    DisconnectedEvent,
    InterruptCommand,
    PlayCommand,
    RawAudio,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)
from helomi_runtime.audio.room_voice import RoomVoiceProfile
from helomi_runtime.audio.twilio.bridge import TwilioBridge, TwilioConnection
from helomi_runtime.audio.twilio.config import TwilioProfile, TwilioSettings
from helomi_runtime.audio.twilio.driver import TwilioDriver
from helomi_runtime.audio.twilio.entrypoint import create_app, handle_websocket
from helomi_runtime.audio.twilio.mixer import TwilioMixer


class FakeWebSocket:
    def __init__(self, messages: list[dict] | None = None):
        self.messages = deque(json.dumps(message) for message in messages or [])
        self.sent: list[str] = []
        self.closed: list[int] = []

    async def receive_text(self) -> str:
        if not self.messages:
            raise WebSocketDisconnect()
        return self.messages.popleft()

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)


def create_bridge(
    events: list | None = None,
    *,
    clock=lambda: 100.0,
    validate_signature: bool = True,
) -> TwilioBridge:
    settings = TwilioSettings(
        auth_token="secret",
        public_url="https://voice.example.test/twilio/",
        validate_signature=validate_signature,
        session_ttl=30,
    )
    return TwilioBridge(
        settings,
        {"alexa": TwilioProfile(callees=["+15555550100"])},
        (events if events is not None else []).append,
        wall_clock=clock,
    )


def twilio_connected() -> dict:
    return {"event": "connected", "protocol": "Call", "version": "1.0.0"}


def twilio_start(call_sid: str = "CA1", encoding: str = "audio/x-mulaw") -> dict:
    return {
        "event": "start",
        "sequenceNumber": "1",
        "streamSid": "MZ1",
        "start": {
            "accountSid": "AC1",
            "streamSid": "MZ1",
            "callSid": call_sid,
            "tracks": ["inbound"],
            "mediaFormat": {
                "encoding": encoding,
                "sampleRate": 8000,
                "channels": 1,
            },
        },
    }


def session_parts(url: str) -> tuple[str, str, str, str]:
    profile_id, call_sid, deadline, signature = (
        urlparse(url).path.rstrip("/").split("/")[-4:]
    )
    return profile_id, call_sid, deadline, signature


async def test_call_reservation_is_busy_expiring_and_one_time():
    now = [100.0]
    bridge = create_bridge(clock=lambda: now[0])
    url = await bridge.reserve_call("alexa", "CA1", "+15555550101")
    assert url is not None
    assert await bridge.reserve_call("alexa", "CA2", "+15555550102") is None

    assert await bridge.claim_session(*session_parts(url))
    assert not await bridge.claim_session(*session_parts(url))

    now[0] = 131.0
    second_url = await bridge.reserve_call("alexa", "CA2", "+15555550102")
    assert second_url is not None
    now[0] = 162.0
    assert not await bridge.claim_session(*session_parts(second_url))


def test_signature_uses_forwarded_url_and_all_parameters():
    params = [("CallSid", "CA1"), ("Unknown", "value"), ("To", "+15555550100")]
    public_url = "https://public.example.test/proxy/voice?source=twilio"
    payload = public_url + "".join(f"{key}{value}" for key, value in sorted(params))
    signature = base64.b64encode(
        hmac.new(b"secret", payload.encode(), hashlib.sha1).digest()
    ).decode()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/voice",
            "query_string": b"source=twilio",
            "headers": [
                (b"host", b"internal:8000"),
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"public.example.test"),
                (b"x-forwarded-prefix", b"/proxy"),
                (b"x-twilio-signature", signature.encode()),
            ],
            "server": ("internal", 8000),
            "client": ("127.0.0.1", 1234),
        }
    )

    assert create_bridge().is_request_valid(request, params)


async def test_valid_handshake_dispatches_inbound_audio_and_disconnect():
    events = []
    bridge = create_bridge(events)
    url = await bridge.reserve_call("alexa", "CA1", "+15555550101")
    assert url is not None
    assert await bridge.claim_session(*session_parts(url))
    payload = base64.b64encode(b"\xff" * 160).decode()
    websocket = FakeWebSocket(
        [
            twilio_connected(),
            twilio_start(),
            {
                "event": "media",
                "sequenceNumber": "2",
                "streamSid": "MZ1",
                "media": {
                    "track": "inbound",
                    "chunk": "1",
                    "timestamp": "0",
                    "payload": payload,
                },
            },
            {
                "event": "stop",
                "sequenceNumber": "3",
                "streamSid": "MZ1",
                "stop": {"accountSid": "AC1", "callSid": "CA1"},
            },
        ]
    )

    await bridge.connect("alexa", "CA1", websocket)  # type: ignore[arg-type]

    assert [type(event) for event in events] == [
        ConnectedEvent,
        CapturedEvent,
        DisconnectedEvent,
    ]
    assert len(events[1].audio.data) == 160 * 4


async def test_malformed_handshake_is_closed_without_starting_session():
    events = []
    bridge = create_bridge(events)
    url = await bridge.reserve_call("alexa", "CA1", "+15555550101")
    assert url is not None
    assert await bridge.claim_session(*session_parts(url))
    websocket = FakeWebSocket([twilio_connected(), twilio_start(encoding="linear16")])

    await bridge.connect("alexa", "CA1", websocket)  # type: ignore[arg-type]

    assert websocket.closed == [1003]
    assert not events


def test_mixer_outputs_exact_twenty_millisecond_frames_and_bounds_queue():
    mixer = TwilioMixer(max_pending_playbacks=1)
    samples = np.linspace(-0.5, 0.5, 320, dtype=np.float32)
    raw = RawAudio(AudioFormat.MONO_8, samples.tobytes())

    assert mixer.enqueue(raw, "first", 1)
    assert not mixer.enqueue(raw, "second", 1)
    first = mixer.next_frame()
    second = mixer.next_frame()

    assert first is not None and len(first.data) == 160
    assert not first.completed_playbacks
    assert second is not None and len(second.data) == 160
    assert second.completed_playbacks == ("first",)


def test_mixer_resamples_invalidates_stale_turns_and_ducks_room_voice(tmp_path):
    room_path = tmp_path / "room.wav"
    AudioFile(room_path).write(
        AudioChunk(
            AudioFormat.MONO_8,
            np.full(80, 0.5, dtype=np.float32),
        )
    )
    mixer = TwilioMixer(max_pending_playbacks=2)
    mixer.start_room_voice(RoomVoiceProfile(path=room_path, volume=1.0, ducking=0.25))
    assert mixer.room_voice_active

    ambient_frame = mixer.next_frame()
    assert ambient_frame is not None
    ambient = AudioChunk.from_mulaw(ambient_frame.data, AudioFormat.MONO_8).samples
    assert np.mean(ambient) == pytest.approx(0.5, abs=0.05)

    speech_16k = RawAudio(
        AudioFormat.MONO_16,
        np.full(320, 0.8, dtype=np.float32).tobytes(),
    )
    assert mixer.enqueue(speech_16k, "turn-2", 2)
    assert not mixer.enqueue(speech_16k, "stale-turn", 1)
    mixed_frame = mixer.next_frame()
    assert mixed_frame is not None
    mixed = AudioChunk.from_mulaw(mixed_frame.data, AudioFormat.MONO_8).samples
    assert np.mean(mixed) == pytest.approx(0.925, abs=0.06)
    assert mixed_frame.completed_playbacks == ("turn-2",)

    assert mixer.enqueue(speech_16k, "queued", 2)
    mixer.interrupt(turn_id=3)
    assert mixer.pending_playbacks == 0
    assert not mixer.enqueue(speech_16k, "invalidated", 2)
    mixer.stop_room_voice()
    assert not mixer.room_voice_active
    assert mixer.next_frame() is None


async def test_output_is_paced_and_sends_mark_after_logical_playback():
    current = [0.0]
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)
        current[0] += delay

    settings = TwilioSettings(
        auth_token="secret",
        public_url="https://voice.example.test/twilio/",
    )
    bridge = TwilioBridge(
        settings,
        {"alexa": TwilioProfile(callees=["+15555550100"])},
        lambda event: None,
        monotonic=lambda: current[0],
        sleep=sleep,
    )
    websocket = FakeWebSocket()
    connection = TwilioConnection(websocket)  # type: ignore[arg-type]
    connection.start("MZ1")
    bridge._connection = connection
    raw = RawAudio(
        AudioFormat.MONO_8,
        np.zeros(320, dtype=np.float32).tobytes(),
    )

    assert await bridge.execute_command(PlayCommand(raw, playback_id="playback-1"))
    task = asyncio.create_task(bridge._output_loop(connection))
    for _ in range(10):
        if any('"event":"mark"' in message for message in websocket.sent):
            break
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    commands = [json.loads(message) for message in websocket.sent]
    assert [command["event"] for command in commands] == ["media", "media", "mark"]
    assert all(
        len(base64.b64decode(command["media"]["payload"])) == 160
        for command in commands[:2]
    )
    assert delays == [pytest.approx(0.02)]


async def test_mark_acknowledges_playback_and_interrupt_sends_clear():
    events = []
    bridge = create_bridge(events)
    url = await bridge.reserve_call("alexa", "CA1", "+15555550101")
    assert url is not None
    assert await bridge.claim_session(*session_parts(url))
    bridge._pending_marks.add("playback-1")
    websocket = FakeWebSocket(
        [
            twilio_connected(),
            twilio_start(),
            {
                "event": "mark",
                "sequenceNumber": "2",
                "streamSid": "MZ1",
                "mark": {"name": "playback-1"},
            },
            {
                "event": "stop",
                "sequenceNumber": "3",
                "streamSid": "MZ1",
                "stop": {"accountSid": "AC1", "callSid": "CA1"},
            },
        ]
    )
    await bridge.connect("alexa", "CA1", websocket)  # type: ignore[arg-type]
    assert any(event.__class__.__name__ == "PlaybackFinishedEvent" for event in events)

    active_socket = FakeWebSocket()
    connection = TwilioConnection(active_socket)  # type: ignore[arg-type]
    connection.start("MZ2")
    bridge._connection = connection
    replacement = RawAudio(
        AudioFormat.MONO_8,
        np.zeros(160, dtype=np.float32).tobytes(),
    )
    assert await bridge.execute_command(InterruptCommand(audio=replacement, turn_id=3))
    assert json.loads(active_socket.sent[0])["event"] == "clear"
    assert bridge._mixer.pending_playbacks == 1
    assert not bridge._mixer.enqueue(replacement, "stale-after-clear", 2)


async def test_http_entrypoint_handles_connect_reject_busy_and_errors():
    bridge = create_bridge(validate_signature=False)
    app = create_app(bridge)
    ringing = {
        "CallStatus": "ringing",
        "From": "+15555550101",
        "To": "+15555550100",
        "CallSid": "CA1",
        "Unknown": "preserved",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/")).json()["version"] == "0.8.0"
        assert (await client.get("/health")).json() == {"status": "OK"}
        ignored = await client.post("/", data={"CallStatus": "completed"})
        assert ignored.status_code == 204
        invalid = await client.post("/", data={"CallStatus": "ringing"})
        assert invalid.status_code == 400
        connected = await client.post("/", data=ringing)
        assert connected.status_code == 200
        assert "&lt;" not in connected.text
        assert "<Connect><Stream" in connected.text
        busy = await client.post("/", data={**ringing, "CallSid": "CA2"})
        assert 'reason="busy"' in busy.text

    restricted = TwilioBridge(
        TwilioSettings(
            auth_token="secret",
            public_url="https://voice.example.test/",
            allowed_callers=["+100"],
            validate_signature=False,
        ),
        {"alexa": TwilioProfile(callees=["+200"])},
        lambda event: None,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(restricted)),
        base_url="http://test",
    ) as client:
        rejected = await client.post(
            "/",
            data={
                "CallStatus": "ringing",
                "From": "+999",
                "To": "+200",
                "CallSid": "CA3",
            },
        )
        assert 'reason="rejected"' in rejected.text
        missing = await client.post(
            "/",
            data={
                "CallStatus": "ringing",
                "From": "+100",
                "To": "+404",
                "CallSid": "CA4",
            },
        )
        assert missing.status_code == 404

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(create_bridge())),
        base_url="http://test",
    ) as client:
        unauthorized = await client.post("/", data=ringing)
        assert unauthorized.status_code == 401


async def test_websocket_entrypoint_claims_before_accepting():
    bridge = MagicMock()
    bridge.claim_session = AsyncMock(return_value=False)
    bridge.connect = AsyncMock()
    websocket = MagicMock()
    websocket.app.state.bridge = bridge
    websocket.close = AsyncMock()
    websocket.accept = AsyncMock()

    with pytest.raises(HTTPException):
        await handle_websocket(websocket)

    await handle_websocket(websocket, "alexa", "CA1", "100", "bad")
    websocket.close.assert_awaited_once_with(code=4401)
    websocket.accept.assert_not_awaited()

    bridge.claim_session.return_value = True
    await handle_websocket(websocket, "alexa", "CA1", "100", "good")
    websocket.accept.assert_awaited_once()
    bridge.connect.assert_awaited_once_with("alexa", "CA1", websocket)


async def test_connection_and_bridge_command_branches(tmp_path):
    socket = FakeWebSocket()
    connection = TwilioConnection(socket)  # type: ignore[arg-type]
    raw_audio = RawAudio(AudioFormat.MONO_8, b"")
    assert not await connection.send(PlayCommand(raw_audio))  # type: ignore[arg-type]
    connection.start("MZ1")
    with pytest.raises(RuntimeError, match="already started"):
        connection.start("MZ2")

    bridge = create_bridge()
    bridge._connection = connection
    assert await bridge.execute_command(InterruptCommand())
    assert not await bridge.execute_command(StartRoomVoiceCommand(profile_id="alexa"))
    room_path = tmp_path / "room.wav"
    AudioFile(room_path).write(
        AudioChunk(AudioFormat.MONO_8, np.zeros(160, dtype=np.float32))
    )
    bridge._profiles["alexa"] = TwilioProfile(
        callees=["+15555550100"],
        room_voice=RoomVoiceProfile(path=room_path),
    )
    assert await bridge.execute_command(StartRoomVoiceCommand(profile_id="alexa"))
    assert await bridge.execute_command(StopRoomVoiceCommand())
    assert not await bridge.execute_command(StopRoomVoiceCommand())
    assert await bridge.execute_command(DisconnectCommand())
    assert not await connection.close()
    assert not await connection.send(PlayCommand(raw_audio))  # type: ignore[arg-type]
    await bridge.shutdown()


async def test_twilio_driver_delegates_and_stops_server():
    settings = TwilioSettings(
        auth_token="secret",
        public_url="https://voice.example.test/",
    )
    fake_server = MagicMock()
    fake_server.serve = AsyncMock()
    fake_bridge = MagicMock()
    fake_bridge.is_connected = True
    fake_bridge.execute_command = AsyncMock(return_value=True)
    fake_bridge.shutdown = AsyncMock()
    with (
        patch(
            "helomi_runtime.audio.twilio.driver.uvicorn.Server",
            return_value=fake_server,
        ),
        patch(
            "helomi_runtime.audio.twilio.driver.TwilioBridge",
            return_value=fake_bridge,
        ),
    ):
        driver = TwilioDriver(
            settings, {"alexa": TwilioProfile(callees=["+15555550100"])}
        )
        assert driver.descriptor.id == "twilio"
        assert driver.state.value == "connected"
        assert await driver.execute_command(DisconnectCommand())
        await driver.__aenter__()
        await asyncio.sleep(0)
        await driver.__aexit__(None, None, None)
    fake_server.serve.assert_awaited_once()
    fake_bridge.shutdown.assert_awaited_once()
    assert fake_server.should_exit is True
