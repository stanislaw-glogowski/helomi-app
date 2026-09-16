import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from fastapi import (
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from helomi_app.common import EpochEnvelope, TaskManager

from ..domain import AudioFormat, RawAudio
from ..messages import (
    AudioCmd,
    AudioEvent,
    CapturedEvent,
    DisconnectCmd,
    DisconnectedEvent,
    InterruptCmd,
    PlayCmd,
)
from ..resampler import AudioResampler
from .config import TwilioProfile, TwilioSettings
from .protocol import (
    ClearCmd,
    MediaCmd,
    MediaEvent,
    StartEvent,
    StopEvent,
    TwilioCmd,
    TwilioEvent,
)


@dataclass(frozen=True, slots=True)
class MediaRequest(EpochEnvelope):
    data: bytes
    epoch: int


class TwilioConnection:
    def __init__(self, websocket: WebSocket) -> None:
        self._websocket: WebSocket | None = websocket
        self._sid: str | None = None
        self._lock = asyncio.Lock()

    def set_sid(self, sid: str):
        self._sid = sid

    async def send(self, cmd: TwilioCmd) -> bool:
        async with self._lock:
            if self._websocket is None or self._sid is None:
                return False

            cmd.stream_sid = self._sid
            data = cmd.model_dump_json(by_alias=True)
            await self._websocket.send_text(data)
        return True

    async def close(self) -> bool:
        async with self._lock:
            if self._websocket is None:
                return False
            websocket, self._websocket = self._websocket, None
            await websocket.close()
            return True


class TwilioBridge:
    _OUTPUT_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_8

    def __init__(
        self,
        settings: TwilioSettings,
        profiles: dict[str, TwilioProfile],
        dispatch_event: Callable[[AudioEvent], None],
    ) -> None:
        loop = asyncio.get_running_loop()

        def _dispatch_event(event: AudioEvent) -> None:
            loop.call_soon_threadsafe(
                dispatch_event,
                event,
            )

        self._dispatch_event = _dispatch_event

        self._settings = settings
        self._profiles = {
            profile.callee: profile_id for profile_id, profile in profiles.items()
        }
        self._secret = secrets.token_hex(32).encode()
        self._resamples = AudioResampler(self._OUTPUT_FORMAT)

        self._connection: TwilioConnection | None = None
        self._media_requests: asyncio.Queue[MediaRequest] = asyncio.Queue()
        self._media_epoch = 0
        self._lock = asyncio.Lock()

    @property
    def is_sending(self) -> bool:
        return True

    async def connect(
        self,
        profile_id: str,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            if self._connection is not None:
                return
            connection = TwilioConnection(websocket)
            self._connection = connection

        exit_signal = asyncio.Event()

        async def _receive_loop():
            try:
                while True:
                    text = await websocket.receive_text()
                    match event := TwilioEvent.validate_json(text):
                        case StartEvent():
                            connection.set_sid(event.stream_sid)

                        case StopEvent():
                            self._dispatch_event(
                                DisconnectedEvent(),
                            )
                            break

                        case MediaEvent():
                            self._dispatch_event(
                                CapturedEvent(
                                    audio=RawAudio.from_mulaw(
                                        format=self._OUTPUT_FORMAT,
                                        data=event.data,
                                    ),
                                    profile_id=profile_id,
                                )
                            )
            except WebSocketDisconnect:
                pass
            exit_signal.set()

        async def _media_loop():
            while True:
                request = await self._media_requests.get()
                try:
                    if not request.is_valid:
                        continue
                    await connection.send(
                        MediaCmd.create(
                            data=request.data,
                        )
                    )
                finally:
                    self._media_requests.task_done()

        async with TaskManager() as tasks:
            tasks.add_task(_receive_loop())
            tasks.add_task(_media_loop())

            await exit_signal.wait()

        self._resamples.reset()

        async with self._lock:
            self._connection = None

    async def execute_command(self, cmd: AudioCmd) -> bool:
        async with self._lock:
            if self._connection is None:
                return False
            connection = self._connection

        match cmd:
            case PlayCmd(audio=raw):
                epoch = MediaRequest.current_epoch()
                self._media_epoch = epoch

                for chunk in self._resamples.resample(raw):
                    self._media_requests.put_nowait(
                        MediaRequest(
                            epoch=epoch,
                            data=chunk.to_mulaw(),
                        )
                    )
                return True

            case InterruptCmd():
                self._media_epoch = MediaRequest.bump()
                await connection.send(ClearCmd(stream_sid=""))
                return True

            case DisconnectCmd():
                return await connection.close()

        return False

    def get_websocket_url(self, profile_id: str, call_sid: str) -> str:
        deadline = int(time.time()) + self._settings.handshake_timeout
        sig = self._sign_session(profile_id, call_sid, deadline)

        url = re.sub(r"^http", "ws", str(self._settings.public_url))
        url += profile_id
        url += f"/{call_sid}"
        url += f"/{deadline}"
        url += f"/{sig}"

        return url

    def is_request_valid(self, request: Request, params: dict) -> bool:
        if self._settings.disable_signature_validation:
            return True

        signature = request.headers.get("x-twilio-signature", "")

        if not signature:
            return False

        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)

        data = f"{proto}://{host}{request.url.path}"
        data += "".join(f"{key}{params[key]}" for key in sorted(params.keys()))

        mac = hmac.new(
            self._settings.auth_token.encode(),
            data.encode(),
            hashlib.sha1,
        ).digest()

        return hmac.compare_digest(
            base64.b64encode(mac).decode(),
            signature,
        )

    def is_signature_valid(
        self,
        profile_id: str,
        call_sid: str,
        deadline: int | str,
        sig: str,
    ) -> bool:
        return hmac.compare_digest(
            self._sign_session(profile_id, call_sid, deadline),
            sig,
        )

    def is_caller_allowed(self, caller: str) -> bool:
        if (callers := self._settings.allowed_callers) is None:
            return True

        return caller in callers

    def get_profile_id(self, callee: str) -> str | None:
        return self._profiles.get(callee, None)

    def _sign_session(self, profile_id: str, call_sid: str, deadline: int | str) -> str:
        payload = f"{profile_id}:{call_sid}:{deadline}"
        return hashlib.blake2b(
            payload.encode(),
            key=self._secret,
            digest_size=16,
        ).hexdigest()
