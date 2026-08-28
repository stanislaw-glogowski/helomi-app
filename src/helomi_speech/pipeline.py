import asyncio
from collections.abc import AsyncIterator

from helomi_common import AbstractAsyncComponent, TaskManager
from helomi_core import Profile, Runtime
from helomi_core.audio import AudioMode, RawAudio
from helomi_core.detection import (
    ConversationEnded,
    DetectionMode,
    ProfileDetected,
    UtteranceDetected,
)
from helomi_core.stt import STTRequest, STTResponse
from helomi_core.tts import TTSChunk, TTSRequest

from .domain import (
    ActivateProfile,
    DeactivateProfile,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    SpeechCmd,
    SpeechEvent,
    SpeechRequest,
    TranscriptionReady,
)


class SpeechPipeline(AbstractAsyncComponent):
    def __init__(self, runtime: Runtime) -> None:
        super().__init__()

        self._runtime = runtime
        self._tasks = TaskManager()
        self._audio_driver = runtime.get_audio_driver(AudioMode.DUPLEX)

        self._detection_worker = runtime.get_detection_worker()
        self._detection_queue: asyncio.Queue[RawAudio] = asyncio.Queue()

        self._stt_worker = runtime.get_stt_worker()
        self._stt_requests: asyncio.Queue[SpeechRequest[STTRequest]] = asyncio.Queue()

        self._tts_worker = runtime.get_tts_worker()
        self._tts_requests: asyncio.Queue[SpeechRequest[TTSRequest]] = asyncio.Queue()

        self._current_profile: Profile | None = None

        self._subscriptions: set[asyncio.Queue[SpeechEvent | None]] = set()

    @property
    def active_profile(self) -> Profile | None:
        return self._current_profile

    async def activate_profile(
        self,
        profile_id: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        profile = self._runtime.get_profile(profile_id)
        active_profile = self._current_profile

        if active_profile is not None:
            if active_profile.id == profile.id:
                return False

            self._send_event(
                ProfileDeactivated(
                    trace_id=trace_id,
                    profile_id=profile.id,
                )
            )

        self._current_profile = profile
        self._send_event(
            ProfileActivated(
                trace_id=trace_id,
                profile_id=profile.id,
            )
        )
        return True

    async def deactivate_profile(
        self,
        trace_id: str | None = None,
    ) -> bool:
        profile, self._current_profile = self._current_profile, None
        if profile is None:
            return False

        self._current_profile = None

        await self._detection_worker.change_mode(DetectionMode.PROFILE)

        self._send_event(
            ProfileDeactivated(
                trace_id=trace_id,
                profile_id=profile.id,
            )
        )
        return True

    async def say_text(
        self,
        text: str,
        profile_id: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        if profile_id is not None or self._current_profile is None:
            await self.activate_profile(profile_id, trace_id)

        if self._current_profile is None:
            return False

        self._tts_requests.put_nowait(
            SpeechRequest(
                trace_id=trace_id,
                profile_id=self._current_profile.id,
                data=TTSRequest(text=text),
            )
        )
        return True

    async def publish(self, cmd: SpeechCmd) -> bool:
        match cmd:
            case ActivateProfile():
                return await self.activate_profile(cmd.profile_id, cmd.trace_id)
            case DeactivateProfile():
                return await self.deactivate_profile(cmd.trace_id)
            case SayText():
                return await self.say_text(cmd.text, cmd.profile_id, cmd.trace_id)

        return False

    async def subscribe(self) -> AsyncIterator[SpeechEvent]:
        subscription: asyncio.Queue[SpeechEvent | None] = asyncio.Queue()

        self._subscriptions.add(subscription)

        try:
            while True:
                event = await subscription.get()
                try:
                    if event is None:
                        return

                    yield event
                finally:
                    subscription.task_done()
        finally:
            self._subscriptions.discard(subscription)

    async def _do_open(self) -> None:
        await self._exit_stack.enter_async_context(self._tasks)
        await self._exit_stack.enter_async_context(self._audio_driver)
        await self._exit_stack.enter_async_context(self._detection_worker)
        await self._exit_stack.enter_async_context(self._stt_worker)
        await self._exit_stack.enter_async_context(self._tts_worker)

        self._tasks.add_task(
            self._capture_loop(),
            self._detection_loop(),
            self._stt_loop(),
            self._tts_loop(),
        )

    async def _do_close(self) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(None)

        self._subscriptions.clear()

    async def _capture_loop(self) -> None:
        async for raw in self._audio_driver.capture():
            self._detection_queue.put_nowait(raw)

    async def _detection_loop(self) -> None:
        await self._audio_driver.start_room_voice()

        while True:
            audio = await self._detection_queue.get()

            try:
                async for result in self._detection_worker.detect(audio):
                    match result:
                        case ProfileDetected(profile_id):
                            self._current_profile = self._runtime.get_profile(
                                profile_id
                            )
                            self._send_event(
                                ProfileActivated(
                                    profile_id=profile_id,
                                ),
                            )
                        case UtteranceDetected(audio=audio):
                            if self._current_profile:
                                self._stt_requests.put_nowait(
                                    SpeechRequest(
                                        profile_id=self._current_profile.id,
                                        data=STTRequest(
                                            audio=audio,
                                        ),
                                    ),
                                )

                        case ConversationEnded():
                            if self._current_profile:
                                self._send_event(
                                    ProfileDeactivated(
                                        profile_id=self._current_profile.id,
                                    ),
                                )
                                self._current_profile = None
            finally:
                self._detection_queue.task_done()

    async def _stt_loop(self) -> None:
        while True:
            request = await self._stt_requests.get()

            try:
                if profile := request.verify_profile(self._current_profile):
                    async for response in self._stt_worker.transcribe(
                        request=request.data,
                        profile=profile.stt,
                    ):
                        if isinstance(response, STTResponse):
                            self._send_event(
                                TranscriptionReady(
                                    trace_id=request.trace_id,
                                    profile_id=profile.id,
                                    text=response.text,
                                )
                            )
            finally:
                self._stt_requests.task_done()

    async def _tts_loop(self) -> None:
        while True:
            request = await self._tts_requests.get()

            try:
                if profile := request.verify_profile(self._current_profile):
                    async for chunk in self._tts_worker.synthesize(
                        request=request.data,
                        profile=profile.tts,
                    ):
                        if isinstance(chunk, TTSChunk):
                            self._audio_driver.play(chunk.audio)

            finally:
                self._tts_requests.task_done()

    def _send_event(self, event: SpeechEvent) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(event)
