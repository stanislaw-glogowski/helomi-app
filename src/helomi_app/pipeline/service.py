import asyncio
from asyncio import Queue
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from helomi_core.audio import AudioDriver, RawAudio
from helomi_core.detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
    UtteranceDetected,
)
from helomi_core.stt import STTRequest, STTResponse, STTWorker
from helomi_core.tts import TTSChunk, TTSRequest, TTSWorker

from .component import PipelineComponent
from .domain import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    PipelineEvent,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    TranscriptionReady,
)

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog


@dataclass(frozen=True, slots=True)
class _Request[TData]:
    profile_id: str
    data: TData
    trace_id: str | None = None


class PipelineService(PipelineComponent):
    def __init__(
        self,
        profiles: ProfileCatalog,
        audio_driver: AudioDriver,
        detection_worker: DetectionWorker,
        stt_worker: STTWorker,
        tts_worker: TTSWorker,
    ) -> None:
        super().__init__()

        self._audio_driver = audio_driver

        self._detection_worker = detection_worker
        self._detection_queue: Queue[RawAudio] = Queue()

        self._stt_worker = stt_worker
        self._stt_queue: Queue[_Request[STTRequest]] = Queue()

        self._tts_worker = tts_worker
        self._tts_queue: Queue[_Request[TTSRequest]] = Queue()

        self._profiles = profiles
        self._active_profile: Profile | None = None
        self._subscriptions: set[Queue[PipelineEvent | None]] = set()
        self._lock = asyncio.Lock()

    @property
    def profiles(self) -> ProfileCatalog:
        return self._profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._active_profile

    async def execute(self, cmd: PipelineCmd) -> bool:
        async with self._lock:
            match cmd:
                case ActivateProfile():
                    return await self._handle_activate_profile(cmd)
                case DeactivateProfile():
                    return await self._handle_deactivate_profile(cmd)
                case SayText():
                    return await self._handle_say_text(cmd)

    async def subscribe(
        self,
        is_enabled: asyncio.Event | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        subscription = Queue[PipelineEvent | None]()

        self._subscriptions.add(subscription)

        try:
            while True:
                event = await subscription.get()
                subscription.task_done()
                if event is None:
                    return
                if is_enabled is None or is_enabled.is_set():
                    yield event
        finally:
            self._subscriptions.discard(subscription)

    async def _do_open(self) -> None:
        self._tasks.add_task(
            self._capture_loop(),
            self._detection_loop(),
            self._stt_loop(),
            self._tts_loop(),
        )

    async def _do_close(self) -> None:
        await self._audio_driver.stop_room_voice()
        for subscription in self._subscriptions:
            subscription.put_nowait(None)
        self._subscriptions.clear()

    async def _capture_loop(self) -> None:
        async for raw in self._audio_driver.capture():
            self._detection_queue.put_nowait(raw)

    async def _detection_loop(self) -> None:
        while True:
            audio = await self._detection_queue.get()

            try:
                async for res in self._detection_worker.detect(audio):
                    match res:
                        case ProfileDetected():
                            await self.execute(
                                ActivateProfile(profile_id=res.profile_id),
                            )

                        case UtteranceDetected():
                            profile = self._active_profile

                            if profile is None:
                                continue

                            self._stt_queue.put_nowait(
                                _Request(
                                    profile_id=profile.id,
                                    data=STTRequest(
                                        audio=res.audio,
                                    ),
                                ),
                            )

                        case ConversationEnded():
                            await self.execute(
                                DeactivateProfile(),
                            )

            finally:
                self._detection_queue.task_done()

    async def _stt_loop(self) -> None:
        while True:
            request = await self._stt_queue.get()
            profile = self._active_profile

            if profile is None or profile.id != request.profile_id:
                continue

            try:
                async for response in self._stt_worker.transcribe(
                    request=request.data,
                    profile=profile.stt,
                ):
                    if isinstance(response, STTResponse):
                        self._dispatch(
                            TranscriptionReady(
                                trace_id=request.trace_id,
                                profile_id=profile.id,
                                text=response.text,
                            )
                        )
            finally:
                self._stt_queue.task_done()

    async def _tts_loop(self) -> None:
        while True:
            request = await self._tts_queue.get()
            profile = self._active_profile

            if profile is None or profile.id != request.profile_id:
                continue

            try:
                async for chunk in self._tts_worker.synthesize(
                    request=request.data,
                    profile=profile.tts,
                ):
                    if isinstance(chunk, TTSChunk):
                        self._audio_driver.play(chunk.audio)

            finally:
                self._tts_queue.task_done()

    async def _handle_activate_profile(self, cmd: ActivateProfile) -> bool:
        profile = self._profiles.get(cmd.profile_id)

        if self._active_profile is profile:
            return False

        if self._active_profile is None:
            await self._audio_driver.start_room_voice()
            await self._detection_worker.change_mode(DetectionMode.UTTERANCE)
        else:
            self._dispatch(
                ProfileDeactivated(
                    profile_id=self._active_profile.id,
                    trace_id=cmd.trace_id,
                )
            )

        self._active_profile = profile
        self._dispatch(
            ProfileActivated(
                profile_id=profile.id,
                trace_id=cmd.trace_id,
            )
        )
        return True

    async def _handle_deactivate_profile(self, cmd: DeactivateProfile) -> bool:
        profile, self._active_profile = self._active_profile, None
        if profile is None:
            return False

        await self._audio_driver.stop_room_voice()
        await self._detection_worker.change_mode(DetectionMode.PROFILE)

        self._active_profile = None
        self._dispatch(
            ProfileDeactivated(
                profile_id=profile.id,
                trace_id=cmd.trace_id,
            )
        )

        return True

    async def _handle_say_text(self, cmd: SayText) -> bool:
        match self._active_profile:
            case None:
                await self._handle_activate_profile(
                    ActivateProfile(
                        profile_id=cmd.profile_id,
                        trace_id=cmd.trace_id,
                    ),
                )
            case profile if cmd.profile_id is not None and profile.id != cmd.profile_id:
                return False

        if self._active_profile is None:
            return False

        self._tts_queue.put_nowait(
            _Request(
                profile_id=self._active_profile.id,
                data=TTSRequest(text=cmd.text),
                trace_id=cmd.trace_id,
            )
        )

        return True

    def _dispatch(
        self,
        event: PipelineEvent,
    ) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(event)
