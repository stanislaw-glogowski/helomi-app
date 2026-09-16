import asyncio
from asyncio import Queue
from collections.abc import AsyncIterator
from typing import Any

from ..core.audio import (
    AudioDriver,
    CapturedEvent,
    DisconnectedEvent,
    RawAudio,
)
from ..core.detection import (
    ConversationEndedEvent,
    DetectionMode,
    DetectionWorker,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)
from ..core.stt import STTRequest, STTResponse, STTWorker
from ..core.tts import TTSChunk, TTSRequest, TTSWorker
from ..profile import Profile, ProfileCatalog, ReactionKind
from .component import PipelineComponent
from .config import PipelineSettings
from .domain import PipelineExtensionLike, PipelineExtensionType, PipelineOptions
from .extension import PipelineExtension
from .messages import (
    ActivateProfileCmd,
    DeactivateProfileCmd,
    ExtensionActivatedEvent,
    ExtensionDeactivatedEvent,
    OptionsSetEvent,
    PipelineCmd,
    PipelineEvent,
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
from .request import PipelineRequest


class PipelineService(PipelineComponent):
    def __init__(
        self,
        profiles: ProfileCatalog,
        audio_driver: AudioDriver,
        detection_worker: DetectionWorker,
        stt_worker: STTWorker,
        tts_worker: TTSWorker,
        settings: PipelineSettings | None = None,
        options: PipelineOptions | None = None,
    ) -> None:
        super().__init__()

        settings = settings or PipelineSettings()
        self._profiles = profiles
        self._options = options or PipelineOptions(
            persistent_profile_enabled=settings.persistent_profile,
            persistent_profile_supported=False,
            reactions_enabled=settings.reactions,
            reactions_supported=False,
            room_voice_enabled=settings.room_voice,
            room_voice_supported=False,
            wakeword_enabled=settings.wakeword,
            wakeword_supported=False,
        )

        self._audio_driver = audio_driver

        self._detection_worker = detection_worker
        self._detection_queue: Queue[RawAudio] = Queue()

        self._stt_worker = stt_worker
        self._stt_queue: Queue[PipelineRequest[STTRequest]] = Queue()

        self._tts_worker = tts_worker
        self._tts_queue: Queue[PipelineRequest[TTSRequest]] = Queue()

        self._playback_queue: Queue[PipelineRequest[RawAudio]] = Queue()

        self._extensions: set[PipelineExtensionType] = set()
        self._subscriptions: set[Queue[PipelineEvent | None]] = set()

        self._active_profile: Profile | None = None
        self._active_extension: PipelineExtensionType | None = None
        self._interrupt_cooldown = False

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
            self._sync_options()

    async def activate_extension(
        self,
        extension_like: PipelineExtensionLike,
    ) -> bool:
        extension = self._resolve_extension(extension_like)

        if extension not in self._extensions:
            return False

        if self._active_extension is extension:
            return False

        prev_extension = self._active_extension
        if prev_extension:
            self._dispatch_event(
                ExtensionDeactivatedEvent(
                    extension=prev_extension,
                ),
            )

        self._active_extension = extension
        self._sync_options()

        if (
            prev_extension is None
            and self._active_profile
            and self._options.is_enabled("room_voice")
        ):
            try:
                await self._audio_driver.start_room_voice(
                    profile_id=self._active_profile.id,
                )
            except Exception as err:
                self._logger.warning(
                    "Failed to start room voice profile {}: {}",
                    self._active_profile.id,
                    err,
                )

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
            try:
                await self._audio_driver.stop_room_voice()
            except Exception as err:
                self._logger.warning(
                    "Failed to stop room voice: {}",
                    err,
                )

        self._active_extension = None
        self._sync_options()

        self._dispatch_event(
            ExtensionDeactivatedEvent(
                extension=extension,
                options=self._options.model_copy(deep=True),
            ),
        )

        return True

    async def sync_extension(self) -> None:
        if self._active_extension is None:
            return

        self._dispatch_event(
            ExtensionActivatedEvent(
                active_profile_id=self._active_profile.id
                if self._active_profile
                else None,
                options=self._options.model_copy(deep=True),
                extension=self._active_extension,
            )
        )

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
        self._tasks.add_tasks(
            self._capture_loop(),
            self._detection_loop(),
            self._stt_loop(),
            self._tts_loop(),
            self._playback_loop(),
        )

    async def _do_close(self) -> None:
        await self._audio_driver.disconnect()
        for subscription in self._subscriptions:
            subscription.put_nowait(None)
        self._subscriptions.clear()

    async def _capture_loop(self) -> None:
        async for event in self._audio_driver.subscribe_event():
            match event:
                case CapturedEvent():
                    if event.profile_id and (
                        not self._active_profile
                        or self._active_profile.id != event.profile_id
                    ):
                        await self._handle_activate_profile(
                            ActivateProfileCmd(
                                profile_id=event.profile_id,
                            )
                        )

                    self._detection_queue.put_nowait(event.audio)

                case DisconnectedEvent() if self._active_profile is not None:
                    profile, self._active_profile = self._active_profile, None
                    self._dispatch_event(
                        ProfileDeactivatedEvent(
                            profile_id=profile.id,
                        )
                    )

    async def _detection_loop(self) -> None:
        while True:
            audio = await self._detection_queue.get()

            try:
                async for res in self._detection_worker.detect(audio):
                    match res:
                        case WakeWordDetectedEvent():
                            if self._options.is_enabled("wakeword"):
                                await self.execute_command(
                                    ActivateProfileCmd(profile_id=res.profile_id),
                                )

                        case ConversationEndedEvent():
                            self._interrupt_cooldown = False
                            if (
                                not self._options.is_enabled("persistent_profile")
                                and self._active_profile
                            ):
                                await self.execute_command(
                                    DeactivateProfileCmd(),
                                )

                    if (profile := self._active_profile) is None:
                        continue

                    match res:
                        case UtteranceStartedEvent() | UtteranceDetectedEvent():
                            if (
                                not self._interrupt_cooldown
                                and await self._audio_driver.interrupt()
                            ):
                                PipelineRequest.bump_generation()
                                self._interrupt_cooldown = True

                                self._dispatch_event(
                                    SpeechInterruptedEvent(
                                        profile_id=profile.id,
                                    )
                                )

                                if self._options.is_enabled("reactions"):
                                    reaction = profile.get_reaction(
                                        ReactionKind.INTERRUPTED
                                    )
                                    if reaction:
                                        self._tts_queue.put_nowait(
                                            PipelineRequest(
                                                data=TTSRequest(
                                                    text=reaction,
                                                    profile_id=profile.id,
                                                ),
                                            )
                                        )

                    match res:
                        case UtteranceDetectedEvent():
                            self._interrupt_cooldown = False

                            self._stt_queue.put_nowait(
                                PipelineRequest(
                                    data=STTRequest(
                                        audio=res.audio,
                                        profile_id=profile.id,
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
                ):
                    if isinstance(chunk, TTSChunk):
                        if request.is_current_generation:
                            chunks.append(chunk.audio)

                            self._playback_queue.put_nowait(
                                PipelineRequest(
                                    trace_id=request.trace_id,
                                    data=chunk.audio,
                                    is_final=request.is_final,
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
                if request.is_current_generation and self._active_profile:
                    await self._audio_driver.play(audio=request.data)
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

        for key in (
            "persistent_profile_enabled",
            "reactions_enabled",
            "room_voice_enabled",
            "wakeword_enabled",
        ):
            if (enabled := getattr(cmd, key)) is not None and getattr(
                self._options, key
            ) != enabled:
                update[key] = enabled

        if not update:
            return False

        options = self._options.model_copy(deep=True, update=update)

        if (
            self._options.room_voice_supported
            and options.room_voice_enabled != self._options.room_voice_enabled
            and self._active_profile
            and self._active_extension
        ):
            if options.room_voice_enabled:
                try:
                    await self._audio_driver.start_room_voice(
                        profile_id=self._active_profile.id,
                    )
                except Exception as err:
                    self._logger.warning(
                        "Failed to start room voice profile {}: {}",
                        self._active_profile.id,
                        err,
                    )
            else:
                try:
                    await self._audio_driver.stop_room_voice()
                except Exception as err:
                    self._logger.warning(
                        "Failed to stop room voice: {}",
                        err,
                    )

        self._options = options
        self._dispatch_event(OptionsSetEvent(**update))

        return True

    async def _handle_activate_profile(self, cmd: ActivateProfileCmd) -> bool:
        try:
            profile = self._profiles.get(cmd.profile_id)
        except KeyError:
            return False

        if self._active_profile is profile:
            PipelineRequest.bump_generation()
            self._interrupt_cooldown = False
            await self._detection_worker.change_mode(DetectionMode.UTTERANCE)
            if self._options.is_enabled("reactions"):
                reaction = profile.get_reaction(ReactionKind.GREETING)
                if reaction:
                    self._tts_queue.put_nowait(
                        PipelineRequest(
                            trace_id=cmd.trace_id,
                            data=TTSRequest(
                                text=reaction,
                                profile_id=profile.id,
                            ),
                        )
                    )
            return True

        PipelineRequest.bump_generation()
        self._interrupt_cooldown = False

        if self._active_profile is not None:
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

        if self._options.is_enabled("room_voice"):
            try:
                await self._audio_driver.start_room_voice(
                    profile_id=profile.id,
                )
            except Exception as err:
                self._logger.warning(
                    "Failed to start room voice profile {}: {}",
                    profile.id,
                    err,
                )

        await self._detection_worker.change_mode(DetectionMode.UTTERANCE)

        if self._options.is_enabled("reactions"):
            reaction = profile.get_reaction(ReactionKind.GREETING)

            if reaction:
                self._tts_queue.put_nowait(
                    PipelineRequest(
                        trace_id=cmd.trace_id,
                        data=TTSRequest(
                            text=reaction,
                            profile_id=profile.id,
                        ),
                    )
                )

        return True

    async def _handle_deactivate_profile(self, cmd: DeactivateProfileCmd) -> bool:
        if self._active_profile is None:
            return False

        profile = self._active_profile
        PipelineRequest.bump_generation()
        self._interrupt_cooldown = False

        if self._options.is_enabled("wakeword"):
            await self._detection_worker.change_mode(DetectionMode.WAKEWORD)

        if self._options.is_enabled("room_voice"):
            try:
                await self._audio_driver.stop_room_voice()
            except Exception as err:
                self._logger.warning(
                    "Failed to stop room voice: {}",
                    err,
                )

        if self._options.is_enabled("reactions"):
            reaction = profile.get_reaction(ReactionKind.FAREWELL)

            if reaction:
                self._tts_queue.put_nowait(
                    PipelineRequest(
                        trace_id=cmd.trace_id,
                        data=TTSRequest(
                            text=reaction,
                            profile_id=profile.id,
                        ),
                        is_final=True,
                    )
                )
                return True

        self._active_profile = None
        await self._audio_driver.disconnect()

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
                data=TTSRequest(
                    text=text,
                    profile_id=self._active_profile.id,
                ),
                trace_id=cmd.trace_id,
            )
        )

        return True

    def _sync_options(self) -> None:
        if self._active_extension:
            self._options.persistent_profile_supported = True
            self._options.wakeword_supported = self._detection_worker.wakeword_supported
            self._options.reactions_supported = True
            self._options.room_voice_supported = self._audio_driver.room_voice_supported
        else:
            self._options.persistent_profile_supported = False
            self._options.wakeword_supported = False
            self._options.reactions_supported = False
            self._options.room_voice_supported = False

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
