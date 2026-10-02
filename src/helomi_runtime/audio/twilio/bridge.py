import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import ClassVar
from uuid import uuid4

from fastapi import Request, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..domain import AudioFormat, RawAudio
from ..messages import (
    AudioCommand,
    AudioEvent,
    CapturedEvent,
    ConnectedEvent,
    DisconnectCommand,
    DisconnectedEvent,
    InterruptCommand,
    PlaybackFinishedEvent,
    PlayCommand,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)
from .config import TwilioProfile, TwilioSettings
from .mixer import TwilioMixer
from .protocol import (
    ClearCommand,
    ConnectedMessage,
    MarkCommand,
    MarkMessage,
    MediaCommand,
    MediaMessage,
    StartMessage,
    StopMessage,
    TwilioCommand,
    TwilioMessageAdapter,
)


@dataclass(slots=True)
class CallReservation:
    profile_id: str
    call_sid: str
    caller: str
    deadline: int
    claimed: bool = False


class TwilioConnection:
    def __init__(self, websocket: WebSocket):
        self._websocket: WebSocket | None = websocket
        self._stream_sid: str | None = None
        self._send_lock = asyncio.Lock()

    @property
    def stream_sid(self) -> str | None:
        return self._stream_sid

    def start(self, stream_sid: str) -> None:
        if self._stream_sid is not None:
            raise RuntimeError("Twilio stream is already started")
        self._stream_sid = stream_sid

    async def send(self, command: TwilioCommand) -> bool:
        async with self._send_lock:
            if self._websocket is None or self._stream_sid is None:
                return False
            command.stream_sid = self._stream_sid
            await self._websocket.send_text(command.model_dump_json(by_alias=True))
            return True

    async def close(self, code: int = 1000) -> bool:
        async with self._send_lock:
            if self._websocket is None:
                return False
            websocket, self._websocket = self._websocket, None
            await websocket.close(code=code)
            return True


class TwilioBridge:
    """Reserve, validate, and bridge one inbound Twilio Media Stream."""

    _INPUT_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_8
    _FRAME_DURATION: ClassVar[float] = 0.020

    def __init__(
        self,
        settings: TwilioSettings,
        profiles: dict[str, TwilioProfile],
        dispatch_event: Callable[[AudioEvent], None],
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._dispatch_event = dispatch_event
        self._settings = settings
        self._profiles = profiles
        self._callee_profiles = {
            callee: profile_id
            for profile_id, profile in profiles.items()
            for callee in profile.callees
        }
        self._secret = secrets.token_bytes(32)
        self._wall_clock = wall_clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._mixer = TwilioMixer(settings.output_buffer_chunks)
        self._reservation: CallReservation | None = None
        self._connection: TwilioConnection | None = None
        self._pending_marks: set[str] = set()
        self._output_ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._mixer_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    def get_profile_id(self, callee: str) -> str | None:
        return self._callee_profiles.get(callee)

    def is_caller_allowed(self, caller: str) -> bool:
        allowed = self._settings.allowed_callers
        return allowed is None or caller in allowed

    async def reserve_call(
        self,
        profile_id: str,
        call_sid: str,
        caller: str,
    ) -> str | None:
        async with self._lock:
            self._discard_expired_reservation()
            if self._reservation is not None or self._connection is not None:
                return None
            deadline = int(self._wall_clock() + self._settings.session_ttl)
            self._reservation = CallReservation(
                profile_id=profile_id,
                call_sid=call_sid,
                caller=caller,
                deadline=deadline,
            )
        return self._websocket_url(profile_id, call_sid, deadline)

    async def claim_session(
        self,
        profile_id: str,
        call_sid: str,
        deadline: str,
        signature: str,
    ) -> bool:
        try:
            deadline_value = int(deadline)
        except ValueError:
            return False
        expected = self._sign_session(profile_id, call_sid, deadline_value)
        if not hmac.compare_digest(expected, signature):
            return False

        async with self._lock:
            self._discard_expired_reservation()
            reservation = self._reservation
            # Claiming is one-shot to bind a websocket to its webhook CallSid.
            if (
                reservation is None
                or reservation.claimed
                or deadline_value < int(self._wall_clock())
                or reservation.profile_id != profile_id
                or reservation.call_sid != call_sid
                or reservation.deadline != deadline_value
            ):
                return False
            reservation.claimed = True
            return True

    async def connect(
        self,
        profile_id: str,
        call_sid: str,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            reservation = self._reservation
            if (
                reservation is None
                or not reservation.claimed
                or reservation.profile_id != profile_id
                or reservation.call_sid != call_sid
                or self._connection is not None
            ):
                await websocket.close(code=4409)
                return
            connection = TwilioConnection(websocket)
            self._connection = connection

        started = False
        try:
            await self._handshake(connection, websocket, reservation)
            started = True
            self._dispatch_event(
                ConnectedEvent(
                    driver_id="twilio",
                    profile_id=profile_id,
                    call_sid=call_sid,
                    caller=reservation.caller,
                )
            )
            output_task = asyncio.create_task(
                self._output_loop(connection),
                name=f"twilio-output:{call_sid}",
            )
            try:
                await self._receive_loop(connection, websocket, call_sid, profile_id)
            finally:
                output_task.cancel()
                await asyncio.gather(output_task, return_exceptions=True)
        except ValidationError, ValueError, RuntimeError, TimeoutError:
            await connection.close(code=1003)
        except WebSocketDisconnect:
            pass
        finally:
            async with self._mixer_lock:
                self._mixer.interrupt()
                self._mixer.stop_room_voice()
            self._pending_marks.clear()
            self._output_ready.clear()
            async with self._lock:
                if self._connection is connection:
                    self._connection = None
                if self._reservation is reservation:
                    self._reservation = None
            if started:
                self._dispatch_event(
                    DisconnectedEvent(driver_id="twilio", call_sid=call_sid)
                )

    async def execute_command(self, command: AudioCommand) -> bool:
        async with self._lock:
            connection = self._connection
        if connection is None or connection.stream_sid is None:
            return False

        match command:
            case PlayCommand(audio=audio, playback_id=playback_id, turn_id=turn_id):
                async with self._mixer_lock:
                    queued = self._mixer.enqueue(
                        audio,
                        playback_id or uuid4().hex,
                        turn_id,
                    )
                if queued:
                    self._output_ready.set()
                return queued
            case InterruptCommand(audio=audio, turn_id=turn_id):
                async with self._mixer_lock:
                    self._mixer.interrupt(turn_id)
                self._pending_marks.clear()
                sent = await connection.send(ClearCommand(stream_sid=""))
                if audio is not None:
                    async with self._mixer_lock:
                        queued = self._mixer.enqueue(audio, uuid4().hex, None)
                    if queued:
                        self._output_ready.set()
                return sent
            case StartRoomVoiceCommand(profile_id=profile_id):
                profile = self._profiles.get(profile_id)
                if profile is None or profile.room_voice is None:
                    return False
                async with self._mixer_lock:
                    await asyncio.to_thread(
                        self._mixer.start_room_voice,
                        profile.room_voice,
                    )
                self._output_ready.set()
                return True
            case StopRoomVoiceCommand():
                async with self._mixer_lock:
                    if not self._mixer.room_voice_active:
                        return False
                    self._mixer.stop_room_voice()
                return True
            case DisconnectCommand():
                return await connection.close()

    async def shutdown(self) -> None:
        async with self._lock:
            connection = self._connection
            self._reservation = None
        if connection is not None:
            await connection.close()

    def is_request_valid(
        self,
        request: Request,
        params: Sequence[tuple[str, str]],
    ) -> bool:
        if not self._settings.validate_signature:
            return True
        signature = request.headers.get("x-twilio-signature", "")

        if not signature:
            return False
        url = self._public_request_url(request)

        payload = url + "".join(
            f"{key}{value}" for key, value in sorted(params, key=lambda item: item)
        )
        digest = hmac.new(
            self._settings.auth_token.encode(),
            payload.encode(),
            hashlib.sha1,
        ).digest()

        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(expected, signature)

    async def _handshake(
        self,
        connection: TwilioConnection,
        websocket: WebSocket,
        reservation: CallReservation,
    ) -> None:
        connected = TwilioMessageAdapter.validate_json(
            await asyncio.wait_for(
                websocket.receive_text(),
                timeout=self._settings.handshake_timeout,
            )
        )
        if not isinstance(connected, ConnectedMessage):
            raise ValueError("Expected Twilio connected event")
        if connected.protocol != "Call" or connected.version != "1.0.0":
            raise ValueError("Unsupported Twilio media protocol")

        start = TwilioMessageAdapter.validate_json(
            await asyncio.wait_for(
                websocket.receive_text(),
                timeout=self._settings.handshake_timeout,
            )
        )
        if not isinstance(start, StartMessage):
            raise ValueError("Expected Twilio start event")
        if start.start.call_sid != reservation.call_sid:
            raise ValueError("Twilio CallSid does not match the reservation")
        if start.stream_sid != start.start.stream_sid:
            raise ValueError("Twilio StreamSid mismatch")
        if start.sequence_number != "1" or "inbound" not in start.start.tracks:
            raise ValueError("Invalid Twilio start sequence or tracks")
        media_format = start.start.format
        if (
            media_format.encoding != "audio/x-mulaw"
            or media_format.sample_rate != 8_000
            or media_format.channels != 1
        ):
            raise ValueError("Unsupported Twilio media format")
        connection.start(start.stream_sid)

    async def _receive_loop(
        self,
        connection: TwilioConnection,
        websocket: WebSocket,
        call_sid: str,
        profile_id: str,
    ) -> None:
        sequence = 1
        while True:
            event = TwilioMessageAdapter.validate_json(await websocket.receive_text())
            if isinstance(event, ConnectedMessage):
                raise ValueError("Unexpected duplicate Twilio connected event")
            event_sequence = int(event.sequence_number)
            if event_sequence <= sequence:
                raise ValueError("Twilio sequence number is not increasing")
            sequence = event_sequence

            match event:
                case MediaMessage():
                    if event.stream_sid != connection.stream_sid:
                        raise ValueError("Twilio StreamSid mismatch")
                    if event.media.track != "inbound":
                        raise ValueError("Only the inbound Twilio track is supported")
                    self._dispatch_event(
                        CapturedEvent(
                            audio=RawAudio.from_mulaw(
                                event.data,
                                self._INPUT_FORMAT,
                            ),
                            profile_id=profile_id,
                            driver_id="twilio",
                        )
                    )
                case MarkMessage():
                    playback_id = event.mark.name
                    if playback_id in self._pending_marks:
                        self._pending_marks.remove(playback_id)
                        self._dispatch_event(
                            PlaybackFinishedEvent(
                                driver_id="twilio",
                                playback_id=playback_id,
                            )
                        )
                case StopMessage():
                    if event.stop.call_sid != call_sid:
                        raise ValueError("Twilio stop CallSid mismatch")
                    return
                case _:
                    raise ValueError("Unexpected Twilio event after start")

    async def _output_loop(self, connection: TwilioConnection) -> None:
        next_frame_at = self._monotonic()
        while True:
            await self._output_ready.wait()
            async with self._mixer_lock:
                frame = self._mixer.next_frame()
            if frame is None:
                self._output_ready.clear()
                next_frame_at = self._monotonic()
                continue

            delay = next_frame_at - self._monotonic()
            if delay > 0:
                await self._sleep(delay)
            if not await connection.send(MediaCommand.create(frame.data)):
                return
            for playback_id in frame.completed_playbacks:
                self._pending_marks.add(playback_id)
                if not await connection.send(MarkCommand.create(playback_id)):
                    return
            next_frame_at = max(next_frame_at + self._FRAME_DURATION, self._monotonic())
            async with self._mixer_lock:
                if not self._mixer.has_output:
                    self._output_ready.clear()

    def _websocket_url(self, profile_id: str, call_sid: str, deadline: int) -> str:
        signature = self._sign_session(profile_id, call_sid, deadline)
        base_url = re.sub(r"^http", "ws", str(self._settings.public_url))
        if not base_url.endswith("/"):
            base_url += "/"
        return f"{base_url}{profile_id}/{call_sid}/{deadline}/{signature}"

    def _sign_session(self, profile_id: str, call_sid: str, deadline: int) -> str:
        payload = f"{profile_id}:{call_sid}:{deadline}".encode()
        return hmac.new(self._secret, payload, hashlib.sha256).hexdigest()

    def _discard_expired_reservation(self) -> None:
        if self._reservation is not None and self._reservation.deadline < int(
            self._wall_clock()
        ):
            self._reservation = None

    def _public_request_url(self, request: Request) -> str:
        # Twilio signs the externally visible URL, not the proxy's internal URL.
        proto = self._first_header(request, "x-forwarded-proto")
        host = self._first_header(request, "x-forwarded-host")
        if proto and host:
            prefix = self._first_header(request, "x-forwarded-prefix") or ""
            path = f"{prefix.rstrip('/')}{request.url.path}"
            url = f"{proto}://{host}{path}"
            if request.url.query:
                url += f"?{request.url.query}"
            return url
        return str(request.url)

    @staticmethod
    def _first_header(request: Request, name: str) -> str | None:
        value = request.headers.get(name)
        return value.split(",", 1)[0].strip() if value else None
