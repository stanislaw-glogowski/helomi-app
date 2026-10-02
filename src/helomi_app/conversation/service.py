import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal
from uuid import uuid4

from helomi_foundation import EventSource, on_mount, on_run, on_unmount
from helomi_runtime.audio import (
    AudioEvent,
    AudioRouter,
    AudioStreamBuffer,
    CapturedEvent,
    ConnectedEvent,
    DisconnectedEvent,
    RawAudio,
    RouteChangedEvent,
)
from helomi_runtime.config import Profile, ProfileCatalog
from helomi_runtime.detection import (
    ConversationEndedEvent as DetectionConversationEndedEvent,
)
from helomi_runtime.detection import (
    DetectionMode,
    DetectionWorker,
    UtteranceDetectedEvent,
    UtteranceStartedEvent,
    WakeWordDetectedEvent,
)
from helomi_runtime.reaction import ReactionCatalog, ReactionKind
from helomi_runtime.synthesis import SynthesisRequest, SynthesisWorker
from helomi_runtime.transcription import (
    TranscriptionRequest,
    TranscriptionResponse,
    TranscriptionWorker,
)

from ..config import ConversationSettings
from ..messages import (
    ActivateProfileCommand,
    ActivationSource,
    ApplicationCommand,
    ApplicationEvent,
    CallEndedEvent,
    CallStartedEvent,
    CommandRejectionCode,
    CommandResult,
    ConversationOptionsChangedEvent,
    ConversationState,
    ConversationStateChangedEvent,
    DeactivateProfileCommand,
    DriverChangedEvent,
    EndConversationCommand,
    ProcessingFailedEvent,
    ProfileActivatedEvent,
    ProfileDeactivatedEvent,
    ResponseMode,
    ResponseModeChangedEvent,
    SayReactionCommand,
    SayTextCommand,
    SetConversationOptionsCommand,
    SetMonitoringCommand,
    SetResponseModeCommand,
    SpeechInterruptedEvent,
    SwitchDriverCommand,
    SynthesisReadyEvent,
    TranscriptionReadyEvent,
)
from ..response import ResponseModule
from .domain import ConversationIdentity, ConversationOptions, TurnToken


@dataclass(frozen=True, slots=True)
class _SpeechRequest:
    text: str
    profile_id: str
    mode: ResponseMode
    token: TurnToken
    trace_id: str | None
    audio: RawAudio | None = None
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class _PlaybackRequest:
    audio: RawAudio
    profile_id: str
    token: TurnToken
    playback_id: str
    speech_id: str
    trace_id: str | None = None


class ConversationService(EventSource[ApplicationEvent]):
    """Coordinate profile activation, turn processing, and spoken responses."""

    _AUDIO_BUFFER_SECONDS: ClassVar[float] = 1.0
    _CAPTURE_BUFFER_SECONDS: ClassVar[float] = 2.0

    _ALLOWED_TRANSITIONS: ClassVar[dict[ConversationState, set[ConversationState]]] = {
        ConversationState.IDLE: {
            ConversationState.ARMED,
            ConversationState.LISTENING,
            ConversationState.CLOSING,
        },
        ConversationState.ARMED: {
            ConversationState.IDLE,
            ConversationState.LISTENING,
            ConversationState.CLOSING,
        },
        ConversationState.LISTENING: {
            ConversationState.ARMED,
            ConversationState.IDLE,
            ConversationState.PROCESSING,
            ConversationState.SPEAKING,
            ConversationState.CLOSING,
        },
        ConversationState.PROCESSING: {
            ConversationState.LISTENING,
            ConversationState.SPEAKING,
            ConversationState.CLOSING,
        },
        ConversationState.SPEAKING: {
            ConversationState.LISTENING,
            ConversationState.CLOSING,
        },
        ConversationState.CLOSING: {
            ConversationState.IDLE,
            ConversationState.ARMED,
            ConversationState.LISTENING,
        },
    }

    def __init__(
        self,
        settings: ConversationSettings,
        profiles: ProfileCatalog,
        reactions: ReactionCatalog,
        audio_router: AudioRouter,
        detection_worker: DetectionWorker,
        transcription_worker: TranscriptionWorker,
        synthesis_worker: SynthesisWorker,
        transcription_adapter: str,
        synthesis_adapter: str,
        response_mode: ResponseMode,
        response_modules: dict[ResponseMode, ResponseModule],
    ):
        super().__init__()
        self._settings = settings
        self._profiles = profiles
        self._reactions = reactions
        self._audio_router = audio_router
        self._detection_worker = detection_worker
        self._transcription_worker = transcription_worker
        self._synthesis_worker = synthesis_worker
        self._transcription_adapter = transcription_adapter
        self._synthesis_adapter = synthesis_adapter
        self._response_mode = response_mode
        self._response_modules = response_modules
        if response_mode not in response_modules:
            raise ValueError(f"Response mode is not registered: {response_mode}")
        self._options = ConversationOptions.from_settings(settings)
        self._state = ConversationState.IDLE
        self._active_profile: Profile | None = None
        self._remote_call_profile_id: str | None = None
        self._identity = ConversationIdentity()
        self._detection_queue: asyncio.Queue[RawAudio] = asyncio.Queue()
        self._capture_seconds = 0.0
        self._capture_gap = False
        self._transcription_queue: asyncio.Queue[
            tuple[TranscriptionRequest, TurnToken, str | None]
        ] = asyncio.Queue()
        self._speech_queue: asyncio.Queue[_SpeechRequest] = asyncio.Queue()
        self._playback_queue: asyncio.Queue[_PlaybackRequest] = asyncio.Queue()
        self._audio_capacity = asyncio.Condition()
        self._buffered_audio_seconds = 0.0
        self._active_synthesis: asyncio.Task[None] | None = None
        self._synthesis_token: TurnToken | None = None
        self._transcription_token: TurnToken | None = None
        self._playback_tasks: dict[asyncio.Task[None], _PlaybackRequest] = {}
        self._failed_speech: set[str] = set()
        self._speech_idle = asyncio.Event()
        self._speech_idle.set()
        self._remote_call_sid: str | None = None
        self._command_lock = asyncio.Lock()

    @property
    def profiles(self) -> ProfileCatalog:
        return self._profiles

    @property
    def options(self) -> ConversationOptions:
        return self._options

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def active_profile(self) -> Profile | None:
        return self._active_profile

    @property
    def response_mode(self) -> ResponseMode:
        return self._response_mode

    @property
    def audio_router(self) -> AudioRouter:
        return self._audio_router

    async def execute_command(self, command: ApplicationCommand) -> CommandResult:
        if isinstance(command, EndConversationCommand) and command.wait_for_speech:
            async with self._command_lock:
                if self._active_profile is None:
                    return CommandResult.reject(CommandRejectionCode.INVALID_STATE)
                if not self._matches_command_turn(command):
                    return CommandResult.reject(CommandRejectionCode.STALE_TURN)
                token = self._identity.current()
                idle = self._speech_idle
            # Waiting must not hold the command lock needed by barge-in.
            await idle.wait()
            async with self._command_lock:
                if not self._identity.is_current(token):
                    return CommandResult.reject(CommandRejectionCode.STALE_TURN)
                return await self._deactivate_profile(command.play_farewell)
        async with self._command_lock:
            match command:
                case ActivateProfileCommand():
                    return await self._activate_profile(command)
                case DeactivateProfileCommand():
                    return await self._deactivate_profile(command.play_farewell)
                case EndConversationCommand():
                    if not self._matches_command_turn(command):
                        return CommandResult.reject(CommandRejectionCode.STALE_TURN)
                    return await self._deactivate_profile(command.play_farewell)
                case SayTextCommand():
                    return await self._say_text(command)
                case SayReactionCommand():
                    return await self._say_reaction(command)
                case SetResponseModeCommand():
                    return await self._set_response_mode(command.mode)
                case SwitchDriverCommand():
                    return await self._switch_driver(command)
                case SetMonitoringCommand():
                    return self._set_monitoring(command.enabled)
                case SetConversationOptionsCommand():
                    return await self._set_options(command)

    @on_mount()
    async def _prepare_detection(self):
        await self._apply_idle_detection_mode()

    @on_run()
    async def _audio_loop(self):
        async for event in self._audio_router.subscribe_events():
            try:
                await self._handle_audio_event(event)
            except Exception as error:
                self._report_failure("playback", error)

    @on_run()
    async def _detection_loop(self):
        while True:
            audio = await self._detection_queue.get()
            self._capture_seconds = max(
                0.0, self._capture_seconds - audio.duration_seconds
            )
            try:
                if self._capture_gap:
                    self._capture_gap = False
                    await self._detection_worker.set_mode(
                        self._detection_worker.current_mode, force=True
                    )
                async for event in self._detection_worker.detect(audio):
                    await self._handle_detection_event(event)
            except Exception as error:
                self._report_failure("detection", error)
                self._capture_gap = True
            finally:
                self._detection_queue.task_done()

    @on_run()
    async def _transcription_loop(self):
        while True:
            request, token, trace_id = await self._transcription_queue.get()
            self._transcription_token = token
            try:
                if not self._identity.is_current(token):
                    continue
                async for response in self._transcription_worker.transcribe(request):
                    if not self._identity.is_current(token):
                        break
                    if not isinstance(response, TranscriptionResponse):
                        continue
                    text = response.text.strip()
                    if not text or self._active_profile is None:
                        continue
                    self._dispatch_event(
                        TranscriptionReadyEvent(
                            trace_id=trace_id,
                            session_id=token.session_id,
                            turn_id=token.turn_id,
                            profile_id=request.profile_id,
                            text=text,
                        )
                    )
                    mode = self._response_mode
                    response = await self._response_modules[mode].respond(
                        text, request.profile_id
                    )
                    if not self._identity.is_current(token):
                        continue
                    if response:
                        self._enqueue_speech(
                            _SpeechRequest(
                                response, request.profile_id, mode, token, trace_id
                            )
                        )
                    else:
                        await self._settle_speech(token)
            except Exception as error:
                self._report_failure(
                    "transcription", error, token, request.profile_id, trace_id
                )
            finally:
                self._transcription_token = None
                self._transcription_queue.task_done()
                await self._settle_speech(token)

    @on_run()
    async def _synthesis_loop(self):
        while True:
            request = await self._speech_queue.get()
            try:
                if not self._request_is_current(request):
                    continue
                self._synthesis_token = request.token
                task = asyncio.create_task(self._produce_speech(request))
                self._active_synthesis = task
                try:
                    await task
                except asyncio.CancelledError:
                    if self._exit_signal.is_set():
                        raise
            except Exception as error:
                self._report_failure(
                    "synthesis",
                    error,
                    request.token,
                    request.profile_id,
                    request.trace_id,
                )
            finally:
                self._active_synthesis = None
                self._synthesis_token = None
                self._speech_queue.task_done()
                await self._settle_speech(request.token)

    async def _speech_audio(self, request: _SpeechRequest) -> AsyncGenerator[RawAudio]:
        if request.audio is not None:
            yield request.audio
            return
        async with aclosing(
            self._synthesis_worker.synthesize(
                SynthesisRequest(text=request.text, profile_id=request.profile_id)
            )
        ) as stream:
            async for chunk in stream:
                yield chunk.audio

    async def _produce_speech(self, request: _SpeechRequest) -> None:
        buffer = AudioStreamBuffer()
        chunks: list[RawAudio] = []
        async with aclosing(self._speech_audio(request)) as stream:
            async for audio in stream:
                if not self._request_is_current(request):
                    return
                chunks.append(audio)
                for portion in buffer.feed(audio):
                    if not await self._enqueue_audio(request, portion):
                        return
        if (tail := buffer.finish()) is not None:
            if not await self._enqueue_audio(request, tail):
                return
        if chunks and request.audio is None and self._request_is_current(request):
            self._dispatch_event(
                SynthesisReadyEvent(
                    trace_id=request.trace_id,
                    session_id=request.token.session_id,
                    turn_id=request.token.turn_id,
                    profile_id=request.profile_id,
                    text=request.text,
                    audio=RawAudio.concat(chunks),
                )
            )

    async def _enqueue_audio(self, speech: _SpeechRequest, audio: RawAudio) -> bool:
        async with self._audio_capacity:
            await self._audio_capacity.wait_for(
                lambda: (
                    not self._request_is_current(speech)
                    or speech.id in self._failed_speech
                    or self._buffered_audio_seconds + audio.duration_seconds
                    <= self._AUDIO_BUFFER_SECONDS + 1e-9
                )
            )
            if not self._request_is_current(speech) or speech.id in self._failed_speech:
                return False
            self._buffered_audio_seconds += audio.duration_seconds
            self._playback_queue.put_nowait(
                _PlaybackRequest(
                    audio,
                    speech.profile_id,
                    speech.token,
                    uuid4().hex,
                    speech.id,
                    speech.trace_id,
                )
            )
            return True

    async def _release_audio(self, seconds: float) -> None:
        async with self._audio_capacity:
            self._buffered_audio_seconds = max(
                0.0, self._buffered_audio_seconds - seconds
            )
            self._audio_capacity.notify_all()

    @on_run()
    async def _playback_loop(self):
        while True:
            request = await self._playback_queue.get()
            handed_off = False
            try:
                if (
                    not self._identity.is_current(request.token)
                    or request.speech_id in self._failed_speech
                ):
                    continue
                if not await self._audio_router.play(
                    request.audio,
                    playback_id=request.playback_id,
                    turn_id=request.token.turn_id,
                ):
                    raise RuntimeError("Audio driver rejected playback")
                # play() may yield during transport backpressure or a route change.
                if not self._identity.is_current(request.token):
                    continue
                self._set_state(ConversationState.SPEAKING)
                timeout = (
                    self._buffered_audio_seconds + self._settings.playback_ack_timeout
                )
                task = asyncio.create_task(self._complete_playback(request, timeout))
                self._playback_tasks[task] = request
                handed_off = True
            except Exception as error:
                self._fail_playback(request, error)
            finally:
                if not handed_off:
                    await self._release_audio(request.audio.duration_seconds)
                    self._playback_queue.task_done()
                    await self._settle_speech(request.token)

    async def _complete_playback(
        self, request: _PlaybackRequest, timeout_seconds: float
    ) -> None:
        try:
            if not self._identity.is_current(request.token):
                return
            completed = await self._audio_router.wait_for_playback(
                request.playback_id, timeout_seconds
            )
            if not completed and self._identity.is_current(request.token):
                self._fail_playback(
                    request, RuntimeError("Playback did not finish successfully")
                )
                await self._audio_router.interrupt(turn_id=request.token.turn_id)
        except Exception as error:
            self._fail_playback(request, error)
        finally:
            task = asyncio.current_task()
            if task is not None:
                self._playback_tasks.pop(task, None)
            await self._release_audio(request.audio.duration_seconds)
            self._playback_queue.task_done()
            await self._settle_speech(request.token)

    def _fail_playback(self, request: _PlaybackRequest, error: Exception) -> None:
        if request.speech_id not in self._failed_speech:
            self._failed_speech.add(request.speech_id)
            self._report_failure(
                "playback", error, request.token, request.profile_id, request.trace_id
            )

    def _request_is_current(self, request: _SpeechRequest) -> bool:
        return (
            self._identity.is_current(request.token)
            and request.mode == self._response_mode
            and self._active_profile is not None
            and self._active_profile.id == request.profile_id
        )

    def _enqueue_speech(self, request: _SpeechRequest) -> None:
        self._speech_idle.clear()
        self._speech_queue.put_nowait(request)

    def _has_speech(self) -> bool:
        return (
            (
                self._synthesis_token is not None
                and self._identity.is_current(self._synthesis_token)
            )
            or not self._speech_queue.empty()
            or not self._playback_queue.empty()
            or any(
                self._identity.is_current(request.token)
                for request in self._playback_tasks.values()
            )
        )

    async def _settle_speech(self, token: TurnToken) -> None:
        if (
            self._exit_signal.is_set()
            or not self._identity.is_current(token)
            or self._has_speech()
            or self._state == ConversationState.CLOSING
        ):
            return
        self._speech_idle.set()
        if self._state in {ConversationState.PROCESSING, ConversationState.SPEAKING}:
            was_speaking = self._state == ConversationState.SPEAKING
            self._set_state(ConversationState.LISTENING)
            if was_speaking:
                try:
                    await self._detection_worker.reset_idle_timeout()
                except Exception as error:
                    self._report_failure("detection", error, token)

    async def _discard_turn_work(self) -> None:
        self._speech_idle.set()
        self._speech_idle = asyncio.Event()
        self._speech_idle.set()
        if self._active_synthesis is not None:
            self._active_synthesis.cancel()
        for queue in (self._speech_queue, self._transcription_queue):
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
        seconds = 0.0
        while not self._playback_queue.empty():
            request = self._playback_queue.get_nowait()
            seconds += request.audio.duration_seconds
            self._playback_queue.task_done()
        await self._release_audio(seconds)
        self._failed_speech.clear()

    @on_unmount()
    async def _stop_playback_tasks(self) -> None:
        tasks = tuple(self._playback_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._discard_turn_work()
        self._buffered_audio_seconds = 0.0
        while not self._detection_queue.empty():
            self._detection_queue.get_nowait()
            self._detection_queue.task_done()
        self._capture_seconds = 0.0

    def _report_failure(
        self,
        stage: Literal["detection", "transcription", "synthesis", "playback"],
        error: Exception,
        token: TurnToken | None = None,
        profile_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._logger.error("{} failed: {}", stage, error)
        self._dispatch_event(
            ProcessingFailedEvent(
                stage=stage,
                detail=str(error),
                profile_id=profile_id,
                trace_id=trace_id,
                session_id=token.session_id if token else self._identity.session_id,
                turn_id=token.turn_id if token else self._identity.turn_id,
            )
        )

    def _matches_command_turn(
        self, command: SayTextCommand | SayReactionCommand | EndConversationCommand
    ) -> bool:
        return command.session_id is None or (
            command.session_id == self._identity.session_id
            and command.turn_id == self._identity.turn_id
        )

    async def _handle_audio_event(self, event: AudioEvent) -> None:
        match event:
            case ConnectedEvent(
                profile_id=profile_id, caller=caller, call_sid=call_sid
            ):
                if call_sid == self._remote_call_sid:
                    return
                self._remote_call_sid = call_sid
                self._remote_call_profile_id = profile_id
                result = await self.execute_command(
                    ActivateProfileCommand(
                        profile_id=profile_id,
                        source=ActivationSource.TWILIO,
                    )
                )
                if result.accepted:
                    self._dispatch_event(
                        CallStartedEvent(
                            session_id=self._identity.session_id,
                            turn_id=self._identity.turn_id,
                            profile_id=profile_id,
                            caller=self._mask_caller(caller),
                            monitoring=self._audio_router.monitoring_enabled,
                        )
                    )
                else:
                    self._remote_call_profile_id = None
                    await self._audio_router.disconnect()
            case DisconnectedEvent(driver_id="twilio"):
                profile_id = self._remote_call_profile_id
                self._remote_call_profile_id = None
                self._remote_call_sid = None
                self._dispatch_event(
                    CallEndedEvent(
                        session_id=self._identity.session_id,
                        turn_id=self._identity.turn_id,
                        profile_id=profile_id,
                    )
                )
                if (
                    self._active_profile is not None
                    and self._active_profile.id == profile_id
                ):
                    await self._finish_profile(play_farewell=False, disconnect=False)
            case RouteChangedEvent(driver_id=driver_id, previous_driver_id=previous):
                if self._active_profile is not None:
                    self._identity.next_turn()
                    await self._discard_turn_work()
                    if self._state in {
                        ConversationState.PROCESSING,
                        ConversationState.SPEAKING,
                    }:
                        self._set_state(ConversationState.LISTENING)
                self._dispatch_event(
                    DriverChangedEvent(
                        session_id=self._identity.session_id,
                        turn_id=self._identity.turn_id,
                        driver_id=driver_id,
                        previous_driver_id=previous,
                    )
                )
            case CapturedEvent(audio=audio):
                if audio.duration_seconds > self._CAPTURE_BUFFER_SECONDS:
                    size = (
                        round(self._CAPTURE_BUFFER_SECONDS * audio.format.sample_rate)
                        * 4
                    )
                    audio = RawAudio(audio.format, audio.data[-size:])
                    self._capture_gap = True
                dropped = False
                while (
                    not self._detection_queue.empty()
                    and self._capture_seconds + audio.duration_seconds
                    > self._CAPTURE_BUFFER_SECONDS
                ):
                    oldest = self._detection_queue.get_nowait()
                    self._capture_seconds -= oldest.duration_seconds
                    self._detection_queue.task_done()
                    dropped = True
                if dropped:
                    self._capture_gap = True
                    self._logger.warning(
                        "Capture buffer overflow; discarded oldest audio"
                    )
                self._capture_seconds += audio.duration_seconds
                self._detection_queue.put_nowait(audio)

    async def _handle_detection_event(self, event: Any) -> None:
        match event:
            case WakeWordDetectedEvent(profile_id=profile_id):
                if self._options.wakeword:
                    await self.execute_command(
                        ActivateProfileCommand(
                            profile_id=profile_id,
                            source=ActivationSource.WAKEWORD,
                        )
                    )
            case UtteranceStartedEvent():
                if (
                    self._active_profile is None
                    or self._state == ConversationState.CLOSING
                ):
                    return
                was_interrupt = self._state in {
                    ConversationState.PROCESSING,
                    ConversationState.SPEAKING,
                }
                token = self._identity.next_turn()
                await self._discard_turn_work()
                if was_interrupt:
                    await self._audio_router.interrupt(turn_id=token.turn_id)
                    self._dispatch_event(
                        SpeechInterruptedEvent(
                            session_id=token.session_id,
                            turn_id=token.turn_id,
                            profile_id=self._active_profile.id,
                        )
                    )
                self._set_state(ConversationState.LISTENING)
            case UtteranceDetectedEvent(audio=audio):
                if self._active_profile is None:
                    return
                token = self._identity.current()
                self._set_state(ConversationState.PROCESSING)
                self._transcription_queue.put_nowait(
                    (
                        TranscriptionRequest(
                            audio=audio, profile_id=self._active_profile.id
                        ),
                        token,
                        None,
                    )
                )
            case DetectionConversationEndedEvent():
                await self._handle_follow_up_timeout()

    async def _activate_profile(self, command: ActivateProfileCommand) -> CommandResult:
        profile = self._profiles.get(command.profile_id)
        if profile is None:
            return CommandResult.reject(CommandRejectionCode.PROFILE_NOT_FOUND)
        if command.source == ActivationSource.TWILIO:
            if self._audio_router.remote_profile_id != profile.id:
                return CommandResult.reject(CommandRejectionCode.PROFILE_MISMATCH)
        if command.source == ActivationSource.WAKEWORD:
            if profile.get_wakeword_profile("openwakeword") is None:
                return CommandResult.reject(CommandRejectionCode.UNSUPPORTED)
        try:
            profile.get_transcription_profile(self._transcription_adapter)
            profile.get_synthesis_profile(self._synthesis_adapter)
        except ValueError as error:
            return CommandResult.reject(CommandRejectionCode.UNSUPPORTED, str(error))

        if (
            self._active_profile is profile
            and command.source != ActivationSource.TWILIO
        ):
            await self._detection_worker.set_mode(DetectionMode.UTTERANCE)
            self._set_state(ConversationState.LISTENING)
            return CommandResult.ok()
        if self._active_profile is not None:
            await self._finish_profile(play_farewell=False, disconnect=False)

        self._active_profile = profile
        token = self._identity.start_session()
        await self._detection_worker.set_mode(DetectionMode.UTTERANCE)
        self._set_state(ConversationState.LISTENING)
        self._dispatch_event(
            ProfileActivatedEvent(
                trace_id=command.trace_id,
                session_id=token.session_id,
                turn_id=token.turn_id,
                profile_id=profile.id,
                source=command.source,
            )
        )
        if self._options.room_voice:
            await self._audio_router.start_room_voice(profile.id)
        reaction = (
            ReactionKind.CONNECTED
            if command.source == ActivationSource.TWILIO
            else ReactionKind.GREETING
        )
        if (audio := self._reaction_audio(profile.id, reaction)) is not None:
            self._enqueue_speech(
                _SpeechRequest(
                    "", profile.id, self._response_mode, token, command.trace_id, audio
                )
            )
        return CommandResult.ok()

    async def _deactivate_profile(self, play_farewell: bool) -> CommandResult:
        if self._active_profile is None:
            return CommandResult.reject(CommandRejectionCode.INVALID_STATE)
        await self._finish_profile(play_farewell=play_farewell, disconnect=True)
        return CommandResult.ok()

    async def _finish_profile(
        self,
        *,
        play_farewell: bool,
        disconnect: bool,
    ) -> None:
        profile = self._active_profile
        if profile is None:
            return
        self._set_state(ConversationState.CLOSING)
        token = self._identity.next_turn()
        await self._discard_turn_work()
        await self._audio_router.interrupt()
        if play_farewell:
            farewell = self._reaction_audio(profile.id, ReactionKind.FAREWELL)
            if farewell is not None:
                playback_id = uuid4().hex
                if await self._audio_router.play(
                    farewell,
                    playback_id=playback_id,
                    turn_id=token.turn_id,
                ):
                    await self._audio_router.wait_for_playback(
                        playback_id,
                        farewell.duration_seconds + self._settings.playback_ack_timeout,
                    )
        await self._audio_router.stop_room_voice()
        self._active_profile = None
        self._identity.clear()
        if disconnect and self._audio_router.is_remote_session:
            await self._audio_router.disconnect()
        self._dispatch_event(ProfileDeactivatedEvent(profile_id=profile.id))
        await self._apply_idle_detection_mode()

    async def _say_text(self, command: SayTextCommand) -> CommandResult:
        if not self._matches_command_turn(command):
            return CommandResult.reject(CommandRejectionCode.STALE_TURN)
        text = command.text.strip()
        if not text:
            return CommandResult.reject(CommandRejectionCode.EMPTY_TEXT)
        if command.mode != self._response_mode:
            return CommandResult.reject(CommandRejectionCode.MODE_INACTIVE)
        profile = self._active_profile
        if profile is None:
            return CommandResult.reject(CommandRejectionCode.PROFILE_REQUIRED)
        if command.profile_id is not None and command.profile_id != profile.id:
            return CommandResult.reject(CommandRejectionCode.PROFILE_MISMATCH)
        self._prepare_speech_state()
        self._enqueue_speech(
            _SpeechRequest(
                text=text,
                profile_id=profile.id,
                mode=command.mode,
                token=self._identity.current(),
                trace_id=command.trace_id,
            )
        )
        return CommandResult.ok()

    async def _say_reaction(self, command: SayReactionCommand) -> CommandResult:
        if not self._matches_command_turn(command):
            return CommandResult.reject(CommandRejectionCode.STALE_TURN)
        if command.mode != self._response_mode:
            return CommandResult.reject(CommandRejectionCode.MODE_INACTIVE)
        profile = self._active_profile
        if profile is None:
            return CommandResult.reject(CommandRejectionCode.PROFILE_REQUIRED)
        if command.profile_id is not None and command.profile_id != profile.id:
            return CommandResult.reject(CommandRejectionCode.PROFILE_MISMATCH)
        audio = self._reaction_audio(profile.id, command.reaction)
        if audio is None:
            return CommandResult.reject(CommandRejectionCode.UNSUPPORTED)
        token = self._identity.current()
        self._prepare_speech_state()
        self._enqueue_speech(
            _SpeechRequest("", profile.id, command.mode, token, command.trace_id, audio)
        )
        return CommandResult.ok()

    async def _set_response_mode(self, mode: ResponseMode) -> CommandResult:
        if mode == self._response_mode:
            return CommandResult.reject(CommandRejectionCode.INVALID_STATE)
        previous = self._response_mode
        if self._active_profile is not None and (
            self._has_speech()
            or self._state
            in {
                ConversationState.PROCESSING,
                ConversationState.SPEAKING,
            }
        ):
            token = self._identity.next_turn()
            await self._discard_turn_work()
            await self._audio_router.interrupt(turn_id=token.turn_id)
            self._set_state(ConversationState.LISTENING)
        self._response_mode = mode
        self._dispatch_event(
            ResponseModeChangedEvent(
                session_id=self._identity.session_id,
                turn_id=self._identity.turn_id,
                mode=mode,
                previous_mode=previous,
            )
        )
        return CommandResult.ok()

    async def _switch_driver(self, command: SwitchDriverCommand) -> CommandResult:
        if command.driver_id not in {
            driver_descriptor.id
            for driver_descriptor in self._audio_router.driver_descriptors
        }:
            return CommandResult.reject(CommandRejectionCode.DRIVER_NOT_FOUND)
        if self._audio_router.is_remote_session and not command.end_remote_session:
            return CommandResult.reject(CommandRejectionCode.CONFIRMATION_REQUIRED)
        changed = await self._audio_router.switch_driver(
            command.driver_id,  # type: ignore[arg-type]
            end_remote_session=command.end_remote_session,
        )
        return (
            CommandResult.ok()
            if changed
            else CommandResult.reject(CommandRejectionCode.UNSUPPORTED)
        )

    def _set_monitoring(self, enabled: bool) -> CommandResult:
        if not self._audio_router.set_monitoring(enabled):
            return CommandResult.reject(CommandRejectionCode.INVALID_STATE)
        return CommandResult.ok()

    async def _set_options(
        self, command: SetConversationOptionsCommand
    ) -> CommandResult:
        updates = {
            key: value
            for key in ("persistent_profile", "reactions", "room_voice", "wakeword")
            if (value := getattr(command, key)) is not None
            and value != getattr(self._options, key)
        }
        if not updates:
            return CommandResult.reject(CommandRejectionCode.INVALID_STATE)
        old_options = self._options
        self._options = self._options.model_copy(update=updates)
        if (
            self._active_profile is not None
            and old_options.room_voice != self._options.room_voice
        ):
            if self._options.room_voice:
                await self._audio_router.start_room_voice(self._active_profile.id)
            else:
                await self._audio_router.stop_room_voice()
        if old_options.wakeword != self._options.wakeword:
            await self._apply_idle_detection_mode()
        self._dispatch_event(
            ConversationOptionsChangedEvent(
                session_id=self._identity.session_id,
                turn_id=self._identity.turn_id,
                **self._options.model_dump(),
            )
        )
        return CommandResult.ok()

    async def _handle_follow_up_timeout(self) -> None:
        if self._active_profile is not None and (
            self._state
            in {
                ConversationState.PROCESSING,
                ConversationState.SPEAKING,
                ConversationState.CLOSING,
            }
            or self._has_speech()
            or self._transcription_token is not None
        ):
            await self._detection_worker.set_mode(DetectionMode.UTTERANCE)
            return
        if self._active_profile is None:
            await self._apply_idle_detection_mode()
        elif not self._options.persistent_profile:
            await self._finish_profile(play_farewell=True, disconnect=True)
        elif self._options.wakeword and self._detection_worker.wakeword_supported:
            await self._detection_worker.set_mode(DetectionMode.WAKEWORD)
            self._set_state(ConversationState.ARMED)
        else:
            await self._detection_worker.set_mode(DetectionMode.UTTERANCE)
            self._set_state(ConversationState.LISTENING)

    async def _apply_idle_detection_mode(self) -> None:
        if self._active_profile is not None:
            return
        if self._options.wakeword and self._detection_worker.wakeword_supported:
            await self._detection_worker.set_mode(DetectionMode.WAKEWORD)
            self._set_state(ConversationState.ARMED)
        else:
            await self._detection_worker.set_mode(DetectionMode.UTTERANCE)
            self._set_state(ConversationState.IDLE)

    def _reaction_audio(
        self,
        profile_id: str,
        reaction: ReactionKind,
    ) -> RawAudio | None:
        if not self._options.reactions:
            return None
        return self._reactions.get_audio(profile_id, reaction)

    def _set_state(self, state: ConversationState) -> None:
        previous = self._state
        if state == previous:
            return
        if state not in self._ALLOWED_TRANSITIONS[previous]:
            raise RuntimeError(
                f"Invalid conversation transition: {previous} -> {state}"
            )
        self._state = state
        self._dispatch_event(
            ConversationStateChangedEvent(
                session_id=self._identity.session_id,
                turn_id=self._identity.turn_id,
                state=state,
                previous_state=previous,
            )
        )

    def _prepare_speech_state(self) -> None:
        if self._state == ConversationState.ARMED:
            self._set_state(ConversationState.LISTENING)
        if self._state == ConversationState.LISTENING:
            self._set_state(ConversationState.PROCESSING)

    @staticmethod
    def _mask_caller(caller: str) -> str:
        if len(caller) <= 4:
            return "*" * len(caller)
        return f"{'*' * (len(caller) - 4)}{caller[-4:]}"
