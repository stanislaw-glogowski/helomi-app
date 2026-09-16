import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar

from ..domain import AudioDriverKind
from ..messages import (
    AudioCmd,
    AudioEvent,
    CapturedEvent,
    DisconnectCmd,
    InterruptCmd,
    PlayCmd,
    StartRoomVoiceCmd,
    StopRoomVoiceCmd,
)
from ..ports import AudioDriver
from .config import AVFAudioProfile, AVFAudioSettings
from .protocol import (
    AudioMode,
    AudioPacked,
    AudioStartedPacked,
    ErrorPacket,
    HandshakePacked,
    MessageKind,
    PackedMessage,
    StartAudioRequest,
    StartRoomVoiceRequest,
    WireFrame,
)


class AVFAudioDriver(AudioDriver[AVFAudioSettings, AVFAudioProfile]):
    _PROC_PATH: ClassVar[Path] = Path(__file__).resolve().parent / "bin" / "avfaudio"
    _PROC_TIMEOUT: ClassVar[float] = 3.0

    def __init__(self, settings, profiles) -> None:
        super().__init__(settings, profiles)

        self._proc: asyncio.subprocess.Process | None = None
        self._proc_task: asyncio.Task | None = None

        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._pending_playbacks = 0

        self._room_voice_started = False
        self._ready_signal = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def kind(self) -> AudioDriverKind:
        return AudioDriverKind.LOCAL

    @property
    def room_voice_supported(self) -> bool:
        return True

    async def execute_command(self, cmd: AudioCmd) -> bool:
        self._require_ready()

        match cmd:
            case PlayCmd():
                async with self._lock:
                    self._pending_playbacks += 1
                self._send(MessageKind.PLAY, AudioPacked.encode(cmd.audio))

            case InterruptCmd():
                async with self._lock:
                    if not self._pending_playbacks:
                        return False

                    self._pending_playbacks = 0
                self._send(MessageKind.STOP_PLAYBACK)

            case StartRoomVoiceCmd():
                room_voice_path = (
                    profile.room_voice_path
                    if (profile := self._profiles.get(cmd.profile_id, None))
                    else None
                )

                async with self._lock:
                    if room_voice_path is None and not self._room_voice_started:
                        return False
                    self._room_voice_started = room_voice_path is not None

                    if not room_voice_path:
                        self._send(MessageKind.STOP_ROOM_VOICE)
                    else:
                        self._send(
                            MessageKind.START_ROOM_VOICE,
                            StartRoomVoiceRequest(path=str(room_voice_path)),
                        )

            case StopRoomVoiceCmd():
                async with self._lock:
                    if not self._room_voice_started:
                        return False
                    self._room_voice_started = False
                self._send(MessageKind.STOP_ROOM_VOICE)

            case DisconnectCmd():
                async with self._lock:
                    if not self._room_voice_started:
                        return True
                    self._room_voice_started = False
                self._send(MessageKind.STOP_ROOM_VOICE)

        return True

    def subscribe_event(self) -> AsyncIterator[AudioEvent]:
        self._require_ready()
        return super().subscribe_event()

    def _send(self, kind: MessageKind, msg: PackedMessage | None = None) -> int:
        proc = self._require_proc()
        frame = WireFrame.pack(kind, msg)
        frame.write_to(proc.stdin)
        return frame.request_id

    async def _send_wait[R](
        self,
        kind: MessageKind,
        msg: PackedMessage | None = None,
    ) -> R:
        proc = self._require_proc()
        frame = WireFrame.pack(kind, msg)
        try:
            future = asyncio.Future[Any]()
            self._pending_requests[frame.request_id] = future
            frame.write_to(proc.stdin)
            return await asyncio.wait_for(future, timeout=self._PROC_TIMEOUT)
        finally:
            self._pending_requests.pop(frame.request_id, None)

    async def _do_open(self) -> None:
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

    async def _post_open(self) -> None:
        cfg = self._settings

        await self._send_wait(
            MessageKind.START_AUDIO,
            StartAudioRequest(
                mode=AudioMode.DUPLEX,
                voice_processing=cfg.voice_processing,
            ),
        )

    async def _do_close(self) -> None:
        for future in self._pending_requests.values():
            if isinstance(future, asyncio.Future) and not future.done():
                future.cancel()
        self._pending_requests.clear()

    async def _post_close(self) -> None:
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

    async def _proc_loop(self) -> None:
        proc = self._require_proc()

        while not self._exit_signal.is_set():
            frame = await WireFrame.read_from(proc.stdout)
            if frame is None:
                break

            result: Any = None

            match frame.kind:
                case MessageKind.READY:
                    frame.unpack_msg(HandshakePacked).verify()
                    self._ready_signal.set()

                case MessageKind.CAPTURE:
                    audio = frame.unpack_msg(AudioPacked).decode()

                    self._dispatch_event(
                        CapturedEvent(
                            audio=audio,
                        ),
                    )

                case MessageKind.AUDIO_STARTED:
                    result = frame.unpack_msg(AudioStartedPacked)

                case MessageKind.PLAYBACK_FINISHED:
                    async with self._lock:
                        self._pending_playbacks = (
                            self._pending_playbacks > 0 and self._pending_playbacks - 1
                        ) or 0

                case (
                    MessageKind.PLAYBACK_STOPPED
                    | MessageKind.ROOM_VOICE_START_RESULT
                    | MessageKind.ROOM_VOICE_STOP_RESULT
                ):
                    pass

                case MessageKind.ERROR:
                    error_packet = frame.unpack_msg(ErrorPacket)
                    self._logger.warning(error_packet)
                    if not self._ready_signal.is_set():
                        return

                    result = RuntimeError(f"AVFAudio error: {error_packet.message}")

                case _:
                    self._logger.trace("{} frame skipped", frame.kind.name)

            if (
                future := self._pending_requests.pop(frame.request_id, None)
            ) is not None:
                match result:
                    case Exception():
                        future.set_exception(result)
                    case _:
                        future.set_result(result)

    def _require_ready(self) -> None:
        if not self._ready_signal.is_set():
            raise RuntimeError("AVFAudio process is not ready")

    def _require_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:
            raise RuntimeError("AVFAudio process is not running")
        return self._proc
