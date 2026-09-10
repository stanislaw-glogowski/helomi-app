import asyncio
from asyncio import Queue
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from ..audio import AudioDriver, RawAudio
from ..detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
    UtteranceContinued,
    UtteranceDetected,
    UtteranceStarted,
)
from ..reaction import ReactionKind
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
    SynthesisReady,
    TranscriptionReady,
)
from .extension import PipelineExtension, PipelineExtensionKey

if TYPE_CHECKING:
    from ..config import Profile, ProfileCatalog


class PipelineOptions(BaseModel):
    room_voice: bool = True
    wake_word: bool = True


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
        options: PipelineOptions | None = None,
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
        self._options = options or PipelineOptions()
        self._extensions: dict[PipelineExtensionKey, PipelineExtension] = {}

        self._active_profile: Profile | None = None
        self._active_extension: PipelineExtensionKey | None = None

        self._event_subscriptions: set[Queue[PipelineEvent | None]] = set()
        self._lock = asyncio.Lock()

    @property
    def profiles(self) -> ProfileCatalog:
        return self._profiles

    @property
    def options(self) -> PipelineOptions:
        return self._options

    @property
    def active_profile(self) -> Profile | None:
        return self._active_profile

    @property
    def active_extension(self) -> PipelineExtensionKey | None:
        return self._active_extension

    @property
    def _is_active_or_no_extensions(self) -> bool:
        return self._active_extension is not None or not self._extensions

    async def set_option(self, key: str, value: Any) -> bool:
        if not hasattr(self._options, key):
            raise AttributeError(f"Unknown pipeline option: {key}")

        current = getattr(self._options, key)
        if current == value:
            return False

        setattr(self._options, key, value)

        match key:
            case "room_voice":
                if (
                    self._active_profile is not None
                    and self._is_active_or_no_extensions
                ):
                    if value:
                        try:
                            await self._audio_driver.activate(
                                self._active_profile.audio
                            )
                        except Exception as err:
                            self._logger.warning(
                                "Failed to activate room voice for {}: {}",
                                self._active_profile.id,
                                err,
                            )
                    else:
                        await self._audio_driver.deactivate()

            case "wake_word":
                if value:
                    if (
                        self._active_profile is None
                        and self._is_active_or_no_extensions
                    ):
                        await self._detection_worker.change_mode(DetectionMode.PROFILE)
                else:
                    if (
                        self._active_profile is not None
                        and self._is_active_or_no_extensions
                    ):
                        await self._detection_worker.change_mode(
                            DetectionMode.UTTERANCE
                        )

        return True

    async def set_active_extension(self, key: PipelineExtensionKey | None) -> bool:
        if self._active_extension is key:
            return False

        previous_extension = self._active_extension
        self._active_extension = key

        # Entering TTS mode (no extension active)
        if key is None:
            if self._active_profile is not None:
                await self._audio_driver.deactivate()
        # Returning from TTS mode to an active extension
        elif previous_extension is None:
            if self._active_profile is not None and self._options.room_voice:
                try:
                    await self._audio_driver.activate(self._active_profile.audio)
                except Exception as err:
                    self._logger.warning(
                        "Failed to restore room voice for {}: {}",
                        self._active_profile.id,
                        err,
                    )
            mode = (
                DetectionMode.UTTERANCE
                if self._active_profile is not None
                else (
                    DetectionMode.PROFILE
                    if self._options.wake_word
                    else DetectionMode.UTTERANCE
                )
            )
            await self._detection_worker.change_mode(mode)

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
        await self._audio_driver.deactivate()
        for subscription in self._event_subscriptions:
            subscription.put_nowait(None)
        self._event_subscriptions.clear()

    async def _capture_loop(self) -> None:
        async for raw in self._audio_driver.capture():
            self._detection_queue.put_nowait(raw)

    async def _detection_loop(self) -> None:
        while True:
            audio = await self._detection_queue.get()

            if not self._is_active_or_no_extensions:
                continue

            try:
                async for res in self._detection_worker.detect(audio):
                    match res:
                        case ProfileDetected():
                            if self._options.wake_word:
                                await self.execute_command(
                                    ActivateProfile(profile_id=res.profile_id),
                                )

                        case ConversationEnded():
                            if self._options.wake_word:
                                await self.execute_command(
                                    DeactivateProfile(),
                                )
                            elif self._active_profile is not None:
                                await self._detection_worker.change_mode(
                                    DetectionMode.UTTERANCE
                                )

                    profile = self._active_profile
                    if profile is None:
                        continue

                    match res:
                        case UtteranceStarted():
                            if await self._audio_driver.interrupt():
                                PipelineRequest.bump_generation()

                                self._dispatch_event(
                                    SpeechInterrupted(profile_id=profile.id)
                                )

                                reaction = profile.get_reaction(
                                    ReactionKind.INTERRUPTED
                                )

                                if reaction:
                                    self._tts_queue.put_nowait(
                                        PipelineRequest(
                                            data=TTSRequest(
                                                text=reaction,
                                            ),
                                        )
                                    )

                        case UtteranceContinued():
                            pass

                        case UtteranceDetected():
                            if await self._audio_driver.interrupt():
                                PipelineRequest.bump_generation()

                                self._dispatch_event(
                                    SpeechInterrupted(profile_id=profile.id)
                                )

                                reaction = profile.get_reaction(
                                    ReactionKind.INTERRUPTED
                                )

                                if reaction:
                                    self._tts_queue.put_nowait(
                                        PipelineRequest(
                                            data=TTSRequest(
                                                text=reaction,
                                            ),
                                        )
                                    )

                            self._stt_queue.put_nowait(
                                PipelineRequest(
                                    data=STTRequest(
                                        audio=res.audio,
                                    ),
                                ),
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
                        text = response.text.strip()
                        if not text:
                            continue

                        self._dispatch_event(
                            TranscriptionReady(
                                trace_id=request.trace_id,
                                profile_id=profile.id,
                                text=text,
                                audio=request.data.audio,
                            )
                        )
            finally:
                self._stt_queue.task_done()

    async def _tts_loop(self) -> None:
        while True:
            request = await self._tts_queue.get()

            if (
                not request.is_valid
                or not request.data.raw_text
                or (profile := self._active_profile) is None
            ):
                continue

            try:
                chunks: list[RawAudio] = []

                async for chunk in self._tts_worker.synthesize(
                    request=request.data,
                    profile=profile.tts,
                ):
                    if isinstance(chunk, TTSChunk):
                        if request.is_valid:
                            chunks.append(chunk.audio)
                            self._playback_queue.put_nowait(
                                PipelineRequest(
                                    trace_id=request.trace_id,
                                    data=chunk.audio,
                                )
                            )
                        else:
                            chunks.clear()

                if chunks:
                    self._dispatch_event(
                        SynthesisReady(
                            trace_id=request.trace_id,
                            profile_id=profile.id,
                            text=request.data.text,
                            audio=RawAudio.concat(chunks),
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

        if self._active_profile is not None:
            await self._audio_driver.deactivate()
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

        if self._options.room_voice and self._is_active_or_no_extensions:
            try:
                await self._audio_driver.activate(profile.audio)
            except Exception as err:
                self._logger.warning(
                    "Failed to activate audio for profile {}: {}",
                    profile.id,
                    err,
                )

        if self._is_active_or_no_extensions:
            await self._detection_worker.change_mode(DetectionMode.UTTERANCE)

        if self._options.wake_word and cmd.greet and self._is_active_or_no_extensions:
            reaction = profile.get_reaction(ReactionKind.GREETING)

            if reaction:
                self._tts_queue.put_nowait(
                    PipelineRequest(
                        trace_id=cmd.trace_id,
                        data=TTSRequest(
                            text=reaction,
                        ),
                    )
                )

        return True

    async def _handle_deactivate_profile(self, cmd: DeactivateProfile) -> bool:
        profile, self._active_profile = self._active_profile, None
        if profile is None:
            return False

        await self._audio_driver.deactivate()
        mode = (
            DetectionMode.PROFILE
            if self._options.wake_word
            else DetectionMode.UTTERANCE
        )
        await self._detection_worker.change_mode(mode)

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
        text = cmd.text.strip()
        if not text:
            return False

        match self._active_profile:
            case None:
                await self._handle_activate_profile(
                    ActivateProfile(
                        profile_id=cmd.profile_id,
                        trace_id=cmd.trace_id,
                        greet=False,
                    ),
                )
            case profile if cmd.profile_id is not None and profile.id != cmd.profile_id:
                return False

        if self._active_profile is None:
            return False

        self._tts_queue.put_nowait(
            PipelineRequest(
                data=TTSRequest(text=text),
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
