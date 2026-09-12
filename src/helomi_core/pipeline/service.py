import asyncio
from asyncio import Queue
from collections.abc import AsyncIterator
from typing import Any, Literal

from ..audio import AudioDriver, RawAudio
from ..detection import (
    ConversationEnded,
    DetectionMode,
    DetectionWorker,
    ProfileDetected,
    UtteranceDetected,
    UtteranceStarted,
)
from ..profile import Profile, ProfileCatalog, ReactionKind
from ..stt import STTRequest, STTResponse, STTWorker
from ..tts import TTSChunk, TTSRequest, TTSWorker
from .component import PipelineComponent
from .domain import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ExtensionActivatedEvent,
    ExtensionDeactivatedEvent,
    OptionsSetEvent,
    PipelineCmd,
    PipelineEvent,
    PipelineExtensionLike,
    PipelineExtensionType,
    PipelineOptions,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    SayCmd,
    SayReactionCmd,
    SayTextCmd,
    SetOptionsCmd,
    SpeechInterruptedEvent,
    SynthesisReadyEvent,
    TranscriptionReadyEvent,
)
from .extension import PipelineExtension
from .request import PipelineRequest


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
        self._extensions: set[PipelineExtensionType] = set()
        self._subscriptions: set[Queue[PipelineEvent | None]] = set()

        self._active_profile: Profile | None = None
        self._active_extension: PipelineExtensionType | None = None

        self._lock = asyncio.Lock()

    @property
    def options(self) -> PipelineOptions:
        return self._options

    @property
    def profiles(self) -> ProfileCatalog:
        return self._profiles

    @property
    def active_profile(self) -> Profile | None:
        return self._active_profile

    @property
    def active_extension(self) -> PipelineExtensionType | None:
        return self._active_extension

    def register_extension(
        self,
        extension_like: PipelineExtensionLike,
        activate=True,
    ) -> None:
        extension = self._resolve_extension(extension_like)

        if extension in self._extensions:
            raise ValueError(f"{extension.__name__} already registered.")

        self._extensions.add(extension)

        if activate:
            self._active_extension = extension

    async def activate_extension(
        self,
        extension_like: PipelineExtensionLike,
    ) -> bool:
        extension = self._resolve_extension(extension_like)

        if extension not in self._extensions:
            return False

        if self._active_extension is extension:
            return False

        if self._active_extension:
            self._dispatch_event(
                ExtensionDeactivatedEvent(
                    extension=self._active_extension,
                ),
            )
        elif self._active_profile and self._options.room_voice_enabled:
            await self._audio_driver.activate(self._active_profile.audio)

        self._active_extension = extension

        self._dispatch_event(
            ExtensionActivatedEvent(
                active_profile_id=self._active_profile.id
                if self._active_profile
                else None,
                options=self._options.model_copy(deep=True),
                extension=extension,
            )
        )

        return True

    async def deactivate_extension(self) -> bool:
        if self._active_extension is None:
            return False

        extension, self._active_extension = self._active_extension, None

        if self._active_profile and self._options.room_voice_enabled:
            await self._audio_driver.deactivate()

        self._active_extension = None
        self._dispatch_event(
            ExtensionDeactivatedEvent(
                extension=extension,
            ),
        )

        return True

    async def execute_command(
        self,
        cmd: PipelineCmd,
        extension: PipelineExtensionLike | None = None,
    ) -> bool:
        if extension:
            extension_type = self._resolve_extension(extension)
            if extension_type is not self._active_extension:
                return False

        return await self._execute_command(cmd)

    async def subscribe_event(
        self,
        extension: PipelineExtensionLike | None = None,
    ) -> AsyncIterator[PipelineEvent]:
        subscription = Queue[PipelineEvent | None]()

        self._subscriptions.add(subscription)
        extension_type = self._resolve_extension(extension) if extension else None

        try:
            while True:
                event = await subscription.get()
                subscription.task_done()
                if event is None:
                    return

                if (
                    extension_type
                    and extension_type is not self._active_extension
                    and extension_type is not event.extension
                ):
                    continue

                yield event

        finally:
            self._subscriptions.discard(subscription)

    async def _do_open(self) -> None:
        self._tasks.add_task(
            self._activate_initial_extension(),
            self._capture_loop(),
            self._detection_loop(),
            self._stt_loop(),
            self._tts_loop(),
            self._playback_loop(),
        )

    async def _do_close(self) -> None:
        await self._audio_driver.deactivate()
        for subscription in self._subscriptions:
            subscription.put_nowait(None)
        self._subscriptions.clear()

    async def _activate_initial_extension(self) -> None:
        if self._active_extension is None:
            return

        await asyncio.sleep(2.0)

        self._dispatch_event(
            ExtensionActivatedEvent(
                active_profile_id=self._active_profile.id
                if self._active_profile
                else None,
                options=self._options.model_copy(deep=True),
                extension=self._active_extension,
            )
        )

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
                            if self._get_option_flag("wakeword_enabled"):
                                await self.execute_command(
                                    ActivateProfileCmd(profile_id=res.profile_id),
                                )

                        case ConversationEnded():
                            if self._get_option_flag("wakeword_enabled"):
                                await self.execute_command(
                                    DeactivateProfileCmd(),
                                )
                            elif self._active_profile is not None:
                                await self._detection_worker.change_mode(
                                    DetectionMode.UTTERANCE
                                )

                    if (profile := self._active_profile) is None:
                        continue

                    match res:
                        case UtteranceStarted() | UtteranceDetected():
                            if self._audio_driver.interrupt():
                                PipelineRequest.bump_generation()

                                self._dispatch_event(
                                    SpeechInterruptedEvent(
                                        profile_id=profile.id,
                                    )
                                )

                    match res:
                        case UtteranceDetected():
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

            if (
                not request.is_current_generation
                or (profile := self._active_profile) is None
            ):
                continue

            try:
                async for response in self._stt_worker.transcribe(
                    request=request.data,
                    profile=profile.stt,
                ):
                    if request.is_current_generation and isinstance(
                        response, STTResponse
                    ):
                        text = response.text.strip()
                        if not text:
                            continue

                        self._dispatch_event(
                            TranscriptionReadyEvent(
                                trace_id=request.trace_id,
                                profile_id=profile.id,
                                text=text,
                            )
                        )
            finally:
                self._stt_queue.task_done()

    async def _tts_loop(self) -> None:
        while True:
            request = await self._tts_queue.get()

            if (
                not request.is_current_generation
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
                        if request.is_current_generation:
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
                        SynthesisReadyEvent(
                            trace_id=request.trace_id,
                            profile_id=profile.id,
                            audio=RawAudio.concat(chunks),
                        )
                    )

            finally:
                self._tts_queue.task_done()

    async def _playback_loop(self) -> None:
        while True:
            request = await self._playback_queue.get()

            try:
                if request.is_current_generation:
                    self._audio_driver.play(request.data)
            finally:
                self._playback_queue.task_done()

    async def _execute_command(
        self,
        cmd: PipelineCmd,
    ) -> bool:
        async with self._lock:
            match cmd:
                case SetOptionsCmd():
                    return await self._handle_set_options(cmd)
                case ActivateProfileCmd():
                    return await self._handle_activate_profile(cmd)
                case DeactivateProfileCmd():
                    return await self._handle_deactivate_profile(cmd)
                case SayTextCmd() | SayReactionCmd():
                    return await self._handle_say(cmd)

    async def _handle_set_options(self, cmd: SetOptionsCmd) -> bool:
        update: dict[str, Any] = {}

        for key in ("greeting_enabled", "room_voice_enabled", "wakeword_enabled"):
            if (enabled := getattr(cmd, key)) is not None and getattr(
                self._options, key
            ) != enabled:
                update[key] = enabled

        if not update:
            return False

        options = self._options.model_copy(deep=True, update=update)

        if (
            options.room_voice_enabled != self._options.room_voice_enabled
            and self._active_profile
            and self._active_extension
        ):
            if options.room_voice_enabled:
                try:
                    await self._audio_driver.activate(self._active_profile.audio)
                except Exception as err:
                    self._logger.warning(
                        "Failed to activate audio for profile {}: {}",
                        self._active_profile.id,
                        err,
                    )
            else:
                await self._audio_driver.deactivate()

        self._options = options

        self._dispatch_event(OptionsSetEvent(**update))

        return True

    async def _handle_activate_profile(self, cmd: ActivateProfileCmd) -> bool:
        profile = self._profiles.get(cmd.profile_id)

        if self._active_profile is profile:
            return False

        PipelineRequest.bump_generation()

        if self._active_profile is not None:
            await self._audio_driver.deactivate()
            self._dispatch_event(
                ProfileDeactivatedEvent(
                    profile_id=self._active_profile.id,
                    trace_id=cmd.trace_id,
                )
            )

        self._active_profile = profile
        self._dispatch_event(
            ProfileActivatedEvent(
                profile_id=profile.id,
                trace_id=cmd.trace_id,
            )
        )

        if self._get_option_flag("room_voice_enabled"):
            try:
                await self._audio_driver.activate(profile.audio)
            except Exception as err:
                self._logger.warning(
                    "Failed to activate audio for profile {}: {}",
                    profile.id,
                    err,
                )

        await self._detection_worker.change_mode(DetectionMode.UTTERANCE)

        if self._get_option_flag("greeting_enabled"):
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

    async def _handle_deactivate_profile(self, cmd: DeactivateProfileCmd) -> bool:
        profile, self._active_profile = self._active_profile, None
        if profile is None:
            return False

        PipelineRequest.bump_generation()

        if self._get_option_flag("wakeword_enabled"):
            await self._audio_driver.deactivate()
            mode = DetectionMode.PROFILE
        else:
            mode = DetectionMode.UTTERANCE

        await self._detection_worker.change_mode(mode)

        self._active_profile = None
        self._dispatch_event(
            ProfileDeactivatedEvent(
                profile_id=profile.id,
                trace_id=cmd.trace_id,
            )
        )

        return True

    async def _handle_say(self, cmd: SayCmd) -> bool:
        match self._active_profile:
            case None:
                await self._handle_activate_profile(
                    ActivateProfileCmd(
                        profile_id=cmd.profile_id,
                        trace_id=cmd.trace_id,
                    )
                )
            case profile if cmd.profile_id is not None and profile.id != cmd.profile_id:
                return False

        if self._active_profile is None:
            return False

        match cmd:
            case SayTextCmd():
                text = cmd.text.strip()
            case SayReactionCmd():
                text = self._active_profile.get_reaction(cmd.reaction)

        if not text:
            return False

        self._tts_queue.put_nowait(
            PipelineRequest(
                data=TTSRequest(text=text),
                trace_id=cmd.trace_id,
            )
        )

        return True

    def _get_option_flag(
        self,
        key: Literal[
            "greeting_enabled",
            "room_voice_enabled",
            "wakeword_enabled",
        ],
    ) -> bool:
        return (
            self._active_extension is not None and getattr(self._options, key) is True
        )

    def _dispatch_event(
        self,
        event: PipelineEvent,
    ) -> None:
        for subscription in self._subscriptions:
            subscription.put_nowait(event)

    @staticmethod
    def _resolve_extension(
        extension_like: PipelineExtensionLike,
    ) -> PipelineExtensionType:
        return (
            extension_like.__class__
            if isinstance(extension_like, PipelineExtension)
            else extension_like
        )
