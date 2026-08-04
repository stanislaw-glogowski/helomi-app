from __future__ import annotations

import asyncio
from concurrent.futures import Future
from dataclasses import replace
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any, cast

from helomi.app import ApplicationRuntime, ProgressSnapshot
from helomi.common.events import EventSubscription, ShutdownEvent
from helomi.conversation.events import (
    CancelReply,
    ConversationReady,
    ReplyDraftUpdated,
    ReplyGenerationCompleted,
    ReplyGenerationStarted,
    ReplyPhrase,
)
from helomi.speech.events import (
    AudioDevicesSelected,
    InteractionTimingObserved,
    ReplyPhraseDelivered,
    ReplyPhrasePlaybackStarted,
    SpeechChunkCaptured,
    TranscriptionProgressObserved,
    UserTurnCommitted,
    VADObserved,
    VoiceSessionMode,
    VoiceSessionModeChanged,
    WakeWordObserved,
)

from .state import AgentActivity, DesktopMode, DesktopSnapshot, PhraseState, SystemInfo


class DesktopRuntime:
    """Owns the asyncio loop behind the AppKit main thread."""

    def __init__(
        self,
        *,
        language: str | None = None,
        selected_profile: str | None = None,
    ) -> None:
        self._updates: Queue[DesktopSnapshot] = Queue(maxsize=1)
        self._queue_lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = Event()
        self._terminated = Event()
        self._thread: Thread | None = None
        self._command_active = False
        self._selected_profile_id: str | None = None
        self._runtime: ApplicationRuntime | None = None
        self._shutdown_signal: asyncio.Event | None = None
        self._shutting_down = False
        self._watch_task: asyncio.Task[None] | None = None
        self._events_task: asyncio.Task[None] | None = None
        self._snapshot = DesktopSnapshot(DesktopMode.READY, detail="Loading profiles…")
        self._language = language
        self._startup_profile = selected_profile

    @property
    def terminated(self) -> bool:
        return self._terminated.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Desktop runtime is already started")
        self._thread = Thread(target=self._run, name="helomi-desktop-runtime")
        self._thread.start()
        self._loop_ready.wait()

    def retry(self) -> Future[None] | None:
        if self._command_active or self._loop is None:
            return None
        profile_id = self._selected_profile_id
        if profile_id is None:
            return None
        self._command_active = True
        self._set_snapshot(mode=DesktopMode.RETRYING, detail=None)
        return asyncio.run_coroutine_threadsafe(
            self._start_profile(profile_id), self._loop
        )

    def shutdown(self) -> Future[None] | None:
        if self._loop is None or self._terminated.is_set() or self._shutting_down:
            return None
        self._command_active = True
        self._shutting_down = True
        self._set_snapshot(mode=DesktopMode.SHUTTING_DOWN, detail=None)
        return asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)

    def drain(self) -> DesktopSnapshot | None:
        latest: DesktopSnapshot | None = None
        while True:
            try:
                latest = self._updates.get_nowait()
            except Empty:
                return latest

    def join(self) -> None:
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        try:
            asyncio.run(self._run_async())
        finally:
            self._terminated.set()

    async def _run_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop_ready.set()
        shutdown = asyncio.Event()
        self._shutdown_signal = shutdown
        try:
            async with ApplicationRuntime(
                language=self._language,
                selected_profile=self._startup_profile,
            ) as runtime:
                unsubscribe = runtime.progress.subscribe(self._progress_changed)
                profile = runtime.startup_profile
                self._selected_profile_id = profile.id
                self._snapshot = DesktopSnapshot(
                    DesktopMode.STARTING,
                    profile.name,
                    profile.id,
                    data_path=profile.data_path,
                    system_info=SystemInfo.from_runtime(profile, runtime.settings),
                    agent_activity=(
                        AgentActivity.WAITING
                        if getattr(profile, "wakeword", None) is not None
                        else AgentActivity.LISTENING
                    ),
                )
                self._publish(self._snapshot)
                self._runtime = runtime
                events = self._subscribe_events(runtime)
                self._events_task = asyncio.create_task(
                    self._consume_events(events), name="helomi-desktop-events"
                )
                await self._start_profile(profile.id)
                await shutdown.wait()
                unsubscribe()
                if self._events_task is not None:
                    self._events_task.cancel()
                    await asyncio.gather(self._events_task, return_exceptions=True)
                    self._events_task = None
        except Exception as error:
            self._set_snapshot(mode=DesktopMode.FAILED, detail=str(error))
            await shutdown.wait()

    async def _start_profile(self, profile_id: str) -> None:
        runtime = self._runtime
        if runtime is None:
            self._command_active = False
            return
        try:
            await runtime.start(profile_id)
        except BaseException as error:
            self._command_active = False
            if not self._shutting_down:
                self._set_snapshot(mode=DesktopMode.FAILED, detail=str(error))
            return
        self._command_active = False
        self._set_snapshot(mode=DesktopMode.RUNNING, detail=None)
        self._watch_task = asyncio.create_task(
            self._watch_runtime(profile_id), name="helomi-desktop-watch"
        )

    async def _watch_runtime(self, profile_id: str) -> None:
        try:
            runtime = self._runtime
            if runtime is None:
                return
            await runtime.wait()
        except BaseException as error:
            if not self._shutting_down:
                self._set_snapshot(mode=DesktopMode.FAILED, detail=str(error))
        else:
            if not self._shutting_down and self._shutdown_signal is not None:
                self._shutdown_signal.set()

    async def _shutdown(self) -> None:
        try:
            if self._runtime is not None:
                await self._runtime.shutdown()
        finally:
            if self._shutdown_signal is not None:
                self._shutdown_signal.set()

    def _progress_changed(self, progress: ProgressSnapshot) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._publish_progress, progress)

    def _publish_progress(self, progress: ProgressSnapshot) -> None:
        self._set_snapshot(mode=self._progress_mode(), progress=progress)

    def _subscribe_events(self, runtime: ApplicationRuntime) -> EventSubscription:
        return runtime.subscribe(
            AudioDevicesSelected,
            CancelReply,
            ConversationReady,
            InteractionTimingObserved,
            ReplyDraftUpdated,
            ReplyGenerationCompleted,
            ReplyGenerationStarted,
            ReplyPhrase,
            ReplyPhraseDelivered,
            ReplyPhrasePlaybackStarted,
            ShutdownEvent,
            SpeechChunkCaptured,
            TranscriptionProgressObserved,
            UserTurnCommitted,
            VADObserved,
            VoiceSessionModeChanged,
            WakeWordObserved,
        )

    async def _consume_events(self, events: EventSubscription) -> None:
        with events:
            async for event in events:
                try:
                    self._reduce_event(event)
                    if isinstance(event, ShutdownEvent):
                        return
                finally:
                    events.task_done()

    def _reduce_event(self, event: object) -> None:
        snapshot = self._snapshot
        info = snapshot.system_info
        conversation = snapshot.conversation
        session_mode = snapshot.session_mode
        agent_activity = snapshot.agent_activity
        match event:
            case AudioDevicesSelected(driver, devices):
                info = replace(
                    info,
                    audio_driver=driver,
                    input_device=devices.input.name,
                    output_device=devices.output.name,
                )
            case SpeechChunkCaptured(samples_len):
                info = replace(
                    info, captured_sample_count=info.captured_sample_count + samples_len
                )
            case VADObserved(score, detected):
                info = replace(info, vad_score=score, vad_detected=detected)
            case WakeWordObserved(score, detected):
                info = replace(info, wakeword_score=score, wakeword_detected=detected)
            case InteractionTimingObserved(stage, elapsed_ms):
                timings = dict(info.timings)
                timings[stage] = elapsed_ms
                info = replace(info, timings=tuple(timings.items()))
            case VoiceSessionModeChanged(mode):
                session_mode = mode
                agent_activity = (
                    AgentActivity.WAITING
                    if mode is VoiceSessionMode.WAITING_FOR_WAKE_WORD
                    else AgentActivity.LISTENING
                )
            case TranscriptionProgressObserved(turn_id, content, likely_complete):
                conversation = conversation.update_transcription(turn_id, content)
                agent_activity = (
                    AgentActivity.THINKING
                    if likely_complete
                    else AgentActivity.LISTENING
                )
            case UserTurnCommitted(turn_id, text):
                conversation = conversation.commit_user(turn_id, text)
                agent_activity = AgentActivity.THINKING
            case ReplyGenerationStarted(reply_id):
                conversation = conversation.start_reply(reply_id)
                agent_activity = AgentActivity.THINKING
            case ReplyDraftUpdated(reply_id, text):
                conversation = conversation.update_reply_draft(reply_id, text)
                agent_activity = AgentActivity.THINKING
            case ReplyPhrase(reply_id, phrase_id, text):
                conversation = conversation.queue_phrase(reply_id, phrase_id, text)
                agent_activity = AgentActivity.THINKING
            case ReplyPhrasePlaybackStarted(reply_id, phrase_id):
                conversation = conversation.transition_phrase(
                    reply_id, phrase_id, PhraseState.SPEAKING
                )
                agent_activity = AgentActivity.SPEAKING
            case ReplyPhraseDelivered(reply_id, phrase_id):
                conversation = conversation.transition_phrase(
                    reply_id, phrase_id, PhraseState.DELIVERED
                )
                agent_activity = (
                    AgentActivity.COMPLETED
                    if self._reply_is_delivered(conversation, reply_id)
                    else AgentActivity.SPEAKING
                )
            case ReplyGenerationCompleted(reply_id):
                conversation = conversation.complete_reply(reply_id)
            case CancelReply(_, reply_id):
                conversation = conversation.interrupt_reply(reply_id)
                agent_activity = AgentActivity.INTERRUPTED
            case _:
                return
        self._set_snapshot(
            system_info=info,
            conversation=conversation,
            session_mode=session_mode,
            agent_activity=agent_activity,
        )

    @staticmethod
    def _reply_is_delivered(conversation: object, reply_id: int) -> bool:
        messages = getattr(conversation, "messages", ())
        for message in reversed(messages):
            if getattr(message, "reply_id", None) == reply_id:
                phrases = getattr(message, "phrases", ())
                return bool(phrases) and all(
                    phrase.state is PhraseState.DELIVERED for phrase in phrases
                )
        return False

    def _publish(self, snapshot: DesktopSnapshot) -> None:
        with self._queue_lock:
            try:
                self._updates.put_nowait(snapshot)
            except Full:
                self._updates.get_nowait()
                self._updates.put_nowait(snapshot)

    def _set_snapshot(self, **changes: object) -> None:
        mode = changes.get("mode")
        if mode is not None and mode is not DesktopMode.RUNNING:
            changes.setdefault("agent_activity", AgentActivity.OFFLINE)
        self._snapshot = replace(self._snapshot, **cast(Any, changes))
        self._publish(self._snapshot)

    def _progress_mode(self) -> DesktopMode:
        if self._shutting_down:
            return DesktopMode.SHUTTING_DOWN
        if self._command_active:
            return DesktopMode.STARTING
        if self._selected_profile_id:
            return DesktopMode.RUNNING
        return DesktopMode.READY
