import asyncio
import base64
import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Callable
from typing import ClassVar

from fastapi import (
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from ...domain import AudioFormat, RawAudio
from ...messages import AudioEvent, CapturedEvent, DisconnectedEvent
from ...resampler import AudioResampler
from ..config import TwilioProfile, TwilioSettings
from .messages import (
    EventParser,
    MediaCmd,
    MediaEvent,
    StartEvent,
    StopEvent,
)


class Bridge:
    _OUTPUT_FORMAT: ClassVar[AudioFormat] = AudioFormat.MONO_8

    def __init__(
        self,
        settings: TwilioSettings,
        profiles: dict[str, TwilioProfile],
        dispatch_event: Callable[[AudioEvent], None],
    ) -> None:
        loop = asyncio.get_running_loop()

        self._settings = settings
        self._profiles = {
            profile.callee: profile_id for profile_id, profile in profiles.items()
        }

        def _dispatch_event(event: AudioEvent) -> None:
            loop.call_soon_threadsafe(dispatch_event, event)

        self._dispatch_event = _dispatch_event
        self._active_websocket: WebSocket | None = None
        self._active_profile: str | None = None
        self._active_sid: str | None = None
        self._active_signal = asyncio.Event()

        self._resamples = AudioResampler(self._OUTPUT_FORMAT)
        self._secret = secrets.token_hex(32).encode()
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._send_abort = asyncio.Event()

    @property
    def is_sending_audio(self) -> bool:
        return self._send_lock.locked()

    async def connect_profile(
        self,
        profile_id: str,
        websocket: WebSocket,
    ) -> None:
        if self._active_websocket:
            return

        async with self._connect_lock:
            self._active_websocket = websocket
            self._active_profile = profile_id

        try:
            while True:
                text = await websocket.receive_text()
                match event := EventParser.validate_json(text):
                    case StartEvent():
                        self._active_sid = event.stream_sid

                    case StopEvent():
                        self._dispatch_event(
                            DisconnectedEvent(),
                        )
                        break

                    case MediaEvent():
                        self._dispatch_event(
                            CapturedEvent(
                                audio=RawAudio.from_mulan(
                                    format=self._OUTPUT_FORMAT,
                                    data=event.data,
                                ),
                                profile_id=profile_id,
                            )
                        )

        except WebSocketDisconnect:
            pass

        self._resamples.reset()

        async with self._connect_lock:
            self._active_websocket = None
            self._active_profile = None
            self._active_sid = None

    async def disconnect_profile(self) -> bool:
        if self._active_websocket is None:
            return False

        await self._active_websocket.close()
        return True

    async def send_audio(self, raw: RawAudio, is_final: bool) -> bool:
        async with self._send_lock:
            if (
                self._active_websocket is None
                or self._active_sid is None
                or self._active_profile is None
            ):
                return False

            for chunk in self._resamples.resample(raw):
                if self._send_abort.is_set():
                    break

                media = MediaCmd.create(
                    stream_sid=self._active_sid,
                    data=chunk.to_mulaw(),
                )
                text = media.model_dump_json(by_alias=True)
                await self._active_websocket.send_text(text)

            self._send_abort.clear()

            if is_final:
                await self._active_websocket.close()

        return True

    async def abort_sending_audio(self) -> bool:
        if not self._send_lock.locked():
            return False

        self._send_abort.set()
        return True

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
