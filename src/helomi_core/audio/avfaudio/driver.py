import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar

from ..domain import AudioMode, RawAudio
from ..ports import AudioDriver
from .config import AVFAudioConfig
from .protocol import (
    AudioDevicesPacket,
    AudioPacked,
    AudioStartedPacked,
    ErrorPacket,
    HandshakePacked,
    MessageKind,
    PackedMessage,
    StartAudioRequest,
    WireFrame,
)


class AVFAudioDriver(AudioDriver[AVFAudioConfig]):
    _PROC_PATH: ClassVar[Path] = Path(__file__).resolve().parent / "bin" / "avfaudio"
    _PROC_TIMEOUT: ClassVar[float] = 3.0
    _PROC_ROOM_VOICE_ARG: ClassVar[str] = "--room-voice"

    def __init__(self, config, mode) -> None:
        super().__init__(config, mode)

        self._proc: asyncio.subprocess.Process | None = None
        self._proc_task: asyncio.Task | None = None

        self._pending_requests: dict[int, asyncio.Future[Any]] = {}
        self._playback_counter = 0
        self._capture_queues: set[asyncio.Queue[RawAudio | None]] = set()
        self._ready_signal = asyncio.Event()

    async def capture(self) -> AsyncIterator[RawAudio]:
        self._require_ready(AudioMode.INPUT)

        queue = asyncio.Queue[RawAudio | None]()
        self._capture_queues.add(queue)
        try:
            while not self._exit_signal.is_set():
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
                queue.task_done()
        finally:
            self._capture_queues.discard(queue)

    def play(self, audio: RawAudio) -> None:
        self._require_ready(AudioMode.OUTPUT)
        self._playback_counter += 1
        self._send(MessageKind.PLAY, AudioPacked.encode(audio))

    async def interrupt(self) -> bool:
        self._require_ready(AudioMode.DUPLEX)
        if self._playback_counter > 0:
            await self._send_wait(MessageKind.STOP_PLAYBACK)
            return True
        return False

    async def start_room_voice(self):
        self._require_ready(AudioMode.OUTPUT)
        if self._config.room_voice_path:
            await self._send_wait(MessageKind.START_ROOM_VOICE)

    async def stop_room_voice(self):
        self._require_ready(AudioMode.OUTPUT)
        if self._config.room_voice_path:
            await self._send_wait(MessageKind.STOP_ROOM_VOICE)

    def _send(self, kind: MessageKind, msg: PackedMessage | None = None) -> bool:
        proc = self._require_proc()
        return WireFrame.pack(kind, msg).write_to(proc.stdin)

    async def _send_wait[R](
        self,
        kind: MessageKind,
        msg: PackedMessage | None = None,
    ) -> R:
        proc = self._require_proc()
        frame = WireFrame.pack(kind, msg)
        try:
            request = asyncio.Future[Any]()
            self._pending_requests[frame.request_id] = request

            if not frame.write_to(proc.stdin):
                raise RuntimeError("Failed to write frame to AVFAudio process")

            return await asyncio.wait_for(request, timeout=self._PROC_TIMEOUT)
        finally:
            self._pending_requests.pop(frame.request_id, None)

    async def _do_open(self) -> None:
        if self._proc is not None:
            return

        cfg = self._config

        proc_path = str(self._PROC_PATH)
        proc_args: list[str] = []

        if cfg.room_voice_path:
            proc_args.append(self._PROC_ROOM_VOICE_ARG)
            proc_args.append(str(cfg.room_voice_path))

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
        await self._send_wait(
            MessageKind.START_AUDIO,
            StartAudioRequest(
                mode=self._mode,
            ),
        )

    async def _do_close(self) -> None:
        for queue in self._capture_queues:
            queue.put_nowait(None)

        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()

        self._pending_requests.clear()
        self._capture_queues.clear()

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

                case MessageKind.DEVICES:
                    result = frame.unpack_msg(AudioDevicesPacket)

                case MessageKind.CAPTURE:
                    if not self._capture_queues:
                        continue
                    raw = frame.unpack_msg(AudioPacked).decode()
                    for sub in self._capture_queues:
                        sub.put_nowait(raw)

                case MessageKind.AUDIO_STARTED:
                    result = frame.unpack_msg(AudioStartedPacked)

                case (
                    MessageKind.ROOM_VOICE_START_RESULT
                    | MessageKind.ROOM_VOICE_STOP_RESULT
                ):
                    pass

                case MessageKind.PLAYBACK_FINISHED:
                    self._playback_counter = (
                        self._playback_counter > 0 and self._playback_counter - 1
                    ) or 0

                case MessageKind.PLAYBACK_STOPPED:
                    self._playback_counter = 0

                case MessageKind.ERROR:
                    self._logger.warning(frame.unpack_msg(ErrorPacket))
                    if not self._ready_signal.is_set():
                        return

                case _:
                    self._logger.trace("Unhandled frame kind: {}", frame.kind.name)

            self._resolve_request(frame.request_id, result)

    def _resolve_request(self, request_id, result: Any) -> None:
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id, None)
            if not future:
                return
            future.set_result(result)

    def _require_ready(self, mode: AudioMode) -> None:
        if not self._ready_signal.is_set():
            raise RuntimeError("AVFAudio process is not ready")
        self._mode.verify(mode)

    def _require_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:
            raise RuntimeError("AVFAudio process is not running")
        return self._proc
