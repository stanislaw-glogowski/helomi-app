from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager, suppress
from types import TracebackType
from typing import Self

from helomi.common.events import Event, EventBus, EventSubscription, ShutdownEvent
from helomi.conversation import (
    BackgroundResult,
    ConversationActivated,
    ConversationReady,
    GenerateReply,
    QuitRequested,
    run_conversation_worker,
)
from helomi.conversation.tools.service import ToolService
from helomi.resources import LocalStore, Profile, ProfileEntry, Settings
from helomi.speech import run_speech_worker
from helomi.speech.events import ReplyPhraseDelivered, SpeechReady
from helomi.speech.synthesis.config import MLXChatterboxSettings, PiperSettings

from .progress import HuggingFaceProgress, ProgressStore


class ApplicationRuntime(AbstractAsyncContextManager):
    """One retryable Helomi worker runtime, owned by a single asyncio loop."""

    def __init__(
        self,
        store: LocalStore | None = None,
        *,
        language: str | None = None,
        selected_profile: str | None = None,
    ) -> None:
        self._store = store or LocalStore(
            language=language,
            selected_profile=selected_profile,
        )
        self._events = EventBus()
        self._progress = ProgressStore()
        self._progress_adapter = HuggingFaceProgress(self._progress)
        self._profiles: tuple[ProfileEntry, ...] = ()
        self._settings: Settings | None = None
        self._backend: asyncio.Task[None] | None = None
        self._starting = False
        self._entered = False

    async def __aenter__(self) -> Self:
        if self._entered:
            raise RuntimeError("Application runtime is already open")
        self._entered = True
        self._settings = self._store.load_settings()
        self._profiles = _validate_profiles(
            tuple(self._store.inspect_profiles()), self._settings
        )
        self._progress_adapter.__enter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        try:
            await self.shutdown()
        finally:
            self._progress_adapter.__exit__(exc_type, exc_value, traceback)
            self._events.close()
            self._entered = False

    @property
    def profiles(self) -> tuple[ProfileEntry, ...]:
        self._require_open()
        return self._profiles

    @property
    def settings(self) -> Settings:
        self._require_open()
        assert self._settings is not None
        return self._settings

    @property
    def default_profile_id(self) -> str | None:
        return self.settings.profiles.default

    @property
    def selected_profile(self) -> Profile | None:
        """Return the explicit configured startup profile, if any."""
        profile_id = self.settings.profiles.selected
        if not profile_id:
            return None
        return self._profile(profile_id, label="Selected")

    @property
    def startup_profile(self) -> Profile:
        """Return the configured startup profile or the validated default."""
        if profile := self.selected_profile:
            return profile
        if profile_id := self.default_profile_id:
            for entry in self.profiles:
                if entry.id == profile_id and entry.profile is not None:
                    return entry.profile
        for entry in self.profiles:
            if entry.profile is not None:
                return entry.profile
        raise FileNotFoundError("No valid profiles are available")

    @property
    def progress(self) -> ProgressStore:
        self._require_open()
        return self._progress

    @property
    def event_bus(self) -> EventBus:
        """Typed domain-event source for frontend projections."""
        self._require_open()
        return self._events

    def subscribe(self, *event_types: type[Event]) -> EventSubscription:
        self._require_open()
        return self._events.subscribe(*event_types)

    async def start(self, profile_id: str) -> None:
        self._require_open()
        if self._backend is not None or self._starting:
            raise RuntimeError("Application runtime is already running")
        profile = self._profile(profile_id)
        self._starting = True
        try:
            self._backend = await _start_runtime(
                self._events, profile, self.settings, self._store
            )
        except BaseException:
            self._backend = None
            raise
        finally:
            self._starting = False

    async def wait(self) -> None:
        self._require_open()
        backend = self._backend
        if backend is None:
            raise RuntimeError("Application runtime is not running")
        try:
            await backend
        finally:
            if self._backend is backend:
                self._backend = None

    async def shutdown(self) -> None:
        if not self._entered:
            return
        backend = self._backend
        self._events.publish(ShutdownEvent())
        if backend is not None:
            await asyncio.gather(backend, return_exceptions=True)
            if self._backend is backend:
                self._backend = None

    def _profile(self, profile_id: str, *, label: str = "Profile") -> Profile:
        for entry in self.profiles:
            if entry.id == profile_id:
                if entry.profile is None:
                    raise ValueError(
                        entry.error or f"{label} profile is invalid: {profile_id}"
                    )
                return entry.profile
        raise ValueError(f"{label} profile does not exist: {profile_id}")

    def _require_open(self) -> None:
        if not self._entered:
            raise RuntimeError("Application runtime is not open")


async def _run_workers(
    event_bus: EventBus,
    profile: Profile,
    settings: Settings,
    store: LocalStore,
    start_event: asyncio.Event,
) -> None:
    async def background_completed(call: object, result: object) -> None:
        from helomi.conversation.tools.domain import ToolCall, ToolResult

        if isinstance(call, ToolCall) and isinstance(result, ToolResult):
            event_bus.publish(
                GenerateReply(
                    BackgroundResult(call.name, result.content, result.is_error),
                    protected_delivery=True,
                )
            )

    tools = (
        ToolService(
            store.text_files(),
            profile.mcp.endpoints,
            on_background_result=background_completed,
        )
        if hasattr(store, "text_files")
        else None
    )
    if tools is not None:
        await tools.start()
    quit_ready = asyncio.Event()
    quit_coordinator = asyncio.create_task(
        _shutdown_after_quit(event_bus, quit_ready),
        name="helomi-quit-coordinator",
    )
    try:
        await quit_ready.wait()
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(
                run_conversation_worker(
                    event_bus,
                    profile.conversation,
                    settings.conversation,
                    start_event,
                    tools,
                )
            )
            tasks.create_task(
                run_speech_worker(
                    profile,
                    settings.speech,
                    store,
                    event_bus,
                    start_event,
                )
            )
    finally:
        quit_coordinator.cancel()
        with suppress(asyncio.CancelledError):
            await quit_coordinator
        if tools is not None:
            await tools.stop()


async def _shutdown_after_quit(event_bus: EventBus, ready: asyncio.Event) -> None:
    with event_bus.subscribe(
        QuitRequested, ReplyPhraseDelivered, ShutdownEvent
    ) as events:
        last_delivered: tuple[int, int] | None = None
        ready.set()
        async for event in events:
            try:
                if isinstance(event, ShutdownEvent):
                    return
                if isinstance(event, ReplyPhraseDelivered):
                    last_delivered = (event.reply_id, event.phrase_id)
                    continue
                if not isinstance(event, QuitRequested):
                    continue
                expected = (event.reply_id, event.final_phrase_id)
                if event.final_phrase_id == 0 or last_delivered == expected:
                    event_bus.publish(ShutdownEvent())
                    return
                while True:
                    delivered = await asyncio.wait_for(events.__anext__(), timeout=10)
                    try:
                        if isinstance(delivered, ShutdownEvent):
                            return
                        if isinstance(delivered, ReplyPhraseDelivered):
                            last_delivered = (
                                delivered.reply_id,
                                delivered.phrase_id,
                            )
                        if last_delivered == expected:
                            event_bus.publish(ShutdownEvent())
                            return
                    finally:
                        events.task_done()
            except TimeoutError:
                event_bus.publish(ShutdownEvent())
                return
            finally:
                events.task_done()


async def _wait_until_ready(events: EventSubscription) -> None:
    conversation_ready = False
    speech_ready = False
    async for event in events:
        try:
            match event:
                case ConversationReady():
                    conversation_ready = True
                case SpeechReady():
                    speech_ready = True
                case ShutdownEvent():
                    raise asyncio.CancelledError
            if conversation_ready and speech_ready:
                return
        finally:
            events.task_done()


async def _start_runtime(
    event_bus: EventBus,
    profile: Profile,
    settings: Settings,
    store: LocalStore,
) -> asyncio.Task[None]:
    start_event = asyncio.Event()
    with event_bus.subscribe(
        ConversationReady, SpeechReady, ShutdownEvent
    ) as readiness:
        backend = asyncio.create_task(
            _run_workers(event_bus, profile, settings, store, start_event),
            name="helomi-runtime",
        )
        ready = asyncio.create_task(
            _wait_until_ready(readiness), name="helomi-runtime-readiness"
        )
        done, _ = await asyncio.wait(
            (backend, ready), return_when=asyncio.FIRST_COMPLETED
        )
        if backend in done:
            ready.cancel()
            with suppress(asyncio.CancelledError):
                await ready
            await backend
        else:
            await ready
            start_event.set()
            if profile.wakeword is None:
                event_bus.publish(GenerateReply(ConversationActivated()))
            return backend
    raise RuntimeError("Helomi runtime stopped before it became ready")


def _validate_profiles(
    profiles: tuple[ProfileEntry, ...], settings: Settings
) -> tuple[ProfileEntry, ...]:
    validated: list[ProfileEntry] = []
    for entry in profiles:
        if entry.profile is None:
            validated.append(entry)
            continue
        try:
            _validate_runtime_profile(entry.profile, settings)
        except Exception as error:
            validated.append(
                ProfileEntry(
                    id=entry.id,
                    name=entry.name,
                    error=f"Incompatible with current settings: {error}",
                )
            )
        else:
            validated.append(entry)
    return tuple(validated)


def _validate_runtime_profile(profile: Profile, settings: Settings) -> None:
    if settings.conversation.language_model.adapter == "mlx":
        models = profile.conversation.models_mlx
    else:
        models = profile.conversation.models_langchain
    _ = tuple(
        model.model_id
        for model in (models.fast, models.detailed, models.classifier)
        if model is not None
    )
    match settings.speech.stt.adapter:
        case "mlx:parakeet-tdt":
            _ = profile.stt_mlx_parakeet_tdt
        case "mlx:qwen3-asr":
            _ = profile.stt_mlx_qwen3_asr
        case "mlx:whisper":
            _ = profile.stt_mlx_whisper
    match settings.speech.tts:
        case PiperSettings():
            _ = profile.tts_piper
        case MLXChatterboxSettings():
            _ = profile.tts_mlx_chatterbox
