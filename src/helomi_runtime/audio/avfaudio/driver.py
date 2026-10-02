import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, Literal

from helomi_foundation import on_mount, on_unmount

from ..domain import AudioDriverCapabilities, AudioDriverDescriptor, AudioDriverKind
from ..messages import (
    AudioCommand,
    AudioEvent,
    CapturedEvent,
    DisconnectCommand,
    InterruptCommand,
    PlaybackFinishedEvent,
    PlayCommand,
    StartRoomVoiceCommand,
    StopRoomVoiceCommand,
)
from ..ports import AudioDriver
from .config import AVFAudioProfile, AVFAudioSettings
from .protocol import (
    AudioMode,
    AudioPacket,
    AudioStartedPacket,
    ErrorPacket,
    HandshakePayload,
    MessageKind,
    StartAudioRequest,
    StartRoomVoiceRequest,
    WireFrame,
    WirePayload,
)


class AVFAudioDriver(AudioDriver[AVFAudioSettings, AVFAudioProfile]):
    _PROC_PATH: ClassVar[Path] = Path(__file__).resolve().parent / "bin" / "avfaudio"
    _PROC_TIMEOUT: ClassVar[float] = 3.0
    _DESCRIPTOR: ClassVar[AudioDriverDescriptor] = AudioDriverDescriptor(
        id="avfaudio",
        name="Mac audio",
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

    def __init__(self, settings, profiles):
        super().__init__(settings, profiles)

        self._proc: asyncio.subprocess.Process | None = None
        self._proc_task: asyncio.Task | None = None

        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._playback_requests: dict[int, str | None] = {}

        self._room_voice_started = False
        self._ready_signal = asyncio.Event()
        self._lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def descriptor(self) -> AudioDriverDescriptor:
        return self._DESCRIPTOR

    @property
    def _pending_playbacks(self) -> int:
        return len(self._playback_requests)

    async def execute_command(self, cmd: AudioCommand) -> bool:
        self._require_ready()

        match cmd:
            case PlayCommand():
                frame = WireFrame.pack(MessageKind.PLAY, AudioPacket.encode(cmd.audio))
                async with self._lock:
                    self._playback_requests[frame.request_id] = cmd.playback_id
                try:
                    await self._write_frame(frame)
                except BaseException:
                    await self._finish_playback(frame.request_id, "failed")
                    raise

            case InterruptCommand():
                async with self._lock:
                    if not self._pending_playbacks:
                        return False

                    interrupted = tuple(self._playback_requests)
                await self._send(MessageKind.STOP_PLAYBACK)
                for request_id in interrupted:
                    await self._finish_playback(request_id, "interrupted")

            case StartRoomVoiceCommand():
                room_voice_path = (
                    profile.room_voice.path
                    if (profile := self._profiles.get(cmd.profile_id, None))
                    and profile.room_voice is not None
                    else None
                )

                async with self._lock:
                    if room_voice_path is None and not self._room_voice_started:
                        return False
                    self._room_voice_started = room_voice_path is not None

                    if not room_voice_path:
                        await self._send(MessageKind.STOP_ROOM_VOICE)
                    else:
                        await self._send(
                            MessageKind.START_ROOM_VOICE,
                            StartRoomVoiceRequest(path=str(room_voice_path)),
                        )

            case StopRoomVoiceCommand():
                async with self._lock:
                    if not self._room_voice_started:
                        return False
                    self._room_voice_started = False
                await self._send(MessageKind.STOP_ROOM_VOICE)

            case DisconnectCommand():
                async with self._lock:
                    if not self._room_voice_started:
                        return True
                    self._room_voice_started = False
                await self._send(MessageKind.STOP_ROOM_VOICE)

        return True

    def subscribe_events(self) -> AsyncIterator[AudioEvent]:
        self._require_ready()
        return super().subscribe_events()

    async def _write_frame(self, frame: WireFrame) -> None:
        proc = self._require_proc()
        async with self._write_lock:
            frame.write_to(proc.stdin)
            if proc.stdin is not None:
                await proc.stdin.drain()

    async def _send(self, kind: MessageKind, msg: WirePayload | None = None) -> int:
        frame = WireFrame.pack(kind, msg)
        await self._write_frame(frame)
        return frame.request_id

    async def _finish_playback(
        self,
        request_id: int,
        status: Literal["played", "interrupted", "failed"],
    ) -> None:
        async with self._lock:
            playback_id = self._playback_requests.pop(request_id, None)
        if playback_id is not None:
            self._dispatch_event(
                PlaybackFinishedEvent(self.descriptor.id, playback_id, status)
            )

    async def _send_wait[R](
        self,
        kind: MessageKind,
        msg: WirePayload | None = None,
    ) -> R:
        frame = WireFrame.pack(kind, msg)
        try:
            future = asyncio.Future[Any]()
            self._pending_requests[frame.request_id] = future
            await self._write_frame(frame)
            return await asyncio.wait_for(future, timeout=self._PROC_TIMEOUT)
        finally:
            self._pending_requests.pop(frame.request_id, None)

    @on_mount()
    async def _start_process(self):
        if self._proc is not None:
            return

        proc_path = str(self._PROC_PATH)
        proc_args: list[str] = []

        self._proc = await asyncio.create_subprocess_exec(
            proc_path,
            *proc_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._proc_task = asyncio.create_task(self._proc_loop())

        await asyncio.wait_for(self._ready_signal.wait(), timeout=self._PROC_TIMEOUT)

    @on_mount(order=10)
    async def _start_audio(self):
        settings = self._settings

        await self._send_wait(
            MessageKind.START_AUDIO,
            StartAudioRequest(
                mode=AudioMode.DUPLEX,
                voice_processing=settings.voice_processing,
            ),
        )

    @on_unmount(order=10)
    async def _cancel_pending_requests(self):
        for future in self._pending_requests.values():
            if isinstance(future, asyncio.Future) and not future.done():
                future.cancel()
        self._pending_requests.clear()
        for request_id in tuple(self._playback_requests):
            await self._finish_playback(request_id, "interrupted")

    @on_unmount()
    async def _stop_process(self):
        proc, proc_task, self._proc, self._proc_task = (
            self._proc,
            self._proc_task,
            None,
            None,
        )
        if proc is None:
            return
        self._ready_signal.clear()

        if proc_task is not None:
            self._exit_signal.set()
            try:
                proc_task.cancel()
                with suppress(asyncio.CancelledError):
                    await proc_task
            finally:
                self._exit_signal.clear()

        if proc.returncode is not None:
            return

        try:
            await asyncio.wait_for(proc.wait(), timeout=self._PROC_TIMEOUT)
        except TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=self._PROC_TIMEOUT)
            except TimeoutError:
                proc.kill()
                await proc.wait()

    async def _proc_loop(self):
        proc = self._require_proc()

        try:
            while not self._exit_signal.is_set():
                frame = await WireFrame.read_from(proc.stdout)
                if frame is None:
                    break

                result: Any = None

                match frame.kind:
                    case MessageKind.READY:
                        frame.unpack_payload(HandshakePayload).verify()
                        self._ready_signal.set()

                    case MessageKind.CAPTURE:
                        audio = frame.unpack_payload(AudioPacket).decode()

                        self._dispatch_event(
                            CapturedEvent(
                                audio=audio,
                            ),
                        )

                    case MessageKind.AUDIO_STARTED:
                        result = frame.unpack_payload(AudioStartedPacket)

                    case MessageKind.PLAYBACK_FINISHED:
                        if frame.payload not in {b"\x00", b"\x01"}:
                            raise RuntimeError("Invalid AVFAudio playback status")
                        status = "played" if frame.payload == b"\x00" else "interrupted"
                        await self._finish_playback(frame.request_id, status)

                    case (
                        MessageKind.PLAYBACK_STOPPED
                        | MessageKind.ROOM_VOICE_START_RESULT
                        | MessageKind.ROOM_VOICE_STOP_RESULT
                    ):
                        pass

                    case MessageKind.ERROR:
                        error_packet = frame.unpack_payload(ErrorPacket)
                        self._logger.warning("{}", error_packet)
                        if not self._ready_signal.is_set():
                            return

                        result = RuntimeError(f"AVFAudio error: {error_packet.message}")
                        await self._finish_playback(frame.request_id, "failed")

                    case _:
                        self._logger.trace("{} frame skipped", frame.kind.name)

                if (
                    future := self._pending_requests.pop(frame.request_id, None)
                ) is not None and not future.done():
                    match result:
                        case Exception():
                            future.set_exception(result)
                        case _:
                            future.set_result(result)
        finally:
            self._ready_signal.clear()
            for request_id in tuple(self._playback_requests):
                await self._finish_playback(request_id, "failed")
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(RuntimeError("AVFAudio process stopped"))
            self._pending_requests.clear()

    def _require_ready(self):
        if not self._ready_signal.is_set():
            raise RuntimeError("AVFAudio process is not ready")

    def _require_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:
            raise RuntimeError("AVFAudio process is not running")
        return self._proc
