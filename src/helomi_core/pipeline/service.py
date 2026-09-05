import asyncio
from asyncio import Queue
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from ..audio import AudioDriver, RawAudio
from ..detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
    UtteranceDetected,
)
from ..stt import STTRequest, STTResponse, STTWorker
from ..tts import TTSChunk, TTSRequest, TTSWorker
from .component import PipelineComponent
from .domain import (
    ActivateProfile,
    DeactivateProfile,
    PipelineCmd,
    PipelineEvent,
    ProfileActivated,
    ProfileDeactivated,
    SayText,
    SpeechInterrupted,
    TranscriptionReady,
)
from .extension import PipelineExtension, PipelineExtensionKey

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog


@dataclass(frozen=True, slots=True)
class PipelineRequest[TData]:
    _current_generation: ClassVar[int] = 0

    @classmethod
    def current_generation(cls) -> int:
        return cls._current_generation

    @classmethod
    def bump_generation(cls) -> None:
        cls._current_generation += 1

    data: TData
    trace_id: str | None = None
    generation: int = field(
        default_factory=lambda: PipelineRequest.current_generation(),
    )

    @property
    def is_valid(self) -> bool:
        return self.generation == PipelineRequest.current_generation()


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
        self._stt_queue: Queue[PipelineRequest[STTRequest]] = Queue()

        self._tts_worker = tts_worker
        self._tts_queue: Queue[PipelineRequest[TTSRequest]] = Queue()

        self._playback_queue: Queue[PipelineRequest[RawAudio]] = Queue()

        self._profiles = profiles
        self._extensions: dict[PipelineExtensionKey, PipelineExtension] = {}

        self._active_profile: Profile | None = None
        self._active_extension: PipelineExtensionKey | None = None

        self._event_subscriptions: set[Queue[PipelineEvent | None]] = set()
        self._lock = asyncio.Lock()

    @property
    def profiles(self) -> ProfileCatalog:
        return self._profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._active_profile

    @property
    def active_extension(self) -> PipelineExtensionKey | None:
        return self._active_extension

    async def set_active_extension(self, key: PipelineExtensionKey) -> bool:
        if self._active_extension is key:
            return False
        self._active_extension = key
        return True

    def register_extension(
        self,
        extension: PipelineExtension,
        activate=True,
    ) -> None:
        key = extension.__class__
        if self._extensions.get(key, None) is not None:
            raise ValueError(f"{key.__component__} already registered.")

        self._extensions[extension.__class__] = extension
        if activate:
            self._active_extension = extension.__class__

    async def execute_command(
        self,
        cmd: PipelineCmd,
        extension: PipelineExtension | None = None,
    ) -> bool:
        if not self._verify_extension(extension):
            return False

        return await self._execute_command(cmd)

    async def subscribe_event(
        self,
        extension: PipelineExtension | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        subscription = Queue[PipelineEvent | None]()

        self._event_subscriptions.add(subscription)

        try:
            while True:
                event = await subscription.get()
                subscription.task_done()
                if event is None:
                    return

                if self._verify_extension(extension):
                    yield event

        finally:
            self._event_subscriptions.discard(subscription)

    def _verify_extension(self, extension: PipelineExtension | None) -> bool:
        return (
            True
            if extension is None or extension.__class__ is self._active_extension
            else False
        )

    async def _execute_command(
        self,
        cmd: PipelineCmd,
    ) -> bool:
        async with self._lock:
            match cmd:
                case ActivateProfile():
                    return await self._handle_activate_profile(cmd)
                case DeactivateProfile():
                    return await self._handle_deactivate_profile(cmd)
                case SayText():
                    return await self._handle_say_text(cmd)

    async def _do_open(self) -> None:
        self._tasks.add_task(
            self._capture_loop(),
            self._detection_loop(),
            self._stt_loop(),
            self._tts_loop(),
            self._playback_loop(),
        )

    async def _do_close(self) -> None:
        await self._audio_driver.stop_room_voice()
        for subscription in self._event_subscriptions:
            subscription.put_nowait(None)
        self._event_subscriptions.clear()

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
                            await self.execute_command(
                                ActivateProfile(profile_id=res.profile_id),
                            )

                        case UtteranceDetected():
                            profile = self._active_profile

                            if profile is None:
                                continue

                            if await self._audio_driver.interrupt():
                                PipelineRequest.bump_generation()

                                self._dispatch_event(
                                    SpeechInterrupted(profile_id=profile.id)
                                )

                            self._stt_queue.put_nowait(
                                PipelineRequest(
                                    data=STTRequest(
                                        audio=res.audio,
                                    ),
                                ),
                            )

                        case ConversationEnded():
                            await self.execute_command(
                                DeactivateProfile(),
                            )

            finally:
                self._detection_queue.task_done()

    async def _stt_loop(self) -> None:
        while True:
            request = await self._stt_queue.get()

            if not request.is_valid or (profile := self._active_profile) is None:
                continue

            try:
                async for response in self._stt_worker.transcribe(
                    request=request.data,
                    profile=profile.stt,
                ):
                    if request.is_valid and isinstance(response, STTResponse):
                        self._dispatch_event(
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

            if not request.is_valid or (profile := self._active_profile) is None:
                continue

            try:
                async for chunk in self._tts_worker.synthesize(
                    request=request.data,
                    profile=profile.tts,
                ):
                    if request.is_valid and isinstance(chunk, TTSChunk):
                        self._playback_queue.put_nowait(
                            PipelineRequest(
                                trace_id=request.trace_id,
                                data=chunk.audio,
                            )
                        )

            finally:
                self._tts_queue.task_done()

    async def _playback_loop(self) -> None:
        while True:
            request = await self._playback_queue.get()

            try:
                if request.is_valid:
                    self._audio_driver.play(request.data)
            finally:
                self._playback_queue.task_done()

    async def _handle_activate_profile(self, cmd: ActivateProfile) -> bool:
        profile = self._profiles.get(cmd.profile_id)

        if self._active_profile is profile:
            return False

        PipelineRequest.bump_generation()

        if self._active_profile is None:
            await self._audio_driver.start_room_voice()
            await self._detection_worker.change_mode(DetectionMode.UTTERANCE)
        else:
            self._dispatch_event(
                ProfileDeactivated(
                    profile_id=self._active_profile.id,
                    trace_id=cmd.trace_id,
                )
            )

        self._active_profile = profile
        self._dispatch_event(
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
        self._dispatch_event(
            ProfileDeactivated(
                profile_id=profile.id,
                trace_id=cmd.trace_id,
            )
        )

        PipelineRequest.bump_generation()

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
            PipelineRequest(
                data=TTSRequest(text=cmd.text),
                trace_id=cmd.trace_id,
            )
        )

        return True

    def _dispatch_event(
        self,
        event: PipelineEvent,
    ) -> None:
        for subscription in self._event_subscriptions:
            subscription.put_nowait(event)
